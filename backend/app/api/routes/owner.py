"""Shop owner: shop settings, inventory, catalog, reservation and delivery queues, insights."""
import re
from typing import Literal

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.ai.semantic_index import index
from app.core.database import Database
from app.core.deps import DB, OwnerShop, OwnerUser
from app.core.errors import AppError, Conflict, NotFound
from app.models import Category, GeoPoint, InventoryReason, Order, Product, Reservation, Shop
from app.schemas.requests import (
    CatalogAddIn,
    ProductIn,
    ProductUpdateIn,
    ShopUpdateIn,
    StockIn,
    TransitionIn,
)
from app.schemas.serializers import listing, order_out, reservation_out, review_out, shop_detail
from app.services import analytics, importer
from app.services import orders as order_service
from app.services import reservations as reservation_service
from app.services.inventory import apply_bulk, change_stock, set_stock
from app.services.loaders import (
    categories,
    category_by_slug,
    hydrate_orders,
    hydrate_reservations,
    product_names,
    timelines,
    with_category,
    with_customers,
)
from app.services.media import delete_image, save_image
from app.services.reliability import shop_reliability
from app.services.search import reset_vocabulary
from app.utils.text import normalize_query

router = APIRouter(prefix="/owner", tags=["shop owner"])

RES_ACTIVE = list(reservation_service.ACTIVE)
ORDER_OPEN = [*order_service.ACTIVE, "DELIVERY_FAILED"]


def _listings_changed() -> None:
    """Search caches (semantic index, spelling vocabulary) are rebuilt on the next query."""
    index.mark_dirty()
    reset_vocabulary()


# ------------------------------------------------------------------ shop

@router.get("/shop")
def my_shop(shop: OwnerShop, db: DB):
    return shop_detail(shop, None, shop_reliability(db, shop))


@router.patch("/shop")
def update_shop(body: ShopUpdateIn, shop: OwnerShop, db: DB):
    data = body.model_dump(exclude_unset=True)
    if "category_slugs" in data:
        slugs = set(data.pop("category_slugs"))
        cats = [c for c in categories(db).values() if c.slug in slugs]
        if not cats:
            raise AppError("Choose at least one category")
        data["category_ids"] = [c.id for c in cats]
        shop.categories = cats
    if "lat" in data or "lng" in data:
        data["location"] = GeoPoint.of(data.pop("lat", None) or shop.lat, data.pop("lng", None) or shop.lng)
    offers_delivery = data.get("offers_delivery", shop.offers_delivery)
    if offers_delivery and data.get("delivery_radius_km", shop.delivery_radius_km) <= 0:
        raise AppError("Set a delivery radius to offer delivery")
    if data:
        db.shops.set(shop, **data)
    return shop_detail(shop, None, shop_reliability(db, shop))


@router.post("/shop/image")
async def upload_shop_image(shop: OwnerShop, db: DB, file: UploadFile = File(...)):
    rel = await save_image(file, "shops")
    delete_image(shop.image_path)
    db.shops.set(shop, image_path=rel)
    return {"image_url": f"/media/{rel}"}


@router.get("/overview")
def overview(shop: OwnerShop, db: DB):
    reservation_service.expire_due(db)
    data, requests, pending = db.gather(
        lambda: analytics.owner_overview(db, shop),
        lambda: db.reservations.find({"shop_id": shop.id, "status": "REQUESTED"}, sort=[("created_at", 1)], limit=6),
        lambda: db.orders.find({"shop_id": shop.id, "status": "PENDING"}, sort=[("created_at", 1)], limit=6),
    )
    data["reservation_requests"] = _res(db, requests)
    data["pending_orders"] = _ord(db, pending)
    data["shop"] = {"id": shop.id, "name": shop.name, "slug": shop.slug, "offers_delivery": shop.offers_delivery}
    return data


@router.get("/insights")
def insights(shop: OwnerShop, db: DB):
    return analytics.owner_insights(db, shop)


@router.get("/reviews")
def reviews(shop: OwnerShop, db: DB):
    rows = with_customers(db, db.reviews.find({"shop_id": shop.id}, sort=[("created_at", -1)], limit=50))
    names = product_names(db, (r.product_id for r in rows))
    return [review_out(r, names.get(r.product_id)) for r in rows]


# ------------------------------------------------------------------ inventory

