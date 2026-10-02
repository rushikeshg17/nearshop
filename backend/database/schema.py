"""MongoDB schema for NearShop: collections, validation rules and indexes.

    uv run python -m database.schema          # create / update collections and indexes (idempotent)

MongoDB does not need migrations to add a field, but the rules that keep data correct still
live in the database, not only in application code:

  * `$jsonSchema` validators reject documents with missing fields, wrong types, unknown enum
    values, negative stock or prices, and out-of-range coordinates or ratings.
  * unique indexes enforce one account per email, one listing per (shop, catalog item) and one
    review per purchase.
  * every query the app runs is backed by an index declared here.

How the relational model maps to documents
------------------------------------------
  shop_categories (join table)   -> `shops.category_ids` array (multikey index)
  order_items (child table)      -> `orders.items` embedded array (an order is one document)
  shops.lat / shops.lng          -> `shops.location` GeoJSON point (2dsphere index)
  products_fts (FTS5 table)      -> weighted text index on `products`
  search_history.lat / lng       -> `search_history.location` GeoJSON point (2dsphere index)
  text_embeddings (model, hash)  -> `text_embeddings._id` = "<model>:<sha256>"
  autoincrement primary keys     -> integer `_id` issued from the `counters` collection
  AVG(rating) per shop           -> `shops.rating_sum` / `rating_count`, updated with each review

Everything else stays a reference by id (products -> shops, reservations -> products, ...):
those documents are read on their own, change independently and grow without bound, which is
exactly when embedding is the wrong choice.
"""
from __future__ import annotations

import logging

from pymongo import ASCENDING, DESCENDING, GEOSPHERE, TEXT, IndexModel
from pymongo.database import Database as MongoDatabase
from pymongo.errors import OperationFailure

from app.models.enums import (
    AnomalyStatus,
    InventoryReason,
    OrderStatus,
    ReservationStatus,
    Role,
    SaleSource,
)

log = logging.getLogger(__name__)

INT = ["int", "long"]
INT_N = ["int", "long", "null"]
NUM = ["int", "long", "double", "decimal"]
NUM_N = [*NUM, "null"]
STR = "string"
STR_N = ["string", "null"]
DATE = "date"
DATE_N = ["date", "null"]
BOOL = "bool"


def enum(e) -> dict:
    return {"enum": [m.value for m in e]}


def schema(required: list[str], **properties: dict | str | list) -> dict:
    props = {k: (v if isinstance(v, dict) else {"bsonType": v}) for k, v in properties.items()}
    return {"$jsonSchema": {"bsonType": "object", "required": ["_id", *required], "properties": {
        "_id": {"bsonType": INT}, **props}}}


POINT = {
    "bsonType": "object",
    "required": ["type", "coordinates"],
    "properties": {
        "type": {"enum": ["Point"]},
        "coordinates": {
            "bsonType": "array", "minItems": 2, "maxItems": 2,
            "items": [{"bsonType": NUM, "minimum": -180, "maximum": 180},  # longitude
                      {"bsonType": NUM, "minimum": -90, "maximum": 90}],  # latitude
        },
    },
}
RATING = {"bsonType": INT, "minimum": 1, "maximum": 5}
RATING_N = {"oneOf": [{"bsonType": "null"}, RATING]}
POSITIVE_INT = {"bsonType": INT, "minimum": 1}
NON_NEGATIVE = {"bsonType": NUM, "minimum": 0}

