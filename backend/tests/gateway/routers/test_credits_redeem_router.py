from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.auth_dependencies import get_current_user
from src.gateway.routers import credits_redeem


def _client(service: AsyncMock) -> TestClient:
    app = FastAPI()
    user = MagicMock()
    user.id = "user-1"

    async def override_user():
        return user

    async def override_service():
        return service

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[credits_redeem._service] = override_service
    app.include_router(credits_redeem.router)
    return TestClient(app)


def test_redeem_route_normalizes_code_and_returns_transaction_payload():
    tx = MagicMock()
    tx.amount = 200
    tx.balance_after = 1200
    tx.id = "tx-1"
    service = AsyncMock()
    service.redeem = AsyncMock(return_value=tx)

    response = _client(service).post("/credits/redeem", json={"code": " welcome200 "})

    assert response.status_code == 200
    assert response.json() == {
        "amount": 200,
        "balance_after": 1200,
        "transaction_id": "tx-1",
    }
    service.redeem.assert_awaited_once_with(code="WELCOME200", user_id="user-1")


def test_redeem_route_rejects_empty_code():
    response = _client(AsyncMock()).post("/credits/redeem", json={"code": " "})

    assert response.status_code == 400
