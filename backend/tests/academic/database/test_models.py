"""Tests for academic database models."""

import pytest
from datetime import datetime

from src.database import (
    Workspace,
    WorkspaceType,
    Paper,
    WorkspacePaper,
    PaperExtraction,
    PaperChunk,
    PaperSection,
    Artifact,
    ArtifactType,
    UserKnowledge,
    KnowledgeCategory,
    GenerationRecord,
)
from src.database.base import generate_uuid


def test_workspace_creation():
    """Test Workspace model instantiation."""
    workspace_id = generate_uuid()
    workspace = Workspace(
        id=workspace_id,
        user_id="user-1",
        name="Test Workspace",
        type="sci",
        discipline="computer_science",
    )
    assert workspace.name == "Test Workspace"
    assert workspace.type == "sci"
    assert workspace.discipline == "computer_science"
    assert workspace.id == workspace_id


def test_workspace_type_enum():
    """Test WorkspaceType enum values."""
    assert WorkspaceType.SCI.value == "sci"
    assert WorkspaceType.THESIS.value == "thesis"
    assert WorkspaceType.PROPOSAL.value == "proposal"
    assert WorkspaceType.GRANT.value == "grant"
    assert WorkspaceType.LITERATURE_REVIEW.value == "literature_review"


def test_paper_creation():
    """Test Paper model instantiation."""
    paper_id = generate_uuid()
    paper = Paper(
        id=paper_id,
        doi="10.1234/test",
        title="Test Paper",
        authors=[{"name": "Author One"}],
        year=2024,
        source="manual_upload",  # Explicitly set since SQLAlchemy default is DB-level
    )
    assert paper.doi == "10.1234/test"
    assert paper.year == 2024
    assert paper.id == paper_id
    assert paper.source == "manual_upload"


def test_paper_authors_property():
    """Test Paper author_names property."""
    paper = Paper(
        title="Test Paper",
        authors=[
            {"name": "Author One"},
            {"name": "Author Two"},
        ],
    )
    assert paper.author_names == ["Author One", "Author Two"]
    assert paper.first_author == "Author One"


def test_workspace_paper_creation():
    """Test WorkspacePaper association model."""
    workspace_paper = WorkspacePaper(
        workspace_id="ws-1",
        paper_id="paper-1",
        notes="Important paper",
        tags=["primary", "methodology"],
        is_primary=True,
        read_status="unread",  # Explicitly set
    )
    assert workspace_paper.notes == "Important paper"
    assert workspace_paper.is_primary == True
    assert workspace_paper.read_status == "unread"


def test_paper_extraction_creation():
    """Test PaperExtraction model."""
    extraction = PaperExtraction(
        paper_id="paper-1",
        tier=1,
        extraction_type="metadata",
        structured_data={"sections": ["abstract", "introduction"]},
        processing_time_ms=500,
    )
    assert extraction.tier == 1
    assert extraction.extraction_type == "metadata"


def test_paper_chunk_creation():
    """Test PaperChunk model instantiation."""
    chunk_id = generate_uuid()
    chunk = PaperChunk(
        id=chunk_id,
        paper_id="paper-1",
        workspace_id="ws-1",
        chunk_index=0,
        content="This is a test chunk of paper content.",
        embedding=[0.1] * 1536,
    )
    assert chunk.chunk_index == 0
    assert len(chunk.embedding) == 1536
    assert chunk.id == chunk_id


def test_paper_section_creation():
    """Test PaperSection model instantiation."""
    section_id = generate_uuid()
    section = PaperSection(
        id=section_id,
        paper_id="paper-1",
        workspace_id="ws-1",
        section_title="Model Architecture",
        section_path="3",
        page_start=5,
        page_end=8,
        content="The Transformer uses multi-head attention mechanism...",
        level=1,
    )
    assert section.section_title == "Model Architecture"
    assert section.section_path == "3"
    assert section.page_start == 5
    assert section.page_end == 8
    assert section.level == 1
    assert section.id == section_id


