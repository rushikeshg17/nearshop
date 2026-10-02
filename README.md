# NearShop

**Find it nearby.** A hyperlocal commerce platform for Tier-2 and Tier-3 Indian cities. Customers see which nearby shops have an item on the shelf right now, what it costs, and how recently that stock count was updated. They then reserve it for pickup or ask the shop to deliver it.

NearShop = Discover + Compare + Verify availability + Reserve + Pickup / Shop delivery + AI.

---

## What's inside

| Area | What it does |
|---|---|
| **Search** | Hybrid search: sentence embeddings (meaning) plus a weighted MongoDB text index (keywords), local synonyms, spelling correction, radius filter, stock, price and fulfilment filters. The same item sold by several shops is grouped so customers can compare. |
| **Map** | OpenStreetMap vector tiles through MapLibre GL, with price pins, a search-radius circle and directions links. |
| **Pickup reservations** | `REQUESTED -> CONFIRMED -> READY_FOR_PICKUP -> COMPLETED`, with `REJECTED`, `CANCELLED` and `EXPIRED` exits. Stock is held when the shop confirms and released on cancel or expiry. There is a live countdown and a pickup code. |
| **Shop delivery** | `PENDING -> SHOP_CONFIRMED -> PREPARING -> OUT_FOR_DELIVERY -> DELIVERED`, with `CANCELLED`, `DELIVERY_FAILED` and `RETURNED_TO_SHOP` paths. Each shop sets its own radius, fee and free-delivery threshold. Payment is cash on delivery, with a modular payment field for later. |
| **Trust signals** | Factual only: "Inventory updated 4 min ago", "Confirmed 44 of 47 requests", typical confirmation time, ratings from verified purchases. There is no opaque score. |
| **Shop dashboard** | Live queue with confirm and decline actions, inline stock and price editing, bulk add from a catalogue with local price guidance, photo upload, sales chart, AI insights. |
| **Excel/CSV import** | Owners upload the item list their billing app exports. Columns are detected automatically ("Particulars", "Closing Qty", "Sale Price"...), each row is fuzzy-matched to their listings or the catalogue, and nothing changes until they confirm the preview. |
| **Admin console** | Platform KPIs, category and search analytics, searches with no results, shop verification, price-anomaly review queue. |
| **AI Lab** | Side-by-side comparison of four search methods and live model cards with metrics. |

### The four AI modules (plus the Word2Vec reference)

| Module | Algorithm | Honest about |
|---|---|---|
| Semantic search | `sentence-transformers/all-MiniLM-L6-v2` via fastembed (ONNX, no PyTorch), behind a swappable `EmbeddingProvider` interface. Falls back to TF-IDF if the model can't download. | Embeddings are cached per unique text in `text_embeddings`. |
| Word2Vec (reference) | gensim skip-gram trained on the catalogue. Shown in the AI Lab for comparison. | It is kept as the academic baseline and is not used for ranking. |
| Demand prediction | Random Forest over lag features, calendar, category and price position, predicting next-7-day sales. It is validated on the most recent weeks against a naive "same as last week" baseline. | MAE, baseline MAE, R² and feature importance are shown. Any output trained on seeded sales is flagged `is_demo`. |
| Recommendations | Apriori and association rules (mlxtend) over baskets of completed purchases. | Support, confidence and lift are stored. If there is no rule for an item, the UI says "Popular in category" instead of inventing one. |
| Price anomalies | Isolation Forest over price relative to the local median for the same item (log ratio, robust z-score, price vs MRP). | Flags go to an admin review queue and are never auto-penalised. Small deviations are ignored. |

---

## Tech stack

**Frontend:** Next.js 16 (App Router, React 19, React Compiler), TypeScript, Tailwind CSS 4, shadcn/ui (Radix), Motion, TanStack Query 5, MapLibre GL 6 with OpenFreeMap tiles, Recharts.

**Backend:** Python 3.12, FastAPI, MongoDB (Atlas) through PyMongo, Pydantic 2 document models, multi-document transactions, `$jsonSchema` validation, 2dsphere and text indexes, Argon2 password hashing, JWT in an httpOnly cookie, APScheduler.

**AI/ML:** scikit-learn, pandas, NumPy, fastembed (ONNX Runtime), gensim, mlxtend, rapidfuzz.

```
browser ──> Next.js (localhost:3000) ──/api, /media rewrite──> FastAPI (localhost:8000) ──> MongoDB Atlas
                                                                   │
                                                                   ├── services/   state machines, search, analytics
                                                                   ├── ai/         embeddings, word2vec, demand, apriori, anomalies
                                                                   └── jobs.py     expires reservations every 30 s
```

