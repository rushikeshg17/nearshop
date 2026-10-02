from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.database import utcnow
from app.core.deps import DB, AdminUser
from app.core.errors import NotFound
from app.models import AnomalyStatus, PriceAnomaly, Product, Role, Shop, User
from app.schemas.requests import AdminShopUpdateIn, AnomalyReviewIn
from app.schemas.serializers import iso, listing, shop_brief
from app.services import analytics
from app.services.reliability import ratings_for

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview")
def overview(_: AdminUser, db: DB):
    return analytics.admin_overview(db)


@router.get("/anomalies")
def anomalies(_: AdminUser, db: DB, status: Literal["open", "reviewed", "dismissed"] = "open"):
    rows = db.execute(
        select(PriceAnomaly, Product, Shop)
        .join(Product, Product.id == PriceAnomaly.product_id).join(Shop, Shop.id == PriceAnomaly.shop_id)
        .options(selectinload(Product.category))
        .where(PriceAnomaly.status == AnomalyStatus(status))
        .order_by(PriceAnomaly.score.desc())
    ).all()
    return [
        {"id": a.id, "price": a.price, "reference_price": a.reference_price, "deviation_pct": a.deviation_pct,
         "score": a.score, "direction": a.direction, "peer_count": a.peer_count, "status": a.status.value,
         "review_note": a.review_note, "created_at": iso(a.created_at), "reviewed_at": iso(a.reviewed_at),
         "product": listing(p), "shop": {"id": s.id, "name": s.name, "slug": s.slug, "locality": s.locality}}
        for a, p, s in rows
    ]


@router.post("/anomalies/{anomaly_id}")
def review_anomaly(anomaly_id: int, body: AnomalyReviewIn, admin: AdminUser, db: DB):
    a = db.get(PriceAnomaly, anomaly_id)
    if a is None:
        raise NotFound("Flag not found")
    a.status = AnomalyStatus(body.status)
    a.review_note = body.note
    a.reviewed_by = admin.id
    a.reviewed_at = utcnow()
    db.commit()
    return {"ok": True}


@router.get("/shops")
def shops(_: AdminUser, db: DB, q: str | None = Query(None, max_length=80)):
    stmt = select(Shop).options(selectinload(Shop.categories), selectinload(Shop.owner)).order_by(Shop.name)
    if q:
        stmt = stmt.where(Shop.name.ilike(f"%{q}%") | Shop.locality.ilike(f"%{q}%"))
    rows = db.scalars(stmt).all()
    ratings = ratings_for(db, [s.id for s in rows])
    counts = dict(db.execute(select(Product.shop_id, func.count()).where(Product.is_active.is_(True))
                             .group_by(Product.shop_id)).all())
    return [{**shop_brief(s, None, ratings.get(s.id)), "is_active": s.is_active, "owner": s.owner.name,
             "owner_email": s.owner.email, "listings": counts.get(s.id, 0), "created_at": iso(s.created_at)}
            for s in rows]


@router.patch("/shops/{shop_id}")
def update_shop(shop_id: int, body: AdminShopUpdateIn, _: AdminUser, db: DB):
    s = db.get(Shop, shop_id)
    if s is None:
        raise NotFound("Shop not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    db.commit()
    return {"ok": True}


@router.get("/users")
def users(_: AdminUser, db: DB, role: Literal["customer", "owner", "admin"] | None = None,
          q: str | None = Query(None, max_length=80), limit: int = Query(100, ge=1, le=500)):
    stmt = select(User).order_by(User.created_at.desc())
    if role:
        stmt = stmt.where(User.role == Role(role))
    if q:
        stmt = stmt.where(User.name.ilike(f"%{q}%") | User.email.ilike(f"%{q}%"))
    return [{"id": u.id, "name": u.name, "email": u.email, "role": u.role.value, "is_active": u.is_active,
             "created_at": iso(u.created_at), "last_login_at": iso(u.last_login_at)}
            for u in db.scalars(stmt.limit(limit))]
