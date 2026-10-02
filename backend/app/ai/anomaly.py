"""Price anomaly detection with Isolation Forest.

Prices are only comparable for the same item, so each listing is described RELATIVE to
other shops selling the same catalog item: log(price / local median), a robust z-score
(median absolute deviation) and price / MRP. Isolation Forest learns what normal relative
pricing looks like across all items and isolates listings that are unusually high or low.

Flags are review items for an admin, never automatic penalties. A small-deviation guard
stops trivial differences (e.g. Rs 5 on a Rs 400 item) from being flagged.
"""
from __future__ import annotations

import time
from collections import defaultdict

import numpy as np
from sklearn.ensemble import IsolationForest

from app.core.database import Database
from app.models import AnomalyStatus, ModelRun, PriceAnomaly, Product
from app.services.loaders import with_catalog_items

MIN_PEERS = 4
MIN_DEVIATION = 0.18  # at least 18% from the local median to be worth a human look


def detect(db: Database) -> ModelRun:
    started = time.time()
    listings = with_catalog_items(db, db.products.find({"is_active": True, "catalog_item_id": {"$ne": None}},
                                                       projection={"description": 0, "specs": 0}))
    groups: dict[int, list[Product]] = defaultdict(list)
    for p in listings:
        groups[p.catalog_item_id].append(p)

    feats, meta = [], []
    for ps in groups.values():
        if len(ps) < MIN_PEERS:
            continue
        prices = np.array([p.price for p in ps])
        median = float(np.median(prices))
        mad = float(np.median(np.abs(prices - median))) or median * 0.05
        for p in ps:
            mrp = p.mrp or (p.catalog_item.mrp if p.catalog_item else None) or median
            feats.append([np.log(p.price / median), (p.price - median) / (1.4826 * mad), p.price / mrp])
            meta.append((p, median, len(ps)))

    run = ModelRun(name="anomalies", algorithm="IsolationForest", uses_demo_data=True)
    if len(feats) < 30:
        run.n_samples = len(feats)
        run.metrics = {"listings_checked": len(feats), "flagged": 0}
        run.data_note = "Not enough shops selling the same items to compare prices yet."
        db.model_runs.insert(run)
        return run

    X = np.array(feats)
    forest = IsolationForest(n_estimators=200, contamination="auto", random_state=7).fit(X)
    scores = -forest.score_samples(X)  # higher = more isolated = more unusual
    preds = forest.predict(X)

    run.id = db.next_id("model_runs")
    # Replace previous open flags; keep reviewed/dismissed decisions for audit.
    dismissed = {
        (a["product_id"], round(a["price"], 2))
        for a in db.price_anomalies.find_raw({"status": {"$ne": AnomalyStatus.OPEN}}, {"product_id": 1, "price": 1})
    }
    flags = []
    for (p, median, peers), score, pred in zip(meta, scores, preds):
        deviation = (p.price - median) / median
        if pred != -1 or abs(deviation) < MIN_DEVIATION or (p.id, round(p.price, 2)) in dismissed:
            continue
        flags.append(
            PriceAnomaly(
                product_id=p.id,
                shop_id=p.shop_id,
                catalog_item_id=p.catalog_item_id,
                price=p.price,
                reference_price=round(median, 2),
                deviation_pct=round(deviation * 100, 1),
                score=round(float(score), 4),
                direction="high" if deviation > 0 else "low",
                peer_count=peers,
                model_run_id=run.id,
            )
        )
    flagged = len(flags)
    run.n_samples = len(X)
    run.metrics = {
        "listings_checked": len(X),
        "item_groups": sum(1 for ps in groups.values() if len(ps) >= MIN_PEERS),
        "isolated_by_forest": int((preds == -1).sum()),
        "flagged_for_review": flagged,
        "min_deviation_pct": MIN_DEVIATION * 100,
    }
    run.data_note = "Compares each listing with other shops selling the same item (seeded demo prices)."
    run.duration_ms = int((time.time() - started) * 1000)

    def publish() -> None:
        db.price_anomalies.delete_many({"status": AnomalyStatus.OPEN})
        db.price_anomalies.insert_many(flags)
        db.model_runs.insert(run)

    db.transaction(publish)
    return run
