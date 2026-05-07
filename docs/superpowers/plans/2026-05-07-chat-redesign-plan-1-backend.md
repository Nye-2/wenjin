# Chat Redesign · Plan 1: Backend Protocol + Prompt + Pause + Persistence

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend pieces of the chat redesign — a structured `AgentBlock` protocol with LLM JSON failure degradation, prompt rewrites that purge jargon and self-narration, pause/cancel hooks on `ParallelExecutor`, and a `workspace_run` persistence table.

**Architecture:** A new `AgentMessage = list[AgentBlock]` Pydantic schema becomes the agent's only output contract; LangChain `with_structured_output` enforces it. The lead agent's system prompt and each skill's `guidance_prompt` are rewritten to the new contract and snapshotted to prevent silent drift. `ParallelExecutor` gains an `asyncio.Event`-based pause hook checked at phase boundaries. A new `workspace_run` table persists completed runs for the iterate-and-fold UX in Plan 2/3.

**Tech Stack:** Python 3.12, FastAPI, LangGraph (`create_react_agent`), LangChain (`with_structured_output`), Pydantic v2, SQLAlchemy + Alembic, pytest, `syrupy` for snapshot tests.

**Reference spec:** [docs/superpowers/specs/2026-05-07-chat-experience-redesign-design.md](../specs/2026-05-07-chat-experience-redesign-design.md). Section numbers below refer to that spec.

**Out of scope for this plan:** Frontend types, store, components, e2e (Plan 2 / Plan 3). Old code deletion (Plan 3 Phase 7).

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `backend/src/agents/lead_agent/blocks.py` | **create** | Pydantic `AgentBlock` union + `AgentMessage` |
| `backend/src/agents/lead_agent/prompts/__init__.py` | **create** | Single source for system & skill prompts |
| `backend/src/agents/lead_agent/prompts/system.py` | **create** | Lead-agent system prompt (rewritten) |
| `backend/src/agents/lead_agent/prompts/skills.py` | **create** | Per-skill guidance prompts (rewritten) |
| `backend/src/agents/lead_agent/prompts/jargon.py` | **create** | Black-list of forbidden tokens |
| `backend/src/agents/lead_agent/agent.py` | modify | Inject `with_structured_output`, emit `block` events, drop `assistant_message` emission |
| `backend/src/agents/lead_agent/structured_output.py` | **create** | `parse_with_fallback()` — runs `with_structured_output`, on failure returns `[TextBlock(content=raw)]` and emits a metric |
| `backend/src/runtime/runs/worker.py` | modify | Replace `assistant_message` SSE with per-block `block` events |
| `backend/src/subagents/parallel.py` | modify | Add `pause_event` checked at phase boundaries |
| `backend/src/subagents/manager.py` | modify | Surface `pause_run/resume_run/cancel_run` ops |
| `backend/src/gateway/routers/runs.py` | modify | New endpoints `POST /runs/{run_id}/{pause,resume,cancel}` |
| `backend/src/database/models/workspace_run.py` | **create** | `WorkspaceRun` SQLAlchemy model |
| `backend/src/services/workspace_run_service.py` | **create** | CRUD + soft-delete |
| `backend/src/gateway/routers/runs.py` | modify | New `DELETE /runs/{run_id}` |
| `backend/alembic/versions/<NEW1>_workspace_run.py` | **create** | Migration for `workspace_run` |
| `backend/alembic/versions/<NEW2>_subagent_criticality.py` | **create** | Adds `criticality` column to `subagent_task` |
| `backend/tests/agents/lead_agent/test_blocks_schema.py` | **create** | Schema validation |
| `backend/tests/agents/lead_agent/test_structured_output.py` | **create** | Failure degradation |
| `backend/tests/agents/lead_agent/test_prompts_snapshot.py` | **create** | Snapshot all prompts |
| `backend/tests/agents/lead_agent/test_jargon.py` | **create** | Output never contains blacklist tokens |
| `backend/tests/subagents/test_pause.py` | **create** | Pause/resume/cancel through ParallelExecutor |
| `backend/tests/services/test_workspace_run_service.py` | **create** | Persistence service |
| `backend/tests/gateway/test_runs_router.py` | **create** | New endpoints |

---

## Task 1: Pydantic `AgentBlock` schema

**Files:**
- Create: `backend/src/agents/lead_agent/blocks.py`
- Test: `backend/tests/agents/lead_agent/test_blocks_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/agents/lead_agent/test_blocks_schema.py
"""Schema validation for AgentBlock protocol (spec §5.1)."""
import pytest
from pydantic import ValidationError

from src.agents.lead_agent.blocks import (
    AgentMessage,
    QuestionCardBlock,
    ResultCardBlock,
    StatusLineBlock,
    TextBlock,
)


def test_text_block_minimal():
    b = TextBlock(content="hello")
    assert b.kind == "text"


def test_status_line_default_tone_is_info():
    b = StatusLineBlock(label="phase 1 done", run_id="r1")
    assert b.tone == "info"


def test_status_line_rejects_unknown_tone():
    with pytest.raises(ValidationError):
        StatusLineBlock(label="x", run_id="r1", tone="boom")


def test_question_card_max_three_pills():
    with pytest.raises(ValidationError):
        QuestionCardBlock(
            label="?",
            question="why",
            pills=[{"label": str(i), "intent": str(i)} for i in range(4)],
        )


def test_result_card_requires_feedback_and_stats():
    with pytest.raises(ValidationError):
        ResultCardBlock(
            run_id="r1",
            title="t",
            tldr="x",
            findings=[{"id": "1", "text": "a"}],
        )


def test_agent_message_discriminated_union_roundtrip():
    raw = {
        "blocks": [
            {"kind": "text", "content": "hi"},
            {
                "kind": "status_line",
                "label": "phase 1 done",
                "run_id": "r1",
                "tone": "info",
            },
        ]
    }
    parsed = AgentMessage.model_validate(raw)
    assert len(parsed.blocks) == 2
    assert parsed.blocks[0].kind == "text"
    assert parsed.blocks[1].kind == "status_line"
    # roundtrip
    assert parsed.model_dump()["blocks"] == raw["blocks"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/agents/lead_agent/test_blocks_schema.py -v
```
Expected: FAIL — `ModuleNotFoundError: src.agents.lead_agent.blocks`

- [ ] **Step 3: Implement the schema**

```python
# backend/src/agents/lead_agent/blocks.py
"""Structured chat-block protocol (spec §5.1).

The agent's only output contract: a list of AgentBlock variants.
LangChain `with_structured_output` enforces this schema.
"""
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class TextBlock(BaseModel):
    kind: Literal["text"] = "text"
    content: str


class StatusLineBlock(BaseModel):
    kind: Literal["status_line"] = "status_line"
    label: str
    run_id: str
    phase_index: int | None = None
    tone: Literal["info", "warn", "error"] = "info"


class Pill(BaseModel):
    label: str
    intent: str  # directive sent back to agent on click


class QuestionCardBlock(BaseModel):
    kind: Literal["question_card"] = "question_card"
    label: str
    question: str
    pills: list[Pill] = Field(default_factory=list, max_length=3)
    context_ref_subagent_task_id: str | None = None
    context_ref_phase_index: int | None = None


class Finding(BaseModel):
    id: str  # used by users to reference: "深入第 ① 点"
    text: str


class Recommend(BaseModel):
    label: str
    body: str


class Link(BaseModel):
    icon: str
    label: str
    href: str


class FeedbackPill(BaseModel):
    kind: Literal["primary", "normal", "warn"]
    label: str
    intent: str


class FeedbackBlock(BaseModel):
    question: str
    pills: list[FeedbackPill]
    allow_free_input: bool = True


class RunStats(BaseModel):
    duration_ms: int
    subagents: int
    tokens: int


class ResultCardBlock(BaseModel):
    kind: Literal["result_card"] = "result_card"
    run_id: str
    title: str
    tldr: str
    findings: list[Finding]
    recommend: Recommend | None = None
    links: list[Link] = Field(default_factory=list)
    feedback: FeedbackBlock
    stats: RunStats


AgentBlock = Annotated[
    Union[TextBlock, StatusLineBlock, QuestionCardBlock, ResultCardBlock],
    Field(discriminator="kind"),
]


class AgentMessage(BaseModel):
    blocks: list[AgentBlock]
```

