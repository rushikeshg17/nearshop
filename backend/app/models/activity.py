"""Reservations, delivery orders, reviews, notifications, search history and AI outputs."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from app.core.database import utcnow
from app.models.base import Document, Embedded, GeoPoint, Timestamps
from app.models.core import Product, Shop, User
from app.models.enums import AnomalyStatus, OrderStatus, ReservationStatus, SaleSource


class Reservation(Document, Timestamps):
    """Collection `reservations`. Unique on code."""

    code: str
    customer_id: int
    shop_id: int
    product_id: int
    quantity: int
    unit_price: float
    status: ReservationStatus = ReservationStatus.REQUESTED
    note: str | None = None
    hold_minutes: int = 30
    expires_at: datetime
    stock_held: bool = False
    confirmed_at: datetime | None = None
    ready_at: datetime | None = None
    completed_at: datetime | None = None
    closed_at: datetime | None = None
    close_reason: str | None = None

    customer: User | None = Field(default=None, exclude=True)
    shop: Shop | None = Field(default=None, exclude=True)
    product: Product | None = Field(default=None, exclude=True)

    @property
    def total(self) -> float:
        return round(self.unit_price * self.quantity, 2)


class OrderItem(Embedded):
    """Line item embedded in its order. `name` and `unit_price` are snapshots taken at order time."""

    product_id: int
    name: str
    unit_price: float
    quantity: int

    product: Product | None = Field(default=None, exclude=True)


class Order(Document, Timestamps):
    """Collection `orders`. Shop-managed delivery order with its line items embedded, so an order
    is read and written as one document (cash on delivery in V1; payment_method keeps it modular)."""

    code: str
    customer_id: int
    shop_id: int
    status: OrderStatus = OrderStatus.PENDING
    payment_method: str = "cod"
    payment_status: str = "unpaid"
    delivery_address: str
    delivery_lat: float
    delivery_lng: float
    contact_phone: str
    distance_km: float
    subtotal: float
    delivery_fee: float
    total: float
    note: str | None = None
    stock_held: bool = False
    delivered_at: datetime | None = None
    closed_at: datetime | None = None
    close_reason: str | None = None
    items: list[OrderItem] = Field(default_factory=list)

    customer: User | None = Field(default=None, exclude=True)
    shop: Shop | None = Field(default=None, exclude=True)


class StatusEvent(Document):
    """Collection `status_events`. Every state-machine transition; used for timelines and reliability stats."""

    entity: str  # reservation | order
    entity_id: int
    shop_id: int
    from_status: str | None = None
    to_status: str
    actor_role: str  # customer | owner | admin | system
    actor_id: int | None = None
    note: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Review(Document):
    """Collection `reviews`. Exactly one of reservation_id / order_id is set, and each is unique:
    one review per completed reservation or delivered order."""

    customer_id: int
    shop_id: int
    product_id: int | None = None
    reservation_id: int | None = None
    order_id: int | None = None
    rating: int
    accuracy_rating: int | None = None
    delivery_rating: int | None = None
    comment: str | None = None
    created_at: datetime = Field(default_factory=utcnow)

    customer: User | None = Field(default=None, exclude=True)


class Notification(Document):
    """Collection `notifications`."""

    user_id: int
    kind: str
    title: str
    body: str | None = None
    link: str | None = None
    read_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class SearchEvent(Document):
    """Collection `search_history`. `location` (rounded to ~100 m) lets a shop see what people
    nearby are searching for with a geo query."""

    user_id: int | None = None
    query: str
    normalized_query: str
    category_slug: str | None = None
    results_count: int = 0
    location: GeoPoint | None = None
    created_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="before")
    @classmethod
    def _lat_lng_to_location(cls, data: Any) -> Any:
        if isinstance(data, dict) and "location" not in data and data.get("lat") is not None \
                and data.get("lng") is not None:
            data = dict(data)
            data["location"] = GeoPoint.of(data.pop("lat"), data.pop("lng"))
        return data


class SalesRecord(Document):
    """Collection `sales_history`. Completed sales. Real ones come from reservations/orders;
    demo rows are clearly flagged."""

    shop_id: int
    product_id: int
    catalog_item_id: int | None = None
    category_id: int | None = None  # denormalised from the product: category revenue without a join
    customer_id: int | None = None
    basket_id: str
    quantity: int
    unit_price: float
    source: SaleSource
    is_demo: bool = False
    sold_at: datetime = Field(default_factory=utcnow)


class ModelRun(Document):
    """Collection `model_runs`. One row per training run of an AI component."""

    name: str  # demand | recommendations | anomalies | embeddings | word2vec
    algorithm: str
    n_samples: int = 0
    metrics: dict[str, Any] = Field(default_factory=dict)
    data_note: str | None = None
    uses_demo_data: bool = False
    duration_ms: int = 0
    created_at: datetime = Field(default_factory=utcnow)


class AssociationRule(Document):
    """Collection `recommendations`. Apriori market-basket rule over catalog items: antecedents -> consequents."""

    antecedents: list[int]
    consequents: list[int]
    antecedent_key: str  # sorted ids joined by ","
    support: float
    confidence: float
    lift: float
    model_run_id: int


class DemandForecast(Document):
    """Collection `demand_forecasts`. One per product (unique on product_id)."""

    product_id: int
    shop_id: int
    predicted_7d: float
    daily_rate: float
    days_to_stockout: float | None = None
    recommended_restock: int = 0
    trend: str = "steady"  # rising | steady | falling
    confidence: str = "low"
    history_days: int = 0
    is_demo: bool = True
    model_run_id: int
    created_at: datetime = Field(default_factory=utcnow)


class PriceAnomaly(Document):
    """Collection `price_anomalies`. Review queue for an admin; never an automatic penalty."""

    product_id: int
    shop_id: int
    catalog_item_id: int
    price: float
    reference_price: float  # local median
    deviation_pct: float
    score: float  # isolation forest anomaly score (higher = more unusual)
    direction: str  # high | low
    peer_count: int
    status: AnomalyStatus = AnomalyStatus.OPEN
    review_note: str | None = None
    reviewed_by: int | None = None
    reviewed_at: datetime | None = None
    model_run_id: int
    created_at: datetime = Field(default_factory=utcnow)
