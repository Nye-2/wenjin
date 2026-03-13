"""Route tests for thesis API credit integration."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.gateway.routers.auth import get_current_user
from src.gateway.routers.tasks import get_task_service
from src.services.credit_service import InsufficientCreditsError
from src.thesis.api import get_credit_service, router as thesis_router


@pytest.fixture
def thesis_app() -> FastAPI:
    """Create isolated FastAPI app for thesis route tests."""
    app = FastAPI()
    app.include_router(thesis_router, prefix="/api/thesis")
    return app


@pytest.mark.asyncio
async def test_generate_thesis_requires_credits(thesis_app: FastAPI):
    """Generate endpoint should reject requests with insufficient credits."""
    credit_service = AsyncMock()
    credit_service.consume_for_feature = AsyncMock(
        side_effect=InsufficientCreditsError(current_balance=50, required=200)
    )

    task_service = AsyncMock()
    task_service.submit_task = AsyncMock(return_value="task-1")

    async def override_current_user():
        return SimpleNamespace(id="user-1")

    async def override_task_service():
        yield task_service

    async def override_credit_service():
        return credit_service

    thesis_app.dependency_overrides[get_current_user] = override_current_user
    thesis_app.dependency_overrides[get_task_service] = override_task_service
    thesis_app.dependency_overrides[get_credit_service] = override_credit_service

    async with AsyncClient(
        transport=ASGITransport(app=thesis_app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/thesis/generate",
            json={
                "workspace_id": "ws-1",
                "paper_title": "测试论文",
                "discipline": "计算机科学",
                "abstract_content": "摘要",
                "framework_json": {"chapters": []},
                "enable_search": True,
                "enable_images": True,
            },
        )

    assert response.status_code == 402
    assert "积分不足" in response.json()["detail"]
    task_service.submit_task.assert_not_called()


@pytest.mark.asyncio
async def test_generate_thesis_charges_and_passes_credit_metadata(thesis_app: FastAPI):
    """Generate endpoint should attach credit transaction metadata into task payload."""
    tx = SimpleNamespace(id="tx-1", amount=-200, task_id=None)
    credit_service = AsyncMock()
    credit_service.consume_for_feature = AsyncMock(return_value=tx)
    credit_service.refund_failed_task = AsyncMock(return_value=None)
    credit_service.db = AsyncMock()
    credit_service.db.commit = AsyncMock()

    task_service = AsyncMock()
    task_service.submit_task = AsyncMock(return_value="task-1")

    async def override_current_user():
        return SimpleNamespace(id="user-1")

    async def override_task_service():
        yield task_service

    async def override_credit_service():
        return credit_service

    thesis_app.dependency_overrides[get_current_user] = override_current_user
    thesis_app.dependency_overrides[get_task_service] = override_task_service
    thesis_app.dependency_overrides[get_credit_service] = override_credit_service

    async with AsyncClient(
        transport=ASGITransport(app=thesis_app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/thesis/generate",
            json={
                "workspace_id": "ws-1",
                "paper_title": "测试论文",
                "discipline": "计算机科学",
                "abstract_content": "摘要",
                "framework_json": {"chapters": []},
                "enable_search": True,
                "enable_images": True,
            },
        )

    assert response.status_code == 200
    assert response.json()["task_id"] == "task-1"
    task_service.submit_task.assert_awaited_once()

    submit_kwargs = task_service.submit_task.call_args.kwargs
    assert submit_kwargs["task_type"] == "thesis_generation"
    assert submit_kwargs["payload"]["credit_transaction_id"] == "tx-1"
    assert submit_kwargs["payload"]["credit_cost"] == 200

    assert tx.task_id == "task-1"
    credit_service.db.commit.assert_awaited_once()
