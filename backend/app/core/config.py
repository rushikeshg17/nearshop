"""Application settings, loaded from environment variables / .env."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_prefix="NEARSHOP_", extra="ignore")

    app_name: str = "NearShop"
    environment: str = "development"

    # Database: SQLite is the V1 requirement. SQLAlchemy keeps it portable.
    database_url: str = f"sqlite:///{BACKEND_DIR / 'nearshop.db'}"

    # Auth. secret_key MUST be overridden outside development.
    secret_key: str = "dev-only-change-me"
    access_token_minutes: int = 60 * 24 * 7
    cookie_name: str = "nearshop_session"
    cookie_secure: bool = False

    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    media_dir: Path = BACKEND_DIR / "media"
    max_upload_mb: int = 5

    # Seed / location defaults
    seed_city: str = "ballari"

    # Fulfillment defaults
    reservation_hold_minutes: int = 30
    request_response_minutes: int = 20  # shop must respond to a reservation request within this window

    # AI
    embedding_provider: str = "fastembed"  # fastembed | tfidf
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    model_dir: Path = BACKEND_DIR / "ml_artifacts"
    enable_scheduler: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
