from tests.conftest import CENTER, HEADERS, PASSWORD


def test_register_login_and_me(client):
    res = client.post("/api/auth/register", json={"name": "New Person", "email": "new@example.com", "password": "longenough1"},
                      headers=HEADERS)
    assert res.status_code == 200
    assert res.json()["role"] == "customer"
    assert client.get("/api/auth/me").json()["email"] == "new@example.com"

    dup = client.post("/api/auth/register", json={"name": "Again", "email": "new@example.com", "password": "longenough1"},
                      headers=HEADERS)
    assert dup.status_code == 409


def test_login_errors_do_not_reveal_accounts(client):
    wrong_pw = client.post("/api/auth/login", json={"email": "cust@example.com", "password": "nope"}, headers=HEADERS)
    no_user = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": PASSWORD}, headers=HEADERS)
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json()["error"]["message"] == no_user.json()["error"]["message"]


def test_state_changing_requests_need_client_header(client):
    res = client.post("/api/auth/login", json={"email": "cust@example.com", "password": PASSWORD})
    assert res.status_code == 403


def test_me_is_null_when_signed_out(client):
    assert client.get("/api/auth/me").json() is None


def test_password_is_hashed(ids):
    from app.core.database import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        u = db.query(User).filter_by(email="cust@example.com").one()
        assert u.password_hash.startswith("$argon2")


def test_search_finds_by_keyword_and_filters_by_distance(client, ids):
    res = client.get("/api/search", params={"q": "teflon tape", "lat": CENTER[0], "lng": CENTER[1], "radius_km": 5}).json()
    offers = [o["id"] for g in res["groups"] for o in g["offers"]]
    assert ids["tape"] in offers
    assert ids["tape_far"] not in offers  # 22 km away, outside the radius


def test_search_uses_synonyms_and_meaning(client, ids):
    res = client.get("/api/search", params={"q": "phone charging adaptor", "lat": CENTER[0], "lng": CENTER[1]}).json()
    assert any(g["best_offer"]["id"] == ids["charger"] for g in res["groups"])


def test_search_corrects_spelling(client, ids):
    res = client.get("/api/search", params={"q": "tefloon tape", "lat": CENTER[0], "lng": CENTER[1]}).json()
    assert res["total"] >= 1


def test_product_detail_shows_stock_and_trust(client, ids):
    res = client.get(f"/api/products/{ids['charger']}", params={"lat": CENTER[0], "lng": CENTER[1]}).json()
    assert res["stock_status"] == "in_stock"
    assert res["shop"]["reliability"]["inventory_update_days_7d"] >= 0
    assert res["delivery_quote"]["eligible"] is True
