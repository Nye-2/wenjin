"""Tests for AgentBlock-conformant feature task result/failure cards."""
from __future__ import annotations

from src.application.presenters.agent_result_card import (
    build_completion_result_card,
    build_failure_result_card,
)


def test_completion_card_emits_result_card_block_only():
    reply = build_completion_result_card(
        feature_id="paper_analysis",
        task_id="task-1",
        run_id="run-1",
        execution_session_id="es-1",
        payload={"params": {"paper_title": "联邦学习"}},
        result={
            "data": {"summary": "分析完成", "used_context_count": 12},
            "artifacts": [{"id": "a-1", "title": "Paper Analysis Report"}],
        },
        duration_ms=15234,
        subagents_count=4,
        tokens_total=8500,
    )

    assert reply.content
    assert len(reply.blocks) == 1
    block = reply.blocks[0]
    assert block["kind"] == "result_card"
    assert block["run_id"] == "run-1"
    assert block["title"]
    assert isinstance(block["tldr"], str) and block["tldr"]
    assert isinstance(block["findings"], list)
    assert isinstance(block["links"], list)
    assert block["stats"] == {"duration_ms": 15234, "subagents": 4, "tokens": 8500}
    feedback = block["feedback"]
    assert feedback["question"]
    assert isinstance(feedback["pills"], list) and len(feedback["pills"]) >= 1
    assert feedback["allow_free_input"] is True


def test_completion_card_includes_artifact_link():
    reply = build_completion_result_card(
        feature_id="literature_search",
        task_id="task-2",
        run_id="run-2",
        execution_session_id=None,
        payload={"params": {"query": "fed learning"}},
        result={
            "data": {"summary": "找到 12 篇候选"},
            "artifacts": [{"id": "art-1", "title": "Literature Search Results"}],
        },
        duration_ms=22000,
        subagents_count=2,
        tokens_total=4200,
    )

    block = reply.blocks[0]
    links = block["links"]
    assert any(link.get("href", "").startswith("/artifacts/") for link in links)


def test_failure_card_emits_result_card_block_with_error_tldr():
    reply = build_failure_result_card(
        feature_id="writing",
        task_id="task-x",
        run_id="run-x",
        execution_session_id="es-x",
        payload={"params": {"topic": "test"}},
        error="LLM 超时",
        failed_phase="phase 2",
        duration_ms=30000,
        subagents_count=1,
        tokens_total=1200,
    )

    assert len(reply.blocks) == 1
    block = reply.blocks[0]
    assert block["kind"] == "result_card"
    assert "失败" in block["title"] or "失败" in block["tldr"]
    assert "LLM 超时" in block["tldr"]
    feedback = block["feedback"]
    pill_intents = {p["intent"] for p in feedback["pills"]}
    assert "retry_run" in pill_intents


def test_blocks_validate_against_agent_message_schema():
    """The output must validate against AgentMessage(blocks=[...])."""
    from src.agents.chat_agent.blocks import AgentMessage

    reply = build_completion_result_card(
        feature_id="paper_analysis",
        task_id="t1",
        run_id="r1",
        execution_session_id=None,
        payload={"params": {}},
        result={"data": {"summary": "ok"}, "artifacts": []},
        duration_ms=1000,
        subagents_count=0,
        tokens_total=100,
    )
    AgentMessage.model_validate({"blocks": reply.blocks})
