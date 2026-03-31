"""Bootstrap admin user for Wenjin (问津).

This module creates the default admin account on first deployment.
It is designed to be idempotent - safe to run multiple times.

Environment variables:
    DATABASE_URL: PostgreSQL connection string (required)
    ADMIN_EMAIL: Admin email (default: admin@wenjin.ai)
    ADMIN_PASSWORD: Admin password (default: admin123)
    ADMIN_NAME: Admin display name (default: Admin)
"""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Default admin credentials
DEFAULT_ADMIN_EMAIL = "admin@wenjin.ai"
DEFAULT_ADMIN_PASSWORD = "admin123"
DEFAULT_ADMIN_NAME = "Admin"


async def create_admin_user(
    session: AsyncSession,
    email: str,
    password: str,
    name: str,
) -> bool:
    """Create admin user if not exists.

    Args:
        session: Database session
        email: Admin email (plain text, will be normalized)
        password: Admin password (plain text, will be hashed)
        name: Admin display name

    Returns:
        True if admin was created, False if already existed
    """
    # Import here to avoid circular imports
    from src.database import User
    from src.services.auth import hash_password

    # Check if admin already exists
    result = await session.execute(
        select(User).where(User.email == email.lower().strip())
    )
    existing_user = result.scalar_one_or_none()

    if existing_user:
        # Ensure existing user has admin privileges
        if not existing_user.is_superuser:
            existing_user.is_superuser = True
            await session.commit()
            print(f"[bootstrap-admin] User {email} promoted to admin")
        else:
            print(f"[bootstrap-admin] Admin user {email} already exists")
        return False

    # Create new admin user
    hashed_password = hash_password(password)

    admin = User(
        email=email.lower().strip(),
        name=name,
        hashed_password=hashed_password,
        is_active=True,
        is_superuser=True,
        credits=10000,  # Grant generous credits to admin
        total_credits_earned=10000,
    )

    session.add(admin)
    await session.commit()

    print(f"[bootstrap-admin] Admin user created: {email}")
    return True


async def async_main() -> int:
    """Main async entry point."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[bootstrap-admin] ERROR: DATABASE_URL is required")
        return 1

    admin_email = os.getenv("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL)
    admin_password = os.getenv("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)
    admin_name = os.getenv("ADMIN_NAME", DEFAULT_ADMIN_NAME)

    # Create async engine
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        async with async_session() as session:
            await create_admin_user(
                session=session,
                email=admin_email,
                password=admin_password,
                name=admin_name,
            )
        return 0
    except Exception as e:
        print(f"[bootstrap-admin] ERROR: {e}")
        return 1
    finally:
        await engine.dispose()


def main() -> int:
    """Main entry point for docker-compose."""
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
