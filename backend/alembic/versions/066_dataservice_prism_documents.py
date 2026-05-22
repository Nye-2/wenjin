"""Add DataService Prism document aggregate.

Revision ID: 066_dataservice_prism_documents
Revises: 065_dataservice_workspace_assets
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "066_dataservice_prism_documents"
down_revision: str | None = "065_dataservice_workspace_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "prism_projects",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("adapter_kind", sa.String(length=50), server_default="latex", nullable=False),
        sa.Column("adapter_ref_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("settings_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("adapter_metadata_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("trashed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_prism_projects_workspace_primary_active",
        "prism_projects",
        ["workspace_id", "role"],
        unique=True,
        postgresql_where=sa.text("role = 'primary_manuscript' AND status = 'active' AND trashed_at IS NULL"),
    )
    op.create_index("ix_prism_projects_workspace_status", "prism_projects", ["workspace_id", "status"])
    op.create_index("ix_prism_projects_adapter_ref", "prism_projects", ["adapter_kind", "adapter_ref_id"])

    op.create_table(
        "prism_documents",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("document_kind", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("adapter_kind", sa.String(length=50), server_default="latex", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("root_file_id", sa.String(length=36), nullable=True),
        sa.Column("metadata_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["prism_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prism_documents_workspace_status", "prism_documents", ["workspace_id", "status"])
    op.create_index("ix_prism_documents_project_kind", "prism_documents", ["project_id", "document_kind"])

    op.create_table(
        "prism_files",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("file_role", sa.String(length=50), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("current_version_id", sa.String(length=36), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("metadata_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["prism_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_prism_files_document_path", "prism_files", ["document_id", "path"], unique=True)
    op.create_index("ix_prism_files_workspace", "prism_files", ["workspace_id"])
    op.create_index("ix_prism_files_document_order", "prism_files", ["document_id", "sort_order"])

    op.create_table(
        "prism_file_versions",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("review_item_id", sa.String(length=36), nullable=True),
        sa.Column("content_inline", sa.Text(), nullable=True),
        sa.Column("content_asset_id", sa.String(length=36), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "(content_inline IS NOT NULL AND content_asset_id IS NULL) "
            "OR (content_inline IS NULL AND content_asset_id IS NOT NULL)",
            name="ck_prism_file_versions_one_content_pointer",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["prism_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_item_id"], ["review_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["content_asset_id"], ["workspace_assets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_prism_file_versions_file_version",
        "prism_file_versions",
        ["file_id", "version_no"],
        unique=True,
    )
    op.create_index(
        "ix_prism_file_versions_workspace_created",
        "prism_file_versions",
        ["workspace_id", "created_at"],
    )
    op.create_index("ix_prism_file_versions_review_item", "prism_file_versions", ["review_item_id"])

    op.create_table(
        "prism_renders",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("execution_id", sa.String(length=36), nullable=True),
        sa.Column("render_kind", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("engine", sa.String(length=50), nullable=True),
        sa.Column("input_hash", sa.String(length=128), nullable=False),
        sa.Column("output_asset_id", sa.String(length=36), nullable=True),
        sa.Column("log_asset_id", sa.String(length=36), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["prism_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["output_asset_id"], ["workspace_assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["log_asset_id"], ["workspace_assets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prism_renders_document_created", "prism_renders", ["document_id", "created_at"])
    op.create_index("ix_prism_renders_workspace_status", "prism_renders", ["workspace_id", "status"])

    op.create_table(
        "prism_protected_scopes",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("file_id", sa.String(length=36), nullable=True),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("section_key", sa.String(length=255), server_default="", nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["prism_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_prism_protected_scopes_scope",
        "prism_protected_scopes",
        ["project_id", "file_path", "section_key", "scope"],
        unique=True,
    )
    op.create_index("ix_prism_protected_scopes_workspace", "prism_protected_scopes", ["workspace_id"])
    op.create_index("ix_prism_protected_scopes_project", "prism_protected_scopes", ["project_id"])

    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    conn.execute(sa.text("""
        INSERT INTO prism_projects (
            id, workspace_id, role, title, adapter_kind, adapter_ref_id, status,
            settings_json, adapter_metadata_json, trashed_at, created_at, updated_at
        )
        SELECT
            id,
            workspace_id,
            COALESCE(surface_role, 'primary_manuscript'),
            name,
            'latex',
            id,
            CASE
                WHEN trashed THEN 'trashed'
                WHEN archived THEN 'archived'
                ELSE 'active'
            END,
            jsonb_build_object('tags', tags),
            jsonb_build_object(
                'latex_project_id', id,
                'main_file', main_file,
                'template_id', template_id,
                'file_order', file_order,
                'legacy_metadata', COALESCE(llm_config -> 'metadata', '{}'::jsonb),
                'llm_config', COALESCE(llm_config, '{}'::jsonb)
            ),
            trashed_at,
            created_at,
            updated_at
        FROM latex_projects
        WHERE workspace_id IS NOT NULL
          AND surface_role = 'primary_manuscript'
        ON CONFLICT (id) DO NOTHING
    """))

    conn.execute(sa.text("""
        INSERT INTO prism_documents (
            id, workspace_id, project_id, document_kind, title, adapter_kind, status,
            root_file_id, metadata_json, created_at, updated_at
        )
        SELECT
            md5(id || ':document:manuscript'),
            workspace_id,
            id,
            'manuscript',
            name,
            'latex',
            CASE
                WHEN trashed THEN 'trashed'
                WHEN archived THEN 'archived'
                ELSE 'active'
            END,
            md5(id || ':file:' || main_file),
            jsonb_build_object('main_file', main_file, 'latex_project_id', id),
            created_at,
            updated_at
        FROM latex_projects
        WHERE workspace_id IS NOT NULL
          AND surface_role = 'primary_manuscript'
        ON CONFLICT (id) DO NOTHING
    """))

    conn.execute(sa.text("""
        INSERT INTO prism_files (
            id, workspace_id, document_id, path, file_role, mime_type, sort_order,
            metadata_json, created_at, updated_at
        )
        SELECT
            md5(id || ':file:' || main_file),
            workspace_id,
            md5(id || ':document:manuscript'),
            main_file,
            'main',
            'text/x-tex',
            0,
            jsonb_build_object('latex_project_id', id, 'source', 'latex_projects.main_file'),
            created_at,
            updated_at
        FROM latex_projects
        WHERE workspace_id IS NOT NULL
          AND surface_role = 'primary_manuscript'
        ON CONFLICT (document_id, path) DO NOTHING
    """))

    conn.execute(sa.text("""
        INSERT INTO prism_files (
            id, workspace_id, document_id, path, file_role, mime_type, sort_order,
            metadata_json, created_at, updated_at
        )
        SELECT
            md5(lp.id || ':file:' || (managed.value ->> 'path')),
            lp.workspace_id,
            md5(lp.id || ':document:manuscript'),
            managed.value ->> 'path',
            'generated',
            'text/x-tex',
            row_number() OVER (PARTITION BY lp.id ORDER BY managed.key),
            jsonb_build_object(
                'latex_project_id', lp.id,
                'logical_key', managed.key,
                'legacy_record', managed.value
            ),
            lp.created_at,
            lp.updated_at
        FROM latex_projects lp,
             jsonb_each(COALESCE(lp.llm_config -> 'metadata' -> 'managed_files', '{}'::jsonb)) AS managed(key, value)
        WHERE lp.workspace_id IS NOT NULL
          AND lp.surface_role = 'primary_manuscript'
          AND (managed.value ->> 'path') IS NOT NULL
        ON CONFLICT (document_id, path) DO NOTHING
    """))


def downgrade() -> None:
    op.drop_index("ix_prism_protected_scopes_project", table_name="prism_protected_scopes")
    op.drop_index("ix_prism_protected_scopes_workspace", table_name="prism_protected_scopes")
    op.drop_index("uq_prism_protected_scopes_scope", table_name="prism_protected_scopes")
    op.drop_table("prism_protected_scopes")
    op.drop_index("ix_prism_renders_workspace_status", table_name="prism_renders")
    op.drop_index("ix_prism_renders_document_created", table_name="prism_renders")
    op.drop_table("prism_renders")
    op.drop_index("ix_prism_file_versions_review_item", table_name="prism_file_versions")
    op.drop_index("ix_prism_file_versions_workspace_created", table_name="prism_file_versions")
    op.drop_index("uq_prism_file_versions_file_version", table_name="prism_file_versions")
    op.drop_table("prism_file_versions")
    op.drop_index("ix_prism_files_document_order", table_name="prism_files")
    op.drop_index("ix_prism_files_workspace", table_name="prism_files")
    op.drop_index("uq_prism_files_document_path", table_name="prism_files")
    op.drop_table("prism_files")
    op.drop_index("ix_prism_documents_project_kind", table_name="prism_documents")
    op.drop_index("ix_prism_documents_workspace_status", table_name="prism_documents")
    op.drop_table("prism_documents")
    op.drop_index("ix_prism_projects_adapter_ref", table_name="prism_projects")
    op.drop_index("ix_prism_projects_workspace_status", table_name="prism_projects")
    op.drop_index("uq_prism_projects_workspace_primary_active", table_name="prism_projects")
    op.drop_table("prism_projects")
