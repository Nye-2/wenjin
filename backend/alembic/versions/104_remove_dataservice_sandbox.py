"""Remove the obsolete DataService sandbox aggregate.

Revision ID: 104_remove_dataservice_sandbox
Revises: 103_dataservice_concurrency_fences
"""

from alembic import op

revision = "104_remove_dataservice_sandbox"
down_revision = "103_dataservice_concurrency_fences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        raise RuntimeError("104_remove_dataservice_sandbox targets PostgreSQL only")

    op.drop_table("sandbox_artifacts")
    op.drop_table("sandbox_leases")
    op.drop_table("sandbox_job_records")
    op.drop_table("sandbox_environments")
    op.drop_table("sandboxes")


def downgrade() -> None:
    raise RuntimeError("104 is an irreversible development cutover; reseed instead")
