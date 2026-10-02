.PHONY: setup seed api web test retrain lint

setup:
	cd backend && uv sync && ( [ -f .env ] || cp .env.example .env )
	cd frontend && npm install

seed:
	cd backend && uv run python -m database.seed.seed

api:
	cd backend && uv run uvicorn app.main:app --reload --reload-dir app --port 8000

web:
	cd frontend && npm run dev

test:
	cd backend && uv run pytest -q

retrain:
	cd backend && uv run python -m app.ai.pipeline

lint:
	cd backend && uv run ruff check app database tests
	cd frontend && npx tsc --noEmit && npx eslint src
