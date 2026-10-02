from fastapi import APIRouter

from app.core.deps import DB
from app.schemas.serializers import category_out
from app.services.loaders import categories
from app.services.meta import city_config

router = APIRouter(tags=["meta"])


@router.get("/meta")
def meta(db: DB):
    city = city_config()
    # One pass over active listings gives the totals and the per-category in-stock counts.
    by_category, shops = db.gather(
        lambda: db.products.aggregate([
            {"$match": {"is_active": True}},
            {"$group": {"_id": "$category_id", "listings": {"$sum": 1},
                        "in_stock": {"$sum": {"$cond": [{"$gt": ["$quantity", 0]}, 1, 0]}}}},
        ]),
        lambda: db.shops.count({"is_active": True}),
    )
    counts = {r["_id"]: r for r in by_category}
    return {
        "city": city,
        "categories": [
            {**category_out(c), "in_stock_listings": counts.get(c.id, {}).get("in_stock", 0)}
            for c in categories(db).values()
        ],
        "stats": {
            "shops": shops,
            "listings": sum(r["listings"] for r in by_category),
            "in_stock": sum(r["in_stock"] for r in by_category),
        },
    }
