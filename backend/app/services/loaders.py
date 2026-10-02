"""Resolve references between documents in batches.

MongoDB stores references as ids (`product.shop_id`). These helpers load the referenced
documents with one `$in` query per collection, never one query per row, and attach them to the
models (`product.shop`) so serializers can read them.
"""
from __future__ import annotations

import time
from collections.abc import Iterable

from app.core.database import Database
from app.models import CatalogItem, Category, Order, Product, Reservation, Review, Shop

_CATEGORY_TTL = 300.0
_category_cache: dict[str, tuple[float, dict[int, Category]]] = {}


def categories(db: Database) -> dict[int, Category]:
    """All categories by id. Tiny reference data that only the seed changes, so it is cached."""
    key = db.mongo.name
    hit = _category_cache.get(key)
    if hit and time.monotonic() - hit[0] < _CATEGORY_TTL:
        return hit[1]
    cats = {c.id: c for c in db.categories.find(sort=[("sort_order", 1), ("name", 1)])}
    _category_cache[key] = (time.monotonic(), cats)
    return cats


def reset_category_cache() -> None:
    _category_cache.clear()


def category_by_slug(db: Database, slug: str | None) -> Category | None:
    return next((c for c in categories(db).values() if c.slug == slug), None) if slug else None


def with_categories(db: Database, shops: Iterable[Shop]) -> list[Shop]:
    cats = categories(db)
    shops = list(shops)
    for s in shops:
        s.categories = [cats[i] for i in s.category_ids if i in cats]
    return shops


def with_category(db: Database, items: Iterable[Product | CatalogItem]) -> list:
    cats = categories(db)
    items = list(items)
    for p in items:
        p.category = cats.get(p.category_id)
    return items


def with_shops(db: Database, products: Iterable[Product], *, active_only: bool = False) -> list[Product]:
    """Attach category and shop. With `active_only`, listings of inactive shops are dropped."""
    products = with_category(db, products)
    shops = db.shops.by_ids(p.shop_id for p in products)
    with_categories(db, shops.values())
    out = []
    for p in products:
        p.shop = shops.get(p.shop_id)
        if p.shop is not None and (p.shop.is_active or not active_only):
            out.append(p)
    return out


def with_catalog_items(db: Database, products: Iterable[Product]) -> list[Product]:
    products = list(products)
    items = db.catalog_items.by_ids(p.catalog_item_id for p in products)
    for p in products:
        p.catalog_item = items.get(p.catalog_item_id)
    return products


def hydrate_reservations(db: Database, reservations: Iterable[Reservation], *,
                         customers: bool = False) -> list[Reservation]:
    reservations = list(reservations)
    products = db.products.by_ids(r.product_id for r in reservations)
    shops = db.shops.by_ids(r.shop_id for r in reservations)
    users = db.users.by_ids(r.customer_id for r in reservations) if customers else {}
    for r in reservations:
        r.product, r.shop, r.customer = products.get(r.product_id), shops.get(r.shop_id), users.get(r.customer_id)
    return reservations


def hydrate_orders(db: Database, orders: Iterable[Order], *, customers: bool = False) -> list[Order]:
    orders = list(orders)
    products = db.products.by_ids(i.product_id for o in orders for i in o.items)
    shops = db.shops.by_ids(o.shop_id for o in orders)
    users = db.users.by_ids(o.customer_id for o in orders) if customers else {}
    for o in orders:
        o.shop, o.customer = shops.get(o.shop_id), users.get(o.customer_id)
        for item in o.items:
            item.product = products.get(item.product_id)
    return orders


def with_customers(db: Database, reviews: Iterable[Review]) -> list[Review]:
    reviews = list(reviews)
    users = db.users.by_ids(r.customer_id for r in reviews)
    for r in reviews:
        r.customer = users.get(r.customer_id)
    return reviews


def product_names(db: Database, product_ids: Iterable[int | None]) -> dict[int, str]:
    ids = list({i for i in product_ids if i})
    return {d["_id"]: d["name"] for d in db.products.find_raw({"_id": {"$in": ids}}, {"name": 1})} if ids else {}


def timelines(db: Database, entity: str, entity_ids: Iterable[int]) -> dict[int, list]:
    ids = list(entity_ids)
    out: dict[int, list] = {i: [] for i in ids}
    if ids:
        for e in db.status_events.find({"entity": entity, "entity_id": {"$in": ids}},
                                       sort=[("created_at", 1), ("_id", 1)]):
            out[e.entity_id].append(e)
    return out