- [ ] **Step 4: Run test, expect PASS**

```bash
cd backend && uv run pytest tests/agents/lead_agent/test_blocks_schema.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/lead_agent/blocks.py backend/tests/agents/lead_agent/test_blocks_schema.py
git commit -m "feat(agent): add AgentBlock pydantic schema for structured chat output"
```

---

## Task 2: Structured-output wrapper with JSON-failure degradation

**Files:**
- Create: `backend/src/agents/lead_agent/structured_output.py`
- Test: `backend/tests/agents/lead_agent/test_structured_output.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/agents/lead_agent/test_structured_output.py
"""Spec §5.5 — LLM-JSON failure degrades to TextBlock, not raise."""
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.lead_agent.blocks import (
    AgentMessage,
    StatusLineBlock,
    TextBlock,
)
from src.agents.lead_agent.structured_output import parse_with_fallback


@pytest.mark.asyncio
async def test_returns_parsed_message_on_success():
    fake_llm = AsyncMock()
    fake_llm.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value=AgentMessage(
            blocks=[StatusLineBlock(label="ok", run_id="r1")]
        )
    )
    msg = await parse_with_fallback(fake_llm, "prompt-text", run_id="r1")
    assert msg.blocks[0].kind == "status_line"


@pytest.mark.asyncio
async def test_invalid_json_degrades_to_text_block():
    fake_llm = AsyncMock()
    # First call raises (structured), second call returns plain text
    fake_llm.with_structured_output.return_value.ainvoke = AsyncMock(
        side_effect=ValueError("invalid JSON from model")
    )
    fake_llm.ainvoke = AsyncMock(return_value=type("Msg", (), {"content": "raw text"})())

    with patch("src.agents.lead_agent.structured_output.record_parse_failure") as metric:
        msg = await parse_with_fallback(fake_llm, "prompt-text", run_id="r1")

    assert isinstance(msg.blocks[0], TextBlock)
    assert msg.blocks[0].content == "raw text"
    metric.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/agents/lead_agent/test_structured_output.py -v
```
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
# backend/src/agents/lead_agent/structured_output.py
"""LLM structured-output wrapper with JSON-failure degradation (spec §5.5).

Not a fallback for compat — a fallback for LLM non-determinism.
Spec mandates this exists.
"""
import logging
from typing import Any

from src.agents.lead_agent.blocks import AgentMessage, TextBlock

logger = logging.getLogger(__name__)

# Prometheus counter is wired in src.observability.metrics; provide a default
# no-op so unit tests can patch this name without importing prom.
def record_parse_failure() -> None:
    logger.warning("agent_block_json_parse_failure")


async def parse_with_fallback(llm: Any, prompt: str, *, run_id: str) -> AgentMessage:
    """Run `with_structured_output(AgentMessage)`; on failure, degrade to TextBlock.

    Args:
        llm: LangChain chat model instance.
        prompt: Composed prompt text or message list.
        run_id: Current run id; used to attach to a degraded TextBlock context.

    Returns:
        A valid AgentMessage. Never raises on parse error.
    """
    try:
        structured = llm.with_structured_output(AgentMessage)
        result = await structured.ainvoke(prompt)
        return result
    except Exception as exc:  # noqa: BLE001 — fallback for ANY model parse failure
        record_parse_failure()
        logger.exception("structured_output_failed run_id=%s err=%s", run_id, exc)
        # Salvage raw text from a plain (non-structured) call.
        plain = await llm.ainvoke(prompt)
        raw = getattr(plain, "content", None) or str(plain)
        return AgentMessage(blocks=[TextBlock(content=raw)])
```

- [ ] **Step 4: Run test, expect PASS**

```bash
cd backend && uv run pytest tests/agents/lead_agent/test_structured_output.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/lead_agent/structured_output.py backend/tests/agents/lead_agent/test_structured_output.py
git commit -m "feat(agent): structured-output wrapper with TextBlock degradation on JSON failure"
```

---

## Task 3: Jargon black-list & assertion helper

**Files:**
- Create: `backend/src/agents/lead_agent/prompts/__init__.py` (empty package marker)
- Create: `backend/src/agents/lead_agent/prompts/jargon.py`
- Test: `backend/tests/agents/lead_agent/test_jargon.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/agents/lead_agent/test_jargon.py
"""Spec §1.1 — these tokens MUST NOT appear in agent output."""
import pytest

from src.agents.lead_agent.blocks import AgentMessage, TextBlock
from src.agents.lead_agent.prompts.jargon import (
    BLACKLIST,
    assert_no_jargon,
)


def test_blacklist_contains_known_leaks():
    assert "message_feature_proposal" in BLACKLIST
    assert "意图置信度" in BLACKLIST
    assert "我会先复用" in BLACKLIST
    assert "将进入" in BLACKLIST
    assert "识别依据" in BLACKLIST


def test_clean_message_passes():
    msg = AgentMessage(blocks=[TextBlock(content="好，我先去扫文献")])
    assert_no_jargon(msg)  # no exception


def test_jargon_in_text_block_raises():
    msg = AgentMessage(blocks=[
        TextBlock(content="将进入「论文分析」执行链路。识别依据：message_feature_proposal")
    ])
    with pytest.raises(AssertionError, match="message_feature_proposal"):
        assert_no_jargon(msg)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/agents/lead_agent/test_jargon.py -v
```
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
# backend/src/agents/lead_agent/prompts/__init__.py
"""Prompts package for lead_agent."""
```

```python
# backend/src/agents/lead_agent/prompts/jargon.py
"""Black-list of tokens that must never appear in user-facing agent output.

Sourced from real bug reports (spec §1.1). Used both to:
1. Lint LLM responses post-parse (enforced in tests).
2. Negative examples in the system prompt itself.
"""
from src.agents.lead_agent.blocks import (
    AgentMessage,
    QuestionCardBlock,
    ResultCardBlock,
    StatusLineBlock,
    TextBlock,
)

BLACKLIST: tuple[str, ...] = (
    # Internal taxonomy tokens
    "message_feature_proposal",
    "意图置信度",
    # Self-narration phrases
    "我会先复用",
    "将进入",
    "识别依据",
    "执行链路",
    # Debug fields (turn count, node names — partial matches caught by callers)
)


def _strings_in_block(block) -> list[str]:
    if isinstance(block, TextBlock):
        return [block.content]
    if isinstance(block, StatusLineBlock):
        return [block.label]
    if isinstance(block, QuestionCardBlock):
        return [block.label, block.question, *(p.label for p in block.pills)]
    if isinstance(block, ResultCardBlock):
        return [
            block.title,
            block.tldr,
            *(f.text for f in block.findings),
            *((block.recommend.label, block.recommend.body) if block.recommend else ()),
            block.feedback.question,
            *(p.label for p in block.feedback.pills),
        ]
    return []


def assert_no_jargon(msg: AgentMessage) -> None:
    """Raise AssertionError naming the offending token if any blacklist hit found."""
    for block in msg.blocks:
        for s in _strings_in_block(block):
            for token in BLACKLIST:
                if token in s:
                    raise AssertionError(
                        f"jargon `{token}` leaked into agent output: {s!r}"
                    )
```

