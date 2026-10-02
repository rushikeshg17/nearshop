"""Reservations, delivery orders, reviews, notifications, search history and AI outputs."""
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, utcnow
from app.models.core import Product, Shop, TimestampMixin, User, str_enum
from app.models.enums import AnomalyStatus, OrderStatus, ReservationStatus, SaleSource


class Reservation(TimestampMixin, Base):
    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_reservation_qty"),
        Index("ix_reservations_shop_status", "shop_id", "status"),
        Index("ix_reservations_customer_status", "customer_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(12), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[float] = mapped_column(Float)
    status: Mapped[ReservationStatus] = mapped_column(str_enum(ReservationStatus), default=ReservationStatus.REQUESTED)
    note: Mapped[str | None] = mapped_column(String(300))
    hold_minutes: Mapped[int] = mapped_column(Integer, default=30)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    stock_held: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    close_reason: Mapped[str | None] = mapped_column(String(300))

    customer: Mapped[User] = relationship()
    shop: Mapped[Shop] = relationship()
    product: Mapped[Product] = relationship()

    @property
    def total(self) -> float:
        return round(self.unit_price * self.quantity, 2)


class Order(TimestampMixin, Base):
    """Shop-managed delivery order (cash on delivery in V1; payment_method keeps it modular)."""

    __tablename__ = "orders"
    __table_args__ = (Index("ix_orders_shop_status", "shop_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(12), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True)
    status: Mapped[OrderStatus] = mapped_column(str_enum(OrderStatus), default=OrderStatus.PENDING)
    payment_method: Mapped[str] = mapped_column(String(20), default="cod")
    payment_status: Mapped[str] = mapped_column(String(20), default="unpaid")
    delivery_address: Mapped[str] = mapped_column(String(300))
    delivery_lat: Mapped[float] = mapped_column(Float)
    delivery_lng: Mapped[float] = mapped_column(Float)
    contact_phone: Mapped[str] = mapped_column(String(20))
    distance_km: Mapped[float] = mapped_column(Float)
    subtotal: Mapped[float] = mapped_column(Float)
    delivery_fee: Mapped[float] = mapped_column(Float)
    total: Mapped[float] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(String(300))
    stock_held: Mapped[bool] = mapped_column(Boolean, default=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    close_reason: Mapped[str | None] = mapped_column(String(300))

    customer: Mapped[User] = relationship()
    shop: Mapped[Shop] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_order_item_qty"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))  # snapshot at order time
    unit_price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer)

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class StatusEvent(Base):
    """Every state-machine transition, used for timelines and reliability stats."""

    __tablename__ = "status_events"
    __table_args__ = (Index("ix_status_events_entity", "entity", "entity_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entity: Mapped[str] = mapped_column(String(20))  # reservation | order
    entity_id: Mapped[int] = mapped_column(Integer)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(24))
    to_status: Mapped[str] = mapped_column(String(24))
    actor_role: Mapped[str] = mapped_column(String(16))  # customer | owner | admin | system
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_review_rating"),
        CheckConstraint("accuracy_rating IS NULL OR accuracy_rating BETWEEN 1 AND 5", name="ck_review_accuracy"),
        CheckConstraint("delivery_rating IS NULL OR delivery_rating BETWEEN 1 AND 5", name="ck_review_delivery"),
        CheckConstraint("(reservation_id IS NOT NULL) <> (order_id IS NOT NULL)", name="ck_review_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), index=True)
    # Unique: one review per completed reservation / delivered order.
    reservation_id: Mapped[int | None] = mapped_column(ForeignKey("reservations.id"), unique=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), unique=True)
    rating: Mapped[int] = mapped_column(Integer)
    accuracy_rating: Mapped[int | None] = mapped_column(Integer)
    delivery_rating: Mapped[int | None] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    customer: Mapped[User] = relationship()


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_read", "user_id", "read_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str | None] = mapped_column(String(400))
    link: Mapped[str | None] = mapped_column(String(255))
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class SearchEvent(Base):
    __tablename__ = "search_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    query: Mapped[str] = mapped_column(String(200))
    normalized_query: Mapped[str] = mapped_column(String(200), index=True)
    category_slug: Mapped[str | None] = mapped_column(String(60))
    results_count: Mapped[int] = mapped_column(Integer, default=0)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class SalesRecord(Base):
    """Completed sales. Real ones come from reservations/orders; demo rows are clearly flagged."""

    __tablename__ = "sales_history"
    __table_args__ = (Index("ix_sales_product_date", "product_id", "sold_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    catalog_item_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_items.id"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    basket_id: Mapped[str] = mapped_column(String(40), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[float] = mapped_column(Float)
    source: Mapped[SaleSource] = mapped_column(str_enum(SaleSource, 16))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    sold_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), index=True)  # demand | recommendations | anomalies | embeddings
    algorithm: Mapped[str] = mapped_column(String(80))
    n_samples: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    data_note: Mapped[str | None] = mapped_column(String(300))
    uses_demo_data: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class AssociationRule(Base):
    """Apriori market-basket rule over catalog items: antecedents -> consequents."""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    antecedents: Mapped[list] = mapped_column(JSON)  # list[catalog_item_id]
    consequents: Mapped[list] = mapped_column(JSON)
    antecedent_key: Mapped[str] = mapped_column(String(120), index=True)  # sorted ids joined by ","
    support: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    lift: Mapped[float] = mapped_column(Float)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id", ondelete="CASCADE"))


class DemandForecast(Base):
    __tablename__ = "demand_forecasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), unique=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    predicted_7d: Mapped[float] = mapped_column(Float)
    daily_rate: Mapped[float] = mapped_column(Float)
    days_to_stockout: Mapped[float | None] = mapped_column(Float)
    recommended_restock: Mapped[int] = mapped_column(Integer, default=0)
    trend: Mapped[str] = mapped_column(String(12), default="steady")  # rising | steady | falling
    confidence: Mapped[str] = mapped_column(String(12), default="low")
    history_days: Mapped[int] = mapped_column(Integer, default=0)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PriceAnomaly(Base):
    __tablename__ = "price_anomalies"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    catalog_item_id: Mapped[int] = mapped_column(ForeignKey("catalog_items.id"), index=True)
    price: Mapped[float] = mapped_column(Float)
    reference_price: Mapped[float] = mapped_column(Float)  # local median
    deviation_pct: Mapped[float] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float)  # isolation forest anomaly score (higher = more unusual)
    direction: Mapped[str] = mapped_column(String(8))  # high | low
    peer_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[AnomalyStatus] = mapped_column(str_enum(AnomalyStatus, 12), default=AnomalyStatus.OPEN, index=True)
    review_note: Mapped[str | None] = mapped_column(String(300))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
