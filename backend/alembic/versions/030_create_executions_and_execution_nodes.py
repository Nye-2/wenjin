"""create executions and execution_nodes tables

Revision ID: 030_create_executions_and_execution_nodes
Revises: 029_add_subagent_output
Create Date: 2026-05-08 21:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "030_create_executions_and_execution_nodes"
down_revision: Union[str, None] = "029_add_subagent_output"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create executions table
    op.create_table(
        "executions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True, index=True),
        sa.Column("thread_id", sa.String(length=36), nullable=True, index=True),
        sa.Column("execution_type", sa.String(length=20), nullable=False, index=True),
        sa.Column("workspace_type", sa.String(length=50), nullable=True),
        sa.Column("feature_id", sa.String(length=100), nullable=True, index=True),
        sa.Column("entry_skill_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, default="pending", index=True),
        sa.Column("params", sa.JSON(), nullable=False, default=dict),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("graph_structure", sa.JSON(), nullable=True),
        sa.Column("node_states", sa.JSON(), nullable=False, default=dict),
        sa.Column("runtime_state", sa.JSON(), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False, default=0),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("artifact_ids", sa.JSON(), nullable=False, default=list),
        sa.Column("next_actions", sa.JSON(), nullable=False, default=list),
        sa.Column("advisory_code", sa.String(length=100), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("dispatch_mode", sa.String(length=20), nullable=True),
        sa.Column("worker_task_id", sa.String(length=36), nullable=True),
        sa.Column(
            "parent_execution_id",
            sa.String(length=36),
            sa.ForeignKey("executions.id"),
            nullable=True,
        ),
        sa.Column("child_execution_ids", sa.JSON(), nullable=False, default=list),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Composite indexes for executions
    op.create_index("ix_executions_user_status", "executions", ["user_id", "status"])
    op.create_index("ix_executions_workspace_feature_status", "executions", ["workspace_id", "feature_id", "status"])
    op.create_index("ix_executions_thread_created", "executions", ["thread_id", "created_at"])
    op.create_index("ix_executions_parent", "executions", ["parent_execution_id"])
    op.create_index("ix_executions_type_status", "executions", ["execution_type", "status"])

    # Create execution_nodes table
    op.create_table(
        "execution_nodes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "execution_id",
            sa.String(length=36),
            sa.ForeignKey("executions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "parent_node_id",
            sa.String(length=36),
            sa.ForeignKey("execution_nodes.id"),
            nullable=True,
        ),
        sa.Column("node_id", sa.String(length=100), nullable=False),
        sa.Column("node_type", sa.String(length=20), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, default="pending"),
        sa.Column("input_data", sa.JSON(), nullable=True),
        sa.Column("output_data", sa.JSON(), nullable=True),
        sa.Column("thinking", sa.Text(), nullable=True),
        sa.Column("tool_calls", sa.JSON(), nullable=True),
        sa.Column("token_usage", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("node_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Composite index for execution_nodes
    op.create_index("ix_execution_nodes_execution_node_id", "execution_nodes", ["execution_id", "node_id"])

    # Add execution_id to subagent_task_records (nullable during migration)
    op.add_column(
        "subagent_task_records",
        sa.Column("execution_id", sa.String(length=36), sa.ForeignKey("executions.id"), nullable=True),
    )
    op.create_index("ix_subagent_task_records_execution", "subagent_task_records", ["execution_id"])


def downgrade() -> None:
    op.drop_index("ix_subagent_task_records_execution", table_name="subagent_task_records")
    op.drop_column("subagent_task_records", "execution_id")

    op.drop_index("ix_execution_nodes_execution_node_id", table_name="execution_nodes")
    op.drop_table("execution_nodes")

    op.drop_index("ix_executions_type_status", table_name="executions")
    op.drop_index("ix_executions_parent", table_name="executions")
    op.drop_index("ix_executions_thread_created", table_name="executions")
    op.drop_index("ix_executions_workspace_feature_status", table_name="executions")
    op.drop_index("ix_executions_user_status", table_name="executions")
    op.drop_table("executions")
