"""Tests for authentication router.

This module tests the auth endpoints including:
- User registration
- User login
- Token refresh
- Current user retrieval
"""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.dataservice_client.contracts.account import (
    AccountRefreshTokenPayload,
    AccountUserCreatePayload,
    AccountUserPayload,
)
from src.gateway.deps.core import get_dataservice_client
from src.gateway.routers.auth import router
from src.services import credit_grant_rule_service as _cgr_module
from src.services import referral_service as _referral_module
from src.services.auth import create_tokens
from src.services.user_service import UserService


class FakeAccountClient:
    def __init__(self) -> None:
        self.users: dict[str, AccountUserPayload] = {}
        self.by_email: dict[str, str] = {}
        self._counter = 0

    async def create_account_user(self, command: AccountUserCreatePayload) -> AccountUserPayload:
        email = command.email.lower().strip()
        if email in self.by_email:
            raise ValueError("Email already registered")
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
        updated = user.model_copy(update={"last_login": datetime.now()})
        self.users[user_id] = updated
        self.by_email[updated.email] = updated.id
        return updated

    async def update_account_refresh_token(
        self,
        user_id: str,
        command: AccountRefreshTokenPayload,
    ) -> AccountUserPayload | None:
        user = self.users.get(user_id)
        if user is None:
            return None
        updated = user.model_copy(
            update={
                "refresh_token_hash": command.refresh_token_hash,
                "refresh_token_expires_at": command.refresh_token_expires_at,
            }
        )
        self.users[user_id] = updated
        self.by_email[updated.email] = updated.id
        return updated


@pytest.fixture
def fake_account_client() -> FakeAccountClient:
    return FakeAccountClient()


@pytest.fixture
def app(monkeypatch, fake_account_client):
    """Create FastAPI app with auth router."""
    monkeypatch.setattr(
        _cgr_module.CreditGrantRuleService,
        "apply_registration_bonus",
        AsyncMock(),
    )

    app = FastAPI()

    async def get_dataservice_client_override():
        yield fake_account_client

    app.dependency_overrides[get_dataservice_client] = get_dataservice_client_override
    app.include_router(router)

    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestRegister:
    """Test registration endpoint."""

    def test_register_success(self, client):
        """Test successful user registration."""
        response = client.post(
            "/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "securepassword123",
                "name": "New User",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0

    def test_register_without_name(self, client):
        """Test registration without name uses email prefix."""
        response = client.post(
            "/auth/register",
            json={
                "email": "noname@example.com",
                "password": "securepassword123",
            },
        )

        assert response.status_code == 201
        assert "access_token" in response.json()

    def test_register_duplicate_email(self, client):
        """Test registration with duplicate email fails."""
        # First registration
        client.post(
            "/auth/register",
            json={
                "email": "duplicate@example.com",
                "password": "securepassword123",
            },
        )

        # Second registration with same email
        response = client.post(
            "/auth/register",
            json={
                "email": "duplicate@example.com",
                "password": "anotherpassword123",
            },
        )

        assert response.status_code == 400
        assert "already registered" in response.json()["detail"].lower()

    def test_register_password_too_short(self, client):
        """Test registration with short password fails."""
        response = client.post(
            "/auth/register",
            json={
                "email": "shortpass@example.com",
                "password": "short",
            },
        )

        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        # The error message is in Chinese or contains password length info
        assert "short" in detail or "8" in detail or "password" in detail

    def test_register_invalid_email(self, client):
        """Test registration with invalid email fails."""
        response = client.post(
            "/auth/register",
            json={
                "email": "not-an-email",
                "password": "securepassword123",
            },
        )

        assert response.status_code == 422  # Validation error

    def test_register_with_invite_code_records_referral(
        self,
        client,
        fake_account_client,
        monkeypatch,
    ):
        """A user-id invite code should resolve the referrer and create referral records."""
        fake_account_client.users["user-ref"] = AccountUserPayload(
            id="user-ref",
            email="referrer@example.com",
            name="Referrer",
            role="user",
            is_active=True,
            is_superuser=False,
            credits=0,
            total_credits_earned=0,
            total_credits_spent=0,
            hashed_password="hashed",
            last_login=None,
        )
        fake_account_client.by_email["referrer@example.com"] = "user-ref"
        record_referral = AsyncMock()
        fire_referee_on_signup = AsyncMock()
        monkeypatch.setattr(_referral_module.ReferralService, "record", record_referral)
        monkeypatch.setattr(
            _referral_module.ReferralService,
            "fire_referee_on_signup",
            fire_referee_on_signup,
        )

        response = client.post(
            "/auth/register",
            json={
                "email": "invited@example.com",
                "password": "securepassword123",
                "name": "Invited User",
                "invite_code": "USER-user-ref",
            },
        )

        assert response.status_code == 201
        record_referral.assert_awaited_once_with(
            referrer_user_id="user-ref",
            referee_user_id="user-1",
        )
        fire_referee_on_signup.assert_awaited_once_with("user-1")


class TestLogin:
    """Test login endpoint."""

    def test_login_success(self, client):
        """Test successful login."""
        # Register user first
        client.post(
            "/auth/register",
            json={
                "email": "login@example.com",
                "password": "correctpassword",
                "name": "Login User",
            },
        )

        # Login
        response = client.post(
            "/auth/login",
            json={
                "email": "login@example.com",
                "password": "correctpassword",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client):
        """Test login with wrong password fails."""
        # Register user first
        client.post(
            "/auth/register",
            json={
                "email": "wrongpass@example.com",
                "password": "correctpassword",
            },
        )

        # Login with wrong password
        response = client.post(
            "/auth/login",
            json={
                "email": "wrongpass@example.com",
                "password": "wrongpassword",
            },
        )

        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()

    def test_login_nonexistent_user(self, client):
        """Test login with non-existent user fails."""
        response = client.post(
            "/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "anypassword",
            },
        )

        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()

    def test_login_invalid_email_format(self, client):
        """Test login with invalid email format fails."""
        response = client.post(
            "/auth/login",
            json={
                "email": "not-an-email",
                "password": "anypassword",
            },
        )

        assert response.status_code == 422  # Validation error


class TestRefresh:
    """Test token refresh endpoint."""

    def test_refresh_invalid_token(self, client):
        """Test refresh with invalid token fails."""
        response = client.post(
            "/auth/refresh",
            json={
                "refresh_token": "invalid.token.here",
            },
        )

        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()

    def test_refresh_success(self, client):
        """Test successful token refresh."""
        # Register and get tokens
        register_response = client.post(
            "/auth/register",
            json={
                "email": "refresh@example.com",
                "password": "securepassword123",
            },
        )
        refresh_token = register_response.json()["refresh_token"]

        # Refresh tokens
        response = client.post(
            "/auth/refresh",
            json={
                "refresh_token": refresh_token,
            },
        )

        assert response.status_code == 200

    def test_refresh_rotates_refresh_token(self, client):
        """Refreshing should invalidate the previous refresh token."""
        register_response = client.post(
            "/auth/register",
            json={
                "email": "rotate@example.com",
                "password": "securepassword123",
            },
        )
        old_refresh_token = register_response.json()["refresh_token"]

        refresh_response = client.post(
            "/auth/refresh",
            json={"refresh_token": old_refresh_token},
        )

        assert refresh_response.status_code == 200
        new_refresh_token = refresh_response.json()["refresh_token"]
        assert new_refresh_token != old_refresh_token

        old_token_response = client.post(
            "/auth/refresh",
            json={"refresh_token": old_refresh_token},
        )
        assert old_token_response.status_code == 401


class TestGetMe:
    """Test current user endpoint."""

    def test_get_me_success(self, client):
        """Test getting current user info."""
        # Register and get tokens
        register_response = client.post(
            "/auth/register",
            json={
                "email": "me@example.com",
                "password": "securepassword123",
                "name": "Me User",
            },
        )
        access_token = register_response.json()["access_token"]

        # Get current user
        response = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "me@example.com"
        assert data["name"] == "Me User"
        assert data["role"] == "user"

    def test_get_me_no_token(self, client):
        """Test getting current user without token fails."""
        response = client.get("/auth/me")

        assert response.status_code == 401
        assert "not authenticated" in response.json()["detail"].lower()

    def test_get_me_invalid_token(self, client):
        """Test getting current user with invalid token fails."""
        response = client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )

        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()


