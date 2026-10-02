"""Public product and shop pages."""
import re
from datetime import timedelta
from statistics import median

from fastapi import APIRouter, Query

from app.ai.recommend import bundle_for
from app.core.database import Database, utcnow
from app.core.deps import DB, OptionalUser
from app.core.errors import NotFound
from app.models import Product, Role, Shop
from app.schemas.serializers import listing, review_out, shop_brief, shop_detail
from app.services import reservations as reservation_service
from app.services.loaders import (
    category_by_slug,
    product_names,
    with_categories,
    with_category,
    with_customers,
    with_shops,
)
from app.services.meta import city_config
from app.services.orders import quote_delivery
from app.services.reliability import shop_reliability
from app.services.search import SearchParams, run_search
from app.utils.geo import haversine_km, within_km

router = APIRouter(tags=["catalog"])


def _dist(lat, lng, s: Shop) -> float | None:
    return haversine_km(lat, lng, s.lat, s.lng) if lat is not None and lng is not None else None


def price_insight(product: Product, prices: list[float]) -> dict | None:
    """Where this price sits among every active listing of the same catalogue item."""
    if not product.catalog_item_id or not prices:
        return None
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


def _sold_last_30d(db: Database, product_id: int) -> int:
    rows = db.sales_history.aggregate([
        {"$match": {"product_id": product_id, "sold_at": {"$gte": utcnow() - timedelta(days=30)}}},
        {"$group": {"_id": None, "n": {"$sum": "$quantity"}}},
    ])
    return int(rows[0]["n"]) if rows else 0


@router.get("/products/{product_id}")
def product_detail(product_id: int, db: DB, user: OptionalUser, lat: float | None = None, lng: float | None = None):
    p = db.products.get(product_id)
    if p is None or not p.is_active:
        raise NotFound("This product is no longer listed")
    with_category(db, [p])

    def same_item() -> list[Product]:
        # Every active listing of this catalogue item, this one included (for the price insight).
        if not p.catalog_item_id:
            return []
        return with_shops(db, db.products.find({"catalog_item_id": p.catalog_item_id, "is_active": True}),
                          active_only=True)

    def my_reservation() -> dict | None:
        if not (user and user.role == Role.CUSTOMER):
            return None
        r = db.reservations.find_one({"customer_id": user.id, "product_id": p.id,
                                      "status": {"$in": list(reservation_service.ACTIVE)}})
        return {"id": r.id, "code": r.code, "status": r.status.value} if r else None

    shop, catalog, peers, own_reviews, sold_30d, reservation = db.gather(
        lambda: with_categories(db, [db.shops.get(p.shop_id)])[0],
        lambda: db.catalog_items.get(p.catalog_item_id),
        same_item,
        lambda: db.reviews.find({"product_id": p.id}, sort=[("created_at", -1)], limit=6),
        lambda: _sold_last_30d(db, p.id),
        my_reservation,
    )
    distance = _dist(lat, lng, shop)

    others = [listing(r, shop_brief(r.shop, _dist(lat, lng, r.shop))) for r in peers if r.id != p.id]
    others.sort(key=lambda o: (o["quantity"] <= 0, o["shop"]["distance_km"] if o["shop"]["distance_km"]
                               is not None else o["price"]))

    # Reviews of this exact listing first, then recent reviews of the shop.
    reviews = list(own_reviews)
    if len(reviews) < 6:
        reviews += db.reviews.find({"shop_id": shop.id, "product_id": {"$ne": p.id}},
                                   sort=[("created_at", -1)], limit=6 - len(reviews))
    reliability, _, names = db.gather(
        lambda: shop_reliability(db, shop),
        lambda: with_customers(db, reviews),
        lambda: product_names(db, (r.product_id for r in reviews)),
    )

    return {
        **listing(p, None),
        "description": p.description,
        "specs": p.specs or {},
        "sku": p.sku,
        "category_detail": {"slug": p.category.slug, "name": p.category.name, "icon": p.category.icon,
                            "color_hue": p.category.color_hue},
        "subcategory": catalog.subcategory if catalog else None,
        "shop": shop_detail(shop, distance, reliability),
        "other_offers": others,
        "price_insight": price_insight(p, [r.price for r in peers]),
        "delivery_quote": quote_delivery(shop, lat, lng, p.price) if lat is not None and lng is not None else None,
        "reviews": [review_out(r, names.get(r.product_id)) for r in reviews],
        "sold_last_30d": sold_30d,
        "my_reservation": reservation,
    }


