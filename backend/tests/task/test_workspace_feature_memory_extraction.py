"""Tests for feature-result memory extraction scaffolding."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.task.handlers.workspace_feature_handler import (
    _build_feature_memory_conversation,
    _schedule_memory_extraction,
)


def test_build_feature_memory_conversation_uses_thread_context_and_result_summary():
    payload = {
        "workspace_id": "ws-1",
        "workspace_type": "thesis",
        "feature_id": "deep_research",
        "params": {
            "__thread_context_focus": "围绕医学影像分割做多模态大模型调研",
            "topic": "多模态大模型",
            "keywords": ["医学影像", "分割", "benchmark"],
            "__thread_context_digest": "用户: 关注模型泛化和可复现性",
        },
        "user_id": "user-1",
    }
    result = {
        "message": "deep_research 已通过 LangGraph 增强完成",
        "data": {
            "summary": "已有研究在小样本分割上表现提升，但跨医院泛化仍不足。",
            "sections": [{"title": "研究现状"}, {"title": "关键空白"}],
            "recommended_actions": [
                {"action": "literature_management", "reason": "先固化核心文献池"},
            ],
        },
    }

    conversation_text = _build_feature_memory_conversation("thesis", payload, result)

    assert "user:" in conversation_text
    assert "assistant:" in conversation_text
    assert "医学影像分割" in conversation_text
    assert "跨医院泛化仍不足" in conversation_text
    assert "输出章节" in conversation_text
    assert "下一步" in conversation_text
    assert "已通过 LangGraph 增强完成" not in conversation_text


def test_build_feature_memory_conversation_skips_low_signal_payload():
    payload = {
        "workspace_id": "ws-1",
        "workspace_type": "thesis",
        "feature_id": "deep_research",
        "params": {},
        "user_id": "user-1",
    }
    result = {
        "message": "deep_research 已通过 LangGraph 增强完成",
        "data": {},
    }

    conversation_text = _build_feature_memory_conversation("thesis", payload, result)

    assert conversation_text == ""


@pytest.mark.asyncio
async def test_schedule_memory_extraction_skips_when_no_conversation_signal():
    payload = {
        "workspace_id": "ws-1",
        "workspace_type": "thesis",
        "feature_id": "deep_research",
        "params": {},
        "user_id": "user-1",
    }
    result = {
        "message": "deep_research 已通过 LangGraph 增强完成",
        "data": {},
    }

    with patch(
        "src.services.memory_capture_service.extract_and_persist_knowledge",
        AsyncMock(),
    ) as extract_mock:
        await _schedule_memory_extraction("thesis", payload, result)

    extract_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_schedule_memory_extraction_persists_meaningful_conversation():
    payload = {
        "workspace_id": "ws-1",
        "workspace_type": "thesis",
        "feature_id": "deep_research",
        "params": {
            "__thread_context_focus": "请聚焦医学影像分割里的泛化能力问题",
            "topic": "多模态大模型",
        },
        "user_id": "user-1",
    }
    result = {
        "message": "deep_research 已通过 LangGraph 增强完成",
        "data": {
            "summary": "调研显示跨域泛化是当前瓶颈，建议优先补充外部验证集。",
        },
    }

    with patch(
        "src.services.memory_capture_service.extract_and_persist_knowledge",
        AsyncMock(),
    ) as extract_mock:
        await _schedule_memory_extraction("thesis", payload, result)

    extract_mock.assert_awaited_once()
    conversation_text = extract_mock.await_args.args[1]
    assert "user:" in conversation_text
    assert "assistant:" in conversation_text
    assert "泛化能力问题" in conversation_text
    assert "跨域泛化是当前瓶颈" in conversation_text