# ============ Integration tests using async fixtures ============


class TestAuthIntegration:
    """Integration tests for auth endpoints."""

    @pytest.mark.asyncio
    async def test_full_auth_flow(self, fake_account_client):
        """Test complete authentication flow: register -> login -> refresh -> me."""
        # This test demonstrates the full flow but uses the services directly
        user_service = UserService(dataservice=fake_account_client)

        # Register
        user = await user_service.create_user(
            email="flow@example.com",
            password="securepassword123",
            name="Flow User",
        )
        assert user is not None

        # Create tokens (simulating login)
        tokens = create_tokens(
            user_id=str(user.id),
            email=user.email,
            role="user",
        )
        assert tokens.access_token is not None
        assert tokens.refresh_token is not None

        # Verify token works
        from src.services.auth import verify_access_token

        token_data = verify_access_token(tokens.access_token)
        assert token_data is not None
        assert token_data.user_id == str(user.id)

        # Refresh token
        from src.services.auth import verify_refresh_token

        user_id = verify_refresh_token(tokens.refresh_token)
        assert user_id == str(user.id)

    @pytest.mark.asyncio
    async def test_login_updates_last_login(self, fake_account_client):
        """Test that login updates last_login timestamp."""
        user_service = UserService(dataservice=fake_account_client)

        # Create user
        user = await user_service.create_user(
            email="lastlogin@example.com",
            password="securepassword123",
        )
        assert user.last_login is None

        # Update last login (simulating login)
        updated = await user_service.update_last_login(str(user.id))
        assert updated.last_login is not None
        assert isinstance(updated.last_login, datetime)

    @pytest.mark.asyncio
    async def test_inactive_user_cannot_authenticate(self, fake_account_client):
        """Test that inactive users cannot authenticate."""
        user_service = UserService(dataservice=fake_account_client)

        # Create user
        user = await user_service.create_user(
            email="inactive@example.com",
            password="securepassword123",
        )

        # Deactivate user
        fake_account_client.users[user.id] = user.model_copy(update={"is_active": False})

        # Try to authenticate
        result = await user_service.authenticate("inactive@example.com", "securepassword123")
        assert result is None

    @pytest.mark.asyncio
    async def test_case_insensitive_email_login(self, fake_account_client):
        """Test that email login is case-insensitive."""
        user_service = UserService(dataservice=fake_account_client)

        # Create user with lowercase email
        await user_service.create_user(
            email="case@example.com",
            password="securepassword123",
        )

        # Authenticate with uppercase email
        user = await user_service.authenticate("CASE@EXAMPLE.COM", "securepassword123")
        assert user is not None
        assert user.email == "case@example.com"
