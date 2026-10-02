"""Shop owner: shop settings, inventory, catalog, reservation and delivery queues, insights."""
from typing import Literal

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.ai.semantic_index import index
from app.core.deps import DB, OwnerShop, OwnerUser
from app.core.errors import AppError, Conflict, NotFound
from app.models import (
    CatalogItem,
    Category,
    InventoryReason,
    Order,
    Product,
    Reservation,
    Review,
    StatusEvent,
)
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
from app.services.inventory import change_stock, set_stock
from app.services.media import delete_image, save_image
from app.services.reliability import shop_reliability
from app.utils.text import normalize_query

router = APIRouter(prefix="/owner", tags=["shop owner"])


# ------------------------------------------------------------------ shop

@router.get("/shop")
def my_shop(shop: OwnerShop, db: DB):
    return shop_detail(shop, None, shop_reliability(db, shop))


@router.patch("/shop")
def update_shop(body: ShopUpdateIn, shop: OwnerShop, db: DB):
    data = body.model_dump(exclude_unset=True)
    if "category_slugs" in data:
        cats = db.scalars(select(Category).where(Category.slug.in_(data.pop("category_slugs")))).all()
        if not cats:
            raise AppError("Choose at least one category")
        shop.categories = cats
    for k, v in data.items():
        setattr(shop, k, v)
    if shop.offers_delivery and shop.delivery_radius_km <= 0:
        raise AppError("Set a delivery radius to offer delivery")
    db.commit()
    return shop_detail(shop, None, shop_reliability(db, shop))


@router.post("/shop/image")
async def upload_shop_image(shop: OwnerShop, db: DB, file: UploadFile = File(...)):
    rel = await save_image(file, "shops")
    delete_image(shop.image_path)
    shop.image_path = rel
    db.commit()
    return {"image_url": f"/media/{rel}"}


@router.get("/overview")
def overview(shop: OwnerShop, db: DB):
    reservation_service.expire_due(db)
    data = analytics.owner_overview(db, shop)
    requests = db.scalars(select(Reservation).where(
        Reservation.shop_id == shop.id, Reservation.status == "REQUESTED").order_by(Reservation.created_at)).all()
    pending = db.scalars(select(Order).where(Order.shop_id == shop.id, Order.status == "PENDING")
                         .order_by(Order.created_at)).all()
    data["reservation_requests"] = [_res(db, r) for r in requests[:6]]
    data["pending_orders"] = [_ord(db, o) for o in pending[:6]]
    data["shop"] = {"id": shop.id, "name": shop.name, "slug": shop.slug, "offers_delivery": shop.offers_delivery}
    return data


@router.get("/insights")
def insights(shop: OwnerShop, db: DB):
    return analytics.owner_insights(db, shop)


@router.get("/reviews")
def reviews(shop: OwnerShop, db: DB):
    rows = db.scalars(select(Review).options(selectinload(Review.customer)).where(Review.shop_id == shop.id)
                      .order_by(Review.created_at.desc()).limit(50)).all()
    names = dict(db.execute(select(Product.id, Product.name).where(
        Product.id.in_([r.product_id for r in rows if r.product_id]))).all())
    return [review_out(r, names.get(r.product_id)) for r in rows]


# ------------------------------------------------------------------ inventory

