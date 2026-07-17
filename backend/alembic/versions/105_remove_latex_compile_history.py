"""Remove obsolete LaTeX compile history persistence.

Revision ID: 105_remove_latex_compile_history
Revises: 104_remove_dataservice_sandbox
"""

from alembic import op

revision = "105_remove_latex_compile_history"
down_revision = "104_remove_dataservice_sandbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        raise RuntimeError("105_remove_latex_compile_history targets PostgreSQL only")

    op.drop_table("latex_compile_history")


def downgrade() -> None:
    raise RuntimeError("105 is an irreversible development cutover; reseed instead")