- [ ] **Step 4: Run test, expect PASS**

```bash
cd backend && uv run pytest tests/agents/lead_agent/test_jargon.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/lead_agent/prompts backend/tests/agents/lead_agent/test_jargon.py
git commit -m "feat(prompts): add jargon blacklist + assert_no_jargon helper"
```

---

## Task 4: Rewrite lead_agent system prompt

**Files:**
- Create: `backend/src/agents/lead_agent/prompts/system.py`
- Test: `backend/tests/agents/lead_agent/test_prompts_snapshot.py` (initial snapshot)

> Background: existing prompt lives in `backend/src/agents/lead_agent/agent.py` in a constant called `_WORKSPACE_TYPE_PROMPTS`. We extract it to `prompts/system.py` and rewrite to the spec.

- [ ] **Step 1: Write the failing snapshot test**

```python
# backend/tests/agents/lead_agent/test_prompts_snapshot.py
"""Snapshot every prompt that ships to the LLM.

Updates require explicit reviewer approval of snapshot diff:
  uv run pytest tests/agents/lead_agent/test_prompts_snapshot.py --snapshot-update
"""
from src.agents.lead_agent.prompts import system as system_prompts


def test_lead_agent_system_prompt_sci(snapshot):
    rendered = system_prompts.render("sci")
    assert rendered == snapshot


def test_lead_agent_system_prompt_thesis(snapshot):
    rendered = system_prompts.render("thesis")
    assert rendered == snapshot


def test_system_prompt_mentions_block_kinds():
    rendered = system_prompts.render("sci")
    for kind in ("text", "status_line", "question_card", "result_card"):
        assert kind in rendered


def test_system_prompt_mentions_no_blacklist_tokens():
    from src.agents.lead_agent.prompts.jargon import BLACKLIST
    rendered = system_prompts.render("sci")
    # The prompt may mention blacklist tokens *as negative examples* explicitly
    # framed as "do not say". Forbid raw appearance in the body otherwise.
    body = rendered.split("# 反例")[0] if "# 反例" in rendered else rendered
    for token in BLACKLIST:
        assert token not in body, f"token {token!r} appears in prompt body"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/agents/lead_agent/test_prompts_snapshot.py -v
```
Expected: FAIL — `prompts.system` not implemented.

- [ ] **Step 3: Implement the new system prompt**

```python
# backend/src/agents/lead_agent/prompts/system.py
"""Lead-agent system prompts, rewritten to spec §8 (chat redesign)."""
from textwrap import dedent

_BASE = dedent("""\
    你是 wenjin 平台的 lead agent。你的任务是根据用户输入完成研究/写作工作。

    # 输出协议
    你**只能**通过 4 类 block 输出对话：
    - `text`：人话段落（chat 主体）
    - `status_line`：phase 切换 / 错误状态的轻量行；`tone` ∈ info/warn/error
    - `question_card`：在真实岔路向用户问 1 个聚焦问题；可附 0-3 个 `pills` 作为建议
    - `result_card`：每轮 run 完成时的结构化汇报，包含 TL;DR / findings / recommend / links / feedback

    # 行为准则
    1. 直接动手，不汇报、不解释、不讨指令。
    2. phase 切换前必须先发 `status_line` 标明转换。
    3. 同 thread 同时最多 1 个未回答的 `question_card`；用户回答前不要再问。
    4. result_card 之前必须先发一条 `status_line`：tone=info、label="正在汇总结果（约 10-20s）"。
    5. 每轮 run 必以 `result_card` 闭合。

    # 反例（绝对不要写）
    - "建议启动「论文分析」。识别依据：message_feature_proposal"  ← 暴露内部分类 token
    - "意图置信度 60%"                                          ← 暴露 debug 信号
    - "我会先复用当前工作区、线程上下文..."                       ← 自我汇报
    - "将进入「论文分析」执行链路"                               ← 元话术
""")

_SCI = dedent("""\
    # 工作区类型：sci（科研论文）
    用户的目标是研究方向探索、文献综述、论文写作。岔路通常出现在：
    - 选题方向（综述 / 实证 / 理论）
    - 文献覆盖范围
    - 阅读顺序与重点
""")

_THESIS = dedent("""\
    # 工作区类型：thesis（学位论文）
    用户的目标是学位论文章节产出。岔路通常出现在：
    - 章节大纲
    - 写作风格与引用规范
    - 评审反馈处理方式
""")

_BY_TYPE = {"sci": _SCI, "thesis": _THESIS}


def render(workspace_type: str) -> str:
    """Render the system prompt for a given workspace type.

    Args:
        workspace_type: one of "sci", "thesis".
    """
    type_block = _BY_TYPE.get(workspace_type, "")
    return f"{_BASE}\n{type_block}".strip()
```

- [ ] **Step 4: Run test, accept snapshots**

```bash
cd backend && uv run pytest tests/agents/lead_agent/test_prompts_snapshot.py --snapshot-update -v
```
Expected: snapshots written; 4 passed on re-run.

```bash
cd backend && uv run pytest tests/agents/lead_agent/test_prompts_snapshot.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/lead_agent/prompts/system.py \
        backend/tests/agents/lead_agent/test_prompts_snapshot.py \
        backend/tests/agents/lead_agent/__snapshots__/
git commit -m "feat(prompts): rewrite lead_agent system prompt for AgentBlock contract"
```

---

## Task 5: Rewrite skill guidance prompts

**Files:**
- Create: `backend/src/agents/lead_agent/prompts/skills.py`
- Modify: `backend/src/workspace_features/skills.py:1-50` (re-export)
- Test: extend `test_prompts_snapshot.py`

- [ ] **Step 1: Add tests**

```python
# append to backend/tests/agents/lead_agent/test_prompts_snapshot.py
from src.agents.lead_agent.prompts import skills as skill_prompts


def test_skill_paper_analyst_prompt(snapshot):
    rendered = skill_prompts.render("paper-analyst")
    assert rendered == snapshot


def test_skill_framework_designer_prompt(snapshot):
    rendered = skill_prompts.render("framework-designer")
    assert rendered == snapshot


def test_skill_unknown_returns_empty():
    assert skill_prompts.render("nonexistent") == ""
```

- [ ] **Step 2: Run, expect FAIL**

```bash
cd backend && uv run pytest tests/agents/lead_agent/test_prompts_snapshot.py::test_skill_paper_analyst_prompt -v
```
Expected: FAIL — `prompts.skills` not implemented.

- [ ] **Step 3: Implement**

```python
# backend/src/agents/lead_agent/prompts/skills.py
"""Skill-specific guidance prompts (spec §8).

Returns the *additional* system-prompt body appended after the base
system prompt for a given skill.
"""
from textwrap import dedent

_PAPER_ANALYST = dedent("""\
    # Skill: 论文分析师
    你的工作流通常是：检索文献 → 并行精读 → 提炼方法分类 → 找切入角度 → 给推荐。
    完成后，result_card 必须包含：
    - tldr：1 句话回答用户的研究方向问题
    - findings：3-5 条编号关键发现（用户可引用 "深入第 ① 点"）
    - recommend：你的判断 / 立场（用户可接受或推翻）
    - feedback.pills：至少 1 个 primary "进入下一阶段" + 1-2 个 "深入第 N 点" + 1 个 warn "换方向"
""")

_FRAMEWORK_DESIGNER = dedent("""\
    # Skill: 框架设计师
    你的工作流通常是：分析需求 → 列出候选架构 → 比较 trade-off → 推荐 → 列出风险。
    result_card 必须包含 trade-off 表格作为 findings。
""")

_BY_SKILL = {
    "paper-analyst": _PAPER_ANALYST,
    "framework-designer": _FRAMEWORK_DESIGNER,
}


def render(skill_id: str) -> str:
    return _BY_SKILL.get(skill_id, "")
```

