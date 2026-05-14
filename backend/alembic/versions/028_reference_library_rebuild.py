"""rebuild workspace reference library

Revision ID: 028_reference_library_rebuild
Revises: 027_add_compute_sessions
Create Date: 2026-04-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "028_reference_library_rebuild"
down_revision: str | None = "027_add_compute_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _has_table(table_name: str) -> bool:
    return table_name in _table_names()


def _drop_old_reference_tables() -> None:
    """Drop legacy paper/literature tables in dependency order."""
    for table_name in (
        "citations",
        "paper_sections",
        "paper_chunks",
        "paper_extractions",
        "workspace_papers",
        "workspace_literature",
        "papers",
    ):
        if _has_table(table_name):
            op.drop_table(table_name)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    """Create canonical reference-library tables and remove legacy tables."""
    _drop_old_reference_tables()

    op.create_table(
        "workspace_references",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("normalized_title", sa.String(length=1000), nullable=False),
        sa.Column("authors", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("venue", sa.String(length=500), nullable=True),
        sa.Column("publication_type", sa.String(length=80), nullable=True),
        sa.Column("doi", sa.String(length=255), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("citation_count", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_label", sa.String(length=255), nullable=True),
        sa.Column("source_run_id", sa.String(length=100), nullable=True),
        sa.Column("source_artifact_id", sa.String(length=36), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("library_status", sa.String(length=50), server_default="candidate", nullable=False),
        sa.Column("evidence_level", sa.String(length=50), server_default="metadata_only", nullable=False),
        sa.Column("fulltext_status", sa.String(length=50), server_default="none", nullable=False),
        sa.Column("citation_key", sa.String(length=255), nullable=False),
        sa.Column("bibtex_entry_type", sa.String(length=50), server_default="article", nullable=False),
        sa.Column("bibtex_fields", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("read_status", sa.String(length=50), server_default="unread", nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["source_artifact_id"], ["artifacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "citation_key", name="uq_workspace_references_workspace_citation_key"),
    )
    op.create_index("ix_workspace_references_workspace_id", "workspace_references", ["workspace_id"])
    op.create_index("ix_workspace_references_workspace_status", "workspace_references", ["workspace_id", "library_status"])
    op.create_index("ix_workspace_references_workspace_created", "workspace_references", ["workspace_id", "created_at"])
    op.create_index("ix_workspace_references_workspace_title", "workspace_references", ["workspace_id", "normalized_title"])
    op.create_index(
        "uq_workspace_references_workspace_doi_active",
        "workspace_references",
        ["workspace_id", "doi"],
        unique=True,
        postgresql_where=sa.text("doi IS NOT NULL AND is_deleted = false"),
    )

    op.create_table(
        "reference_external_ids",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("reference_id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["reference_id"], ["workspace_references.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "source", "external_id", name="uq_reference_external_ids_workspace_source_external"),
    )
    op.create_index("ix_reference_external_ids_workspace_id", "reference_external_ids", ["workspace_id"])
    op.create_index("ix_reference_external_ids_reference", "reference_external_ids", ["reference_id"])

    op.create_table(
        "reference_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("reference_id", sa.String(length=36), nullable=False),
        sa.Column("source_asset_id", sa.String(length=36), nullable=True),
        sa.Column("asset_type", sa.String(length=50), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("virtual_path", sa.Text(), nullable=True),
        sa.Column("public_url", sa.Text(), nullable=True),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("file_hash", sa.String(length=128), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(length=50), nullable=True),
        sa.Column("preprocess_status", sa.String(length=50), server_default="skipped", nullable=False),
        sa.Column("preprocess_task_id", sa.String(length=36), nullable=True),
        sa.Column("preprocess_error", sa.Text(), nullable=True),
        sa.Column("manifest_path", sa.Text(), nullable=True),
        sa.Column("markdown_paths", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["reference_id"], ["workspace_references.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_asset_id"], ["reference_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reference_assets_workspace_id", "reference_assets", ["workspace_id"])
    op.create_index("ix_reference_assets_reference_type", "reference_assets", ["reference_id", "asset_type"])
    op.create_index("ix_reference_assets_workspace_status", "reference_assets", ["workspace_id", "preprocess_status"])
    op.create_index("ix_reference_assets_source_asset", "reference_assets", ["source_asset_id"])

    op.create_table(
        "reference_outline_nodes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("reference_id", sa.String(length=36), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("section_path", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("normalized_title", sa.String(length=1000), nullable=False),
        sa.Column("level", sa.Integer(), server_default="1", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("keywords", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["parent_id"], ["reference_outline_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reference_id"], ["workspace_references.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference_id", "section_path", name="uq_reference_outline_nodes_reference_section_path"),
    )
    op.create_index("ix_reference_outline_nodes_workspace_id", "reference_outline_nodes", ["workspace_id"])
    op.create_index("ix_reference_outline_nodes_workspace_reference", "reference_outline_nodes", ["workspace_id", "reference_id"])
    op.create_index("ix_reference_outline_nodes_parent", "reference_outline_nodes", ["parent_id"])

    op.create_table(
        "reference_text_units",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("reference_id", sa.String(length=36), nullable=False),
        sa.Column("outline_node_id", sa.String(length=36), nullable=True),
        sa.Column("asset_id", sa.String(length=36), nullable=True),
        sa.Column("unit_type", sa.String(length=50), nullable=False),
        sa.Column("unit_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["asset_id"], ["reference_assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["outline_node_id"], ["reference_outline_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reference_id"], ["workspace_references.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reference_text_units_workspace_id", "reference_text_units", ["workspace_id"])
    op.create_index("ix_reference_text_units_workspace_reference", "reference_text_units", ["workspace_id", "reference_id"])
    op.create_index("ix_reference_text_units_outline", "reference_text_units", ["outline_node_id"])
    op.create_index(
        "ix_reference_text_units_search_fts",
        "reference_text_units",
        [sa.text("to_tsvector('simple', search_text)")],
        postgresql_using="gin",
    )

    op.create_table(
        "reference_usage_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("reference_id", sa.String(length=36), nullable=False),
        sa.Column("outline_node_id", sa.String(length=36), nullable=True),
        sa.Column("text_unit_id", sa.String(length=36), nullable=True),
        sa.Column("execution_id", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("artifact_id", sa.String(length=36), nullable=True),
        sa.Column("latex_project_id", sa.String(length=36), nullable=True),
        sa.Column("target_section", sa.String(length=255), nullable=True),
        sa.Column("claim_text", sa.Text(), nullable=True),
        sa.Column("generated_text", sa.Text(), nullable=True),
        sa.Column("citation_key", sa.String(length=255), nullable=True),
        sa.Column("usage_type", sa.String(length=50), server_default="background", nullable=False),
        sa.Column("accepted_status", sa.String(length=50), server_default="pending", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["outline_node_id"], ["reference_outline_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reference_id"], ["workspace_references.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["text_unit_id"], ["reference_text_units.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reference_usage_events_workspace_id", "reference_usage_events", ["workspace_id"])
    op.create_index("ix_reference_usage_events_workspace_created", "reference_usage_events", ["workspace_id", "created_at"])
    op.create_index("ix_reference_usage_events_reference", "reference_usage_events", ["reference_id"])

    op.create_table(
        "reference_bibtex_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("latex_project_id", sa.String(length=36), nullable=True),
        sa.Column("scope", sa.String(length=50), server_default="included_and_core", nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("reference_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reference_bibtex_snapshots_workspace_id", "reference_bibtex_snapshots", ["workspace_id"])
    op.create_index("ix_reference_bibtex_snapshots_workspace_created", "reference_bibtex_snapshots", ["workspace_id", "created_at"])
    op.create_index("ix_reference_bibtex_snapshots_project_scope", "reference_bibtex_snapshots", ["latex_project_id", "scope"])


def downgrade() -> None:
    """Drop rebuilt reference-library tables.

    Legacy paper/literature tables are intentionally not recreated: this
    migration is a destructive product-level rebuild with no old data contract.
    """
    for table_name in (
        "reference_bibtex_snapshots",
        "reference_usage_events",
        "reference_text_units",
        "reference_outline_nodes",
        "reference_assets",
        "reference_external_ids",
        "workspace_references",
    ):
        if _has_table(table_name):
            op.drop_table(table_name)
