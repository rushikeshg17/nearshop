"""Test fixtures: an isolated SQLite database with a tiny, known dataset.

Settings are read at import time, so the environment is configured before importing the app.
"""
import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="nearshop-test-"))
os.environ["NEARSHOP_DATABASE_URL"] = f"sqlite:///{_tmp / 'test.db'}"
os.environ["NEARSHOP_ENABLE_SCHEDULER"] = "false"
os.environ["NEARSHOP_EMBEDDING_PROVIDER"] = "tfidf"  # fast and offline for tests
os.environ["NEARSHOP_MEDIA_DIR"] = str(_tmp / "media")
os.environ["NEARSHOP_MODEL_DIR"] = str(_tmp / "models")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.ai.semantic_index import index  # noqa: E402
from app.core.config import BACKEND_DIR  # noqa: E402
from app.core.database import SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import CatalogItem, Category, Product, Role, Shop, User  # noqa: E402

PASSWORD = "test-password-1"
CENTER = (12.3052, 76.6552)
HEADERS = {"X-NearShop-Client": "web"}


def _migrate() -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "database" / "migrations"))
    command.upgrade(cfg, "head")


def _seed() -> dict:
    db = SessionLocal()
    pw = hash_password(PASSWORD)
    mobile = Category(slug="mobile-accessories", name="Mobile Accessories", icon="Smartphone", color_hue=280)
    plumbing = Category(slug="plumbing", name="Plumbing", icon="Droplets", color_hue=210)
    db.add_all([mobile, plumbing])
    db.flush()
    charger = CatalogItem(slug="samsung-25w-charger", name="Samsung 25W USB-C Fast Travel Charger", brand="Samsung",
                          category_id=mobile.id, subcategory="chargers", typical_price=1299, mrp=1699,
                          tags=["phone charger", "adapter", "fast charger", "type c charger"], icon="PlugZap")
    tape = CatalogItem(slug="teflon-tape", name="Astral PTFE Thread Seal Tape", brand="Astral", category_id=plumbing.id,
                       subcategory="sealants", typical_price=40, mrp=50, tags=["teflon tape", "leak", "tap leak"],
                       icon="Droplets")
    db.add_all([charger, tape])
    db.flush()

    customer = User(name="Test Customer", email="cust@example.com", password_hash=pw, role=Role.CUSTOMER, phone="9876543210")
    other_customer = User(name="Other Customer", email="other@example.com", password_hash=pw, role=Role.CUSTOMER)
    owner_a = User(name="Owner A", email="a@example.com", password_hash=pw, role=Role.OWNER)
    owner_b = User(name="Owner B", email="b@example.com", password_hash=pw, role=Role.OWNER)
    admin = User(name="Admin", email="admin@example.com", password_hash=pw, role=Role.ADMIN)
    db.add_all([customer, other_customer, owner_a, owner_b, admin])
    db.flush()

    shop_a = Shop(owner_id=owner_a.id, name="Shop A", slug="shop-a", address_line="1 Main Road", locality="Agrahara",
                  city="Mysuru", lat=CENTER[0] + 0.004, lng=CENTER[1], offers_delivery=True, delivery_radius_km=3,
                  delivery_fee=30, free_delivery_above=2000, categories=[mobile, plumbing])
    shop_b = Shop(owner_id=owner_b.id, name="Shop B", slug="shop-b", address_line="2 Market Road", locality="Far Away",
                  city="Mysuru", lat=CENTER[0] + 0.2, lng=CENTER[1], categories=[plumbing])
    db.add_all([shop_a, shop_b])
    db.flush()

    def listing(shop, item, price, qty):
        return Product(shop_id=shop.id, catalog_item_id=item.id, category_id=item.category_id, name=item.name,
                       brand=item.brand, keywords=" ".join(item.tags), icon=item.icon, price=price, mrp=item.mrp,
                       quantity=qty, low_stock_threshold=2)

    p_charger = listing(shop_a, charger, 1249, 3)
    p_tape = listing(shop_a, tape, 40, 50)
    p_tape_far = listing(shop_b, tape, 38, 10)
    db.add_all([p_charger, p_tape, p_tape_far])
    db.commit()
    ids = {
        "charger": p_charger.id, "tape": p_tape.id, "tape_far": p_tape_far.id,
        "shop_a": shop_a.id, "shop_b": shop_b.id,
    }
    db.close()
    return ids


@pytest.fixture(scope="session")
def ids():
    _migrate()
    data = _seed()
    index.mark_dirty()
    yield data
    engine.dispose()


@pytest.fixture
def client(ids):
    with TestClient(app) as c:
        yield c


def login(client: TestClient, email: str) -> TestClient:
    res = client.post("/api/auth/login", json={"email": email, "password": PASSWORD}, headers=HEADERS)
    assert res.status_code == 200, res.text
    return client


@pytest.fixture
def customer(client):
    return login(client, "cust@example.com")


@pytest.fixture
def owner_a(ids):
    with TestClient(app) as c:
        yield login(c, "a@example.com")


@pytest.fixture
def owner_b(ids):
    with TestClient(app) as c:
        yield login(c, "b@example.com")


@pytest.fixture
def admin(ids):
    with TestClient(app) as c:
        yield login(c, "admin@example.com")
