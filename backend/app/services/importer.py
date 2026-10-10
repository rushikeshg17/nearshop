"""Bulk stock import from the Excel/CSV item list a shop already has.

Most local shops keep stock in a billing app (Vyapar, Tally, Marg, Khatabook...) that can export
an item list. The owner uploads that file; we detect the columns, match every row to their existing
listings or to the NearShop catalogue with fuzzy matching, and show a preview. Nothing changes
until the owner confirms (commit).
"""
from __future__ import annotations

import io
import re
from typing import TYPE_CHECKING

from rapidfuzz import fuzz, process

from app.core.database import Database
from app.core.errors import AppError
from app.models import Product, Shop
from app.services.inventory import apply_bulk
from app.services.loaders import categories as load_categories
from app.services.loaders import with_category

if TYPE_CHECKING:  # pandas is imported on use: it stays out of the API's serving memory
    import pandas as pd

MAX_ROWS = 2000
MAX_BYTES = 5 * 1024 * 1024
AUTO_MATCH = 86  # at or above: confidently the same item
SUGGEST_MATCH = 72  # between SUGGEST and AUTO: suggested, owner should check

# Header names used by common billing apps and hand-made sheets.
COLUMN_ALIASES: dict[str, list[str]] = {
    "name": ["item name", "item", "product name", "product", "name", "particulars", "item description", "description",
             "stock item", "item details"],
    "quantity": ["quantity", "qty", "stock", "closing stock", "closing qty", "current stock", "stock qty", "balance",
                 "in stock", "available", "available qty", "opening stock"],
    "price": ["selling price", "sale price", "sales price", "price", "rate", "sp", "unit price", "retail price"],
    "mrp": ["mrp", "m.r.p", "max retail price"],
    "brand": ["brand", "company", "manufacturer", "make"],
    "category": ["category", "item group", "group", "department", "type", "stock group"],
    "sku": ["sku", "item code", "code", "barcode", "product code"],
}

TEMPLATE_CSV = (
    "Item name,Brand,Category,Quantity,Selling price,MRP\n"
    "Samsung 25W USB-C Fast Charger,Samsung,Mobile Accessories,6,1249,1699\n"
    "Astral PTFE Thread Seal Tape 12 mm,Astral,Plumbing,40,40,50\n"
    "Classmate Long Notebook 172 pages,Classmate,Stationery,25,65,70\n"
)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9. ]+", " ", str(s).lower()).strip()


