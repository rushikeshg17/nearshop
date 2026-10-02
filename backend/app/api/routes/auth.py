from fastapi import APIRouter, Response
from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.core.database import Database, utcnow
from app.core.deps import DB, CurrentUser, OptionalUser
from app.core.errors import AppError, Conflict
from app.core.security import create_access_token, hash_password, verify_password
from app.models import Role, Shop, User
from app.schemas.requests import LoginIn, ProfileUpdateIn, RegisterIn, RegisterShopIn
from app.services.loaders import categories
from app.services.meta import city_config
from app.utils.text import slugify

router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_TAKEN = Conflict("An account with this email already exists", code="email_taken")


def user_out(user: User, db: Database) -> dict:
    shop = None
    if user.role == Role.OWNER:
        s = db.shops.find_one({"owner_id": user.id}, sort=[("_id", 1)])
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


def _ensure_email_free(db: Database, email: str) -> None:
    if db.users.exists({"email": email.lower()}):
        raise EMAIL_TAKEN


@router.post("/register")
def register(body: RegisterIn, response: Response, db: DB):
    _ensure_email_free(db, body.email)
    try:
        user = db.users.insert(User(name=body.name, email=body.email.lower(), phone=body.phone,
                                    password_hash=hash_password(body.password), role=Role.CUSTOMER))
    except DuplicateKeyError:  # two sign-ups raced: the unique index on email decides
        raise EMAIL_TAKEN from None
    _start_session(response, user)
    return user_out(user, db)


@router.post("/register-shop")
def register_shop(body: RegisterShopIn, response: Response, db: DB):
    _ensure_email_free(db, body.owner.email)
    cats = [c for c in categories(db).values() if c.slug in set(body.shop.category_slugs)]
    if len(cats) != len(set(body.shop.category_slugs)):
        raise AppError("Choose categories from the list")
    password_hash = hash_password(body.owner.password)
    data = body.shop.model_dump(exclude={"category_slugs"})
    base = slugify(f"{body.shop.name} {body.shop.locality or ''}")
    taken = {d["slug"] for d in db.shops.find_raw({"slug": {"$regex": f"^{base}(-\\d+)?$"}}, {"slug": 1})}
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1

    def create() -> User:
        # The owner account and the shop are created together or not at all.
        user = db.users.insert(User(name=body.owner.name, email=body.owner.email.lower(),
                                    phone=body.owner.phone or body.shop.phone, password_hash=password_hash,
                                    role=Role.OWNER))
        db.shops.insert(Shop(**data, owner_id=user.id, slug=slug, city=city_config()["name"],
                             category_ids=[c.id for c in cats], inventory_updated_at=utcnow()))
        return user

    try:
        user = db.transaction(create)
    except DuplicateKeyError:
        raise EMAIL_TAKEN from None
    _start_session(response, user)
    return user_out(user, db)


@router.post("/login")
def login(body: LoginIn, response: Response, db: DB):
    user = db.users.find_one({"email": body.email.lower()})
    # Same message for unknown email and wrong password, so accounts cannot be enumerated.
    if not user or not verify_password(body.password, user.password_hash) or not user.is_active:
        raise AppError("Email or password is incorrect", code="invalid_credentials", status_code=401)
    db.users.set(user, last_login_at=utcnow())
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
    changes = body.model_dump(exclude_unset=True)
    if changes:
        db.users.set(user, **changes)
    return user_out(user, db)
