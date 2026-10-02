"""Pickup reservation state machine.

    REQUESTED --confirm--> CONFIRMED --ready--> READY_FOR_PICKUP --complete--> COMPLETED
        |                      |                      |
        +--reject--> REJECTED  +------cancel / expire-+--> CANCELLED / EXPIRED

Stock is held when the shop confirms (so the unit is physically set aside) and returned
to stock if the reservation is cancelled or expires.
"""
import logging
from datetime import timedelta

from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.core.database import Database, utcnow
from app.core.errors import Conflict, Forbidden, InvalidTransition, NotFound
from app.models import (
    InventoryReason,
    Reservation,
    Role,
    SaleSource,
    User,
)
from app.models import (
    ReservationStatus as RS,
)
from app.services.fulfillment_common import record_event, record_sales
from app.services.inventory import change_stock
from app.services.notifications import notify
from app.utils.text import short_code

log = logging.getLogger(__name__)

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


def create_reservation(db: Database, customer: User, product_id: int, quantity: int, note: str | None) -> Reservation:
    try:
        return db.transaction(lambda: _create_reservation(db, customer, product_id, quantity, note))
    except DuplicateKeyError:
        # The unique partial index on (customer, product) for active reservations caught a double submit.
        raise Conflict("You already have an active reservation for this item", code="duplicate_reservation") from None


def _create_reservation(db: Database, customer: User, product_id: int, quantity: int, note: str | None) -> Reservation:
    product = db.products.get(product_id)
    if product is None or not product.is_active:
        raise NotFound("This product is no longer listed")
    shop = db.shops.get(product.shop_id)
    if not shop.is_active or not shop.offers_pickup:
        raise Conflict("This shop is not accepting pickup reservations right now")
    if quantity < 1 or quantity > 20:
        raise Conflict("You can reserve between 1 and 20 units")
    if product.quantity < quantity:
        raise Conflict(
            f"Only {product.quantity} in stock" if product.quantity else "This item is out of stock",
            code="insufficient_stock",
        )

    active = db.reservations.find_raw({"customer_id": customer.id, "status": {"$in": list(ACTIVE)}}, {"product_id": 1})
    if any(r["product_id"] == product.id for r in active):
        raise Conflict("You already have an active reservation for this item", code="duplicate_reservation")
    if len(active) >= MAX_ACTIVE_PER_CUSTOMER:
        raise Conflict(f"You can hold up to {MAX_ACTIVE_PER_CUSTOMER} active reservations at a time")

    now = utcnow()
    res = db.reservations.insert(Reservation(
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
        created_at=now,
        updated_at=now,
    ))
    record_event(db, entity="reservation", entity_id=res.id, shop_id=shop.id, from_status=None,
                 to_status=RS.REQUESTED, actor_role="customer", actor_id=customer.id)
    notify(db, shop.owner_id, "reservation_new", f"New reservation {res.code}",
           f"{customer.name} wants {quantity} x {product.name}. Confirm within {settings.request_response_minutes} min.",
           "/shop/reservations")
    return res


def _actor_for(user: User | None, res: Reservation, shop_owner_id: int) -> str:
    if user is None:
        return "system"
    if user.role == Role.CUSTOMER and res.customer_id == user.id:
        return "customer"
    if user.role == Role.OWNER and shop_owner_id == user.id:
        return "owner"
    if user.role == Role.ADMIN:
        return "admin"
    raise Forbidden("This reservation belongs to someone else")


def transition(db: Database, reservation_id: int, action: str, user: User | None,
               reason: str | None = None) -> Reservation:
    """Move a reservation through its state machine. The reservation, the stock hold, the audit
    event, the sale and the notifications commit together or not at all."""
    return db.transaction(lambda: _transition(db, reservation_id, action, user, reason))


