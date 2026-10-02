"""Pickup reservation state machine.

    REQUESTED --confirm--> CONFIRMED --ready--> READY_FOR_PICKUP --complete--> COMPLETED
        |                      |                      |
        +--reject--> REJECTED  +------cancel / expire-+--> CANCELLED / EXPIRED

Stock is held when the shop confirms (so the unit is physically set aside) and returned
to stock if the reservation is cancelled or expires.
"""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import utcnow
from app.core.errors import Conflict, Forbidden, InvalidTransition, NotFound
from app.models import (
    InventoryReason,
    Product,
    Reservation,
    Role,
    SaleSource,
    Shop,
    User,
)
from app.models import (
    ReservationStatus as RS,
)
from app.services.fulfillment_common import record_event, record_sale
from app.services.inventory import change_stock
from app.services.notifications import notify
from app.utils.text import short_code

ACTIVE = {RS.REQUESTED, RS.CONFIRMED, RS.READY_FOR_PICKUP}
MAX_ACTIVE_PER_CUSTOMER = 5

# (from_status, action) -> (to_status, who may do it)
TRANSITIONS: dict[tuple[RS, str], tuple[RS, set[str]]] = {
    (RS.REQUESTED, "confirm"): (RS.CONFIRMED, {"owner"}),
    (RS.REQUESTED, "reject"): (RS.REJECTED, {"owner"}),
    (RS.REQUESTED, "cancel"): (RS.CANCELLED, {"customer"}),
    (RS.REQUESTED, "expire"): (RS.EXPIRED, {"system"}),
    (RS.CONFIRMED, "ready"): (RS.READY_FOR_PICKUP, {"owner"}),
    (RS.CONFIRMED, "complete"): (RS.COMPLETED, {"owner"}),
    (RS.CONFIRMED, "cancel"): (RS.CANCELLED, {"customer", "owner"}),
    (RS.CONFIRMED, "expire"): (RS.EXPIRED, {"system"}),
    (RS.READY_FOR_PICKUP, "complete"): (RS.COMPLETED, {"owner"}),
    (RS.READY_FOR_PICKUP, "cancel"): (RS.CANCELLED, {"customer", "owner"}),
    (RS.READY_FOR_PICKUP, "expire"): (RS.EXPIRED, {"system"}),
}


def allowed_actions(reservation: Reservation, actor: str) -> list[str]:
    return [action for (status, action), (_, actors) in TRANSITIONS.items() if status == reservation.status and actor in actors]


def create_reservation(db: Session, customer: User, product_id: int, quantity: int, note: str | None) -> Reservation:
    product = db.get(Product, product_id)
    if product is None or not product.is_active:
        raise NotFound("This product is no longer listed")
    shop = product.shop
    if not shop.is_active or not shop.offers_pickup:
        raise Conflict("This shop is not accepting pickup reservations right now")
    if quantity < 1 or quantity > 20:
        raise Conflict("You can reserve between 1 and 20 units")
    if product.quantity < quantity:
        raise Conflict(
            f"Only {product.quantity} in stock" if product.quantity else "This item is out of stock",
            code="insufficient_stock",
        )

    active = db.scalars(
        select(Reservation).where(Reservation.customer_id == customer.id, Reservation.status.in_(ACTIVE))
    ).all()
    if any(r.product_id == product.id for r in active):
        raise Conflict("You already have an active reservation for this item", code="duplicate_reservation")
    if len(active) >= MAX_ACTIVE_PER_CUSTOMER:
        raise Conflict(f"You can hold up to {MAX_ACTIVE_PER_CUSTOMER} active reservations at a time")

    now = utcnow()
    res = Reservation(
        code=short_code("R"),
        customer_id=customer.id,
        shop_id=shop.id,
        product_id=product.id,
        quantity=quantity,
        unit_price=product.price,
        status=RS.REQUESTED,
        note=(note or "").strip() or None,
        hold_minutes=shop.hold_minutes,
        expires_at=now + timedelta(minutes=settings.request_response_minutes),
    )
    db.add(res)
    db.flush()
    record_event(db, entity="reservation", entity_id=res.id, shop_id=shop.id, from_status=None,
                 to_status=RS.REQUESTED, actor_role="customer", actor_id=customer.id)
    notify(db, shop.owner_id, "reservation_new", f"New reservation {res.code}",
           f"{customer.name} wants {quantity} x {product.name}. Confirm within {settings.request_response_minutes} min.",
           "/shop/reservations")
    db.commit()
    db.refresh(res)
    return res


