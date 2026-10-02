"""Alembic environment: uses the app's SQLAlchemy metadata and database URL."""
from logging.config import fileConfig

from alembic import context

import app.models  # noqa: F401  (registers all tables on Base.metadata)
from app.core.database import Base, engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# FTS5 virtual tables and their shadow tables are managed by hand in migrations.
FTS_TABLE_PREFIX = "products_fts"


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table" and name and name.startswith(FTS_TABLE_PREFIX):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite needs batch mode for ALTER TABLE
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
