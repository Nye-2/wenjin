"""Tests for authentication service."""

import pytest
from datetime import datetime, timedelta, timezone

from src.services.auth import (
    Token,
    TokenData,
    create_access_token,
    create_refresh_token,
    create_tokens,
    decode_token,
    verify_access_token,
    verify_refresh_token,
    verify_password,
    hash_password,
    hash_token,
)


class TestPasswordHashing:
    """Test password hashing functions."""

    def test_hash_password_creates_valid_hash(self):
        """Test that hash_password creates a valid bcrypt hash."""
        password = "test_password_123"
        hashed = hash_password(password)

        assert hashed != password
        assert hashed.startswith("$2b$")
        assert len(hashed) == 60

    def test_verify_password_correct(self):
        """Test verify_password returns True for correct password."""
        password = "test_password_123"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test verify_password returns False for incorrect password."""
        password = "test_password_123"
        hashed = hash_password(password)

        assert verify_password("wrong_password", hashed) is False

    def test_hash_password_too_short_raises_error(self):
        """Test that short passwords raise ValueError."""
        with pytest.raises(ValueError, match="密码过短"):
            hash_password("short")

    def test_hash_password_too_long_raises_error(self):
        """Test that long passwords raise ValueError."""
        long_password = "a" * 100  # 100 characters > 72 bytes
        with pytest.raises(ValueError, match="密码过长"):
            hash_password(long_password)

    def test_hash_password_strips_whitespace(self):
        """Test that password whitespace is stripped."""
        password = "  test_password_123  "
        hashed = hash_password(password)
        assert verify_password("test_password_123", hashed) is True


class TestTokenHashing:
    """Test token hashing function."""

    def test_hash_token_creates_sha256(self):
        """Test that hash_token creates SHA256 hash."""
        token = "test_token_123"
        hashed = hash_token(token)

        assert hashed != token
        assert len(hashed) == 64  # SHA256 hex length


class TestJWTTokenCreation:
    """Test JWT token creation."""

    def test_create_access_token_returns_valid_jwt(self):
        """Test that create_access_token returns a valid JWT."""
        token = create_access_token(
            user_id="user-123",
            email="test@example.com",
            role="user"
        )

        assert token is not None
        assert isinstance(token, str)
        assert token.count(".") == 2  # JWT format: header.payload.signature

    def test_create_refresh_token_returns_valid_jwt(self):
        """Test that create_refresh_token returns a valid JWT."""
        token = create_refresh_token(user_id="user-123")

        assert token is not None
        assert isinstance(token, str)
        assert token.count(".") == 2

    def test_create_tokens_returns_token_object(self):
        """Test that create_tokens returns a Token object."""
        result = create_tokens(
            user_id="user-123",
            email="test@example.com",
            role="user"
        )

        assert isinstance(result, Token)
        assert result.access_token is not None
        assert result.refresh_token is not None
        assert result.token_type == "bearer"
        assert result.expires_in > 0


class TestJWTTokenVerification:
    """Test JWT token verification."""

    def test_verify_access_token_returns_token_data(self):
        """Test verify_access_token returns TokenData for valid token."""
        token = create_access_token(
            user_id="user-123",
            email="test@example.com",
            role="admin"
        )

        result = verify_access_token(token)

        assert result is not None
        assert isinstance(result, TokenData)
        assert result.user_id == "user-123"
        assert result.email == "test@example.com"
        assert result.role == "admin"
        assert result.exp is not None

    def test_verify_access_token_invalid_returns_none(self):
        """Test verify_access_token returns None for invalid token."""
        result = verify_access_token("invalid.token.here")
        assert result is None

    def test_verify_refresh_token_returns_user_id(self):
        """Test verify_refresh_token returns user_id for valid token."""
        token = create_refresh_token(user_id="user-456")

        result = verify_refresh_token(token)

        assert result == "user-456"

    def test_verify_refresh_token_invalid_returns_none(self):
        """Test verify_refresh_token returns None for invalid token."""
        result = verify_refresh_token("invalid.token.here")
        assert result is None

    def test_verify_access_token_rejects_refresh_token(self):
        """Test verify_access_token rejects refresh tokens."""
        refresh_token = create_refresh_token(user_id="user-123")
        result = verify_access_token(refresh_token)
        assert result is None

    def test_verify_refresh_token_rejects_access_token(self):
        """Test verify_refresh_token rejects access tokens."""
        access_token = create_access_token(
            user_id="user-123",
            email="test@example.com"
        )
        result = verify_refresh_token(access_token)
        assert result is None


class TestDecodeToken:
    """Test decode_token function."""

    def test_decode_token_returns_payload(self):
        """Test decode_token returns payload dict."""
        token = create_access_token(
            user_id="user-123",
            email="test@example.com",
            role="user"
        )

        payload = decode_token(token)

        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["email"] == "test@example.com"
        assert payload["role"] == "user"
        assert payload["type"] == "access"
        assert "exp" in payload

    def test_decode_token_invalid_returns_none(self):
        """Test decode_token returns None for invalid token."""
        result = decode_token("invalid.token.here")
        assert result is None