- [ ] **Step 4: Update snapshots, expect PASS**

```bash
cd backend && uv run pytest tests/agents/lead_agent/test_prompts_snapshot.py --snapshot-update -v
cd backend && uv run pytest tests/agents/lead_agent/test_prompts_snapshot.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Update `workspace_features/skills.py` to import from new module**

Edit `backend/src/workspace_features/skills.py`: replace any inline prompt strings with calls to `prompts.skills.render(skill_id)`. Specific edits depend on existing structure — find the `guidance_prompt` field assignments and replace literals with `render(skill_id_constant)`.

- [ ] **Step 6: Commit**

```bash
git add backend/src/agents/lead_agent/prompts/skills.py \
        backend/src/workspace_features/skills.py \
        backend/tests/agents/lead_agent/test_prompts_snapshot.py \
        backend/tests/agents/lead_agent/__snapshots__/
git commit -m "feat(prompts): rewrite skill guidance prompts for AgentBlock contract"
```

---

## Task 6: Wire `with_structured_output` into lead_agent runtime

**Files:**
- Modify: `backend/src/agents/lead_agent/agent.py:947-960` (the `create_react_agent` call site)
- Test: `backend/tests/agents/lead_agent/test_thread_feature_flow.py` (existing) — add 2 cases

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/agents/lead_agent/test_thread_feature_flow.py
import pytest

from src.agents.lead_agent.blocks import AgentMessage, TextBlock
from src.agents.lead_agent.prompts.jargon import assert_no_jargon


@pytest.mark.asyncio
async def test_first_turn_outputs_blocks_only(make_lead_agent, fake_llm):
    """Spec §5.3 — agent's only output channel is AgentMessage.blocks."""
    agent = make_lead_agent(workspace_type="sci")
    fake_llm.queue_response(AgentMessage(blocks=[
        TextBlock(content="好，我先扫一下这个方向的文献。"),
    ]))

    result = await agent.handle_user_message("我想写一篇论文，联邦学习结合大模型方向。")

    assert isinstance(result, AgentMessage)
    assert len(result.blocks) >= 1
    assert_no_jargon(result)


@pytest.mark.asyncio
async def test_invalid_json_does_not_raise_to_caller(make_lead_agent, broken_llm):
    """Spec §5.5 — degraded TextBlock surfaces, no exception."""
    agent = make_lead_agent(workspace_type="sci")
    result = await agent.handle_user_message("hello")
    assert isinstance(result, AgentMessage)
    assert result.blocks[0].kind == "text"
```

> The fixtures `make_lead_agent`, `fake_llm`, `broken_llm` need to exist in `tests/agents/lead_agent/conftest.py`. If they don't, add them — `fake_llm` is a stub with `queue_response()` and `ainvoke()`/`with_structured_output()` returning queued items.

- [ ] **Step 2: Run, expect FAIL**

```bash
cd backend && uv run pytest tests/agents/lead_agent/test_thread_feature_flow.py::test_first_turn_outputs_blocks_only -v
```
Expected: FAIL — agent doesn't return `AgentMessage` yet.

- [ ] **Step 3: Modify `agent.py` to use `parse_with_fallback`**

Locate the response-generation path (around `agent.py:947-1000` where `create_react_agent` is invoked and assistant content is produced). Replace direct LLM call with:

```python
# in agent.py, near the response generation
from src.agents.lead_agent.blocks import AgentMessage
from src.agents.lead_agent.structured_output import parse_with_fallback
from src.agents.lead_agent.prompts import system as system_prompts
from src.agents.lead_agent.prompts import skills as skill_prompts

# Build system prompt from new modules
def _build_system_prompt(workspace_type: str, skill_id: str | None) -> str:
    base = system_prompts.render(workspace_type)
    skill = skill_prompts.render(skill_id) if skill_id else ""
    return f"{base}\n\n{skill}".strip() if skill else base

# In the response generation method:
async def _generate_assistant_blocks(
    self, llm, messages, run_id: str, workspace_type: str, skill_id: str | None
) -> AgentMessage:
    sys = _build_system_prompt(workspace_type, skill_id)
    composed = [{"role": "system", "content": sys}, *messages]
    return await parse_with_fallback(llm, composed, run_id=run_id)
```

Replace existing free-text generation at the call site with `_generate_assistant_blocks(...)`.

- [ ] **Step 4: Run tests, expect PASS**

```bash
cd backend && uv run pytest tests/agents/lead_agent/test_thread_feature_flow.py -v
```
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/lead_agent/agent.py backend/tests/agents/lead_agent/
git commit -m "feat(agent): wire AgentMessage structured output via parse_with_fallback"
```

---

## Task 7: Replace `assistant_message` SSE with `block` events

**Files:**
- Modify: `backend/src/runtime/runs/worker.py:160-180`
- Modify: `backend/src/application/handlers/thread_turn_handler.py:980-1070` (anywhere `assistant_message` is built/sent)
- Modify: `backend/src/application/results.py:80-90` (rename `assistant_message` → `blocks`)
- Test: extend `tests/runtime/` (find existing SSE test, adapt)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/runtime/test_block_sse.py — new file
"""Spec §5.2 — SSE emits `type: 'block'` events, not `assistant_message`."""
import pytest

from src.runtime.runs.worker import emit_assistant_blocks  # to be created


@pytest.mark.asyncio
async def test_emits_one_event_per_block(stream_capture):
    blocks = [
        {"kind": "text", "content": "hi"},
        {"kind": "status_line", "label": "phase 1 done", "run_id": "r1", "tone": "info"},
    ]
    await emit_assistant_blocks(stream_capture, message_id="m1", blocks=blocks)

    events = stream_capture.events
    assert len(events) == 2
    for ev in events:
        assert ev["type"] == "block"
        assert ev["message_id"] == "m1"

    # No legacy assistant_message
    assert not any(ev["type"] == "assistant_message" for ev in events)
```

The fixture `stream_capture` needs to be defined in `tests/runtime/conftest.py` as a recording sink — append to or create that conftest.

- [ ] **Step 2: Run, expect FAIL**

```bash
cd backend && uv run pytest tests/runtime/test_block_sse.py -v
```
Expected: FAIL — `emit_assistant_blocks` not defined.

- [ ] **Step 3: Implement emission helper and remove `assistant_message` path**

In `backend/src/runtime/runs/worker.py`:

```python
async def emit_assistant_blocks(stream, *, message_id: str, blocks: list[dict]) -> None:
    """Spec §5.2 — emit one `block` SSE event per AgentBlock."""
    for block in blocks:
        await stream.send({
            "type": "block",
            "message_id": message_id,
            "block": block,
        })
```

Then locate the existing emission of `"assistant_message"` (worker.py:168-171) and **delete** it entirely; replace with a call to `emit_assistant_blocks(stream, message_id=msg_id, blocks=msg.model_dump()["blocks"])`.

In `backend/src/application/results.py:80-90`, rename `assistant_message: dict[str, Any]` → `blocks: list[dict[str, Any]]`. Update consumers in `thread_turn_handler.py` accordingly.

- [ ] **Step 4: Run, expect PASS**

```bash
cd backend && uv run pytest tests/runtime/test_block_sse.py tests/application/handlers/ -v
```
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add backend/src/runtime/runs/worker.py \
        backend/src/application/handlers/thread_turn_handler.py \
        backend/src/application/results.py \
        backend/tests/runtime/