def _actor_for(user: User | None, res: Reservation, db: Session) -> str:
    if user is None:
        return "system"
    if user.role == Role.CUSTOMER and res.customer_id == user.id:
        return "customer"
    if user.role == Role.OWNER and db.get(Shop, res.shop_id).owner_id == user.id:
        return "owner"
    if user.role == Role.ADMIN:
        return "admin"
    raise Forbidden("This reservation belongs to someone else")


def transition(db: Session, res: Reservation, action: str, user: User | None, reason: str | None = None) -> Reservation:
    actor = _actor_for(user, res, db)
    key = (res.status, action)
    if key not in TRANSITIONS:
        raise InvalidTransition(f"Cannot {action} a reservation that is {res.status.replace('_', ' ').lower()}")
    to_status, actors = TRANSITIONS[key]
    if actor not in actors and actor != "admin":
        raise Forbidden(f"Only the {' or '.join(sorted(actors))} can {action} this reservation")

    now = utcnow()
    from_status = res.status
    product = db.get(Product, res.product_id)
    shop = db.get(Shop, res.shop_id)

    if action == "confirm":
        change_stock(db, product, -res.quantity, InventoryReason.RESERVATION_HOLD, user.id if user else None)
        res.stock_held = True
        res.confirmed_at = now
        res.expires_at = now + timedelta(minutes=res.hold_minutes)
        notify(db, res.customer_id, "reservation_confirmed", f"{shop.name} confirmed your reservation",
               f"{res.quantity} x {product.name} is held for you for {res.hold_minutes} minutes. Code {res.code}.",
               f"/account/reservations/{res.id}")
    elif action == "ready":
        res.ready_at = now
        res.expires_at = max(res.expires_at, now + timedelta(minutes=res.hold_minutes))
        notify(db, res.customer_id, "reservation_ready", "Ready for pickup",
               f"{product.name} is packed at {shop.name}. Show code {res.code} at the counter.",
               f"/account/reservations/{res.id}")
    elif action == "complete":
        res.completed_at = now
        res.stock_held = False  # the held unit left the shop with the customer
        record_sale(db, product=product, quantity=res.quantity, unit_price=res.unit_price,
                    source=SaleSource.RESERVATION, basket_id=res.code, customer_id=res.customer_id)
        notify(db, res.customer_id, "reservation_completed", "Pickup complete",
               f"Thanks for shopping at {shop.name}. How was it? Leave a quick review.",
               f"/account/reservations/{res.id}")
    else:  # reject / cancel / expire
        if res.stock_held:
            change_stock(db, product, res.quantity, InventoryReason.RESERVATION_RELEASE, user.id if user else None)
            res.stock_held = False
        res.closed_at = now
        res.close_reason = (reason or "").strip() or None
        if action == "reject":
            notify(db, res.customer_id, "reservation_rejected", f"{shop.name} could not hold your item",
                   res.close_reason or "The shop was unable to confirm this reservation. Try another shop nearby.",
                   f"/search?q={product.name}")
        elif action == "cancel" and actor == "customer":
            notify(db, shop.owner_id, "reservation_cancelled", f"Reservation {res.code} cancelled by customer",
                   f"{res.quantity} x {product.name} is back in stock.", "/shop/reservations")
        elif action == "cancel":
            notify(db, res.customer_id, "reservation_cancelled", f"{shop.name} cancelled your reservation",
                   res.close_reason or "The shop cancelled this reservation.", f"/account/reservations/{res.id}")
        elif action == "expire":
            was_request = from_status == RS.REQUESTED
            notify(db, res.customer_id, "reservation_expired",
                   "Reservation request timed out" if was_request else "Your reservation expired",
                   f"{shop.name} did not respond in time." if was_request
                   else f"The hold on {product.name} at {shop.name} has ended.",
                   f"/account/reservations/{res.id}")
            if not was_request:
                notify(db, shop.owner_id, "reservation_expired", f"Reservation {res.code} expired",
                       f"{res.quantity} x {product.name} has been returned to stock.", "/shop/reservations")

    res.status = to_status
    record_event(db, entity="reservation", entity_id=res.id, shop_id=res.shop_id, from_status=from_status,
                 to_status=to_status, actor_role=actor, actor_id=user.id if user else None, note=reason)
    db.commit()
    db.refresh(res)
    return res


def expire_due(db: Session) -> int:
    """Expire reservations whose timer has run out. Called by the scheduler and lazily on reads."""
    now = utcnow()
    due = db.scalars(select(Reservation).where(Reservation.status.in_(ACTIVE), Reservation.expires_at <= now)).all()
    for res in due:
        try:
            transition(db, res, "expire", None)
        except Exception:  # never let one bad row stop the sweep
            db.rollback()
    return len(due)
