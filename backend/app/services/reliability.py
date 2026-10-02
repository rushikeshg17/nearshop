"""Shop trust signals built from facts, not an opaque score.

Everything shown to customers is a statement they can understand and verify:
'Inventory updated 4 minutes ago', 'Confirmed 18 of 19 reservations in the last 90 days'.
"""
from datetime import timedelta
from statistics import median

from app.core.database import Database, utcnow
from app.models import InventoryReason, Shop
from app.models import OrderStatus as OS
from app.models import ReservationStatus as RS

WINDOW_DAYS = 90
OWNER_REASONS = [InventoryReason.INITIAL.value, InventoryReason.RESTOCK.value, InventoryReason.ADJUSTMENT.value]
HELD = {RS.CONFIRMED.value, RS.READY_FOR_PICKUP.value}


def shop_reliability(db: Database, shop: Shop) -> dict:
    now = utcnow()
    since = now - timedelta(days=WINDOW_DAYS)

    def update_days() -> int:
        # Distinct (IST) days in the last week on which the owner touched stock.
        rows = db.inventory_events.aggregate([
            {"$match": {"shop_id": shop.id, "created_at": {"$gte": now - timedelta(days=7)},
                        "reason": {"$in": OWNER_REASONS}}},
            {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}}}},
            {"$count": "days"},
        ])
        return rows[0]["days"] if rows else 0

    def reservations() -> list[dict]:
        return db.reservations.find_raw({"shop_id": shop.id, "created_at": {"$gte": since}},
                                        {"status": 1, "created_at": 1, "confirmed_at": 1})

    def transitions() -> list[dict]:
        return db.status_events.aggregate([
            {"$match": {"shop_id": shop.id, "created_at": {"$gte": since}}},
            {"$group": {"_id": {"entity": "$entity", "from": "$from_status", "to": "$to_status",
                                "actor": "$actor_role"}, "n": {"$sum": 1}}},
        ])

    def delivered() -> int:
        return db.orders.count({"shop_id": shop.id, "status": OS.DELIVERED, "created_at": {"$gte": since}})

    def accuracy() -> float | None:
        rows = db.reviews.aggregate([
            {"$match": {"shop_id": shop.id, "accuracy_rating": {"$ne": None}}},
            {"$group": {"_id": None, "avg": {"$avg": "$accuracy_rating"}}},
        ])
        return rows[0]["avg"] if rows else None

    days, res_rows, events, orders_delivered, avg_accuracy = db.gather(
        update_days, reservations, transitions, delivered, accuracy)

    def moved(*, entity: str | None = "reservation", frm: set | None = None, to: set | None = None,
              actor: str | None = None) -> int:
        return sum(e["n"] for e in events
                   if (entity is None or e["_id"]["entity"] == entity)
                   and (frm is None or e["_id"]["from"] in frm)
                   and (to is None or e["_id"]["to"] in to)
                   and (actor is None or e["_id"]["actor"] == actor))

    # Held reservations that ended without a pickup (customer no-show, cancellation, expiry).
    dropped_after_hold = moved(frm=HELD, to={RS.CANCELLED.value, RS.EXPIRED.value})
    responded = moved(frm={RS.REQUESTED.value}, to={RS.CONFIRMED.value})
    request_expired = moved(frm={RS.REQUESTED.value}, to={RS.EXPIRED.value})
    shop_cancels = moved(entity=None, to={"CANCELLED"}, actor="owner")
    rejected = sum(1 for r in res_rows if r["status"] == RS.REJECTED)
    completed = sum(1 for r in res_rows if r["status"] == RS.COMPLETED)
    requests_decided = responded + rejected + request_expired

    # Median minutes from request to confirmation.
    response_minutes = [(r["confirmed_at"] - r["created_at"]).total_seconds() / 60 for r in res_rows
                        if r.get("confirmed_at") and r["confirmed_at"] >= r["created_at"]]
    median_response = round(median(response_minutes)) if response_minutes else None

    highlights: list[str] = []
    if days >= 5:
        highlights.append("Frequently updated inventory")
    if requests_decided >= 5 and responded / requests_decided >= 0.9:
        highlights.append(f"Confirmed {responded} of {requests_decided} reservation requests")
    if median_response is not None and median_response <= 10 and len(response_minutes) >= 5:
        highlights.append(f"Usually confirms in about {max(median_response, 1)} min")
    if avg_accuracy and avg_accuracy >= 4.5 and shop.rating_count >= 5:
        highlights.append("Customers say items match the listing")
    if shop.established_year and now.year - shop.established_year >= 15:
        highlights.append(f"Serving since {shop.established_year}")

    return {
        "inventory_updated_at": shop.inventory_updated_at,
        "inventory_update_days_7d": days,
        "frequently_updated": days >= 5,
        "reservation_requests_90d": requests_decided,
        "reservations_confirmed_90d": responded,
        "acceptance_rate": round(responded / requests_decided, 3) if requests_decided else None,
        "completion_rate": (
            round(completed / (completed + dropped_after_hold), 3) if completed + dropped_after_hold else None
        ),
        "shop_cancellations_90d": shop_cancels,
        "median_response_minutes": median_response,
        "orders_delivered_90d": orders_delivered,
        "rating_avg": shop.rating_avg,
        "rating_count": shop.rating_count,
        "accuracy_avg": round(float(avg_accuracy), 1) if avg_accuracy else None,
        "highlights": highlights,
    }
