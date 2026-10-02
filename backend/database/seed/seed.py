"""Seed NearShop with a realistic, clearly-labelled demo city.

    uv run python -m database.seed.seed

It writes to the MongoDB database in NEARSHOP_MONGODB_URI / NEARSHOP_MONGODB_DB and REPLACES what is
there. Documents are built in memory and sent with bulk inserts, so a hosted cluster is seeded in
about a minute. The city comes from NEARSHOP_SEED_CITY (default ballari; see cities.json for options).

What it creates (all demo data; sales are flagged is_demo=True so AI outputs say so):
  - categories + ~300 catalog items, ~48 shops spread over real localities
  - each shop's listings with local price variation (and a few deliberate outliers)
  - 150 days of daily sales with weekday + monthly seasonality, plus co-purchase baskets
  - reservation / delivery history with realistic outcomes, status timelines and reviews
  - search history around the city, then trains every AI model

Demo logins (password from NEARSHOP_DEMO_PASSWORD, default in .env.example):
  customer  priya@nearshop.demo
  owner     owner@nearshop.demo
  admin     admin@nearshop.demo
"""
from __future__ import annotations

import json
import math
import os
import random
import time
from collections import defaultdict
from datetime import datetime, timedelta

import numpy as np

from app.ai.pipeline import train_all
from app.core.config import BACKEND_DIR, settings
from app.core.database import Database, utcnow
from app.core.security import hash_password
from app.models import (
    CatalogItem,
    Category,
    InventoryReason,
    Notification,
    Order,
    OrderItem,
    Product,
    Reservation,
    Review,
    Role,
    SaleSource,
    SalesRecord,
    SearchEvent,
    Shop,
    User,
)
from app.models import (
    OrderStatus as OS,
)
from app.models import (
    ReservationStatus as RS,
)
from app.services.loaders import reset_category_cache
from app.utils.geo import haversine_km
from app.utils.text import short_code, slugify
from database import schema

DATA = BACKEND_DIR / "database" / "seed" / "data"
SALES_DAYS = 150
HISTORY_DAYS = 60
rng = random.Random(42)
nprng = np.random.default_rng(42)

FIRST_NAMES = ["Aarav", "Ananya", "Arjun", "Bhavya", "Chaitra", "Deepak", "Divya", "Ganesh", "Harsha", "Ishita",
               "Karthik", "Kavya", "Lakshmi", "Manoj", "Meghana", "Mohan", "Nandini", "Naveen", "Pooja", "Prakash",
               "Rahul", "Ramya", "Ravi", "Rekha", "Rohit", "Sandeep", "Shreya", "Sneha", "Suresh", "Swathi",
               "Tejas", "Uma", "Varun", "Vidya", "Vinay", "Yamini", "Abdul", "Farah", "Imran", "Joseph", "Mary",
               "Nisha", "Pradeep", "Sanjay", "Sunitha", "Venkatesh", "Zoya", "Girish", "Hema", "Kiran"]
LAST_NAMES = ["Rao", "Gowda", "Shetty", "Kumar", "Hegde", "Nayak", "Reddy", "Iyer", "Murthy", "Prasad", "Bhat",
              "Naik", "Patil", "Khan", "D'Souza", "Menon", "Sharma", "Joshi", "Kulkarni", "Swamy"]

REVIEW_COMMENTS = {
    5: ["Item was kept ready at the counter. In and out in two minutes.",
        "Exactly what the listing said. Stock count was accurate.",
        "Owner explained the difference between the two models. Very helpful.",
        "Saved me a trip across town. Will reserve here again.",
        "Good price and genuine product. Bill given without asking.",
        "Delivered within the hour and the delivery person called before arriving."],
    4: ["Got what I needed. Had to wait a few minutes at pickup.",
        "Good shop, slightly busy in the evening.",
        "Product was fine, packaging could be better.",
        "Confirmed quickly. Price was a little higher than the next shop but they had it in stock."],
    3: ["Item was available but they took a while to confirm.",
        "Okay experience. The colour was slightly different from what I expected.",
        "Delivery came later than promised."],
    2: ["Had to wait 20 minutes even after the reservation was confirmed.",
        "Listing said 5 in stock but only one was left."],
    1: ["Shop was closed when I arrived even though it showed open."],
}
ZERO_RESULT_QUERIES = ["sofa set", "cement bag 50kg", "gas cylinder", "paracetamol", "fresh vegetables",
                       "car tyre 185/65 r15", "gold chain", "laptop repair", "wedding lehenga", "ac gas refill"]
