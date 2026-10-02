from fastapi import APIRouter, Response
from sqlalchemy import select

from app.core.config import settings
from app.core.database import utcnow
from app.core.deps import DB, CurrentUser, OptionalUser
from app.core.errors import AppError, Conflict
from app.core.security import create_access_token, hash_password, verify_password
from app.models import Category, Role, Shop, User
from app.schemas.requests import LoginIn, ProfileUpdateIn, RegisterIn, RegisterShopIn
from app.services.meta import city_config
from app.utils.text import slugify

router = APIRouter(prefix="/auth", tags=["auth"])


def user_out(user: User, db) -> dict:
    shop = None
    if user.role == Role.OWNER:
        s = db.scalars(select(Shop).where(Shop.owner_id == user.id).order_by(Shop.id)).first()
        if s:
            shop = {"id": s.id, "slug": s.slug, "name": s.name}
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "phone": user.phone,
        "role": user.role.value,
        "home_lat": user.home_lat,
        "home_lng": user.home_lng,
        "home_label": user.home_label,
        "shop": shop,
    }


def _start_session(response: Response, user: User) -> None:
    response.set_cookie(
        settings.cookie_name,
        create_access_token(user.id, user.role.value),
        max_age=settings.access_token_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def _ensure_email_free(db, email: str) -> None:
    if db.scalar(select(User.id).where(User.email == email.lower())):
        raise Conflict("An account with this email already exists", code="email_taken")


@router.post("/register")
def register(body: RegisterIn, response: Response, db: DB):
    _ensure_email_free(db, body.email)
    user = User(name=body.name, email=body.email.lower(), phone=body.phone,
                password_hash=hash_password(body.password), role=Role.CUSTOMER)
    db.add(user)
    db.commit()
    _start_session(response, user)
    return user_out(user, db)


@router.post("/register-shop")
def register_shop(body: RegisterShopIn, response: Response, db: DB):
    _ensure_email_free(db, body.owner.email)
    cats = db.scalars(select(Category).where(Category.slug.in_(body.shop.category_slugs))).all()
    if len(cats) != len(set(body.shop.category_slugs)):
        raise AppError("Choose categories from the list")
    user = User(name=body.owner.name, email=body.owner.email.lower(), phone=body.owner.phone or body.shop.phone,
                password_hash=hash_password(body.owner.password), role=Role.OWNER)
    db.add(user)
    db.flush()
    data = body.shop.model_dump(exclude={"category_slugs"})
    base = slugify(f"{body.shop.name} {body.shop.locality or ''}")
    slug, n = base, 2
    while db.scalar(select(Shop.id).where(Shop.slug == slug)):
        slug, n = f"{base}-{n}", n + 1
    shop = Shop(**data, owner_id=user.id, slug=slug, city=city_config()["name"], categories=cats,
                inventory_updated_at=utcnow())
    db.add(shop)
    db.commit()
    _start_session(response, user)
    return user_out(user, db)


@router.post("/login")
def login(body: LoginIn, response: Response, db: DB):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    # Same message for unknown email and wrong password, so accounts cannot be enumerated.
    if not user or not verify_password(body.password, user.password_hash) or not user.is_active:
        raise AppError("Email or password is incorrect", code="invalid_credentials", status_code=401)
    user.last_login_at = utcnow()
    db.commit()
    _start_session(response, user)
    return user_out(user, db)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(settings.cookie_name, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: OptionalUser, db: DB):
    """The signed-in user, or null (200) when signed out so browsers don't log errors."""
    return user_out(user, db) if user else None


@router.patch("/me")
def update_me(body: ProfileUpdateIn, user: CurrentUser, db: DB):
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    return user_out(user, db)
