"""Shop-managed delivery order state machine.

    PENDING -> SHOP_CONFIRMED -> PREPARING -> OUT_FOR_DELIVERY -> DELIVERED
       |            |               |               |
       +------------+---cancel------+               +--fail--> DELIVERY_FAILED --return--> RETURNED_TO_SHOP

Stock is held at SHOP_CONFIRMED and released on cancel or return. Payment is cash on
delivery in V1; payment_method/payment_status keep the model open for UPI/cards later.
"""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.core.errors import Conflict, Forbidden, InvalidTransition, NotFound
from app.models import (
    InventoryReason,
    Order,
    OrderItem,
    Product,
    Role,
    SaleSource,
    Shop,
    User,
)
from app.models import (
    OrderStatus as OS,
)
from app.services.fulfillment_common import record_event, record_sale
from app.services.inventory import change_stock
from app.services.notifications import notify
from app.utils.geo import haversine_km
from app.utils.text import short_code

ACTIVE = {OS.PENDING, OS.SHOP_CONFIRMED, OS.PREPARING, OS.OUT_FOR_DELIVERY}
PENDING_TIMEOUT_MINUTES = 60

TRANSITIONS: dict[tuple[OS, str], tuple[OS, set[str]]] = {
    (OS.PENDING, "confirm"): (OS.SHOP_CONFIRMED, {"owner"}),
    (OS.PENDING, "cancel"): (OS.CANCELLED, {"customer", "owner", "system"}),
    (OS.SHOP_CONFIRMED, "prepare"): (OS.PREPARING, {"owner"}),
    (OS.SHOP_CONFIRMED, "cancel"): (OS.CANCELLED, {"customer", "owner"}),
    (OS.PREPARING, "dispatch"): (OS.OUT_FOR_DELIVERY, {"owner"}),
    (OS.PREPARING, "cancel"): (OS.CANCELLED, {"owner"}),
    (OS.OUT_FOR_DELIVERY, "deliver"): (OS.DELIVERED, {"owner"}),
    (OS.OUT_FOR_DELIVERY, "fail"): (OS.DELIVERY_FAILED, {"owner"}),
    (OS.DELIVERY_FAILED, "return"): (OS.RETURNED_TO_SHOP, {"owner"}),
}

CUSTOMER_MESSAGES = {
    OS.SHOP_CONFIRMED: ("Order confirmed", "{shop} confirmed your order and set the items aside."),
    OS.PREPARING: ("Packing your order", "{shop} is preparing your order."),
    OS.OUT_FOR_DELIVERY: ("Out for delivery", "Your order from {shop} is on the way. Keep cash ready: Rs {total:.0f}."),
    OS.DELIVERED: ("Delivered", "Your order from {shop} was delivered. How did it go? Leave a quick review."),
    OS.DELIVERY_FAILED: ("Delivery attempt failed", "{shop} could not complete the delivery. They may contact you."),
    OS.CANCELLED: ("Order cancelled", "Your order from {shop} was cancelled."),
}


def allowed_actions(order: Order, actor: str) -> list[str]:
    return [a for (s, a), (_, actors) in TRANSITIONS.items() if s == order.status and actor in actors]


def quote_delivery(shop: Shop, lat: float, lng: float, subtotal: float) -> dict:
    distance = haversine_km(shop.lat, shop.lng, lat, lng)
    eligible = shop.offers_delivery and distance <= shop.delivery_radius_km
    fee = shop.delivery_fee
    if shop.free_delivery_above is not None and subtotal >= shop.free_delivery_above:
        fee = 0.0
    reason = None
    if not shop.offers_delivery:
        reason = "This shop offers pickup only"
    elif not eligible:
        reason = f"You are {distance:.1f} km away; {shop.name} delivers within {shop.delivery_radius_km:.0f} km"
    return {
        "eligible": eligible,
        "distance_km": round(distance, 2),
        "delivery_fee": round(fee, 2) if eligible else None,
        "free_delivery_above": shop.free_delivery_above,
        "reason": reason,
    }


