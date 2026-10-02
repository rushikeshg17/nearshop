from typing import Literal

from fastapi import APIRouter, Query

from app.core.deps import DB, OptionalUser
from app.services import search as search_service
from app.services.meta import city_config

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def search(
    db: DB,
    user: OptionalUser,
    q: str = Query("", max_length=120),
    lat: float | None = Query(None, ge=-90, le=90),
    lng: float | None = Query(None, ge=-180, le=180),
    radius_km: float = Query(5, gt=0, le=50),
    category: str | None = None,
    min_price: float | None = Query(None, ge=0),
    max_price: float | None = Query(None, ge=0),
    in_stock_only: bool = False,
    fulfillment: Literal["pickup", "delivery"] | None = None,
    sort: Literal["relevance", "distance", "price_asc", "price_desc"] = "relevance",
    page: int = Query(1, ge=1, le=50),
    page_size: int = Query(20, ge=1, le=50),
):
    if lat is None or lng is None:
        center = city_config()["center"]
        lat, lng = center["lat"], center["lng"]
    params = search_service.SearchParams(
        q=q, lat=lat, lng=lng, radius_km=radius_km, category=category, min_price=min_price, max_price=max_price,
        in_stock_only=in_stock_only, fulfillment=fulfillment, sort=sort, page=page, page_size=page_size,
    )
    return search_service.run_search(db, params, user_id=user.id if user else None)


@router.get("/suggest")
def suggest(db: DB, q: str = Query("", max_length=80)):
    return search_service.suggestions(db, q)


@router.get("/discover")
def discover(db: DB, user: OptionalUser):
    return {
        "popular": search_service.popular_searches(db),
        "recent": search_service.recent_searches(db, user.id) if user else [],
    }