MISSPELLINGS = {"charger": "chrager", "notebook": "notbook", "umbrella": "umbrela", "helmet": "helmit",
                "slipper": "sliper", "engine oil": "enjine oil", "extension board": "extention board",
                "tempered glass": "temperd glass", "detergent": "detergant", "mosquito": "mosquto"}


def load(name: str):
    return json.loads((DATA / name).read_text())


class Ids:
    """Hands out integer ids locally while seeding; `save_counters` then tells the database where
    each sequence ended so the running app continues from there."""

    def __init__(self) -> None:
        self.last: dict[str, int] = defaultdict(int)

    def __call__(self, collection: str) -> int:
        self.last[collection] += 1
        return self.last[collection]

    def save_counters(self, db: Database) -> None:
        db.mongo["counters"].delete_many({})
        db.mongo["counters"].insert_many([{"_id": name, "seq": seq} for name, seq in self.last.items()])


def bulk_insert(collection, docs: list, chunk: int = 5000) -> None:
    """Insert models or plain dicts in unordered batches."""
    for i in range(0, len(docs), chunk):
        batch = [d if isinstance(d, dict) else d.to_mongo() for d in docs[i:i + chunk]]
        collection.raw.insert_many(batch, ordered=False)


def round_price(p: float) -> float:
    if p >= 500:
        return float(round(p / 10) * 10 - (1 if rng.random() < 0.5 else 0))
    if p >= 100:
        return float(round(p / 5) * 5)
    return float(max(1, round(p)))


def seasonal_factor(season: list[float], day: datetime) -> float:
    """Smoothly interpolate monthly multipliers so demand drifts day by day (enables trend detection)."""
    pos = day.month - 1 + (day.day - 15) / 30.0
    lo = math.floor(pos)
    frac = pos - lo
    return season[lo % 12] * (1 - frac) + season[(lo + 1) % 12] * frac


WEEKDAY = [0.9, 0.92, 0.95, 0.97, 1.05, 1.2, 1.3]  # Mon..Sun


