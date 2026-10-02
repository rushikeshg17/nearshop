"""Numbers behind the shop-owner and admin dashboards.

Each figure is one aggregation pipeline that runs inside MongoDB; the independent ones for a
page are sent together (db.gather), so a dashboard costs about one network round trip.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.ai.semantic_index import index
from app.core.database import Database, utcnow
from app.models import AnomalyStatus, InventoryReason, OrderStatus, ReservationStatus, Role, Shop
from app.schemas.serializers import iso, listing
from app.services.loaders import categories, with_category
from app.services.search import keyword_scores
from app.utils.geo import within_km
from app.utils.text import normalize_query

IST = ZoneInfo("Asia/Kolkata")
REVENUE = {"$sum": {"$multiply": ["$quantity", "$unit_price"]}}


def ist_day(field: str) -> dict:
    """Aggregation expression: the local (IST) calendar day of a UTC timestamp, as YYYY-MM-DD."""
    return {"$dateToString": {"format": "%Y-%m-%d", "date": field, "timezone": "Asia/Kolkata"}}


def ist_day_start_utc(days_ago: int = 0) -> datetime:
    """UTC timestamp of local (IST) midnight `days_ago` days back."""
    now_ist = datetime.now(IST)
    midnight = (now_ist - timedelta(days=days_ago)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def _sales_by_ist_day(db: Database, match: dict | None = None, days: int = 30) -> list[dict]:
    rows = db.sales_history.aggregate([
        {"$match": {"sold_at": {"$gte": ist_day_start_utc(days - 1)}, **(match or {})}},
        {"$group": {"_id": ist_day("$sold_at"), "revenue": REVENUE, "units": {"$sum": "$quantity"}}},
    ])
    by_day = {r["_id"]: r for r in rows}
    out = []
    for i in range(days - 1, -1, -1):
        day = (datetime.now(IST) - timedelta(days=i)).date().isoformat()
        r = by_day.get(day, {})
        out.append({"date": day, "revenue": round(float(r.get("revenue") or 0), 2), "units": int(r.get("units") or 0)})
    return out


def _count_by(db_collection, field: str, match: dict | None = None) -> dict:
    return {r["_id"]: r["n"] for r in db_collection.aggregate([
        {"$match": match or {}}, {"$group": {"_id": f"${field}", "n": {"$sum": 1}}}])}


# ------------------------------------------------------------------ shop owner

def owner_overview(db: Database, shop: Shop) -> dict:
    today = ist_day_start_utc(0)
    mine = {"shop_id": shop.id}
    low_stock_expr = {"$expr": {"$lte": ["$quantity", "$low_stock_threshold"]}}

    def top_products() -> list[dict]:
        return db.sales_history.aggregate([
            {"$match": {**mine, "sold_at": {"$gte": ist_day_start_utc(29)}}},
            {"$group": {"_id": "$product_id", "units": {"$sum": "$quantity"}, "revenue": REVENUE}},
            {"$sort": {"units": -1, "_id": 1}},
            {"$limit": 6},
        ])

    def inventory() -> dict:
        rows = db.products.aggregate([
            {"$match": {**mine, "is_active": True}},
            {"$group": {
                "_id": None,
                "listings": {"$sum": 1},
                "in_stock": {"$sum": {"$cond": [{"$gt": ["$quantity", "$low_stock_threshold"]}, 1, 0]}},
                "low_stock": {"$sum": {"$cond": [{"$and": [{"$gt": ["$quantity", 0]},
                                                           {"$lte": ["$quantity", "$low_stock_threshold"]}]}, 1, 0]}},
                "out_of_stock": {"$sum": {"$cond": [{"$eq": ["$quantity", 0]}, 1, 0]}},
            }},
        ])
        return rows[0] if rows else {}

    series, top, inv, low, res_status, ord_status, res_today, orders_today, uses_demo = db.gather(
        lambda: _sales_by_ist_day(db, mine, days=30),
        top_products,
        inventory,
        lambda: with_category(db, db.products.find({**mine, "is_active": True, **low_stock_expr},
                                                   sort=[("quantity", 1)], limit=8)),
        lambda: _count_by(db.reservations, "status", mine),
        lambda: _count_by(db.orders, "status", mine),
        lambda: db.reservations.count({**mine, "created_at": {"$gte": today}}),
        lambda: db.orders.count({**mine, "created_at": {"$gte": today}}),
        lambda: db.sales_history.exists({**mine, "is_demo": True}),
    )
    top_by_id, forecasts = db.gather(
        lambda: {p.id: p for p in with_category(db, db.products.by_ids(t["_id"] for t in top).values())},
        lambda: {f.product_id: f for f in db.demand_forecasts.find({"product_id": {"$in": [p.id for p in low]}})},
    )

    def revenue(days_from: int, days_to: int = 0) -> float:
        """Revenue for the IST days [days_from .. days_to] ago, read off the 30-day series."""
        return round(sum(d["revenue"] for d in series[len(series) - 1 - days_from: len(series) - days_to]), 2)

    def res(*statuses) -> int:
        return sum(res_status.get(s.value, 0) for s in statuses)

    def orders(*statuses) -> int:
        return sum(ord_status.get(s.value, 0) for s in statuses)

    return {
        "today": {"revenue": series[-1]["revenue"], "units": series[-1]["units"], "reservations": res_today,
                  "orders": orders_today},
        "revenue_7d": revenue(6),
        "revenue_prev_7d": revenue(13, 7),
        "revenue_30d": revenue(29),
        "queue": {
            "reservation_requests": res(ReservationStatus.REQUESTED),
            "pickups_waiting": res(ReservationStatus.CONFIRMED, ReservationStatus.READY_FOR_PICKUP),
            "orders_pending": orders(OrderStatus.PENDING),
            "deliveries_in_progress": orders(OrderStatus.SHOP_CONFIRMED, OrderStatus.PREPARING,
                                             OrderStatus.OUT_FOR_DELIVERY),
        },
        "inventory": {
            "listings": inv.get("listings", 0),
            "in_stock": inv.get("in_stock", 0),
            "low_stock": inv.get("low_stock", 0),
            "out_of_stock": inv.get("out_of_stock", 0),
            "updated_at": iso(shop.inventory_updated_at),
        },
        "sales_series": series,
        "top_products": [
            {**listing(top_by_id[t["_id"]]), "units": int(t["units"]), "revenue": round(float(t["revenue"]), 2)}
            for t in top if t["_id"] in top_by_id
        ],
        "low_stock": [
            {**listing(p), "days_to_stockout": forecasts[p.id].days_to_stockout if p.id in forecasts else None,
             "recommended_restock": forecasts[p.id].recommended_restock if p.id in forecasts else None}
            for p in low
        ],
        "rating": {"avg": shop.rating_avg, "count": shop.rating_count},
        "includes_demo_data": uses_demo,
    }


def owner_insights(db: Database, shop: Shop) -> dict:
    since = utcnow() - timedelta(days=14)
    forecasts, flags, searches, my_products, rules, runs = db.gather(
        lambda: db.demand_forecasts.find({"shop_id": shop.id}),
        lambda: db.price_anomalies.find({"shop_id": shop.id, "status": AnomalyStatus.OPEN}, sort=[("score", -1)]),
        # What people within 3 km searched for in the last 14 days (2dsphere index).
        lambda: db.search_history.find_raw(
            {"created_at": {"$gte": since}, "location": within_km(shop.lat, shop.lng, 3)},
            {"normalized_query": 1, "results_count": 1}),
        lambda: db.products.find_raw({"shop_id": shop.id, "is_active": True}, {"catalog_item_id": 1, "quantity": 1}),
        lambda: db.recommendations.find(sort=[("lift", -1)], limit=3000),
        lambda: db.model_runs.find({"name": {"$in": ["demand", "recommendations", "anomalies"]}},
                                   sort=[("created_at", 1)]),
    )
    products = {p.id: p for p in with_category(
        db, db.products.by_ids([f.product_id for f in forecasts] + [a.product_id for a in flags]).values())}

    # 1. Demand forecasts (Random Forest)
    restock, rising = [], []
    for fc in forecasts:
        p = products.get(fc.product_id)
        if p is None or not p.is_active:
            continue
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
    price_flags = [
        {"id": a.id, "product": listing(products[a.product_id]), "price": a.price,
         "reference_price": a.reference_price, "deviation_pct": a.deviation_pct, "direction": a.direction,
         "peer_count": a.peer_count}
        for a in flags if a.product_id in products
    ]

    # 3. What people nearby are searching for
    counts: dict[str, int] = {}
    zero: dict[str, int] = {}
    for s in searches:
        q = s["normalized_query"]
        counts[q] = counts.get(q, 0) + 1
        if s["results_count"] == 0:
            zero[q] = zero.get(q, 0) + 1
    top_queries = sorted(counts.items(), key=lambda kv: -kv[1])[:10]
    in_stock_ids = {p["_id"] for p in my_products if p["quantity"] > 0}

    def stocked(q: str) -> bool:
        kw = keyword_scores(db, normalize_query(q).split())
        sem = index.query(db, q)
        return any(pid in kw or sem.get(pid, 0) > 0.5 for pid in in_stock_ids)

    stocked_flags = db.gather(*[lambda q=q: stocked(q) for q, _ in top_queries])
    area_demand = [{"query": q, "searches": n, "you_stock_it": s} for (q, n), s in zip(top_queries, stocked_flags)]

    # 4. Bundle gaps (Apriori): things often bought with what you sell, that you do not stock
    my_items = {p["catalog_item_id"] for p in my_products if p.get("catalog_item_id")}
    gaps: dict[int, dict] = {}
    if my_items:
        for rule in rules:
            if len(rule.antecedents) != 1 or rule.antecedents[0] not in my_items:
                continue
            for c in rule.consequents:
                if c not in my_items and (c not in gaps or gaps[c]["confidence"] < rule.confidence):
                    gaps[c] = {"catalog_item_id": c, "because_of": rule.antecedents[0], "confidence": rule.confidence,
                               "lift": rule.lift}
    top_gaps = sorted(gaps.values(), key=lambda g: -g["confidence"] * g["lift"])[:6]
    names = db.catalog_items.by_ids([g["catalog_item_id"] for g in top_gaps] + [g["because_of"] for g in top_gaps])
    bundle_gaps = [
        {"item": {"id": g["catalog_item_id"], "name": names[g["catalog_item_id"]].name,
                  "icon": names[g["catalog_item_id"]].icon,
                  "typical_price": names[g["catalog_item_id"]].typical_price},
         "because_of": names[g["because_of"]].name, "confidence": g["confidence"], "lift": g["lift"]}
        for g in top_gaps if g["catalog_item_id"] in names and g["because_of"] in names
    ]

    latest = {r.name: r for r in runs}  # sorted oldest first, so the newest run of each model wins
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
            for name, r in latest.items()
        },
    }


# ------------------------------------------------------------------ admin

def admin_overview(db: Database) -> dict:
    since30 = ist_day_start_utc(29)
    since14 = ist_day_start_utc(13)
    owner_reasons = [InventoryReason.RESTOCK.value, InventoryReason.ADJUSTMENT.value, InventoryReason.INITIAL.value]

    def by_day(collection, match: dict) -> dict:
        return {r["_id"]: r["n"] for r in collection.aggregate([
            {"$match": match}, {"$group": {"_id": ist_day("$created_at"), "n": {"$sum": 1}}}])}

    def top_shops() -> list[dict]:
        return db.sales_history.aggregate([
            {"$match": {"sold_at": {"$gte": since30}}},
            {"$group": {"_id": "$shop_id", "rev": REVENUE, "baskets": {"$addToSet": "$basket_id"}}},
            {"$project": {"rev": 1, "baskets": {"$size": "$baskets"}}},
            {"$sort": {"rev": -1}},
            {"$limit": 8},
        ])

    def searches(match: dict, limit: int) -> list[dict]:
        return db.search_history.aggregate([
            {"$match": match},
            {"$group": {"_id": "$normalized_query", "n": {"$sum": 1}, "avg": {"$avg": "$results_count"}}},
            {"$sort": {"n": -1, "_id": 1}},
            {"$limit": limit},
        ])

    def product_totals() -> dict:
        rows = db.products.aggregate([
            {"$match": {"is_active": True}},
            {"$group": {"_id": None, "listings": {"$sum": 1},
                        "in_stock": {"$sum": {"$cond": [{"$gt": ["$quantity", 0]}, 1, 0]}}}},
        ])
        return rows[0] if rows else {}

    def shop_totals() -> dict:
        rows = db.shops.aggregate([{"$group": {
            "_id": None,
            "active": {"$sum": {"$cond": ["$is_active", 1, 0]}},
            "verified": {"$sum": {"$cond": ["$is_verified", 1, 0]}},
        }}])
        return rows[0] if rows else {}

    (res_status, ord_status, cat_sales, cat_searches, top, popular, zero, inv_rows, search_rows, roles, shops_n,
     products_n, revenue_by_demo, searches_30d, open_flags, series) = db.gather(
        lambda: _count_by(db.reservations, "status"),
        lambda: _count_by(db.orders, "status"),
        # Category revenue straight from sales: `category_id` is denormalised onto each sale.
        lambda: db.sales_history.aggregate([
            {"$match": {"sold_at": {"$gte": since30}, "category_id": {"$ne": None}}},
            {"$group": {"_id": "$category_id", "rev": REVENUE}},
            {"$sort": {"rev": -1}},
        ]),
        lambda: _count_by(db.search_history, "category_slug", {"category_slug": {"$ne": None}}),
        top_shops,
        lambda: searches({"created_at": {"$gte": utcnow() - timedelta(days=14)}}, 10),
        lambda: searches({"results_count": 0, "created_at": {"$gte": utcnow() - timedelta(days=30)}}, 8),
        lambda: by_day(db.inventory_events, {"created_at": {"$gte": since14}, "reason": {"$in": owner_reasons}}),
        lambda: by_day(db.search_history, {"created_at": {"$gte": since14}}),
        lambda: _count_by(db.users, "role"),
        shop_totals,
        product_totals,
        lambda: {r["_id"]: r["rev"] for r in db.sales_history.aggregate([
            {"$match": {"sold_at": {"$gte": since30}}}, {"$group": {"_id": "$is_demo", "rev": REVENUE}}])},
        lambda: db.search_history.count({"created_at": {"$gte": since30}}),
        lambda: db.price_anomalies.count({"status": AnomalyStatus.OPEN}),
        lambda: _sales_by_ist_day(db, days=30),
    )
    cats = categories(db)
    top_shop_docs = db.shops.by_ids(s["_id"] for s in top)

    activity = []
    for i in range(13, -1, -1):
        d = (datetime.now(IST) - timedelta(days=i)).date().isoformat()
        activity.append({"date": d, "inventory_updates": inv_rows.get(d, 0), "searches": search_rows.get(d, 0)})

    return {
        "totals": {
            "customers": roles.get(Role.CUSTOMER.value, 0),
            "owners": roles.get(Role.OWNER.value, 0),
            "shops": shops_n.get("active", 0),
            "shops_verified": shops_n.get("verified", 0),
            "listings": products_n.get("listings", 0),
            "in_stock": products_n.get("in_stock", 0),
            "reservations": sum(res_status.values()),
            "orders": sum(ord_status.values()),
            "revenue_30d": round(float(sum(revenue_by_demo.values())), 2),
            "revenue_30d_real": round(float(revenue_by_demo.get(False, 0)), 2),
            "searches_30d": searches_30d,
            "open_price_flags": open_flags,
        },
        "reservations_by_status": res_status,
        "orders_by_status": ord_status,
        "sales_series": series,
        "categories": [{"name": cats[r["_id"]].name, "slug": cats[r["_id"]].slug, "color_hue": cats[r["_id"]].color_hue,
                        "revenue_30d": round(float(r["rev"] or 0), 2),
                        "searches": cat_searches.get(cats[r["_id"]].slug, 0)}
                       for r in cat_sales if r["_id"] in cats],
        "top_shops": [{"id": s["_id"], "name": top_shop_docs[s["_id"]].name, "slug": top_shop_docs[s["_id"]].slug,
                       "locality": top_shop_docs[s["_id"]].locality, "revenue_30d": round(float(s["rev"]), 2),
                       "baskets": s["baskets"], "rating_avg": top_shop_docs[s["_id"]].rating_avg}
                      for s in top if s["_id"] in top_shop_docs],
        "popular_searches": [{"query": r["_id"], "count": r["n"], "avg_results": round(float(r["avg"] or 0), 1)}
                             for r in popular],
        "zero_result_searches": [{"query": r["_id"], "count": r["n"]} for r in zero],
        "activity": activity,
    }
