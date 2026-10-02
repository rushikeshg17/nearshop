"""Public product and shop pages."""
from datetime import timedelta
from statistics import median

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.ai.recommend import bundle_for
from app.core.database import utcnow
from app.core.deps import DB, OptionalUser
from app.core.errors import NotFound
from app.models import (
    CatalogItem,
    Category,
    Product,
    Reservation,
    Review,
    Role,
    SalesRecord,
    Shop,
)
from app.schemas.serializers import listing, review_out, shop_brief, shop_detail
from app.services import reservations as reservation_service
from app.services.meta import city_config
from app.services.orders import quote_delivery
from app.services.reliability import ratings_for, shop_reliability
from app.services.search import SearchParams, run_search
from app.utils.geo import haversine_km

router = APIRouter(tags=["catalog"])


def _dist(lat, lng, s: Shop) -> float | None:
    return haversine_km(lat, lng, s.lat, s.lng) if lat is not None and lng is not None else None


def price_insight(db, product: Product) -> dict | None:
    if not product.catalog_item_id:
        return None
    prices = db.scalars(
        select(Product.price).where(Product.catalog_item_id == product.catalog_item_id, Product.is_active.is_(True))
    ).all()
    if len(prices) < 3:
        return {"peer_count": len(prices), "median": None, "min": min(prices), "max": max(prices), "statement": None}
    med = float(median(prices))
    diff = product.price - med
    pct = diff / med * 100
    if abs(pct) < 3:
        statement = "Priced in line with other shops nearby"
    elif diff < 0:
        statement = f"Rs {abs(diff):.0f} below the typical price across {len(prices)} shops"
    else:
        statement = f"Rs {diff:.0f} above the typical price across {len(prices)} shops"
    return {"peer_count": len(prices), "median": round(med, 2), "min": min(prices), "max": max(prices),
            "deviation_pct": round(pct, 1), "statement": statement}


@router.get("/products/{product_id}")
def product_detail(product_id: int, db: DB, user: OptionalUser, lat: float | None = None, lng: float | None = None):
    p = db.get(Product, product_id)
    if p is None or not p.is_active:
        raise NotFound("This product is no longer listed")
    shop = p.shop
    distance = _dist(lat, lng, shop)

    others = []
    if p.catalog_item_id:
        rows = db.scalars(
            select(Product)
            .options(selectinload(Product.shop).selectinload(Shop.categories), selectinload(Product.category))
            .join(Shop)
            .where(Product.catalog_item_id == p.catalog_item_id, Product.id != p.id, Product.is_active.is_(True),
                   Shop.is_active.is_(True))
        ).all()
        ratings = ratings_for(db, [r.shop_id for r in rows])
        others = [listing(r, shop_brief(r.shop, _dist(lat, lng, r.shop), ratings.get(r.shop_id))) for r in rows]
        others.sort(key=lambda o: (o["quantity"] <= 0, o["shop"]["distance_km"] if o["shop"]["distance_km"]
                                   is not None else o["price"]))

    # Reviews of this exact listing first, then recent reviews of the shop.
    base = select(Review).options(selectinload(Review.customer)).order_by(Review.created_at.desc())
    reviews = list(db.scalars(base.where(Review.product_id == p.id).limit(6)))
    if len(reviews) < 6:
        reviews += db.scalars(
            base.where(Review.shop_id == shop.id, Review.product_id.is_distinct_from(p.id)).limit(6 - len(reviews))
        ).all()
    product_names = dict(db.execute(select(Product.id, Product.name).where(
        Product.id.in_([r.product_id for r in reviews if r.product_id]))).all())

    sold_30d = db.scalar(
        select(func.coalesce(func.sum(SalesRecord.quantity), 0)).where(
            SalesRecord.product_id == p.id, SalesRecord.sold_at >= utcnow() - timedelta(days=30))
    )

    my_reservation = None
    if user and user.role == Role.CUSTOMER:
        r = db.scalar(select(Reservation).where(
            Reservation.customer_id == user.id, Reservation.product_id == p.id,
            Reservation.status.in_(reservation_service.ACTIVE)))
        if r:
            my_reservation = {"id": r.id, "code": r.code, "status": r.status.value}

    catalog = p.catalog_item
    return {
        **listing(p, None),
        "description": p.description,
        "specs": p.specs or {},
        "sku": p.sku,
        "category_detail": {"slug": p.category.slug, "name": p.category.name, "icon": p.category.icon,
                            "color_hue": p.category.color_hue},
        "subcategory": catalog.subcategory if catalog else None,
        "shop": shop_detail(shop, distance, shop_reliability(db, shop)),
        "other_offers": others,
        "price_insight": price_insight(db, p),
        "delivery_quote": quote_delivery(shop, lat, lng, p.price) if lat is not None and lng is not None else None,
        "reviews": [review_out(r, product_names.get(r.product_id)) for r in reviews],
        "sold_last_30d": int(sold_30d or 0),
        "my_reservation": my_reservation,
    }


