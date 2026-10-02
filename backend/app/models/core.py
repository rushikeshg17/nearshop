"""Users, categories, catalog, shops and products."""
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, utcnow
from app.models.enums import InventoryReason, Role


def str_enum(enum_cls, length: int = 24) -> Enum:
    """Store a StrEnum as a VARCHAR with a CHECK constraint (portable across SQLite/Postgres)."""
    return Enum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        length=length,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(str_enum(Role, 16), default=Role.CUSTOMER, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Saved default location for "near me"
    home_lat: Mapped[float | None] = mapped_column(Float)
    home_lng: Mapped[float | None] = mapped_column(Float)
    home_label: Mapped[str | None] = mapped_column(String(160))

    shops: Mapped[list["Shop"]] = relationship(back_populates="owner")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    icon: Mapped[str] = mapped_column(String(60), default="Package")
    description: Mapped[str | None] = mapped_column(String(255))
    color_hue: Mapped[int] = mapped_column(Integer, default=250)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class CatalogItem(Base):
    """Master product definition. Shop listings (Product) may link to one so prices can be compared."""

    __tablename__ = "catalog_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    brand: Mapped[str | None] = mapped_column(String(80))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    subcategory: Mapped[str | None] = mapped_column(String(60), index=True)
    unit: Mapped[str | None] = mapped_column(String(40))
    mrp: Mapped[float | None] = mapped_column(Float)
    typical_price: Mapped[float | None] = mapped_column(Float)
    description: Mapped[str | None] = mapped_column(Text)
    specs: Mapped[dict] = mapped_column(JSON, default=dict)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    icon: Mapped[str] = mapped_column(String(60), default="Package")

    category: Mapped[Category] = relationship()


shop_categories = Table(
    "shop_categories",
    Base.metadata,
    Column("shop_id", ForeignKey("shops.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True),
)


class Shop(TimestampMixin, Base):
    __tablename__ = "shops"
    __table_args__ = (
        CheckConstraint("lat BETWEEN -90 AND 90", name="ck_shop_lat"),
        CheckConstraint("lng BETWEEN -180 AND 180", name="ck_shop_lng"),
        CheckConstraint("delivery_radius_km >= 0", name="ck_shop_radius"),
        Index("ix_shops_lat_lng", "lat", "lng"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(180), unique=True)
    tagline: Mapped[str | None] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(20))
    address_line: Mapped[str] = mapped_column(String(255))
    locality: Mapped[str | None] = mapped_column(String(120), index=True)
    city: Mapped[str] = mapped_column(String(80))
    pincode: Mapped[str | None] = mapped_column(String(10))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    opening_hours: Mapped[str | None] = mapped_column(String(80))
    closed_on: Mapped[str | None] = mapped_column(String(40))
    established_year: Mapped[int | None] = mapped_column(Integer)

    offers_pickup: Mapped[bool] = mapped_column(Boolean, default=True)
    offers_delivery: Mapped[bool] = mapped_column(Boolean, default=False)
    delivery_radius_km: Mapped[float] = mapped_column(Float, default=0)
    delivery_fee: Mapped[float] = mapped_column(Float, default=0)
    free_delivery_above: Mapped[float | None] = mapped_column(Float)
    hold_minutes: Mapped[int] = mapped_column(Integer, default=30)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    image_path: Mapped[str | None] = mapped_column(String(255))
    inventory_updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    owner: Mapped[User] = relationship(back_populates="shops")
    categories: Mapped[list[Category]] = relationship(secondary=shop_categories)
    products: Mapped[list["Product"]] = relationship(back_populates="shop")


class Product(TimestampMixin, Base):
    """A shop's listing: its own price and stock for an item."""

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_product_price"),
        CheckConstraint("quantity >= 0", name="ck_product_qty"),
        UniqueConstraint("shop_id", "catalog_item_id", name="uq_product_shop_catalog"),
        Index("ix_products_shop_active", "shop_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    catalog_item_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_items.id"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    brand: Mapped[str | None] = mapped_column(String(80))
    sku: Mapped[str | None] = mapped_column(String(60))
    unit: Mapped[str | None] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(Text)
    specs: Mapped[dict] = mapped_column(JSON, default=dict)
    keywords: Mapped[str] = mapped_column(Text, default="")  # tags + category words, indexed by FTS5
    icon: Mapped[str] = mapped_column(String(60), default="Package")
    image_path: Mapped[str | None] = mapped_column(String(255))
    price: Mapped[float] = mapped_column(Float, index=True)
    mrp: Mapped[float | None] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=5)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    stock_updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    shop: Mapped[Shop] = relationship(back_populates="products")
    category: Mapped[Category] = relationship()
    catalog_item: Mapped[CatalogItem | None] = relationship()

    @property
    def stock_status(self) -> str:
        if self.quantity <= 0:
            return "out_of_stock"
        if self.quantity <= self.low_stock_threshold:
            return "low_stock"
        return "in_stock"


class InventoryEvent(Base):
    """Audit log of every stock change. Powers 'inventory freshness' trust signals."""

    __tablename__ = "inventory_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    quantity_after: Mapped[int] = mapped_column(Integer)
    reason: Mapped[InventoryReason] = mapped_column(str_enum(InventoryReason))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class TextEmbedding(Base):
    """Cached sentence embeddings keyed by a hash of the embedded text (shared across identical listings)."""

    __tablename__ = "text_embeddings"

    text_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    model: Mapped[str] = mapped_column(String(120), primary_key=True)
    dim: Mapped[int] = mapped_column(Integer)
    vector: Mapped[bytes] = mapped_column(LargeBinary)
