"""Unarchive workspace_references — migration 042 was wrong

042_archive_legacy_tables renamed ``workspace_references`` →
``_legacy_workspace_references`` on the premise that the table was
superseded by the new ``reference_*`` subsystem (reference_assets,
reference_text_units, reference_outline_nodes, etc).  That premise was
false: the ``reference_*`` tables *augment* the canonical reference list
with fulltext / outline / asset records.  The canonical list itself
still lives in ``workspace_references`` — referenced by ``WorkspaceReference``
in ``backend/src/database/models/reference.py:152`` and queried live by
``services/references/service.py``, ``agents/middlewares/execution.py``,
``services/dashboard/thesis.py`` and ``gateway/routers/latex_helpers.py``.

After 042 applied, every chat turn that touched citation state crashed
with::

    sqlalchemy.exc.ProgrammingError: relation "workspace_references" does not exist

This migration renames it back.  If the legacy alias does not exist on
disk (fresh install where 042 ran on an empty DB) the rename is a no-op.

Revision ID: 044_unarchive_workspace_references
Revises: 043_capability_skill_closed_loop
Create Date: 2026-05-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "044_unarchive_workspace_references"
down_revision: str | None = "043_capability_skill_closed_loop"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(table_name: str) -> bool:
    return table_name in set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    # Only rename if the legacy alias is still parked there and the canonical
    # name is free.  Both checks make the migration safe to re-run on a DB
    # that's already in the desired shape.
    if _has_table("_legacy_workspace_references") and not _has_table(
        "workspace_references"
    ):
        op.rename_table("_legacy_workspace_references", "workspace_references")


def downgrade() -> None:
    if _has_table("workspace_references") and not _has_table(
        "_legacy_workspace_references"
    ):
        op.rename_table("workspace_references", "_legacy_workspace_references")
