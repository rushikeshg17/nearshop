"""Shop trust signals built from facts, not an opaque score.

Everything shown to customers is a statement they can understand and verify:
'Inventory updated 4 minutes ago', 'Confirmed 18 of 19 reservations in the last 90 days'.
"""
from datetime import timedelta
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.models import (
    InventoryEvent,
    InventoryReason,
    Order,
    Reservation,
    Review,
    StatusEvent,
)
from app.models import (
    OrderStatus as OS,
)
from app.models import (
    ReservationStatus as RS,
)

WINDOW_DAYS = 90
OWNER_REASONS = [InventoryReason.INITIAL.value, InventoryReason.RESTOCK.value, InventoryReason.ADJUSTMENT.value]


def ratings_for(db: Session, shop_ids: list[int]) -> dict[int, tuple[float, int]]:
    if not shop_ids:
        return {}
    rows = db.execute(
        select(Review.shop_id, func.avg(Review.rating), func.count(Review.id))
        .where(Review.shop_id.in_(shop_ids))
        .group_by(Review.shop_id)
    ).all()
    return {sid: (round(float(avg), 1), int(n)) for sid, avg, n in rows}


def shop_reliability(db: Session, shop) -> dict:
    now = utcnow()
    since = now - timedelta(days=WINDOW_DAYS)

    update_days = db.scalar(
        select(func.count(func.distinct(func.date(InventoryEvent.created_at)))).where(
            InventoryEvent.shop_id == shop.id,
            InventoryEvent.reason.in_(OWNER_REASONS),
            InventoryEvent.created_at >= now - timedelta(days=7),
        )
    ) or 0

    res_counts = dict(
        db.execute(
            select(Reservation.status, func.count())
            .where(Reservation.shop_id == shop.id, Reservation.created_at >= since)
            .group_by(Reservation.status)
        ).all()
    )
    # Held reservations that ended without a pickup (customer no-show, cancellation, expiry).
    dropped_after_hold = db.scalar(
        select(func.count()).select_from(StatusEvent).where(
            StatusEvent.shop_id == shop.id,
            StatusEvent.entity == "reservation",
            StatusEvent.from_status.in_([RS.CONFIRMED.value, RS.READY_FOR_PICKUP.value]),
            StatusEvent.to_status.in_([RS.CANCELLED.value, RS.EXPIRED.value]),
            StatusEvent.created_at >= since,
        )
    ) or 0
    responded = db.scalar(
        select(func.count()).select_from(StatusEvent).where(
            StatusEvent.shop_id == shop.id,
            StatusEvent.entity == "reservation",
            StatusEvent.from_status == RS.REQUESTED.value,
            StatusEvent.to_status == RS.CONFIRMED.value,
            StatusEvent.created_at >= since,
        )
    ) or 0
    rejected = res_counts.get(RS.REJECTED, 0)
    request_expired = db.scalar(
        select(func.count()).select_from(StatusEvent).where(
            StatusEvent.shop_id == shop.id,
            StatusEvent.entity == "reservation",
            StatusEvent.from_status == RS.REQUESTED.value,
            StatusEvent.to_status == RS.EXPIRED.value,
            StatusEvent.created_at >= since,
        )
    ) or 0
    requests_decided = responded + rejected + request_expired
    completed = res_counts.get(RS.COMPLETED, 0)
    shop_cancels = db.scalar(
        select(func.count()).select_from(StatusEvent).where(
            StatusEvent.shop_id == shop.id,
            StatusEvent.to_status == "CANCELLED",
            StatusEvent.actor_role == "owner",
            StatusEvent.created_at >= since,
        )
    ) or 0

    # Median minutes from request to confirmation.
    pairs = db.execute(
        select(Reservation.created_at, Reservation.confirmed_at).where(
            Reservation.shop_id == shop.id, Reservation.confirmed_at.is_not(None), Reservation.created_at >= since
        )
    ).all()
    response_minutes = [(c - r).total_seconds() / 60 for r, c in pairs if c and c >= r]
    median_response = round(median(response_minutes)) if response_minutes else None

    delivered = db.scalar(
        select(func.count()).select_from(Order).where(
            Order.shop_id == shop.id, Order.status == OS.DELIVERED, Order.created_at >= since
        )
    ) or 0

    rating = ratings_for(db, [shop.id]).get(shop.id, (None, 0))
    avg_accuracy = db.scalar(
        select(func.avg(Review.accuracy_rating)).where(Review.shop_id == shop.id, Review.accuracy_rating.is_not(None))
    )

    highlights: list[str] = []
    if update_days >= 5:
        highlights.append("Frequently updated inventory")
    if requests_decided >= 5 and responded / requests_decided >= 0.9:
        highlights.append(f"Confirmed {responded} of {requests_decided} reservation requests")
    if median_response is not None and median_response <= 10 and len(response_minutes) >= 5:
        highlights.append(f"Usually confirms in about {max(median_response, 1)} min")
    if avg_accuracy and avg_accuracy >= 4.5 and rating[1] >= 5:
        highlights.append("Customers say items match the listing")
    if shop.established_year and now.year - shop.established_year >= 15:
        highlights.append(f"Serving since {shop.established_year}")

    return {
        "inventory_updated_at": shop.inventory_updated_at,
        "inventory_update_days_7d": update_days,
        "frequently_updated": update_days >= 5,
        "reservation_requests_90d": requests_decided,
        "reservations_confirmed_90d": responded,
        "acceptance_rate": round(responded / requests_decided, 3) if requests_decided else None,
        "completion_rate": (
            round(completed / (completed + dropped_after_hold), 3) if completed + dropped_after_hold else None
        ),
        "shop_cancellations_90d": shop_cancels,
        "median_response_minutes": median_response,
        "orders_delivered_90d": delivered,
        "rating_avg": rating[0],
        "rating_count": rating[1],
        "accuracy_avg": round(float(avg_accuracy), 1) if avg_accuracy else None,
        "highlights": highlights,
    }
