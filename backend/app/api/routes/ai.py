"""AI Lab: model cards, retraining, and a side-by-side comparison of search methods."""
import threading

from fastapi import APIRouter, Query

from app.ai import word2vec_ref
from app.ai.pipeline import train_all
from app.ai.semantic_index import index
from app.core.database import Database
from app.core.deps import DB, AdminUser
from app.models import ModelRun
from app.schemas.serializers import iso
from app.services.loaders import with_category
from app.services.meta import city_config
from app.services.search import SearchParams, keyword_scores, run_search
from app.utils.text import normalize_query

router = APIRouter(prefix="/ai", tags=["ai"])

_training = threading.Event()

MODEL_INFO = {
    "embeddings": {
        "title": "Semantic search",
        "purpose": "Understands what a search means, so 'phone charging adapter' finds 'Samsung 25W USB-C charger'.",
    },
    "word2vec": {
        "title": "Word2Vec (reference)",
        "purpose": "Academic baseline: expands a query with words that co-occur in the product catalogue.",
    },
    "demand": {
        "title": "Demand prediction",
        "purpose": "Predicts next-7-day sales per listing to suggest restock quantities before items run out.",
    },
    "recommendations": {
        "title": "Frequently bought together",
        "purpose": "Market-basket analysis over completed purchases to suggest bundles.",
    },
    "anomalies": {
        "title": "Price anomaly detection",
        "purpose": "Flags listings priced far from other shops selling the same item, for human review.",
    },
}


@router.get("/models")
def models(db: DB):
    runs = db.model_runs.find(sort=[("created_at", -1)], limit=200)
    latest: dict[str, ModelRun] = {}
    history: dict[str, list] = {}
    for r in runs:
        latest.setdefault(r.name, r)
        history.setdefault(r.name, []).append({"at": iso(r.created_at), "n_samples": r.n_samples,
                                               "duration_ms": r.duration_ms})
    return {
        "training": _training.is_set(),
        "models": [
            {"name": name, **info,
             "algorithm": latest[name].algorithm if name in latest else None,
             "trained_at": iso(latest[name].created_at) if name in latest else None,
             "n_samples": latest[name].n_samples if name in latest else 0,
             "metrics": latest[name].metrics if name in latest else {},
             "note": latest[name].data_note if name in latest else "Not trained yet",
             "uses_demo_data": latest[name].uses_demo_data if name in latest else False,
             "duration_ms": latest[name].duration_ms if name in latest else 0,
             "runs": history.get(name, [])[:5]}
            for name, info in MODEL_INFO.items()
        ],
    }


@router.post("/retrain")
def retrain(_: AdminUser):
    if _training.is_set():
        return {"started": False, "message": "Training is already running"}

    def job():
        _training.set()
        try:
            train_all(Database())
        finally:
            _training.clear()

    threading.Thread(target=job, daemon=True).start()
    return {"started": True}


@router.get("/search-compare")
def search_compare(db: DB, q: str = Query(..., min_length=2, max_length=120), limit: int = Query(6, ge=1, le=20)):
    """Same query through each method, over all listings (no location filter), top unique items."""
    norm = normalize_query(q)
    products = {p.id: p for p in with_category(
        db, db.products.find({"is_active": True}, projection={"description": 0, "specs": 0}))}

    def top_unique(scores: dict[int, float]) -> list[dict]:
        seen, out = set(), []
        for pid, score in sorted(scores.items(), key=lambda kv: -kv[1]):
            p = products.get(pid)
            if p is None:
                continue
            key = p.catalog_item_id or f"p{p.id}"
            if key in seen:
                continue
            seen.add(key)
            out.append({"name": p.name, "icon": p.icon, "category": p.category.slug, "score": round(score, 3)})
            if len(out) >= limit:
                break
        return out

    kw = keyword_scores(db, norm.split())
    w2v_terms = word2vec_ref.expand(norm)
    w2v = keyword_scores(db, w2v_terms)
    sem = {k: v for k, v in index.query(db, norm).items() if v > 0.25}

    center = city_config()["center"]
    res = run_search(db, SearchParams(q=q, lat=center["lat"], lng=center["lng"], radius_km=50, page_size=limit),
                     log=False)
    hybrid_groups = [{"name": g["name"], "icon": g["icon"], "category": g["category"], "score": g["relevance"]}
                     for g in res["groups"]]

    return {
        "query": q,
        "normalized": norm,
        "methods": [
            {"key": "keyword", "title": "Keyword only (BM25)", "note": "Exact words in the listing.",
             "results": top_unique(kw)},
            {"key": "word2vec", "title": "Word2Vec expansion", "note": f"Expanded to: {', '.join(w2v_terms)}",
             "results": top_unique(w2v)},
            {"key": "semantic", "title": "Sentence embeddings", "note": index.provider_name,
             "results": top_unique(sem)},
            {"key": "hybrid", "title": "NearShop hybrid", "note": "60% meaning + 40% keywords, used in the app.",
             "results": hybrid_groups},
        ],
    }