def _own_product(db: Database, shop: Shop, product_id: int) -> Product:
    p = db.products.get(product_id)
    if p is None or p.shop_id != shop.id:
        raise NotFound("Product not found in your shop")
    return with_category(db, [p])[0]


def _keywords(tags: list[str], category: Category, subcategory: str | None = None) -> str:
    return " ".join(dict.fromkeys([*tags, category.name.lower(), (subcategory or "").replace("-", " ")])).strip()


@router.get("/products")
def list_products(
    shop: OwnerShop, db: DB,
    q: str = Query("", max_length=120),
    stock: Literal["all", "in_stock", "low_stock", "out_of_stock", "inactive"] = "all",
    category: str | None = None,
    sort: Literal["name", "stock_asc", "stock_desc", "price_asc", "price_desc", "updated"] = "name",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    query: dict = {"shop_id": shop.id, "is_active": stock != "inactive"}
    if stock == "in_stock":
        query["$expr"] = {"$gt": ["$quantity", "$low_stock_threshold"]}
    elif stock == "low_stock":
        query["quantity"] = {"$gt": 0}
        query["$expr"] = {"$lte": ["$quantity", "$low_stock_threshold"]}
    elif stock == "out_of_stock":
        query["quantity"] = 0
    if category:
        cat = category_by_slug(db, category)
        query["category_id"] = cat.id if cat else -1
    if q:
        like = {"$regex": re.escape(normalize_query(q)), "$options": "i"}
        query["$or"] = [{"name": like}, {"brand": like}, {"sku": like}]
    order = {
        "name": [("name", 1)], "stock_asc": [("quantity", 1)], "stock_desc": [("quantity", -1)],
        "price_asc": [("price", 1)], "price_desc": [("price", -1)], "updated": [("stock_updated_at", -1)],
    }[sort]
    total, rows = db.gather(
        lambda: db.products.count(query),
        lambda: with_category(db, db.products.find(query, sort=[*order, ("_id", 1)], skip=(page - 1) * page_size,
                                                   limit=page_size)),
    )
    items = [
        {**listing(p), "sku": p.sku, "description": p.description, "specs": p.specs or {}, "keywords": p.keywords}
        for p in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/products")
def create_product(body: ProductIn, shop: OwnerShop, user: OwnerUser, db: DB):
    cat = category_by_slug(db, body.category_slug)
    if cat is None:
        raise AppError("Unknown category")
    p = Product(shop_id=shop.id, category_id=cat.id, name=body.name, brand=body.brand, sku=body.sku,
                unit=body.unit, description=body.description, specs=body.specs,
                keywords=_keywords([t.lower() for t in body.tags], cat), icon=cat.icon, price=body.price,
                mrp=body.mrp, quantity=0, low_stock_threshold=body.low_stock_threshold, category=cat)

    def create() -> None:
        db.products.insert(p)
        if body.quantity:
            change_stock(db, p, body.quantity, InventoryReason.INITIAL, user.id)

    db.transaction(create)
    _listings_changed()
    return listing(p)


@router.patch("/products/{product_id}")
def update_product(product_id: int, body: ProductUpdateIn, shop: OwnerShop, db: DB):
    p = _own_product(db, shop, product_id)
    data = body.model_dump(exclude_unset=True)
    if "category_slug" in data:
        cat = category_by_slug(db, data.pop("category_slug"))
        if cat is None:
            raise AppError("Unknown category")
        data["category_id"], p.category = cat.id, cat
    if "tags" in data:
        data["keywords"] = _keywords([t.lower() for t in data.pop("tags")], p.category)
    if data:
        db.products.set(p, **data)
    _listings_changed()
    return listing(p)


@router.put("/products/{product_id}/stock")
def update_stock(product_id: int, body: StockIn, shop: OwnerShop, user: OwnerUser, db: DB):
    p = _own_product(db, shop, product_id)
    set_stock(db, p, body.quantity, user.id)
    return listing(p)


@router.delete("/products/{product_id}")
def delete_product(product_id: int, shop: OwnerShop, db: DB):
    """Soft delete: the listing disappears from search but past orders and reviews keep their history."""
    p = _own_product(db, shop, product_id)
    active_holds = db.reservations.count({"product_id": p.id, "status": {"$in": RES_ACTIVE}})
    if active_holds:
        raise Conflict(f"This item has {active_holds} active reservation(s). Complete or cancel them first.")
    db.products.set(p, is_active=False)
    _listings_changed()
    return {"ok": True}


@router.post("/products/{product_id}/image")
async def upload_product_image(product_id: int, shop: OwnerShop, db: DB, file: UploadFile = File(...)):
    p = _own_product(db, shop, product_id)
    rel = await save_image(file, "products")
    delete_image(p.image_path)
    db.products.set(p, image_path=rel)
    return listing(p)


@router.get("/catalog")
def browse_catalog(shop: OwnerShop, db: DB, q: str = Query("", max_length=120), category: str | None = None,
                   limit: int = Query(60, ge=1, le=200)):
    query: dict = {}
    if category:
        cat = category_by_slug(db, category)
        query["category_id"] = cat.id if cat else -1
    elif not q:
        query["category_id"] = {"$in": shop.category_ids}
    if q:
        like = {"$regex": re.escape(normalize_query(q)), "$options": "i"}
        query["$or"] = [{"name": like}, {"brand": like}, {"subcategory": like}]
    found = with_category(db, db.catalog_items.find(query, sort=[("name", 1)], limit=limit))
    ids = [c.id for c in found]
    listed, medians = db.gather(
        lambda: {d["catalog_item_id"] for d in db.products.find_raw(
            {"shop_id": shop.id, "is_active": True, "catalog_item_id": {"$in": ids}}, {"catalog_item_id": 1})},
        # Local price guidance: median price of each item across shops, computed in the database.
        lambda: {r["_id"]: r["median"] for r in db.products.aggregate([
            {"$match": {"is_active": True, "catalog_item_id": {"$in": ids}}},
            {"$group": {"_id": "$catalog_item_id",
                        "median": {"$median": {"input": "$price", "method": "approximate"}}}},
        ])},
    )
    items = [
        {"id": c.id, "name": c.name, "brand": c.brand, "unit": c.unit, "icon": c.icon, "mrp": c.mrp,
         "typical_price": c.typical_price, "local_median": medians.get(c.id), "category": c.category.slug,
         "subcategory": c.subcategory, "already_listed": c.id in listed}
        for c in found
    ]
    return {"items": items}


@router.post("/catalog/add")
def add_from_catalog(body: CatalogAddIn, shop: OwnerShop, user: OwnerUser, db: DB):
    wanted = {i.catalog_item_id: i for i in body.items}
    catalog, existing = db.gather(
        lambda: db.catalog_items.by_ids(wanted),
        lambda: {p.catalog_item_id: p for p in db.products.find(
            {"shop_id": shop.id, "catalog_item_id": {"$in": list(wanted)}})},
    )
    if len(catalog) != len(wanted):
        raise NotFound("Catalog item not found")
    cats = categories(db)
    creates, updates = [], []
    for cid, item in wanted.items():
        c = catalog[cid]
        if cid in existing:
            if not existing[cid].is_active:  # previously removed: bring it back with the new price and count
                updates.append((existing[cid], {"is_active": True, "price": item.price}, item.quantity))
            continue
        creates.append((Product(shop_id=shop.id, catalog_item_id=c.id, category_id=c.category_id, name=c.name,
                                brand=c.brand, unit=c.unit, description=c.description, specs=c.specs or {},
                                keywords=_keywords(c.tags or [], cats[c.category_id], c.subcategory), icon=c.icon,
                                price=item.price, mrp=c.mrp, quantity=0), item.quantity))
    apply_bulk(db, shop, user.id, creates, updates)
    _listings_changed()
    return {"added": len(creates), "reactivated": len(updates)}


# ------------------------------------------------------------------ reservations & orders

def _res(db: Database, rows: list[Reservation], with_events: bool = False) -> list[dict]:
    hydrate_reservations(db, rows, customers=True)
    events = timelines(db, "reservation", [r.id for r in rows]) if with_events else {}
    return [reservation_out(r, actions=reservation_service.allowed_actions(r, "owner"), for_owner=True,
                            events=events.get(r.id) if with_events else None) for r in rows]


def _ord(db: Database, rows: list[Order], with_events: bool = False) -> list[dict]:
    hydrate_orders(db, rows, customers=True)
    events = timelines(db, "order", [o.id for o in rows]) if with_events else {}
    return [order_out(o, actions=order_service.allowed_actions(o, "owner"), for_owner=True,
                      events=events.get(o.id) if with_events else None) for o in rows]


def _shop_reservation(db: Database, shop: Shop, reservation_id: int) -> Reservation:
    r = db.reservations.get(reservation_id)
    if r is None or r.shop_id != shop.id:
        raise NotFound("Reservation not found")
    return r


def _shop_order(db: Database, shop: Shop, order_id: int) -> Order:
    o = db.orders.get(order_id)
    if o is None or o.shop_id != shop.id:
        raise NotFound("Order not found")
    return o


@router.get("/reservations")
def shop_reservations(shop: OwnerShop, db: DB, scope: Literal["active", "history"] = "active"):
    reservation_service.expire_due(db)
    if scope == "active":
        rows = db.reservations.find({"shop_id": shop.id, "status": {"$in": RES_ACTIVE}}, sort=[("created_at", 1)])
    else:
        rows = db.reservations.find({"shop_id": shop.id, "status": {"$nin": RES_ACTIVE}},
                                    sort=[("updated_at", -1)], limit=100)
    return _res(db, rows)


@router.get("/reservations/{reservation_id}")
def shop_reservation(reservation_id: int, shop: OwnerShop, db: DB):
    return _res(db, [_shop_reservation(db, shop, reservation_id)], with_events=True)[0]


@router.post("/reservations/{reservation_id}/{action}")
def act_on_reservation(reservation_id: int, action: Literal["confirm", "reject", "ready", "complete", "cancel"],
                       body: TransitionIn, shop: OwnerShop, user: OwnerUser, db: DB):
    r = _shop_reservation(db, shop, reservation_id)
    r = reservation_service.transition(db, r.id, action, user, body.reason)
    return _res(db, [r], with_events=True)[0]


@router.get("/orders")
def shop_orders(shop: OwnerShop, db: DB, scope: Literal["active", "history"] = "active"):
    if scope == "active":
        rows = db.orders.find({"shop_id": shop.id, "status": {"$in": ORDER_OPEN}}, sort=[("created_at", 1)])
    else:
        rows = db.orders.find({"shop_id": shop.id, "status": {"$nin": ORDER_OPEN}},
                              sort=[("updated_at", -1)], limit=100)
    return _ord(db, rows)


@router.get("/orders/{order_id}")
def shop_order(order_id: int, shop: OwnerShop, db: DB):
    return _ord(db, [_shop_order(db, shop, order_id)], with_events=True)[0]


@router.post("/orders/{order_id}/{action}")
def act_on_order(order_id: int, action: Literal["confirm", "prepare", "dispatch", "deliver", "fail", "return",
                                                 "cancel"],
                 body: TransitionIn, shop: OwnerShop, user: OwnerUser, db: DB):
    o = _shop_order(db, shop, order_id)
    o = order_service.transition(db, o.id, action, user, body.reason)
    return _ord(db, [o], with_events=True)[0]


# ------------------------------------------------------------------ bulk import (Excel / CSV)

class ImportRow(BaseModel):
    model_config = {"extra": "ignore"}
    row: int | None = None
    action: Literal["update", "add_catalog", "add_new", "skip"]
    product_id: int | None = None
    catalog_item_id: int | None = None
    name: str = Field(default="", max_length=200)
    brand: str | None = Field(default=None, max_length=80)
    category_slug: str | None = None
    quantity: int | None = Field(default=None, ge=0, le=100_000)
    price: float | None = Field(default=None, ge=0, le=10_000_000)
    mrp: float | None = Field(default=None, ge=0)


class ImportCommitIn(BaseModel):
    rows: list[ImportRow] = Field(min_length=1, max_length=importer.MAX_ROWS)


@router.get("/import/template", response_class=PlainTextResponse)
def import_template(_: OwnerShop):
    return PlainTextResponse(importer.TEMPLATE_CSV, media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="nearshop-stock-template.csv"'})


@router.post("/import/preview")
async def import_preview(shop: OwnerShop, db: DB, file: UploadFile = File(...)):
    data = await file.read(importer.MAX_BYTES + 1)
    return importer.preview(db, shop, data, file.filename or "upload.csv")


@router.post("/import/commit")
def import_commit(body: ImportCommitIn, shop: OwnerShop, user: OwnerUser, db: DB):
    result = importer.commit(db, shop, [r.model_dump() for r in body.rows], user.id)
    _listings_changed()
    return result
