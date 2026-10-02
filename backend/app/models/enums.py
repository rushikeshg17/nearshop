"""Enumerations shared by models, schemas and services."""
from enum import StrEnum


class Role(StrEnum):
    CUSTOMER = "customer"
    OWNER = "owner"
    ADMIN = "admin"


class ReservationStatus(StrEnum):
    """Pickup reservation lifecycle.

    REQUESTED -> CONFIRMED -> READY_FOR_PICKUP -> COMPLETED
    Side exits: REJECTED (shop declines), CANCELLED (customer or shop), EXPIRED (timer ran out).
    Stock is held (decremented) when the shop confirms, and released on any side exit.
    """

    REQUESTED = "REQUESTED"
    CONFIRMED = "CONFIRMED"
    READY_FOR_PICKUP = "READY_FOR_PICKUP"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class OrderStatus(StrEnum):
    """Shop-managed delivery lifecycle.

    PENDING -> SHOP_CONFIRMED -> PREPARING -> OUT_FOR_DELIVERY -> DELIVERED
    Failure paths: CANCELLED (before dispatch), DELIVERY_FAILED -> RETURNED_TO_SHOP.
    """

    PENDING = "PENDING"
    SHOP_CONFIRMED = "SHOP_CONFIRMED"
    PREPARING = "PREPARING"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    DELIVERY_FAILED = "DELIVERY_FAILED"
    RETURNED_TO_SHOP = "RETURNED_TO_SHOP"


class InventoryReason(StrEnum):
    INITIAL = "initial"
    RESTOCK = "restock"
    ADJUSTMENT = "adjustment"
    RESERVATION_HOLD = "reservation_hold"
    RESERVATION_RELEASE = "reservation_release"
    ORDER_HOLD = "order_hold"
    ORDER_RELEASE = "order_release"


class AnomalyStatus(StrEnum):
    OPEN = "open"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"


class SaleSource(StrEnum):
    RESERVATION = "reservation"
    ORDER = "order"
    DEMO = "demo"
