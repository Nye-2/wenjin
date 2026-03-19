"""legacy toc bridge revision

Revision ID: 20260309_toc
Revises: 001_initial
Create Date: 2026-03-09

This revision is intentionally a no-op.

Background:
- Some local databases were stamped with `20260309_toc` in earlier branches.
- The current migration chain in this repository starts from `001_initial`
  and then `002_task_records`.
- Without this bridge, Alembic cannot locate that legacy revision and
  fails with:
  "Can't locate revision identified by '20260309_toc'".
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "20260309_toc"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op bridge for legacy revision compatibility."""
    pass


def downgrade() -> None:
    """No-op bridge for legacy revision compatibility."""
    pass
