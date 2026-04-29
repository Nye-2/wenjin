"""Tests for workspace feature token usage collection and settlement."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.services.token_usage_collector import record_token_usage
from src.task.handlers import workspace_feature_handler
from src.task.tasks import base as task_base


@pytest.mark.asyncio
async def test_execute_workspace_feature_attaches_collected_token_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feature = SimpleNamespace(id="deep_research")
    monkeypatch.setattr(workspace_feature_handler, "get_workspace_feature", lambda *_: feature)

    async def _fake_try_langgraph_execution(*_: Any, **__: Any) -> dict[str, Any]:
        record_token_usage({"input_tokens": 12, "output_tokens": 3})
        return {"success": True, "feature_id": "deep_research"}

    monkeypatch.setattr(
        workspace_feature_handler,
        "_try_langgraph_execution",
        _fake_try_langgraph_execution,
    )
    monkeypatch.setattr(
        workspace_feature_handler,
        "_schedule_memory_extraction",
        lambda *_: None,
    )

    result = await workspace_feature_handler.execute_workspace_feature(
        {
            "workspace_type": "thesis",
            "feature_id": "deep_research",
            "params": {},
        },
        AsyncMock(),
    )

    assert result["token_usage"] == {
        "input_tokens": 12,
        "output_tokens": 3,
        "total_tokens": 15,
    }


@pytest.mark.asyncio
async def test_workspace_feature_billing_settlement_uses_task_token_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _FakeCreditService:
        def __init__(self, db: Any) -> None:
            captured["db"] = db

        async def consume_for_feature_usage(self, **kwargs: Any) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(
                as_metadata=lambda: {
                    "type": "feature_token_billing",
                    "credits_charged": 1,
                }
            )

    monkeypatch.setattr(task_base, "CreditService", _FakeCreditService, raising=False)
    monkeypatch.setattr(
        "src.services.credit_service.CreditService",
        _FakeCreditService,
    )

    store = SimpleNamespace(
        get_task_record=AsyncMock(
            return_value=SimpleNamespace(
                user_id="user-1",
                feature_id="deep_research",
                workspace_id="ws-1",
            )
        )
    )
    result = {"token_usage": {"input_tokens": 8000, "output_tokens": 3000}}

    await task_base._settle_workspace_feature_billing(
        db=object(),
        store=store,
        task_id="task-1",
        task_type="workspace_feature",
        payload={
            "workspace_id": "ws-1",
            "workspace_type": "thesis",
            "feature_id": "deep_research",
            "feature_name": "深度调研",
            "handler_key": "thesis.deep_research",
            "params": {"topic": "LLM"},
        },
        result=result,
    )

    assert captured["user_id"] == "user-1"
    assert captured["feature_id"] == "deep_research"
    assert captured["token_usage"].total_tokens == 11000
    assert captured["metadata"]["workspace_type"] == "thesis"
    assert result["billing"]["type"] == "feature_token_billing"
