"""Customer: reservations, delivery orders, reviews, dashboard, notifications."""
from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.ai.recommend import bundle_for
from app.core.database import utcnow
from app.core.deps import DB, CurrentUser, CustomerUser
from app.core.errors import Conflict, NotFound
from app.models import (
    Notification,
    Order,
    OrderStatus,
    Product,
    Reservation,
    ReservationStatus,
    Review,
    SalesRecord,
    Shop,
    StatusEvent,
)
from app.schemas.requests import NotificationsReadIn, OrderIn, OrderQuoteIn, ReservationIn, ReviewIn, TransitionIn
from app.schemas.serializers import listing, notification_out, order_out, reservation_out, shop_brief
from app.services import orders as order_service
from app.services import reservations as reservation_service
from app.services.search import recent_searches
from app.utils.geo import haversine_km

router = APIRouter(tags=["customer"])


def _events(db, entity: str, entity_id: int) -> list[StatusEvent]:
    return db.scalars(
        select(StatusEvent).where(StatusEvent.entity == entity, StatusEvent.entity_id == entity_id)
        .order_by(StatusEvent.created_at, StatusEvent.id)
    ).all()


def _reviewed_ids(db, customer_id: int) -> tuple[set[int], set[int]]:
    rows = db.execute(select(Review.reservation_id, Review.order_id).where(Review.customer_id == customer_id)).all()
    return {r for r, _ in rows if r}, {o for _, o in rows if o}


def _res_json(db, r: Reservation, reviewed: set[int], with_events: bool = False) -> dict:
    return reservation_out(r, actions=reservation_service.allowed_actions(r, "customer"),
                           events=_events(db, "reservation", r.id) if with_events else None,
                           reviewed=r.id in reviewed)


def _order_json(db, o: Order, reviewed: set[int], with_events: bool = False) -> dict:
    return order_out(o, actions=order_service.allowed_actions(o, "customer"),
                     events=_events(db, "order", o.id) if with_events else None, reviewed=o.id in reviewed)


# ------------------------------------------------------------------ reservations

@router.post("/reservations")
def create_reservation(body: ReservationIn, user: CustomerUser, db: DB):
    r = reservation_service.create_reservation(db, user, body.product_id, body.quantity, body.note)
    return _res_json(db, r, set(), with_events=True)


@router.get("/reservations")
def my_reservations(user: CustomerUser, db: DB, scope: Literal["active", "past", "all"] = "all"):
    reservation_service.expire_due(db)
    stmt = select(Reservation).where(Reservation.customer_id == user.id).order_by(Reservation.created_at.desc())
    if scope == "active":
        stmt = stmt.where(Reservation.status.in_(reservation_service.ACTIVE))
    elif scope == "past":
        stmt = stmt.where(Reservation.status.not_in(reservation_service.ACTIVE))
    reviewed, _ = _reviewed_ids(db, user.id)
    return [_res_json(db, r, reviewed) for r in db.scalars(stmt.limit(100))]


def _own_reservation(db, user, reservation_id: int) -> Reservation:
    r = db.get(Reservation, reservation_id)
    if r is None or r.customer_id != user.id:
        raise NotFound("Reservation not found")
    return r


@router.get("/reservations/{reservation_id}")
def reservation_detail(reservation_id: int, user: CustomerUser, db: DB):
    reservation_service.expire_due(db)
    r = _own_reservation(db, user, reservation_id)
    reviewed, _ = _reviewed_ids(db, user.id)
    return _res_json(db, r, reviewed, with_events=True)


@router.post("/reservations/{reservation_id}/cancel")
def cancel_reservation(reservation_id: int, body: TransitionIn, user: CustomerUser, db: DB):
    r = _own_reservation(db, user, reservation_id)
    r = reservation_service.transition(db, r, "cancel", user, body.reason)
    return _res_json(db, r, set(), with_events=True)


# ------------------------------------------------------------------ delivery orders

