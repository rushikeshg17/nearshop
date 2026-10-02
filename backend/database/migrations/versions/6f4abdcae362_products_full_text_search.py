"""products full text search

SQLite FTS5 index over product listings, kept in sync with triggers.
This is the keyword half of NearShop's hybrid (keyword + semantic) search.

Revision ID: 6f4abdcae362
Revises: e3f914dda3f6
Create Date: 2026-09-30 00:57:53.557956

"""
from typing import Sequence, Union

from alembic import op

revision: str = "6f4abdcae362"
down_revision: Union[str, Sequence[str], None] = "e3f914dda3f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIRTUAL TABLE products_fts USING fts5(
            name, brand, keywords, description,
            content='products', content_rowid='id',
            tokenize='porter unicode61 remove_diacritics 2',
            prefix='2 3'
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER products_fts_ai AFTER INSERT ON products BEGIN
            INSERT INTO products_fts(rowid, name, brand, keywords, description)
            VALUES (new.id, new.name, coalesce(new.brand, ''), new.keywords, coalesce(new.description, ''));
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER products_fts_ad AFTER DELETE ON products BEGIN
            INSERT INTO products_fts(products_fts, rowid, name, brand, keywords, description)
            VALUES ('delete', old.id, old.name, coalesce(old.brand, ''), old.keywords, coalesce(old.description, ''));
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER products_fts_au AFTER UPDATE OF name, brand, keywords, description ON products BEGIN
            INSERT INTO products_fts(products_fts, rowid, name, brand, keywords, description)
            VALUES ('delete', old.id, old.name, coalesce(old.brand, ''), old.keywords, coalesce(old.description, ''));
            INSERT INTO products_fts(rowid, name, brand, keywords, description)
            VALUES (new.id, new.name, coalesce(new.brand, ''), new.keywords, coalesce(new.description, ''));
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS products_fts_au")
    op.execute("DROP TRIGGER IF EXISTS products_fts_ad")
    op.execute("DROP TRIGGER IF EXISTS products_fts_ai")
    op.execute("DROP TABLE IF EXISTS products_fts")