VALIDATORS: dict[str, dict] = {
    "users": schema(
        ["name", "email", "password_hash", "role", "is_active", "created_at", "updated_at"],
        name=STR, email={"bsonType": STR, "pattern": "^[^@\\s]+@[^@\\s]+$"}, phone=STR_N, password_hash=STR,
        role=enum(Role), is_active=BOOL, last_login_at=DATE_N, home_lat=NUM_N, home_lng=NUM_N, home_label=STR_N,
        created_at=DATE, updated_at=DATE,
    ),
    "categories": schema(["slug", "name", "icon", "sort_order"], slug=STR, name=STR, icon=STR, sort_order=INT),
    "catalog_items": schema(
        ["slug", "name", "category_id", "specs", "tags"],
        slug=STR, name=STR, brand=STR_N, category_id=INT, subcategory=STR_N, mrp=NUM_N, typical_price=NUM_N,
        specs="object", tags={"bsonType": "array", "items": {"bsonType": STR}},
    ),
    "shops": schema(
        ["owner_id", "name", "slug", "address_line", "city", "location", "offers_pickup", "offers_delivery",
         "delivery_radius_km", "delivery_fee", "hold_minutes", "is_active", "is_verified", "category_ids",
         "created_at", "updated_at"],
        owner_id=INT, name=STR, slug=STR, address_line=STR, city=STR, location=POINT, offers_pickup=BOOL,
        offers_delivery=BOOL, delivery_radius_km=NON_NEGATIVE, delivery_fee=NON_NEGATIVE,
        free_delivery_above={"oneOf": [{"bsonType": "null"}, NON_NEGATIVE]},
        hold_minutes=POSITIVE_INT, is_active=BOOL, is_verified=BOOL, inventory_updated_at=DATE_N,
        category_ids={"bsonType": "array", "items": {"bsonType": INT}},
        rating_sum={"bsonType": INT, "minimum": 0}, rating_count={"bsonType": INT, "minimum": 0},
        created_at=DATE, updated_at=DATE,
    ),
    "products": schema(
        ["shop_id", "category_id", "name", "keywords", "price", "quantity", "low_stock_threshold", "is_active",
         "stock_updated_at", "created_at", "updated_at"],
        shop_id=INT, catalog_item_id=INT_N, category_id=INT, name=STR, brand=STR_N, sku=STR_N, keywords=STR,
        specs="object", price=NON_NEGATIVE, mrp=NUM_N,
        quantity={"bsonType": INT, "minimum": 0},  # stock can never go negative, whatever the code does
        low_stock_threshold={"bsonType": INT, "minimum": 0}, is_active=BOOL, stock_updated_at=DATE,
        created_at=DATE, updated_at=DATE,
    ),
    "inventory_events": schema(
        ["product_id", "shop_id", "delta", "quantity_after", "reason", "created_at"],
        product_id=INT, shop_id=INT, delta=INT, quantity_after={"bsonType": INT, "minimum": 0},
        reason=enum(InventoryReason), actor_id=INT_N, created_at=DATE,
    ),
    "reservations": schema(
        ["code", "customer_id", "shop_id", "product_id", "quantity", "unit_price", "status", "hold_minutes",
         "expires_at", "stock_held", "created_at", "updated_at"],
        code=STR, customer_id=INT, shop_id=INT, product_id=INT, quantity=POSITIVE_INT, unit_price=NON_NEGATIVE,
        status=enum(ReservationStatus), hold_minutes=POSITIVE_INT, expires_at=DATE, stock_held=BOOL,
        confirmed_at=DATE_N, ready_at=DATE_N, completed_at=DATE_N, closed_at=DATE_N, close_reason=STR_N,
        created_at=DATE, updated_at=DATE,
    ),
    "orders": schema(
        ["code", "customer_id", "shop_id", "status", "payment_method", "payment_status", "delivery_address",
         "delivery_lat", "delivery_lng", "contact_phone", "distance_km", "subtotal", "delivery_fee", "total",
         "stock_held", "items", "created_at", "updated_at"],
        code=STR, customer_id=INT, shop_id=INT, status=enum(OrderStatus), payment_method=STR,
        payment_status={"enum": ["unpaid", "paid", "refunded"]}, delivery_address=STR,
        delivery_lat={"bsonType": NUM, "minimum": -90, "maximum": 90},
        delivery_lng={"bsonType": NUM, "minimum": -180, "maximum": 180},
        subtotal=NON_NEGATIVE, delivery_fee=NON_NEGATIVE, total=NON_NEGATIVE, stock_held=BOOL,
        items={
            "bsonType": "array", "minItems": 1,
            "items": {"bsonType": "object", "required": ["product_id", "name", "unit_price", "quantity"],
                      "properties": {"product_id": {"bsonType": INT}, "name": {"bsonType": STR},
                                     "unit_price": NON_NEGATIVE, "quantity": POSITIVE_INT}},
        },
        delivered_at=DATE_N, closed_at=DATE_N, created_at=DATE, updated_at=DATE,
    ),
    "status_events": schema(
        ["entity", "entity_id", "shop_id", "to_status", "actor_role", "created_at"],
        entity={"enum": ["reservation", "order"]}, entity_id=INT, shop_id=INT, from_status=STR_N, to_status=STR,
        actor_role={"enum": ["customer", "owner", "admin", "system"]}, actor_id=INT_N, created_at=DATE,
    ),
    "reviews": {"$jsonSchema": {
        **schema(
            ["customer_id", "shop_id", "reservation_id", "order_id", "rating", "created_at"],
            customer_id=INT, shop_id=INT, product_id=INT_N, rating=RATING, accuracy_rating=RATING_N,
            delivery_rating=RATING_N, comment=STR_N, created_at=DATE,
        )["$jsonSchema"],
        # A review belongs to exactly one purchase: a pickup reservation or a delivery order.
        "oneOf": [
            {"properties": {"reservation_id": {"bsonType": INT}, "order_id": {"bsonType": "null"}}},
            {"properties": {"reservation_id": {"bsonType": "null"}, "order_id": {"bsonType": INT}}},
        ],
    }},
    "notifications": schema(["user_id", "kind", "title", "created_at"],
                            user_id=INT, kind=STR, title=STR, read_at=DATE_N, created_at=DATE),
    "search_history": schema(
        ["query", "normalized_query", "results_count", "created_at"],
        user_id=INT_N, query=STR, normalized_query=STR, results_count={"bsonType": INT, "minimum": 0},
        location={"oneOf": [{"bsonType": "null"}, POINT]}, created_at=DATE,
    ),
    "sales_history": schema(
        ["shop_id", "product_id", "basket_id", "quantity", "unit_price", "source", "is_demo", "sold_at"],
        shop_id=INT, product_id=INT, catalog_item_id=INT_N, category_id=INT_N, customer_id=INT_N, basket_id=STR,
        quantity=POSITIVE_INT, unit_price=NON_NEGATIVE, source=enum(SaleSource), is_demo=BOOL, sold_at=DATE,
    ),
    "model_runs": schema(["name", "algorithm", "metrics", "created_at"],
                         name=STR, algorithm=STR, metrics="object", created_at=DATE),
    "recommendations": schema(
        ["antecedents", "consequents", "antecedent_key", "support", "confidence", "lift", "model_run_id"],
        antecedents={"bsonType": "array", "minItems": 1, "items": {"bsonType": INT}},
        consequents={"bsonType": "array", "minItems": 1, "items": {"bsonType": INT}},
        antecedent_key=STR, support=NUM, confidence=NUM, lift=NUM, model_run_id=INT,
    ),
    "demand_forecasts": schema(
        ["product_id", "shop_id", "predicted_7d", "daily_rate", "trend", "confidence", "model_run_id"],
        product_id=INT, shop_id=INT, predicted_7d=NON_NEGATIVE, daily_rate=NON_NEGATIVE,
        trend={"enum": ["rising", "steady", "falling"]}, confidence={"enum": ["low", "medium", "high"]},
        model_run_id=INT,
    ),
    "price_anomalies": schema(
        ["product_id", "shop_id", "catalog_item_id", "price", "reference_price", "deviation_pct", "score",
         "direction", "peer_count", "status", "model_run_id", "created_at"],
        product_id=INT, shop_id=INT, catalog_item_id=INT, price=NON_NEGATIVE, reference_price=NON_NEGATIVE,
        direction={"enum": ["high", "low"]}, status=enum(AnomalyStatus), reviewed_by=INT_N, reviewed_at=DATE_N,
        model_run_id=INT, created_at=DATE,
    ),
    # No validators: `counters` ({_id: collection name, seq}) and `text_embeddings` (binary vector cache).
    "counters": {},
    "text_embeddings": {},
}

