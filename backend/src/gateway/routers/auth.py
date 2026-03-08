"""Authentication router for user authentication endpoints.

This module provides REST endpoints for:
- User registration
- User login
- Token refresh
- Current user info retrieval
"""

from typing import Optional, AsyncGenerator

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db_session, User
from src.services.user_service import UserService
from src.services.auth import (
    create_tokens,
    verify_access_token,
    verify_refresh_token,
    TokenData,
)


router = APIRouter()

# Security scheme for Swagger UI
security = HTTPBearer(auto_error=False)


# ============ Request/Response Models ============

class RegisterRequest(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str
    name: Optional[str] = None


class LoginRequest(BaseModel):
    """User login request."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Token response for login/register/refresh."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    """User information response."""
    id: str
    email: str
    name: Optional[str]
    role: str


class RefreshRequest(BaseModel):
    """Token refresh request."""
    refresh_token: str


# ============ Dependencies ============

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session."""
    async for session in get_db_session():
        yield session


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get current authenticated user from JWT token.

    Args:
        credentials: HTTP Bearer credentials
        db: Database session

    Returns:
        User object

    Raises:
        HTTPException: If authentication fails
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    token_data = verify_access_token(token)

    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_service = UserService(db)
    user = await user_service.get_by_id(token_data.user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Get current user if authenticated, otherwise return None.

    Args:
        credentials: HTTP Bearer credentials
        db: Database session

    Returns:
        User object or None
    """
    if credentials is None:
        return None

    token = credentials.credentials
    token_data = verify_access_token(token)

    if token_data is None:
        return None

    user_service = UserService(db)
    user = await user_service.get_by_id(token_data.user_id)

    if user is None or not user.is_active:
        return None

    return user


# ============ Endpoints ============

@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user.

    Creates a new user account and returns authentication tokens.

    Args:
        request: Registration request with email, password, and optional name
        db: Database session

    Returns:
        TokenResponse with access and refresh tokens

    Raises:
        HTTPException: If registration fails (e.g., email already exists)
    """
    user_service = UserService(db)

    # Check if user already exists
    existing_user = await user_service.get_by_email(request.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    try:
        # Create user
        user = await user_service.create_user(
            email=request.email,
            password=request.password,
            name=request.name,
        )

        # Generate tokens
        tokens = create_tokens(
            user_id=str(user.id),
            email=user.email,
            role="admin" if user.is_superuser else "user",
        )

        return TokenResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_type=tokens.token_type,
            expires_in=tokens.expires_in,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Login with email and password.

    Authenticates user credentials and returns authentication tokens.

    Args:
        request: Login request with email and password
        db: Database session

    Returns:
        TokenResponse with access and refresh tokens

    Raises:
        HTTPException: If authentication fails
    """
    user_service = UserService(db)

    # Authenticate user
    user = await user_service.authenticate(request.email, request.password)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Update last login timestamp
    await user_service.update_last_login(str(user.id))

    # Generate tokens
    tokens = create_tokens(
        user_id=str(user.id),
        email=user.email,
        role="admin" if user.is_superuser else "user",
    )

    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token using refresh token.

    Validates the refresh token and issues new tokens.

    Args:
        request: Refresh request with refresh token
        db: Database session

    Returns:
        TokenResponse with new access and refresh tokens

    Raises:
        HTTPException: If refresh token is invalid
    """
    # Verify refresh token
    user_id = verify_refresh_token(request.refresh_token)

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user
    user_service = UserService(db)
    user = await user_service.get_by_id(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generate new tokens
    tokens = create_tokens(
        user_id=str(user.id),
        email=user.email,
        role="admin" if user.is_superuser else "user",
    )

    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )


@router.get("/auth/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
):
    """Get current authenticated user info.

    Returns the authenticated user's profile information.

    Args:
        current_user: Current authenticated user (injected via dependency)

    Returns:
        UserResponse with user details
    """
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        name=current_user.name,
        role="admin" if current_user.is_superuser else "user",
    )
