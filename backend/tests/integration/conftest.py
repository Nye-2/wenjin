"""Test fixtures for integration tests.

This module provides:
- In-memory SQLite database for testing
- Async test client fixtures
- Authentication fixtures with test tokens
- Test data factories

Note: We use SQLite-compatible test models instead of the production PostgreSQL models
to enable in-memory database testing without requiring PostgreSQL.
"""

import asyncio
from collections.abc import AsyncGenerator, Generator
from datetime import datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.pool import StaticPool

from src.services.auth import create_tokens, hash_password

# ============ Test Database Models (SQLite-compatible) ============

class TestBase(DeclarativeBase):
    """Base class for test models."""
    pass


def generate_uuid() -> str:
    """Generate a UUID string."""
    return str(uuid4())


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class FixtureUser(TestBase, TimestampMixin):
    """Test User model compatible with SQLite."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workspaces: Mapped[list["FixtureWorkspace"]] = relationship(
        "FixtureWorkspace", back_populates="user", cascade="all, delete-orphan"
    )


class FixtureWorkspace(TestBase, TimestampMixin):
    """Test Workspace model compatible with SQLite."""
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    discipline: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    user: Mapped["FixtureUser"] = relationship("FixtureUser", back_populates="workspaces")
    workspace_papers: Mapped[list["FixtureWorkspacePaper"]] = relationship(
        "FixtureWorkspacePaper", back_populates="workspace", cascade="all, delete-orphan"
    )


class FixturePaper(TestBase, TimestampMixin):
    """Test Paper model compatible with SQLite."""
    __tablename__ = "papers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    doi: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    venue: Mapped[str | None] = mapped_column(Text, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual_upload")
    external_ids: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    toc: Mapped[list | None] = mapped_column(JSON, nullable=True)
    citation_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    workspace_papers: Mapped[list["FixtureWorkspacePaper"]] = relationship(
        "FixtureWorkspacePaper", back_populates="paper", cascade="all, delete-orphan"
    )


class FixtureWorkspacePaper(TestBase, TimestampMixin):
    """Test WorkspacePaper association model compatible with SQLite."""
    __tablename__ = "workspace_papers"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paper_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_status: Mapped[str] = mapped_column(String(20), default="unread", nullable=False)

    workspace: Mapped["FixtureWorkspace"] = relationship("FixtureWorkspace", back_populates="workspace_papers")
    paper: Mapped["FixturePaper"] = relationship("FixturePaper", back_populates="workspace_papers")


# ============ Fixtures ============

# Test database URL (in-memory SQLite)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create a test database engine with in-memory SQLite."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(TestBase.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(TestBase.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def test_app(test_engine, test_session):
    """Create a test FastAPI application with overridden dependencies."""
    from collections.abc import AsyncGenerator as AG
    from contextlib import asynccontextmanager

    from fastapi import Depends, FastAPI, HTTPException, status
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    from pydantic import BaseModel, ConfigDict, EmailStr, Field
    from sqlalchemy import select

    # ============ Request/Response Models ============

    class RegisterRequest(BaseModel):
        email: EmailStr
        password: str
        name: str | None = None

    class LoginRequest(BaseModel):
        email: EmailStr
        password: str

    class TokenResponse(BaseModel):
        access_token: str
        refresh_token: str
        token_type: str = "bearer"
        expires_in: int

    class UserResponse(BaseModel):
        id: str
        email: str
        name: str | None
        role: str

    class RefreshRequest(BaseModel):
        refresh_token: str

    class CreateWorkspaceRequest(BaseModel):
        name: str = Field(..., min_length=1, max_length=255)
        type: str
        discipline: str | None = Field(None, max_length=100)
        description: str | None = None
        config: dict | None = None

    class UpdateWorkspaceRequest(BaseModel):
        name: str | None = Field(None, min_length=1, max_length=255)
        discipline: str | None = Field(None, max_length=100)
        description: str | None = None
        config: dict | None = None

    class WorkspaceResponse(BaseModel):
        id: str
        user_id: str
        name: str
        type: str
        discipline: str | None
        description: str | None
        config: dict

        model_config = ConfigDict(from_attributes=True)

    class CreatePaperRequest(BaseModel):
        workspace_id: str
        doi: str | None = None
        title: str
        authors: list | None = None
        year: int | None = None
        venue: str | None = None
        abstract: str | None = None
        file_path: str | None = None
        source: str = "manual_upload"
        external_ids: dict | None = None
        citation_count: int | None = None
        reference_count: int | None = None

    class UpdatePaperRequest(BaseModel):
        title: str | None = None
        authors: list | None = None
        year: int | None = None
        venue: str | None = None
        abstract: str | None = None
        citation_count: int | None = None
        reference_count: int | None = None

    class PaperResponse(BaseModel):
        id: str
        doi: str | None
        title: str
        authors: list
        year: int | None
        venue: str | None
        abstract: str | None
        file_path: str | None
        source: str
        external_ids: dict
        toc: list | None
        citation_count: int | None
        reference_count: int | None

        model_config = ConfigDict(from_attributes=True)

    class PapersListResponse(BaseModel):
        papers: list[PaperResponse]
        count: int

    class AddPaperRequest(BaseModel):
        notes: str | None = None
        tags: list | None = None
        is_primary: bool = False

    class SearchPapersRequest(BaseModel):
        query: str = Field(..., min_length=1)
        workspace_id: str | None = None
        limit: int = Field(default=10, ge=1, le=100)

    # ============ Auth Helpers ============

    security = HTTPBearer(auto_error=False)

    async def get_current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
    ) -> FixtureUser:
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )
        from src.services.auth import verify_access_token
        token_data = verify_access_token(credentials.credentials)
        if token_data is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        result = await test_session.execute(
            select(FixtureUser).where(FixtureUser.id == token_data.user_id)
        )
        user = result.scalar_one_or_none()
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        return user

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AG[None, None]:
        yield

    app = FastAPI(
        title="Test AcademiaGPT API",
        version="2.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ============ Auth Routes ============

    @app.post("/api/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
    async def register(request: RegisterRequest):
        result = await test_session.execute(
            select(FixtureUser).where(FixtureUser.email == request.email.lower())
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already registered")

        try:
            hashed_pw = hash_password(request.password)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        user = FixtureUser(
            email=request.email.lower().strip(),
            name=request.name or request.email.split("@")[0],
            hashed_password=hashed_pw,
            is_active=True,
            is_superuser=False,
        )
        test_session.add(user)
        await test_session.commit()
        await test_session.refresh(user)

        tokens = create_tokens(str(user.id), user.email, "user")
        return TokenResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_type=tokens.token_type,
            expires_in=tokens.expires_in,
        )

    @app.post("/api/auth/login", response_model=TokenResponse)
    async def login(request: LoginRequest):
        result = await test_session.execute(
            select(FixtureUser).where(FixtureUser.email == request.email.lower())
        )
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        from src.services.auth import verify_password
        if not verify_password(request.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        tokens = create_tokens(str(user.id), user.email, "admin" if user.is_superuser else "user")
        return TokenResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_type=tokens.token_type,
            expires_in=tokens.expires_in,
        )

    @app.post("/api/auth/refresh", response_model=TokenResponse)
    async def refresh_token(request: RefreshRequest):
        from src.services.auth import verify_refresh_token
        user_id = verify_refresh_token(request.refresh_token)
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

        result = await test_session.execute(select(FixtureUser).where(FixtureUser.id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User not found")

        tokens = create_tokens(str(user.id), user.email, "admin" if user.is_superuser else "user")
        return TokenResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_type=tokens.token_type,
            expires_in=tokens.expires_in,
        )

    @app.get("/api/auth/me", response_model=UserResponse)
    async def get_me(current_user: FixtureUser = Depends(get_current_user)):
        return UserResponse(
            id=str(current_user.id),
            email=current_user.email,
            name=current_user.name,
            role="admin" if current_user.is_superuser else "user",
        )

    # ============ Workspace Routes ============

    @app.post("/api/workspaces", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
    async def create_workspace(request: CreateWorkspaceRequest, user_id: str):
        valid_types = [
            "sci",
            "thesis",
            "proposal",
            "software_copyright",
            "patent",
        ]
        if request.type not in valid_types:
            raise HTTPException(status_code=400, detail=f"Invalid workspace type: {request.type}")

        workspace = FixtureWorkspace(
            user_id=user_id,
            name=request.name,
            type=request.type,
            discipline=request.discipline,
            description=request.description,
            config=request.config or {},
        )
        test_session.add(workspace)
        await test_session.commit()
        await test_session.refresh(workspace)
        return WorkspaceResponse(
            id=str(workspace.id),
            user_id=str(workspace.user_id),
            name=workspace.name,
            type=workspace.type,
            discipline=workspace.discipline,
            description=workspace.description,
            config=workspace.config or {},
        )

    @app.get("/api/workspaces", response_model=list[WorkspaceResponse])
    async def list_workspaces(user_id: str):
        result = await test_session.execute(
            select(FixtureWorkspace).where(FixtureWorkspace.user_id == user_id).order_by(FixtureWorkspace.updated_at.desc())
        )
        workspaces = result.scalars().all()
        return [
            WorkspaceResponse(
                id=str(w.id),
                user_id=str(w.user_id),
                name=w.name,
                type=w.type,
                discipline=w.discipline,
                description=w.description,
                config=w.config or {},
            )
            for w in workspaces
        ]

    @app.get("/api/workspaces/{workspace_id}", response_model=WorkspaceResponse)
    async def get_workspace(workspace_id: str):
        result = await test_session.execute(select(FixtureWorkspace).where(FixtureWorkspace.id == workspace_id))
        workspace = result.scalar_one_or_none()
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")
        return WorkspaceResponse(
            id=str(workspace.id),
            user_id=str(workspace.user_id),
            name=workspace.name,
            type=workspace.type,
            discipline=workspace.discipline,
            description=workspace.description,
            config=workspace.config or {},
        )

    @app.put("/api/workspaces/{workspace_id}", response_model=WorkspaceResponse)
    async def update_workspace(workspace_id: str, request: UpdateWorkspaceRequest):
        result = await test_session.execute(select(FixtureWorkspace).where(FixtureWorkspace.id == workspace_id))
        workspace = result.scalar_one_or_none()
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        update_data = request.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if hasattr(workspace, key) and value is not None:
                setattr(workspace, key, value)

        await test_session.commit()
        await test_session.refresh(workspace)
        return WorkspaceResponse(
            id=str(workspace.id),
            user_id=str(workspace.user_id),
            name=workspace.name,
            type=workspace.type,
            discipline=workspace.discipline,
            description=workspace.description,
            config=workspace.config or {},
        )

    @app.delete("/api/workspaces/{workspace_id}")
    async def delete_workspace(workspace_id: str):
        result = await test_session.execute(select(FixtureWorkspace).where(FixtureWorkspace.id == workspace_id))
        workspace = result.scalar_one_or_none()
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")
        await test_session.delete(workspace)
        await test_session.commit()
        return {"success": True}

    @app.get("/api/workspaces/{workspace_id}/papers", response_model=PapersListResponse)
    async def list_workspace_papers(workspace_id: str, read_status: str | None = None):
        query = (
            select(FixturePaper)
            .join(FixtureWorkspacePaper, FixturePaper.id == FixtureWorkspacePaper.paper_id)
            .where(FixtureWorkspacePaper.workspace_id == workspace_id)
        )
        if read_status:
            query = query.where(FixtureWorkspacePaper.read_status == read_status)
        query = query.order_by(FixtureWorkspacePaper.created_at.desc())
        result = await test_session.execute(query)
        papers = result.scalars().all()
        return PapersListResponse(
            papers=[
                PaperResponse(
                    id=str(p.id),
                    doi=p.doi,
                    title=p.title,
                    authors=p.authors or [],
                    year=p.year,
                    venue=p.venue,
                    abstract=p.abstract,
                    file_path=p.file_path,
                    source=p.source,
                    external_ids=p.external_ids or {},
                    toc=p.toc,
                    citation_count=p.citation_count,
                    reference_count=p.reference_count,
                )
                for p in papers
            ],
            count=len(papers),
        )

    @app.post("/api/workspaces/{workspace_id}/papers/{paper_id}")
    async def add_paper_to_workspace(workspace_id: str, paper_id: str, request: AddPaperRequest):
        result = await test_session.execute(
            select(FixtureWorkspacePaper).where(
                FixtureWorkspacePaper.workspace_id == workspace_id,
                FixtureWorkspacePaper.paper_id == paper_id,
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"Paper {paper_id} is already in workspace {workspace_id}")

        wp = FixtureWorkspacePaper(
            workspace_id=workspace_id,
            paper_id=paper_id,
            notes=request.notes,
            tags=request.tags or [],
            is_primary=request.is_primary,
        )
        test_session.add(wp)
        await test_session.commit()
        return {"success": True, "paper_id": paper_id}

    @app.delete("/api/workspaces/{workspace_id}/papers/{paper_id}")
    async def remove_paper_from_workspace(workspace_id: str, paper_id: str):
        result = await test_session.execute(
            select(FixtureWorkspacePaper).where(
                FixtureWorkspacePaper.workspace_id == workspace_id,
                FixtureWorkspacePaper.paper_id == paper_id,
            )
        )
        wp = result.scalar_one_or_none()
        if not wp:
            raise HTTPException(status_code=404, detail="Paper not found in workspace")
        await test_session.delete(wp)
        await test_session.commit()
        return {"success": True}

    # ============ Paper Routes ============

    @app.post("/api/papers", response_model=PaperResponse, status_code=status.HTTP_201_CREATED)
    async def create_paper(request: CreatePaperRequest):
        paper = FixturePaper(
            doi=request.doi,
            title=request.title,
            authors=request.authors or [],
            year=request.year,
            venue=request.venue,
            abstract=request.abstract,
            file_path=request.file_path,
            source=request.source,
            external_ids=request.external_ids or {},
            citation_count=request.citation_count,
            reference_count=request.reference_count,
        )
        test_session.add(paper)
        await test_session.flush()

        workspace_paper = FixtureWorkspacePaper(
            workspace_id=request.workspace_id,
            paper_id=str(paper.id),
            notes=None,
            tags=[],
            is_primary=False,
            read_status="unread",
        )
        test_session.add(workspace_paper)
        await test_session.commit()
        await test_session.refresh(paper)
        return PaperResponse(
            id=str(paper.id),
            doi=paper.doi,
            title=paper.title,
            authors=paper.authors or [],
            year=paper.year,
            venue=paper.venue,
            abstract=paper.abstract,
            file_path=paper.file_path,
            source=paper.source,
            external_ids=paper.external_ids or {},
            toc=paper.toc,
            citation_count=paper.citation_count,
            reference_count=paper.reference_count,
        )

    @app.get("/api/papers", response_model=list[PaperResponse])
    async def list_papers(workspace_id: str | None = None, limit: int = 20):
        if workspace_id:
            query = (
                select(FixturePaper)
                .join(FixtureWorkspacePaper, FixturePaper.id == FixtureWorkspacePaper.paper_id)
                .where(FixtureWorkspacePaper.workspace_id == workspace_id)
                .order_by(FixtureWorkspacePaper.created_at.desc())
                .limit(limit)
            )
        else:
            query = select(FixturePaper).order_by(FixturePaper.created_at.desc()).limit(limit)
        result = await test_session.execute(query)
        papers = result.scalars().all()
        return [
            PaperResponse(
                id=str(p.id),
                doi=p.doi,
                title=p.title,
                authors=p.authors or [],
                year=p.year,
                venue=p.venue,
                abstract=p.abstract,
                file_path=p.file_path,
                source=p.source,
                external_ids=p.external_ids or {},
                toc=p.toc,
                citation_count=p.citation_count,
                reference_count=p.reference_count,
            )
            for p in papers
        ]

    @app.get("/api/papers/{paper_id}", response_model=PaperResponse)
    async def get_paper(paper_id: str):
        result = await test_session.execute(select(FixturePaper).where(FixturePaper.id == paper_id))
        paper = result.scalar_one_or_none()
        if not paper:
            raise HTTPException(status_code=404, detail=f"Paper not found: {paper_id}")
        return PaperResponse(
            id=str(paper.id),
            doi=paper.doi,
            title=paper.title,
            authors=paper.authors or [],
            year=paper.year,
            venue=paper.venue,
            abstract=paper.abstract,
            file_path=paper.file_path,
            source=paper.source,
            external_ids=paper.external_ids or {},
            toc=paper.toc,
            citation_count=paper.citation_count,
            reference_count=paper.reference_count,
        )

    @app.put("/api/papers/{paper_id}", response_model=PaperResponse)
    async def update_paper(paper_id: str, request: UpdatePaperRequest):
        result = await test_session.execute(select(FixturePaper).where(FixturePaper.id == paper_id))
        paper = result.scalar_one_or_none()
        if not paper:
            raise HTTPException(status_code=404, detail=f"Paper not found: {paper_id}")

        update_data = request.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if hasattr(paper, key) and value is not None:
                setattr(paper, key, value)

        await test_session.commit()
        await test_session.refresh(paper)
        return PaperResponse(
            id=str(paper.id),
            doi=paper.doi,
            title=paper.title,
            authors=paper.authors or [],
            year=paper.year,
            venue=paper.venue,
            abstract=paper.abstract,
            file_path=paper.file_path,
            source=paper.source,
            external_ids=paper.external_ids or {},
            toc=paper.toc,
            citation_count=paper.citation_count,
            reference_count=paper.reference_count,
        )

    @app.delete("/api/papers/{paper_id}")
    async def delete_paper(paper_id: str):
        result = await test_session.execute(select(FixturePaper).where(FixturePaper.id == paper_id))
        paper = result.scalar_one_or_none()
        if not paper:
            raise HTTPException(status_code=404, detail=f"Paper not found: {paper_id}")
        await test_session.delete(paper)
        await test_session.commit()
        return {"success": True, "message": f"Paper {paper_id} deleted"}

    @app.post("/api/papers/search")
    async def search_papers(request: SearchPapersRequest):
        from sqlalchemy import or_
        if request.workspace_id:
            query = (
                select(FixturePaper)
                .join(FixtureWorkspacePaper, FixturePaper.id == FixtureWorkspacePaper.paper_id)
                .where(FixtureWorkspacePaper.workspace_id == request.workspace_id)
                .where(
                    or_(
                        FixturePaper.title.ilike(f"%{request.query}%"),
                        FixturePaper.abstract.ilike(f"%{request.query}%"),
                    )
                )
                .limit(request.limit)
            )
        else:
            query = (
                select(FixturePaper)
                .where(
                    or_(
                        FixturePaper.title.ilike(f"%{request.query}%"),
                        FixturePaper.abstract.ilike(f"%{request.query}%"),
                    )
                )
                .limit(request.limit)
            )
        result = await test_session.execute(query)
        papers = result.scalars().all()
        return {
            "query": request.query,
            "count": len(papers),
            "papers": [
                PaperResponse(
                    id=str(p.id),
                    doi=p.doi,
                    title=p.title,
                    authors=p.authors or [],
                    year=p.year,
                    venue=p.venue,
                    abstract=p.abstract,
                    file_path=p.file_path,
                    source=p.source,
                    external_ids=p.external_ids or {},
                    toc=p.toc,
                    citation_count=p.citation_count,
                    reference_count=p.reference_count,
                )
                for p in papers
            ],
        }

    yield app


@pytest_asyncio.fixture(scope="function")
async def client(test_app) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest_asyncio.fixture(scope="function")
async def test_user(test_session: AsyncSession) -> FixtureUser:
    """Create a test user."""
    user = FixtureUser(
        email="testuser@example.com",
        name="Test User",
        hashed_password=hash_password("testpassword123"),
        is_active=True,
        is_superuser=False,
    )
    test_session.add(user)
    await test_session.commit()
    await test_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def test_admin(test_session: AsyncSession) -> FixtureUser:
    """Create a test admin user."""
    user = FixtureUser(
        email="admin@example.com",
        name="Admin User",
        hashed_password=hash_password("adminpassword123"),
        is_active=True,
        is_superuser=True,
    )
    test_session.add(user)
    await test_session.commit()
    await test_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def test_user_tokens(test_user: FixtureUser) -> dict:
    """Create tokens for test user."""
    tokens = create_tokens(
        user_id=str(test_user.id),
        email=test_user.email,
        role="user",
    )
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": tokens.token_type,
        "expires_in": tokens.expires_in,
    }


@pytest_asyncio.fixture(scope="function")
async def authenticated_client(
    client: AsyncClient,
    test_user_tokens: dict,
) -> AsyncClient:
    """Create an authenticated test client."""
    client.headers["Authorization"] = f"Bearer {test_user_tokens['access_token']}"
    return client


@pytest_asyncio.fixture(scope="function")
async def test_workspace(test_session: AsyncSession, test_user: FixtureUser) -> FixtureWorkspace:
    """Create a test workspace."""
    workspace = FixtureWorkspace(
        user_id=str(test_user.id),
        name="Test Workspace",
        type="sci",
        discipline="computer_science",
        description="A test workspace for integration tests",
        config={},
    )
    test_session.add(workspace)
    await test_session.commit()
    await test_session.refresh(workspace)
    return workspace


@pytest_asyncio.fixture(scope="function")
async def test_paper(test_session: AsyncSession) -> FixturePaper:
    """Create a test paper."""
    paper = FixturePaper(
        doi="10.1234/test.2024.001",
        title="A Test Paper for Integration Testing",
        authors=[
            {"name": "John Doe", "affiliation": "Test University"},
            {"name": "Jane Smith", "affiliation": "Test Institute"},
        ],
        year=2024,
        venue="International Conference on Testing",
        abstract="This is a test abstract for integration testing purposes.",
        source="manual_upload",
    )
    test_session.add(paper)
    await test_session.commit()
    await test_session.refresh(paper)
    return paper


@pytest_asyncio.fixture(scope="function")
async def test_workspace_paper(
    test_session: AsyncSession,
    test_workspace: FixtureWorkspace,
    test_paper: FixturePaper,
) -> FixtureWorkspacePaper:
    """Create a test workspace-paper association."""
    workspace_paper = FixtureWorkspacePaper(
        workspace_id=str(test_workspace.id),
        paper_id=str(test_paper.id),
        notes="Test notes for this paper",
        tags=["test", "integration"],
        is_primary=False,
        read_status="unread",
    )
    test_session.add(workspace_paper)
    await test_session.commit()
    await test_session.refresh(workspace_paper)
    return workspace_paper


def make_authenticated_client(client: AsyncClient, access_token: str) -> AsyncClient:
    """Helper to add auth header to client."""
    client.headers["Authorization"] = f"Bearer {access_token}"
    return client
