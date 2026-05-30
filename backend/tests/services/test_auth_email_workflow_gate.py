"""Auth email verification workflow release gate tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.config import app_config
from src.gateway.routers import auth as auth_router
from src.services import email_service as email_service_module
from src.services.email_service import EmailService

REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = REPO_ROOT / "frontend"
AUTH_STORE_FILE = FRONTEND_DIR / "stores" / "auth.ts"
REGISTER_PAGE_FILE = FRONTEND_DIR / "app" / "(auth)" / "register" / "page.tsx"


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    async def exists(self, key: str) -> bool:
        return key in self.values

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int | None = None) -> None:
        self.values[key] = value
        if ex is not None:
            self.expirations[key] = ex

    async def incr(self, key: str) -> int:
        value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(value)
        return value

    async def expire(self, key: str, seconds: int) -> None:
        self.expirations[key] = seconds

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.values.pop(key, None)
            self.expirations.pop(key, None)


class _FakeAccountDataService:
    def __init__(self) -> None:
        self.users_by_email: dict[str, SimpleNamespace] = {}
        self.update_account_refresh_token = AsyncMock(side_effect=self._update_refresh_token)

    async def get_account_auth_user_by_email(self, email: str):
        return self.users_by_email.get(email.lower().strip())

    async def get_account_auth_user(self, user_id: str):
        for user in self.users_by_email.values():
            if str(user.id) == str(user_id):
                return user
        return None

    async def create_account_user(self, payload):
        user = SimpleNamespace(
            id=f"user-{len(self.users_by_email) + 1}",
            email=payload.email,
            name=payload.name,
            hashed_password=payload.hashed_password,
            is_active=True,
            is_superuser=False,
            refresh_token_hash=None,
            refresh_token_expires_at=None,
        )
        self.users_by_email[user.email] = user
        return user

    async def _update_refresh_token(self, user_id: str, payload):
        user = await self.get_account_auth_user(user_id)
        if user is not None:
            user.refresh_token_hash = payload.refresh_token_hash
            user.refresh_token_expires_at = payload.refresh_token_expires_at
        return user


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    dataservice = _FakeAccountDataService()

    async def get_dataservice_override():
        yield dataservice

    app.dependency_overrides[auth_router.get_dataservice_client] = get_dataservice_override
    app.include_router(auth_router.router)
    return TestClient(app)


def test_smtp_enabled_registration_requires_and_verifies_code(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_config.smtp_settings, "enabled", True)
    fake_email_service = SimpleNamespace(
        verify_code=AsyncMock(return_value=(True, "验证成功")),
        settings=SimpleNamespace(code_ttl=600),
    )
    monkeypatch.setattr(email_service_module, "email_service", fake_email_service)

    from src.services import credit_grant_rule_service as _cgr_module

    monkeypatch.setattr(
        _cgr_module.CreditGrantRuleService,
        "apply_registration_bonus",
        AsyncMock(),
    )

    missing_code_response = client.post(
        "/auth/register",
        json={
            "email": "verify-required@example.com",
            "password": "securepassword123",
        },
    )
    assert missing_code_response.status_code == 400
    assert missing_code_response.json()["detail"] == "Verification code is required"

    response = client.post(
        "/auth/register",
        json={
            "email": "verified@example.com",
            "password": "securepassword123",
            "name": "Verified User",
            "verification_code": "123456",
        },
    )

    assert response.status_code == 201
    assert response.json()["token_type"] == "bearer"
    fake_email_service.verify_code.assert_awaited_once_with(
        email="verified@example.com",
        code="123456",
        purpose="注册",
    )


@pytest.mark.asyncio
async def test_email_service_dev_mode_stores_and_consumes_single_use_code() -> None:
    service = EmailService()
    fake_redis = _FakeRedis()
    service.settings = SimpleNamespace(
        enabled=False,
        code_ttl=600,
        send_interval=60,
        daily_limit=10,
    )
    service._get_redis = AsyncMock(return_value=fake_redis)  # type: ignore[method-assign]

    success, code = await service.send_verification_code(
        email="user@example.com",
        purpose="注册",
    )

    assert success is True
    assert len(code) == 6
    assert code.isdigit()
    assert fake_redis.values["verify:code:register:user@example.com"] == code
    assert fake_redis.expirations["verify:code:register:user@example.com"] == 600
    assert fake_redis.values["verify:limit:user@example.com"] == "1"
    assert fake_redis.values["verify:daily:user@example.com"] == "1"

    verified, message = await service.verify_code(
        email="user@example.com",
        code=code,
        purpose="注册",
    )

    assert verified is True
    assert message == "验证成功"
    assert "verify:code:register:user@example.com" not in fake_redis.values


def test_frontend_register_flow_sends_and_submits_verification_code() -> None:
    auth_store = AUTH_STORE_FILE.read_text(encoding="utf-8")
    register_page = REGISTER_PAGE_FILE.read_text(encoding="utf-8")

    assert "sendVerificationCode(email, 'register')" in register_page
    assert "verificationCode" in register_page
    assert "await register(email, password, name || email.split('@')[0], verificationCode)" in register_page

    assert "/auth/send-verification-code" in auth_store
    assert "body: JSON.stringify({ email, purpose })" in auth_store
    assert "verification_code: verificationCode" in auth_store
    assert "expireSeconds: data.expire_seconds" in auth_store
