"""Word2Vec reference model (academic baseline from the original NearShop concept).

Trained on the product corpus itself (names, brands, tags, descriptions). It learns which
words co-occur, then expands a query with nearby words before keyword search. It is shown
side by side with the sentence-embedding search in the AI Lab so the two can be compared.
"""
from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # gensim is imported on use: it stays out of the API's serving memory
    from gensim.models import Word2Vec

from app.core.config import settings
from app.core.database import Database

MODEL_PATH = settings.model_dir / "word2vec.model"
_model: Word2Vec | None = None
_lock = threading.Lock()


def _corpus(db: Database) -> list[list[str]]:
    from gensim.utils import simple_preprocess

    sentences: list[list[str]] = []
    for c in db.catalog_items.find():
        base = simple_preprocess(f"{c.name} {c.brand or ''} {c.subcategory or ''}")
        tags = [simple_preprocess(t) for t in (c.tags or [])]
        sentences.append(base + [w for t in tags for w in t])
        for t in tags:  # each tag phrase next to the product words, so synonyms land close together
            sentences.append(t + base[:4])
        if c.description:
            sentences.append(simple_preprocess(c.description))
    for p in db.products.find_raw({"catalog_item_id": None}, {"name": 1, "keywords": 1}):
        sentences.append(simple_preprocess(f"{p['name']} {p.get('keywords') or ''}"))
    return [s for s in sentences if len(s) > 1]


def train(db: Database) -> dict:
    from gensim.models import Word2Vec

    global _model
    started = time.time()
    sentences = _corpus(db)
    model = Word2Vec(sentences=sentences, vector_size=96, window=6, min_count=1, sg=1, epochs=60, workers=2, seed=7)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(MODEL_PATH))
    with _lock:
        _model = model
    return {
        "sentences": len(sentences),
        "vocabulary": len(model.wv),
        "duration_ms": int((time.time() - started) * 1000),
    }


def _load() -> Word2Vec | None:
    global _model
    if _model is None and MODEL_PATH.exists():
        from gensim.models import Word2Vec

        with _lock:
            if _model is None:
                _model = Word2Vec.load(str(MODEL_PATH))
    return _model


def expand(query: str, topn: int = 4, min_sim: float = 0.55) -> list[str]:
    model = _load()
    if model is None:  # not trained on this machine yet: plain words, and gensim is never loaded
        return query.lower().split()
    from gensim.utils import simple_preprocess

    tokens = simple_preprocess(query)
    out = list(tokens)
    for tok in tokens:
        if tok in model.wv:
            out += [w for w, s in model.wv.most_similar(tok, topn=topn) if s >= min_sim]
    return list(dict.fromkeys(out))
