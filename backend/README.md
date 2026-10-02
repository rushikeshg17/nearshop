# NearShop API

FastAPI + MongoDB (PyMongo, Pydantic document models). See the root README for setup, the demo script and the architecture.

- `uv run uvicorn app.main:app --reload`: run the API (interactive docs at http://localhost:8000/docs)
- `uv run python -m database.seed.seed`: rebuild and seed the demo database, then train all models
- `uv run pytest -q`: tests
- `uv run python -m database.schema`: create or update collections, validators and indexes (idempotent). The data model and how it maps from the old relational schema is documented at the top of `database/schema.py`
