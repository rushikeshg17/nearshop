"""NearShop search pipeline.

    query -> normalise + synonyms -> keyword (SQLite FTS5 / BM25) + semantic (sentence embeddings)
          -> location filter (bounding box + Haversine) -> availability / price / fulfilment filters
          -> hybrid relevance + proximity ranking -> group listings of the same item -> results

Results are grouped by catalog item so a customer sees "Samsung 25W charger: 4 shops nearby
from Rs 1,249" and can compare shops, instead of four near-identical cards.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, replace

from rapidfuzz import fuzz, process
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from app.ai.semantic_index import index
from app.models import CatalogItem, Category, Product, SearchEvent, Shop
from app.schemas.serializers import listing, shop_brief
from app.services.reliability import ratings_for
from app.utils.geo import bounding_box, haversine_km
from app.utils.text import expand_synonyms, fts_escape_terms, normalize_query

SEM_FLOOR, SEM_CEIL = 0.22, 0.62  # cosine range mapped to 0..1 for all-MiniLM-L6-v2
SEM_MIN_MATCH = 0.34  # a listing with no keyword hit needs at least this much meaning overlap
W_SEMANTIC, W_KEYWORD = 0.6, 0.4
RELATIVE_CUTOFF = 0.42  # drop results far weaker than the best one


@dataclass
class SearchParams:
    q: str = ""
    lat: float = 0.0
    lng: float = 0.0
    radius_km: float = 5.0
    category: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    in_stock_only: bool = False
    fulfillment: str | None = None  # pickup | delivery
    sort: str = "relevance"  # relevance | distance | price_asc | price_desc
    shop_id: int | None = None
    page: int = 1
    page_size: int = 20


def nearby_shops(db: Session, lat: float, lng: float, radius_km: float, fulfillment: str | None = None,
                 shop_id: int | None = None) -> dict[int, tuple[Shop, float]]:
    min_lat, max_lat, min_lng, max_lng = bounding_box(lat, lng, radius_km)
    stmt = (
        select(Shop)
        .options(selectinload(Shop.categories))
        .where(Shop.is_active.is_(True), Shop.lat.between(min_lat, max_lat), Shop.lng.between(min_lng, max_lng))
    )
    if shop_id:
        stmt = stmt.where(Shop.id == shop_id)
    out = {}
    for s in db.scalars(stmt):
        d = haversine_km(lat, lng, s.lat, s.lng)
        if d > radius_km:
            continue
        if fulfillment == "delivery" and not (s.offers_delivery and d <= s.delivery_radius_km):
            continue
        if fulfillment == "pickup" and not s.offers_pickup:
            continue
        out[s.id] = (s, d)
    return out


def keyword_scores(db: Session, terms: list[str]) -> dict[int, float]:
    """BM25 over name/brand/keywords/description (weights 10/6/4/1). Higher = better."""
    tokens = fts_escape_terms(terms)
    if not tokens:
        return {}
    # prefix-match the last typed word so "chargi" still finds "charger"
    tokens[-1] = tokens[-1] + "*"
    expr = " OR ".join(dict.fromkeys(tokens))
    rows = db.execute(
        text("SELECT rowid, bm25(products_fts, 10.0, 6.0, 4.0, 1.0) FROM products_fts WHERE products_fts MATCH :q"),
        {"q": expr},
    ).all()
    return {rid: -score for rid, score in rows}


def _norm_sem(sim: float) -> float:
    return min(max((sim - SEM_FLOOR) / (SEM_CEIL - SEM_FLOOR), 0.0), 1.0)


def run_search(db: Session, p: SearchParams, user_id: int | None = None, log: bool = True) -> dict:
    norm = normalize_query(p.q) if p.q else ""
    shops = nearby_shops(db, p.lat, p.lng, p.radius_km, p.fulfillment, p.shop_id)

    stmt = select(Product).options(selectinload(Product.category)).where(
        Product.is_active.is_(True), Product.shop_id.in_(list(shops) or [-1])
    )
    if p.category:
        stmt = stmt.join(Category, Product.category_id == Category.id).where(Category.slug == p.category)
    if p.min_price is not None:
        stmt = stmt.where(Product.price >= p.min_price)
    if p.max_price is not None:
        stmt = stmt.where(Product.price <= p.max_price)
    if p.in_stock_only:
        stmt = stmt.where(Product.quantity > 0)
    products = db.scalars(stmt).all()

    relevance: dict[int, float] = {}
    expanded: list[str] = []
    if norm:
        expanded = expand_synonyms(norm)
        kw = keyword_scores(db, norm.split() + expanded)
        sem = index.query(db, norm)
        kw_max = max((kw.get(pr.id, 0.0) for pr in products), default=0.0) or 1.0
        for pr in products:
            k = kw.get(pr.id, 0.0) / kw_max
            s = sem.get(pr.id, 0.0)
            if k <= 0 and s < SEM_MIN_MATCH:
                continue
            relevance[pr.id] = W_SEMANTIC * _norm_sem(s) + W_KEYWORD * k
        if relevance:
            best = max(relevance.values())
            relevance = {k: v for k, v in relevance.items() if v >= best * RELATIVE_CUTOFF}
        products = [pr for pr in products if pr.id in relevance]
    else:
        relevance = {pr.id: 1.0 for pr in products}

    ratings = ratings_for(db, list({pr.shop_id for pr in products}))
    shop_cache: dict[int, dict] = {}

    def shop_json(sid: int) -> dict:
        if sid not in shop_cache:
            s, d = shops[sid]
            shop_cache[sid] = shop_brief(s, d, ratings.get(sid))
        return shop_cache[sid]

    # Group listings of the same catalog item.
    groups: dict[str, list[Product]] = defaultdict(list)
    for pr in products:
        groups[f"c{pr.catalog_item_id}" if pr.catalog_item_id else f"p{pr.id}"].append(pr)

    group_rows = []
    category_counts: dict[str, int] = defaultdict(int)
    for key, items in groups.items():
        in_stock = [x for x in items if x.quantity > 0]
        pool = in_stock or items
        nearest = min(shops[x.shop_id][1] for x in pool)
        rel = max(relevance[x.id] for x in items)
        proximity = max(0.0, 1 - nearest / max(p.radius_km, 0.5))
        score = 0.75 * rel + 0.15 * proximity + (0.1 if in_stock else 0.0)
        if not in_stock:
            score *= 0.6
        prices = [x.price for x in pool]
        # Best offer: in stock, balancing price and distance.
        lo, hi = min(prices), max(prices)
        best = min(
            pool,
            key=lambda x: ((x.price - lo) / (hi - lo) if hi > lo else 0) + shops[x.shop_id][1] / max(p.radius_km, 1),
        )
        offers = sorted(items, key=lambda x: (x.quantity <= 0, shops[x.shop_id][1]))
        head = best
        category_counts[head.category.slug] += 1
        group_rows.append(
            {
                "key": key,
                "catalog_item_id": head.catalog_item_id,
                "name": head.name,
                "brand": head.brand,
                "unit": head.unit,
                "icon": head.icon,
                "image_url": next((listing(x)["image_url"] for x in items if x.image_path), None),
                "category": head.category.slug,
                "min_price": min(x.price for x in pool),
                "max_price": max(x.price for x in pool),
                "mrp": head.mrp,
                "nearest_km": round(nearest, 2),
                "shop_count": len(items),
                "in_stock_count": len(in_stock),
                "relevance": round(rel, 3),
                "score": round(score, 4),
                "best_offer": listing(best, shop_json(best.shop_id)),
                "offers": [listing(x, shop_json(x.shop_id)) for x in offers[:6]],
            }
        )

    sorters = {
        "relevance": lambda g: -g["score"],
        "distance": lambda g: (g["in_stock_count"] == 0, g["nearest_km"]),
        "price_asc": lambda g: (g["in_stock_count"] == 0, g["min_price"]),
        "price_desc": lambda g: (g["in_stock_count"] == 0, -g["min_price"]),
    }
    if not norm and p.sort == "relevance":
        # Browsing without a query: in-stock items near you first.
        group_rows.sort(key=lambda g: (g["in_stock_count"] == 0, g["nearest_km"], -g["shop_count"]))
    else:
        group_rows.sort(key=sorters.get(p.sort, sorters["relevance"]))

    total = len(group_rows)
    start = (max(p.page, 1) - 1) * p.page_size
    page_rows = group_rows[start : start + p.page_size]

    # Map pins: every shop with at least one matching listing.
    pins: dict[int, dict] = {}
    for pr in products:
        pin = pins.setdefault(pr.shop_id, {**shop_json(pr.shop_id), "match_count": 0, "in_stock_count": 0,
                                           "min_price": None})
        pin["match_count"] += 1
        if pr.quantity > 0:
            pin["in_stock_count"] += 1
            pin["min_price"] = pr.price if pin["min_price"] is None else min(pin["min_price"], pr.price)

    did_you_mean = suggest_correction(db, norm) if norm and total < 3 else None

    # Nothing found but the query looks misspelled: show results for the correction instead of an empty page.
    if total == 0 and did_you_mean:
        corrected = run_search(db, replace(p, q=did_you_mean), user_id=user_id, log=log)
        if corrected["total"]:
            return {**corrected, "query": p.q, "corrected_from": p.q, "did_you_mean": None}

    if log and norm:
        db.add(SearchEvent(user_id=user_id, query=p.q[:200], normalized_query=norm[:200], category_slug=p.category,
                           results_count=total, lat=round(p.lat, 3), lng=round(p.lng, 3)))
        db.commit()

    return {
        "query": p.q,
        "normalized_query": norm,
        "expanded_terms": expanded,
        "did_you_mean": did_you_mean,
        "corrected_from": None,
        "total": total,
        "page": p.page,
        "page_size": p.page_size,
        "has_more": start + p.page_size < total,
        "shops_in_radius": len(shops),
        "groups": page_rows,
        "shops": sorted(pins.values(), key=lambda s: s["distance_km"]),
        "category_counts": dict(category_counts),
        "engine": {"semantic": index.provider_name or "loading", "keyword": "sqlite-fts5-bm25"},
    }


# ---------------------------------------------------------------- "did you mean"

_vocab: set[str] = set()


def _vocabulary(db: Session) -> set[str]:
    global _vocab
    if not _vocab:
        words: set[str] = set()
        for name, brand, tags in db.execute(select(CatalogItem.name, CatalogItem.brand, CatalogItem.tags)):
            for chunk in [name, brand or "", *(tags or [])]:
                words.update(w for w in re.findall(r"[a-z]{3,}", chunk.lower()))
        for (name,) in db.execute(select(Category.name)):
            words.update(re.findall(r"[a-z]{3,}", name.lower()))
        _vocab = words
    return _vocab


def suggest_correction(db: Session, norm: str) -> str | None:
    vocab = _vocabulary(db)
    if not vocab:
        return None
    changed = False
    out = []
    for word in norm.split():
        if len(word) < 4 or word in vocab or not word.isalpha():
            out.append(word)
            continue
        match = process.extractOne(word, vocab, scorer=fuzz.ratio, score_cutoff=78)
        if match:
            out.append(match[0])
            changed = True
        else:
            out.append(word)
    return " ".join(out) if changed else None


# ---------------------------------------------------------------- suggestions

def suggestions(db: Session, q: str, limit: int = 8) -> dict:
    norm = normalize_query(q)
    if len(norm) < 2:
        return {"queries": [], "items": [], "categories": []}
    like = f"%{norm}%"
    queries = [
        r[0]
        for r in db.execute(
            select(SearchEvent.normalized_query, func.count().label("n"))
            .where(SearchEvent.normalized_query.like(f"{norm}%"), SearchEvent.results_count > 0)
            .group_by(SearchEvent.normalized_query)
            .order_by(text("n DESC"))
            .limit(4)
        )
    ]
    items = db.execute(
        select(CatalogItem.id, CatalogItem.name, CatalogItem.brand, CatalogItem.icon, Category.slug)
        .join(Category, CatalogItem.category_id == Category.id)
        .where((CatalogItem.name.ilike(like)) | (CatalogItem.brand.ilike(f"{norm}%")))
        .limit(limit)
    ).all()
    cats = db.execute(select(Category).where(Category.name.ilike(like))).scalars().all()
    return {
        "queries": queries,
        "items": [{"id": i.id, "name": i.name, "brand": i.brand, "icon": i.icon, "category": i.slug} for i in items],
        "categories": [{"slug": c.slug, "name": c.name, "icon": c.icon} for c in cats],
    }


def popular_searches(db: Session, limit: int = 8) -> list[str]:
    rows = db.execute(
        select(SearchEvent.normalized_query, func.count().label("n"))
        .where(SearchEvent.results_count > 0)
        .group_by(SearchEvent.normalized_query)
        .order_by(text("n DESC"))
        .limit(limit)
    ).all()
    return [r[0] for r in rows]


def recent_searches(db: Session, user_id: int, limit: int = 6) -> list[str]:
    rows = db.execute(
        select(SearchEvent.normalized_query, func.max(SearchEvent.created_at).label("t"))
        .where(SearchEvent.user_id == user_id)
        .group_by(SearchEvent.normalized_query)
        .order_by(text("t DESC"))
        .limit(limit)
    ).all()
    return [r[0] for r in rows]


def reset_vocabulary() -> None:
    global _vocab
    _vocab = set()