git commit -m "feat(stream): emit per-block SSE events; remove legacy assistant_message"
```

---

## Task 8: Add `pause_event` to `ParallelExecutor`

**Files:**
- Modify: `backend/src/subagents/parallel.py:83-110, 183-230`
- Test: `backend/tests/subagents/test_pause.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/subagents/test_pause.py
"""Spec §6.1 — pause/resume blocks at phase boundaries."""
import asyncio
import pytest

from src.subagents.parallel import ParallelExecutor, PhasedPlan, ExecutionPhase
from src.subagents.models import SubagentTask
from datetime import datetime, UTC


def _stub_task(name: str) -> SubagentTask:
    return SubagentTask(
        task_id=name, thread_id="t", prompt=name, created_at=datetime.now(UTC)
    )


@pytest.mark.asyncio
async def test_pause_blocks_next_phase_until_resume():
    exec = ParallelExecutor(max_concurrent=2)
    p1 = ExecutionPhase(name="p1", tasks=[_stub_task("a")], dependencies=[])
    p2 = ExecutionPhase(name="p2", tasks=[_stub_task("b")], dependencies=["p1"])
    plan = PhasedPlan(phases=[p1, p2])

    async def fast_runner(task, **_):
        await asyncio.sleep(0.01)
        return type("R", (), {"task_id": task.task_id, "status": "completed"})()

    exec._run_task = fast_runner  # type: ignore[attr-defined]

    exec.pause()
    task = asyncio.create_task(exec.execute_plan(plan))
    await asyncio.sleep(0.1)
    assert not task.done(), "execution should be blocked while paused"

    exec.resume()
    results = await asyncio.wait_for(task, timeout=2)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_cancel_aborts_pending_phases():
    exec = ParallelExecutor(max_concurrent=2)
    p1 = ExecutionPhase(name="p1", tasks=[_stub_task("a")], dependencies=[])
    p2 = ExecutionPhase(name="p2", tasks=[_stub_task("b")], dependencies=["p1"])
    plan = PhasedPlan(phases=[p1, p2])

    async def slow_runner(task, **_):
        await asyncio.sleep(0.5)
        return type("R", (), {"task_id": task.task_id, "status": "completed"})()

    exec._run_task = slow_runner  # type: ignore[attr-defined]

    task = asyncio.create_task(exec.execute_plan(plan))
    await asyncio.sleep(0.05)
    exec.cancel()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=2)
```

- [ ] **Step 2: Run, expect FAIL**

```bash
cd backend && uv run pytest tests/subagents/test_pause.py -v
```
Expected: FAIL — `pause()`/`resume()`/`cancel()` not defined.

- [ ] **Step 3: Modify `parallel.py`**

In `backend/src/subagents/parallel.py`, modify `__init__` and add three methods + a check at phase boundary:

```python
class ParallelExecutor:
    def __init__(self, max_concurrent: int = 4, phase_timeout: float | None = None, fail_fast: bool = False):
        # … existing fields …
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._phase_events: dict[str, asyncio.Event] = {}
        # NEW
        self._pause_event = asyncio.Event()
        self._pause_event.set()                     # initially unpaused
        self._cancel_event = asyncio.Event()

    def pause(self) -> None:
        self._pause_event.clear()

    def resume(self) -> None:
        self._pause_event.set()

    def cancel(self) -> None:
        self._cancel_event.set()
        self._pause_event.set()                     # release any pause wait

    async def _wait_if_paused(self) -> None:
        if not self._pause_event.is_set():
            await self._pause_event.wait()
        if self._cancel_event.is_set():
            raise asyncio.CancelledError()
```

Then in `_execute_phase` (around line 183), insert at the top:

```python
async def _execute_phase(self, phase, phase_index, context):
    await self._wait_if_paused()
    # … existing body …
```

And in `execute_plan` (around line 170), wrap the for-loop with the same check before each phase.

- [ ] **Step 4: Run, expect PASS**

```bash
cd backend && uv run pytest tests/subagents/test_pause.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/subagents/parallel.py backend/tests/subagents/test_pause.py
git commit -m "feat(subagents): pause/resume/cancel hooks at phase boundaries"
```

---

## Task 9: Plumb pause/resume/cancel through `GlobalSubagentManager`

**Files:**
- Modify: `backend/src/subagents/manager.py`
- Test: extend `tests/subagents/test_pause.py`

- [ ] **Step 1: Add a test**

```python
# append to tests/subagents/test_pause.py
import pytest
from src.subagents.manager import GlobalSubagentManager


@pytest.mark.asyncio
async def test_manager_pauses_run_by_id(monkeypatch):
    mgr = GlobalSubagentManager()
    run_id = "run-x"
    # Manager tracks an executor per run; pause forwards
    fake_exec = type("X", (), {"pause": lambda self: setattr(self, "paused", True)})()
    fake_exec.paused = False
    mgr._executors[run_id] = fake_exec  # type: ignore[attr-defined]
    mgr.pause_run(run_id)
    assert fake_exec.paused is True
```

- [ ] **Step 2: Run, expect FAIL**

```bash
cd backend && uv run pytest tests/subagents/test_pause.py::test_manager_pauses_run_by_id -v
```
Expected: FAIL — `pause_run` not defined.

- [ ] **Step 3: Modify `manager.py`**

Add to `GlobalSubagentManager`:

```python
class GlobalSubagentManager:
    def __init__(self) -> None:
        # … existing …
        self._executors: dict[str, ParallelExecutor] = {}  # run_id -> executor

    def register_executor(self, run_id: str, executor) -> None:
        self._executors[run_id] = executor

    def pause_run(self, run_id: str) -> None:
        if run_id in self._executors:
            self._executors[run_id].pause()

    def resume_run(self, run_id: str) -> None:
        if run_id in self._executors:
            self._executors[run_id].resume()

    def cancel_run(self, run_id: str) -> None:
        ex = self._executors.pop(run_id, None)
        if ex is not None:
            ex.cancel()
```

Then in the call site that creates an executor for a run, immediately call `register_executor(run_id, executor)`.

- [ ] **Step 4: Run, expect PASS**

```bash
cd backend && uv run pytest tests/subagents/test_pause.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/subagents/manager.py backend/tests/subagents/test_pause.py
git commit -m "feat(subagents): plumb pause/resume/cancel through GlobalSubagentManager"
```

---

## Task 10: Pause/resume/cancel HTTP endpoints

**Files:**
- Modify: `backend/src/gateway/routers/runs.py` — add 3 endpoints
- Test: `backend/tests/gateway/test_runs_router.py` (new or extend existing)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/gateway/test_runs_router.py
"""Spec §6.1 — POST /runs/{id}/pause|resume|cancel."""
import pytest
from fastapi.testclient import TestClient

from src.gateway.app import create_app
from src.subagents.manager import GlobalSubagentManager


@pytest.fixture
def client(monkeypatch):
    app = create_app()
    return TestClient(app)


def test_pause_calls_manager(client, monkeypatch):
    called = {"run": None}
    def fake_pause(self, run_id): called["run"] = run_id
    monkeypatch.setattr(GlobalSubagentManager, "pause_run", fake_pause)
    r = client.post("/workspaces/ws1/runs/r1/pause")
    assert r.status_code == 204
    assert called["run"] == "r1"


def test_resume_calls_manager(client, monkeypatch):
    called = {"run": None}
    def fake_resume(self, run_id): called["run"] = run_id
    monkeypatch.setattr(GlobalSubagentManager, "resume_run", fake_resume)
    r = client.post("/workspaces/ws1/runs/r1/resume")
    assert r.status_code == 204
    assert called["run"] == "r1"


def test_cancel_calls_manager(client, monkeypatch):
    called = {"run": None}
    def fake_cancel(self, run_id): called["run"] = run_id
    monkeypatch.setattr(GlobalSubagentManager, "cancel_run", fake_cancel)
    r = client.post("/workspaces/ws1/runs/r1/cancel")
    assert r.status_code == 204
    assert called["run"] == "r1"
```

