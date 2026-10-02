"""In-app notifications. The notify() call is the single seam for adding email/push later."""
from app.core.database import Database
from app.models import Notification


def notify(db: Database, user_id: int, kind: str, title: str, body: str | None = None, link: str | None = None) -> None:
    db.notifications.insert(Notification(user_id=user_id, kind=kind, title=title, body=body, link=link))