def _detect_columns(columns: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    normed = {c: _norm(c) for c in columns}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:  # aliases are ordered by preference
            hit = next((c for c, n in normed.items() if n == alias and c not in found.values()), None)
            if hit is None:
                hit = next((c for c, n in normed.items() if alias in n and c not in found.values()), None)
            if hit is not None:
                found[field] = hit
                break
    return found


def _number(v) -> float | None:
    if v is None or (isinstance(v, float) and v != v):  # NaN is the only value not equal to itself
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", str(v).replace(",", ""))
    return float(m.group()) if m else None


def read_table(data: bytes, filename: str) -> pd.DataFrame:
    import pandas as pd

    if len(data) > MAX_BYTES:
        raise AppError("File is larger than 5 MB. Split it or export only items in stock.", code="file_too_large")
    name = filename.lower()
    try:
        if name.endswith(".xlsx"):
            df = pd.read_excel(io.BytesIO(data), engine="openpyxl", dtype=str)
        elif name.endswith(".csv") or name.endswith(".txt"):
            try:
                df = pd.read_csv(io.BytesIO(data), dtype=str, encoding="utf-8-sig")
            except UnicodeDecodeError:
                df = pd.read_csv(io.BytesIO(data), dtype=str, encoding="latin-1")
        else:
            raise AppError("Upload a .xlsx or .csv file. Old .xls files: open and 'Save as' .xlsx first.", code="bad_file")
    except AppError:
        raise
    except Exception:
        raise AppError("Couldn't read that file. Check it opens in Excel and has a header row.", code="bad_file") from None
    df = df.dropna(how="all")
    if len(df) > MAX_ROWS:
        raise AppError(f"That file has {len(df)} rows; the limit is {MAX_ROWS} per upload.", code="too_many_rows")
    return df


def preview(db: Database, shop: Shop, data: bytes, filename: str) -> dict:
    df = read_table(data, filename)
    cols = _detect_columns([str(c) for c in df.columns])
    if "name" not in cols:
        raise AppError("Couldn't find an item name column. Name it 'Item name' (see the template).", code="no_name_column")

    catalog, mine = db.gather(lambda: with_category(db, db.catalog_items.find()),
                              lambda: db.products.find({"shop_id": shop.id}))
    catalog_keys = {c.id: _norm(f"{c.brand or ''} {c.name}") for c in catalog}
    catalog_by_id = {c.id: c for c in catalog}
    mine_by_name = {_norm(p.name): p for p in mine}
    mine_by_catalog = {p.catalog_item_id: p for p in mine if p.catalog_item_id}
    categories = list(load_categories(db).values())
    cat_names = {c.slug: _norm(c.name) for c in categories}
    default_cat = shop.categories[0].slug if shop.categories else categories[0].slug

    rows = []
    for i, rec in enumerate(df.to_dict("records"), start=2):  # row 1 is the header in Excel
        name = str(rec.get(cols["name"]) or "").strip()
        if not name or name.lower() == "nan":
            continue
        qty = _number(rec.get(cols.get("quantity"))) if "quantity" in cols else None
        price = _number(rec.get(cols.get("price"))) if "price" in cols else None
        mrp = _number(rec.get(cols.get("mrp"))) if "mrp" in cols else None
        brand = str(rec.get(cols["brand"]) or "").strip() if "brand" in cols else ""
        brand = "" if brand.lower() == "nan" else brand
        price_from_mrp = price is None and mrp is not None
        if price_from_mrp:
            price = mrp

        row = {"row": i, "name": name, "brand": brand or None, "quantity": int(qty) if qty is not None and qty >= 0 else None,
               "price": round(price, 2) if price else None, "mrp": round(mrp, 2) if mrp else None,
               "action": "add_new", "product_id": None, "catalog_item_id": None, "match_name": None, "score": 0,
               "category_slug": default_cat, "issues": []}

        existing = mine_by_name.get(_norm(name))
        match = process.extractOne(_norm(f"{brand} {name}"), catalog_keys, scorer=fuzz.token_set_ratio)
        if match:
            _, score, cid = match
            # token_set_ratio scores 100 when one name's words are a subset of the other's, so a bare
            # "cable" would match every cable. Require at least two meaningful words to auto-match.
            if len([w for w in _norm(name).split() if len(w) > 2]) < 2:
                score = min(score, SUGGEST_MATCH - 1)
            item = catalog_by_id[cid]
            row["category_slug"] = item.category.slug if score >= SUGGEST_MATCH - 10 else row["category_slug"]
            if score >= SUGGEST_MATCH:
                row.update(catalog_item_id=cid, match_name=item.name, score=round(score))
                if existing is None and cid in mine_by_catalog:
                    existing = mine_by_catalog[cid]
                if existing is None:
                    row["action"] = "add_catalog"
                    if score < AUTO_MATCH:
                        row["issues"].append("Check the catalogue match")
                    if row["price"] is None and item.typical_price:
                        row["price"] = item.typical_price
                        row["issues"].append("No price in file; using the typical local price")
        if existing is not None:
            row.update(action="update", product_id=existing.id, match_name=existing.name,
                       score=max(row["score"], 100 if _norm(existing.name) == _norm(name) else row["score"]))
            if row["price"] is None:
                row["price"] = existing.price

        if "category" in cols and row["action"] == "add_new":
            raw = _norm(rec.get(cols["category"]) or "")
            if raw:
                best = process.extractOne(raw, cat_names, scorer=fuzz.WRatio)
                if best and best[1] >= 70:
                    row["category_slug"] = best[2]
        if price_from_mrp:
            row["issues"].append("No selling price in file; using MRP")
        if row["quantity"] is None:
            row["issues"].append("No quantity; stock will not be changed" if row["action"] == "update" else "No quantity; will be added as 0")
        if row["price"] is None and row["action"] != "update":
            row["issues"].append("Price missing: enter one before importing")
        rows.append(row)

    summary = {a: sum(1 for r in rows if r["action"] == a) for a in ("update", "add_catalog", "add_new")}
    return {"columns": cols, "rows": rows, "summary": summary, "total": len(rows)}


def commit(db: Database, shop: Shop, rows: list[dict], actor_id: int) -> dict:
    """Apply confirmed rows in a single transaction: all rows succeed or none do.

    Everything is validated and prepared in memory first, then written in a few bulk operations,
    so a 2,000-row sheet is as safe (and nearly as fast) as a 2-row one."""
    counts = {"updated": 0, "added": 0, "skipped": 0}
    cats = {c.slug: c for c in load_categories(db).values()}
    cats_by_id = load_categories(db)
    mine = db.products.find({"shop_id": shop.id})
    mine_by_id = {p.id: p for p in mine}
    mine_by_catalog = {p.catalog_item_id: p for p in mine if p.catalog_item_id}
    catalog = db.catalog_items.by_ids(r.get("catalog_item_id") for r in rows if r["action"] == "add_catalog")

    creates: list[tuple[Product, int]] = []
    updates: dict[int, tuple[Product, dict, int | None]] = {}

    def update(p: Product, price, qty) -> None:
        _, fields, old_qty = updates.get(id(p), (p, {}, None))
        fields["is_active"] = True
        if price:
            fields["price"] = float(price)
        updates[id(p)] = (p, fields, int(qty) if qty is not None else old_qty)
        counts["updated"] += 1

    for r in rows:
        action = r["action"]
        qty = r.get("quantity")
        price = r.get("price")
        if action == "skip":
            counts["skipped"] += 1
            continue
        if action == "update":
            p = mine_by_id.get(r["product_id"])
            if p is None:
                raise AppError(f"Row {r.get('row')}: that product is not in your shop")
            update(p, price, qty)
            continue
        if not price or float(price) <= 0:
            raise AppError(f"Row {r.get('row')} ({r.get('name')}): enter a price", code="missing_price")
        if action == "add_catalog":
            c = catalog.get(r["catalog_item_id"])
            if c is None:
                raise AppError(f"Row {r.get('row')}: catalogue item not found")
            existing = mine_by_catalog.get(c.id)
            if existing:  # listed meanwhile (or duplicate row): treat as update
                update(existing, price, qty)
                continue
            category = cats_by_id[c.category_id]
            p = Product(shop_id=shop.id, catalog_item_id=c.id, category_id=c.category_id, name=c.name,
                        brand=c.brand, unit=c.unit, description=c.description, specs=c.specs or {},
                        keywords=" ".join(dict.fromkeys([*(c.tags or []), category.name.lower(),
                                                         (c.subcategory or "").replace("-", " ")])),
                        icon=c.icon, price=float(price), mrp=c.mrp, quantity=0)
            mine_by_catalog[c.id] = p
        elif action == "add_new":
            cat = cats.get(r.get("category_slug") or "")
            if cat is None:
                raise AppError(f"Row {r.get('row')} ({r.get('name')}): choose a category")
            name = str(r.get("name") or "").strip()[:200]
            if len(name) < 2:
                raise AppError(f"Row {r.get('row')}: item name is missing")
            p = Product(shop_id=shop.id, category_id=cat.id, name=name, brand=(r.get("brand") or None),
                        keywords=cat.name.lower(), icon=cat.icon, price=float(price),
                        mrp=float(r["mrp"]) if r.get("mrp") else None, quantity=0)
        else:
            raise AppError(f"Unknown action '{action}'")
        creates.append((p, int(qty or 0)))
        counts["added"] += 1

    # A duplicate catalogue row that followed its own "add" in the same file updates the new listing.
    new_ids = {id(p) for p, _ in creates}
    for key, (p, fields, qty) in list(updates.items()):
        if id(p) in new_ids:
            for k, v in fields.items():
                setattr(p, k, v)
            if qty is not None:
                creates = [(cp, qty if cp is p else cq) for cp, cq in creates]
            del updates[key]
    apply_bulk(db, shop, actor_id, creates, list(updates.values()))
    return counts
