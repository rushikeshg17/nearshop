"""MongoDB connection, a request-scoped database handle, and transactions.

`Database` is what routes and services receive as `db`. It exposes one typed `Collection`
per MongoDB collection (`db.products.get(7)` returns a `Product`). Inside `db.transaction(...)`
(or a function decorated with `@transactional`) every call made through the handle joins the
same multi-document transaction, so services never pass a session around by hand.

Ids are integers issued from the `counters` collection. They stay stable in URLs, JWTs and
the public API, and remain readable at a shop counter ("order 512").
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from functools import wraps
from typing import Any

from pydantic import BaseModel
from pymongo import MongoClient, ReturnDocument
from pymongo.client_session import ClientSession
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from app.core.config import settings

client: MongoClient = MongoClient(
    settings.mongodb_uri,
    appname="nearshop-api",
    serverSelectionTimeoutMS=15000,
    retryWrites=True,
    tz_aware=False,  # everything is stored and handled as naive UTC
    connect=False,  # resolve and connect on first use, so a slow DNS lookup cannot stop the API from starting
)

log = logging.getLogger(__name__)

# Independent read queries of one request run side by side: with a hosted cluster the network
# round trip, not the query, is what a page waits for.
_POOL_PREFIX = "mongo-io"
_pool = ThreadPoolExecutor(max_workers=24, thread_name_prefix=_POOL_PREFIX)



def utcnow() -> datetime:
    """Naive UTC timestamp, truncated to milliseconds (BSON date precision)."""
    now = datetime.now(UTC).replace(tzinfo=None)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


class Collection[T: BaseModel]:
    """A MongoDB collection that returns documents as models and joins the handle's transaction."""

    def __init__(self, db: Database, name: str, model: type[T]):
        self._db = db
        self.name = name
        self.model = model
        self.raw = db.mongo[name]

    @property
    def _s(self) -> ClientSession | None:
        return self._db.session

    # ---- reads
    def get(self, doc_id: Any) -> T | None:
        return self.find_one({"_id": doc_id}) if doc_id is not None else None

    def find_one(self, filter: dict | None = None, *, sort: list | None = None) -> T | None:
        doc = self.raw.find_one(filter or {}, sort=sort, session=self._s)
        return self.model.model_validate(doc) if doc else None

    def find(self, filter: dict | None = None, *, sort: list | None = None, skip: int = 0, limit: int = 0,
             projection: dict | None = None) -> list[T]:
        cursor = self.raw.find(filter or {}, projection, sort=sort, skip=skip, limit=limit, session=self._s)
        return [self.model.model_validate(d) for d in cursor]

    def find_raw(self, filter: dict | None = None, projection: dict | None = None, *, sort: list | None = None,
                 limit: int = 0) -> list[dict]:
        return list(self.raw.find(filter or {}, projection, sort=sort, limit=limit, session=self._s))

    def by_ids(self, ids: Iterable[Any]) -> dict[Any, T]:
        ids = list({i for i in ids if i is not None})
        return {d.id: d for d in self.find({"_id": {"$in": ids}})} if ids else {}

    def count(self, filter: dict | None = None) -> int:
        return self.raw.count_documents(filter or {}, session=self._s)

    def exists(self, filter: dict) -> bool:
        return self.raw.find_one(filter, {"_id": 1}, session=self._s) is not None

    def distinct(self, key: str, filter: dict | None = None) -> list:
        return self.raw.distinct(key, filter or {}, session=self._s)

    def aggregate(self, pipeline: list[dict]) -> list[dict]:
        return list(self.raw.aggregate(pipeline, session=self._s))

    # ---- writes
    def insert(self, doc: T) -> T:
        if not getattr(doc, "id", None):
            doc.id = self._db.next_id(self.name)
        self.raw.insert_one(doc.to_mongo(), session=self._s)
        return doc

    def insert_many(self, docs: list[T]) -> list[T]:
        if not docs:
            return docs
        missing = [d for d in docs if not getattr(d, "id", None)]
        for d, new_id in zip(missing, self._db.next_ids(self.name, len(missing))):
            d.id = new_id
        self.raw.insert_many([d.to_mongo() for d in docs], ordered=False, session=self._s)
        return docs

    def set(self, doc: T, **fields: Any) -> T:
        """Assign `fields` on the model and persist exactly those fields."""
        if "updated_at" in type(doc).model_fields:
            fields.setdefault("updated_at", utcnow())
        for key, value in fields.items():
            setattr(doc, key, value)
        self.raw.update_one({"_id": doc.id}, {"$set": type(doc).encode_fields(fields)}, session=self._s)
        return doc

    def update_one(self, filter: dict, update: dict, *, upsert: bool = False) -> int:
        return self.raw.update_one(filter, update, upsert=upsert, session=self._s).modified_count

    def update_many(self, filter: dict, update: dict) -> int:
        return self.raw.update_many(filter, update, session=self._s).modified_count

    def find_one_and_update(self, filter: dict, update: dict) -> T | None:
        doc = self.raw.find_one_and_update(filter, update, return_document=ReturnDocument.AFTER, session=self._s)
        return self.model.model_validate(doc) if doc else None

    def bulk_write(self, operations: list) -> None:
        if operations:
            self.raw.bulk_write(operations, ordered=False, session=self._s)

    def delete_many(self, filter: dict) -> int:
        return self.raw.delete_many(filter, session=self._s).deleted_count


