"""Authentication router for user authentication endpoints.

This module provides REST endpoints for:
- User registration
- User login
- Token refresh
- Current user info retrieval
- Email verification code
"""

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import User, get_db_session
from src.services.auth import (
    create_tokens,
    verify_access_token,
    verify_refresh_token,
)
from src.services.user_service import UserService

router = APIRouter()

# Security scheme for Swagger UI
security = HTTPBearer(auto_error=False)


# ============ Request/Response Models ============

class RegisterRequest(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str
    name: str | None = None
    verification_code: str | None = Field(default=None, description="Email verification code")


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
    name: str | None
    role: str


class RefreshRequest(BaseModel):
    """Token refresh request."""
    refresh_token: str


class SendVerificationCodeRequest(BaseModel):
    """Request to send verification code."""
    email: EmailStr
    purpose: str = Field(default="register", pattern="^(register|reset_password)$")


class SendVerificationCodeResponse(BaseModel):
    """Response for verification code sending."""
    success: bool
    message: str
    expire_seconds: int


# ============ Dependencies ============

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session."""
    async with get_db_session() as session:
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
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
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User | None:
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

@router.post("/auth/send-verification-code", response_model=SendVerificationCodeResponse)
async def send_verification_code(
    request: SendVerificationCodeRequest,
    req: Request,
):
    """Send verification code to email.

    - Rate limit: One request per 60 seconds
    - Daily limit: 10 emails per day per address
    - Code validity: 10 minutes

    Args:
        request: Request with email and purpose
        req: FastAPI request object

    Returns:
        SendVerificationCodeResponse with success status

    Raises:
        HTTPException: 429 if rate limited
    """
    from src.services.email_service import email_service

    purpose_map = {
        "register": "注册",
        "reset_password": "重置密码"
    }

    success, result = await email_service.send_verification_code(
        email=request.email,
        purpose=purpose_map.get(request.purpose, "验证"),
        ip_address=req.client.host if req.client else None
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=result
        )

    return SendVerificationCodeResponse(
        success=True,
        message="验证码已发送，请查收邮件",
        expire_seconds=email_service.settings.code_ttl
    )


@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user.

    Creates a new user account and returns authentication tokens.
    If SMTP is enabled, requires verification code.

    Args:
        request: Registration request with email, password, optional name, and verification code
        db: Database session

    Returns:
        TokenResponse with access and refresh tokens

    Raises:
        HTTPException: If registration fails (e.g., email already exists, invalid verification code)
    """
    from src.config.app_config import smtp_settings
    from src.services.email_service import email_service

    user_service = UserService(db)

    # Check if user already exists
    existing_user = await user_service.get_by_email(request.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Verify verification code if SMTP is enabled
    if smtp_settings.enabled:
        if not request.verification_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification code is required",
            )
        is_valid, message = await email_service.verify_code(
            email=request.email,
            code=request.verification_code,
            purpose="注册"
        )
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=message,
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
        ) from e


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
