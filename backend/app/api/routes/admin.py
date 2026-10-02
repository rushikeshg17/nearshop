import re
from typing import Literal

from fastapi import APIRouter, Query

from app.core.database import utcnow
from app.core.deps import DB, AdminUser
from app.core.errors import NotFound
from app.models import AnomalyStatus, Role
from app.schemas.requests import AdminShopUpdateIn, AnomalyReviewIn
from app.schemas.serializers import iso, listing, shop_brief
from app.services import analytics
from app.services.loaders import with_categories, with_category

router = APIRouter(prefix="/admin", tags=["admin"])


def _contains(q: str) -> dict:
    return {"$regex": re.escape(q.strip()), "$options": "i"}


@router.get("/overview")
def overview(_: AdminUser, db: DB):
    return analytics.admin_overview(db)


@router.get("/anomalies")
def anomalies(_: AdminUser, db: DB, status: Literal["open", "reviewed", "dismissed"] = "open"):
    rows = db.price_anomalies.find({"status": AnomalyStatus(status)}, sort=[("score", -1)])
    products, shops = db.gather(
        lambda: {p.id: p for p in with_category(db, db.products.by_ids(a.product_id for a in rows).values())},
        lambda: db.shops.by_ids(a.shop_id for a in rows),
    )
    return [
        {"id": a.id, "price": a.price, "reference_price": a.reference_price, "deviation_pct": a.deviation_pct,
         "score": a.score, "direction": a.direction, "peer_count": a.peer_count, "status": a.status.value,
         "review_note": a.review_note, "created_at": iso(a.created_at), "reviewed_at": iso(a.reviewed_at),
         "product": listing(products[a.product_id]),
         "shop": {"id": s.id, "name": s.name, "slug": s.slug, "locality": s.locality}}
        for a in rows
        if a.product_id in products and (s := shops.get(a.shop_id))
    ]


@router.post("/anomalies/{anomaly_id}")
def review_anomaly(anomaly_id: int, body: AnomalyReviewIn, admin: AdminUser, db: DB):
    a = db.price_anomalies.get(anomaly_id)
    if a is None:
        raise NotFound("Flag not found")
    db.price_anomalies.set(a, status=AnomalyStatus(body.status), review_note=body.note, reviewed_by=admin.id,
                           reviewed_at=utcnow())
    return {"ok": True}


@router.get("/shops")
def shops(_: AdminUser, db: DB, q: str | None = Query(None, max_length=80)):
    query = {"$or": [{"name": _contains(q)}, {"locality": _contains(q)}]} if q else {}
    rows, counts = db.gather(
        lambda: with_categories(db, db.shops.find(query, sort=[("name", 1)])),
        lambda: {r["_id"]: r["n"] for r in db.products.aggregate([
            {"$match": {"is_active": True}}, {"$group": {"_id": "$shop_id", "n": {"$sum": 1}}}])},
    )
    owners = db.users.by_ids(s.owner_id for s in rows)
    return [{**shop_brief(s), "is_active": s.is_active, "owner": owners[s.owner_id].name,
             "owner_email": owners[s.owner_id].email, "listings": counts.get(s.id, 0), "created_at": iso(s.created_at)}
            for s in rows if s.owner_id in owners]


@router.patch("/shops/{shop_id}")
def update_shop(shop_id: int, body: AdminShopUpdateIn, _: AdminUser, db: DB):
    s = db.shops.get(shop_id)
    if s is None:
        raise NotFound("Shop not found")
    changes = body.model_dump(exclude_unset=True)
    if changes:
        db.shops.set(s, **changes)
    return {"ok": True}


@router.get("/users")
def users(_: AdminUser, db: DB, role: Literal["customer", "owner", "admin"] | None = None,
          q: str | None = Query(None, max_length=80), limit: int = Query(100, ge=1, le=500)):
    query: dict = {}
    if role:
        query["role"] = Role(role)
    if q:
        query["$or"] = [{"name": _contains(q)}, {"email": _contains(q)}]
    return [{"id": u.id, "name": u.name, "email": u.email, "role": u.role.value, "is_active": u.is_active,
             "created_at": iso(u.created_at), "last_login_at": iso(u.last_login_at)}
            for u in db.users.find(query, sort=[("created_at", -1)], limit=limit)]