def test_paper_section_subsection():
    """Test PaperSection model for nested subsection."""
    section = PaperSection(
        paper_id="paper-1",
        workspace_id="ws-1",
        section_title="Encoder Stack",
        section_path="3.1.2",
        page_start=6,
        page_end=7,
        content="The encoder is composed of a stack of N layers...",
        level=3,
    )
    assert section.section_path == "3.1.2"
    assert section.level == 3


def test_paper_with_toc():
    """Test Paper model with TOC field."""
    paper = Paper(
        title="Test Paper",
        authors=[{"name": "Author One"}],
        year=2024,
        toc=[
            {"number": "1", "title": "Introduction", "level": 1},
            {"number": "2", "title": "Background", "level": 1},
            {"number": "2.1", "title": "Related Work", "level": 2},
        ],
    )
    assert paper.toc is not None
    assert len(paper.toc) == 3
    assert paper.toc[0]["title"] == "Introduction"
    assert paper.toc[2]["level"] == 2


def test_paper_without_toc():
    """Test Paper model without TOC (nullable)."""
    paper = Paper(
        title="Test Paper",
        authors=[{"name": "Author One"}],
        year=2024,
    )
    assert paper.toc is None


def test_artifact_creation():
    """Test Artifact model instantiation."""
    artifact_id = generate_uuid()
    artifact = Artifact(
        id=artifact_id,
        workspace_id="ws-1",
        type="research_idea",
        title="Novel FL Approach",
        content={"title": "Idea", "description": "Desc"},
        created_by_skill="deep-research",
        version=1,
        status="draft",
    )
    assert artifact.type == "research_idea"
    assert artifact.created_by_skill == "deep-research"
    assert artifact.version == 1
    assert artifact.status == "draft"
    assert artifact.id == artifact_id


def test_artifact_type_enum():
    """Test ArtifactType enum values."""
    assert ArtifactType.RESEARCH_IDEA.value == "research_idea"
    assert ArtifactType.METHODOLOGY.value == "methodology"
    assert ArtifactType.FRAMEWORK_OUTLINE.value == "framework_outline"
    assert ArtifactType.ABSTRACT.value == "abstract"


def test_user_knowledge_creation():
    """Test UserKnowledge model instantiation."""
    knowledge_id = generate_uuid()
    knowledge = UserKnowledge(
        id=knowledge_id,
        user_id="user-1",
        category="preference",
        content="Prefers APA citation style",
        confidence=0.85,
        is_active=True,
    )
    assert knowledge.category == "preference"
    assert knowledge.confidence == 0.85
    assert knowledge.is_active == True
    assert knowledge.id == knowledge_id


def test_knowledge_category_enum():
    """Test KnowledgeCategory enum values."""
    assert KnowledgeCategory.PREFERENCE.value == "preference"
    assert KnowledgeCategory.KNOWLEDGE.value == "knowledge"
    assert KnowledgeCategory.CONTEXT.value == "context"
    assert KnowledgeCategory.GOAL.value == "goal"


def test_generation_record_creation():
    """Test GenerationRecord model instantiation."""
    record = GenerationRecord(
        workspace_id="ws-1",
        skill_name="deep-research",
        input_summary="Research topic: Federated Learning",
        output_summary="Generated 5 research ideas",
        duration_ms=15000,
        token_usage={"input": 500, "output": 2000, "total": 2500},
    )
    assert record.skill_name == "deep-research"
    assert record.duration_ms == 15000
    assert record.total_tokens == 2500
    assert record.input_tokens == 500
    assert record.output_tokens == 2000


def test_generation_record_token_properties():
    """Test GenerationRecord token helper properties."""
    record = GenerationRecord(
        workspace_id="ws-1",
        skill_name="test-skill",
        token_usage={"input": 100, "output": 200, "total": 300},
    )
    assert record.input_tokens == 100
    assert record.output_tokens == 200
    assert record.total_tokens == 300

    # Test with no token usage
    record_no_tokens = GenerationRecord(
        workspace_id="ws-1",
        skill_name="test-skill",
    )
    assert record_no_tokens.total_tokens == 0
    assert record_no_tokens.input_tokens == 0
    assert record_no_tokens.output_tokens == 0
