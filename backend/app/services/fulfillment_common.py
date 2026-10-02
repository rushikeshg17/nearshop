"""Helpers shared by the reservation and delivery-order state machines."""
from app.core.database import Database, utcnow
from app.models import Product, SaleSource, SalesRecord, StatusEvent


def record_event(
    db: Database,
    *,
    entity: str,
    entity_id: int,
    shop_id: int,
    from_status: str | None,
    to_status: str,
    actor_role: str,
    actor_id: int | None,
    note: str | None = None,
) -> None:
    db.status_events.insert(
        StatusEvent(
            entity=entity,
            entity_id=entity_id,
            shop_id=shop_id,
            from_status=from_status,
            to_status=to_status,
            actor_role=actor_role,
            actor_id=actor_id,
            note=note,
        )
    )


def record_sales(db: Database, lines: list[tuple[Product, int, float]], *, source: SaleSource, basket_id: str,
                 customer_id: int | None) -> None:
    """Completed sales feed demand prediction and market-basket analysis.
    `lines` is (product, quantity, unit_price) for everything bought together."""
    now = utcnow()
    db.sales_history.insert_many([
        SalesRecord(
            shop_id=product.shop_id,
            product_id=product.id,
            catalog_item_id=product.catalog_item_id,
            category_id=product.category_id,
            customer_id=customer_id,
            basket_id=basket_id,
            quantity=quantity,
            unit_price=unit_price,
            source=source,
            is_demo=False,
            sold_at=now,
        )
        for product, quantity, unit_price in lines
    ])
