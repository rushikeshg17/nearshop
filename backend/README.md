# NearShop API

FastAPI + SQLAlchemy + SQLite. See the root README for setup, the demo script and the architecture.

- `uv run uvicorn app.main:app --reload`: run the API (interactive docs at http://localhost:8000/docs)
- `uv run python -m database.seed.seed`: rebuild and seed the demo database, then train all models
- `uv run pytest -q`: tests
- `uv run alembic revision --autogenerate -m "..."`: new migration after changing models
