"""Opening-hours parsing for strings like '9:30 AM - 9:00 PM' with an optional weekly closed day."""
import re
from datetime import datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
_RANGE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([AP]M)\s*[-–to]+\s*(\d{1,2})(?::(\d{2}))?\s*([AP]M)", re.I)


def _to_time(h: str, m: str | None, ampm: str) -> time:
    hour = int(h) % 12 + (12 if ampm.upper() == "PM" else 0)
    return time(hour, int(m or 0))


def open_status(opening_hours: str | None, closed_on: str | None, now: datetime | None = None) -> dict:
    """{'is_open': bool | None, 'label': 'Open now, closes 9 PM'}; None when hours are unknown."""
    now = now or datetime.now(IST)
    if closed_on and now.strftime("%A").lower() == closed_on.strip().lower():
        return {"is_open": False, "label": f"Closed on {closed_on}s"}
    m = _RANGE.search(opening_hours or "")
    if not m:
        return {"is_open": None, "label": opening_hours or "Hours not listed"}
    start, end = _to_time(*m.group(1, 2, 3)), _to_time(*m.group(4, 5, 6))
    t = now.time()
    fmt = lambda x: x.strftime("%-I:%M %p").replace(":00", "")  # noqa: E731
    if start <= t < end:
        return {"is_open": True, "label": f"Open now, closes {fmt(end)}"}
    return {"is_open": False, "label": f"Closed, opens {fmt(start)}"}
