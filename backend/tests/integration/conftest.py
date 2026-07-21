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
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
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
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    user: Mapped["FixtureUser"] = relationship("FixtureUser", back_populates="workspaces")


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
        description: str | None = None
        config: dict | None = None

    class UpdateWorkspaceRequest(BaseModel):
        name: str | None = Field(None, min_length=1, max_length=255)
        description: str | None = None
        config: dict | None = None

    class WorkspaceResponse(BaseModel):
        id: str
        user_id: str
        name: str
        type: str
        description: str | None
        config: dict

        model_config = ConfigDict(from_attributes=True)

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
        title="Test Wenjin API",
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
        description="A test workspace for integration tests",
        config={},
    )
    test_session.add(workspace)
    await test_session.commit()
    await test_session.refresh(workspace)
    return workspace


def make_authenticated_client(client: AsyncClient, access_token: str) -> AsyncClient:
    """Helper to add auth header to client."""
    client.headers["Authorization"] = f"Bearer {access_token}"
    return client