def main() -> None:
    city_slug = settings.seed_city
    started = time.time()
    demo_password = os.environ.get("NEARSHOP_DEMO_PASSWORD", "nearshop123")
    cities = load("cities.json")
    if city_slug not in cities:
        raise SystemExit(f"Unknown NEARSHOP_SEED_CITY '{city_slug}'. Options: {', '.join(cities)}")
    city = cities[city_slug]
    categories_data = load("categories.json")
    catalog_data = load("catalog.json")
    shops_data = load("shops.json")
    baskets_data = load("baskets.json")

    db = Database()
    print(f"Resetting MongoDB database '{db.mongo.name}' and seeding {city['name']}...")
    schema.reset(db.mongo)
    reset_category_cache()
    now = utcnow()
    nid = Ids()
    pw_hash = hash_password(demo_password)
    filler_hash = hash_password(os.urandom(16).hex())  # synthetic customers cannot log in

    # ------------------------------------------------------------ categories + catalog
    cats: dict[str, Category] = {}
    for i, c in enumerate(categories_data):
        cats[c["slug"]] = Category(id=nid("categories"), slug=c["slug"], name=c["name"], icon=c["icon"],
                                   description=c.get("description"), color_hue=c.get("color_hue", 250), sort_order=i)
    cat_by_id = {c.id: c for c in cats.values()}
    catalog: dict[str, CatalogItem] = {}
    meta: dict[int, dict] = {}
    for item in catalog_data:
        catalog[item["slug"]] = CatalogItem(
            id=nid("catalog_items"), slug=item["slug"], name=item["name"], brand=item.get("brand"),
            category_id=cats[item["category"]].id, subcategory=item.get("subcategory"),
            unit=item.get("unit"), mrp=item.get("mrp"), typical_price=item["typical_price"],
            description=item.get("description"), specs=item.get("specs") or {},
            tags=item.get("tags") or [], icon=item.get("icon") or cats[item["category"]].icon)
    for item in catalog_data:
        ci = catalog[item["slug"]]
        meta[ci.id] = {"demand": float(item.get("base_daily_demand", 0.5)),
                       "season": item.get("seasonality") or [1.0] * 12, "category": item["category"]}
    by_category: dict[str, list[CatalogItem]] = defaultdict(list)
    for ci in catalog.values():
        by_category[cat_by_id[ci.category_id].slug].append(ci)

    # ------------------------------------------------------------ users
    admin = User(id=nid("users"), name="NearShop Admin", email="admin@nearshop.demo", password_hash=pw_hash, role=Role.ADMIN)
    center = city["center"]
    priya = User(id=nid("users"), name="Priya Sharma", email="priya@nearshop.demo", phone="9876501234", password_hash=pw_hash,
                 role=Role.CUSTOMER, home_lat=center["lat"] + 0.004, home_lng=center["lng"] - 0.006,
                 home_label=city["localities"][0]["name"])
    users: list[User] = [admin, priya]
    customers = [priya]
    used_emails = {"admin@nearshop.demo", "priya@nearshop.demo"}
    for _ in range(140):
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        email = f"{slugify(name).replace('-', '.')}{rng.randint(1, 999)}@example.com"
        if email in used_emails:
            continue
        used_emails.add(email)
        customers.append(User(id=nid("users"), name=name, email=email, phone=f"9{rng.randint(100000000, 999999999)}",
                              password_hash=filler_hash, role=Role.CUSTOMER,
                              created_at=now - timedelta(days=rng.randint(20, 200))))
    users += customers[1:]

    # ------------------------------------------------------------ shops
    localities = city["localities"]
    # The featured demo shop: a mobile-accessories shop placed at the locality closest to the city centre.
    central = sorted(localities, key=lambda loc: haversine_km(center["lat"], center["lng"], loc["lat"], loc["lng"]))
    featured_idx = next((i for i, s in enumerate(shops_data) if "mobile-accessories" in s["categories"]), 0)
    shops: list[Shop] = []
    shop_profile: dict[int, dict] = {}
    for i, tpl in enumerate(shops_data):
        loc = central[0] if i == featured_idx else localities[(i * 7 + 3) % len(localities)]
        jitter = 0.0 if i == featured_idx else 0.0035
        lat = loc["lat"] + rng.uniform(-jitter, jitter)
        lng = loc["lng"] + rng.uniform(-jitter, jitter)
        is_featured = i == featured_idx
        owner = User(id=nid("users"), name=tpl["owner_name"], password_hash=pw_hash if is_featured else filler_hash,
                     email="owner@nearshop.demo" if is_featured else f"{slugify(tpl['name'])}@shops.nearshop.demo",
                     phone=f"9{rng.randint(100000000, 999999999)}", role=Role.OWNER,
                     created_at=now - timedelta(days=rng.randint(150, 400)))
        users.append(owner)
        slug = slugify(f"{tpl['name']} {loc['name']}")
        shop = Shop(
            id=nid("shops"), owner=owner, owner_id=owner.id, name=tpl["name"], slug=slug, tagline=tpl.get("tagline"),
            description=tpl.get("description"), phone=owner.phone,
            address_line=f"{rng.randint(1, 480)}, {rng.choice(['Main Road', 'Cross Road', '1st Main', '2nd Cross', 'Market Road', 'Temple Street'])}, {loc['name']}",
            locality=loc["name"], city=city["name"], pincode=loc.get("pincode"), lat=lat, lng=lng,
            opening_hours=tpl.get("opening_hours", "9:30 AM - 9:00 PM"), closed_on=tpl.get("closed_on"),
            established_year=tpl.get("established_year"), offers_pickup=True,
            offers_delivery=bool(tpl.get("offers_delivery")) or is_featured,
            delivery_radius_km=float(tpl.get("delivery_radius_km") or (5 if is_featured else 0)),
            delivery_fee=float(tpl.get("delivery_fee") or (30 if is_featured else 0)),
            free_delivery_above=tpl.get("free_delivery_above") or (999 if is_featured else None),
            hold_minutes=rng.choice([30, 30, 45, 60]) if not is_featured else 30,
            is_verified=is_featured or rng.random() < 0.7,
            categories=[cats[c] for c in tpl["categories"]],
            category_ids=[cats[c].id for c in tpl["categories"]],
            created_at=owner.created_at, updated_at=owner.created_at,
        )
        shops.append(shop)
    for s in shops:
        s_featured = s.owner.email == "owner@nearshop.demo"
        shop_profile[s.id] = {
            "activity": 1.0 if s_featured else rng.choice([0.35, 0.55, 0.75, 0.9, 1.0]),
            "popularity": 1.25 if s_featured else rng.uniform(0.6, 1.4),
            "quality": 4.6 if s_featured else rng.uniform(3.7, 4.8),
            "responsiveness": 0.95 if s_featured else rng.uniform(0.7, 0.98),
            "response_median": 4 if s_featured else rng.choice([4, 6, 9, 14, 25]),
        }

    # ------------------------------------------------------------ listings
    products: list[Product] = []
    for s in shops:
        cat_slugs = [c.slug for c in s.categories]
        share = 0.8 if len(cat_slugs) == 1 else 0.5 if len(cat_slugs) == 2 else 0.38
        for cs in cat_slugs:
            pool = by_category[cs]
            chosen = rng.sample(pool, max(6, int(len(pool) * rng.uniform(share - 0.1, share + 0.1))))
            for ci in chosen:
                m = meta[ci.id]
                factor = min(max(rng.gauss(1.0, 0.05), 0.88), 1.08)
                outlier = rng.random()
                if outlier < 0.02:
                    factor = rng.uniform(1.35, 1.7)  # deliberately overpriced (for anomaly detection demo)
                elif outlier < 0.035:
                    factor = rng.uniform(0.55, 0.7)  # suspiciously cheap / data-entry error
                price = round_price(ci.typical_price * factor)
                if ci.mrp and factor <= 1.08:
                    price = min(price, ci.mrp)
                daily = m["demand"] * shop_profile[s.id]["popularity"]
                r = rng.random()
                if r < 0.07:
                    qty = 0
                elif r < 0.17:
                    qty = rng.randint(1, 4)
                else:
                    qty = max(3, int(daily * rng.uniform(8, 35)) + rng.randint(0, 6))
                keywords = " ".join(dict.fromkeys([*(ci.tags or []), cats[cs].name.lower(),
                                                   (ci.subcategory or "").replace("-", " ")]))
                p = Product(id=nid("products"), shop_id=s.id, catalog_item_id=ci.id, category_id=ci.category_id, name=ci.name,
                            brand=ci.brand, unit=ci.unit, description=ci.description, specs=ci.specs,
                            keywords=keywords, icon=ci.icon, price=price, mrp=ci.mrp, quantity=qty,
                            low_stock_threshold=max(2, min(10, int(daily * 3) + 1)),
                            sku=f"{slugify(ci.brand or 'gen')[:4].upper()}-{ci.id:04d}",
                            created_at=now - timedelta(days=SALES_DAYS + rng.randint(0, 60)))
                products.append(p)
    print(f"  {len(shops)} shops, {len(products)} listings")

    # ------------------------------------------------------------ freshness + inventory events
    inv_rows = []
    for s in shops:
        act = shop_profile[s.id]["activity"]
        minutes = rng.uniform(2, 40) if act >= 0.9 else rng.uniform(60, 600) if act >= 0.7 else rng.uniform(900, 5000)
        s.inventory_updated_at = now - timedelta(minutes=minutes)
    shop_by_id = {s.id: s for s in shops}
    for p in products:
        s = shop_by_id[p.shop_id]
        act = shop_profile[s.id]["activity"]
        inv_rows.append(dict(_id=nid("inventory_events"), product_id=p.id, shop_id=s.id, delta=p.quantity,
                             quantity_after=p.quantity,
                             reason=InventoryReason.INITIAL.value, actor_id=s.owner_id, created_at=p.created_at))
        qty_after = p.quantity
        for d in range(0, 7):
            if rng.random() < act * 0.18:
                when = now - timedelta(days=d, minutes=rng.randint(0, 600))
                when = max(min(when, s.inventory_updated_at), now - timedelta(days=7))
                delta = rng.randint(2, 12)
                inv_rows.append(dict(_id=nid("inventory_events"), product_id=p.id, shop_id=s.id, delta=delta,
                                     quantity_after=qty_after,
                                     reason=InventoryReason.RESTOCK.value, actor_id=s.owner_id, created_at=when))
                qty_after = max(0, qty_after - delta)
        p.stock_updated_at = s.inventory_updated_at - timedelta(minutes=rng.uniform(0, 240) * (1.2 - act))
        p.updated_at = p.stock_updated_at

    # ------------------------------------------------------------ demo sales (daily demand + baskets)
    print("  generating sales history...")
    sales_rows = []
    day0 = (now - timedelta(days=SALES_DAYS - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    for p in products:
        m = meta[p.catalog_item_id]
        pop = shop_profile[p.shop_id]["popularity"]
        base = m["demand"] * pop
        drift = rng.uniform(-0.25, 0.25)  # slow product-level trend over the window
        for d in range(SALES_DAYS):
            day = day0 + timedelta(days=d)
            lam = base * seasonal_factor(m["season"], day) * WEEKDAY[day.weekday()] * (1 + drift * d / SALES_DAYS)
            k = int(nprng.poisson(max(lam, 0)))
            if k:
                sold_at = day + timedelta(hours=rng.randint(4, 15), minutes=rng.randint(0, 59))  # 9:30am-9pm IST
                if sold_at > now:
                    continue
                sales_rows.append(dict(_id=nid("sales_history"), shop_id=p.shop_id, product_id=p.id,
                                       catalog_item_id=p.catalog_item_id, category_id=p.category_id,
                                       customer_id=None, basket_id=f"demo-{len(sales_rows)}", quantity=k,
                                       unit_price=p.price, source=SaleSource.DEMO.value, is_demo=True,
                                       sold_at=sold_at))

    # Co-purchase baskets, only where the shop actually stocks the items.
    shop_items: dict[int, dict[int, Product]] = defaultdict(dict)
    for p in products:
        shop_items[p.shop_id][p.catalog_item_id] = p
    basket_defs = [([catalog[s].id for s in b["items"] if s in catalog], b.get("weight", 1)) for b in baskets_data]
    basket_defs = [(ids, w) for ids, w in basket_defs if len(ids) >= 2]
    n_baskets = 0
    for s in shops:
        items = shop_items[s.id]
        usable = [(ids, w) for ids, w in basket_defs if sum(1 for i in ids if i in items) >= 2]
        if not usable:
            continue
        per_day = 0.9 * shop_profile[s.id]["popularity"]
        for d in range(SALES_DAYS):
            for _ in range(int(nprng.poisson(per_day))):
                ids, _w = rng.choices(usable, weights=[w for _, w in usable])[0]
                present = [i for i in ids if i in items]
                # customers do not always buy the whole bundle
                picked = [i for i in present if rng.random() < 0.85] or present[:2]
                if len(picked) < 2:
                    continue
                sold_at = day0 + timedelta(days=d, hours=rng.randint(4, 15), minutes=rng.randint(0, 59))
                if sold_at > now:
                    continue
                bid = f"demo-b{n_baskets}"
                n_baskets += 1
                for cid in picked:
                    p = items[cid]
                    sales_rows.append(dict(_id=nid("sales_history"), shop_id=s.id, product_id=p.id,
                                           catalog_item_id=cid, category_id=p.category_id, customer_id=None,
                                           basket_id=bid, quantity=1, unit_price=p.price,
                                           source=SaleSource.DEMO.value, is_demo=True, sold_at=sold_at))
    print(f"  {len(sales_rows)} demo sales, {n_baskets} multi-item baskets")

    # ------------------------------------------------------------ reservation / order history
    print("  generating reservations, orders and reviews...")
    events: list[dict] = []
    reservations: list[Reservation] = []
    orders: list[Order] = []
    reviews: list[Review] = []
    notifications: list[Notification] = []

    def sale(shop, p, customer, basket_id, quantity, source, at) -> None:
        sales_rows.append(SalesRecord(id=nid("sales_history"), shop_id=shop.id, product_id=p.id,
                                      catalog_item_id=p.catalog_item_id, category_id=p.category_id,
                                      customer_id=customer.id, basket_id=basket_id, quantity=quantity,
                                      unit_price=p.price, source=source, is_demo=True, sold_at=at).to_mongo())

    in_stock_by_shop: dict[int, list[Product]] = defaultdict(list)
    for p in products:
        if p.quantity > 0:
            in_stock_by_shop[p.shop_id].append(p)

    def ev(entity, eid, shop_id, frm, to, role, actor, at, note=None):
        events.append(dict(_id=nid("status_events"), entity=entity, entity_id=eid, shop_id=shop_id, from_status=frm, to_status=to,
                           actor_role=role, actor_id=actor, note=note, created_at=at))

    def add_review(customer, shop, product_id, at, reservation_id=None, order_id=None):
        q = shop_profile[shop.id]["quality"]
        rating = int(min(5, max(1, round(rng.gauss(q, 0.7)))))
        reviews.append(Review(id=nid("reviews"), customer_id=customer.id, shop_id=shop.id, product_id=product_id,
                              reservation_id=reservation_id, order_id=order_id, rating=rating,
                              accuracy_rating=int(min(5, max(1, round(rng.gauss(q + 0.1, 0.6))))),
                              delivery_rating=int(min(5, max(1, round(rng.gauss(q, 0.7))))) if order_id else None,
                              comment=rng.choice(REVIEW_COMMENTS[rating]) if rng.random() < 0.75 else None,
                              created_at=at + timedelta(hours=rng.randint(1, 30))))
        # Computed pattern: the shop carries its own rating totals.
        shop.rating_sum += rating
        shop.rating_count += 1

    for s in shops:
        prof = shop_profile[s.id]
        stock = in_stock_by_shop[s.id]
        if not stock:
            continue
        n_res = int(rng.uniform(12, 45) * prof["popularity"])
        for _ in range(n_res):
            cust = rng.choice(customers[1:])
            p = rng.choice(stock)
            created = now - timedelta(days=rng.uniform(0.5, HISTORY_DAYS), minutes=rng.randint(0, 600))
            qty = 1 if rng.random() < 0.85 else 2
            r = Reservation(id=nid("reservations"), code=short_code("R"), customer_id=cust.id, shop_id=s.id,
                            product_id=p.id, quantity=qty,
                            unit_price=p.price, status=RS.REQUESTED, hold_minutes=s.hold_minutes,
                            expires_at=created + timedelta(minutes=settings.request_response_minutes),
                            created_at=created, updated_at=created)
            reservations.append(r)
            ev("reservation", r.id, s.id, None, "REQUESTED", "customer", cust.id, created)
            roll = rng.random()
            if roll > prof["responsiveness"]:
                if rng.random() < 0.5:
                    r.status, r.closed_at = RS.REJECTED, created + timedelta(minutes=rng.randint(2, 15))
                    r.close_reason = rng.choice(["Last piece was sold at the counter", "Item damaged, sorry"])
                    ev("reservation", r.id, s.id, "REQUESTED", "REJECTED", "owner", s.owner_id, r.closed_at,
                       r.close_reason)
                else:
                    r.status, r.closed_at = RS.EXPIRED, r.expires_at
                    ev("reservation", r.id, s.id, "REQUESTED", "EXPIRED", "system", None, r.expires_at)
                r.updated_at = r.closed_at
                continue
            conf = created + timedelta(minutes=max(1, rng.lognormvariate(math.log(prof["response_median"]), 0.6)))
            conf = min(conf, r.expires_at - timedelta(minutes=1))
            r.confirmed_at, r.expires_at = conf, conf + timedelta(minutes=s.hold_minutes)
            ev("reservation", r.id, s.id, "REQUESTED", "CONFIRMED", "owner", s.owner_id, conf)
            outcome = rng.random()
            if outcome < 0.06:
                r.status, r.closed_at = RS.CANCELLED, conf + timedelta(minutes=rng.randint(3, 20))
                r.close_reason = "Found it closer to home"
                ev("reservation", r.id, s.id, "CONFIRMED", "CANCELLED", "customer", cust.id, r.closed_at)
            elif outcome < 0.11:
                r.status, r.closed_at = RS.EXPIRED, r.expires_at
                ev("reservation", r.id, s.id, "CONFIRMED", "EXPIRED", "system", None, r.expires_at)
            else:
                ready = conf + timedelta(minutes=rng.randint(2, 10))
                done = ready + timedelta(minutes=rng.randint(5, max(6, s.hold_minutes - 2)))
                r.ready_at, r.completed_at, r.status = ready, done, RS.COMPLETED
                ev("reservation", r.id, s.id, "CONFIRMED", "READY_FOR_PICKUP", "owner", s.owner_id, ready)
                ev("reservation", r.id, s.id, "READY_FOR_PICKUP", "COMPLETED", "owner", s.owner_id, done)
                sale(s, p, cust, r.code, qty, SaleSource.RESERVATION, done)
                if rng.random() < 0.5:
                    add_review(cust, s, p.id, done, reservation_id=r.id)
            r.updated_at = r.closed_at or r.completed_at or r.confirmed_at

        if s.offers_delivery:
            for _ in range(int(rng.uniform(5, 18) * prof["popularity"])):
                cust = rng.choice(customers[1:])
                picks = rng.sample(stock, k=min(len(stock), rng.choice([1, 1, 2, 3])))
                created = now - timedelta(days=rng.uniform(0.5, HISTORY_DAYS), minutes=rng.randint(0, 600))
                ang, dist = rng.uniform(0, 2 * math.pi), rng.uniform(0.4, max(0.5, s.delivery_radius_km * 0.9))
                dlat = s.lat + (dist / 111) * math.cos(ang)
                dlng = s.lng + (dist / (111 * math.cos(math.radians(s.lat)))) * math.sin(ang)
                subtotal = round(sum(p.price for p in picks), 2)
                fee = 0.0 if s.free_delivery_above and subtotal >= s.free_delivery_above else s.delivery_fee
                o = Order(id=nid("orders"), code=short_code("D"), customer_id=cust.id, shop_id=s.id, status=OS.PENDING,
                          delivery_address=f"{rng.randint(1, 900)}, {rng.choice(localities)['name']}, {city['name']}",
                          delivery_lat=dlat, delivery_lng=dlng, contact_phone=cust.phone or "9876500000",
                          distance_km=round(haversine_km(s.lat, s.lng, dlat, dlng), 2), subtotal=subtotal,
                          delivery_fee=fee, total=subtotal + fee, created_at=created, updated_at=created,
                          items=[OrderItem(product_id=p.id, name=p.name, unit_price=p.price, quantity=1)
                                 for p in picks])
                orders.append(o)
                ev("order", o.id, s.id, None, "PENDING", "customer", cust.id, created)
                t = created + timedelta(minutes=rng.randint(3, 20))
                if rng.random() < 0.06:
                    o.status, o.closed_at, o.close_reason = OS.CANCELLED, t, "Out of delivery range today"
                    ev("order", o.id, s.id, "PENDING", "CANCELLED", "owner", s.owner_id, t, o.close_reason)
                    o.updated_at = t
                    continue
                chain = [("PENDING", "SHOP_CONFIRMED"), ("SHOP_CONFIRMED", "PREPARING"),
                         ("PREPARING", "OUT_FOR_DELIVERY")]
                for frm, to in chain:
                    ev("order", o.id, s.id, frm, to, "owner", s.owner_id, t)
                    t += timedelta(minutes=rng.randint(5, 25))
                if rng.random() < 0.04:
                    o.status = OS.RETURNED_TO_SHOP
                    ev("order", o.id, s.id, "OUT_FOR_DELIVERY", "DELIVERY_FAILED", "owner", s.owner_id, t,
                       "Customer not reachable")
                    ev("order", o.id, s.id, "DELIVERY_FAILED", "RETURNED_TO_SHOP", "owner", s.owner_id,
                       t + timedelta(minutes=30))
                    o.closed_at, o.close_reason = t + timedelta(minutes=30), "Customer not reachable"
                else:
                    o.status, o.delivered_at, o.payment_status = OS.DELIVERED, t, "paid"
                    ev("order", o.id, s.id, "OUT_FOR_DELIVERY", "DELIVERED", "owner", s.owner_id, t)
                    for p in picks:
                        sale(s, p, cust, o.code, 1, SaleSource.ORDER, t)
                    if rng.random() < 0.45:
                        add_review(cust, s, picks[0].id, t, order_id=o.id)
                o.updated_at = o.closed_at or o.delivered_at

    # ------------------------------------------------------------ Priya's personal history
    featured = next(s for s in shops if s.owner.email == "owner@nearshop.demo")
    near = sorted(shops, key=lambda s: haversine_km(priya.home_lat, priya.home_lng, s.lat, s.lng))[:5]
    for i, s in enumerate(near[:4]):
        stock = in_stock_by_shop[s.id]
        if not stock:
            continue
        p = rng.choice(stock)
        created = now - timedelta(days=3 + i * 6, hours=rng.randint(1, 8))
        conf = created + timedelta(minutes=5)
        done = conf + timedelta(minutes=18)
        r = Reservation(id=nid("reservations"), code=short_code("R"), customer_id=priya.id, shop_id=s.id, product_id=p.id, quantity=1,
                        unit_price=p.price, status=RS.COMPLETED, hold_minutes=s.hold_minutes,
                        expires_at=conf + timedelta(minutes=s.hold_minutes), confirmed_at=conf,
                        ready_at=conf + timedelta(minutes=6), completed_at=done, created_at=created, updated_at=done)
        reservations.append(r)
        for frm, to, at, role in [(None, "REQUESTED", created, "customer"), ("REQUESTED", "CONFIRMED", conf, "owner"),
                                  ("CONFIRMED", "READY_FOR_PICKUP", r.ready_at, "owner"),
                                  ("READY_FOR_PICKUP", "COMPLETED", done, "owner")]:
            ev("reservation", r.id, s.id, frm, to, role, priya.id if role == "customer" else s.owner_id, at)
        sale(s, p, priya, r.code, 1, SaleSource.RESERVATION, done)
        if i > 0:  # leave the most recent one unreviewed so the "rate your pickup" prompt shows
            add_review(priya, s, p.id, done, reservation_id=r.id)

    # A live request waiting at the featured shop, so the owner dashboard has something to act on.
    fstock = sorted(in_stock_by_shop[featured.id], key=lambda p: -p.quantity)
    for cust, p, mins in [(customers[5], fstock[0], 3), (customers[9], fstock[3], 7)]:
        created = now - timedelta(minutes=mins)
        r = Reservation(id=nid("reservations"), code=short_code("R"), customer_id=cust.id, shop_id=featured.id, product_id=p.id, quantity=1,
                        unit_price=p.price, status=RS.REQUESTED, hold_minutes=featured.hold_minutes,
                        expires_at=created + timedelta(minutes=settings.request_response_minutes),
                        created_at=created, updated_at=created)
        reservations.append(r)
        ev("reservation", r.id, featured.id, None, "REQUESTED", "customer", cust.id, created)
        notifications.append(Notification(
            id=nid("notifications"), user_id=featured.owner_id, kind="reservation_new",
            title=f"New reservation {r.code}", body=f"{cust.name} wants 1 x {p.name}.",
            link="/shop/reservations", created_at=created))
    notifications.append(Notification(
        id=nid("notifications"), user_id=priya.id, kind="welcome", title="Welcome to NearShop",
        body="Search for anything and see which shops near you have it in stock right now.",
        link="/search", created_at=now - timedelta(days=30)))

    # ------------------------------------------------------------ search history
    queries: list[str] = []
    for ci in catalog.values():
        queries += [t for t in (ci.tags or [])[:4]]
        queries.append(ci.name.split(" ")[0].lower() + " " + (ci.subcategory or "").replace("-", " "))
    search_rows = []
    for _ in range(4000):
        loc = rng.choice(localities)
        roll = rng.random()
        if roll < 0.05:
            q, n = rng.choice(ZERO_RESULT_QUERIES), 0
        elif roll < 0.09:
            q, n = rng.choice(list(MISSPELLINGS.values())), rng.randint(2, 12)
        else:
            q, n = rng.choice(queries).strip().lower(), rng.randint(3, 40)
        cust = rng.choice(customers) if rng.random() < 0.6 else None
        search_rows.append(SearchEvent(
            id=nid("search_history"), user_id=cust.id if cust else None, query=q, normalized_query=q,
            results_count=n, lat=round(loc["lat"] + rng.uniform(-0.01, 0.01), 3),
            lng=round(loc["lng"] + rng.uniform(-0.01, 0.01), 3), created_at=now - timedelta(days=rng.uniform(0, 30))))
    for q in ["phone charger", "usb c cable", "umbrella", "led bulb 9w", "engine oil"]:
        search_rows.append(SearchEvent(
            id=nid("search_history"), user_id=priya.id, query=q, normalized_query=q, results_count=12,
            lat=round(priya.home_lat, 3), lng=round(priya.home_lng, 3),
            created_at=now - timedelta(days=rng.uniform(0, 6))))
    print(f"  {len(reservations)} reservations, {len(orders)} orders, {len(events)} status events, "
          f"{len(reviews)} reviews, {len(search_rows)} searches")

    # ------------------------------------------------------------ write everything to MongoDB
    print("  writing to MongoDB...")
    for collection, docs in [
        (db.categories, list(cats.values())), (db.catalog_items, list(catalog.values())), (db.users, users),
        (db.shops, shops), (db.products, products), (db.inventory_events, inv_rows),
        (db.reservations, reservations), (db.orders, orders), (db.status_events, events), (db.reviews, reviews),
        (db.notifications, notifications), (db.search_history, search_rows), (db.sales_history, sales_rows),
    ]:
        bulk_insert(collection, docs)
        print(f"    {collection.name}: {len(docs)}")
    nid.save_counters(db)

    # ------------------------------------------------------------ train AI
    print("  training AI models (first run downloads the embedding model)...")
    results = train_all(db)
    print(json.dumps({k: v for k, v in results.items() if k != "demand"}, indent=1, default=str)[:1500])
    print(f"  demand: {results.get('demand')}")
    print(f"Done in {time.time() - started:.0f}s. Demo password: set by NEARSHOP_DEMO_PASSWORD (see .env.example)")


if __name__ == "__main__":
    main()
