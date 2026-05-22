"""Tests for DataService-backed user service."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError

from src.dataservice_client.contracts.account import AccountUserCreatePayload, AccountUserPayload
from src.services.auth import verify_password
from src.services.user_service import UserService


class FakeAccountClient:
    def __init__(self) -> None:
        self.users: dict[str, AccountUserPayload] = {}
        self.by_email: dict[str, str] = {}
        self._counter = 0

    async def create_account_user(self, command: AccountUserCreatePayload) -> AccountUserPayload:
        email = command.email.lower().strip()
        if email in self.by_email:
            raise IntegrityError("insert", {}, Exception("duplicate email"))
        self._counter += 1
        user = AccountUserPayload(
            id=f"user-{self._counter}",
            email=email,
            name=command.name,
            role="user",
            is_active=True,
            is_superuser=False,
            credits=0,
            total_credits_earned=0,
            total_credits_spent=0,
            hashed_password=command.hashed_password,
            last_login=None,
        )
        self.users[user.id] = user
        self.by_email[email] = user.id
        return user

    async def get_account_auth_user_by_email(self, email: str) -> AccountUserPayload | None:
        user_id = self.by_email.get(email.lower().strip())
        return self.users.get(user_id or "")

    async def get_account_auth_user(self, user_id: str) -> AccountUserPayload | None:
        return self.users.get(user_id)

    async def update_account_last_login(self, user_id: str) -> AccountUserPayload | None:
        user = self.users.get(user_id)
        if user is None:
            return None
        updated = user.model_copy(update={"last_login": datetime.now(UTC)})
        self.users[user_id] = updated
        self.by_email[updated.email] = updated.id
        return updated


@pytest_asyncio.fixture
async def fake_account_client() -> FakeAccountClient:
    return FakeAccountClient()


@pytest_asyncio.fixture
async def user_service(fake_account_client: FakeAccountClient) -> UserService:
    return UserService(dataservice=fake_account_client)


class TestCreateUser:
    @pytest.mark.asyncio
    async def test_create_user_success(self, user_service):
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
        assert user.hashed_password is not None
        assert verify_password("securepassword123", user.hashed_password)
        assert user.is_active is True
        assert user.is_superuser is False
        assert user.last_login is None

    @pytest.mark.asyncio
    async def test_create_user_without_name(self, user_service):
        user = await user_service.create_user(
            email="john.doe@example.com",
            password="securepassword123",
        )

        assert user.name == "john.doe"

    @pytest.mark.asyncio
    async def test_create_user_normalizes_email(self, user_service):
        user = await user_service.create_user(
            email="  TEST@EXAMPLE.COM  ",
            password="securepassword123",
        )

        assert user.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_create_user_password_too_short_raises_error(self, user_service):
        with pytest.raises(ValueError, match="密码过短"):
            await user_service.create_user(
                email="test@example.com",
                password="short",
            )

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email_raises_error(self, user_service):
        await user_service.create_user(
            email="test@example.com",
            password="securepassword123",
        )

        with pytest.raises(IntegrityError):
            await user_service.create_user(
                email="test@example.com",
                password="anotherpassword123",
            )


class TestGetByEmail:
    @pytest.mark.asyncio
    async def test_get_by_email_found(self, user_service):
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
        found = await user_service.get_by_email("nonexistent@example.com")

        assert found is None

    @pytest.mark.asyncio
    async def test_get_by_email_case_insensitive(self, user_service):
        created = await user_service.create_user(
            email="case@example.com",
            password="securepassword123",
        )

        found = await user_service.get_by_email("CASE@EXAMPLE.COM")

        assert found is not None
        assert found.id == created.id


class TestGetById:
    @pytest.mark.asyncio
    async def test_get_by_id_found(self, user_service):
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
        found = await user_service.get_by_id("non-existent-uuid")

        assert found is None


class TestAuthenticate:
    @pytest.mark.asyncio
    async def test_authenticate_success(self, user_service):
        created = await user_service.create_user(
            email="auth@example.com",
            password="correctpassword",
        )

        user = await user_service.authenticate("auth@example.com", "correctpassword")

        assert user is not None
        assert user.id == created.id

    @pytest.mark.asyncio
    async def test_authenticate_wrong_password(self, user_service):
        await user_service.create_user(
            email="auth2@example.com",
            password="correctpassword",
        )

        user = await user_service.authenticate("auth2@example.com", "wrongpassword")

        assert user is None

    @pytest.mark.asyncio
    async def test_authenticate_nonexistent_user(self, user_service):
        user = await user_service.authenticate("nonexistent@example.com", "password")

        assert user is None

    @pytest.mark.asyncio
    async def test_authenticate_inactive_user(
        self,
        user_service,
        fake_account_client: FakeAccountClient,
    ):
        user = await user_service.create_user(
            email="inactive@example.com",
            password="securepassword123",
        )
        fake_account_client.users[user.id] = user.model_copy(update={"is_active": False})

        result = await user_service.authenticate("inactive@example.com", "securepassword123")

        assert result is None


class TestUpdateLastLogin:
    @pytest.mark.asyncio
    async def test_update_last_login_success(self, user_service):
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
        result = await user_service.update_last_login("non-existent-uuid")

        assert result is None

    @pytest.mark.asyncio
    async def test_update_last_login_preserves_other_fields(self, user_service):
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
