from app.core.database import SessionLocal
from app.models import InventoryEvent
from tests.conftest import CENTER, HEADERS


def test_owner_updates_stock_and_it_is_audited(owner_a, ids):
    res = owner_a.put(f"/api/owner/products/{ids['charger']}/stock", json={"quantity": 9}, headers=HEADERS).json()
    assert res["quantity"] == 9 and res["stock_status"] == "in_stock"
    with SessionLocal() as db:
        last = db.query(InventoryEvent).filter_by(product_id=ids["charger"]).order_by(InventoryEvent.id.desc()).first()
        assert last.quantity_after == 9


def test_out_of_stock_items_still_appear_marked(owner_a, client, ids):
    owner_a.put(f"/api/owner/products/{ids['charger']}/stock", json={"quantity": 0}, headers=HEADERS)
    detail = client.get(f"/api/products/{ids['charger']}").json()
    assert detail["stock_status"] == "out_of_stock"
    owner_a.put(f"/api/owner/products/{ids['charger']}/stock", json={"quantity": 5}, headers=HEADERS)


def test_owner_cannot_edit_another_shops_product(owner_b, ids):
    res = owner_b.patch(f"/api/owner/products/{ids['charger']}", json={"price": 1}, headers=HEADERS)
    assert res.status_code == 404
    res = owner_b.put(f"/api/owner/products/{ids['charger']}/stock", json={"quantity": 0}, headers=HEADERS)
    assert res.status_code == 404


def test_owner_creates_custom_product_that_becomes_searchable(owner_a, client):
    res = owner_a.post("/api/owner/products", json={
        "name": "Hand Pump Washer Kit", "category_slug": "plumbing", "price": 120, "quantity": 7,
        "tags": ["borewell", "hand pump", "washer"],
    }, headers=HEADERS)
    assert res.status_code == 200
    found = client.get("/api/search", params={"q": "borewell washer", "lat": CENTER[0], "lng": CENTER[1]}).json()
    assert any(g["name"] == "Hand Pump Washer Kit" for g in found["groups"])


def test_customer_cannot_use_owner_or_admin_api(customer):
    assert customer.get("/api/owner/overview").status_code == 403
    assert customer.get("/api/admin/overview").status_code == 403


def test_admin_overview_and_price_review(admin):
    res = admin.get("/api/admin/overview")
    assert res.status_code == 200
    assert res.json()["totals"]["shops"] >= 2
    assert admin.get("/api/admin/anomalies").status_code == 200


def test_validation_errors_are_readable(owner_a):
    res = owner_a.post("/api/owner/products", json={"name": "x", "category_slug": "plumbing", "price": -1, "quantity": 1},
                       headers=HEADERS)
    assert res.status_code == 422
    assert "message" in res.json()["error"]


def test_import_preview_matches_and_commit_applies(owner_a, ids):
    # Headers and values the way a billing app exports them: odd names, rupee signs, units in quantity.
    csv = (
        "Particulars,Closing Stock,Sale Price,MRP\n"
        "Samsung 25W USB-C Fast Travel Charger,8 pcs,\"Rs 1,199\",1699\n"  # already listed -> update
        "Astral PTFE Thread Seal Tape,20,39,50\n"  # listed at shop A -> update
        "Havells 16A Plug Top,5,95,\n"  # unknown -> new product
    )
    res = owner_a.post("/api/owner/import/preview", files={"file": ("stock.csv", csv, "text/csv")}, headers=HEADERS)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["columns"]["name"] == "Particulars" and body["columns"]["quantity"] == "Closing Stock"
    rows = {r["name"]: r for r in body["rows"]}
    charger = rows["Samsung 25W USB-C Fast Travel Charger"]
    assert charger["action"] == "update" and charger["product_id"] == ids["charger"]
    assert charger["quantity"] == 8 and charger["price"] == 1199
    assert rows["Havells 16A Plug Top"]["action"] == "add_new"

    rows["Havells 16A Plug Top"]["category_slug"] = "plumbing"
    done = owner_a.post("/api/owner/import/commit", json={"rows": list(rows.values())}, headers=HEADERS)
    assert done.status_code == 200, done.text
    assert done.json() == {"updated": 2, "added": 1, "skipped": 0}
    with SessionLocal() as db:
        from app.models import Product

        p = db.get(Product, ids["charger"])
        assert p.quantity == 8 and p.price == 1199


def test_import_rejects_non_spreadsheets(owner_a):
    res = owner_a.post("/api/owner/import/preview", files={"file": ("photo.png", b"\x89PNG", "image/png")}, headers=HEADERS)
    assert res.status_code == 400
