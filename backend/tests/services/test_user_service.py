"""Tests for user service.

This module tests the UserService class including:
- User creation with password hashing
- User retrieval by email and ID
- Authentication with email/password
- Last login timestamp updates
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.database.models.user import User
from src.services.user_service import UserService
from src.services.auth import hash_password, verify_password


# Use in-memory SQLite for testing
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_engine():
    """Create async engine for tests."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
    )
    # Only create the User table (not all models - some use JSONB which SQLite doesn't support)
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.drop)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine):
    """Create database session for tests."""
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with async_session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def user_service(db_session):
    """Create UserService instance."""
    return UserService(db_session)


class TestCreateUser:
    """Test user creation."""

    @pytest.mark.asyncio
    async def test_create_user_success(self, user_service):
        """Test successful user creation."""
        user = await user_service.create_user(
            email="test@example.com",
            password="securepassword123",
            name="Test User",
        )

        assert user is not None
        assert user.id is not None
        assert user.email == "test@example.com"
        assert user.name == "Test User"
        assert user.hashed_password != "securepassword123"
        assert verify_password("securepassword123", user.hashed_password)
        assert user.is_active is True
        assert user.is_superuser is False
        assert user.last_login is None

    @pytest.mark.asyncio
    async def test_create_user_without_name(self, user_service):
        """Test user creation without name uses email prefix."""
        user = await user_service.create_user(
            email="john.doe@example.com",
            password="securepassword123",
        )

        assert user.name == "john.doe"

    @pytest.mark.asyncio
    async def test_create_user_normalizes_email(self, user_service):
        """Test that email is normalized to lowercase."""
        user = await user_service.create_user(
            email="  TEST@EXAMPLE.COM  ",
            password="securepassword123",
        )

        assert user.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_create_user_password_too_short_raises_error(self, user_service):
        """Test that short password raises ValueError."""
        with pytest.raises(ValueError, match="密码过短"):
            await user_service.create_user(
                email="test@example.com",
                password="short",
            )

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email_raises_error(self, user_service):
        """Test that duplicate email raises IntegrityError."""
        # Create first user
        await user_service.create_user(
            email="test@example.com",
            password="securepassword123",
        )

        # Try to create second user with same email
        with pytest.raises(Exception):  # IntegrityError from SQLAlchemy
            await user_service.create_user(
                email="test@example.com",
                password="anotherpassword123",
            )


class TestGetByEmail:
    """Test get_by_email method."""

    @pytest.mark.asyncio
    async def test_get_by_email_found(self, user_service):
        """Test finding user by email."""
        created = await user_service.create_user(
            email="find@example.com",
            password="securepassword123",
        )

        found = await user_service.get_by_email("find@example.com")

        assert found is not None
        assert found.id == created.id
        assert found.email == "find@example.com"

    @pytest.mark.asyncio
    async def test_get_by_email_not_found(self, user_service):
        """Test that non-existent email returns None."""
        found = await user_service.get_by_email("nonexistent@example.com")

        assert found is None

    @pytest.mark.asyncio
    async def test_get_by_email_case_insensitive(self, user_service):
        """Test that email lookup is case-insensitive."""
        created = await user_service.create_user(
            email="case@example.com",
            password="securepassword123",
        )

        found = await user_service.get_by_email("CASE@EXAMPLE.COM")

        assert found is not None
        assert found.id == created.id


class TestGetById:
    """Test get_by_id method."""

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, user_service):
        """Test finding user by ID."""
        created = await user_service.create_user(
            email="byid@example.com",
            password="securepassword123",
        )

        found = await user_service.get_by_id(created.id)

        assert found is not None
        assert found.id == created.id
        assert found.email == "byid@example.com"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, user_service):
        """Test that non-existent ID returns None."""
        found = await user_service.get_by_id("non-existent-uuid")

        assert found is None


class TestAuthenticate:
    """Test authenticate method."""

    @pytest.mark.asyncio
    async def test_authenticate_success(self, user_service):
        """Test successful authentication."""
        created = await user_service.create_user(
            email="auth@example.com",
            password="correctpassword",
        )

        user = await user_service.authenticate("auth@example.com", "correctpassword")

        assert user is not None
        assert user.id == created.id

    @pytest.mark.asyncio
    async def test_authenticate_wrong_password(self, user_service):
        """Test authentication with wrong password returns None."""
        await user_service.create_user(
            email="auth2@example.com",
            password="correctpassword",
        )

        user = await user_service.authenticate("auth2@example.com", "wrongpassword")

        assert user is None

    @pytest.mark.asyncio
    async def test_authenticate_nonexistent_user(self, user_service):
        """Test authentication with non-existent user returns None."""
        user = await user_service.authenticate("nonexistent@example.com", "password")

        assert user is None

    @pytest.mark.asyncio
    async def test_authenticate_inactive_user(self, user_service, db_session):
        """Test authentication with inactive user returns None."""
        user = await user_service.create_user(
            email="inactive@example.com",
            password="securepassword123",
        )

        # Manually set user as inactive
        user.is_active = False
        await db_session.commit()

        result = await user_service.authenticate("inactive@example.com", "securepassword123")

        assert result is None


class TestUpdateLastLogin:
    """Test update_last_login method."""

    @pytest.mark.asyncio
    async def test_update_last_login_success(self, user_service):
        """Test successful last login update."""
        user = await user_service.create_user(
            email="login@example.com",
            password="securepassword123",
        )

        assert user.last_login is None

        updated = await user_service.update_last_login(user.id)

        assert updated is not None
        assert updated.last_login is not None
        assert isinstance(updated.last_login, datetime)

    @pytest.mark.asyncio
    async def test_update_last_login_nonexistent_user(self, user_service):
        """Test updating last login for non-existent user returns None."""
        result = await user_service.update_last_login("non-existent-uuid")

        assert result is None

    @pytest.mark.asyncio
    async def test_update_last_login_preserves_other_fields(self, user_service):
        """Test that updating last login doesn't change other fields."""
        user = await user_service.create_user(
            email="preserve@example.com",
            password="securepassword123",
            name="Original Name",
        )

        original_id = user.id
        original_name = user.name
        original_email = user.email

        updated = await user_service.update_last_login(user.id)

        assert updated.id == original_id
        assert updated.name == original_name
        assert updated.email == original_email
