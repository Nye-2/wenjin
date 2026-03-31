"""drop unused paper chunk embedding column

Revision ID: 015_drop_paper_chunk_embedding
Revises: 014_schema_parity_papers
Create Date: 2026-03-30

The project no longer uses vector-based retrieval for paper chunks. The
embedding column and its ivfflat index are legacy schema artifacts and should
be removed so the live schema matches the ORM.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = "015_drop_paper_chunk_embedding"
down_revision: Union[str, None] = "014_schema_parity_papers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return set(inspector.get_table_names(schema="public"))


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {
        column["name"]
        for column in inspector.get_columns(table_name, schema="public")
    }


def _index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {
        index["name"]
        for index in inspector.get_indexes(table_name, schema="public")
    }


def upgrade() -> None:
    """Drop the legacy vector index and embedding column from paper_chunks."""
    tables = _table_names()
    if "paper_chunks" not in tables:
        return

    indexes = _index_names("paper_chunks")
    if "ix_paper_chunks_embedding" in indexes:
        op.drop_index("ix_paper_chunks_embedding", table_name="paper_chunks")

    columns = _column_names("paper_chunks")
    if "embedding" in columns:
        op.drop_column("paper_chunks", "embedding")


def downgrade() -> None:
    """Recreate the legacy embedding column and ivfflat index."""
    tables = _table_names()
    if "paper_chunks" not in tables:
        return

    columns = _column_names("paper_chunks")
    if "embedding" not in columns:
        op.add_column("paper_chunks", sa.Column("embedding", sa.Text(), nullable=True))
        op.execute(
            """
            ALTER TABLE paper_chunks
            ALTER COLUMN embedding TYPE vector(1536)
            USING embedding::vector(1536)
            """
        )

    indexes = _index_names("paper_chunks")
    if "ix_paper_chunks_embedding" not in indexes:
        op.execute(
            """
            CREATE INDEX ix_paper_chunks_embedding
            ON paper_chunks
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
            """
        )
