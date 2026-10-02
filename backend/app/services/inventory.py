"""Stock changes. Every change goes through here so it is atomic and audited."""
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.core.errors import Conflict
from app.models import InventoryEvent, InventoryReason, Product, Shop
from app.services.notifications import notify

OWNER_REASONS = {InventoryReason.INITIAL, InventoryReason.RESTOCK, InventoryReason.ADJUSTMENT}


def change_stock(
    db: Session,
    product: Product,
    delta: int,
    reason: InventoryReason,
    actor_id: int | None = None,
) -> Product:
    """Atomically add `delta` to stock. A negative delta fails (Conflict) if stock is insufficient,
    so two customers can never both take the last unit."""
    if delta == 0:
        return product
    # Persist any pending edits (e.g. a price change) first: the refresh below reloads the row.
    db.flush()
    now = utcnow()
    stmt = (
        update(Product)
        .where(Product.id == product.id)
        .values(quantity=Product.quantity + delta, stock_updated_at=now)
    )
    if delta < 0:
        stmt = stmt.where(Product.quantity >= -delta)
    result = db.execute(stmt)
    if result.rowcount == 0:
        db.refresh(product)
        raise Conflict(
            f"Only {product.quantity} of {product.name} left in stock",
            code="insufficient_stock",
        )
    db.refresh(product)
    before = product.quantity - delta
    db.add(
        InventoryEvent(
            product_id=product.id,
            shop_id=product.shop_id,
            delta=delta,
            quantity_after=product.quantity,
            reason=reason,
            actor_id=actor_id,
        )
    )
    if reason in OWNER_REASONS:
        db.execute(update(Shop).where(Shop.id == product.shop_id).values(inventory_updated_at=now))

    # Tell the owner when an item crosses into low stock or runs out.
    threshold = product.low_stock_threshold
    if before > threshold >= product.quantity or (before > 0 and product.quantity == 0):
        shop = db.get(Shop, product.shop_id)
        state = "is out of stock" if product.quantity == 0 else f"is running low ({product.quantity} left)"
        notify(
            db,
            shop.owner_id,
            "low_stock",
            f"{product.name} {state}",
            "Restock soon so customers nearby can still find it.",
            f"/shop/inventory?focus={product.id}",
        )
    return product


def set_stock(db: Session, product: Product, new_quantity: int, actor_id: int) -> Product:
    """Owner sets an absolute count (e.g. after counting shelves)."""
    if new_quantity < 0:
        raise Conflict("Stock cannot be negative")
    delta = new_quantity - product.quantity
    if delta == 0:
        # Still a meaningful "I checked this" signal for freshness.
        now = utcnow()
        product.stock_updated_at = now
        db.execute(update(Shop).where(Shop.id == product.shop_id).values(inventory_updated_at=now))
        return product
    reason = InventoryReason.RESTOCK if delta > 0 else InventoryReason.ADJUSTMENT
    return change_stock(db, product, delta, reason, actor_id)