- [ ] **Step 2: Run, expect FAIL**

```bash
cd backend && uv run pytest tests/gateway/test_runs_router.py -v
```
Expected: FAIL — endpoint not found (404).

- [ ] **Step 3: Add endpoints**

Append to `backend/src/gateway/routers/runs.py`:

```python
from src.subagents.manager import GlobalSubagentManager
from src.gateway.dependencies import get_subagent_manager

@router.post("/workspaces/{workspace_id}/runs/{run_id}/pause", status_code=204)
async def pause_run(
    workspace_id: str,
    run_id: str,
    mgr: GlobalSubagentManager = Depends(get_subagent_manager),
) -> None:
    mgr.pause_run(run_id)

@router.post("/workspaces/{workspace_id}/runs/{run_id}/resume", status_code=204)
async def resume_run(
    workspace_id: str,
    run_id: str,
    mgr: GlobalSubagentManager = Depends(get_subagent_manager),
) -> None:
    mgr.resume_run(run_id)

@router.post("/workspaces/{workspace_id}/runs/{run_id}/cancel", status_code=204)
async def cancel_run(
    workspace_id: str,
    run_id: str,
    mgr: GlobalSubagentManager = Depends(get_subagent_manager),
) -> None:
    mgr.cancel_run(run_id)
```

> If `get_subagent_manager` doesn't exist in `dependencies.py`, add a singleton: `_mgr = GlobalSubagentManager()` and `def get_subagent_manager() -> GlobalSubagentManager: return _mgr`.

- [ ] **Step 4: Run, expect PASS**

```bash
cd backend && uv run pytest tests/gateway/test_runs_router.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/gateway/routers/runs.py \
        backend/src/gateway/dependencies.py \
        backend/tests/gateway/test_runs_router.py
git commit -m "feat(api): pause/resume/cancel endpoints for run lifecycle"
```

---

## Task 11: `criticality` field on `subagent_task`

**Files:**
- Create: `backend/alembic/versions/<NEXT_REVID>_subagent_criticality.py`
- Modify: `backend/src/database/models/subagent_task.py` — add column
- Modify: `backend/src/subagents/models.py` — add `criticality` to dataclass
- Test: `backend/tests/database/test_subagent_task_criticality.py` (new)

- [ ] **Step 1: Determine the revision id**

```bash
cd backend && uv run alembic heads
```
Note the current head id (e.g., `c41ed149a3b5`). Generate next:

```bash
cd backend && uv run alembic revision -m "subagent_task add criticality column"
```
This creates an empty migration file. Open it and edit:

```python
"""subagent_task add criticality column

Revision ID: <auto-generated>
Revises: c41ed149a3b5
Create Date: 2026-05-07 ...
"""
from alembic import op
import sqlalchemy as sa

revision = "<auto-generated>"
down_revision = "c41ed149a3b5"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        "subagent_task",
        sa.Column("criticality", sa.String(length=8), nullable=False, server_default="low"),
    )

def downgrade():
    op.drop_column("subagent_task", "criticality")
```

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/database/test_subagent_task_criticality.py
import pytest
from sqlalchemy import inspect

from src.database.models.subagent_task import SubagentTaskRow
from src.database.session import engine


def test_subagent_task_has_criticality_column():
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("subagent_task")}
    assert "criticality" in cols


def test_default_criticality_is_low():
    row = SubagentTaskRow(task_id="t", thread_id="th", prompt="p")
    assert row.criticality == "low"
```

- [ ] **Step 3: Run migration + test, expect FAIL on first run, PASS after migration applied**

```bash
cd backend && uv run alembic upgrade head
cd backend && uv run pytest tests/database/test_subagent_task_criticality.py -v
```
Expected (after migration): 2 passed.

- [ ] **Step 4: Modify `subagents/models.py` and `database/models/subagent_task.py`**

In `backend/src/subagents/models.py`:

```python
@dataclass
class SubagentTask:
    # … existing …
    criticality: Literal["low", "high"] = "low"
```

In `backend/src/database/models/subagent_task.py`:

```python
class SubagentTaskRow(Base):
    # … existing columns …
    criticality: Mapped[str] = mapped_column(String(8), default="low", nullable=False)
```

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/*subagent_criticality.py \
        backend/src/database/models/subagent_task.py \
        backend/src/subagents/models.py \
        backend/tests/database/test_subagent_task_criticality.py
git commit -m "feat(db): add criticality column to subagent_task"
```

---

## Task 12: Severity-based error handling in `ParallelExecutor`

**Files:**
- Modify: `backend/src/subagents/parallel.py` — `_execute_task` failure handler
- Test: extend `backend/tests/subagents/test_pause.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/subagents/test_pause.py
@pytest.mark.asyncio
async def test_high_criticality_failure_pauses_run(monkeypatch):
    """Spec §6.3 — high-criticality failure auto-pauses; low does not."""
    exec = ParallelExecutor(max_concurrent=2)
    p1 = ExecutionPhase(name="p1", tasks=[
        SubagentTask(task_id="a", thread_id="t", prompt="x",
                     created_at=datetime.now(UTC), criticality="high")
    ], dependencies=[])
    plan = PhasedPlan(phases=[p1])

    async def boom(task, **_):
        raise RuntimeError("boom")

    exec._run_task = boom  # type: ignore[attr-defined]
    paused = []
    monkeypatch.setattr(exec, "pause", lambda: paused.append(True))

    await exec.execute_plan(plan)
    assert paused == [True]


@pytest.mark.asyncio
async def test_low_criticality_failure_does_not_pause(monkeypatch):
    exec = ParallelExecutor(max_concurrent=2)
    p1 = ExecutionPhase(name="p1", tasks=[
        SubagentTask(task_id="a", thread_id="t", prompt="x",
                     created_at=datetime.now(UTC), criticality="low")
    ], dependencies=[])
    plan = PhasedPlan(phases=[p1])

    async def boom(task, **_):
        raise RuntimeError("boom")

    exec._run_task = boom  # type: ignore[attr-defined]
    paused = []
    monkeypatch.setattr(exec, "pause", lambda: paused.append(True))

    await exec.execute_plan(plan)
    assert paused == []
```

- [ ] **Step 2: Run, expect FAIL**

```bash
cd backend && uv run pytest tests/subagents/test_pause.py::test_high_criticality_failure_pauses_run -v
```
Expected: FAIL.

- [ ] **Step 3: Modify failure handler**

In `parallel.py`, wherever a subagent task raises (or returns failure), add:

```python
async def _execute_task(self, task, **kwargs):
    try:
        return await self._run_task(task, **kwargs)
    except Exception as exc:
        # spec §6.3 severity routing
        if task.criticality == "high":
            self.pause()
        # status_line/question_card emission is the agent's job — see Task 6's
        # response generation. Here we just re-raise as a failure result so the
        # caller can record it.
        return type("R", (), {
            "task_id": task.task_id, "status": "failed", "error": str(exc),
        })()
```

- [ ] **Step 4: Run, expect PASS**

```bash
cd backend && uv run pytest tests/subagents/test_pause.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/subagents/parallel.py backend/tests/subagents/test_pause.py
git commit -m "feat(subagents): high-criticality failures auto-pause the run"
```

---

## Task 13: `workspace_run` table + migration

**Files:**
- Create: `backend/alembic/versions/<NEXT_REVID>_workspace_run.py`
- Create: `backend/src/database/models/workspace_run.py`
- Test: `backend/tests/database/test_workspace_run_model.py`

- [ ] **Step 1: Generate migration**

```bash
cd backend && uv run alembic revision -m "create workspace_run table"
```

