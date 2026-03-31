"""backfill missing paper and citation schema objects

Revision ID: 014_schema_parity_papers
Revises: c41ed149a3b5
Create Date: 2026-03-30

This revision restores ORM/schema parity for paper-related models that were
introduced in code but never added to Alembic revisions:
- papers.source_url
- papers.toc
- paper_sections table
- citations table
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers
revision: str = "014_schema_parity_papers"
down_revision: Union[str, None] = "c41ed149a3b5"
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
    """Apply schema parity fixes for papers and citations."""
    tables = _table_names()

    if "papers" in tables:
        paper_columns = _column_names("papers")
        if "source_url" not in paper_columns:
            op.add_column("papers", sa.Column("source_url", sa.String(length=500), nullable=True))
        if "toc" not in paper_columns:
            op.add_column("papers", sa.Column("toc", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    if "paper_sections" not in tables:
        op.create_table(
            "paper_sections",
            sa.Column("paper_id", sa.String(length=36), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
            sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
            sa.Column("section_title", sa.Text(), nullable=False),
            sa.Column("section_path", sa.String(length=50), nullable=False),
            sa.Column("page_start", sa.Integer(), nullable=False),
            sa.Column("page_end", sa.Integer(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("level", sa.Integer(), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_paper_sections_paper_workspace",
            "paper_sections",
            ["paper_id", "workspace_id"],
            unique=False,
        )
        op.create_index(
            "ix_paper_sections_path",
            "paper_sections",
            ["paper_id", "section_path"],
            unique=False,
        )
        op.create_index(
            "ix_paper_sections_content_fts",
            "paper_sections",
            [sa.text("to_tsvector('simple', content)")],
            unique=False,
            postgresql_using="gin",
        )

    if "citations" not in tables:
        op.create_table(
            "citations",
            sa.Column("paper_id", sa.String(length=36), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
            sa.Column("cited_paper_id", sa.String(length=36), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
            sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
            sa.Column("citation_type", sa.String(length=20), nullable=False),
            sa.Column("citation_context", sa.Text(), nullable=True),
            sa.Column("section", sa.String(length=200), nullable=True),
            sa.Column("page_number", sa.Integer(), nullable=True),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("paper_id", "cited_paper_id", "workspace_id", name="uq_citation_relationship"),
        )
        op.create_index("ix_citations_source", "citations", ["paper_id"], unique=False)
        op.create_index("ix_citations_target", "citations", ["cited_paper_id"], unique=False)
        op.create_index("ix_citations_workspace", "citations", ["workspace_id"], unique=False)


def downgrade() -> None:
    """Rollback schema parity fixes for papers and citations."""
    tables = _table_names()

    if "citations" in tables:
        citation_indexes = _index_names("citations")
        if "ix_citations_workspace" in citation_indexes:
            op.drop_index("ix_citations_workspace", table_name="citations")
        if "ix_citations_target" in citation_indexes:
            op.drop_index("ix_citations_target", table_name="citations")
        if "ix_citations_source" in citation_indexes:
            op.drop_index("ix_citations_source", table_name="citations")
        op.drop_table("citations")

    if "paper_sections" in tables:
        section_indexes = _index_names("paper_sections")
        if "ix_paper_sections_content_fts" in section_indexes:
            op.drop_index("ix_paper_sections_content_fts", table_name="paper_sections", postgresql_using="gin")
        if "ix_paper_sections_path" in section_indexes:
            op.drop_index("ix_paper_sections_path", table_name="paper_sections")
        if "ix_paper_sections_paper_workspace" in section_indexes:
            op.drop_index("ix_paper_sections_paper_workspace", table_name="paper_sections")
        op.drop_table("paper_sections")

    if "papers" in tables:
        paper_columns = _column_names("papers")
        if "toc" in paper_columns:
            op.drop_column("papers", "toc")
        if "source_url" in paper_columns:
            op.drop_column("papers", "source_url")