A, D = ASCENDING, DESCENDING
IS_INT = {"$type": "number"}  # partial-index filter: "this optional reference is set"

INDEXES: dict[str, list[IndexModel]] = {
    "users": [
        IndexModel([("email", A)], unique=True, name="uq_email"),
        IndexModel([("role", A), ("created_at", D)], name="role_created"),
    ],
    "categories": [
        IndexModel([("slug", A)], unique=True, name="uq_slug"),
        IndexModel([("sort_order", A), ("name", A)], name="sort_order"),
    ],
    "catalog_items": [
        IndexModel([("slug", A)], unique=True, name="uq_slug"),
        IndexModel([("category_id", A), ("name", A)], name="category_name"),
    ],
    "shops": [
        IndexModel([("slug", A)], unique=True, name="uq_slug"),
        IndexModel([("owner_id", A)], name="owner"),
        IndexModel([("location", GEOSPHERE)], name="location_2dsphere"),
        IndexModel([("category_ids", A)], name="categories"),
    ],
    "products": [
        IndexModel([("shop_id", A), ("is_active", A), ("quantity", A)], name="shop_active_stock"),
        IndexModel([("shop_id", A), ("catalog_item_id", A)], unique=True, name="uq_shop_catalog_item",
                   partialFilterExpression={"catalog_item_id": IS_INT}),
        IndexModel([("catalog_item_id", A), ("is_active", A)], name="catalog_item_active"),
        IndexModel([("category_id", A), ("is_active", A)], name="category_active"),
        # Keyword half of hybrid search (replaces SQLite FTS5): weighted, stemmed text index.
        IndexModel([("name", TEXT), ("brand", TEXT), ("keywords", TEXT), ("description", TEXT)],
                   weights={"name": 10, "brand": 6, "keywords": 4, "description": 1},
                   default_language="english", name="text_search"),
    ],
    "inventory_events": [
        IndexModel([("shop_id", A), ("created_at", D)], name="shop_created"),
        IndexModel([("product_id", A), ("_id", D)], name="product_latest"),
        IndexModel([("created_at", D)], name="created"),
    ],
    "reservations": [
        IndexModel([("code", A)], unique=True, name="uq_code"),
        IndexModel([("shop_id", A), ("status", A), ("created_at", A)], name="shop_status_created"),
        IndexModel([("customer_id", A), ("status", A), ("created_at", D)], name="customer_status_created"),
        IndexModel([("status", A), ("expires_at", A)], name="status_expires"),  # the expiry sweep
        IndexModel([("product_id", A), ("status", A)], name="product_status"),
        # A customer can hold only one active reservation per listing, guaranteed by the database.
        IndexModel([("customer_id", A), ("product_id", A)], unique=True, name="uq_active_customer_product",
                   partialFilterExpression={"status": {"$in": ["REQUESTED", "CONFIRMED", "READY_FOR_PICKUP"]}}),
    ],
    "orders": [
        IndexModel([("code", A)], unique=True, name="uq_code"),
        IndexModel([("shop_id", A), ("status", A), ("created_at", A)], name="shop_status_created"),
        IndexModel([("customer_id", A), ("status", A), ("created_at", D)], name="customer_status_created"),
        IndexModel([("status", A), ("created_at", A)], name="status_created"),  # stale-pending sweep
    ],
    "status_events": [
        IndexModel([("entity", A), ("entity_id", A), ("created_at", A)], name="entity_timeline"),
        IndexModel([("shop_id", A), ("created_at", D)], name="shop_created"),
    ],
    "reviews": [
        IndexModel([("reservation_id", A)], unique=True, name="uq_reservation",
                   partialFilterExpression={"reservation_id": IS_INT}),
        IndexModel([("order_id", A)], unique=True, name="uq_order", partialFilterExpression={"order_id": IS_INT}),
        IndexModel([("shop_id", A), ("created_at", D)], name="shop_created"),
        IndexModel([("product_id", A), ("created_at", D)], name="product_created"),
        IndexModel([("customer_id", A)], name="customer"),
    ],
    "notifications": [
        IndexModel([("user_id", A), ("created_at", D)], name="user_created"),
        IndexModel([("user_id", A), ("read_at", A)], name="user_read"),
    ],
    "search_history": [
        IndexModel([("normalized_query", A), ("results_count", A)], name="query_results"),
        IndexModel([("created_at", D)], name="created"),
        IndexModel([("user_id", A), ("created_at", D)], name="user_created"),
        IndexModel([("location", GEOSPHERE)], name="location_2dsphere"),
    ],
    "sales_history": [
        IndexModel([("shop_id", A), ("sold_at", D)], name="shop_sold"),
        IndexModel([("product_id", A), ("sold_at", D)], name="product_sold"),
        IndexModel([("sold_at", D)], name="sold"),
        IndexModel([("customer_id", A), ("sold_at", D)], name="customer_sold",
                   partialFilterExpression={"customer_id": IS_INT}),
        IndexModel([("catalog_item_id", A)], name="catalog_item"),
    ],
    "model_runs": [IndexModel([("name", A), ("created_at", D)], name="name_created")],
    "recommendations": [IndexModel([("antecedent_key", A)], name="antecedent_key")],
    "demand_forecasts": [
        IndexModel([("product_id", A)], unique=True, name="uq_product"),
        IndexModel([("shop_id", A)], name="shop"),
    ],
    "price_anomalies": [
        IndexModel([("status", A), ("score", D)], name="status_score"),
        IndexModel([("shop_id", A), ("status", A)], name="shop_status"),
    ],
    "text_embeddings": [IndexModel([("model", A)], name="model")],
}