The browser only talks to the Next.js origin. API calls and uploaded images are proxied, so the session cookie is first-party and SameSite=Lax.

---

## Run it locally

Requirements: Node 20.9+, [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 for you), and a MongoDB database: a free [Atlas](https://www.mongodb.com/atlas) cluster works. After `make setup`, put your connection string in `backend/.env` as `NEARSHOP_MONGODB_URI` (that file is gitignored; never commit it) and allow your IP address under Atlas > Network Access.

```bash
make setup     # install backend + frontend dependencies
make seed      # reset the MongoDB database, generate the demo city, train all models (~3 min on Atlas; first run downloads a 90 MB model)
make api       # FastAPI on http://localhost:8000  (API docs at /docs)
make web       # Next.js on http://localhost:3000  (in a second terminal)
```

Without make:

```bash
cd backend && uv sync && cp .env.example .env && uv run python -m database.seed.seed && uv run uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
```

### Demo accounts

The password for all three is `NEARSHOP_DEMO_PASSWORD` in `backend/.env.example`.

| Role | Email |
|---|---|
| Customer | `priya@nearshop.demo` |
| Shop owner (Kaveri Mobiles) | `owner@nearshop.demo` |
| Admin | `admin@nearshop.demo` |

### A five-minute demo

1. Open the home page and search **"phone charging adapter"**. The results include "Samsung 25W USB-C Fast Charger" even though the words don't match, because the search matches on meaning.
2. Compare the same item across shops on the list and map, then open a product. You'll see stock, freshness, price vs the local typical price, and the shop's track record.
3. Sign in as the customer and **Reserve for pickup**. A real reservation is created with a live countdown.
4. In another browser (or after signing out), sign in as the shop owner. The request is at the top of **Overview**. **Confirm and hold** and watch stock drop by one; the customer is notified.
5. Mark it ready and complete it. The sale is recorded and feeds the models.
6. Open **Inventory** and change a count. The freshness label updates everywhere.
7. Open **AI insights** for restock forecasts, local search demand, bundle gaps and price flags.
8. Sign in as admin. See **Price review** for the Isolation Forest queue and **AI Lab** to retrain every model.

All seed data (shops, prices, sales, reviews, searches) is generated for demonstration and labelled as such in the UI.

### Change the city

```bash
NEARSHOP_SEED_CITY=mysuru make seed   # ballari (default) | mysuru | hubballi | vijayawada | coimbatore | nashik
```

---

## Project structure

```
backend/
  app/
    api/routes/     auth, meta, search, catalog (public pages), customer, owner, admin, ai
    core/           config, database, security, deps (auth + CSRF guard), errors
    models/         Pydantic document models, one per MongoDB collection (users, shops, products, reservations, orders, reviews, AI outputs...)
    schemas/        request validation (Pydantic) and response serializers
    services/       search pipeline, reservation + order state machines, inventory, reliability, analytics
    ai/             embeddings, semantic index, word2vec, demand, recommend, anomaly, pipeline
    jobs.py         background expiry sweep
  database/
    schema.py       MongoDB collections, validation rules and indexes (+ how tables map to documents)
    seed/           seed.py and data/*.json (catalogue, cities, shops, co-purchase baskets)
  tests/            pytest: auth, CSRF, search, state machines, permissions
frontend/
  src/app/          (site) customer pages, (auth) sign-in/up, shop/ owner console, admin/
  src/components/   ui (shadcn), site shell, search, product, map, fulfilment, owner, dashboard
  src/lib/          api client, types, formatting, location context
```

## Security notes

- Argon2 password hashing. Login errors never reveal whether an account exists.
- JWT in an httpOnly, SameSite=Lax cookie. State-changing requests also require a custom header (CSRF defence in depth).
- Role checks on every route. Owners can only see and act on their own shop's data (tested).
- Pydantic validation on every request. ORM queries only; FTS terms are quoted.
- Uploads are decoded and re-encoded by Pillow (non-images are rejected, EXIF/GPS is stripped), with a size limit.
- `NEARSHOP_SECRET_KEY` must be set outside development; the app refuses to start otherwise.
- Security headers are set in `next.config.ts`.

## Tests

```bash
make test        # backend: 26 tests
cd frontend && npx tsc --noEmit && npx eslint src && npm run build
```

## Roadmap (designed for, not built)

PostgreSQL + PostGIS (the geo helpers are isolated), Redis cache, OpenSearch or pgvector (the embedding provider is an interface), S3 (the media service is an interface), Razorpay UPI (the order has `payment_method` and `payment_status`), push and email notifications (a single `notify()` seam), a NearShop rider network, and multi-city.
