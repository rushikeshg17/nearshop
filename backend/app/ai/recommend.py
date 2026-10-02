"""Market-basket recommendations with Apriori (mlxtend).

A basket is everything bought together in one visit/order (same basket_id). Apriori finds
item sets that often appear together; association rules turn them into
"customers who bought A also bought B" with support, confidence and lift.
"""
from __future__ import annotations

import time
from collections import defaultdict

import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules
from mlxtend.preprocessing import TransactionEncoder

from app.core.database import Database
from app.models import AssociationRule, ModelRun

MIN_SUPPORT_COUNT = 8  # an item set must appear in at least this many baskets
MIN_CONFIDENCE = 0.12
MIN_LIFT = 1.5


def train(db: Database) -> ModelRun:
    started = time.time()
    rows = db.sales_history.find_raw({"catalog_item_id": {"$ne": None}},
                                     {"_id": 0, "basket_id": 1, "catalog_item_id": 1, "is_demo": 1})
    baskets: dict[str, set[int]] = defaultdict(set)
    uses_demo = False
    for r in rows:
        baskets[r["basket_id"]].add(r["catalog_item_id"])
        uses_demo |= bool(r["is_demo"])
    multi = [sorted(b) for b in baskets.values() if len(b) >= 2]

    run = ModelRun(name="recommendations", algorithm="Apriori + association rules", uses_demo_data=uses_demo)
    if len(multi) < 20:
        run.n_samples = len(multi)
        run.metrics = {"baskets": len(baskets), "multi_item_baskets": len(multi), "rules": 0}
        run.data_note = "Not enough multi-item baskets yet to learn bundles."
        db.recommendations.delete_many({})
        db.model_runs.insert(run)
        return run

    # Baskets are item-id lists; single-item baskets still count toward support denominators.
    all_baskets = [sorted(b) for b in baskets.values()]
    te = TransactionEncoder()
    onehot = pd.DataFrame(te.fit(all_baskets).transform(all_baskets, sparse=False), columns=te.columns_)
    min_support = max(MIN_SUPPORT_COUNT / len(all_baskets), 0.0005)
    itemsets = apriori(onehot, min_support=min_support, use_colnames=True, max_len=3, low_memory=True)

    rules_df = pd.DataFrame()
    if not itemsets.empty and (itemsets["itemsets"].apply(len) > 1).any():
        rules_df = association_rules(itemsets, metric="confidence", min_threshold=MIN_CONFIDENCE)
        rules_df = rules_df[rules_df["lift"] >= MIN_LIFT]

    run.id = db.next_id("model_runs")
    rules = []
    for r in rules_df.itertuples():
        ante = sorted(int(x) for x in r.antecedents)
        cons = sorted(int(x) for x in r.consequents)
        rules.append(
            AssociationRule(
                antecedents=ante,
                consequents=cons,
                antecedent_key=",".join(map(str, ante)),
                support=round(float(r.support), 5),
                confidence=round(float(r.confidence), 4),
                lift=round(float(r.lift), 3),
                model_run_id=run.id,
            )
        )
    run.n_samples = len(all_baskets)
    run.metrics = {
        "baskets": len(all_baskets),
        "multi_item_baskets": len(multi),
        "frequent_itemsets": int(len(itemsets)),
        "rules": int(len(rules_df)),
        "min_support": round(min_support, 5),
        "min_confidence": MIN_CONFIDENCE,
        "min_lift": MIN_LIFT,
        "avg_confidence": round(float(rules_df["confidence"].mean()), 3) if len(rules_df) else None,
        "avg_lift": round(float(rules_df["lift"].mean()), 3) if len(rules_df) else None,
    }
    run.data_note = "Learned from seeded demo baskets plus real orders." if uses_demo else "Learned from real orders."
    run.duration_ms = int((time.time() - started) * 1000)

    def publish() -> None:  # swap the old rule set for the new one atomically
        db.recommendations.delete_many({})
        db.recommendations.insert_many(rules)
        db.model_runs.insert(run)

    db.transaction(publish)
    return run


def bundle_for(db: Database, catalog_item_id: int, limit: int = 6) -> list[dict]:
    """Items frequently bought with `catalog_item_id`, strongest first."""
    rules = sorted(db.recommendations.find({"antecedent_key": str(catalog_item_id)}),
                   key=lambda r: -r.confidence * r.lift)
    seen: dict[int, dict] = {}
    for r in rules:
        for c in r.consequents:
            if c != catalog_item_id and c not in seen:
                seen[c] = {"catalog_item_id": c, "confidence": r.confidence, "lift": r.lift, "support": r.support}
    return list(seen.values())[:limit]
