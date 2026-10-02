"""Numbers behind the shop-owner and admin dashboards."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.ai.semantic_index import index
from app.core.database import utcnow
from app.models import (
    AnomalyStatus,
    AssociationRule,
    CatalogItem,
    Category,
    DemandForecast,
    InventoryEvent,
    InventoryReason,
    ModelRun,
    Order,
    OrderStatus,
    PriceAnomaly,
    Product,
    Reservation,
    ReservationStatus,
    Role,
    SalesRecord,
    SearchEvent,
    Shop,
    User,
)
from app.schemas.serializers import iso, listing
from app.services.reliability import ratings_for
from app.services.search import keyword_scores
from app.utils.geo import bounding_box, haversine_km
from app.utils.text import normalize_query

IST = ZoneInfo("Asia/Kolkata")


def ist_day_start_utc(days_ago: int = 0) -> datetime:
    """UTC timestamp of local (IST) midnight `days_ago` days back."""
    now_ist = datetime.now(IST)
    midnight = (now_ist - timedelta(days=days_ago)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def _daily_series(rows: list[tuple[str, float, float]], days: int) -> list[dict]:
    by_day = {d: (rev, units) for d, rev, units in rows}
    out = []
    for i in range(days - 1, -1, -1):
        day = (datetime.now(IST) - timedelta(days=i)).date().isoformat()
        rev, units = by_day.get(day, (0, 0))
        out.append({"date": day, "revenue": round(float(rev or 0), 2), "units": int(units or 0)})
    return out


def _sales_by_ist_day(db: Session, *filters, days: int = 30) -> list[dict]:
    # SQLite: shift UTC to IST (+5:30) before taking the date.
    day = func.date(SalesRecord.sold_at, "+330 minutes")
    rows = db.execute(
        select(day, func.sum(SalesRecord.quantity * SalesRecord.unit_price), func.sum(SalesRecord.quantity))
        .where(SalesRecord.sold_at >= ist_day_start_utc(days - 1), *filters)
        .group_by(day)
    ).all()
    return _daily_series(rows, days)


def _revenue(db: Session, since: datetime, until: datetime | None = None, *filters) -> float:
    stmt = select(func.coalesce(func.sum(SalesRecord.quantity * SalesRecord.unit_price), 0)).where(
        SalesRecord.sold_at >= since, *filters)
    if until:
        stmt = stmt.where(SalesRecord.sold_at < until)
    return round(float(db.scalar(stmt) or 0), 2)


# ------------------------------------------------------------------ shop owner

def owner_overview(db: Session, shop: Shop) -> dict:
    today = ist_day_start_utc(0)
    f = (SalesRecord.shop_id == shop.id,)
    active_listings = select(func.count()).select_from(Product).where(Product.shop_id == shop.id,
                                                                      Product.is_active.is_(True))

    def count_res(*statuses):
        return db.scalar(select(func.count()).select_from(Reservation).where(
            Reservation.shop_id == shop.id, Reservation.status.in_(statuses))) or 0

    def count_orders(*statuses):
        return db.scalar(select(func.count()).select_from(Order).where(
            Order.shop_id == shop.id, Order.status.in_(statuses))) or 0

    series = _sales_by_ist_day(db, *f, days=30)
    top = db.execute(
        select(Product.id, func.sum(SalesRecord.quantity).label("units"),
               func.sum(SalesRecord.quantity * SalesRecord.unit_price).label("revenue"))
        .join(Product, Product.id == SalesRecord.product_id)
        .where(SalesRecord.shop_id == shop.id, SalesRecord.sold_at >= ist_day_start_utc(29))
        .group_by(Product.id).order_by(func.sum(SalesRecord.quantity).desc()).limit(6)
    ).all()
    top_products = {p.id: p for p in db.scalars(select(Product).options(selectinload(Product.category))
                                                  .where(Product.id.in_([t.id for t in top])))}

    low = db.scalars(
        select(Product).options(selectinload(Product.category))
        .where(Product.shop_id == shop.id, Product.is_active.is_(True),
               Product.quantity <= Product.low_stock_threshold)
        .order_by(Product.quantity).limit(8)
    ).all()
    forecasts = {f.product_id: f for f in db.scalars(select(DemandForecast).where(
        DemandForecast.product_id.in_([p.id for p in low])))}

    uses_demo = bool(db.scalar(select(func.count()).select_from(SalesRecord).where(
        SalesRecord.shop_id == shop.id, SalesRecord.is_demo.is_(True))))
    rating = ratings_for(db, [shop.id]).get(shop.id, (None, 0))

    return {
        "today": {
            "revenue": _revenue(db, today, None, *f),
            "units": int(db.scalar(select(func.coalesce(func.sum(SalesRecord.quantity), 0)).where(
                SalesRecord.sold_at >= today, *f)) or 0),
            "reservations": db.scalar(select(func.count()).select_from(Reservation).where(
                Reservation.shop_id == shop.id, Reservation.created_at >= today)) or 0,
            "orders": db.scalar(select(func.count()).select_from(Order).where(
                Order.shop_id == shop.id, Order.created_at >= today)) or 0,
        },
        "revenue_7d": _revenue(db, ist_day_start_utc(6), None, *f),
        "revenue_prev_7d": _revenue(db, ist_day_start_utc(13), ist_day_start_utc(6), *f),
        "revenue_30d": _revenue(db, ist_day_start_utc(29), None, *f),
        "queue": {
            "reservation_requests": count_res(ReservationStatus.REQUESTED),
            "pickups_waiting": count_res(ReservationStatus.CONFIRMED, ReservationStatus.READY_FOR_PICKUP),
            "orders_pending": count_orders(OrderStatus.PENDING),
            "deliveries_in_progress": count_orders(OrderStatus.SHOP_CONFIRMED, OrderStatus.PREPARING,
                                                   OrderStatus.OUT_FOR_DELIVERY),
        },
        "inventory": {
            "listings": db.scalar(active_listings) or 0,
            "in_stock": db.scalar(active_listings.where(Product.quantity > Product.low_stock_threshold)) or 0,
            "low_stock": db.scalar(active_listings.where(Product.quantity > 0,
                                                         Product.quantity <= Product.low_stock_threshold)) or 0,
            "out_of_stock": db.scalar(active_listings.where(Product.quantity == 0)) or 0,
            "updated_at": iso(shop.inventory_updated_at),
        },
        "sales_series": series,
        "top_products": [
            {**listing(top_products[t.id]), "units": int(t.units), "revenue": round(float(t.revenue), 2)}
            for t in top if t.id in top_products
        ],
        "low_stock": [
            {**listing(p), "days_to_stockout": forecasts[p.id].days_to_stockout if p.id in forecasts else None,
             "recommended_restock": forecasts[p.id].recommended_restock if p.id in forecasts else None}
            for p in low
        ],
        "rating": {"avg": rating[0], "count": rating[1]},
        "includes_demo_data": uses_demo,
    }


def owner_insights(db: Session, shop: Shop) -> dict:
    # 1. Demand forecasts (Random Forest)
    fc_rows = db.execute(
        select(DemandForecast, Product).join(Product, Product.id == DemandForecast.product_id)
        .options(selectinload(Product.category))
        .where(DemandForecast.shop_id == shop.id, Product.is_active.is_(True))
    ).all()
    restock, rising = [], []
    for fc, p in fc_rows:
        item = {
            **listing(p),
            "predicted_7d": fc.predicted_7d,
            "daily_rate": fc.daily_rate,
            "days_to_stockout": fc.days_to_stockout,
            "recommended_restock": fc.recommended_restock,
            "trend": fc.trend,
            "confidence": fc.confidence,
            "is_demo": fc.is_demo,
        }
        if fc.recommended_restock > 0 or (fc.days_to_stockout is not None and fc.days_to_stockout < 10):
            restock.append(item)
        if fc.trend == "rising" and fc.predicted_7d >= 3:
            rising.append(item)
    restock.sort(key=lambda x: (x["days_to_stockout"] if x["days_to_stockout"] is not None else 999))
    rising.sort(key=lambda x: -x["predicted_7d"])

    # 2. Price review flags (Isolation Forest) for this shop's own listings
    flags = db.execute(
        select(PriceAnomaly, Product).join(Product, Product.id == PriceAnomaly.product_id)
        .where(PriceAnomaly.shop_id == shop.id, PriceAnomaly.status == AnomalyStatus.OPEN)
        .order_by(PriceAnomaly.score.desc())
    ).all()
    price_flags = [
        {"id": a.id, "product": listing(p), "price": a.price, "reference_price": a.reference_price,
         "deviation_pct": a.deviation_pct, "direction": a.direction, "peer_count": a.peer_count}
        for a, p in flags
    ]

    # 3. What people nearby are searching for (last 14 days, within 3 km)
    since = utcnow() - timedelta(days=14)
    min_lat, max_lat, min_lng, max_lng = bounding_box(shop.lat, shop.lng, 3)
    searches = db.execute(
        select(SearchEvent.normalized_query, SearchEvent.results_count, SearchEvent.lat, SearchEvent.lng)
        .where(SearchEvent.created_at >= since, SearchEvent.lat.between(min_lat, max_lat),
               SearchEvent.lng.between(min_lng, max_lng))
    ).all()
    counts: dict[str, int] = {}
    zero: dict[str, int] = {}
    for q, n, la, ln in searches:
        if la is None or haversine_km(shop.lat, shop.lng, la, ln) > 3:
            continue
        counts[q] = counts.get(q, 0) + 1
        if n == 0:
            zero[q] = zero.get(q, 0) + 1
    top_queries = sorted(counts.items(), key=lambda kv: -kv[1])[:10]
    shop_product_ids = set(db.scalars(select(Product.id).where(
        Product.shop_id == shop.id, Product.is_active.is_(True), Product.quantity > 0)))
    area_demand = []
    for q, n in top_queries:
        kw = keyword_scores(db, normalize_query(q).split())
        sem = index.query(db, q)
        stocked = any(pid in kw or sem.get(pid, 0) > 0.5 for pid in shop_product_ids)
        area_demand.append({"query": q, "searches": n, "you_stock_it": stocked})

    # 4. Bundle gaps (Apriori): things often bought with what you sell, that you do not stock
    my_items = set(db.scalars(select(Product.catalog_item_id).where(
        Product.shop_id == shop.id, Product.is_active.is_(True), Product.catalog_item_id.is_not(None))))
    gaps: dict[int, dict] = {}
    if my_items:
        for rule in db.scalars(select(AssociationRule).order_by(AssociationRule.lift.desc()).limit(3000)):
            if len(rule.antecedents) != 1 or rule.antecedents[0] not in my_items:
                continue
            for c in rule.consequents:
                if c not in my_items and (c not in gaps or gaps[c]["confidence"] < rule.confidence):
                    gaps[c] = {"catalog_item_id": c, "because_of": rule.antecedents[0], "confidence": rule.confidence,
                               "lift": rule.lift}
    top_gaps = sorted(gaps.values(), key=lambda g: -g["confidence"] * g["lift"])[:6]
    names = {c.id: c for c in db.scalars(select(CatalogItem).where(
        CatalogItem.id.in_([g["catalog_item_id"] for g in top_gaps] + [g["because_of"] for g in top_gaps])))}
    bundle_gaps = [
        {"item": {"id": g["catalog_item_id"], "name": names[g["catalog_item_id"]].name,
                  "icon": names[g["catalog_item_id"]].icon,
                  "typical_price": names[g["catalog_item_id"]].typical_price},
         "because_of": names[g["because_of"]].name, "confidence": g["confidence"], "lift": g["lift"]}
        for g in top_gaps if g["catalog_item_id"] in names and g["because_of"] in names
    ]

    runs = {r.name: r for r in db.scalars(select(ModelRun).order_by(ModelRun.created_at))}
    return {
        "restock": restock[:12],
        "rising": rising[:6],
        "price_flags": price_flags,
        "area_demand": area_demand,
        "missed_demand": [{"query": q, "searches": n} for q, n in sorted(zero.items(), key=lambda kv: -kv[1])[:6]],
        "bundle_gaps": bundle_gaps,
        "models": {
            name: {"algorithm": r.algorithm, "trained_at": iso(r.created_at), "uses_demo_data": r.uses_demo_data,
                   "metrics": r.metrics, "note": r.data_note}
            for name, r in runs.items() if name in {"demand", "recommendations", "anomalies"}
        },
    }


# ------------------------------------------------------------------ admin

def admin_overview(db: Session) -> dict:
    def count(model, *where):
        return db.scalar(select(func.count()).select_from(model).where(*where)) or 0

    since30 = ist_day_start_utc(29)
    res_status = dict(db.execute(select(Reservation.status, func.count()).group_by(Reservation.status)).all())
    ord_status = dict(db.execute(select(Order.status, func.count()).group_by(Order.status)).all())

    cat_sales = db.execute(
        select(Category.name, Category.slug, Category.color_hue,
               func.sum(SalesRecord.quantity * SalesRecord.unit_price).label("rev"))
        .join(Product, Product.id == SalesRecord.product_id).join(Category, Category.id == Product.category_id)
        .where(SalesRecord.sold_at >= since30).group_by(Category.id).order_by(func.sum(
            SalesRecord.quantity * SalesRecord.unit_price).desc())
    ).all()
    cat_searches = dict(db.execute(select(SearchEvent.category_slug, func.count())
                                   .where(SearchEvent.category_slug.is_not(None))
                                   .group_by(SearchEvent.category_slug)).all())

    top_shops = db.execute(
        select(Shop.id, Shop.name, Shop.slug, Shop.locality,
               func.sum(SalesRecord.quantity * SalesRecord.unit_price).label("rev"),
               func.count(func.distinct(SalesRecord.basket_id)).label("baskets"))
        .join(SalesRecord, SalesRecord.shop_id == Shop.id)
        .where(SalesRecord.sold_at >= since30).group_by(Shop.id)
        .order_by(func.sum(SalesRecord.quantity * SalesRecord.unit_price).desc()).limit(8)
    ).all()
    ratings = ratings_for(db, [s.id for s in top_shops])

    popular = db.execute(
        select(SearchEvent.normalized_query, func.count().label("n"), func.avg(SearchEvent.results_count))
        .where(SearchEvent.created_at >= utcnow() - timedelta(days=14))
        .group_by(SearchEvent.normalized_query).order_by(func.count().desc()).limit(10)
    ).all()
    zero = db.execute(
        select(SearchEvent.normalized_query, func.count().label("n"))
        .where(SearchEvent.results_count == 0, SearchEvent.created_at >= utcnow() - timedelta(days=30))
        .group_by(SearchEvent.normalized_query).order_by(func.count().desc()).limit(8)
    ).all()

    inv_day = func.date(InventoryEvent.created_at, "+330 minutes")
    inv_rows = dict(db.execute(
        select(inv_day, func.count()).where(
            InventoryEvent.created_at >= ist_day_start_utc(13),
            InventoryEvent.reason.in_([InventoryReason.RESTOCK.value, InventoryReason.ADJUSTMENT.value,
                                       InventoryReason.INITIAL.value]))
        .group_by(inv_day)).all())
    search_day = func.date(SearchEvent.created_at, "+330 minutes")
    search_rows = dict(db.execute(select(search_day, func.count()).where(
        SearchEvent.created_at >= ist_day_start_utc(13)).group_by(search_day)).all())
    activity = []
    for i in range(13, -1, -1):
        d = (datetime.now(IST) - timedelta(days=i)).date().isoformat()
        activity.append({"date": d, "inventory_updates": inv_rows.get(d, 0), "searches": search_rows.get(d, 0)})

    return {
        "totals": {
            "customers": count(User, User.role == Role.CUSTOMER),
            "owners": count(User, User.role == Role.OWNER),
            "shops": count(Shop, Shop.is_active.is_(True)),
            "shops_verified": count(Shop, Shop.is_verified.is_(True)),
            "listings": count(Product, Product.is_active.is_(True)),
            "in_stock": count(Product, Product.is_active.is_(True), Product.quantity > 0),
            "reservations": sum(res_status.values()),
            "orders": sum(ord_status.values()),
            "revenue_30d": _revenue(db, since30),
            "revenue_30d_real": _revenue(db, since30, None, SalesRecord.is_demo.is_(False)),
            "searches_30d": count(SearchEvent, SearchEvent.created_at >= since30),
            "open_price_flags": count(PriceAnomaly, PriceAnomaly.status == AnomalyStatus.OPEN),
        },
        "reservations_by_status": {k.value: v for k, v in res_status.items()},
        "orders_by_status": {k.value: v for k, v in ord_status.items()},
        "sales_series": _sales_by_ist_day(db, days=30),
        "categories": [{"name": n, "slug": s, "color_hue": h, "revenue_30d": round(float(r or 0), 2),
                        "searches": cat_searches.get(s, 0)} for n, s, h, r in cat_sales],
        "top_shops": [{"id": s.id, "name": s.name, "slug": s.slug, "locality": s.locality,
                       "revenue_30d": round(float(s.rev), 2), "baskets": s.baskets,
                       "rating_avg": ratings.get(s.id, (None, 0))[0]} for s in top_shops],
        "popular_searches": [{"query": q, "count": n, "avg_results": round(float(a or 0), 1)} for q, n, a in popular],
        "zero_result_searches": [{"query": q, "count": n} for q, n in zero],
        "activity": activity,
    }
