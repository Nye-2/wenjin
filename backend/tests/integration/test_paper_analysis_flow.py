"""Backend integration test for the paper-analysis block stream.

The historical WorkspaceRun persistence checks were removed when product run
state converged on DataService Execution projections. This file now verifies
only SSE emission correctness for a scripted AgentMessage.
"""
from __future__ import annotations

from typing import Any

import pytest

from src.runtime.runs.worker import _emit_assistant_blocks
from src.runtime.stream_bridge import END_SENTINEL, MemoryStreamBridge


def _scripted_message() -> dict[str, Any]:
    """Return a full AgentMessage payload with all 4 block kinds.

    Block sequence (spec §5.3 + §5.4):
      1. text         — agent acknowledgment
      2. status_line  — phase 1 start
      3. status_line  — phase 2 transition
      4. status_line  — result-card preamble ("正在汇总…")
      5. result_card  — final summary card
    """
    return {
        "role": "assistant",
        "blocks": [
            {
                "kind": "text",
                "content": "我正在为您深度解读这篇论文，请稍候。",
            },
            {
                "kind": "status_line",
                "label": "正在检索文献",
                "run_id": "run-sse-001",
                "phase_index": 0,
                "tone": "info",
            },
            {
                "kind": "status_line",
                "label": "正在分析方法论",
                "run_id": "run-sse-001",
                "phase_index": 1,
                "tone": "info",
            },
            {
                "kind": "status_line",
                "label": "正在汇总分析结果",
                "run_id": "run-sse-001",
                "phase_index": 2,
                "tone": "info",
            },
            {
                "kind": "result_card",
                "run_id": "run-sse-001",
                "title": "深度解读：Attention Is All You Need",
                "tldr": "Transformer 架构通过自注意力机制实现了并行化训练。",
                "findings": [
                    {"id": "①", "text": "多头注意力机制的并行性优于 RNN"},
                ],
                "recommend": {"label": "延伸阅读", "body": "BERT 论文"},
                "links": [],
                "feedback": {
                    "question": "这次分析对你有帮助吗？",
                    "pills": [
                        {"kind": "primary", "label": "很有帮助", "intent": "helpful"},
                    ],
                    "allow_free_input": True,
                },
                "stats": {"duration_ms": 3800, "subagents": 3, "tokens": 10500},
            },
        ],
    }


async def _collect_block_events(
    bridge: MemoryStreamBridge, run_id: str
) -> list[dict[str, Any]]:
    """Emit blocks, signal end, then drain and return only 'block' event payloads.

    Note: publish_end must have already been called before subscribing in a
    synchronous context (all blocks are buffered before we start reading).
    """
    events = []
    async for item in bridge.subscribe(run_id):
        if item is END_SENTINEL:
            break
        if item.event == "block":
            events.append(item.data)
    return events


async def _emit_and_collect(message: dict[str, Any], run_id: str) -> list[dict[str, Any]]:
    """Emit all blocks for a message then publish_end, and collect block events."""
    bridge = MemoryStreamBridge()
    await _emit_assistant_blocks(bridge, run_id=run_id, message=message)
    await bridge.publish_end(run_id)
    return await _collect_block_events(bridge, run_id)


@pytest.mark.asyncio
async def test_sse_emits_all_block_kinds_in_order():
    """All 5 blocks from the scripted message are emitted in order."""
    events = await _emit_and_collect(_scripted_message(), "run-sse-001")

    assert len(events) == 5, f"expected 5 block events, got {len(events)}: {events}"

    kinds = [e["block"]["kind"] for e in events]
    assert kinds[0] == "text", "First block must be text"
    assert kinds[1] == "status_line"
    assert kinds[2] == "status_line"
    assert kinds[3] == "status_line"
    assert kinds[4] == "result_card", "Last block must be result_card"


@pytest.mark.asyncio
async def test_sse_all_blocks_share_one_message_id():
    """All blocks from a single turn share one message_id (spec §5.2)."""
    events = await _emit_and_collect(_scripted_message(), "run-sse-002")

    message_ids = {e["message_id"] for e in events}
    assert len(message_ids) == 1, (
        f"Expected single message_id across all blocks, got: {message_ids}"
    )


@pytest.mark.asyncio
async def test_sse_result_card_preamble_status_line():
    """There must be a status_line with label containing '正在汇总' before result_card."""
    events = await _emit_and_collect(_scripted_message(), "run-sse-003")
    blocks = [e["block"] for e in events]

    # Find the result_card position
    result_card_idx = next(
        (i for i, b in enumerate(blocks) if b.get("kind") == "result_card"), None
    )
    assert result_card_idx is not None, "result_card block not found"

    # There must be a status_line with '正在汇总' before the result_card
    preamble_blocks = blocks[:result_card_idx]
    preamble_labels = [
        b.get("label", "")
        for b in preamble_blocks
        if b.get("kind") == "status_line"
    ]
    assert any("正在汇总" in label for label in preamble_labels), (
        f"No status_line with '正在汇总' found before result_card. "
        f"status_line labels before result_card: {preamble_labels}"
    )


@pytest.mark.asyncio
async def test_sse_no_jargon_leak():
    """Spec §1.1 — internal jargon must not appear in any block content.

    Forbidden strings:
    - 'message_feature_proposal' (internal feature routing label)
    - '意图置信度' (intent confidence — internal metric)
    - '我会先复用' (internal sub-task reuse phrase)
    """
    events = await _emit_and_collect(_scripted_message(), "run-sse-004")

    # Collect all text-bearing fields from blocks
    all_text_content: list[str] = []
    for e in events:
        block = e.get("block", {})
        kind = block.get("kind", "")
        if kind == "text":
            all_text_content.append(block.get("content", ""))
        elif kind == "status_line":
            all_text_content.append(block.get("label", ""))
        elif kind == "result_card":
            all_text_content.append(block.get("title", ""))
            all_text_content.append(block.get("tldr", ""))
            for finding in block.get("findings", []):
                all_text_content.append(finding.get("text", ""))

    combined = "\n".join(all_text_content)

    forbidden = [
        "message_feature_proposal",
        "意图置信度",
        "我会先复用",
    ]
    for term in forbidden:
        assert term not in combined, (
            f"Jargon leak detected: '{term}' found in block content"
        )


@pytest.mark.asyncio
async def test_sse_at_least_two_phase_status_lines():
    """Spec §5.3 — at least 2 status_line blocks emitted between text and result_card."""
    events = await _emit_and_collect(_scripted_message(), "run-sse-005")
    blocks = [e["block"] for e in events]

    status_lines = [b for b in blocks if b.get("kind") == "status_line"]
    assert len(status_lines) >= 2, (
        f"Expected at least 2 status_line blocks, got {len(status_lines)}"
    )
