"""Test fixtures: an isolated, throwaway MongoDB database with a tiny, known dataset.

Tests use the cluster from NEARSHOP_MONGODB_URI (backend/.env) but their own database
(`nearshop_test_<random>`), which is dropped when the run ends. Your real data is never touched.
Settings are read at import time, so the environment is configured before importing the app.
"""
import os
import tempfile
import uuid
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="nearshop-test-"))
os.environ["NEARSHOP_MONGODB_DB"] = f"nearshop_test_{uuid.uuid4().hex[:10]}"
os.environ["NEARSHOP_ENABLE_SCHEDULER"] = "false"
os.environ["NEARSHOP_WARM_ON_STARTUP"] = "false"  # the fixture below creates the schema
os.environ["NEARSHOP_EMBEDDING_PROVIDER"] = "tfidf"  # fast and offline for tests
os.environ["NEARSHOP_MEDIA_DIR"] = str(_tmp / "media")
os.environ["NEARSHOP_MODEL_DIR"] = str(_tmp / "models")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.ai.semantic_index import index  # noqa: E402
from app.core.database import Database  # noqa: E402
from app.core.database import client as mongo_client  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import CatalogItem, Category, Product, Role, Shop, User  # noqa: E402
from database import schema  # noqa: E402

PASSWORD = "test-password-1"
CENTER = (12.3052, 76.6552)
HEADERS = {"X-NearShop-Client": "web"}


def _seed() -> dict:
    db = Database()
    schema.reset(db.mongo)
    pw = hash_password(PASSWORD)
    mobile = db.categories.insert(Category(slug="mobile-accessories", name="Mobile Accessories", icon="Smartphone",
                                           color_hue=280))
    plumbing = db.categories.insert(Category(slug="plumbing", name="Plumbing", icon="Droplets", color_hue=210,
                                             sort_order=1))
    charger = db.catalog_items.insert(CatalogItem(
        slug="samsung-25w-charger", name="Samsung 25W USB-C Fast Travel Charger", brand="Samsung",
        category_id=mobile.id, subcategory="chargers", typical_price=1299, mrp=1699,
        tags=["phone charger", "adapter", "fast charger", "type c charger"], icon="PlugZap"))
    tape = db.catalog_items.insert(CatalogItem(
        slug="teflon-tape", name="Astral PTFE Thread Seal Tape", brand="Astral", category_id=plumbing.id,
        subcategory="sealants", typical_price=40, mrp=50, tags=["teflon tape", "leak", "tap leak"], icon="Droplets"))

    def user(name, email, role, phone=None):
        return User(name=name, email=email, password_hash=pw, role=role, phone=phone)

    _, _, owner_a, owner_b, _ = db.users.insert_many([
        user("Test Customer", "cust@example.com", Role.CUSTOMER, "9876543210"),
        user("Other Customer", "other@example.com", Role.CUSTOMER),
        user("Owner A", "a@example.com", Role.OWNER),
        user("Owner B", "b@example.com", Role.OWNER),
        user("Admin", "admin@example.com", Role.ADMIN),
    ])

    shop_a, shop_b = db.shops.insert_many([
        Shop(owner_id=owner_a.id, name="Shop A", slug="shop-a", address_line="1 Main Road", locality="Agrahara",
             city="Mysuru", lat=CENTER[0] + 0.004, lng=CENTER[1], offers_delivery=True, delivery_radius_km=3,
             delivery_fee=30, free_delivery_above=2000, category_ids=[mobile.id, plumbing.id]),
        Shop(owner_id=owner_b.id, name="Shop B", slug="shop-b", address_line="2 Market Road", locality="Far Away",
             city="Mysuru", lat=CENTER[0] + 0.2, lng=CENTER[1], category_ids=[plumbing.id]),
    ])

    def listing(shop, item, price, qty):
        return Product(shop_id=shop.id, catalog_item_id=item.id, category_id=item.category_id, name=item.name,
                       brand=item.brand, keywords=" ".join(item.tags), icon=item.icon, price=price, mrp=item.mrp,
                       quantity=qty, low_stock_threshold=2)

    p_charger, p_tape, p_tape_far = db.products.insert_many([
        listing(shop_a, charger, 1249, 3), listing(shop_a, tape, 40, 50), listing(shop_b, tape, 38, 10)])
    return {
        "charger": p_charger.id, "tape": p_tape.id, "tape_far": p_tape_far.id,
        "shop_a": shop_a.id, "shop_b": shop_b.id,
    }


@pytest.fixture(scope="session")
def ids():
    data = _seed()
    index.mark_dirty()
    yield data
    mongo_client.drop_database(os.environ["NEARSHOP_MONGODB_DB"])


@pytest.fixture
def db(ids):
    return Database()


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
