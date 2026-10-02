"""Validated request bodies (Pydantic). Anything a client sends is checked here first."""
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

PHONE_PATTERN = r"^[6-9]\d{9}$"  # Indian mobile numbers


class _Strict(BaseModel):
    model_config = {"extra": "forbid", "str_strip_whitespace": True}


class RegisterIn(_Strict):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = Field(default=None, pattern=PHONE_PATTERN)


class ShopSetupIn(_Strict):
    name: str = Field(min_length=3, max_length=160)
    tagline: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    category_slugs: list[str] = Field(min_length=1, max_length=3)
    phone: str = Field(pattern=PHONE_PATTERN)
    address_line: str = Field(min_length=5, max_length=255)
    locality: str | None = Field(default=None, max_length=120)
    pincode: str | None = Field(default=None, pattern=r"^\d{6}$")
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    opening_hours: str | None = Field(default="9:30 AM - 9:00 PM", max_length=80)
    closed_on: str | None = Field(default=None, max_length=40)
    offers_delivery: bool = False
    delivery_radius_km: float = Field(default=0, ge=0, le=25)
    delivery_fee: float = Field(default=0, ge=0, le=500)
    free_delivery_above: float | None = Field(default=None, ge=0)
    hold_minutes: int = Field(default=30, ge=10, le=240)


class RegisterShopIn(_Strict):
    owner: RegisterIn
    shop: ShopSetupIn


class LoginIn(_Strict):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ProfileUpdateIn(_Strict):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    home_lat: float | None = Field(default=None, ge=-90, le=90)
    home_lng: float | None = Field(default=None, ge=-180, le=180)
    home_label: str | None = Field(default=None, max_length=160)


class ShopUpdateIn(_Strict):
    name: str | None = Field(default=None, min_length=3, max_length=160)
    tagline: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    category_slugs: list[str] | None = Field(default=None, min_length=1, max_length=3)
    phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    address_line: str | None = Field(default=None, min_length=5, max_length=255)
    locality: str | None = Field(default=None, max_length=120)
    pincode: str | None = Field(default=None, pattern=r"^\d{6}$")
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    opening_hours: str | None = Field(default=None, max_length=80)
    closed_on: str | None = Field(default=None, max_length=40)
    offers_pickup: bool | None = None
    offers_delivery: bool | None = None
    delivery_radius_km: float | None = Field(default=None, ge=0, le=25)
    delivery_fee: float | None = Field(default=None, ge=0, le=500)
    free_delivery_above: float | None = Field(default=None, ge=0)
    hold_minutes: int | None = Field(default=None, ge=10, le=240)
    is_active: bool | None = None


class ProductIn(_Strict):
    name: str = Field(min_length=2, max_length=200)
    category_slug: str
    brand: str | None = Field(default=None, max_length=80)
    sku: str | None = Field(default=None, max_length=60)
    unit: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=2000)
    specs: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list, max_length=20)
    price: float = Field(gt=0, le=10_000_000)
    mrp: float | None = Field(default=None, gt=0)
    quantity: int = Field(ge=0, le=100_000)
    low_stock_threshold: int = Field(default=5, ge=0, le=10_000)


class ProductUpdateIn(_Strict):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    category_slug: str | None = None
    brand: str | None = Field(default=None, max_length=80)
    sku: str | None = Field(default=None, max_length=60)
    unit: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=2000)
    specs: dict[str, str] | None = None
    tags: list[str] | None = Field(default=None, max_length=20)
    price: float | None = Field(default=None, gt=0, le=10_000_000)
    mrp: float | None = Field(default=None, gt=0)
    low_stock_threshold: int | None = Field(default=None, ge=0, le=10_000)
    is_active: bool | None = None


class StockIn(_Strict):
    quantity: int = Field(ge=0, le=100_000)


class CatalogAddItem(_Strict):
    catalog_item_id: int
    price: float = Field(gt=0, le=10_000_000)
    quantity: int = Field(ge=0, le=100_000)


class CatalogAddIn(_Strict):
    items: list[CatalogAddItem] = Field(min_length=1, max_length=100)


class ReservationIn(_Strict):
    product_id: int
    quantity: int = Field(ge=1, le=20)
    note: str | None = Field(default=None, max_length=300)


class TransitionIn(_Strict):
    reason: str | None = Field(default=None, max_length=300)


class OrderItemIn(_Strict):
    product_id: int
    quantity: int = Field(ge=1, le=50)


class DeliveryLocation(_Strict):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class OrderQuoteIn(DeliveryLocation):
    items: list[OrderItemIn] = Field(min_length=1, max_length=20)


class OrderIn(DeliveryLocation):
    items: list[OrderItemIn] = Field(min_length=1, max_length=20)
    address: str = Field(min_length=8, max_length=300)
    phone: str = Field(pattern=PHONE_PATTERN)
    note: str | None = Field(default=None, max_length=300)


class ReviewIn(_Strict):
    reservation_id: int | None = None
    order_id: int | None = None
    rating: int = Field(ge=1, le=5)
    accuracy_rating: int | None = Field(default=None, ge=1, le=5)
    delivery_rating: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def one_source(self):
        if (self.order_id is None) == (self.reservation_id is None):
            raise ValueError("Review exactly one completed reservation or delivered order")
        return self


class NotificationsReadIn(_Strict):
    ids: list[int] | None = None  # None = mark all read


class AnomalyReviewIn(_Strict):
    status: Literal["reviewed", "dismissed"]
    note: str | None = Field(default=None, max_length=300)


class AdminShopUpdateIn(_Strict):
    is_verified: bool | None = None
    is_active: bool | None = None
