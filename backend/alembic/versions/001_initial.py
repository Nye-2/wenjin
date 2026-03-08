"""Initial database schema

Revision ID: 001_initial
Revises:
Create Date: 2026-03-08

Creates all academic tables with pgvector support.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial database schema."""

    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("is_superuser", sa.Boolean, default=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # Create workspaces table
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("discipline", sa.String(100)),
        sa.Column("description", sa.Text),
        sa.Column("config", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_workspaces_user", "workspaces", ["user_id"])

    # Create papers table (globally shared)
    op.create_table(
        "papers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("doi", sa.String(255), unique=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("authors", postgresql.JSONB, server_default="[]"),
        sa.Column("year", sa.Integer),
        sa.Column("venue", sa.Text),
        sa.Column("abstract", sa.Text),
        sa.Column("file_path", sa.String(500)),
        sa.Column("source", sa.String(50), server_default="manual_upload"),
        sa.Column("external_ids", postgresql.JSONB, server_default="{}"),
        sa.Column("citation_count", sa.Integer),
        sa.Column("reference_count", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_papers_doi", "papers", ["doi"])
    op.create_index("ix_papers_year", "papers", ["year"])

    # Create workspace_papers association table
    op.create_table(
        "workspace_papers",
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("paper_id", sa.String(36), sa.ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("notes", sa.Text),
        sa.Column("tags", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("is_primary", sa.Boolean, default=False, nullable=False),
        sa.Column("read_status", sa.String(20), default="unread", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_workspace_papers_workspace", "workspace_papers", ["workspace_id"])
    op.create_index("ix_workspace_papers_paper", "workspace_papers", ["paper_id"])

    # Create paper_extractions table (Two-Tier extraction)
    op.create_table(
        "paper_extractions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("paper_id", sa.String(36), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tier", sa.Integer, nullable=False),
        sa.Column("extraction_type", sa.String(50), nullable=False),
        sa.Column("structured_data", postgresql.JSONB, server_default="{}"),
        sa.Column("processing_time_ms", sa.Integer),
        sa.Column("model_used", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_paper_extractions_paper", "paper_extractions", ["paper_id"])

    # Create paper_chunks table (RAG with vectors)
    op.create_table(
        "paper_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("paper_id", sa.String(36), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", sa.Text),  # Will be converted to vector type below
        sa.Column("metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_paper_chunks_paper_workspace", "paper_chunks", ["paper_id", "workspace_id"])

    # Convert embedding column to vector type and create index
    op.execute("""
        ALTER TABLE paper_chunks
        ALTER COLUMN embedding TYPE vector(1536)
        USING embedding::vector(1536)
    """)
    op.execute("""
        CREATE INDEX ix_paper_chunks_embedding
        ON paper_chunks
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)

    # Create artifacts table
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(100), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("content", postgresql.JSONB, nullable=False),
        sa.Column("created_by_skill", sa.String(100)),
        sa.Column("parent_artifact_id", sa.String(36), sa.ForeignKey("artifacts.id")),
        sa.Column("version", sa.Integer, default=1, nullable=False),
        sa.Column("status", sa.String(20), default="draft", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_artifacts_workspace_type", "artifacts", ["workspace_id", "type"])

    # Create user_knowledge table (cross-workspace)
    op.create_table(
        "user_knowledge",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("confidence", sa.Float, default=0.7, nullable=False),
        sa.Column("source", sa.String(100)),
        sa.Column("workspace_context", sa.String(36)),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_user_knowledge_user_category", "user_knowledge", ["user_id", "category"])
    op.create_index("ix_user_knowledge_confidence", "user_knowledge", ["confidence"])

    # Create generation_records table
    op.create_table(
        "generation_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("thread_id", sa.String(36)),
        sa.Column("skill_name", sa.String(100), nullable=False),
        sa.Column("model_name", sa.String(100)),
        sa.Column("input_summary", sa.Text),
        sa.Column("output_summary", sa.Text),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("token_usage", postgresql.JSONB),
        sa.Column("status", sa.String(20), default="success", nullable=False),
        sa.Column("error_message", sa.Text),
        sa.Column("metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_generation_records_workspace", "generation_records", ["workspace_id"])
    op.create_index("ix_generation_records_skill", "generation_records", ["skill_name"])
    op.create_index("ix_generation_records_created", "generation_records", ["created_at"])


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table("generation_records")
    op.drop_table("user_knowledge")
    op.drop_table("artifacts")
    op.drop_table("paper_chunks")
    op.drop_table("paper_extractions")
    op.drop_table("workspace_papers")
    op.drop_table("papers")
    op.drop_table("workspaces")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS vector")
