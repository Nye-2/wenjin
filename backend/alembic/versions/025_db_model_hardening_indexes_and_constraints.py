"""db model hardening: hot-path indexes and integrity constraints

Revision ID: 025_db_model_hardening
Revises: 024_add_thread_summary_columns
Create Date: 2026-04-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "025_db_model_hardening"
down_revision: str | None = "024_add_thread_summary_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in set(inspector.get_table_names())


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return index_name in {item["name"] for item in inspector.get_indexes(table_name)}


def _has_check_constraint(table_name: str, constraint_name: str) -> bool:
    if not _has_table(table_name):
        return False
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return constraint_name in {
        item["name"] for item in inspector.get_check_constraints(table_name)
    }


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {item["name"] for item in inspector.get_columns(table_name)}


def _upgrade_workspace_literature() -> None:
    if not _has_table("workspace_literature"):
        return

    bind = op.get_bind()

    if _has_column("workspace_literature", "authors"):
        bind.execute(
            sa.text(
                "UPDATE workspace_literature "
                "SET authors = '[]'::jsonb "
                "WHERE authors IS NULL"
            )
        )
        op.alter_column(
            "workspace_literature",
            "authors",
            existing_type=sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        )

    if _has_column("workspace_literature", "source"):
        bind.execute(
            sa.text(
                "UPDATE workspace_literature "
                "SET source = 'manual' "
                "WHERE source IS NULL OR btrim(source) = ''"
            )
        )
        op.alter_column(
            "workspace_literature",
            "source",
            existing_type=sa.String(length=50),
            nullable=False,
            server_default="manual",
        )

    if _has_column("workspace_literature", "is_core"):
        bind.execute(
            sa.text(
                "UPDATE workspace_literature "
                "SET is_core = false "
                "WHERE is_core IS NULL"
            )
        )
        op.alter_column(
            "workspace_literature",
            "is_core",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        )

    if not _has_index("workspace_literature", "ix_workspace_literature_workspace_created"):
        op.create_index(
            "ix_workspace_literature_workspace_created",
            "workspace_literature",
            ["workspace_id", "created_at"],
        )
    if not _has_index(
        "workspace_literature",
        "ix_workspace_literature_workspace_core_created",
    ):
        op.create_index(
            "ix_workspace_literature_workspace_core_created",
            "workspace_literature",
            ["workspace_id", "is_core", "created_at"],
        )
    if not _has_index(
        "workspace_literature",
        "ix_workspace_literature_workspace_source_created",
    ):
        op.create_index(
            "ix_workspace_literature_workspace_source_created",
            "workspace_literature",
            ["workspace_id", "source", "created_at"],
        )


def _upgrade_execution_sessions() -> None:
    if not _has_table("execution_sessions"):
        return
    if not _has_index(
        "execution_sessions",
        "ix_execution_sessions_user_workspace_updated",
    ):
        op.create_index(
            "ix_execution_sessions_user_workspace_updated",
            "execution_sessions",
            ["user_id", "workspace_id", "updated_at"],
        )


def _upgrade_progress_and_message_count_constraints() -> None:
    bind = op.get_bind()
    if _has_column("task_records", "progress"):
        bind.execute(
            sa.text(
                "UPDATE task_records "
                "SET progress = GREATEST(0, LEAST(progress, 100)) "
                "WHERE progress < 0 OR progress > 100"
            )
        )
        if not _has_check_constraint("task_records", "ck_task_records_progress_range"):
            op.create_check_constraint(
                "ck_task_records_progress_range",
                "task_records",
                "progress >= 0 AND progress <= 100",
            )

    if _has_column("threads", "message_count"):
        bind.execute(
            sa.text(
                "UPDATE threads "
                "SET message_count = 0 "
                "WHERE message_count < 0"
            )
        )
        if not _has_check_constraint("threads", "ck_threads_message_count_non_negative"):
            op.create_check_constraint(
                "ck_threads_message_count_non_negative",
                "threads",
                "message_count >= 0",
            )


def _upgrade_task_indexes() -> None:
    if not _has_table("task_records"):
        return
    if not _has_index("task_records", "ix_task_records_user_created"):
        op.create_index(
            "ix_task_records_user_created",
            "task_records",
            ["user_id", "created_at"],
        )
    if not _has_index("task_records", "ix_task_records_dedupe_lookup"):
        op.create_index(
            "ix_task_records_dedupe_lookup",
            "task_records",
            [
                "user_id",
                "task_type",
                "workspace_id",
                "feature_id",
                "action",
                "status",
                "created_at",
            ],
        )
    if not _has_index("task_records", "ix_task_records_active_dedupe_lookup"):
        op.create_index(
            "ix_task_records_active_dedupe_lookup",
            "task_records",
            [
                "user_id",
                "task_type",
                "workspace_id",
                "feature_id",
                "action",
                "created_at",
            ],
            postgresql_where=sa.text("status IN ('pending', 'running')"),
        )


def upgrade() -> None:
    """Apply model hardening upgrades."""
    _upgrade_workspace_literature()
    _upgrade_execution_sessions()
    _upgrade_progress_and_message_count_constraints()
    _upgrade_task_indexes()


def downgrade() -> None:
    """Rollback model hardening upgrades."""
    if _has_index("task_records", "ix_task_records_dedupe_lookup"):
        op.drop_index("ix_task_records_dedupe_lookup", table_name="task_records")
    if _has_index("task_records", "ix_task_records_active_dedupe_lookup"):
        op.drop_index("ix_task_records_active_dedupe_lookup", table_name="task_records")
    if _has_index("task_records", "ix_task_records_user_created"):
        op.drop_index("ix_task_records_user_created", table_name="task_records")
    if _has_check_constraint("threads", "ck_threads_message_count_non_negative"):
        op.drop_constraint(
            "ck_threads_message_count_non_negative",
            "threads",
            type_="check",
        )
    if _has_check_constraint("task_records", "ck_task_records_progress_range"):
        op.drop_constraint(
            "ck_task_records_progress_range",
            "task_records",
            type_="check",
        )

    if _has_index(
        "execution_sessions",
        "ix_execution_sessions_user_workspace_updated",
    ):
        op.drop_index(
            "ix_execution_sessions_user_workspace_updated",
            table_name="execution_sessions",
        )

    if _has_index(
        "workspace_literature",
        "ix_workspace_literature_workspace_source_created",
    ):
        op.drop_index(
            "ix_workspace_literature_workspace_source_created",
            table_name="workspace_literature",
        )
    if _has_index(
        "workspace_literature",
        "ix_workspace_literature_workspace_core_created",
    ):
        op.drop_index(
            "ix_workspace_literature_workspace_core_created",
            table_name="workspace_literature",
        )
    if _has_index("workspace_literature", "ix_workspace_literature_workspace_created"):
        op.drop_index(
            "ix_workspace_literature_workspace_created",
            table_name="workspace_literature",
        )
