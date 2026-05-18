"""Authentication router for user authentication endpoints.

This module provides REST endpoints for:
- User registration
- User login
- Token refresh
- Current user info retrieval
- Email verification code
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from src.database import User
from src.gateway.auth_dependencies import (
    get_current_user,
    get_current_user_optional,
    security,
)
from src.gateway.deps.core import get_db
from src.services.auth import (
    create_and_persist_tokens,
    verify_refresh_token_recorded,
)
from src.services.user_service import UserService

router = APIRouter()
__all__ = [
    "get_current_user",
    "get_current_user_optional",
    "get_db",
    "router",
    "security",
]


# ============ Request/Response Models ============

class RegisterRequest(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str
    name: str | None = None
    verification_code: str | None = Field(default=None, description="Email verification code")
    invite_code: str | None = Field(default=None, description="Referral invite code")


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
    credits: int
    total_credits_earned: int
    total_credits_spent: int


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
# ============ Endpoints ============

@router.post("/auth/send-verification-code", response_model=SendVerificationCodeResponse)
async def send_verification_code(
    request: SendVerificationCodeRequest,
    req: Request,
) -> SendVerificationCodeResponse:
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
) -> TokenResponse:
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
            auto_commit=False,
        )

        # Grant registration bonus with ledger record (rule-based)
        try:
            from src.services.credit_grant_rule_service import CreditGrantRuleService
            rule_svc = CreditGrantRuleService(db)
            await rule_svc.apply_registration_bonus(str(user.id))
        except Exception:
            logger.exception("registration bonus failed for user %s", user.id)

        # Handle referral invite code if provided
        if request.invite_code:
            referrer = await _resolve_invite_code(db, request.invite_code)
            if referrer:
                from src.services.referral_service import ReferralService
                referral_svc = ReferralService(db)
                try:
                    await referral_svc.record(
                        referrer_user_id=str(referrer.id),
                        referee_user_id=str(user.id),
                    )
                    await referral_svc.fire_referee_on_signup(str(user.id))
                except ValueError:
                    pass  # referee already has referrer or other expected error

        await db.commit()
        await db.refresh(user)

        # Generate tokens
        tokens = await create_and_persist_tokens(
            db,
            user_id=str(user.id),
            email=user.email,
            role="admin" if user.is_superuser else "user",
            user=user,
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
) -> TokenResponse:
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
    tokens = await create_and_persist_tokens(
        db,
        user_id=str(user.id),
        email=user.email,
        role="admin" if user.is_superuser else "user",
        user=user,
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
) -> TokenResponse:
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
    user = await verify_refresh_token_recorded(db, request.refresh_token)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generate new tokens
    tokens = await create_and_persist_tokens(
        db,
        user_id=str(user.id),
        email=user.email,
        role="admin" if user.is_superuser else "user",
        user=user,
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
) -> UserResponse:
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
        credits=int(current_user.credits),
        total_credits_earned=int(current_user.total_credits_earned),
        total_credits_spent=int(current_user.total_credits_spent),
    )


async def _resolve_invite_code(db: AsyncSession, code: str) -> User | None:
    """Stub for user-side invite code system.

    Out of scope for this Phase. Returns None for now;
    user-side UI / invite-code system will be wired in a follow-up.
    """
    _ = db
    _ = code
    return None