@router.post("/orders/quote")
def quote(body: OrderQuoteIn, db: DB):
    products = [db.get(Product, i.product_id) for i in body.items]
    if any(p is None for p in products):
        raise NotFound("One of the items is no longer listed")
    subtotal = sum(p.price * i.quantity for p, i in zip(products, body.items))
    shop = products[0].shop
    return {**order_service.quote_delivery(shop, body.lat, body.lng, subtotal), "subtotal": round(subtotal, 2)}


@router.post("/orders")
def create_order(body: OrderIn, user: CustomerUser, db: DB):
    o = order_service.create_order(db, user, [(i.product_id, i.quantity) for i in body.items], body.address,
                                   body.lat, body.lng, body.phone, body.note)
    return _order_json(db, o, set(), with_events=True)


@router.get("/orders")
def my_orders(user: CustomerUser, db: DB, scope: Literal["active", "past", "all"] = "all"):
    stmt = select(Order).options(selectinload(Order.items)).where(Order.customer_id == user.id) \
        .order_by(Order.created_at.desc())
    if scope == "active":
        stmt = stmt.where(Order.status.in_(order_service.ACTIVE))
    elif scope == "past":
        stmt = stmt.where(Order.status.not_in(order_service.ACTIVE))
    _, reviewed = _reviewed_ids(db, user.id)
    return [_order_json(db, o, reviewed) for o in db.scalars(stmt.limit(100))]


def _own_order(db, user, order_id: int) -> Order:
    o = db.get(Order, order_id)
    if o is None or o.customer_id != user.id:
        raise NotFound("Order not found")
    return o


@router.get("/orders/{order_id}")
def order_detail(order_id: int, user: CustomerUser, db: DB):
    o = _own_order(db, user, order_id)
    _, reviewed = _reviewed_ids(db, user.id)
    return _order_json(db, o, reviewed, with_events=True)


@router.post("/orders/{order_id}/cancel")
def cancel_order(order_id: int, body: TransitionIn, user: CustomerUser, db: DB):
    o = _own_order(db, user, order_id)
    o = order_service.transition(db, o, "cancel", user, body.reason)
    return _order_json(db, o, set(), with_events=True)


# ------------------------------------------------------------------ reviews

@router.post("/reviews")
def create_review(body: ReviewIn, user: CustomerUser, db: DB):
    if body.reservation_id:
        r = _own_reservation(db, user, body.reservation_id)
        if r.status != ReservationStatus.COMPLETED:
            raise Conflict("You can review a pickup once it is completed")
        shop_id, product_id = r.shop_id, r.product_id
        delivery_rating = None
    else:
        o = _own_order(db, user, body.order_id)
        if o.status != OrderStatus.DELIVERED:
            raise Conflict("You can review a delivery once it has arrived")
        shop_id, product_id = o.shop_id, o.items[0].product_id if o.items else None
        delivery_rating = body.delivery_rating
    review = Review(customer_id=user.id, shop_id=shop_id, product_id=product_id, reservation_id=body.reservation_id,
                    order_id=body.order_id, rating=body.rating, accuracy_rating=body.accuracy_rating,
                    delivery_rating=delivery_rating, comment=(body.comment or "").strip() or None)
    db.add(review)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("You have already reviewed this purchase", code="duplicate_review") from None
    return {"id": review.id, "ok": True}


# ------------------------------------------------------------------ dashboard

