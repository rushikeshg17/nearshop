"""In-memory semantic index over active product listings.

Many shops list the same item, so vectors are cached per unique text (hash) in the
`text_embeddings` table and only new texts are embedded. With a few thousand listings a
NumPy matrix product is fast enough; OpenSearch/pgvector can replace this later.
"""
from __future__ import annotations

import hashlib
import threading
import time

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.embeddings import get_provider
from app.models import Product, TextEmbedding


def product_text(name: str, brand: str | None, keywords: str, description: str | None) -> str:
    parts = [name]
    if brand and brand.lower() not in name.lower():
        parts.append(brand)
    if keywords:
        parts.append(keywords)
    if description:
        parts.append(description[:240])
    return ". ".join(parts)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class SemanticIndex:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._dirty = True
        self.product_ids = np.zeros(0, dtype=np.int64)
        self.matrix = np.zeros((0, 1), dtype=np.float32)
        self.provider_name = ""
        self.built_at = 0.0

    def mark_dirty(self) -> None:
        self._dirty = True

    def ensure(self, db: Session) -> None:
        if self._dirty:
            with self._lock:
                if self._dirty:
                    self._build(db)

    def _build(self, db: Session) -> None:
        rows = db.execute(
            select(Product.id, Product.name, Product.brand, Product.keywords, Product.description).where(
                Product.is_active.is_(True)
            )
        ).all()
        texts = [product_text(r.name, r.brand, r.keywords, r.description) for r in rows]
        provider = get_provider(fallback_corpus=texts)
        hashes = [_hash(t) for t in texts]

        cached = {
            e.text_hash: np.frombuffer(e.vector, dtype=np.float32)
            for e in db.scalars(select(TextEmbedding).where(TextEmbedding.model == provider.name))
        }
        missing = {h: t for h, t in zip(hashes, texts) if h not in cached}
        if missing:
            keys = list(missing)
            vecs = provider.embed([missing[k] for k in keys])
            for k, v in zip(keys, vecs):
                cached[k] = v
                db.merge(TextEmbedding(text_hash=k, model=provider.name, dim=provider.dim, vector=v.tobytes()))
            db.commit()

        self.product_ids = np.array([r.id for r in rows], dtype=np.int64)
        self.matrix = (
            np.vstack([cached[h] for h in hashes]) if hashes else np.zeros((0, provider.dim), dtype=np.float32)
        )
        self.provider_name = provider.name
        self.built_at = time.time()
        self._dirty = False

    def query(self, db: Session, text: str) -> dict[int, float]:
        """Cosine similarity of `text` against every active listing: {product_id: score}."""
        self.ensure(db)
        if len(self.product_ids) == 0:
            return {}
        q = get_provider().embed([text])[0]
        scores = self.matrix @ q
        return dict(zip(self.product_ids.tolist(), scores.tolist()))


index = SemanticIndex()
