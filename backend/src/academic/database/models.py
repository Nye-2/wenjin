"""Database models for academic entities."""

from datetime import datetime
from typing import Optional, Any
from uuid import uuid4

from pydantic import BaseModel, Field


class Workspace(BaseModel):
    """Workspace model for academic projects."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    name: str
    type: str  # sci, thesis, proposal, grant
    discipline: Optional[str] = None
    config: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Paper(BaseModel):
    """Paper model for academic literature."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    doi: Optional[str] = None
    title: str
    authors: list[dict] = Field(default_factory=list)
    year: Optional[int] = None
    venue: Optional[str] = None
    abstract: Optional[str] = None
    file_path: Optional[str] = None
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
    embedding: Optional[list[float]] = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Artifact(BaseModel):
    """Academic artifact produced by skills."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    workspace_id: str
    type: str  # research_idea, methodology, framework_outline, abstract, paper_draft
    content: dict
    created_by_skill: Optional[str] = None
    parent_artifact_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class UserKnowledge(BaseModel):
    """User knowledge for personalization."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    category: str  # preference, knowledge, context, behavior, goal
    content: str
    confidence: float = 0.7
    source: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class GenerationRecord(BaseModel):
    """Record of skill executions."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    workspace_id: str
    skill_name: str
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    duration_ms: Optional[int] = None
    token_usage: Optional[dict] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