@router.get("/products/{product_id}/recommendations")
def product_recommendations(product_id: int, db: DB, lat: float | None = None, lng: float | None = None):
    p = db.get(Product, product_id)
    if p is None:
        raise NotFound("Product not found")
    lat = lat if lat is not None else p.shop.lat
    lng = lng if lng is not None else p.shop.lng

    source = "apriori"
    targets = bundle_for(db, p.catalog_item_id) if p.catalog_item_id else []
    if not targets:
        source = "popular"
        sub = p.catalog_item.subcategory if p.catalog_item else None
        popular = db.execute(
            select(CatalogItem.id, func.sum(SalesRecord.quantity).label("n"))
            .join(SalesRecord, SalesRecord.catalog_item_id == CatalogItem.id)
            .where(CatalogItem.category_id == p.category_id, CatalogItem.id != (p.catalog_item_id or -1),
                   *( [CatalogItem.subcategory != sub] if sub else [] ))
            .group_by(CatalogItem.id).order_by(func.sum(SalesRecord.quantity).desc()).limit(6)
        ).all()
        targets = [{"catalog_item_id": cid, "confidence": None, "lift": None, "support": None} for cid, _ in popular]

    items = []
    for t in targets:
        offers = db.scalars(
            select(Product).options(selectinload(Product.shop).selectinload(Shop.categories),
                                    selectinload(Product.category))
            .join(Shop)
            .where(Product.catalog_item_id == t["catalog_item_id"], Product.is_active.is_(True),
                   Product.quantity > 0, Shop.is_active.is_(True))
        ).all()
        if not offers:
            continue
        same = next((o for o in offers if o.shop_id == p.shop_id), None)
        best = same or min(offers, key=lambda o: haversine_km(lat, lng, o.shop.lat, o.shop.lng))
        if not same and haversine_km(lat, lng, best.shop.lat, best.shop.lng) > 8:
            continue
        items.append({
            **{k: t[k] for k in ("confidence", "lift", "support")},
            "same_shop": same is not None,
            "offer": listing(best, shop_brief(best.shop, haversine_km(lat, lng, best.shop.lat, best.shop.lng))),
        })
    return {"source": source, "items": items[:4]}


@router.get("/shops")
def list_shops(
    db: DB,
    lat: float | None = None,
    lng: float | None = None,
    radius_km: float = Query(8, gt=0, le=50),
    category: str | None = None,
    q: str | None = Query(None, max_length=80),
    sort: str = "distance",
):
    if lat is None or lng is None:
        c = city_config()["center"]
        lat, lng = c["lat"], c["lng"]
    stmt = select(Shop).options(selectinload(Shop.categories)).where(Shop.is_active.is_(True))
    if category:
        stmt = stmt.where(Shop.categories.any(Category.slug == category))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where((Shop.name.ilike(like)) | (Shop.locality.ilike(like)) | (Shop.tagline.ilike(like)))
    shops = [(s, haversine_km(lat, lng, s.lat, s.lng)) for s in db.scalars(stmt)]
    shops = [(s, d) for s, d in shops if d <= radius_km]
    ratings = ratings_for(db, [s.id for s, _ in shops])
    counts = dict(db.execute(
        select(Product.shop_id, func.count()).where(Product.is_active.is_(True), Product.quantity > 0)
        .group_by(Product.shop_id)).all())
    out = [{**shop_brief(s, d, ratings.get(s.id)), "in_stock_listings": counts.get(s.id, 0)} for s, d in shops]
    if sort == "rating":
        out.sort(key=lambda s: (-(s["rating_avg"] or 0), s["distance_km"]))
    elif sort == "fresh":
        out.sort(key=lambda s: s["inventory_updated_at"] or "", reverse=True)
    else:
        out.sort(key=lambda s: s["distance_km"])
    return {"shops": out, "center": {"lat": lat, "lng": lng}, "radius_km": radius_km}


def _shop_by_slug(db, slug: str) -> Shop:
    shop = db.scalar(select(Shop).options(selectinload(Shop.categories)).where(Shop.slug == slug))
    if shop is None or not shop.is_active:
        raise NotFound("Shop not found")
    return shop


@router.get("/shops/{slug}")
def shop_page(slug: str, db: DB, lat: float | None = None, lng: float | None = None):
    shop = _shop_by_slug(db, slug)
    data = shop_detail(shop, _dist(lat, lng, shop), shop_reliability(db, shop))
    data["listing_counts"] = {
        "total": db.scalar(select(func.count()).select_from(Product).where(
            Product.shop_id == shop.id, Product.is_active.is_(True))) or 0,
        "in_stock": db.scalar(select(func.count()).select_from(Product).where(
            Product.shop_id == shop.id, Product.is_active.is_(True), Product.quantity > 0)) or 0,
    }
    return data


@router.get("/shops/{slug}/products")
def shop_products(
    slug: str, db: DB,
    q: str = Query("", max_length=120),
    category: str | None = None,
    in_stock_only: bool = False,
    sort: str = "relevance",
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=60),
):
    shop = _shop_by_slug(db, slug)
    params = SearchParams(q=q, lat=shop.lat, lng=shop.lng, radius_km=0.5, category=category,
                          in_stock_only=in_stock_only, sort=sort if sort in {"price_asc", "price_desc"} else "relevance",
                          shop_id=shop.id, page=page, page_size=page_size)
    result = run_search(db, params, log=False)
    items = [g["best_offer"] for g in result["groups"]]
    if not q and sort == "relevance":
        items.sort(key=lambda i: (i["quantity"] <= 0, i["name"]))
    return {"items": items, "total": result["total"], "has_more": result["has_more"],
            "category_counts": result["category_counts"]}


@router.get("/shops/{slug}/reviews")
def shop_reviews(slug: str, db: DB, page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=50)):
    shop = _shop_by_slug(db, slug)
    rows = db.scalars(
        select(Review).options(selectinload(Review.customer)).where(Review.shop_id == shop.id)
        .order_by(Review.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    names = dict(db.execute(select(Product.id, Product.name).where(
        Product.id.in_([r.product_id for r in rows if r.product_id]))).all())
    dist = dict(db.execute(select(Review.rating, func.count()).where(Review.shop_id == shop.id)
                           .group_by(Review.rating)).all())
    return {"reviews": [review_out(r, names.get(r.product_id)) for r in rows],
            "distribution": {str(k): dist.get(k, 0) for k in range(1, 6)}}
