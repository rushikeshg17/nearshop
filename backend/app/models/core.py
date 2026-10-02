"""Users, categories, catalog, shops and products."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from app.core.database import utcnow
from app.models.base import Document, GeoPoint, Timestamps
from app.models.enums import InventoryReason, Role


class User(Document, Timestamps):
    """Collection `users`. Unique on email."""

    name: str
    email: str
    phone: str | None = None
    password_hash: str
    role: Role = Role.CUSTOMER
    is_active: bool = True
    last_login_at: datetime | None = None
    # Saved default location for "near me"
    home_lat: float | None = None
    home_lng: float | None = None
    home_label: str | None = None


class Category(Document):
    """Collection `categories`. Small reference data, unique on slug."""

    slug: str
    name: str
    icon: str = "Package"
    description: str | None = None
    color_hue: int = 250
    sort_order: int = 0


class CatalogItem(Document):
    """Collection `catalog_items`. Master product definition; shop listings (Product) may link to
    one so the same item can be compared across shops."""

    slug: str
    name: str
    brand: str | None = None
    category_id: int
    subcategory: str | None = None
    unit: str | None = None
    mrp: float | None = None
    typical_price: float | None = None
    description: str | None = None
    specs: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    icon: str = "Package"

    category: Category | None = Field(default=None, exclude=True)


class Shop(Document, Timestamps):
    """Collection `shops`. `location` is GeoJSON (2dsphere index) and `category_ids` embeds the
    shop-to-category relation, so "shops near me selling X" is a single indexed query."""

    owner_id: int
    name: str
    slug: str
    tagline: str | None = None
    description: str | None = None
    phone: str | None = None
    address_line: str
    locality: str | None = None
    city: str
    pincode: str | None = None
    location: GeoPoint
    opening_hours: str | None = None
    closed_on: str | None = None
    established_year: int | None = None

    offers_pickup: bool = True
    offers_delivery: bool = False
    delivery_radius_km: float = 0
    delivery_fee: float = 0
    free_delivery_above: float | None = None
    hold_minutes: int = 30

    is_active: bool = True
    is_verified: bool = False
    image_path: str | None = None
    inventory_updated_at: datetime | None = None
    category_ids: list[int] = Field(default_factory=list)
    # Computed on write: kept in step with `reviews` in the same transaction, so listing shops
    # never needs to aggregate reviews.
    rating_sum: int = 0
    rating_count: int = 0

    categories: list[Category] = Field(default_factory=list, exclude=True)
    owner: User | None = Field(default=None, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _lat_lng_to_location(cls, data: Any) -> Any:
        # Convenience for code that thinks in lat/lng: Shop(lat=.., lng=..).
        if isinstance(data, dict) and "location" not in data and "lat" in data and "lng" in data:
            data = dict(data)
            data["location"] = GeoPoint.of(data.pop("lat"), data.pop("lng"))
        return data

    @property
    def lat(self) -> float:
        return self.location.lat

    @property
    def lng(self) -> float:
        return self.location.lng

    @property
    def rating_avg(self) -> float | None:
        return round(self.rating_sum / self.rating_count, 1) if self.rating_count else None


class Product(Document, Timestamps):
    """Collection `products`. A shop's listing: its own price and stock for an item.
    Unique on (shop_id, catalog_item_id) when linked to the catalog. Text-indexed for keyword search."""

    shop_id: int
    catalog_item_id: int | None = None
    category_id: int
    name: str
    brand: str | None = None
    sku: str | None = None
    unit: str | None = None
    description: str | None = None
    specs: dict[str, Any] = Field(default_factory=dict)
    keywords: str = ""  # tags + category words, part of the text index
    icon: str = "Package"
    image_path: str | None = None
    price: float
    mrp: float | None = None
    quantity: int = 0
    low_stock_threshold: int = 5
    is_active: bool = True
    stock_updated_at: datetime = Field(default_factory=utcnow)

    shop: Shop | None = Field(default=None, exclude=True)
    category: Category | None = Field(default=None, exclude=True)
    catalog_item: CatalogItem | None = Field(default=None, exclude=True)

    @property
    def stock_status(self) -> str:
        if self.quantity <= 0:
            return "out_of_stock"
        if self.quantity <= self.low_stock_threshold:
            return "low_stock"
        return "in_stock"


class InventoryEvent(Document):
    """Collection `inventory_events`. Append-only audit log of every stock change; powers the
    'inventory freshness' trust signals."""

    product_id: int
    shop_id: int
    delta: int
    quantity_after: int
    reason: InventoryReason
    actor_id: int | None = None
    created_at: datetime = Field(default_factory=utcnow)
