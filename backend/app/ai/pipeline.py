"""Train / refresh every AI component in one call (used by seed, admin 'Retrain', and CLI)."""
import logging
import time

from app.ai import anomaly, demand, recommend, word2vec_ref
from app.ai.semantic_index import index
from app.core.database import Database
from app.models import ModelRun

log = logging.getLogger(__name__)


def train_all(db: Database) -> dict:
    out: dict = {}

    t = time.time()
    index.mark_dirty()
    index.ensure(db)
    db.model_runs.insert(
        ModelRun(
            name="embeddings",
            algorithm=index.provider_name,
            n_samples=len(index.product_ids),
            metrics={"listings_indexed": len(index.product_ids), "dimensions": int(index.matrix.shape[1])},
            data_note="Sentence embeddings for every active listing (cached per unique text).",
            duration_ms=int((time.time() - t) * 1000),
        )
    )
    out["embeddings"] = {"provider": index.provider_name, "listings": len(index.product_ids)}

    stats = word2vec_ref.train(db)
    db.model_runs.insert(ModelRun(name="word2vec", algorithm="Word2Vec skip-gram (gensim)", n_samples=stats["sentences"],
                    metrics=stats, data_note="Academic reference model trained on the product corpus.",
                    duration_ms=stats["duration_ms"]))
    out["word2vec"] = stats

    for name, fn in (("demand", demand.train_and_forecast), ("recommendations", recommend.train),
                     ("anomalies", anomaly.detect)):
        run = fn(db)
        out[name] = run.metrics
        log.info("trained %s in %sms: %s", name, run.duration_ms, run.metrics)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(train_all(Database()))