class Database:
    """Request-scoped handle: typed collections plus the current transaction (if any)."""

    def __init__(self, name: str | None = None):
        from app import models as m  # local import: models import utcnow from this module

        self.mongo = client[name or settings.mongodb_db]
        self.session: ClientSession | None = None

        self.users: Collection[m.User] = Collection(self, "users", m.User)
        self.categories: Collection[m.Category] = Collection(self, "categories", m.Category)
        self.catalog_items: Collection[m.CatalogItem] = Collection(self, "catalog_items", m.CatalogItem)
        self.shops: Collection[m.Shop] = Collection(self, "shops", m.Shop)
        self.products: Collection[m.Product] = Collection(self, "products", m.Product)
        self.inventory_events: Collection[m.InventoryEvent] = Collection(self, "inventory_events", m.InventoryEvent)
        self.reservations: Collection[m.Reservation] = Collection(self, "reservations", m.Reservation)
        self.orders: Collection[m.Order] = Collection(self, "orders", m.Order)
        self.status_events: Collection[m.StatusEvent] = Collection(self, "status_events", m.StatusEvent)
        self.reviews: Collection[m.Review] = Collection(self, "reviews", m.Review)
        self.notifications: Collection[m.Notification] = Collection(self, "notifications", m.Notification)
        self.search_history: Collection[m.SearchEvent] = Collection(self, "search_history", m.SearchEvent)
        self.sales_history: Collection[m.SalesRecord] = Collection(self, "sales_history", m.SalesRecord)
        self.model_runs: Collection[m.ModelRun] = Collection(self, "model_runs", m.ModelRun)
        self.recommendations: Collection[m.AssociationRule] = Collection(self, "recommendations", m.AssociationRule)
        self.demand_forecasts: Collection[m.DemandForecast] = Collection(self, "demand_forecasts", m.DemandForecast)
        self.price_anomalies: Collection[m.PriceAnomaly] = Collection(self, "price_anomalies", m.PriceAnomaly)

    # ---- ids
    def next_ids(self, name: str, n: int) -> range:
        """Reserve `n` consecutive ids. Deliberately outside any transaction: a sequence must never
        make two unrelated transactions conflict, and a gap after an abort is harmless."""
        if n <= 0:
            return range(0)
        doc = self.mongo["counters"].find_one_and_update(
            {"_id": name}, {"$inc": {"seq": n}}, upsert=True, return_document=ReturnDocument.AFTER
        )
        return range(doc["seq"] - n + 1, doc["seq"] + 1)

    def next_id(self, name: str) -> int:
        return self.next_ids(name, 1)[0]

    # ---- concurrency
    def gather(self, *fns: Callable[[], Any]) -> list[Any]:
        """Run independent queries concurrently and return their results in order. Inside a
        transaction they run one after another (a session belongs to a single thread)."""
        nested = threading.current_thread().name.startswith(_POOL_PREFIX)  # never wait on our own pool
        if self.session is not None or len(fns) < 2 or nested:
            return [fn() for fn in fns]
        return [f.result() for f in [_pool.submit(fn) for fn in fns]]

    @staticmethod
    def background(fn: Callable[[], Any]) -> None:
        """Fire-and-forget write that must never slow down or fail a request (e.g. search logging)."""

        def run() -> None:
            try:
                fn()
            except Exception as exc:
                log.warning("background write failed: %s", exc)

        _pool.submit(run)

    # ---- transactions
    def transaction[R](self, fn: Callable[[], R]) -> R:
        """Run `fn` in a multi-document transaction (all-or-nothing). Re-entrant: a nested call joins
        the outer transaction. The driver retries `fn` on transient write conflicts, so `fn` must
        load the documents it changes itself instead of trusting objects read earlier."""
        if self.session is not None:
            return fn()
        with client.start_session() as session:
            self.session = session
            try:
                return session.with_transaction(
                    lambda _s: fn(),
                    read_concern=ReadConcern("snapshot"),
                    write_concern=WriteConcern("majority"),
                )
            finally:
                self.session = None


def transactional[R](fn: Callable[..., R]) -> Callable[..., R]:
    """Decorator for service functions whose first argument is the `Database` handle."""

    @wraps(fn)
    def wrapper(db: Database, *args: Any, **kwargs: Any) -> R:
        return db.transaction(lambda: fn(db, *args, **kwargs))

    return wrapper


def get_db() -> Iterator[Database]:
    yield Database()
