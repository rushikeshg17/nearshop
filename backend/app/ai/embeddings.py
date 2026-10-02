"""Sentence-embedding providers behind one small interface.

The rest of the app only calls `get_provider().embed(texts)`, so the model can be swapped
(Sentence Transformers via fastembed/ONNX today; OpenAI, BGE, or a PyTorch model later)
without touching search code.
"""
from __future__ import annotations

import logging
import threading
from typing import Protocol

import numpy as np

from app.core.config import settings

log = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return L2-normalised float32 vectors, shape (len(texts), dim)."""
        ...


def _normalise(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (mat / norms).astype(np.float32)


class FastEmbedProvider:
    """sentence-transformers/all-MiniLM-L6-v2 run through ONNX Runtime (no PyTorch needed)."""

    def __init__(self, model_name: str):
        from fastembed import TextEmbedding

        cache = settings.model_dir / "fastembed"
        cache.mkdir(parents=True, exist_ok=True)
        self._model = TextEmbedding(model_name=model_name, cache_dir=str(cache))
        self.name = model_name
        self.dim = int(self.embed(["probe"]).shape[1])

    def embed(self, texts: list[str]) -> np.ndarray:
        vecs = np.array(list(self._model.embed(texts, batch_size=64)), dtype=np.float32)
        return _normalise(vecs)


class TfidfProvider:
    """Offline fallback: character n-gram TF-IDF projected with SVD. Catches spelling variants,
    not meaning. Used only if the neural model cannot be downloaded/loaded."""

    def __init__(self, corpus: list[str]):
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.name = "tfidf-char-svd"
        self._vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1, sublinear_tf=True)
        x = self._vec.fit_transform(corpus or ["empty"])
        n_comp = max(2, min(256, x.shape[1] - 1, x.shape[0] - 1))
        self._svd = TruncatedSVD(n_components=n_comp, random_state=7).fit(x)
        self.dim = n_comp

    def embed(self, texts: list[str]) -> np.ndarray:
        return _normalise(self._svd.transform(self._vec.transform(texts)))


_provider: EmbeddingProvider | None = None
_lock = threading.Lock()


def get_provider(fallback_corpus: list[str] | None = None) -> EmbeddingProvider:
    global _provider
    if _provider is not None:
        return _provider
    with _lock:
        if _provider is not None:
            return _provider
        if settings.embedding_provider == "fastembed":
            try:
                _provider = FastEmbedProvider(settings.embedding_model)
                log.info("Embedding provider: %s (dim=%d)", _provider.name, _provider.dim)
                return _provider
            except Exception as exc:  # offline / model download failed
                log.warning("fastembed unavailable (%s); falling back to TF-IDF embeddings", exc)
        _provider = TfidfProvider(fallback_corpus or [])
        return _provider


def reset_provider() -> None:
    global _provider
    _provider = None
