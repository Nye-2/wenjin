"""User service for CRUD operations and authentication.

This service provides user management functionality including:
- User creation with hashed passwords
- User retrieval by email or ID
- Authentication with email/password verification
- Last login timestamp updates
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.account import AccountUserCreatePayload
from src.dataservice_client.provider import dataservice_client
from src.services.auth import hash_password, verify_password


class UserService:
    """Service for managing users.

    This class provides CRUD operations and authentication for users.
    It requires an AsyncSession for database operations.

    Attributes:
        db: AsyncSession for database operations
    """

    def __init__(
        self,
        db: AsyncSession | None = None,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ):
        """Initialize UserService with database session.

        Args:
            db: AsyncSession for database operations
        """
        self.db = db
        self._dataservice = dataservice

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[AsyncDataServiceClient]:
        if self._dataservice is not None:
            yield self._dataservice
            return
        async with dataservice_client() as client:
            yield client

    async def create_user(
        self,
        email: str,
        password: str,
        name: str | None = None,
        auto_commit: bool = True,
    ) -> Any:
        """Create a new user with hashed password.

        Args:
            email: User's email address (must be unique)
            password: Plain text password (will be hashed)
            name: Optional display name (defaults to email prefix)
            auto_commit: Whether to commit immediately

        Returns:
            Created user object

        Raises:
            ValueError: If password validation fails (too short/long)
            IntegrityError: If email already exists
        """
        # Hash the password using auth service
        hashed_password = hash_password(password)

        # Use email prefix as default name
        if name is None:
            name = email.split("@")[0]

        async with self._client() as client:
            user = await client.create_account_user(
                AccountUserCreatePayload(
                    email=email.lower().strip(),
                    name=name,
                    hashed_password=hashed_password,
                    auto_commit=auto_commit,
                )
            )
        if user is not None and user.hashed_password is None:
            user.hashed_password = hashed_password
        return user

    async def get_by_email(self, email: str) -> Any | None:
        """Get user by email address.

        Args:
            email: User's email address (case-insensitive)

        Returns:
            User if found, None otherwise
        """
        async with self._client() as client:
            return await client.get_account_auth_user_by_email(email)

    async def get_by_id(self, user_id: str) -> Any | None:
        """Get user by UUID.

        Args:
            user_id: User's UUID string

        Returns:
            User if found, None otherwise
        """
        async with self._client() as client:
            return await client.get_account_auth_user(user_id)

    async def authenticate(self, email: str, password: str) -> Any | None:
        """Authenticate user with email and password.

        This method verifies the user's credentials and returns the user
        if authentication is successful. It also checks if the user account
        is active.

        Args:
            email: User's email address
            password: Plain text password to verify

        Returns:
            User if authentication succeeds, None otherwise
        """
        user = await self.get_by_email(email)

        if user is None:
            return None

        if not user.is_active:
            return None

        if not verify_password(password, user.hashed_password):
            return None

        return user

    async def update_last_login(self, user_id: str) -> Any | None:
        """Update user's last login timestamp.

        Sets the last_login field to the current UTC time.

        Args:
            user_id: User's UUID string

        Returns:
            Updated user if found, None otherwise
        """
        async with self._client() as client:
            return await client.update_account_last_login(user_id)
