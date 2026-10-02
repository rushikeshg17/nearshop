"""Background jobs (in-process, no queue needed for V1)."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.database import SessionLocal
from app.services.orders import cancel_stale_pending
from app.services.reservations import expire_due

log = logging.getLogger(__name__)


def sweep_expired() -> None:
    with SessionLocal() as db:
        n = expire_due(db)
        m = cancel_stale_pending(db)
        if n or m:
            log.info("expired %d reservations, auto-cancelled %d stale orders", n, m)


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(sweep_expired, "interval", seconds=30, id="sweep_expired", max_instances=1, coalesce=True)
    scheduler.start()
    return scheduler
