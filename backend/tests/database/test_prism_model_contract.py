"""Model-level contracts for canonical Prism integration state."""

from __future__ import annotations

from src.database.models.prism import (
    PrismProtectedSection,
    PrismReviewItem,
    PrismSourceLink,
)


def test_prism_review_items_are_unique_per_project_logical_key() -> None:
    constraint_names = {
        constraint.name
        for constraint in PrismReviewItem.__table__.constraints
        if constraint.name
    }
    index_names = {index.name for index in PrismReviewItem.__table__.indexes}

    assert "uq_prism_review_items_project_logical_key" in constraint_names
    assert "ix_prism_review_items_workspace_status" in index_names
    assert "ix_prism_review_items_project_status" in index_names
    assert PrismReviewItem.__table__.c.preview_payload.nullable is False


def test_prism_source_links_index_workspace_and_source() -> None:
    index_names = {index.name for index in PrismSourceLink.__table__.indexes}

    assert "ix_prism_source_links_workspace" in index_names
    assert "ix_prism_source_links_source" in index_names
    assert "ix_prism_source_links_project_file" in index_names


def test_prism_protected_sections_are_unique_per_scope() -> None:
    constraint_names = {
        constraint.name
        for constraint in PrismProtectedSection.__table__.constraints
        if constraint.name
    }
    index_names = {index.name for index in PrismProtectedSection.__table__.indexes}

    assert "uq_prism_protected_sections_scope" in constraint_names
    assert "ix_prism_protected_sections_workspace" in index_names
    assert "ix_prism_protected_sections_project" in index_names
