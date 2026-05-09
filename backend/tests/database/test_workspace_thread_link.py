"""Model contract tests for the workspace.thread_id 1:1 FK link."""

from sqlalchemy import UniqueConstraint

from src.database.models.workspace import Workspace


def test_workspace_has_thread_id_column() -> None:
    """Workspace model must declare a thread_id column."""
    cols = {c.name for c in Workspace.__table__.columns}
    assert "thread_id" in cols


def test_workspace_thread_id_is_nullable() -> None:
    """thread_id must be nullable (workspaces can exist without a thread)."""
    col = Workspace.__table__.columns["thread_id"]
    assert col.nullable is True


def test_workspace_thread_id_unique_constraint() -> None:
    """thread_id must carry a unique constraint (1:1 cardinality)."""
    unique_cols: set[str] = set()
    for constraint in Workspace.__table__.constraints:
        if isinstance(constraint, UniqueConstraint):
            for col in constraint.columns:
                unique_cols.add(col.name)
    # Also accept a column-level unique index
    for idx in Workspace.__table__.indexes:
        if idx.unique:
            for col in idx.columns:
                unique_cols.add(col.name)
    assert "thread_id" in unique_cols, (
        "thread_id must have a unique constraint or unique index"
    )


def test_workspace_thread_id_foreign_key_targets_threads() -> None:
    """thread_id FK must reference threads.id."""
    col = Workspace.__table__.columns["thread_id"]
    fk_targets = {fk.target_fullname for fk in col.foreign_keys}
    assert "threads.id" in fk_targets


def test_workspace_thread_relationship_exists() -> None:
    """Workspace model must expose a 'thread' relationship attribute."""
    assert hasattr(Workspace, "thread"), (
        "Workspace must have a 'thread' relationship attribute"
    )
