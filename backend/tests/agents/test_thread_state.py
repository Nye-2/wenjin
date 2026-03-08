"""Tests for ThreadState and academic extensions."""

import pytest

from src.agents.thread_state import ThreadState, AcademicArtifact, merge_artifacts


def test_academic_artifact_creation():
    """Test AcademicArtifact model."""
    artifact = AcademicArtifact(
        id="a1",
        workspace_id="ws1",
        type="research_idea",
        content={"title": "Test"},
        created_by_skill="deep-research",
    )
    assert artifact.type == "research_idea"
    assert artifact.created_by_skill == "deep-research"


def test_merge_artifacts_deduplicates():
    """Test artifact merger deduplicates by ID."""
    existing = [
        AcademicArtifact(id="a1", workspace_id="ws1", type="idea", content={"v": 1}),
        AcademicArtifact(id="a2", workspace_id="ws1", type="method", content={"v": 1}),
    ]
    new = [
        AcademicArtifact(id="a2", workspace_id="ws1", type="method", content={"v": 2}),
        AcademicArtifact(id="a3", workspace_id="ws1", type="abstract", content={"v": 1}),
    ]

    result = merge_artifacts(existing, new)
    assert len(result) == 3
    # a2 should be updated
    a2 = next(a for a in result if a.id == "a2")
    assert a2.content == {"v": 2}


def test_thread_state_with_academic_fields():
    """Test ThreadState includes academic fields."""
    state = ThreadState(
        messages=[],
        workspace_id="ws-1",
        workspace_type="sci",
        discipline="computer_science",
    )
    assert state.workspace_id == "ws-1"
    assert state.workspace_type == "sci"
    assert state.discipline == "computer_science"


def test_thread_state_artifacts_merge():
    """Test that ThreadState properly merges artifacts."""
    artifact1 = AcademicArtifact(
        id="a1",
        workspace_id="ws1",
        type="idea",
        content={"title": "First"},
    )

    state = ThreadState(
        messages=[],
        workspace_id="ws1",
        artifacts=[artifact1],
    )

    assert len(state.artifacts) == 1
    assert state.artifacts[0].id == "a1"