@router.get("/me/dashboard")
def dashboard(user: CustomerUser, db: DB):
    reservation_service.expire_due(db)
    reviewed_res, reviewed_orders = _reviewed_ids(db, user.id)
    active_res = db.scalars(select(Reservation).where(
        Reservation.customer_id == user.id, Reservation.status.in_(reservation_service.ACTIVE))
        .order_by(Reservation.expires_at)).all()
    active_orders = db.scalars(select(Order).where(
        Order.customer_id == user.id, Order.status.in_(order_service.ACTIVE)).order_by(Order.created_at.desc())).all()
    past_res = db.scalars(select(Reservation).where(
        Reservation.customer_id == user.id, Reservation.status.not_in(reservation_service.ACTIVE))
        .order_by(Reservation.updated_at.desc()).limit(6)).all()
    past_orders = db.scalars(select(Order).where(
        Order.customer_id == user.id, Order.status.not_in(order_service.ACTIVE))
        .order_by(Order.updated_at.desc()).limit(6)).all()
    history = sorted(
        [_res_json(db, r, reviewed_res) for r in past_res] + [_order_json(db, o, reviewed_orders) for o in past_orders],
        key=lambda x: x["closed_at"] or x.get("completed_at") or x.get("delivered_at") or x["created_at"],
        reverse=True,
    )[:8]
    to_review = [h for h in history if not h["reviewed"] and h["status"] in {"COMPLETED", "DELIVERED"}]

    stats = {
        "completed_pickups": db.scalar(select(func.count()).select_from(Reservation).where(
            Reservation.customer_id == user.id, Reservation.status == ReservationStatus.COMPLETED)) or 0,
        "delivered_orders": db.scalar(select(func.count()).select_from(Order).where(
            Order.customer_id == user.id, Order.status == OrderStatus.DELIVERED)) or 0,
        "shops_visited": db.scalar(select(func.count(func.distinct(SalesRecord.shop_id))).where(
            SalesRecord.customer_id == user.id)) or 0,
    }
    return {
        "active_reservations": [_res_json(db, r, reviewed_res) for r in active_res],
        "active_orders": [_order_json(db, o, reviewed_orders) for o in active_orders],
        "history": history,
        "to_review": to_review[:3],
        "recent_searches": recent_searches(db, user.id),
        "recommendations": _recommendations_for(db, user),
        "stats": stats,
    }


def _recommendations_for(db, user) -> list[dict]:
    """Apriori bundles for things this customer bought recently, available near their last shop."""
    bought = db.execute(
        select(SalesRecord.catalog_item_id, Shop.lat, Shop.lng)
        .join(Shop, Shop.id == SalesRecord.shop_id)
        .where(SalesRecord.customer_id == user.id, SalesRecord.catalog_item_id.is_not(None))
        .order_by(SalesRecord.sold_at.desc()).limit(10)
    ).all()
    if not bought:
        return []
    owned = {b.catalog_item_id for b in bought}
    lat = user.home_lat or bought[0].lat
    lng = user.home_lng or bought[0].lng
    picks: list[dict] = []
    seen: set[int] = set()
    for b in bought:
        for rec in bundle_for(db, b.catalog_item_id, limit=3):
            cid = rec["catalog_item_id"]
            if cid in owned or cid in seen:
                continue
            offers = db.scalars(select(Product).join(Shop).where(
                Product.catalog_item_id == cid, Product.is_active.is_(True), Product.quantity > 0,
                Shop.is_active.is_(True))).all()
            if not offers:
                continue
            best = min(offers, key=lambda o: haversine_km(lat, lng, o.shop.lat, o.shop.lng))
            seen.add(cid)
            picks.append({"confidence": rec["confidence"], "lift": rec["lift"],
                          "offer": listing(best, shop_brief(best.shop, haversine_km(lat, lng, best.shop.lat,
                                                                                     best.shop.lng)))})
            if len(picks) >= 4:
                return picks
    return picks


# ------------------------------------------------------------------ notifications (all roles)

@router.get("/notifications")
def notifications(user: CurrentUser, db: DB, limit: int = Query(30, ge=1, le=100)):
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id)
                      .order_by(Notification.created_at.desc()).limit(limit)).all()
    unread = db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None))) or 0
    return {"items": [notification_out(n) for n in rows], "unread": unread}


@router.get("/notifications/unread-count")
def unread_count(user: CurrentUser, db: DB):
    # Also the heartbeat that keeps reservation timers honest while someone has the app open.
    reservation_service.expire_due(db)
    return {"unread": db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None))) or 0}


@router.post("/notifications/read")
def mark_read(body: NotificationsReadIn, user: CurrentUser, db: DB):
    stmt = update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if body.ids:
        stmt = stmt.where(Notification.id.in_(body.ids))
    db.execute(stmt.values(read_at=utcnow()))
    db.commit()
    return {"ok": True}