def create_order(
    db: Session,
    customer: User,
    items: list[tuple[int, int]],
    address: str,
    lat: float,
    lng: float,
    phone: str,
    note: str | None,
) -> Order:
    if not items:
        raise Conflict("Add at least one item")
    products: list[tuple[Product, int]] = []
    for product_id, qty in items:
        p = db.get(Product, product_id)
        if p is None or not p.is_active:
            raise NotFound("One of the items is no longer listed")
        if qty < 1 or qty > 50:
            raise Conflict("Quantity must be between 1 and 50")
        if p.quantity < qty:
            raise Conflict(f"Only {p.quantity} of {p.name} in stock", code="insufficient_stock")
        products.append((p, qty))
    shop_ids = {p.shop_id for p, _ in products}
    if len(shop_ids) != 1:
        raise Conflict("A delivery order can contain items from one shop only")
    shop = products[0][0].shop
    if not shop.is_active:
        raise Conflict("This shop is not taking orders right now")

    subtotal = round(sum(p.price * q for p, q in products), 2)
    quote = quote_delivery(shop, lat, lng, subtotal)
    if not quote["eligible"]:
        raise Conflict(quote["reason"], code="delivery_unavailable")

    order = Order(
        code=short_code("D"),
        customer_id=customer.id,
        shop_id=shop.id,
        status=OS.PENDING,
        delivery_address=address.strip(),
        delivery_lat=lat,
        delivery_lng=lng,
        contact_phone=phone.strip(),
        distance_km=quote["distance_km"],
        subtotal=subtotal,
        delivery_fee=quote["delivery_fee"],
        total=round(subtotal + quote["delivery_fee"], 2),
        note=(note or "").strip() or None,
        items=[OrderItem(product_id=p.id, name=p.name, unit_price=p.price, quantity=q) for p, q in products],
    )
    db.add(order)
    db.flush()
    record_event(db, entity="order", entity_id=order.id, shop_id=shop.id, from_status=None,
                 to_status=OS.PENDING, actor_role="customer", actor_id=customer.id)
    summary = ", ".join(f"{q} x {p.name}" for p, q in products)
    notify(db, shop.owner_id, "order_new", f"New delivery order {order.code}",
           f"{summary} to {address[:60]} ({quote['distance_km']} km). COD Rs {order.total:.0f}.", "/shop/orders")
    db.commit()
    db.refresh(order)
    return order


def _actor_for(user: User | None, order: Order, db: Session) -> str:
    if user is None:
        return "system"
    if user.role == Role.CUSTOMER and order.customer_id == user.id:
        return "customer"
    if user.role == Role.OWNER and db.get(Shop, order.shop_id).owner_id == user.id:
        return "owner"
    if user.role == Role.ADMIN:
        return "admin"
    raise Forbidden("This order belongs to someone else")


def transition(db: Session, order: Order, action: str, user: User | None, reason: str | None = None) -> Order:
    actor = _actor_for(user, order, db)
    key = (order.status, action)
    if key not in TRANSITIONS:
        raise InvalidTransition(f"Cannot {action} an order that is {order.status.replace('_', ' ').lower()}")
    to_status, actors = TRANSITIONS[key]
    if actor not in actors and actor != "admin":
        raise Forbidden(f"Only the {' or '.join(sorted(actors))} can {action} this order")

    now = utcnow()
    from_status = order.status
    shop = db.get(Shop, order.shop_id)
    actor_id = user.id if user else None

    if action == "confirm":
        # All-or-nothing: if any item is short, change_stock raises and the whole transaction rolls back.
        try:
            for item in order.items:
                change_stock(db, item.product, -item.quantity, InventoryReason.ORDER_HOLD, actor_id)
        except Exception:
            db.rollback()
            raise
        order.stock_held = True
    elif action == "deliver":
        order.delivered_at = now
        order.payment_status = "paid"  # COD collected at the door
        order.stock_held = False
        for item in order.items:
            record_sale(db, product=item.product, quantity=item.quantity, unit_price=item.unit_price,
                        source=SaleSource.ORDER, basket_id=order.code, customer_id=order.customer_id)
    elif action in {"cancel", "return"}:
        if order.stock_held:
            for item in order.items:
                change_stock(db, item.product, item.quantity, InventoryReason.ORDER_RELEASE, actor_id)
            order.stock_held = False
        order.closed_at = now
        order.close_reason = (reason or "").strip() or None
    elif action == "fail":
        order.close_reason = (reason or "").strip() or None

    order.status = to_status

    if actor != "customer" and to_status in CUSTOMER_MESSAGES:
        title, body = CUSTOMER_MESSAGES[to_status]
        body = body.format(shop=shop.name, total=order.total)
        if order.close_reason and to_status in {OS.CANCELLED, OS.DELIVERY_FAILED}:
            body += f" Reason: {order.close_reason}"
        notify(db, order.customer_id, f"order_{to_status.lower()}", title, body, f"/account/orders/{order.id}")
    if actor == "customer" and to_status == OS.CANCELLED:
        notify(db, shop.owner_id, "order_cancelled", f"Order {order.code} cancelled by customer", None, "/shop/orders")

    record_event(db, entity="order", entity_id=order.id, shop_id=order.shop_id, from_status=from_status,
                 to_status=to_status, actor_role=actor, actor_id=actor_id, note=reason)
    db.commit()
    db.refresh(order)
    return order


def cancel_stale_pending(db: Session) -> int:
    cutoff = utcnow() - timedelta(minutes=PENDING_TIMEOUT_MINUTES)
    stale = db.scalars(select(Order).where(Order.status == OS.PENDING, Order.created_at <= cutoff)).all()
    for order in stale:
        try:
            transition(db, order, "cancel", None, "The shop did not respond within an hour")
        except Exception:
            db.rollback()
    return len(stale)
