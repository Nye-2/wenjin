"""Database models for academic entities."""

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class Workspace(BaseModel):
    """Workspace model for academic projects."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    name: str
    type: str  # sci, thesis, proposal, software_copyright, patent
    discipline: str | None = None
    config: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Paper(BaseModel):
    """Paper model for academic literature."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    doi: str | None = None
    title: str
    authors: list[dict] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None
    file_path: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WorkspacePaper(BaseModel):
    """Association between Workspace and Paper."""
    workspace_id: str
    paper_id: str
    added_at: datetime = Field(default_factory=datetime.utcnow)


class PaperExtraction(BaseModel):
    """Paper extraction result."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    paper_id: str
    tier: int  # 1=engineering, 2=LLM
    structured_data: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PaperChunk(BaseModel):
    """Paper chunk for vector storage."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    paper_id: str
    workspace_id: str
    chunk_index: int
    content: str
    embedding: list[float] | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Artifact(BaseModel):
    """Academic artifact produced by skills."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    workspace_id: str
    type: str  # research_idea, methodology, framework_outline, abstract, paper_draft
    content: dict
    created_by_skill: str | None = None
    parent_artifact_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class UserKnowledge(BaseModel):
    """User knowledge for personalization."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    category: str  # preference, knowledge, context, behavior, goal
    content: str
    confidence: float = 0.7
    source: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class GenerationRecord(BaseModel):
    """Record of skill executions."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    workspace_id: str
    skill_name: str
    input_summary: str | None = None
    output_summary: str | None = None
    duration_ms: int | None = None
    token_usage: dict | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
