"""Add DataService sandbox runtime aggregate.

Revision ID: 068_dataservice_sandbox_runtime
Revises: 067_dataservice_sources_provenance
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "068_dataservice_sandbox_runtime"
down_revision: str | None = "067_dataservice_sources_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "sandbox_environments",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("sandbox_id", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("state", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("workspace_path", sa.Text(), nullable=True),
        sa.Column("network_policy", sa.String(length=50), server_default="restricted_egress", nullable=False),
        sa.Column("policy_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("resource_limits_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("created_by", sa.String(length=100), server_default="system", nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sandbox_environments_workspace_state",
        "sandbox_environments",
        ["workspace_id", "state"],
    )
    op.create_index("ix_sandbox_environments_external", "sandbox_environments", ["provider", "sandbox_id"])
    op.create_index(
        "uq_sandbox_environments_workspace_external",
        "sandbox_environments",
        ["workspace_id", "sandbox_id"],
        unique=True,
    )
    op.create_index(
        "uq_sandbox_environments_workspace_active",
        "sandbox_environments",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active'"),
    )

    op.create_table(
        "sandbox_job_records",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("sandbox_environment_id", sa.String(length=36), nullable=False),
        sa.Column("execution_id", sa.String(length=36), nullable=True),
        sa.Column("execution_node_id", sa.String(length=100), nullable=True),
        sa.Column("language", sa.String(length=32), server_default="python", nullable=False),
        sa.Column("runtime_image", sa.String(length=255), nullable=False),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("script_hash", sa.String(length=128), nullable=True),
        sa.Column("input_hashes_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("network_policy", sa.String(length=50), nullable=False),
        sa.Column("resource_limits_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("policy_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("stdout_asset_id", sa.String(length=36), nullable=True),
        sa.Column("stderr_asset_id", sa.String(length=36), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("metadata_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("language = 'python'", name="ck_sandbox_job_records_python_only"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sandbox_environment_id"], ["sandbox_environments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stdout_asset_id"], ["workspace_assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["stderr_asset_id"], ["workspace_assets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sandbox_jobs_environment_created",
        "sandbox_job_records",
        ["sandbox_environment_id", "created_at"],
    )
    op.create_index("ix_sandbox_jobs_workspace_status", "sandbox_job_records", ["workspace_id", "status"])
    op.create_index("ix_sandbox_jobs_execution", "sandbox_job_records", ["execution_id", "execution_node_id"])

    op.create_table(
        "sandbox_artifacts",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("sandbox_environment_id", sa.String(length=36), nullable=False),
        sa.Column("sandbox_job_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_asset_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_kind", sa.String(length=50), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("reproducibility_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("review_batch_id", sa.String(length=36), nullable=True),
        sa.Column("review_item_id", sa.String(length=36), nullable=True),
        sa.Column("materialization_status", sa.String(length=32), server_default="pending_review", nullable=False),
        sa.Column("metadata_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sandbox_environment_id"], ["sandbox_environments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sandbox_job_id"], ["sandbox_job_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_asset_id"], ["workspace_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_batch_id"], ["review_batches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["review_item_id"], ["review_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sandbox_artifacts_job", "sandbox_artifacts", ["sandbox_job_id"])
    op.create_index(
        "ix_sandbox_artifacts_workspace_status",
        "sandbox_artifacts",
        ["workspace_id", "materialization_status"],
    )
    op.create_index("ix_sandbox_artifacts_review_item", "sandbox_artifacts", ["review_item_id"])

    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    conn.execute(sa.text("""
        INSERT INTO sandbox_environments (
            id, workspace_id, sandbox_id, provider, state, workspace_path,
            network_policy, policy_json, resource_limits_json, created_by,
            last_active_at, released_at, metadata_json, created_at, updated_at
        )
        SELECT
            md5(workspace_id || ':sandbox:' || sandbox_id),
            workspace_id,
            sandbox_id,
            provider,
            CASE WHEN state IN ('active', 'stopped', 'error') THEN state ELSE 'error' END,
            workspace_path,
            'restricted_egress',
            jsonb_build_object(
                'schema_version', 'sandbox_policy.v1',
                'allow_python', true,
                'allow_network_egress', true,
                'allow_package_install', true,
                'allow_llm_api', true,
                'allow_web_data_fetch', true,
                'allow_workspace_file_io', true,
                'allow_host_network', false,
                'allow_privileged', false,
                'allow_docker_socket', false,
                'allow_host_path_mounts', false,
                'allow_sibling_container_access', false,
                'allow_server_control', false
            ),
            jsonb_build_object(
                'cpu_count', 2,
                'memory_mb', 4096,
                'timeout_seconds', 300,
                'max_output_bytes', 20000000
            ),
            'migration',
            last_active_at,
            CASE WHEN state = 'stopped' THEN last_active_at ELSE NULL END,
            jsonb_build_object('legacy_table', 'sandboxes', 'legacy_workspace_id', workspace_id),
            created_at,
            COALESCE(last_active_at, created_at)
        FROM sandboxes
        ON CONFLICT (id) DO NOTHING
    """))


def downgrade() -> None:
    op.drop_index("ix_sandbox_artifacts_review_item", table_name="sandbox_artifacts")
    op.drop_index("ix_sandbox_artifacts_workspace_status", table_name="sandbox_artifacts")
    op.drop_index("ix_sandbox_artifacts_job", table_name="sandbox_artifacts")
    op.drop_table("sandbox_artifacts")
    op.drop_index("ix_sandbox_jobs_execution", table_name="sandbox_job_records")
    op.drop_index("ix_sandbox_jobs_workspace_status", table_name="sandbox_job_records")
    op.drop_index("ix_sandbox_jobs_environment_created", table_name="sandbox_job_records")
    op.drop_table("sandbox_job_records")
    op.drop_index("uq_sandbox_environments_workspace_active", table_name="sandbox_environments")
    op.drop_index("uq_sandbox_environments_workspace_external", table_name="sandbox_environments")
    op.drop_index("ix_sandbox_environments_external", table_name="sandbox_environments")
    op.drop_index("ix_sandbox_environments_workspace_state", table_name="sandbox_environments")
    op.drop_table("sandbox_environments")
