"""add credit and admin dashboard related schema

Revision ID: 005_credit_dashboard
Revises: 004_workspace_literature
Create Date: 2026-03-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "005_credit_dashboard"
down_revision: Union[str, None] = "004_workspace_literature"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


credit_transaction_type = sa.Enum(
    "admin_grant",
    "admin_deduct",
    "workflow_consume",
    "registration_bonus",
    "refund",
    name="credit_transaction_type",
)

admin_action_type = sa.Enum(
    "credit_grant",
    "credit_deduct",
    "user_role_change",
    "user_status_change",
    name="admin_action_type",
)


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("credits", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("total_credits_earned", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("total_credits_spent", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_users_credits", "users", ["credits"], unique=False)

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        credit_transaction_type.create(bind, checkfirst=True)
        admin_action_type.create(bind, checkfirst=True)

    op.create_table(
        "credit_transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("transaction_type", credit_transaction_type, nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("feature_id", sa.String(100), nullable=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("task_id", sa.String(36), nullable=True),
        sa.Column(
            "admin_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_credit_transactions_user_id", "credit_transactions", ["user_id"], unique=False)
    op.create_index(
        "ix_credit_transactions_transaction_type",
        "credit_transactions",
        ["transaction_type"],
        unique=False,
    )
    op.create_index("ix_credit_transactions_workspace_id", "credit_transactions", ["workspace_id"], unique=False)
    op.create_index("ix_credit_transactions_task_id", "credit_transactions", ["task_id"], unique=False)
    op.create_index("ix_credit_transactions_admin_id", "credit_transactions", ["admin_id"], unique=False)
    op.create_index("ix_credit_transactions_created_at", "credit_transactions", ["created_at"], unique=False)
    op.create_index(
        "idx_credit_user_created",
        "credit_transactions",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_credit_type_created",
        "credit_transactions",
        ["transaction_type", "created_at"],
        unique=False,
    )

    op.create_table(
        "admin_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "admin_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", admin_action_type, nullable=False),
        sa.Column("target_type", sa.String(50), nullable=False, server_default="user"),
        sa.Column(
            "target_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("details", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_admin_logs_admin_id", "admin_logs", ["admin_id"], unique=False)
    op.create_index("ix_admin_logs_action", "admin_logs", ["action"], unique=False)
    op.create_index("ix_admin_logs_target_user_id", "admin_logs", ["target_user_id"], unique=False)
    op.create_index("ix_admin_logs_created_at", "admin_logs", ["created_at"], unique=False)
    op.create_index(
        "idx_admin_log_admin_created",
        "admin_logs",
        ["admin_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_admin_log_target_user_created",
        "admin_logs",
        ["target_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_admin_log_action_created",
        "admin_logs",
        ["action", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_admin_log_action_created", table_name="admin_logs")
    op.drop_index("idx_admin_log_target_user_created", table_name="admin_logs")
    op.drop_index("idx_admin_log_admin_created", table_name="admin_logs")
    op.drop_index("ix_admin_logs_created_at", table_name="admin_logs")
    op.drop_index("ix_admin_logs_target_user_id", table_name="admin_logs")
    op.drop_index("ix_admin_logs_action", table_name="admin_logs")
    op.drop_index("ix_admin_logs_admin_id", table_name="admin_logs")
    op.drop_table("admin_logs")

    op.drop_index("idx_credit_type_created", table_name="credit_transactions")
    op.drop_index("idx_credit_user_created", table_name="credit_transactions")
    op.drop_index("ix_credit_transactions_created_at", table_name="credit_transactions")
    op.drop_index("ix_credit_transactions_admin_id", table_name="credit_transactions")
    op.drop_index("ix_credit_transactions_task_id", table_name="credit_transactions")
    op.drop_index("ix_credit_transactions_workspace_id", table_name="credit_transactions")
    op.drop_index("ix_credit_transactions_transaction_type", table_name="credit_transactions")
    op.drop_index("ix_credit_transactions_user_id", table_name="credit_transactions")
    op.drop_table("credit_transactions")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        admin_action_type.drop(bind, checkfirst=True)
        credit_transaction_type.drop(bind, checkfirst=True)

    op.drop_index("ix_users_credits", table_name="users")
    op.drop_column("users", "total_credits_spent")
    op.drop_column("users", "total_credits_earned")
    op.drop_column("users", "credits")