def _own_product(db, shop, product_id: int) -> Product:
    p = db.get(Product, product_id)
    if p is None or p.shop_id != shop.id:
        raise NotFound("Product not found in your shop")
    return p


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
    stmt = select(Product).options(selectinload(Product.category)).where(Product.shop_id == shop.id)
    stmt = stmt.where(Product.is_active.is_(stock != "inactive"))
    if stock == "in_stock":
        stmt = stmt.where(Product.quantity > Product.low_stock_threshold)
    elif stock == "low_stock":
        stmt = stmt.where(Product.quantity > 0, Product.quantity <= Product.low_stock_threshold)
    elif stock == "out_of_stock":
        stmt = stmt.where(Product.quantity == 0)
    if category:
        stmt = stmt.join(Category, Category.id == Product.category_id).where(Category.slug == category)
    if q:
        like = f"%{normalize_query(q)}%"
        stmt = stmt.where(Product.name.ilike(like) | Product.brand.ilike(like) | Product.sku.ilike(like))
    order = {
        "name": Product.name, "stock_asc": Product.quantity, "stock_desc": Product.quantity.desc(),
        "price_asc": Product.price, "price_desc": Product.price.desc(), "updated": Product.stock_updated_at.desc(),
    }[sort]
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(order).offset((page - 1) * page_size).limit(page_size)).all()
    items = [
        {**listing(p), "sku": p.sku, "description": p.description, "specs": p.specs or {}, "keywords": p.keywords}
        for p in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/products")
def create_product(body: ProductIn, shop: OwnerShop, user: OwnerUser, db: DB):
    cat = db.scalar(select(Category).where(Category.slug == body.category_slug))
    if cat is None:
        raise AppError("Unknown category")
    p = Product(shop_id=shop.id, category_id=cat.id, name=body.name, brand=body.brand, sku=body.sku,
                unit=body.unit, description=body.description, specs=body.specs,
                keywords=_keywords([t.lower() for t in body.tags], cat), icon=cat.icon, price=body.price,
                mrp=body.mrp, quantity=0, low_stock_threshold=body.low_stock_threshold)
    db.add(p)
    db.flush()
    if body.quantity:
        change_stock(db, p, body.quantity, InventoryReason.INITIAL, user.id)
    db.commit()
    index.mark_dirty()
    return listing(p)


@router.patch("/products/{product_id}")
def update_product(product_id: int, body: ProductUpdateIn, shop: OwnerShop, db: DB):
    p = _own_product(db, shop, product_id)
    data = body.model_dump(exclude_unset=True)
    if "category_slug" in data:
        cat = db.scalar(select(Category).where(Category.slug == data.pop("category_slug")))
        if cat is None:
            raise AppError("Unknown category")
        p.category_id = cat.id
    if "tags" in data:
        cat = db.get(Category, p.category_id)
        p.keywords = _keywords([t.lower() for t in data.pop("tags")], cat)
    for k, v in data.items():
        setattr(p, k, v)
    db.commit()
    index.mark_dirty()
    return listing(p)


@router.put("/products/{product_id}/stock")
def update_stock(product_id: int, body: StockIn, shop: OwnerShop, user: OwnerUser, db: DB):
    p = _own_product(db, shop, product_id)
    set_stock(db, p, body.quantity, user.id)
    db.commit()
    db.refresh(p)
    return listing(p)


@router.delete("/products/{product_id}")
def delete_product(product_id: int, shop: OwnerShop, db: DB):
    """Soft delete: the listing disappears from search but past orders and reviews keep their history."""
    p = _own_product(db, shop, product_id)
    active_holds = db.scalar(select(func.count()).select_from(Reservation).where(
        Reservation.product_id == p.id, Reservation.status.in_(reservation_service.ACTIVE))) or 0
    if active_holds:
        raise Conflict(f"This item has {active_holds} active reservation(s). Complete or cancel them first.")
    p.is_active = False
    db.commit()
    index.mark_dirty()
    return {"ok": True}


@router.post("/products/{product_id}/image")
async def upload_product_image(product_id: int, shop: OwnerShop, db: DB, file: UploadFile = File(...)):
    p = _own_product(db, shop, product_id)
    rel = await save_image(file, "products")
    delete_image(p.image_path)
    p.image_path = rel
    db.commit()
    return listing(p)


@router.get("/catalog")
def browse_catalog(shop: OwnerShop, db: DB, q: str = Query("", max_length=120), category: str | None = None,
                   limit: int = Query(60, ge=1, le=200)):
    listed = set(db.scalars(select(Product.catalog_item_id).where(
        Product.shop_id == shop.id, Product.is_active.is_(True), Product.catalog_item_id.is_not(None))))
    stmt = select(CatalogItem).options(selectinload(CatalogItem.category))
    if category:
        stmt = stmt.join(Category, Category.id == CatalogItem.category_id).where(Category.slug == category)
    elif not q:
        stmt = stmt.where(CatalogItem.category_id.in_([c.id for c in shop.categories]))
    if q:
        like = f"%{normalize_query(q)}%"
        stmt = stmt.where(CatalogItem.name.ilike(like) | CatalogItem.brand.ilike(like)
                          | CatalogItem.subcategory.ilike(like))
    # Local price guidance: median price of each item across other shops.
    medians = {}
    for cid, prices in _price_lists(db).items():
        s = sorted(prices)
        medians[cid] = s[len(s) // 2]
    items = [
        {"id": c.id, "name": c.name, "brand": c.brand, "unit": c.unit, "icon": c.icon, "mrp": c.mrp,
         "typical_price": c.typical_price, "local_median": medians.get(c.id), "category": c.category.slug,
         "subcategory": c.subcategory, "already_listed": c.id in listed}
        for c in db.scalars(stmt.order_by(CatalogItem.name).limit(limit))
    ]
    return {"items": items}


def _price_lists(db) -> dict[int, list[float]]:
    out: dict[int, list[float]] = {}
    for cid, price in db.execute(select(Product.catalog_item_id, Product.price).where(
            Product.is_active.is_(True), Product.catalog_item_id.is_not(None))):
        out.setdefault(cid, []).append(price)
    return out


@router.post("/catalog/add")
def add_from_catalog(body: CatalogAddIn, shop: OwnerShop, user: OwnerUser, db: DB):
    added, reactivated = 0, 0
    for item in body.items:
        c = db.get(CatalogItem, item.catalog_item_id)
        if c is None:
            raise NotFound("Catalog item not found")
        existing = db.scalar(select(Product).where(Product.shop_id == shop.id, Product.catalog_item_id == c.id))
        if existing:
            if existing.is_active:
                continue
            existing.is_active = True
            existing.price = item.price
            set_stock(db, existing, item.quantity, user.id)
            reactivated += 1
            continue
        p = Product(shop_id=shop.id, catalog_item_id=c.id, category_id=c.category_id, name=c.name, brand=c.brand,
                    unit=c.unit, description=c.description, specs=c.specs or {},
                    keywords=_keywords(c.tags or [], c.category, c.subcategory), icon=c.icon, price=item.price,
                    mrp=c.mrp, quantity=0)
        db.add(p)
        db.flush()
        if item.quantity:
            change_stock(db, p, item.quantity, InventoryReason.INITIAL, user.id)
        added += 1
    db.commit()
    index.mark_dirty()
    return {"added": added, "reactivated": reactivated}


# ------------------------------------------------------------------ reservations & orders

def _events(db, entity, entity_id):
    return db.scalars(select(StatusEvent).where(StatusEvent.entity == entity, StatusEvent.entity_id == entity_id)
                      .order_by(StatusEvent.created_at, StatusEvent.id)).all()


def _res(db, r: Reservation, with_events: bool = False) -> dict:
    return reservation_out(r, actions=reservation_service.allowed_actions(r, "owner"), for_owner=True,
                           events=_events(db, "reservation", r.id) if with_events else None)


def _ord(db, o: Order, with_events: bool = False) -> dict:
    return order_out(o, actions=order_service.allowed_actions(o, "owner"), for_owner=True,
                     events=_events(db, "order", o.id) if with_events else None)


@router.get("/reservations")
def shop_reservations(shop: OwnerShop, db: DB, scope: Literal["active", "history"] = "active"):
    reservation_service.expire_due(db)
    stmt = select(Reservation).where(Reservation.shop_id == shop.id)
    if scope == "active":
        stmt = stmt.where(Reservation.status.in_(reservation_service.ACTIVE)).order_by(Reservation.created_at)
    else:
        stmt = stmt.where(Reservation.status.not_in(reservation_service.ACTIVE)) \
            .order_by(Reservation.updated_at.desc()).limit(100)
    return [_res(db, r) for r in db.scalars(stmt)]


@router.get("/reservations/{reservation_id}")
def shop_reservation(reservation_id: int, shop: OwnerShop, db: DB):
    r = db.get(Reservation, reservation_id)
    if r is None or r.shop_id != shop.id:
        raise NotFound("Reservation not found")
    return _res(db, r, with_events=True)


@router.post("/reservations/{reservation_id}/{action}")
def act_on_reservation(reservation_id: int, action: Literal["confirm", "reject", "ready", "complete", "cancel"],
                       body: TransitionIn, shop: OwnerShop, user: OwnerUser, db: DB):
    r = db.get(Reservation, reservation_id)
    if r is None or r.shop_id != shop.id:
        raise NotFound("Reservation not found")
    r = reservation_service.transition(db, r, action, user, body.reason)
    return _res(db, r, with_events=True)


@router.get("/orders")
def shop_orders(shop: OwnerShop, db: DB, scope: Literal["active", "history"] = "active"):
    stmt = select(Order).options(selectinload(Order.items)).where(Order.shop_id == shop.id)
    if scope == "active":
        stmt = stmt.where(Order.status.in_(order_service.ACTIVE | {"DELIVERY_FAILED"})).order_by(Order.created_at)
    else:
        stmt = stmt.where(Order.status.not_in(order_service.ACTIVE | {"DELIVERY_FAILED"})) \
            .order_by(Order.updated_at.desc()).limit(100)
    return [_ord(db, o) for o in db.scalars(stmt)]


@router.get("/orders/{order_id}")
def shop_order(order_id: int, shop: OwnerShop, db: DB):
    o = db.get(Order, order_id)
    if o is None or o.shop_id != shop.id:
        raise NotFound("Order not found")
    return _ord(db, o, with_events=True)


@router.post("/orders/{order_id}/{action}")
def act_on_order(order_id: int, action: Literal["confirm", "prepare", "dispatch", "deliver", "fail", "return",
                                                 "cancel"],
                 body: TransitionIn, shop: OwnerShop, user: OwnerUser, db: DB):
    o = db.get(Order, order_id)
    if o is None or o.shop_id != shop.id:
        raise NotFound("Order not found")
    o = order_service.transition(db, o, action, user, body.reason)
    return _ord(db, o, with_events=True)


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
    index.mark_dirty()
    return result
