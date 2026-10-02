"""Stock changes. Every change goes through here so it is atomic and audited."""
from pymongo import UpdateOne

from app.core.database import Database, transactional, utcnow
from app.core.errors import Conflict
from app.models import InventoryEvent, InventoryReason, Notification, Product, Shop

OWNER_REASONS = {InventoryReason.INITIAL, InventoryReason.RESTOCK, InventoryReason.ADJUSTMENT}


def _crossed_low(before: int, after: int, threshold: int) -> bool:
    return before > threshold >= after or (before > 0 and after == 0)


def _low_stock_notification(owner_id: int, product: Product) -> Notification:
    state = "is out of stock" if product.quantity == 0 else f"is running low ({product.quantity} left)"
    return Notification(user_id=owner_id, kind="low_stock", title=f"{product.name} {state}",
                        body="Restock soon so customers nearby can still find it.",
                        link=f"/shop/inventory?focus={product.id}")


@transactional
def change_stock(
    db: Database,
    product: Product,
    delta: int,
    reason: InventoryReason,
    actor_id: int | None = None,
) -> Product:
    """Atomically add `delta` to stock. A negative delta fails (Conflict) if stock is insufficient,
    so two customers can never both take the last unit: the stock check and the decrement are
    one conditional update, not a read followed by a write."""
    if delta == 0:
        return product
    now = utcnow()
    guard = {"_id": product.id}
    if delta < 0:
        guard["quantity"] = {"$gte": -delta}
    updated = db.products.find_one_and_update(
        guard, {"$inc": {"quantity": delta}, "$set": {"stock_updated_at": now, "updated_at": now}}
    )
    if updated is None:
        current = db.products.get(product.id)
        left = current.quantity if current else 0
        raise Conflict(f"Only {left} of {product.name} left in stock", code="insufficient_stock")
    product.quantity, product.stock_updated_at = updated.quantity, now
    before = updated.quantity - delta
    db.inventory_events.insert(
        InventoryEvent(product_id=product.id, shop_id=product.shop_id, delta=delta, quantity_after=updated.quantity,
                       reason=reason, actor_id=actor_id, created_at=now)
    )
    if reason in OWNER_REASONS:
        db.shops.update_one({"_id": product.shop_id}, {"$set": {"inventory_updated_at": now}})

    # Tell the owner when an item crosses into low stock or runs out.
    if _crossed_low(before, updated.quantity, updated.low_stock_threshold):
        shop = db.shops.get(product.shop_id)
        db.notifications.insert(_low_stock_notification(shop.owner_id, product))
    return product


@transactional
def set_stock(db: Database, product: Product, new_quantity: int, actor_id: int) -> Product:
    """Owner sets an absolute count (e.g. after counting shelves)."""
    if new_quantity < 0:
        raise Conflict("Stock cannot be negative")
    delta = new_quantity - product.quantity
    if delta == 0:
        # Still a meaningful "I checked this" signal for freshness.
        now = utcnow()
        db.products.set(product, stock_updated_at=now)
        db.shops.update_one({"_id": product.shop_id}, {"$set": {"inventory_updated_at": now}})
        return product
    reason = InventoryReason.RESTOCK if delta > 0 else InventoryReason.ADJUSTMENT
    return change_stock(db, product, delta, reason, actor_id)


@transactional
def apply_bulk(
    db: Database,
    shop: Shop,
    actor_id: int,
    creates: list[tuple[Product, int]],
    updates: list[tuple[Product, dict, int | None]],
) -> None:
    """Apply many listing changes as one transaction and a handful of round trips.

    creates: (new product, opening quantity)
    updates: (existing product, fields to set, new absolute quantity or None to leave stock alone)

    Used by the Excel/CSV import and "add from catalogue": either every row lands or none does.
    """
    now = utcnow()
    events: list[InventoryEvent] = []
    notifications: list[Notification] = []
    stock_counted = False

    for product, quantity in creates:
        product.quantity, product.stock_updated_at = quantity, now
    db.products.insert_many([p for p, _ in creates])
    for product, quantity in creates:
        if quantity:
            stock_counted = True
            events.append(InventoryEvent(product_id=product.id, shop_id=shop.id, delta=quantity,
                                         quantity_after=quantity, reason=InventoryReason.INITIAL,
                                         actor_id=actor_id, created_at=now))

    operations = []
    for product, fields, new_quantity in updates:
        changes = {**fields, "updated_at": now}
        if new_quantity is not None:
            if new_quantity < 0:
                raise Conflict("Stock cannot be negative")
            stock_counted = True
            before, delta = product.quantity, new_quantity - product.quantity
            changes.update(quantity=new_quantity, stock_updated_at=now)
            if delta:
                events.append(InventoryEvent(
                    product_id=product.id, shop_id=shop.id, delta=delta, quantity_after=new_quantity,
                    reason=InventoryReason.RESTOCK if delta > 0 else InventoryReason.ADJUSTMENT,
                    actor_id=actor_id, created_at=now))
        for key, value in changes.items():
            setattr(product, key, value)
        if new_quantity is not None and _crossed_low(before, new_quantity, product.low_stock_threshold):
            notifications.append(_low_stock_notification(shop.owner_id, product))
        operations.append(UpdateOne({"_id": product.id, "shop_id": shop.id}, {"$set": changes}))

    db.products.bulk_write(operations)
    db.inventory_events.insert_many(events)
    db.notifications.insert_many(notifications[:20])
    if stock_counted:
        db.shops.update_one({"_id": shop.id}, {"$set": {"inventory_updated_at": now}})