@router.get("/products/{product_id}/recommendations")
def product_recommendations(product_id: int, db: DB, lat: float | None = None, lng: float | None = None):
    p = db.products.get(product_id)
    if p is None:
        raise NotFound("Product not found")
    shop, catalog = db.gather(lambda: db.shops.get(p.shop_id), lambda: db.catalog_items.get(p.catalog_item_id))
    lat = lat if lat is not None else shop.lat
    lng = lng if lng is not None else shop.lng

    source = "apriori"
    targets = bundle_for(db, p.catalog_item_id) if p.catalog_item_id else []
    if not targets:
        source = "popular"
        sub = catalog.subcategory if catalog else None
        # Best sellers in the same category, from a different subcategory than this item.
        query: dict = {"category_id": p.category_id, "_id": {"$ne": p.catalog_item_id or -1}}
        if sub:
            query["subcategory"] = {"$ne": sub}
        candidates = [d["_id"] for d in db.catalog_items.find_raw(query, {"_id": 1})]
        popular = db.sales_history.aggregate([
            {"$match": {"catalog_item_id": {"$in": candidates}}},
            {"$group": {"_id": "$catalog_item_id", "n": {"$sum": "$quantity"}}},
            {"$sort": {"n": -1}},
            {"$limit": 6},
        ]) if candidates else []
        targets = [{"catalog_item_id": r["_id"], "confidence": None, "lift": None, "support": None} for r in popular]

    # One query for the in-stock offers of every recommended item.
    offers_by_item: dict[int, list[Product]] = {}
    target_ids = [t["catalog_item_id"] for t in targets]
    if target_ids:
        for o in with_shops(db, db.products.find({"catalog_item_id": {"$in": target_ids}, "is_active": True,
                                                  "quantity": {"$gt": 0}}), active_only=True):
            offers_by_item.setdefault(o.catalog_item_id, []).append(o)

    items = []
    for t in targets:
        offers = offers_by_item.get(t["catalog_item_id"])
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
    query: dict = {"is_active": True, "location": within_km(lat, lng, radius_km)}
    if category:
        cat = category_by_slug(db, category)
        query["category_ids"] = cat.id if cat else -1
    if q:
        like = {"$regex": re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"name": like}, {"locality": like}, {"tagline": like}]
    found, counts = db.gather(
        lambda: with_categories(db, db.shops.find(query)),
        lambda: {r["_id"]: r["n"] for r in db.products.aggregate([
            {"$match": {"is_active": True, "quantity": {"$gt": 0}}},
            {"$group": {"_id": "$shop_id", "n": {"$sum": 1}}}])},
    )
    shops = [(s, haversine_km(lat, lng, s.lat, s.lng)) for s in found]
    out = [{**shop_brief(s, d), "in_stock_listings": counts.get(s.id, 0)} for s, d in shops if d <= radius_km]
    if sort == "rating":
        out.sort(key=lambda s: (-(s["rating_avg"] or 0), s["distance_km"]))
    elif sort == "fresh":
        out.sort(key=lambda s: s["inventory_updated_at"] or "", reverse=True)
    else:
        out.sort(key=lambda s: s["distance_km"])
    return {"shops": out, "center": {"lat": lat, "lng": lng}, "radius_km": radius_km}


def _shop_by_slug(db: Database, slug: str) -> Shop:
    shop = db.shops.find_one({"slug": slug})
    if shop is None or not shop.is_active:
        raise NotFound("Shop not found")
    return with_categories(db, [shop])[0]


@router.get("/shops/{slug}")
def shop_page(slug: str, db: DB, lat: float | None = None, lng: float | None = None):
    shop = _shop_by_slug(db, slug)
    reliability, total, in_stock = db.gather(
        lambda: shop_reliability(db, shop),
        lambda: db.products.count({"shop_id": shop.id, "is_active": True}),
        lambda: db.products.count({"shop_id": shop.id, "is_active": True, "quantity": {"$gt": 0}}),
    )
    data = shop_detail(shop, _dist(lat, lng, shop), reliability)
    data["listing_counts"] = {"total": total, "in_stock": in_stock}
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
    rows, dist = db.gather(
        lambda: with_customers(db, db.reviews.find({"shop_id": shop.id}, sort=[("created_at", -1)],
                                                   skip=(page - 1) * page_size, limit=page_size)),
        lambda: {r["_id"]: r["n"] for r in db.reviews.aggregate([
            {"$match": {"shop_id": shop.id}}, {"$group": {"_id": "$rating", "n": {"$sum": 1}}}])},
    )
    names = product_names(db, (r.product_id for r in rows))
    return {"reviews": [review_out(r, names.get(r.product_id)) for r in rows],
            "distribution": {str(k): dist.get(k, 0) for k in range(1, 6)}}
