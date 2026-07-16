"""remove obsolete thread-level skill selection

Revision ID: 099_thread_skill_cutover
Revises: 098_mission_user_projection_index
"""

from alembic import op

revision = "099_thread_skill_cutover"
down_revision = "098_mission_user_projection_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("generation_records")
    op.drop_column("threads", "skill")


def downgrade() -> None:
    raise RuntimeError("099 is an irreversible development cutover; reseed instead")
