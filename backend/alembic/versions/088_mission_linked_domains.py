"""cut execution-linked domains over to Mission provenance

Revision ID: 088_mission_linked_domains
Revises: 087_model_capability_profile
Create Date: 2026-07-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "088_mission_linked_domains"
down_revision: str | None = "087_model_capability_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _credit()
    _task_and_rooms()
    _source_and_provenance()
    _prism()
    _sandbox()
    _memory()
    _workspace_review_mode()
    _drop_old_runtime_tables()


def downgrade() -> None:
    raise RuntimeError("088_mission_linked_domains is an irreversible development cutover; reseed instead")


def _credit() -> None:
    op.drop_index("ix_credit_reservations_execution", table_name="credit_reservations")
    op.alter_column("credit_reservations", "execution_id", new_column_name="mission_id")
    op.drop_column("credit_reservations", "node_id")
    op.add_column(
        "credit_reservations",
        sa.Column("mission_item_seq", sa.BigInteger(), nullable=True),
    )
    op.execute("UPDATE credit_reservations SET mission_id = NULL")
    op.create_index(
        "ix_credit_reservations_mission",
        "credit_reservations",
        ["mission_id"],
    )
    op.create_foreign_key(
        "fk_credit_reservations_mission",
        "credit_reservations",
        "mission_runs",
        ["mission_id"],
        ["mission_id"],
        ondelete="SET NULL",
    )
    op.execute("ALTER TABLE credit_reservations ALTER COLUMN scope DROP DEFAULT")
    op.execute("ALTER TABLE credit_reservations ALTER COLUMN scope TYPE text USING scope::text")
    op.execute("DROP TYPE IF EXISTS credit_reservation_scope")
    scope = postgresql.ENUM(
        "mission",
        "sandbox_operation",
        "thread_turn",
        name="credit_reservation_scope",
    )
    scope.create(op.get_bind(), checkfirst=False)
    op.execute("UPDATE credit_reservations SET scope = 'mission' WHERE scope = 'feature_execution'")
    op.execute("ALTER TABLE credit_reservations ALTER COLUMN scope TYPE credit_reservation_scope USING scope::credit_reservation_scope")


def _task_and_rooms() -> None:
    op.alter_column("task_records", "execution_id", new_column_name="mission_id")
    op.execute("UPDATE task_records SET mission_id = NULL")
    op.create_foreign_key(
        "fk_task_records_mission",
        "task_records",
        "mission_runs",
        ["mission_id"],
        ["mission_id"],
        ondelete="SET NULL",
    )

    op.alter_column("workspace_tasks", "related_execution_ids", new_column_name="related_mission_ids")
    op.execute("UPDATE workspace_tasks SET related_mission_ids = '[]'::jsonb")
    for table_name in ("decisions", "workspace_tasks"):
        op.drop_column(table_name, "source_review_batch_id")
        op.drop_column(table_name, "source_review_item_id")
        op.add_column(table_name, sa.Column("source_mission_id", sa.String(36), nullable=True))
        op.add_column(
            table_name,
            sa.Column("source_mission_item_seq", sa.BigInteger(), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("source_mission_commit_id", sa.String(36), nullable=True),
        )
        op.create_foreign_key(
            f"fk_{table_name}_source_mission",
            table_name,
            "mission_runs",
            ["source_mission_id"],
            ["mission_id"],
            ondelete="SET NULL",
        )
        op.create_foreign_key(
            f"fk_{table_name}_source_mission_commit",
            table_name,
            "mission_commits",
            ["source_mission_commit_id"],
            ["commit_id"],
            ondelete="SET NULL",
        )
        op.create_index(
            f"uq_{table_name}_mission_commit",
            table_name,
            ["source_mission_commit_id"],
            unique=True,
            postgresql_where=sa.text("source_mission_commit_id IS NOT NULL"),
        )


def _source_and_provenance() -> None:
    op.alter_column("sources", "ingest_execution_id", new_column_name="ingest_mission_id")
    op.execute("UPDATE sources SET ingest_mission_id = NULL")
    op.add_column(
        "sources",
        sa.Column("ingest_mission_commit_id", sa.String(36), nullable=True),
    )
    op.create_foreign_key(
        "fk_sources_ingest_mission",
        "sources",
        "mission_runs",
        ["ingest_mission_id"],
        ["mission_id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_sources_ingest_mission_commit",
        "sources",
        "mission_commits",
        ["ingest_mission_commit_id"],
        ["commit_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "uq_sources_ingest_mission_commit",
        "sources",
        ["ingest_mission_commit_id"],
        unique=True,
        postgresql_where=sa.text("ingest_mission_commit_id IS NOT NULL"),
    )

    op.drop_index("ix_provenance_links_review_item", table_name="provenance_links")
    op.alter_column("provenance_links", "review_item_id", new_column_name="mission_review_item_id")
    op.alter_column("provenance_links", "execution_id", new_column_name="mission_id")
    op.add_column(
        "provenance_links",
        sa.Column("mission_commit_id", sa.String(36), nullable=True),
    )
    op.execute("UPDATE provenance_links SET mission_id = NULL, mission_review_item_id = NULL")
    op.create_foreign_key(
        "fk_provenance_links_mission",
        "provenance_links",
        "mission_runs",
        ["mission_id"],
        ["mission_id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_provenance_links_mission_review_item",
        "provenance_links",
        "mission_review_items",
        ["mission_review_item_id"],
        ["review_item_id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_provenance_links_mission_commit",
        "provenance_links",
        "mission_commits",
        ["mission_commit_id"],
        ["commit_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_provenance_links_mission_review_item",
        "provenance_links",
        ["mission_review_item_id"],
    )
    op.create_index(
        "ix_provenance_links_mission_commit",
        "provenance_links",
        ["mission_commit_id"],
    )


def _prism() -> None:
    op.drop_index("ix_prism_file_versions_review_item", table_name="prism_file_versions")
    op.alter_column("prism_file_versions", "review_item_id", new_column_name="mission_review_item_id")
    op.add_column(
        "prism_file_versions",
        sa.Column("mission_commit_id", sa.String(36), nullable=True),
    )
    op.execute("UPDATE prism_file_versions SET mission_review_item_id = NULL")
    op.create_foreign_key(
        "fk_prism_file_versions_mission_review_item",
        "prism_file_versions",
        "mission_review_items",
        ["mission_review_item_id"],
        ["review_item_id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_prism_file_versions_mission_commit",
        "prism_file_versions",
        "mission_commits",
        ["mission_commit_id"],
        ["commit_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_prism_file_versions_mission_review_item",
        "prism_file_versions",
        ["mission_review_item_id"],
    )
    op.create_index(
        "uq_prism_file_versions_mission_commit",
        "prism_file_versions",
        ["mission_commit_id"],
        unique=True,
        postgresql_where=sa.text("mission_commit_id IS NOT NULL"),
    )
    op.alter_column("prism_renders", "execution_id", new_column_name="mission_id")
    op.execute("UPDATE prism_renders SET mission_id = NULL")
    op.create_foreign_key(
        "fk_prism_renders_mission",
        "prism_renders",
        "mission_runs",
        ["mission_id"],
        ["mission_id"],
        ondelete="SET NULL",
    )


def _sandbox() -> None:
    op.drop_index("ix_sandbox_jobs_execution", table_name="sandbox_job_records")
    op.alter_column("sandbox_job_records", "execution_id", new_column_name="mission_id")
    op.drop_column("sandbox_job_records", "execution_node_id")
    op.add_column(
        "sandbox_job_records",
        sa.Column("mission_item_seq", sa.BigInteger(), nullable=True),
    )
    op.execute("UPDATE sandbox_job_records SET mission_id = NULL")
    op.create_foreign_key(
        "fk_sandbox_jobs_mission",
        "sandbox_job_records",
        "mission_runs",
        ["mission_id"],
        ["mission_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_sandbox_jobs_mission",
        "sandbox_job_records",
        ["mission_id", "mission_item_seq"],
    )

    op.alter_column("sandbox_leases", "holder_execution_id", new_column_name="holder_mission_id")
    op.execute("UPDATE sandbox_leases SET holder_mission_id = NULL")
    op.create_foreign_key(
        "fk_sandbox_leases_holder_mission",
        "sandbox_leases",
        "mission_runs",
        ["holder_mission_id"],
        ["mission_id"],
        ondelete="SET NULL",
    )

    op.drop_index("ix_sandbox_artifacts_review_item", table_name="sandbox_artifacts")
    op.drop_column("sandbox_artifacts", "review_batch_id")
    op.drop_column("sandbox_artifacts", "review_item_id")
    op.add_column(
        "sandbox_artifacts",
        sa.Column("mission_commit_id", sa.String(36), nullable=True),
    )
    op.create_foreign_key(
        "fk_sandbox_artifacts_mission_commit",
        "sandbox_artifacts",
        "mission_commits",
        ["mission_commit_id"],
        ["commit_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "uq_sandbox_artifacts_mission_commit",
        "sandbox_artifacts",
        ["mission_commit_id"],
        unique=True,
        postgresql_where=sa.text("mission_commit_id IS NOT NULL"),
    )


def _memory() -> None:
    for table_name in ("workspace_memory_documents", "workspace_memory_revisions"):
        op.alter_column(
            table_name,
            "source_execution_id",
            new_column_name="source_mission_id",
        )
        op.execute(sa.text(f"UPDATE {table_name} SET source_mission_id = NULL"))
        op.add_column(
            table_name,
            sa.Column("source_mission_commit_id", sa.String(36), nullable=True),
        )
        op.create_foreign_key(
            f"fk_{table_name}_source_mission",
            table_name,
            "mission_runs",
            ["source_mission_id"],
            ["mission_id"],
            ondelete="SET NULL",
        )
        op.create_foreign_key(
            f"fk_{table_name}_source_mission_commit",
            table_name,
            "mission_commits",
            ["source_mission_commit_id"],
            ["commit_id"],
            ondelete="SET NULL",
        )


def _workspace_review_mode() -> None:
    op.execute(
        """
        UPDATE workspace_settings
        SET settings_json =
            (settings_json - 'write_mode') ||
            jsonb_build_object(
                'review_mode',
                CASE settings_json->>'write_mode'
                    WHEN 'strict_review' THEN 'review_all'
                    WHEN 'ask_workspace_write' THEN 'balanced_default'
                    WHEN 'auto_draft' THEN 'auto_draft'
                    ELSE 'balanced_default'
                END
            )
        """
    )


def _drop_old_runtime_tables() -> None:
    for table_name in (
        "review_action_logs",
        "review_items",
        "review_batches",
        "run_history",
        "compute_sessions",
        "execution_events",
        "execution_nodes",
        "executions",
    ):
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))