def ensure_schema(mongo: MongoDatabase) -> None:
    """Create missing collections, apply validators and build indexes. Safe to run repeatedly."""
    existing = set(mongo.list_collection_names())
    for name, validator in VALIDATORS.items():
        if name not in existing:
            mongo.create_collection(name, **({"validator": validator, "validationLevel": "strict",
                                              "validationAction": "error"} if validator else {}))
        elif validator:
            mongo.command("collMod", name, validator=validator, validationLevel="strict", validationAction="error")
        if name in INDEXES:
            try:
                mongo[name].create_indexes(INDEXES[name])
            except OperationFailure as exc:  # an index changed shape: rebuild that collection's indexes
                if exc.code not in (85, 86):  # IndexOptionsConflict / IndexKeySpecsConflict
                    raise
                mongo[name].drop_indexes()
                mongo[name].create_indexes(INDEXES[name])


def reset(mongo: MongoDatabase) -> None:
    """Drop every NearShop collection and recreate the empty schema (used by the seed script and tests)."""
    for name in VALIDATORS:
        mongo.drop_collection(name)
    ensure_schema(mongo)


if __name__ == "__main__":
    from app.core.config import settings
    from app.core.database import client

    logging.basicConfig(level=logging.INFO)
    ensure_schema(client[settings.mongodb_db])
    print(f"Schema ready in database '{settings.mongodb_db}': {len(VALIDATORS)} collections, "
          f"{sum(len(v) for v in INDEXES.values())} indexes")