Edit the generated file:

```python
from alembic import op
import sqlalchemy as sa

revision = "<auto>"
down_revision = "<previous, the criticality migration>"

def upgrade():
    op.create_table(
        "workspace_run",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("thread_id", sa.String(length=36), sa.ForeignKey("thread.id"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("result_card", sa.JSON(), nullable=True),
        sa.Column("stats", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_workspace_run_thread_started", "workspace_run", ["thread_id", "started_at"])
    op.add_column("subagent_task", sa.Column("run_id", sa.String(length=36), sa.ForeignKey("workspace_run.id"), nullable=True))

def downgrade():
    op.drop_column("subagent_task", "run_id")
    op.drop_index("ix_workspace_run_thread_started", table_name="workspace_run")
    op.drop_table("workspace_run")
```

- [ ] **Step 2: Write model + test**

```python
# backend/src/database/models/workspace_run.py
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database.session import Base


class WorkspaceRunRow(Base):
    __tablename__ = "workspace_run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspace.id"), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(36), ForeignKey("thread.id"), nullable=False)
    title: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16))                    # running/paused/completed/cancelled/failed
    result_card: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    stats: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

```python
# backend/tests/database/test_workspace_run_model.py
import pytest
from sqlalchemy import inspect
from src.database.session import engine


def test_workspace_run_table_exists():
    insp = inspect(engine)
    assert "workspace_run" in insp.get_table_names()


def test_subagent_task_has_run_id_fk():
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("subagent_task")}
    assert "run_id" in cols
```

- [ ] **Step 3: Apply migration + run tests**

```bash
cd backend && uv run alembic upgrade head
cd backend && uv run pytest tests/database/test_workspace_run_model.py -v
```
Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/*workspace_run.py \
        backend/src/database/models/workspace_run.py \
        backend/tests/database/test_workspace_run_model.py
git commit -m "feat(db): create workspace_run table + run_id FK on subagent_task"
```

---

## Task 14: `WorkspaceRunService` (CRUD + soft delete)

**Files:**
- Create: `backend/src/services/workspace_run_service.py`
- Test: `backend/tests/services/test_workspace_run_service.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/test_workspace_run_service.py
import pytest
from datetime import datetime, UTC

from src.services.workspace_run_service import WorkspaceRunService


@pytest.mark.asyncio
async def test_create_run_uses_supplied_id(db_session):
    svc = WorkspaceRunService(db_session)
    run_id = await svc.create_run(
        run_id="es-1", workspace_id="ws1", thread_id="th1", title="t",
        started_at=datetime.now(UTC),
    )
    assert run_id == "es-1"


@pytest.mark.asyncio
async def test_complete_run_writes_result_card(db_session):
    svc = WorkspaceRunService(db_session)
    run_id = await svc.create_run(
        run_id="es-2", workspace_id="ws1", thread_id="th1", title="t",
        started_at=datetime.now(UTC),
    )
    await svc.complete_run(run_id, result_card={"tldr": "x"}, stats={"tokens": 100})
    run = await svc.get_run(run_id)
    assert run.status == "completed"
    assert run.result_card["tldr"] == "x"


@pytest.mark.asyncio
async def test_soft_delete(db_session):
    svc = WorkspaceRunService(db_session)
    run_id = await svc.create_run(
        run_id="es-3", workspace_id="ws1", thread_id="th1", title="t",
        started_at=datetime.now(UTC),
    )
    await svc.delete_run(run_id)
    assert await svc.get_run(run_id) is None
    listed = await svc.list_runs(thread_id="th1", include_deleted=True)
    assert any(r.id == run_id for r in listed)
```

- [ ] **Step 2: Run, expect FAIL**

```bash
cd backend && uv run pytest tests/services/test_workspace_run_service.py -v
```
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
# backend/src/services/workspace_run_service.py
"""CRUD for WorkspaceRun (spec §6.2 B3 — full persistence + soft-delete)."""
from datetime import datetime, UTC
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.workspace_run import WorkspaceRunRow


class WorkspaceRunService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create_run(
        self, *, run_id: str, workspace_id: str, thread_id: str, title: str, started_at: datetime
    ) -> str:
        """Create a workspace_run row with an *externally-supplied* run_id.

        The caller MUST pass `subagent.execution_session_id` as run_id so the
        persisted row matches the id used by the SSE event stream and the
        frontend `Run.id`. (Cross-plan invariant — see Plan 2 Task 3.)
        """
        row = WorkspaceRunRow(
            id=run_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            title=title,
            started_at=started_at,
            status="running",
            created_at=datetime.now(UTC),
        )
        self._s.add(row)
        await self._s.flush()
        return row.id

    async def complete_run(
        self, run_id: str, *, result_card: dict[str, Any], stats: dict[str, Any]
    ) -> None:
        row = await self._s.get(WorkspaceRunRow, run_id)
        if row is None or row.deleted_at is not None:
            return
        row.status = "completed"
        row.completed_at = datetime.now(UTC)
        row.result_card = result_card
        row.stats = stats
        await self._s.flush()

    async def get_run(self, run_id: str) -> WorkspaceRunRow | None:
        row = await self._s.get(WorkspaceRunRow, run_id)
        if row is None or row.deleted_at is not None:
            return None
        return row

    async def delete_run(self, run_id: str) -> None:
        row = await self._s.get(WorkspaceRunRow, run_id)
        if row is None:
            return
        row.deleted_at = datetime.now(UTC)
        await self._s.flush()

    async def list_runs(
        self, *, thread_id: str, include_deleted: bool = False
    ) -> list[WorkspaceRunRow]:
        stmt = select(WorkspaceRunRow).where(WorkspaceRunRow.thread_id == thread_id)
        if not include_deleted:
            stmt = stmt.where(WorkspaceRunRow.deleted_at.is_(None))
        stmt = stmt.order_by(WorkspaceRunRow.started_at)
        result = await self._s.execute(stmt)
        return list(result.scalars())
```

- [ ] **Step 4: Run, expect PASS**

```bash
cd backend && uv run pytest tests/services/test_workspace_run_service.py -v
```
Expected: 3 passed.

> If `db_session` fixture doesn't exist, locate the existing fixture pattern in `backend/tests/conftest.py` and reuse it.

- [ ] **Step 5: Commit**

```bash
git add backend/src/services/workspace_run_service.py \
        backend/tests/services/test_workspace_run_service.py
git commit -m "feat(services): WorkspaceRunService — create / complete / soft-delete"
```

---

## Task 15: Wire result_card to persist + `DELETE /runs/{id}`

**Files:**
- Modify: `backend/src/agents/lead_agent/agent.py` — call `WorkspaceRunService.complete_run` when emitting a `ResultCardBlock`
- Modify: `backend/src/gateway/routers/runs.py` — `DELETE`
- Test: extend `tests/gateway/test_runs_router.py`

- [ ] **Step 1: Add DELETE endpoint test**

```python
# append to tests/gateway/test_runs_router.py
def test_delete_run_returns_204(client, monkeypatch):
    called = {"id": None}
    async def fake_delete(self, run_id): called["id"] = run_id
    monkeypatch.setattr(WorkspaceRunService, "delete_run", fake_delete)
    r = client.delete("/workspaces/ws1/runs/r1")
    assert r.status_code == 204
    assert called["id"] == "r1"
```

(Add `from src.services.workspace_run_service import WorkspaceRunService` at top.)

- [ ] **Step 2: Run, expect FAIL**

```bash
cd backend && uv run pytest tests/gateway/test_runs_router.py::test_delete_run_returns_204 -v
```
Expected: FAIL — 404 / not implemented.

- [ ] **Step 3: Implement endpoint + wire persistence in agent**

In `backend/src/gateway/routers/runs.py`:

```python
@router.delete("/workspaces/{workspace_id}/runs/{run_id}", status_code=204)
async def delete_run(
    workspace_id: str,
    run_id: str,
    svc: WorkspaceRunService = Depends(get_workspace_run_service),
) -> None:
    await svc.delete_run(run_id)
