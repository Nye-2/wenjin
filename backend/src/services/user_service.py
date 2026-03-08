"""User service for CRUD operations and authentication.

This service provides user management functionality including:
- User creation with hashed passwords
- User retrieval by email or ID
- Authentication with email/password verification
- Last login timestamp updates
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import User
from src.services.auth import hash_password, verify_password


class UserService:
    """Service for managing users.

    This class provides CRUD operations and authentication for users.
    It requires an AsyncSession for database operations.

    Attributes:
        db: AsyncSession for database operations
    """

    def __init__(self, db: AsyncSession):
        """Initialize UserService with database session.

        Args:
            db: AsyncSession for database operations
        """
        self.db = db

    async def create_user(
        self,
        email: str,
        password: str,
        name: Optional[str] = None,
    ) -> User:
        """Create a new user with hashed password.

        Args:
            email: User's email address (must be unique)
            password: Plain text password (will be hashed)
            name: Optional display name (defaults to email prefix)

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

        user = User(
            email=email.lower().strip(),
            name=name,
            hashed_password=hashed_password,
            is_active=True,
            is_superuser=False,
        )

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        return user

    async def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email address.

        Args:
            email: User's email address (case-insensitive)

        Returns:
            User if found, None otherwise
        """
        result = await self.db.execute(
            select(User).where(User.email == email.lower().strip())
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: str) -> Optional[User]:
        """Get user by UUID.

        Args:
            user_id: User's UUID string

        Returns:
            User if found, None otherwise
        """
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def authenticate(self, email: str, password: str) -> Optional[User]:
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

    async def update_last_login(self, user_id: str) -> Optional[User]:
        """Update user's last login timestamp.

        Sets the last_login field to the current UTC time.

        Args:
            user_id: User's UUID string

        Returns:
            Updated user if found, None otherwise
        """
        user = await self.get_by_id(user_id)

        if user is None:
            return None

        user.last_login = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(user)

        return user
