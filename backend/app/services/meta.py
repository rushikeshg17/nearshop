"""City configuration (map centre, localities) loaded from the seed data files."""
import json
from functools import lru_cache
from pathlib import Path

from app.core.config import BACKEND_DIR, settings

DATA_DIR: Path = BACKEND_DIR / "database" / "seed" / "data"


@lru_cache
def cities() -> dict:
    path = DATA_DIR / "cities.json"
    return json.loads(path.read_text()) if path.exists() else {}


def city_config() -> dict:
    all_cities = cities()
    city = all_cities.get(settings.seed_city) or next(iter(all_cities.values()), None)
    if city is None:
        return {"slug": settings.seed_city, "name": settings.seed_city.title(), "state": "",
                "center": {"lat": 15.1480, "lng": 76.9230}, "default_zoom": 13, "localities": []}
    return {"slug": settings.seed_city, **city}