```

Add `get_workspace_run_service` to `backend/src/gateway/dependencies.py`:

```python
def get_workspace_run_service(session: AsyncSession = Depends(get_session)) -> WorkspaceRunService:
    return WorkspaceRunService(session)
```

In `backend/src/agents/lead_agent/agent.py`, the lifecycle is:

1. **Run start** — when the agent first spawns a subagent for a turn (the `execution_session_id` is created), call `WorkspaceRunService.create_run(run_id=execution_session_id, ...)`. Use the user's input as the initial title; the agent can later overwrite it via the `result_card.title`.
2. **Run end** — when the agent emits a `ResultCardBlock`, call `complete_run` and update the title.

```python
from src.agents.lead_agent.blocks import ResultCardBlock
from src.services.workspace_run_service import WorkspaceRunService

# When the lead agent starts a new turn that will spawn a subagent run:
await workspace_run_service.create_run(
    run_id=execution_session_id,            # MUST equal subagent.execution_session_id
    workspace_id=ws_id, thread_id=thread_id,
    title=initial_title, started_at=datetime.now(UTC),
)

# … after parse_with_fallback, when iterating blocks for emission:
for block in msg.blocks:
    if isinstance(block, ResultCardBlock):
        # Persist + overwrite title to the agent's chosen one
        await workspace_run_service.complete_run(
            block.run_id,
            result_card=block.model_dump(),
            stats=block.stats.model_dump(),
        )
        # If you want the title saved too, extend WorkspaceRunService.complete_run
        # to accept it; or do an UPDATE on row.title in the same call.
    await emit_block(...)
```

**Cross-plan invariant**: `block.run_id` MUST equal the `execution_session_id` used in `subagent.updated` events. Both originate from the same value when the run is created.

- [ ] **Step 4: Run, expect PASS**

```bash
cd backend && uv run pytest tests/gateway/test_runs_router.py tests/agents/lead_agent/ -v
```
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add backend/src/gateway/routers/runs.py \
        backend/src/gateway/dependencies.py \
        backend/src/agents/lead_agent/agent.py \
        backend/tests/gateway/test_runs_router.py
git commit -m "feat(api): persist result_card to workspace_run; DELETE soft-removes a run"
```

---

## Task 16: End-to-end backend integration test (paper-analysis happy path)

**Files:**
- Create: `backend/tests/integration/test_paper_analysis_flow.py`

- [ ] **Step 1: Write the test**

```python
# backend/tests/integration/test_paper_analysis_flow.py
"""Spec §12 — end-to-end backend assertion for paper analysis run.

Drives the lead agent with a stubbed LLM that returns scripted AgentMessages,
asserts the SSE stream emits expected block types in order, persistence row
exists, and no jargon leaks.
"""
import pytest

from src.agents.lead_agent.blocks import (
    AgentMessage, FeedbackBlock, FeedbackPill, Finding, RunStats,
    ResultCardBlock, StatusLineBlock, TextBlock,
)
from src.agents.lead_agent.prompts.jargon import assert_no_jargon


@pytest.mark.asyncio
async def test_paper_analysis_emits_text_then_status_then_result(
    integration_app, scripted_llm, sse_client
):
    scripted_llm.queue([
        AgentMessage(blocks=[
            TextBlock(content="好，我先去扫这个交叉的文献版图。"),
            StatusLineBlock(label="启动 phase 1 · 检索文献", run_id="r1", phase_index=0),
        ]),
        AgentMessage(blocks=[
            StatusLineBlock(label="phase 1 完成 · 12 篇高相关 → 启动 phase 2", run_id="r1", phase_index=1),
        ]),
        AgentMessage(blocks=[
            StatusLineBlock(label="正在汇总结果（约 10-20s）", run_id="r1", tone="info"),
            ResultCardBlock(
                run_id="r1", title="论文分析 · 完成", tldr="3 个角度",
                findings=[Finding(id="1", text="异构客户端缺口")],
                feedback=FeedbackBlock(
                    question="这个结论你怎么看？",
                    pills=[FeedbackPill(kind="primary", label="进入选题", intent="next")],
                ),
                stats=RunStats(duration_ms=120000, subagents=13, tokens=8400),
            ),
        ]),
    ])

    events = await sse_client.collect(
        "/threads/th-x/runs/stream",
        post_body={"message": "我想写一篇论文，联邦学习结合大模型方向。"},
        until_block_kind="result_card",
    )

    kinds = [e["block"]["kind"] for e in events if e["type"] == "block"]
    # First text → first status_line → second status_line → status_line "汇总" → result_card
    assert kinds[0] == "text"
    assert kinds.count("status_line") >= 3
    assert kinds[-1] == "result_card"
    # Just before result_card is the "正在汇总" status_line
    summary_idx = kinds.index("result_card") - 1
    assert kinds[summary_idx] == "status_line"

    # No jargon in any output
    for ev in events:
        if ev["type"] == "block" and ev["block"]["kind"] in ("text", "status_line"):
            content = ev["block"].get("content") or ev["block"].get("label") or ""
            for token in ["message_feature_proposal", "意图置信度", "我会先复用"]:
                assert token not in content

    # Persistence happened
    from src.services.workspace_run_service import WorkspaceRunService
    async with integration_app.session_factory() as s:
        svc = WorkspaceRunService(s)
        run = await svc.get_run("r1")
        assert run.status == "completed"
        assert run.result_card["tldr"] == "3 个角度"
```

> Fixtures `integration_app`, `scripted_llm`, `sse_client` may already exist under `tests/integration/conftest.py`. If not, base them on existing patterns in `tests/agents/lead_agent/test_thread_feature_flow.py`.

- [ ] **Step 2: Run, expect either PASS or fixture-related FAIL**

```bash
cd backend && uv run pytest tests/integration/test_paper_analysis_flow.py -v
```
If fixtures missing, add them in `tests/integration/conftest.py` based on existing test setup.

- [ ] **Step 3: Commit when green**

```bash
git add backend/tests/integration/test_paper_analysis_flow.py backend/tests/integration/conftest.py
git commit -m "test(integration): paper analysis happy path — blocks, status order, persistence"
```

---

## Self-Review Checklist (run before declaring plan complete)

- [ ] **Spec coverage** — every spec section has a task:
  - §1 (background) — N/A motivation only
  - §2 (principles) — Tasks 4, 5 (prompts encode them)
  - §3 (architecture) — covered across all tasks
  - §4 (frontend components) — Plan 2
  - §5.1 AgentBlock schema — Task 1 ✓
  - §5.2 SSE block event — Task 7 ✓
  - §5.3 with_structured_output — Task 6 ✓
  - §5.4 result-card pre-summary status_line — Task 4 (in prompt) + Task 16 (assert in integration)
  - §5.5 JSON degradation — Task 2 ✓
  - §6.1 pause hook — Tasks 8, 9, 10 ✓
  - §6.2 persistence — Tasks 13, 14, 15 ✓
  - §6.3 severity — Tasks 11, 12 ✓
  - §7 URL params — Plan 3
  - §8 prompt rewrite — Tasks 4, 5 ✓
  - §10 testing — covered per task ✓
- [ ] **Placeholder scan** — none ✓
- [ ] **Type consistency** — `pause/resume/cancel` used identically across Tasks 8, 9, 10. `WorkspaceRunService.complete_run/delete_run/get_run/list_runs` consistent across Tasks 14, 15.

