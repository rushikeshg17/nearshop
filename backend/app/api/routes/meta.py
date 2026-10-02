from fastapi import APIRouter
from sqlalchemy import func, select

from app.core.deps import DB
from app.models import Category, Product, Shop
from app.schemas.serializers import category_out
from app.services.meta import city_config

router = APIRouter(tags=["meta"])


@router.get("/meta")
def meta(db: DB):
    city = city_config()
    counts = dict(
        db.execute(
            select(Category.slug, func.count(Product.id))
            .join(Product, Product.category_id == Category.id)
            .where(Product.is_active.is_(True), Product.quantity > 0)
            .group_by(Category.slug)
        ).all()
    )
    categories = [
        {**category_out(c), "in_stock_listings": counts.get(c.slug, 0)}
        for c in db.scalars(select(Category).order_by(Category.sort_order, Category.name))
    ]
    return {
        "city": city,
        "categories": categories,
        "stats": {
            "shops": db.scalar(select(func.count()).select_from(Shop).where(Shop.is_active.is_(True))) or 0,
            "listings": db.scalar(select(func.count()).select_from(Product).where(Product.is_active.is_(True))) or 0,
            "in_stock": db.scalar(
                select(func.count()).select_from(Product).where(Product.is_active.is_(True), Product.quantity > 0)
            ) or 0,
        },
    }
