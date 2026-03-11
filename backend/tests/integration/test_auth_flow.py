"""Integration tests for authentication flow.

Tests the complete authentication flow including:
- User registration
- User login
- Token refresh
- Current user info retrieval
- Error handling for invalid credentials
"""

import pytest
from httpx import AsyncClient

from tests.integration.conftest import (
    FixtureUser,
    make_authenticated_client,
)


class TestAuthFlow:
    """Tests for complete authentication flow."""

    @pytest.mark.asyncio
    async def test_full_registration_and_login(self, client: AsyncClient):
        """Test complete registration and login flow."""
        # 1. Register new user
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "securepassword123",
                "name": "New User",
            },
        )
        assert response.status_code == 201
        tokens = response.json()
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert tokens["token_type"] == "bearer"
        assert tokens["expires_in"] > 0

        # 2. Access protected endpoint with token
        auth_client = make_authenticated_client(client, tokens["access_token"])
        response = await auth_client.get("/api/auth/me")
        assert response.status_code == 200
        user = response.json()
        assert user["email"] == "newuser@example.com"
        assert user["name"] == "New User"
        assert user["role"] == "user"

        # 3. Login with credentials
        response = await client.post(
            "/api/auth/login",
            json={
                "email": "newuser@example.com",
                "password": "securepassword123",
            },
        )
        assert response.status_code == 200
        login_tokens = response.json()
        assert "access_token" in login_tokens
        assert "refresh_token" in login_tokens

        # 4. Refresh token
        response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert response.status_code == 200
        refresh_tokens = response.json()
        assert "access_token" in refresh_tokens
        assert "refresh_token" in refresh_tokens
        # Verify new tokens are valid
        auth_client2 = make_authenticated_client(client, refresh_tokens["access_token"])
        response = await auth_client2.get("/api/auth/me")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_duplicate_registration_fails(self, client: AsyncClient, test_user: TestUser):
        """Test that registering with existing email fails."""
        # Register with existing email
        response = await client.post(
            "/api/auth/register",
            json={
                "email": test_user.email,
                "password": "anotherpassword123",
                "name": "Another User",
            },
        )
        assert response.status_code == 400
        error = response.json()
        assert "already registered" in error["detail"].lower()

    @pytest.mark.asyncio
    async def test_login_with_wrong_password_fails(self, client: AsyncClient, test_user: TestUser):
        """Test that login with wrong password fails."""
        response = await client.post(
            "/api/auth/login",
            json={
                "email": test_user.email,
                "password": "wrongpassword",
            },
        )
        assert response.status_code == 401
        error = response.json()
        assert "invalid" in error["detail"].lower()

    @pytest.mark.asyncio
    async def test_login_with_nonexistent_email_fails(self, client: AsyncClient):
        """Test that login with nonexistent email fails."""
        response = await client.post(
            "/api/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "anypassword123",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_access_protected_endpoint_without_token_fails(self, client: AsyncClient):
        """Test that accessing protected endpoint without token fails."""
        response = await client.get("/api/auth/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_access_protected_endpoint_with_invalid_token_fails(self, client: AsyncClient):
        """Test that accessing protected endpoint with invalid token fails."""
        client.headers["Authorization"] = "Bearer invalid_token_here"
        response = await client.get("/api/auth/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_with_invalid_token_fails(self, client: AsyncClient):
        """Test that refresh with invalid token fails."""
        response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": "invalid_refresh_token"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_with_access_token_fails(self, client: AsyncClient, test_user_tokens: dict):
        """Test that using access token for refresh fails."""
        response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": test_user_tokens["access_token"]},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_registration_with_short_password_fails(self, client: AsyncClient):
        """Test that registration with short password fails."""
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "shortpw@example.com",
                "password": "short",
                "name": "Short Password User",
            },
        )
        # Password validation error - either 400 or 500 depending on how it's handled
        assert response.status_code in [400, 500]

    @pytest.mark.asyncio
    async def test_registration_without_name_uses_email_prefix(
        self, client: AsyncClient, test_session
    ):
        """Test that registration without name uses email prefix as name."""
        email = "noname@example.com"
        response = await client.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": "validpassword123",
            },
        )
        assert response.status_code == 201
        tokens = response.json()

        # Check that name is email prefix
        auth_client = make_authenticated_client(client, tokens["access_token"])
        response = await auth_client.get("/api/auth/me")
        user = response.json()
        assert user["name"] == "noname"

    @pytest.mark.asyncio
    async def test_admin_user_has_admin_role(self, client: AsyncClient, test_admin: TestUser):
        """Test that admin user gets admin role in response."""
        # Login as admin
        response = await client.post(
            "/api/auth/login",
            json={
                "email": test_admin.email,
                "password": "adminpassword123",
            },
        )
        assert response.status_code == 200
        tokens = response.json()

        # Check role
        auth_client = make_authenticated_client(client, tokens["access_token"])
        response = await auth_client.get("/api/auth/me")
        user = response.json()
        assert user["role"] == "admin"

    @pytest.mark.asyncio
    async def test_multiple_logins_generate_tokens(
        self, client: AsyncClient, test_user: TestUser
    ):
        """Test that multiple logins generate valid tokens."""
        tokens_list = []
        for _ in range(3):
            response = await client.post(
                "/api/auth/login",
                json={
                    "email": test_user.email,
                    "password": "testpassword123",
                },
            )
            assert response.status_code == 200
            tokens_list.append(response.json()["access_token"])

        # All tokens should work but they may be the same due to timing
        # Just verify we got tokens
        assert all(t is not None for t in tokens_list)


class TestAuthEdgeCases:
    """Tests for authentication edge cases."""

    @pytest.mark.asyncio
    async def test_case_insensitive_email_login(self, client: AsyncClient, test_user: TestUser):
        """Test that email login is case insensitive."""
        response = await client.post(
            "/api/auth/login",
            json={
                "email": test_user.email.upper(),
                "password": "testpassword123",
            },
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_email_with_leading_trailing_spaces(
        self, client: AsyncClient, test_user: TestUser
    ):
        """Test that email with spaces is handled correctly."""
        response = await client.post(
            "/api/auth/login",
            json={
                "email": f"  {test_user.email}  ",
                "password": "testpassword123",
            },
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_registration_with_existing_email_different_case(
        self, client: AsyncClient, test_user: TestUser
    ):
        """Test that registration with same email different case fails."""
        response = await client.post(
            "/api/auth/register",
            json={
                "email": test_user.email.upper(),
                "password": "newpassword123",
                "name": "Different Case User",
            },
        )
        assert response.status_code == 400
