"""Model-level contracts for workspace-owned LaTeX projects."""

from __future__ import annotations

from src.database.models.latex_project import LatexProject
from src.database.models.latex_template import LatexTemplate


def test_latex_project_enforces_one_primary_manuscript_per_workspace() -> None:
    index = next(
        (
            item
            for item in LatexProject.__table__.indexes
            if item.name == "uq_latex_projects_workspace_primary_manuscript"
        ),
        None,
    )

    assert index is not None
    assert index.unique is True
    assert [column.name for column in index.columns] == ["workspace_id"]
    assert index.dialect_options["postgresql"]["where"] is not None
    assert index.dialect_options["sqlite"]["where"] is not None


def test_latex_template_has_metadata_json_column() -> None:
    column = LatexTemplate.__table__.columns.get("metadata_json")

    assert column is not None
    assert column.nullable is False
