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
        execution_id="es-1",
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
    assert block["links"] == []
    assert block["stats"] == {"duration_ms": 15234, "subagents": 4, "tokens": 8500}
    feedback = block["feedback"]
    assert feedback["question"]
    assert isinstance(feedback["pills"], list) and len(feedback["pills"]) >= 1
    assert feedback["allow_free_input"] is True


def test_completion_card_includes_workspace_followup_link():
    reply = build_completion_result_card(
        feature_id="literature_search",
        task_id="task-2",
        run_id="run-2",
        execution_id=None,
        payload={
            "workspace_id": "ws-1",
            "skill_id": "deep-research",
            "params": {"query": "fed learning"},
        },
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
    assert {
        (link.get("label"), link.get("href"))
        for link in links
    } >= {
        (
            "基于当前产物继续",
            "/workspaces/ws-1?feature=literature_search&skill=deep-research&query=fed+learning&source_artifact_id=art-1&context_artifact_ids=art-1",
        ),
    }


def test_completion_card_routes_prism_review_links_to_workspace_surface():
    reply = build_completion_result_card(
        feature_id="writing",
        task_id="task-prism",
        run_id="run-prism",
        execution_id="exec-prism",
        payload={
            "workspace_id": "ws-1",
            "params": {"topic": "chapter 1"},
        },
        result={
            "data": {
                "summary": "写作结果已进入 Prism 待确认区",
            },
            "review_items": [
                {
                    "id": "review-1",
                    "kind": "prism_file_change",
                    "logical_key": "section:introduction",
                    "status": "pending",
                    "title": "Intro rewrite",
                    "target": {"file_path": "sections/introduction.tex"},
                }
            ],
            "next_actions": [
                {
                    "action": "preview_prism_changes",
                    "label": "预览待确认修改",
                }
            ],
        },
        duration_ms=9000,
        subagents_count=1,
        tokens_total=900,
    )

    links = reply.blocks[0]["links"]
    assert {
        (link.get("label"), link.get("href"))
        for link in links
    } >= {
        (
            "预览待确认修改",
            "/workspaces/ws-1/prism?focus=file_changes&review_item_id=review-1&logical_key=section%3Aintroduction",
        ),
    }


def test_completion_card_routes_document_artifacts_to_prism_files():
    reply = build_completion_result_card(
        feature_id="writing",
        task_id="task-doc",
        run_id="run-doc",
        execution_id="exec-doc",
        payload={"workspace_id": "ws-1"},
        result={
            "data": {"summary": "文档已生成"},
            "next_actions": [
                {
                    "action": "open_artifact",
                    "label": "打开文档",
                    "artifact_kind": "document",
                    "artifact_id": "file-1",
                    "title": "分析报告",
                }
            ],
        },
        duration_ms=1000,
        subagents_count=1,
        tokens_total=100,
    )

    links = reply.blocks[0]["links"]
    assert {
        (link.get("label"), link.get("href"))
        for link in links
    } >= {("打开文档", "/workspaces/ws-1/prism?file_id=file-1")}


def test_completion_card_carries_canonical_review_items():
    reply = build_completion_result_card(
        feature_id="writing",
        task_id="task-prism",
        run_id="run-prism",
        execution_id="exec-prism",
        payload={"workspace_id": "ws-1"},
        result={
            "data": {"summary": "写作结果已进入 Prism 待确认区"},
            "review_items": [
                {
                    "id": "review-1",
                    "kind": "prism_file_change",
                    "logical_key": "section:introduction",
                    "status": "pending",
                    "title": "Intro rewrite",
                    "target": {"file_path": "sections/introduction.tex"},
                }
            ],
        },
        duration_ms=9000,
        subagents_count=1,
        tokens_total=900,
    )

    block = reply.blocks[0]
    assert block["review_items"][0]["id"] == "review-1"
    assert block["review_items"][0]["target"]["file_path"] == (
        "sections/introduction.tex"
    )


def test_completion_card_does_not_emit_legacy_prism_link_without_workspace():
    reply = build_completion_result_card(
        feature_id="writing",
        task_id="task-prism",
        run_id="run-prism",
        execution_id="exec-prism",
        payload={"params": {"topic": "chapter 1"}},
        result={
            "data": {
                "summary": "写作结果已进入 Prism 待确认区",
                "latex_project_id": "latex-1",
            },
            "next_actions": [
                {
                    "action": "open_prism",
                    "label": "在 WenjinPrism 中继续编辑",
                    "url": "/latex/legacy-project",
                }
            ],
        },
        duration_ms=9000,
        subagents_count=1,
        tokens_total=900,
    )

    assert reply.blocks[0]["links"] == []


def test_failure_card_emits_result_card_block_with_error_tldr():
    reply = build_failure_result_card(
        feature_id="writing",
        task_id="task-x",
        run_id="run-x",
        execution_id="es-x",
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
        execution_id=None,
        payload={"params": {}},
        result={"data": {"summary": "ok"}, "artifacts": []},
        duration_ms=1000,
        subagents_count=0,
        tokens_total=100,
    )
    AgentMessage.model_validate({"blocks": reply.blocks})