def _transition(db: Database, reservation_id: int, action: str, user: User | None, reason: str | None) -> Reservation:
    # Loaded inside the transaction: if someone else changes it first, this transaction is
    # retried and sees the new status instead of overwriting it.
    res = db.reservations.get(reservation_id)
    if res is None:
        raise NotFound("Reservation not found")
    product = db.products.get(res.product_id)
    shop = db.shops.get(res.shop_id)
    actor = _actor_for(user, res, shop.owner_id)
    key = (res.status, action)
    if key not in TRANSITIONS:
        raise InvalidTransition(f"Cannot {action} a reservation that is {res.status.replace('_', ' ').lower()}")
    to_status, actors = TRANSITIONS[key]
    if actor not in actors and actor != "admin":
        raise Forbidden(f"Only the {' or '.join(sorted(actors))} can {action} this reservation")

    now = utcnow()
    from_status = res.status
    actor_id = user.id if user else None
    changes: dict = {"status": to_status}

    if action == "confirm":
        change_stock(db, product, -res.quantity, InventoryReason.RESERVATION_HOLD, actor_id)
        changes.update(stock_held=True, confirmed_at=now, expires_at=now + timedelta(minutes=res.hold_minutes))
        notify(db, res.customer_id, "reservation_confirmed", f"{shop.name} confirmed your reservation",
               f"{res.quantity} x {product.name} is held for you for {res.hold_minutes} minutes. Code {res.code}.",
               f"/account/reservations/{res.id}")
    elif action == "ready":
        changes.update(ready_at=now, expires_at=max(res.expires_at, now + timedelta(minutes=res.hold_minutes)))
        notify(db, res.customer_id, "reservation_ready", "Ready for pickup",
               f"{product.name} is packed at {shop.name}. Show code {res.code} at the counter.",
               f"/account/reservations/{res.id}")
    elif action == "complete":
        changes.update(completed_at=now, stock_held=False)  # the held unit left the shop with the customer
        record_sales(db, [(product, res.quantity, res.unit_price)], source=SaleSource.RESERVATION,
                     basket_id=res.code, customer_id=res.customer_id)
        notify(db, res.customer_id, "reservation_completed", "Pickup complete",
               f"Thanks for shopping at {shop.name}. How was it? Leave a quick review.",
               f"/account/reservations/{res.id}")
    else:  # reject / cancel / expire
        if res.stock_held:
            change_stock(db, product, res.quantity, InventoryReason.RESERVATION_RELEASE, actor_id)
        close_reason = (reason or "").strip() or None
        changes.update(stock_held=False, closed_at=now, close_reason=close_reason)
        if action == "reject":
            notify(db, res.customer_id, "reservation_rejected", f"{shop.name} could not hold your item",
                   close_reason or "The shop was unable to confirm this reservation. Try another shop nearby.",
                   f"/search?q={product.name}")
        elif action == "cancel" and actor == "customer":
            notify(db, shop.owner_id, "reservation_cancelled", f"Reservation {res.code} cancelled by customer",
                   f"{res.quantity} x {product.name} is back in stock.", "/shop/reservations")
        elif action == "cancel":
            notify(db, res.customer_id, "reservation_cancelled", f"{shop.name} cancelled your reservation",
                   close_reason or "The shop cancelled this reservation.", f"/account/reservations/{res.id}")
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

    db.reservations.set(res, **changes)
    record_event(db, entity="reservation", entity_id=res.id, shop_id=res.shop_id, from_status=from_status,
                 to_status=to_status, actor_role=actor, actor_id=actor_id, note=reason)
    return res


def expire_due(db: Database) -> int:
    """Expire reservations whose timer has run out. Called by the scheduler and lazily on reads."""
    due = db.reservations.find_raw({"status": {"$in": list(ACTIVE)}, "expires_at": {"$lte": utcnow()}}, {"_id": 1})
    for doc in due:
        try:
            transition(db, doc["_id"], "expire", None)
        except Exception as exc:  # never let one bad document stop the sweep
            log.warning("could not expire reservation %s: %s", doc["_id"], exc)
    return len(due)
