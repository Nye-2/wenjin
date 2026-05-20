"""Add DataService sources and provenance.

Revision ID: 067_dataservice_sources_provenance
Revises: 066_dataservice_prism_documents
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "067_dataservice_sources_provenance"
down_revision: str | None = "066_dataservice_prism_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("source_kind", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("normalized_title", sa.String(length=1000), nullable=False),
        sa.Column("authors_json", _json_type(), server_default="[]", nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("venue", sa.String(length=500), nullable=True),
        sa.Column("publication_type", sa.String(length=80), nullable=True),
        sa.Column("doi", sa.String(length=255), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("citation_count", sa.Integer(), nullable=True),
        sa.Column("ingest_kind", sa.String(length=50), server_default="manual", nullable=False),
        sa.Column("ingest_label", sa.String(length=255), nullable=True),
        sa.Column("ingest_execution_id", sa.String(length=36), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("library_status", sa.String(length=32), server_default="candidate", nullable=False),
        sa.Column("evidence_level", sa.String(length=32), server_default="metadata_only", nullable=False),
        sa.Column("fulltext_status", sa.String(length=32), server_default="none", nullable=False),
        sa.Column("citation_key", sa.String(length=255), nullable=False),
        sa.Column("bibtex_entry_type", sa.String(length=50), server_default="article", nullable=False),
        sa.Column("bibtex_fields_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("read_status", sa.String(length=32), server_default="unread", nullable=False),
        sa.Column("tags_json", _json_type(), server_default="[]", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sources_workspace_status", "sources", ["workspace_id", "library_status"])
    op.create_index("ix_sources_workspace_title", "sources", ["workspace_id", "normalized_title"])
    op.create_index("uq_sources_workspace_citation_key", "sources", ["workspace_id", "citation_key"], unique=True)
    op.create_index(
        "uq_sources_workspace_doi_active",
        "sources",
        ["workspace_id", "doi"],
        unique=True,
        postgresql_where=sa.text("doi IS NOT NULL AND is_deleted = false"),
    )

    op.create_table(
        "source_external_ids",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("metadata_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_source_external_ids_workspace_provider_external",
        "source_external_ids",
        ["workspace_id", "provider", "external_id"],
        unique=True,
    )
    op.create_index("ix_source_external_ids_source", "source_external_ids", ["source_id"])

    op.create_table(
        "source_assets",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_asset_id", sa.String(length=36), nullable=False),
        sa.Column("asset_type", sa.String(length=40), nullable=False),
        sa.Column("preprocess_status", sa.String(length=32), server_default="skipped", nullable=False),
        sa.Column("manifest_asset_id", sa.String(length=36), nullable=True),
        sa.Column("metadata_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_asset_id"], ["workspace_assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_assets_source_type", "source_assets", ["source_id", "asset_type"])
    op.create_index("ix_source_assets_workspace_status", "source_assets", ["workspace_id", "preprocess_status"])

    op.create_table(
        "source_outline_nodes",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("section_path", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("level", sa.Integer(), server_default="1", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("keywords_json", _json_type(), server_default="[]", nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_outline_nodes_source_order", "source_outline_nodes", ["source_id", "sort_order"])
    op.create_index("ix_source_outline_nodes_parent", "source_outline_nodes", ["parent_id"])

    op.create_table(
        "source_text_units",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("outline_node_id", sa.String(length=36), nullable=True),
        sa.Column("source_asset_id", sa.String(length=36), nullable=True),
        sa.Column("unit_type", sa.String(length=40), nullable=False),
        sa.Column("unit_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("metadata_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_text_units_source_order", "source_text_units", ["source_id", "unit_index"])
    op.create_index("ix_source_text_units_outline", "source_text_units", ["outline_node_id"])

    op.create_table(
        "source_bibtex_snapshots",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("prism_project_id", sa.String(length=36), nullable=True),
        sa.Column("scope", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("reference_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_source_bibtex_snapshots_workspace_created",
        "source_bibtex_snapshots",
        ["workspace_id", "created_at"],
    )

    op.create_table(
        "source_anchors",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("source_text_unit_id", sa.String(length=36), nullable=True),
        sa.Column("anchor_kind", sa.String(length=50), nullable=False),
        sa.Column("anchor_key", sa.String(length=255), nullable=False),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("metadata_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_anchors_source", "source_anchors", ["source_id"])
    op.create_index("ix_source_anchors_workspace_kind", "source_anchors", ["workspace_id", "anchor_kind"])

    op.create_table(
        "provenance_links",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("source_anchor_id", sa.String(length=36), nullable=True),
        sa.Column("target_domain", sa.String(length=64), nullable=False),
        sa.Column("target_kind", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=100), nullable=True),
        sa.Column("target_ref_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("relation_kind", sa.String(length=64), nullable=False),
        sa.Column("citation_key", sa.String(length=255), nullable=True),
        sa.Column("claim_text", sa.Text(), nullable=True),
        sa.Column("generated_text", sa.Text(), nullable=True),
        sa.Column("review_item_id", sa.String(length=36), nullable=True),
        sa.Column("execution_id", sa.String(length=36), nullable=True),
        sa.Column("metadata_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_anchor_id"], ["source_anchors.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_provenance_links_workspace_created", "provenance_links", ["workspace_id", "created_at"])
    op.create_index("ix_provenance_links_source", "provenance_links", ["source_id"])
    op.create_index("ix_provenance_links_target", "provenance_links", ["target_domain", "target_kind", "target_id"])
    op.create_index("ix_provenance_links_review_item", "provenance_links", ["review_item_id"])

    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    conn.execute(sa.text("""
        INSERT INTO sources (
            id, workspace_id, source_kind, title, normalized_title, authors_json, year,
            venue, publication_type, doi, url, abstract, citation_count, ingest_kind,
            ingest_label, ingest_execution_id, verified_at, library_status,
            evidence_level, fulltext_status, citation_key, bibtex_entry_type,
            bibtex_fields_json, read_status, tags_json, notes, is_deleted,
            created_at, updated_at
        )
        SELECT
            id, workspace_id, 'paper', title, normalized_title, authors, year,
            venue, publication_type, doi, url, abstract, citation_count, source_type,
            source_label, source_run_id, verified_at, library_status,
            evidence_level, fulltext_status, citation_key, bibtex_entry_type,
            bibtex_fields, read_status, tags, notes, is_deleted,
            created_at, updated_at
        FROM workspace_references
        ON CONFLICT (id) DO NOTHING
    """))

    conn.execute(sa.text("""
        INSERT INTO sources (
            id, workspace_id, source_kind, title, normalized_title, authors_json, year,
            venue, doi, url, abstract, ingest_kind, library_status, evidence_level,
            fulltext_status, citation_key, bibtex_entry_type, bibtex_fields_json,
            tags_json, is_deleted, created_at, updated_at
        )
        SELECT
            id, workspace_id, item_type, title, lower(title), authors, year,
            venue, doi, url, abstract, 'manual', 'included', 'metadata_only',
            CASE WHEN full_text_path IS NULL THEN 'none' ELSE 'uploaded' END,
            COALESCE(NULLIF(metadata_json ->> 'citation_key', ''), 'lib_' || substr(id, 1, 8)),
            COALESCE(NULLIF(metadata_json ->> 'bibtex_entry_type', ''), 'article'),
            metadata_json,
            tags,
            deleted_at IS NOT NULL,
            created_at,
            updated_at
        FROM library_items
        ON CONFLICT (id) DO NOTHING
    """))

    conn.execute(sa.text("""
        INSERT INTO source_external_ids (
            id, workspace_id, source_id, provider, external_id, url, metadata_json,
            created_at, updated_at
        )
        SELECT id, workspace_id, reference_id, source, external_id, url, '{}'::jsonb,
               created_at, updated_at
        FROM reference_external_ids
        WHERE EXISTS (SELECT 1 FROM sources s WHERE s.id = reference_id)
        ON CONFLICT (id) DO NOTHING
    """))

    conn.execute(sa.text("""
        INSERT INTO workspace_assets (
            id, workspace_id, asset_kind, name, title, mime_type, storage_backend,
            storage_path, size_bytes, content_hash, created_by, source_kind,
            source_id, metadata_json, created_at, updated_at
        )
        SELECT
            id, workspace_id, 'source_file',
            LEFT(COALESCE(NULLIF(virtual_path, ''), NULLIF(file_path, ''), id), 255),
            virtual_path, content_type, 'local',
            COALESCE(NULLIF(file_path, ''), NULLIF(public_url, ''), NULLIF(virtual_path, ''), 'reference_assets/' || id),
            file_size, file_hash, 'reference_import', 'reference_assets', id,
            jsonb_build_object(
                'legacy_table', 'reference_assets',
                'legacy_id', id,
                'reference_id', reference_id,
                'page_count', page_count,
                'language', language,
                'manifest_path', manifest_path,
                'markdown_paths', markdown_paths
            ),
            created_at, updated_at
        FROM reference_assets
        ON CONFLICT (id) DO NOTHING
    """))

    conn.execute(sa.text("""
        INSERT INTO source_assets (
            id, workspace_id, source_id, workspace_asset_id, asset_type,
            preprocess_status, metadata_json, created_at, updated_at
        )
        SELECT id, workspace_id, reference_id, id, asset_type, preprocess_status,
               jsonb_build_object('legacy_table', 'reference_assets', 'legacy_id', id),
               created_at, updated_at
        FROM reference_assets
        WHERE EXISTS (SELECT 1 FROM sources s WHERE s.id = reference_id)
        ON CONFLICT (id) DO NOTHING
    """))

    conn.execute(sa.text("""
        INSERT INTO source_outline_nodes (
            id, workspace_id, source_id, parent_id, section_path, title, level,
            sort_order, page_start, page_end, char_start, char_end, summary,
            keywords_json, created_at, updated_at
        )
        SELECT id, workspace_id, reference_id, parent_id, section_path, title, level,
               sort_order, page_start, page_end, char_start, char_end, summary,
               keywords, created_at, updated_at
        FROM reference_outline_nodes
        WHERE EXISTS (SELECT 1 FROM sources s WHERE s.id = reference_id)
        ON CONFLICT (id) DO NOTHING
    """))

    conn.execute(sa.text("""
        INSERT INTO source_text_units (
            id, workspace_id, source_id, outline_node_id, source_asset_id, unit_type,
            unit_index, content, search_text, token_count, page_start, page_end,
            char_start, char_end, metadata_json, created_at, updated_at
        )
        SELECT id, workspace_id, reference_id, outline_node_id, asset_id, unit_type,
               unit_index, content, search_text, token_count, page_start, page_end,
               char_start, char_end, metadata_json, created_at, updated_at
        FROM reference_text_units
        WHERE EXISTS (SELECT 1 FROM sources s WHERE s.id = reference_id)
        ON CONFLICT (id) DO NOTHING
    """))

    conn.execute(sa.text("""
        INSERT INTO source_bibtex_snapshots (
            id, workspace_id, prism_project_id, scope, content, reference_count,
            checksum, created_at, updated_at
        )
        SELECT id, workspace_id, latex_project_id, scope, content, reference_count,
               checksum, created_at, updated_at
        FROM reference_bibtex_snapshots
        ON CONFLICT (id) DO NOTHING
    """))

    conn.execute(sa.text("""
        INSERT INTO source_anchors (
            id, workspace_id, source_id, source_text_unit_id, anchor_kind, anchor_key,
            quote, metadata_json, created_at, updated_at
        )
        SELECT id, workspace_id, reference_id, text_unit_id, 'reference_usage',
               COALESCE(citation_key, id), claim_text,
               jsonb_build_object('legacy_table', 'reference_usage_events', 'legacy_id', id),
               created_at, updated_at
        FROM reference_usage_events
        WHERE EXISTS (SELECT 1 FROM sources s WHERE s.id = reference_id)
        ON CONFLICT (id) DO NOTHING
    """))

    conn.execute(sa.text("""
        INSERT INTO provenance_links (
            id, workspace_id, source_id, source_anchor_id, target_domain, target_kind,
            target_id, target_ref_json, relation_kind, citation_key, claim_text,
            generated_text, execution_id, metadata_json, created_at, updated_at
        )
        SELECT id, workspace_id, reference_id, id, 'prism', 'latex_section',
               latex_project_id,
               jsonb_build_object('latex_project_id', latex_project_id, 'target_section', target_section),
               usage_type, citation_key, claim_text, generated_text, execution_id,
               jsonb_build_object('legacy_table', 'reference_usage_events', 'legacy_id', id, 'accepted_status', accepted_status),
               created_at, updated_at
        FROM reference_usage_events
        WHERE EXISTS (SELECT 1 FROM sources s WHERE s.id = reference_id)
        ON CONFLICT (id) DO NOTHING
    """))

    conn.execute(sa.text("""
        INSERT INTO provenance_links (
            id, workspace_id, source_id, source_anchor_id, target_domain, target_kind,
            target_id, target_ref_json, relation_kind, citation_key, review_item_id,
            metadata_json, created_at, updated_at
        )
        SELECT id, workspace_id, source_id, NULL, 'prism', 'file',
               latex_project_id,
               jsonb_build_object(
                   'latex_project_id', latex_project_id,
                   'file_path', file_path,
                   'section_key', section_key
               ),
               usage, citation_key, review_item_id,
               jsonb_build_object('legacy_table', 'prism_source_links', 'legacy_id', id, 'source_type', source_type),
               created_at, updated_at
        FROM prism_source_links
        WHERE EXISTS (SELECT 1 FROM sources s WHERE s.id = source_id)
        ON CONFLICT (id) DO NOTHING
    """))


def downgrade() -> None:
    op.drop_index("ix_provenance_links_review_item", table_name="provenance_links")
    op.drop_index("ix_provenance_links_target", table_name="provenance_links")
    op.drop_index("ix_provenance_links_source", table_name="provenance_links")
    op.drop_index("ix_provenance_links_workspace_created", table_name="provenance_links")
    op.drop_table("provenance_links")
    op.drop_index("ix_source_anchors_workspace_kind", table_name="source_anchors")
    op.drop_index("ix_source_anchors_source", table_name="source_anchors")
    op.drop_table("source_anchors")
    op.drop_index("ix_source_bibtex_snapshots_workspace_created", table_name="source_bibtex_snapshots")
    op.drop_table("source_bibtex_snapshots")
    op.drop_index("ix_source_text_units_outline", table_name="source_text_units")
    op.drop_index("ix_source_text_units_source_order", table_name="source_text_units")
    op.drop_table("source_text_units")
    op.drop_index("ix_source_outline_nodes_parent", table_name="source_outline_nodes")
    op.drop_index("ix_source_outline_nodes_source_order", table_name="source_outline_nodes")
    op.drop_table("source_outline_nodes")
    op.drop_index("ix_source_assets_workspace_status", table_name="source_assets")
    op.drop_index("ix_source_assets_source_type", table_name="source_assets")
    op.drop_table("source_assets")
    op.drop_index("ix_source_external_ids_source", table_name="source_external_ids")
    op.drop_index("uq_source_external_ids_workspace_provider_external", table_name="source_external_ids")
    op.drop_table("source_external_ids")
    op.drop_index("uq_sources_workspace_doi_active", table_name="sources")
    op.drop_index("uq_sources_workspace_citation_key", table_name="sources")
    op.drop_index("ix_sources_workspace_title", table_name="sources")
    op.drop_index("ix_sources_workspace_status", table_name="sources")
    op.drop_table("sources")
