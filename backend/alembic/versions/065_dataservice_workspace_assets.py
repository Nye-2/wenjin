"""Add DataService workspace assets.

Revision ID: 065_dataservice_workspace_assets
Revises: 064_dataservice_review_queue
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "065_dataservice_workspace_assets"
down_revision: str | None = "064_dataservice_review_queue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "workspace_assets",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("asset_kind", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("storage_backend", sa.String(length=50), server_default="local", nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("parent_asset_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("source_kind", sa.String(length=50), nullable=True),
        sa.Column("source_id", sa.String(length=100), nullable=True),
        sa.Column("metadata_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_asset_id"], ["workspace_assets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workspace_assets_workspace_kind_created",
        "workspace_assets",
        ["workspace_id", "asset_kind", "created_at"],
    )
    op.create_index("ix_workspace_assets_source", "workspace_assets", ["source_kind", "source_id"])
    op.create_index("ix_workspace_assets_content_hash", "workspace_assets", ["content_hash"])
    op.create_index("ix_workspace_assets_parent", "workspace_assets", ["parent_asset_id"])

    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    conn.execute(sa.text("""
        INSERT INTO workspace_assets (
            id, workspace_id, asset_kind, name, title, mime_type, storage_backend,
            storage_path, size_bytes, content_hash, parent_asset_id, created_by,
            source_kind, source_id, metadata_json, deleted_at, created_at, updated_at
        )
        SELECT
            id,
            workspace_id,
            CASE
                WHEN kind IN ('upload', 'export', 'figure', 'dataset', 'preview') THEN kind
                ELSE 'document'
            END,
            LEFT(name, 255),
            LEFT(name, 500),
            mime_type,
            'local',
            storage_path,
            size_bytes,
            metadata_json ->> 'content_hash',
            NULL,
            added_by,
            'documents_v2',
            id,
            jsonb_build_object(
                'legacy_table', 'documents_v2',
                'legacy_id', id,
                'legacy_kind', kind,
                'legacy_version', version,
                'legacy_parent_id', parent_id,
                'metadata', metadata_json
            ),
            deleted_at,
            created_at,
            updated_at
        FROM documents_v2
        WHERE storage_path IS NOT NULL AND btrim(storage_path) <> ''
        ON CONFLICT (id) DO NOTHING
    """))

    conn.execute(sa.text("""
        INSERT INTO workspace_assets (
            id, workspace_id, asset_kind, name, title, mime_type, storage_backend,
            storage_path, size_bytes, content_hash, parent_asset_id, created_by,
            source_kind, source_id, metadata_json, deleted_at, created_at, updated_at
        )
        SELECT
            id,
            workspace_id,
            'artifact',
            LEFT(COALESCE(NULLIF(title, ''), type || '-' || version::text), 255),
            LEFT(title, 500),
            COALESCE(content ->> 'mime_type', content ->> 'content_type'),
            COALESCE(NULLIF(content ->> 'storage_backend', ''), 'local'),
            COALESCE(
                NULLIF(content ->> 'storage_path', ''),
                NULLIF(content ->> 'file_path', ''),
                NULLIF(content ->> 'path', ''),
                NULLIF(content ->> 'url', ''),
                NULLIF(content ->> 'public_url', '')
            ),
            CASE
                WHEN COALESCE(content ->> 'size_bytes', content ->> 'file_size') ~ '^[0-9]+$'
                    THEN COALESCE(content ->> 'size_bytes', content ->> 'file_size')::bigint
                ELSE NULL
            END,
            COALESCE(content ->> 'content_hash', content ->> 'file_hash', content ->> 'sha256'),
            NULL,
            COALESCE(NULLIF(created_by_skill, ''), 'system'),
            'artifacts',
            id,
            jsonb_build_object(
                'legacy_table', 'artifacts',
                'legacy_id', id,
                'artifact_type', type,
                'status', status,
                'version', version,
                'parent_artifact_id', parent_artifact_id
            ),
            NULL,
            created_at,
            updated_at
        FROM artifacts
        WHERE COALESCE(
            NULLIF(content ->> 'storage_path', ''),
            NULLIF(content ->> 'file_path', ''),
            NULLIF(content ->> 'path', ''),
            NULLIF(content ->> 'url', ''),
            NULLIF(content ->> 'public_url', '')
        ) IS NOT NULL
        ON CONFLICT (id) DO NOTHING
    """))

    conn.execute(sa.text("""
        INSERT INTO workspace_assets (
            id, workspace_id, asset_kind, name, title, mime_type, storage_backend,
            storage_path, size_bytes, content_hash, parent_asset_id, created_by,
            source_kind, source_id, metadata_json, deleted_at, created_at, updated_at
        )
        SELECT
            id,
            workspace_id,
            COALESCE(NULLIF("metadata" ->> 'asset_kind', ''), 'generation_output'),
            LEFT(COALESCE(NULLIF("metadata" ->> 'name', ''), NULLIF("metadata" ->> 'filename', ''), skill_name || '-' || id), 255),
            LEFT(output_summary, 500),
            COALESCE("metadata" ->> 'mime_type', "metadata" ->> 'content_type'),
            COALESCE(NULLIF("metadata" ->> 'storage_backend', ''), 'local'),
            COALESCE(
                NULLIF("metadata" ->> 'storage_path', ''),
                NULLIF("metadata" ->> 'file_path', ''),
                NULLIF("metadata" ->> 'output_path', ''),
                NULLIF("metadata" ->> 'artifact_path', ''),
                NULLIF("metadata" ->> 'url', '')
            ),
            CASE
                WHEN COALESCE("metadata" ->> 'size_bytes', "metadata" ->> 'file_size') ~ '^[0-9]+$'
                    THEN COALESCE("metadata" ->> 'size_bytes', "metadata" ->> 'file_size')::bigint
                ELSE NULL
            END,
            COALESCE("metadata" ->> 'content_hash', "metadata" ->> 'file_hash', "metadata" ->> 'sha256'),
            NULL,
            skill_name,
            'generation_records',
            id,
            jsonb_build_object(
                'legacy_table', 'generation_records',
                'legacy_id', id,
                'thread_id', thread_id,
                'skill_name', skill_name,
                'model_name', model_name,
                'status', status,
                'token_usage', token_usage,
                'metadata', "metadata"
            ),
            NULL,
            created_at,
            updated_at
        FROM generation_records
        WHERE COALESCE(
            NULLIF("metadata" ->> 'storage_path', ''),
            NULLIF("metadata" ->> 'file_path', ''),
            NULLIF("metadata" ->> 'output_path', ''),
            NULLIF("metadata" ->> 'artifact_path', ''),
            NULLIF("metadata" ->> 'url', '')
        ) IS NOT NULL
        ON CONFLICT (id) DO NOTHING
    """))


def downgrade() -> None:
    op.drop_index("ix_workspace_assets_parent", table_name="workspace_assets")
    op.drop_index("ix_workspace_assets_content_hash", table_name="workspace_assets")
    op.drop_index("ix_workspace_assets_source", table_name="workspace_assets")
    op.drop_index("ix_workspace_assets_workspace_kind_created", table_name="workspace_assets")
    op.drop_table("workspace_assets")
