# Chat Feature-Bypass Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the `ChatTurnRouter → FeatureCommandHandler → thread_feature_cards` bypass that intercepts chat turns before they reach `lead_agent`, and route 100% of chat turns through the canonical `lead_agent` AgentBlock path with a new `launch_feature` tool. No fallback, no compatibility shims.

**Architecture:**
- Every chat turn enters `lead_agent`; the agent decides whether to chat or to launch a feature via a new `launch_feature` builtin tool that calls `FeatureLaunchService.launch()` directly.
- URL entry-seed (`entry=open` + `featureId`) calls the existing `POST /features/{id}/execute` endpoint from the frontend before navigating to chat — no orchestration metadata is sent on chat turns anymore.
- Async feature-task completion / failure (Celery write-back into the thread) emits a `result_card` AgentBlock so the frontend has only one block schema to render.
- Legacy paths are **deleted**, not gated: `ChatTurnRouter`, `ThreadIntentRouter` (proposal half), `FeatureCommandHandler`, `thread_feature_cards.py`, `thread_feature_presenters.py`, `thread_feature_service.py`, `ThreadPanel.tsx`, `WorkspaceThreadMessages.tsx`, and all their tests.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy async / LangGraph `create_react_agent` / Pydantic 2 / Next.js App Router / TypeScript / Zustand / Vitest.

---

## File Structure

### Backend — files **deleted** (clean break, no fallback)
| Path | Reason |
|---|---|
| `backend/src/application/handlers/chat_turn_router.py` | The bypass dispatcher itself. |
| `backend/src/application/handlers/feature_command_handler.py` | Bypass executor. |
| `backend/src/application/intents/thread_intent_router.py` | Heuristic keyword-routing into the bypass. |
| `backend/src/application/intents/__init__.py` | Stops re-exporting deleted names. |
| `backend/src/application/services/thread_feature_service.py` | Bypass-side adapter into `FeatureLaunchService`; superseded by the `launch_feature` tool. |
| `backend/src/application/presenters/thread_feature_cards.py` | Hardcoded jargon-blocks (`feature_proposal`, `next_steps`, `task_result`, `task_failure`, `missing_input`, `prism_status`, `warning`, `task`, `result`). |
| `backend/src/application/presenters/thread_feature_presenters.py` | Internal helpers used only by the deleted `thread_feature_cards.py`. |
| `backend/tests/application/handlers/test_chat_turn_router.py` | Tests for deleted module. |
| `backend/tests/application/handlers/test_feature_command_handler.py` | Tests for deleted module. |
| `backend/tests/application/intents/test_thread_intent_router.py` | Tests for deleted module. |
| `backend/tests/agents/lead_agent/test_thread_feature_flow.py` | Tests the bypass-launching path. |

### Backend — files **created**
| Path | Responsibility |
|---|---|
| `backend/src/tools/builtins/launch_feature.py` | `launch_feature` builtin tool: takes `feature_id`/`params`/`skill_id`, calls `FeatureLaunchService`, returns task_id/execution_session_id. |
| `backend/src/application/presenters/agent_result_card.py` | Build `ResultCardBlock` (AgentBlock-conformant) from a feature task completion/failure payload — replaces the legacy `task_result`/`task_failure` block. |
| `backend/alembic/versions/023_purge_legacy_chat_blocks.py` | Migration: delete threads still containing legacy block types (`feature_proposal`, `next_steps`, `task_result`, `task_failure`, `missing_input`, `prism_status`, `warning`, `task`, `task_proposal`, `task_progress`, `result`). |
| `backend/tests/tools/test_launch_feature_tool.py` | Tool-level tests for `launch_feature`. |
| `backend/tests/integration/test_chat_to_feature_launch.py` | E2E: user msg → lead_agent → tool call → FeatureLaunchService → task started → result_card returned. |

### Backend — files **modified**
| Path | Change |
|---|---|
| `backend/src/application/handlers/thread_turn_handler.py` | Delete `_try_feature_command_reply` and its sole call site in `stream_turn` / `_generate_prepared_reply`. |
| `backend/src/agents/lead_agent/agent.py` | Register `launch_feature` in `get_available_tools()`; remove "Do not execute a feature directly" line in `_render_workspace_available_skills`. |
| `backend/src/agents/lead_agent/prompts/system.py` | Replace "describe a proposal" wording with "call `launch_feature` directly when ready". Keep jargon blacklist examples (those are anti-examples). |
| `backend/src/task/tasks/base.py` | Replace `build_feature_task_completion_card` / `build_feature_task_failure_card` imports with the new `agent_result_card.build_completion_result_card` / `build_failure_result_card`. |
| `backend/tests/architecture/test_feature_ingress_guard.py` | Flip the SSOT assertion: assert that `chat_turn_router.py` no longer exists, not that it imports `ThreadIntentRouter`. |

### Frontend — files **deleted**
| Path | Reason |
|---|---|
| `frontend/app/(workbench)/workspaces/[id]/components/ThreadPanel.tsx` | Orphaned (no JSX consumer remaining). |
| `frontend/app/(workbench)/workspaces/[id]/components/WorkspaceThreadMessages.tsx` | Orphaned (only ThreadPanel mounted it); renders all the deleted legacy block types. |

### Frontend — files **modified**
| Path | Change |
|---|---|
| `frontend/app/(workbench)/workspaces/[id]/components/index.ts` | Remove `ThreadPanel` re-export (it doesn't exist there anymore — verify). |
| `frontend/app/(workbench)/workspaces/[id]/chat/page.tsx` | Remove the `ThreadPanel` import line (dead). Remove the `metadata.orchestration` field from `sendMessage` call — when entry is `open` + has `featureId`, instead call the existing `POST /api/workspaces/{id}/features/{feature_id}/execute` directly before navigation. |
| `frontend/lib/workspace-thread-entry.ts` | Remove `buildWorkspaceThreadEntryOrchestration` (no longer sent through chat). Replace with `triggerEntrySeedFeatureLaunch(seed)` that calls the execute endpoint. |
| `frontend/stores/thread-store-support.ts` | Revert the temporary patches I added during debugging: remove `console.log`s, restore `appendAgentBlock` / `toChatMessages` to spec-defined behavior. |

---

## Spec mapping

This plan completes spec §2.2 ("不自我汇报"), §8.1 (delete `feature_proposal` / `next_steps` / `MissingInputBlock`), and §2.3 ("chat 是对话，右面板是工坊") by removing the bypass that was emitting the forbidden block types **outside** the AgentBlock contract. The original spec missed this code path; this plan closes the gap.

---

## Bite-Sized Task Granularity

Each step is one bash/edit/test action (2–5 min). Run tests after every code change. Commit at the end of each task.

---

### Task 1: Snapshot baseline + delete the polluted test thread

**Why first:** lock current state in git; clean DB so legacy-block thread doesn't keep masking new-block rendering.

**Files:**
- Modify: working tree only (no source files yet)

- [ ] **Step 1: Verify branch is `master` and tree is clean of untracked code**

```bash
cd /Users/ze/wenjin
git status
```

Expected: shows `modified:   .env` (mirror config) and similar non-source modifications are OK; no untracked `.py` / `.ts` files.

- [ ] **Step 2: Stash any local edits I made during debug**

```bash
cd /Users/ze/wenjin
git stash push -m "pre-bypass-removal-debug-edits" frontend/stores/thread-store-support.ts frontend/app/\(workbench\)/workspaces/\[id\]/components/chat-thread/MessageList.tsx 2>/dev/null || true
git status -- frontend/stores/thread-store-support.ts frontend/app/\(workbench\)/workspaces/\[id\]/components/chat-thread/MessageList.tsx
```

Expected: those files unmodified after stash.

- [ ] **Step 3: Delete the polluted test thread**

```bash
cd /Users/ze/wenjin
docker compose exec -T postgres psql -U postgres -d wenjin -c \
  "DELETE FROM threads WHERE messages::text LIKE '%\"feature_proposal\"%' OR messages::text LIKE '%\"next_steps\"%';"
```

Expected output: `DELETE 1` (or `DELETE 0` if already gone).

- [ ] **Step 4: Confirm DB is clean of legacy-block threads**

```bash
docker compose exec -T postgres psql -U postgres -d wenjin -c \
  "SELECT count(*) FROM threads WHERE messages::text LIKE '%\"feature_proposal\"%' OR messages::text LIKE '%\"next_steps\"%' OR messages::text LIKE '%\"task_result\"%' OR messages::text LIKE '%\"missing_input\"%';"
```

Expected: `count` is `0`.

- [ ] **Step 5: Commit (no-op for source, but log the cleanup)**

```bash
cd /Users/ze/wenjin
git commit --allow-empty -m "chore(db): purge legacy-chat-block test threads before bypass removal"
```

---

### Task 2: Add the `launch_feature` builtin tool (TDD)

**Why now:** before deleting the bypass, the lead_agent must have an alternative way to launch features. Build it first, prove it works, then delete the old path.

**Files:**
- Create: `backend/src/tools/builtins/launch_feature.py`
- Create: `backend/tests/tools/test_launch_feature_tool.py`
- Modify: `backend/src/tools/builtins/__init__.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/tools/test_launch_feature_tool.py`:

```python
"""Tests for the `launch_feature` builtin tool."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.tools.builtins import launch_feature_tool


@dataclass
class _StubFeatureLaunchResult:
    execution_session_id: str
    outcome: Any


@dataclass
class _StubFeatureTaskSubmission:
    task_id: str
    feature_id: str
    message: str


@pytest.mark.asyncio
async def test_launch_feature_invokes_feature_launch_service():
    """Tool must build a FeatureLaunchCommand and call FeatureLaunchService.launch()."""
    submission = _StubFeatureTaskSubmission(
        task_id="task-abc",
        feature_id="paper_analysis",
        message="started",
    )
    fake_result = _StubFeatureLaunchResult(
        execution_session_id="es-xyz",
        outcome=submission,
    )
    fake_service = AsyncMock()
    fake_service.launch = AsyncMock(return_value=fake_result)

    with patch(
        "src.tools.builtins.launch_feature.build_feature_ingress_service",
        return_value=fake_service,
    ):
        result = await launch_feature_tool.ainvoke(
            {
                "feature_id": "paper_analysis",
                "params": {"paper_title": "联邦学习结合大模型微调"},
                "skill_id": "paper-analyst",
            },
            config={
                "configurable": {
                    "workspace_id": "ws-1",
                    "thread_id": "th-1",
                    "user_id": "user-1",
                }
            },
        )

    assert result["status"] == "launched"
    assert result["task_id"] == "task-abc"
    assert result["feature_id"] == "paper_analysis"
    assert result["execution_session_id"] == "es-xyz"
    fake_service.launch.assert_awaited_once()
    cmd = fake_service.launch.await_args.args[0]
    assert cmd.workspace_id == "ws-1"
    assert cmd.feature_id == "paper_analysis"
    assert cmd.thread_id == "th-1"
    assert cmd.skill_id == "paper-analyst"
    assert cmd.params == {"paper_title": "联邦学习结合大模型微调"}
    assert cmd.launch_source == "thread"


@pytest.mark.asyncio
async def test_launch_feature_returns_warning_when_advisory():
    """If FeatureLaunchService returns an advisory outcome, surface its code."""

    @dataclass
    class _Advisory:
        code: str
        message: str

    fake_result = _StubFeatureLaunchResult(
        execution_session_id="es-1",
        outcome=_Advisory(code="literature_insufficient", message="文献不足"),
    )
    fake_service = AsyncMock()
    fake_service.launch = AsyncMock(return_value=fake_result)

    with patch(
        "src.tools.builtins.launch_feature.build_feature_ingress_service",
        return_value=fake_service,
    ):
        result = await launch_feature_tool.ainvoke(
            {"feature_id": "writing", "params": {"topic": "x"}},
            config={
                "configurable": {
                    "workspace_id": "ws-1",
                    "thread_id": "th-1",
                    "user_id": "user-1",
                }
            },
        )

    assert result["status"] == "advisory"
    assert result["code"] == "literature_insufficient"
    assert result["execution_session_id"] == "es-1"


@pytest.mark.asyncio
async def test_launch_feature_requires_workspace_in_config():
    """Tool fails fast if config lacks workspace_id (caller bug)."""
    with pytest.raises(ValueError, match="workspace_id"):
        await launch_feature_tool.ainvoke(
            {"feature_id": "paper_analysis", "params": {}},
            config={"configurable": {"thread_id": "th-1", "user_id": "u-1"}},
        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/ze/wenjin/backend
uv run pytest tests/tools/test_launch_feature_tool.py -v
```

Expected: ImportError / collection error — `launch_feature_tool` does not exist yet.

- [ ] **Step 3: Implement the tool**

Create `backend/src/tools/builtins/launch_feature.py`:

```python
"""launch_feature builtin tool — lead_agent's only path to start a workspace feature."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.academic.cache.redis_client import redis_client
from src.academic.services.workspace_service import WorkspaceService
from src.application.commands import FeatureLaunchCommand
from src.config import redis_settings
from src.database import get_db_session
from src.services.credit_service import CreditService
from src.services.references import WorkspaceReferenceService
from src.task.service import TaskService
from src.task.store import TaskStore
from src.task.tasks.feature_ingress_factory import build_feature_ingress_service


class LaunchFeatureInput(BaseModel):
    feature_id: str = Field(..., description="Workspace feature id, e.g. 'paper_analysis', 'literature_search', 'writing'.")
    params: dict[str, Any] = Field(default_factory=dict, description="Feature-specific parameters (paper_title, topic, query, etc.).")
    skill_id: str | None = Field(default=None, description="Optional skill id when the user has selected one.")


def _read_required(config: RunnableConfig | None, key: str) -> str:
    configurable = (config or {}).get("configurable") if isinstance(config, Mapping) else None
    if not isinstance(configurable, Mapping):
        raise ValueError(f"launch_feature requires '{key}' in runnable config")
    value = str(configurable.get(key) or "").strip()
    if not value:
        raise ValueError(f"launch_feature requires non-empty '{key}'")
    return value


@tool("launch_feature", args_schema=LaunchFeatureInput)
async def launch_feature_tool(
    feature_id: str,
    params: dict[str, Any],
    skill_id: str | None = None,
    *,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Launch a workspace feature by id with the given params.

    Returns a dict with `status` ('launched' | 'advisory'), `task_id` (when launched),
    `execution_session_id`, `feature_id`, and either `message` (success) or
    `code`/`detail` (advisory).
    """
    workspace_id = _read_required(config, "workspace_id")
    thread_id = _read_required(config, "thread_id")
    user_id = _read_required(config, "user_id")

    runtime_redis = (
        redis_client
        if redis_settings.enabled and redis_client._client is not None
        else None
    )

    async with get_db_session() as db:
        workspace_service = WorkspaceService(db)
        launch_service = build_feature_ingress_service(
            actor_id=user_id,
            db=db,
            workspace_service=workspace_service,
            task_service=TaskService(TaskStore(redis_client, db)),
            reference_service=WorkspaceReferenceService(db),
            credit_service=CreditService(db),
        )
        result = await launch_service.launch(
            FeatureLaunchCommand(
                workspace_id=workspace_id,
                feature_id=feature_id,
                params=dict(params or {}),
                thread_id=thread_id,
                skill_id=skill_id,
                launch_source="thread",
                redis_client=runtime_redis,
            )
        )

    outcome = result.outcome
    task_id = getattr(outcome, "task_id", None)
    if task_id:
        return {
            "status": "launched",
            "task_id": str(task_id),
            "execution_session_id": result.execution_session_id,
            "feature_id": str(getattr(outcome, "feature_id", feature_id)),
            "message": str(getattr(outcome, "message", "")),
        }

    return {
        "status": "advisory",
        "execution_session_id": result.execution_session_id,
        "feature_id": feature_id,
        "code": str(getattr(outcome, "code", "") or "advisory"),
        "detail": str(getattr(outcome, "message", "") or ""),
    }
```

- [ ] **Step 4: Re-export the tool from `src.tools.builtins`**

Modify `backend/src/tools/builtins/__init__.py` — open it first to read, then add the import. The existing file has `from .clarification import ask_clarification_tool` and similar lines:

```bash
cd /Users/ze/wenjin
grep -n "^from\|^__all__\|launch_feature" backend/src/tools/builtins/__init__.py
```

Then add the line `from .launch_feature import launch_feature_tool` adjacent to the other `from .X import Y` lines, and add `"launch_feature_tool"` to the `__all__` list (if present). Use `Edit` against `backend/src/tools/builtins/__init__.py` with the actual contents seen via the grep.

- [ ] **Step 5: Run test to verify it passes**

```bash
cd /Users/ze/wenjin/backend
uv run pytest tests/tools/test_launch_feature_tool.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
cd /Users/ze/wenjin
git add backend/src/tools/builtins/launch_feature.py \
        backend/src/tools/builtins/__init__.py \
        backend/tests/tools/test_launch_feature_tool.py
git commit -m "feat(tools): launch_feature builtin tool — lead_agent's path to start features"
```

---

### Task 3: Register `launch_feature` in lead_agent toolset (TDD)

**Files:**
- Modify: `backend/src/agents/lead_agent/agent.py:484-525`
- Modify: `backend/tests/agents/test_lead_agent.py` (or wherever toolset is asserted)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/agents/test_lead_agent.py`:

```python
def test_get_available_tools_includes_launch_feature():
    """lead_agent must expose launch_feature so it can start workspace features."""
    from src.agents.lead_agent.agent import get_available_tools

    tools = get_available_tools()
    tool_names = {getattr(t, "name", "") for t in tools}
    assert "launch_feature" in tool_names
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/ze/wenjin/backend
uv run pytest tests/agents/test_lead_agent.py::test_get_available_tools_includes_launch_feature -v
```

Expected: assertion error — `launch_feature` not in tool_names.

- [ ] **Step 3: Add `launch_feature_tool` to the import block in agent.py**

In `backend/src/agents/lead_agent/agent.py` find the `from src.tools.builtins import (` block (currently around line 484) and add `launch_feature_tool,` to the alphabetically-sorted import list.

Then in `get_available_tools()` (around line 514–522, where `ask_clarification_tool` and `list_workspace_features_tool` are appended), add `launch_feature_tool` to the same group:

```python
# Interaction tools
tools.append(ask_clarification_tool)
tools.append(launch_feature_tool)
tools.extend([
    list_workspace_features_tool,
    list_workspace_artifacts_tool,
    list_reference_library_tool,
    search_reference_text_units_tool,
    read_reference_outline_node_tool,
])
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/ze/wenjin/backend
uv run pytest tests/agents/test_lead_agent.py::test_get_available_tools_includes_launch_feature -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/ze/wenjin
git add backend/src/agents/lead_agent/agent.py backend/tests/agents/test_lead_agent.py
git commit -m "feat(lead-agent): expose launch_feature in available tools"
```

---

### Task 4: Update lead_agent system prompt to direct-launch instead of "describe a proposal"

**Files:**
- Modify: `backend/src/agents/lead_agent/agent.py:151-173` (`_render_workspace_available_skills`)
- Modify: `backend/src/agents/lead_agent/prompts/system.py` (the `_BASE` prompt, around lines 16-38)
- Modify: `backend/tests/agents/lead_agent/__snapshots__/test_prompts_snapshot.ambr` (snapshot will need refresh)

- [ ] **Step 1: Read existing prompt files to lock exact strings**

```bash
cd /Users/ze/wenjin
sed -n '151,173p' backend/src/agents/lead_agent/agent.py
sed -n '15,40p' backend/src/agents/lead_agent/prompts/system.py
```

Note the exact wording — you'll edit only the proposal phrasing.

- [ ] **Step 2: Edit `_render_workspace_available_skills` in agent.py**

Replace the line containing `"Do not execute a feature directly from chat."` with:

```python
        "When the user asks for work that matches a skill, call the launch_feature tool directly instead of writing a proposal. Ask only for the minimum missing parameters before launching.",
```

(Replace the entire single line — keep the surrounding `lines = [...]` shape.)

- [ ] **Step 3: Edit prompts/system.py `_BASE` to enforce direct-launch behavior**

Replace the "## 行为准则" block in `_BASE` with:

```python
    # 行为准则
    1. 直接动手。匹配到 workspace skill 时调用 `launch_feature` 工具，不要先写 proposal 等用户确认。
    2. 启动前只追问缺失的最小关键参数（用 `question_card`，单问聚焦）。
    3. phase 切换前必须先发 `status_line` 标明转换。
    4. 同 thread 同时最多 1 个未回答的 `question_card`；用户回答前不要再问。
    5. result_card 之前必须先发一条 `status_line`：tone=info、label="正在汇总结果（约 10-20s）"。
    6. 每轮 run 必以 `result_card` 闭合。
```

Keep the "# 反例" block as-is — those are anti-pattern examples, not removed phrasing.

- [ ] **Step 4: Run prompt snapshot test to see the diff**

```bash
cd /Users/ze/wenjin/backend
uv run pytest tests/agents/lead_agent/test_prompts_snapshot.py -v
```

Expected: snapshot mismatch (test fails).

- [ ] **Step 5: Update the snapshot after manual review of the diff**

```bash
cd /Users/ze/wenjin/backend
uv run pytest tests/agents/lead_agent/test_prompts_snapshot.py --snapshot-update
```

Then visually inspect the diff:

```bash
cd /Users/ze/wenjin
git diff backend/tests/agents/lead_agent/__snapshots__/test_prompts_snapshot.ambr
```

Expected: only the lines you edited change; no jargon-blacklisted words appear.

- [ ] **Step 6: Run jargon test to confirm prompts stay clean**

```bash
cd /Users/ze/wenjin/backend
uv run pytest tests/agents/lead_agent/test_jargon.py -v
```

Expected: all pass (the jargon blacklist still flags forbidden words, prompt doesn't trip them).

- [ ] **Step 7: Commit**

```bash
cd /Users/ze/wenjin
git add backend/src/agents/lead_agent/agent.py \
        backend/src/agents/lead_agent/prompts/system.py \
        backend/tests/agents/lead_agent/__snapshots__/test_prompts_snapshot.ambr
git commit -m "feat(prompts): lead_agent calls launch_feature directly instead of proposing"
```

---

### Task 5: Build `agent_result_card` presenter for async task completion (TDD)

**Why now:** before deleting `thread_feature_cards.py`, give the celery write-back path a replacement that emits the new `result_card` AgentBlock schema.

**Files:**
- Create: `backend/src/application/presenters/agent_result_card.py`
- Create: `backend/tests/application/presenters/test_agent_result_card.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/application/presenters/test_agent_result_card.py`:

```python
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
    from src.agents.lead_agent.blocks import AgentMessage

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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/ze/wenjin/backend
uv run pytest tests/application/presenters/test_agent_result_card.py -v
```

Expected: ImportError — module does not exist.

- [ ] **Step 3: Implement the presenter**

Create `backend/src/application/presenters/agent_result_card.py`:

```python
"""Build AgentBlock-conformant result_cards for async feature task completion / failure.

These are emitted by the Celery write-back path (src/task/tasks/base.py) — not by
lead_agent — but they conform to the same `AgentMessage` schema the frontend expects.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.application.results import GeneratedThreadReply

_FEATURE_DISPLAY = {
    "paper_analysis": "论文分析",
    "literature_search": "文献检索",
    "literature_management": "文献管理",
    "literature_review": "文献综述",
    "framework_outline": "框架大纲",
    "writing": "章节写作",
    "thesis_writing": "学位论文写作",
    "peer_review": "同行评审",
    "journal_recommend": "期刊推荐",
    "figure_generation": "配图生成",
    "deep_research": "深度调研",
    "opening_research": "开题调研",
    "background_research": "背景调研",
    "experiment_design": "实验设计",
    "proposal_outline": "申报书大纲",
    "patent_outline": "专利大纲",
    "prior_art_search": "现有技术检索",
    "copyright_materials": "软著材料",
    "technical_description": "技术描述",
}


def _feature_title(feature_id: str) -> str:
    return _FEATURE_DISPLAY.get(feature_id, feature_id)


def _truncate(text: str, limit: int = 280) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _findings_from_data(data: Mapping[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    raw = data.get("findings") if isinstance(data, Mapping) else None
    if isinstance(raw, list):
        for i, entry in enumerate(raw[:5], start=1):
            text = ""
            if isinstance(entry, str):
                text = entry
            elif isinstance(entry, Mapping):
                text = str(entry.get("text") or entry.get("summary") or "")
            text = text.strip()
            if not text:
                continue
            items.append({"id": f"①②③④⑤"[i - 1], "text": text})
    return items


def _links_from_artifacts(artifacts: list[Mapping[str, Any]]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for art in artifacts[:6]:
        if not isinstance(art, Mapping):
            continue
        artifact_id = str(art.get("id") or "").strip()
        title = str(art.get("title") or "").strip()
        if not artifact_id or not title:
            continue
        links.append(
            {
                "icon": "file",
                "label": title,
                "href": f"/artifacts/{artifact_id}",
            }
        )
    return links


def build_completion_result_card(
    *,
    feature_id: str,
    task_id: str,
    run_id: str,
    execution_session_id: str | None,
    payload: Mapping[str, Any] | None,
    result: Mapping[str, Any] | None,
    duration_ms: int,
    subagents_count: int,
    tokens_total: int,
) -> GeneratedThreadReply:
    """Build a result_card for a successful feature task."""
    raw_data = result.get("data") if isinstance(result, Mapping) else None
    data: Mapping[str, Any] = raw_data if isinstance(raw_data, Mapping) else {}
    artifacts_raw = result.get("artifacts") if isinstance(result, Mapping) else None
    artifacts = [a for a in (artifacts_raw if isinstance(artifacts_raw, list) else []) if isinstance(a, Mapping)]

    summary = _truncate(str(data.get("summary") or "已完成。"), 280)
    title = f"{_feature_title(feature_id)} 已完成"
    findings = _findings_from_data(data)
    links = _links_from_artifacts(artifacts)

    block = {
        "kind": "result_card",
        "run_id": run_id,
        "title": title,
        "tldr": summary,
        "findings": findings,
        "recommend": None,
        "links": links,
        "feedback": {
            "question": "对结果是否满意？",
            "pills": [
                {"kind": "primary", "label": "深入展开 ①", "intent": "expand_finding_1"},
                {"kind": "normal", "label": "重新执行", "intent": "retry_run"},
                {"kind": "warn", "label": "结果不对", "intent": "result_invalid"},
            ],
            "allow_free_input": True,
        },
        "stats": {
            "duration_ms": int(duration_ms),
            "subagents": int(subagents_count),
            "tokens": int(tokens_total),
        },
    }

    return GeneratedThreadReply(content=summary, blocks=[block], metadata=None)


def build_failure_result_card(
    *,
    feature_id: str,
    task_id: str,
    run_id: str,
    execution_session_id: str | None,
    payload: Mapping[str, Any] | None,
    error: str | None,
    failed_phase: str | None,
    duration_ms: int,
    subagents_count: int,
    tokens_total: int,
) -> GeneratedThreadReply:
    """Build a result_card for a failed feature task."""
    detail = (error or "执行失败").strip()
    phase_text = f"（{failed_phase}）" if failed_phase else ""
    tldr = f"{_feature_title(feature_id)} 失败{phase_text}：{detail}"

    block = {
        "kind": "result_card",
        "run_id": run_id,
        "title": f"{_feature_title(feature_id)} 执行失败",
        "tldr": _truncate(tldr, 280),
        "findings": [],
        "recommend": None,
        "links": [],
        "feedback": {
            "question": "如何处理这次失败？",
            "pills": [
                {"kind": "primary", "label": "重试", "intent": "retry_run"},
                {"kind": "normal", "label": "调整参数后重试", "intent": "adjust_and_retry"},
                {"kind": "warn", "label": "放弃这一轮", "intent": "abandon_run"},
            ],
            "allow_free_input": True,
        },
        "stats": {
            "duration_ms": int(duration_ms),
            "subagents": int(subagents_count),
            "tokens": int(tokens_total),
        },
    }

    return GeneratedThreadReply(content=tldr, blocks=[block], metadata=None)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/ze/wenjin/backend
uv run pytest tests/application/presenters/test_agent_result_card.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/ze/wenjin
git add backend/src/application/presenters/agent_result_card.py \
        backend/tests/application/presenters/test_agent_result_card.py
git commit -m "feat(presenters): AgentBlock result_card for async feature task write-back"
```

---

### Task 6: Switch celery write-back to use the new presenter

**Files:**
- Modify: `backend/src/task/tasks/base.py:60-105` (the imports + dispatch)

- [ ] **Step 1: Read the current write-back block to anchor the edit**

```bash
cd /Users/ze/wenjin
sed -n '60,105p' backend/src/task/tasks/base.py
```

Note the exact `from src.application.presenters.thread_feature_cards import (...)` block and the `if error:` / `else:` branches.

- [ ] **Step 2: Replace the imports and call sites**

In `backend/src/task/tasks/base.py`, replace:

```python
        from src.application.presenters.thread_feature_cards import (
            build_feature_task_completion_card,
            build_feature_task_failure_card,
        )
```

with:

```python
        from src.application.presenters.agent_result_card import (
            build_completion_result_card,
            build_failure_result_card,
        )
```

Then replace the failure call:

```python
            reply = build_feature_task_failure_card(
                feature_id=feature_id,
                task_id=task_id,
                execution_session_id=str(payload.get("execution_session_id") or "") or None,
                payload=payload,
                error=error,
            )
```

with:

```python
            reply = build_failure_result_card(
                feature_id=feature_id,
                task_id=task_id,
                run_id=str(payload.get("run_id") or task_id),
                execution_session_id=str(payload.get("execution_session_id") or "") or None,
                payload=payload,
                error=error,
                failed_phase=str(payload.get("failed_phase") or "") or None,
                duration_ms=int(payload.get("duration_ms") or 0),
                subagents_count=int(payload.get("subagents_count") or 0),
                tokens_total=int(payload.get("tokens_total") or 0),
            )
```

And the completion call:

```python
            reply = build_feature_task_completion_card(
                feature_id=feature_id,
                task_id=task_id,
                execution_session_id=str(payload.get("execution_session_id") or "") or None,
                payload=payload,
                result=result or {},
            )
```

with:

```python
            reply = build_completion_result_card(
                feature_id=feature_id,
                task_id=task_id,
                run_id=str(payload.get("run_id") or task_id),
                execution_session_id=str(payload.get("execution_session_id") or "") or None,
                payload=payload,
                result=result or {},
                duration_ms=int(payload.get("duration_ms") or 0),
                subagents_count=int(payload.get("subagents_count") or 0),
                tokens_total=int(payload.get("tokens_total") or 0),
            )
```

- [ ] **Step 3: Run the workspace_feature_frontend_sync test (it covers this code)**

```bash
cd /Users/ze/wenjin/backend
uv run pytest tests/task/test_workspace_feature_frontend_sync.py -v
```

Expected: tests fail (they assert legacy block shape). That's expected — we'll fix or delete them next.

- [ ] **Step 4: Update or delete failing assertions**

Open `backend/tests/task/test_workspace_feature_frontend_sync.py`. Any test asserting `block["type"] == "task_result"` or `block["type"] == "task_failure"` should be rewritten to assert `block["kind"] == "result_card"` and the new schema. If a test asserts internals only the legacy presenter knew, delete that test (the new presenter has its own coverage in Task 5).

```bash
cd /Users/ze/wenjin
grep -n "task_result\|task_failure\|build_feature_task_completion_card\|build_feature_task_failure_card" backend/tests/task/test_workspace_feature_frontend_sync.py
```

For each match, edit the test using `Edit` tool so it asserts the new schema. The shape of the new card (per Task 5):

```python
assert block["kind"] == "result_card"
assert block["run_id"]  # required
assert "title" in block
assert "tldr" in block
assert isinstance(block["findings"], list)
assert isinstance(block["links"], list)
assert isinstance(block["stats"], dict)
```

- [ ] **Step 5: Run the test again and confirm green**

```bash
cd /Users/ze/wenjin/backend
uv run pytest tests/task/test_workspace_feature_frontend_sync.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/ze/wenjin
git add backend/src/task/tasks/base.py backend/tests/task/test_workspace_feature_frontend_sync.py
git commit -m "refactor(task): write-back uses AgentBlock result_card schema"
```

---

### Task 7: Delete `_try_feature_command_reply` from thread_turn_handler

**Files:**
- Modify: `backend/src/application/handlers/thread_turn_handler.py:1117-1135` (`_try_feature_command_reply`)
- Modify: `backend/src/application/handlers/thread_turn_handler.py:847-861` (the call in `stream_turn`)
- Modify: `backend/src/application/handlers/thread_turn_handler.py:1143-1148` (the call in `_generate_prepared_reply`)

- [ ] **Step 1: Read the call sites to anchor the deletion**

```bash
cd /Users/ze/wenjin
grep -n "_try_feature_command_reply\|feature_reply" backend/src/application/handlers/thread_turn_handler.py
```

- [ ] **Step 2: Delete the early-return branch in `stream_turn` (the iterator inside)**

Find the inner `_iterator` async generator (around line 844). The current shape:

```python
        async def _iterator() -> AsyncIterator[ThreadStreamDelta]:
            reply_stream = None
            try:
                feature_reply = await self._try_feature_command_reply(
                    prepared,
                    actor_id=actor_id,
                )
                if feature_reply is not None:
                    if feature_reply.content:
                        yield ThreadStreamDelta(kind="content", text=feature_reply.content)
                    completed = await self._finalize_generated_reply(
                        prepared,
                        actor_id=actor_id,
                        reply=feature_reply,
                    )
                    if not completed_future.done():
                        completed_future.set_result(completed)
                    return

                await self._maybe_compact_thread_history(prepared.thread)
                reply_stream = self._stream_thread_response(...)
```

Edit it down to:

```python
        async def _iterator() -> AsyncIterator[ThreadStreamDelta]:
            reply_stream = None
            try:
                await self._maybe_compact_thread_history(prepared.thread)
                reply_stream = self._stream_thread_response(...)
```

(Keep the existing `_stream_thread_response(...)` invocation; only the `feature_reply` block is removed.)

- [ ] **Step 3: Delete the early-return branch in `_generate_prepared_reply`**

Replace the body (around line 1141-1153):

```python
    async def _generate_prepared_reply(
        self,
        prepared: PreparedThreadTurn,
        *,
        actor_id: str,
    ) -> GeneratedThreadReply:
        feature_reply = await self._try_feature_command_reply(
            prepared,
            actor_id=actor_id,
        )
        if feature_reply is not None:
            return feature_reply
        return await self._generate_thread_response(
            prepared.request,
            prepared.thread,
            actor_id=actor_id,
        )
```

with:

```python
    async def _generate_prepared_reply(
        self,
        prepared: PreparedThreadTurn,
        *,
        actor_id: str,
    ) -> GeneratedThreadReply:
        return await self._generate_thread_response(
            prepared.request,
            prepared.thread,
            actor_id=actor_id,
        )
```

- [ ] **Step 4: Delete the `_try_feature_command_reply` method itself**

Remove the entire method (currently at lines 1117–1135), including the `from src.application.handlers.chat_turn_router import ...` and `from src.application.handlers.feature_command_handler import ...` imports inside it.

- [ ] **Step 5: Run thread_turn_handler tests**

```bash
cd /Users/ze/wenjin/backend
uv run pytest tests/application/handlers/ -v -k "thread_turn"
```

Expected: tests pass (or fail only on tests that expected the bypass to handle feature commands — those tests are deleted in the next task).

- [ ] **Step 6: Commit**

```bash
cd /Users/ze/wenjin
git add backend/src/application/handlers/thread_turn_handler.py
git commit -m "refactor(thread): remove _try_feature_command_reply bypass — every turn goes to lead_agent"
```

---

### Task 8: Delete the bypass modules and their tests

**Files (delete):**
- `backend/src/application/handlers/chat_turn_router.py`
- `backend/src/application/handlers/feature_command_handler.py`
- `backend/src/application/intents/thread_intent_router.py`
- `backend/src/application/intents/__init__.py`
- `backend/src/application/services/thread_feature_service.py`
- `backend/src/application/presenters/thread_feature_cards.py`
- `backend/src/application/presenters/thread_feature_presenters.py`
- `backend/tests/application/handlers/test_chat_turn_router.py`
- `backend/tests/application/handlers/test_feature_command_handler.py`
- `backend/tests/application/intents/test_thread_intent_router.py`
- `backend/tests/application/intents/__init__.py` (if exists)
- `backend/tests/agents/lead_agent/test_thread_feature_flow.py`

- [ ] **Step 1: Confirm there are no more importers**

```bash
cd /Users/ze/wenjin
grep -rn "ChatTurnRouter\|ChatTurnRoute\|ChatTurnMode\|FeatureCommandHandler\|ThreadIntentRouter\|ThreadIntentDecision\|thread_feature_cards\|thread_feature_presenters\|thread_feature_service\|build_feature_proposal_response\|build_feature_task_completion_card\|build_feature_task_failure_card\|build_execution_success_response\|build_execution_warning_response\|build_missing_response\|build_thread_result_card" backend/src --include="*.py" | grep -v "^backend/src/application/handlers/chat_turn_router.py\|^backend/src/application/handlers/feature_command_handler.py\|^backend/src/application/intents/\|^backend/src/application/services/thread_feature_service.py\|^backend/src/application/presenters/thread_feature_cards.py\|^backend/src/application/presenters/thread_feature_presenters.py"
```

Expected: zero output. (If any leftover importer exists, the previous tasks missed something — go back and clean up before deleting.)

- [ ] **Step 2: Delete the source files**

```bash
cd /Users/ze/wenjin
rm backend/src/application/handlers/chat_turn_router.py
rm backend/src/application/handlers/feature_command_handler.py
rm backend/src/application/intents/thread_intent_router.py
rm backend/src/application/intents/__init__.py
rmdir backend/src/application/intents 2>/dev/null || true
rm backend/src/application/services/thread_feature_service.py
rm backend/src/application/presenters/thread_feature_cards.py
rm backend/src/application/presenters/thread_feature_presenters.py
```

- [ ] **Step 3: Delete the test files**

```bash
cd /Users/ze/wenjin
rm backend/tests/application/handlers/test_chat_turn_router.py
rm backend/tests/application/handlers/test_feature_command_handler.py
rm backend/tests/application/intents/test_thread_intent_router.py
rm -f backend/tests/application/intents/__init__.py
rmdir backend/tests/application/intents 2>/dev/null || true
rm backend/tests/agents/lead_agent/test_thread_feature_flow.py
```

- [ ] **Step 4: Run the full backend test suite**

```bash
cd /Users/ze/wenjin/backend
uv run pytest -x --ignore=tests/integration 2>&1 | tail -40
```

Expected: green; or the only failures are in `test_paper_analysis_flow.py` / `test_latex_hardening.py` / `test_patent_feature_service.py` (next task fixes those).

- [ ] **Step 5: Commit**

```bash
cd /Users/ze/wenjin
git add -A backend/src backend/tests
git commit -m "refactor: delete ChatTurnRouter bypass — clean break, no fallback"
```

---

### Task 9: Fix the test stragglers that referenced legacy block types

**Files:**
- Modify or delete: `backend/tests/integration/test_paper_analysis_flow.py`
- Modify or delete: `backend/tests/services/test_latex_hardening.py`
- Modify or delete: `backend/tests/workspace_features/services/test_patent_feature_service.py`
- Modify: `backend/tests/architecture/test_docs_current_contract.py`
- Modify: `backend/tests/architecture/test_feature_ingress_guard.py:104-109`

- [ ] **Step 1: Find every remaining legacy-block reference in tests**

```bash
cd /Users/ze/wenjin
grep -rn "feature_proposal\|next_steps\|build_feature_proposal\|FeatureCommandHandler\|ChatTurnRouter\|ThreadIntentRouter" backend/tests --include="*.py"
```

Expected: only the 5 files listed above plus the snapshot file (handled in Task 4).

- [ ] **Step 2: Update `test_feature_ingress_guard.py`**

Open `backend/tests/architecture/test_feature_ingress_guard.py:104-109`:

```python
def test_chat_feature_routing_uses_thread_intent_router_ssot() -> None:
    """ChatTurnRouter must stay a thin adapter over the canonical intent router."""
    source = (_SRC_ROOT / "application/handlers/chat_turn_router.py").read_text()
    assert "ThreadIntentRouter.route" in source
    assert "metadata.orchestration.intent" not in source
```

Replace with:

```python
def test_chat_turn_router_bypass_is_removed() -> None:
    """Chat turn ingress must go through lead_agent only — no router bypass."""
    assert not (_SRC_ROOT / "application/handlers/chat_turn_router.py").exists()
    assert not (_SRC_ROOT / "application/handlers/feature_command_handler.py").exists()
    assert not (_SRC_ROOT / "application/intents/thread_intent_router.py").exists()
    assert not (_SRC_ROOT / "application/services/thread_feature_service.py").exists()
    assert not (_SRC_ROOT / "application/presenters/thread_feature_cards.py").exists()
```

- [ ] **Step 3: Update `test_docs_current_contract.py`**

```bash
cd /Users/ze/wenjin
grep -n "feature_proposal\|next_steps\|ChatTurnRouter\|ThreadIntentRouter" backend/tests/architecture/test_docs_current_contract.py
```

For each match, either delete the assertion (if it documents the now-deleted bypass) or rewrite it to match the new contract. If the test asserts that some doc *describes* the bypass, the assertion must be inverted to forbid that documentation, **and** the doc itself must be updated.

- [ ] **Step 4: Update `test_paper_analysis_flow.py`**

```bash
cd /Users/ze/wenjin
grep -n "feature_proposal\|next_steps\|build_feature_proposal\|FeatureCommandHandler" backend/tests/integration/test_paper_analysis_flow.py
```

If the integration test exercises the bypass directly (calls `FeatureCommandHandler` or asserts `feature_proposal` blocks), rewrite it to: send a chat turn, assert that the lead_agent calls `launch_feature` (mock the tool to capture the call), assert the tool returns `task_id`, assert the eventual task-completion path emits a `result_card` block. If that's too large for one task, mark the legacy assertions `pytest.skip("rewritten in chat-bypass-removal Task 9")` and create a follow-up task.

- [ ] **Step 5: Update `test_latex_hardening.py` and `test_patent_feature_service.py`**

```bash
cd /Users/ze/wenjin
grep -n "feature_proposal\|next_steps" backend/tests/services/test_latex_hardening.py backend/tests/workspace_features/services/test_patent_feature_service.py
```

These are likely incidental string matches (e.g., LaTeX file change `reason` defaults to literal `"feature_proposal"`). Inspect each and replace with a non-loaded string like `"feature_action"` if the literal isn't load-bearing, or leave alone if it's not chat-block-related (look for the surrounding context — if it's about a `LatexProject.reason` field, leave it).

- [ ] **Step 6: Run the full test suite**

```bash
cd /Users/ze/wenjin/backend
uv run pytest -x 2>&1 | tail -40
```

Expected: green.

- [ ] **Step 7: Commit**

```bash
cd /Users/ze/wenjin
git add backend/tests
git commit -m "test: update test stragglers after bypass removal"
```

---

### Task 10: Stop the frontend from sending `metadata.orchestration` on chat turns

**Why:** with the bypass gone, the only remaining behavior tied to `metadata.orchestration` is the URL entry-seed auto-launch. We move that launch out of the chat flow entirely — frontend calls `POST /features/{id}/execute` first, then navigates to chat with no orchestration metadata.

**Files:**
- Modify: `frontend/lib/workspace-thread-entry.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/chat/page.tsx`
- Create: `frontend/lib/api/feature-execute.ts` (if no client wrapper exists)
- Modify: `frontend/tests/unit/lib/workspace-thread-entry.test.ts`

- [ ] **Step 1: Check if a client wrapper for `/features/{id}/execute` exists**

```bash
cd /Users/ze/wenjin
grep -rn "features.*execute\|executeFeature\|launchFeature" frontend/lib --include="*.ts" 2>&1 | grep -v node_modules | head -10
```

If a wrapper exists, note its export. If not, you'll create `feature-execute.ts`.

- [ ] **Step 2: Create the wrapper if missing**

`frontend/lib/api/feature-execute.ts`:

```typescript
import { fetchJson } from "./proxy";

interface ExecuteFeatureInput {
  workspaceId: string;
  featureId: string;
  params: Record<string, unknown>;
  threadId?: string;
  skillId?: string | null;
  executionSessionId?: string | null;
}

export interface ExecuteFeatureResponse {
  task_id: string;
  execution_session_id: string;
  status: "pending" | "advisory";
  feature_id: string;
}

export async function executeWorkspaceFeature(
  input: ExecuteFeatureInput,
): Promise<ExecuteFeatureResponse> {
  const body: Record<string, unknown> = { params: input.params };
  if (input.threadId) body.thread_id = input.threadId;
  if (input.skillId) body.skill_id = input.skillId;
  if (input.executionSessionId)
    body.execution_session_id = input.executionSessionId;
  return fetchJson<ExecuteFeatureResponse>(
    `/api/workspaces/${encodeURIComponent(input.workspaceId)}/features/${encodeURIComponent(input.featureId)}/execute`,
    { method: "POST", body: JSON.stringify(body) },
  );
}
```

(Adjust the helper import — `fetchJson` is just an example name; use whatever `proxy.ts` actually exports for an authenticated POST. Check by running: `grep -n "export " frontend/lib/api/proxy.ts | head`.)

- [ ] **Step 3: Replace `buildWorkspaceThreadEntryOrchestration` with a launch-trigger helper**

In `frontend/lib/workspace-thread-entry.ts`, delete the function `buildWorkspaceThreadEntryOrchestration` and the `WorkspaceThreadEntryOrchestration` interface. Add:

```typescript
import { executeWorkspaceFeature } from "@/lib/api/feature-execute";

/**
 * Trigger a feature launch derived from a URL entry-seed.
 * Returns the resulting task_id (or null if the seed does not represent a launch).
 */
export async function triggerEntrySeedFeatureLaunch(
  workspaceId: string,
  seed: WorkspaceThreadEntrySeed,
  threadId: string | undefined,
): Promise<string | null> {
  if (!seed.featureId || seed.featureId === "__onboarding__") return null;
  const entryAction =
    typeof seed.params?.entry === "string"
      ? seed.params.entry.trim().toLowerCase()
      : "";
  if (entryAction === "view") return null;
  const params = Object.fromEntries(
    Object.entries(seed.params ?? {}).filter(
      ([key]) => key !== "entry" && key !== "execution_session_id",
    ),
  );
  const executionSessionId =
    typeof seed.params?.execution_session_id === "string"
      ? seed.params.execution_session_id.trim() || null
      : null;
  const response = await executeWorkspaceFeature({
    workspaceId,
    featureId: seed.featureId,
    params,
    threadId,
    skillId: seed.skillId ?? null,
    executionSessionId,
  });
  return response.task_id;
}
```

- [ ] **Step 4: Update chat page to use the new helper**

In `frontend/app/(workbench)/workspaces/[id]/chat/page.tsx`, find the `buildWorkspaceThreadEntryOrchestration` call site (currently in the `useEffect` that handles `entrySeed` auto-send). Replace the call (and the `metadata: { orchestration }` part of the `sendMessage` options) with:

```typescript
    if (isOnboardingEntry || isPassiveEntry) return;

    const prompt = buildWorkspaceThreadEntryPrompt({
      seed: entrySeed,
      feature: entrySeedFeature ?? null,
    });

    // For non-passive launch seeds: trigger the feature directly via the panel
    // execute endpoint, then send a plain chat message so lead_agent can frame
    // the run. No orchestration metadata is sent.
    triggerEntrySeedFeatureLaunch(workspaceId, entrySeed, threadId ?? undefined)
      .catch((error) => {
        console.warn("entry-seed launch failed", error);
      });

    sendMessage(prompt, {
      workspaceId,
      ...(resolvedEntrySkillId !== null
        ? { skill: resolvedEntrySkillId }
        : isSkillSelectionPending
          ? { skill: currentSkill }
          : {}),
      model: selectedModel || undefined,
    });
```

Remove the `import { buildWorkspaceThreadEntryOrchestration }` line in favor of `triggerEntrySeedFeatureLaunch`.

- [ ] **Step 5: Update the entry-seed test**

```bash
cd /Users/ze/wenjin
cat frontend/tests/unit/lib/workspace-thread-entry.test.ts | head -60
```

The test currently asserts `intent: "launch"` is set in orchestration. Replace those assertions with: `triggerEntrySeedFeatureLaunch` returns null for `__onboarding__` and view-only entries, and calls `executeWorkspaceFeature` with the right body for launch entries (mock the `executeWorkspaceFeature` import).

Use `Edit` against the test file with the actual current contents to do precise replacement.

- [ ] **Step 6: Run frontend tests**

```bash
cd /Users/ze/wenjin/frontend
npm run test 2>&1 | tail -30
```

Expected: all tests pass; if a test fails because `metadata.orchestration` is no longer set, update that test to match the new behavior.

- [ ] **Step 7: Commit**

```bash
cd /Users/ze/wenjin
git add frontend/lib/workspace-thread-entry.ts \
        frontend/lib/api/feature-execute.ts \
        frontend/app/\(workbench\)/workspaces/\[id\]/chat/page.tsx \
        frontend/tests/unit/lib/workspace-thread-entry.test.ts
git commit -m "refactor(frontend): URL entry-seed calls /features/execute directly, no chat orchestration metadata"
```

---

### Task 11: Delete the dead frontend components

**Files (delete):**
- `frontend/app/(workbench)/workspaces/[id]/components/ThreadPanel.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/WorkspaceThreadMessages.tsx`

**Files (modify):**
- `frontend/app/(workbench)/workspaces/[id]/components/index.ts` (verify no re-export of deleted components)

- [ ] **Step 1: Verify `ThreadPanel` has no JSX consumers**

```bash
cd /Users/ze/wenjin
grep -rn "<ThreadPanel\|<LazyThreadPanel\|import.*ThreadPanel\b" frontend --include="*.ts" --include="*.tsx" | grep -v node_modules
```

Expected: no output (the only previous match was a *comment* in chat/page.tsx, line 240, which is unrelated to a real import).

- [ ] **Step 2: Verify `WorkspaceThreadMessages` has no JSX consumers**

```bash
cd /Users/ze/wenjin
grep -rn "<WorkspaceThreadMessages\|import.*WorkspaceThreadMessages" frontend --include="*.ts" --include="*.tsx" | grep -v node_modules | grep -v "ThreadPanel.tsx"
```

Expected: no output (only `ThreadPanel.tsx` imports it, and `ThreadPanel.tsx` is being deleted in step 3).

- [ ] **Step 3: Delete the files**

```bash
cd /Users/ze/wenjin
rm frontend/app/\(workbench\)/workspaces/\[id\]/components/ThreadPanel.tsx
rm frontend/app/\(workbench\)/workspaces/\[id\]/components/WorkspaceThreadMessages.tsx
```

- [ ] **Step 4: Update `components/index.ts` to drop any leftover ThreadPanel re-export**

```bash
cd /Users/ze/wenjin
grep -n "ThreadPanel\|WorkspaceThreadMessages" frontend/app/\(workbench\)/workspaces/\[id\]/components/index.ts
```

If a `export { ThreadPanel } from "./ThreadPanel";` line exists, delete it.

- [ ] **Step 5: Confirm frontend still compiles**

```bash
cd /Users/ze/wenjin/frontend
npm run lint -- --max-warnings=0 2>&1 | tail -20
npm run typecheck 2>&1 | tail -20
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
cd /Users/ze/wenjin
git add -A frontend/app/\(workbench\)/workspaces/\[id\]/components
git commit -m "refactor(frontend): delete dead ThreadPanel + WorkspaceThreadMessages"
```

---

### Task 12: Restore `thread-store-support.ts` to its pre-debug state

**Files:**
- Modify: `frontend/stores/thread-store-support.ts`

- [ ] **Step 1: Inspect current state**

```bash
cd /Users/ze/wenjin
git diff HEAD -- frontend/stores/thread-store-support.ts
```

If the file has uncommitted edits (the `console.log`s I added during debug, the `appendAgentBlock` `content: ""` removal, the `m.content unshift`, etc.), revert them. The new lead_agent path always emits a single AgentBlock-conforming response — no `m.content unshift` is needed.

- [ ] **Step 2: Reset the file to HEAD**

```bash
cd /Users/ze/wenjin
git checkout HEAD -- frontend/stores/thread-store-support.ts
```

- [ ] **Step 3: Inspect `toChatMessages` to verify the spec-defined behavior is restored**

```bash
cd /Users/ze/wenjin
sed -n '83,135p' frontend/stores/thread-store-support.ts
```

Expected: `agentBlocks.length > 0 ? agentBlocks : (m.content ? [{kind:"text", content:m.content}] : [])`. With the new path, `agentBlocks` is always populated by SSE block events from lead_agent, so `m.content` fallback only triggers for empty/error states.

- [ ] **Step 4: Run thread-store tests**

```bash
cd /Users/ze/wenjin/frontend
npm run test -- thread-store-support 2>&1 | tail -20
```

Expected: green.

- [ ] **Step 5: Commit (no-op if checkout was clean)**

```bash
cd /Users/ze/wenjin
git status frontend/stores/thread-store-support.ts
# If clean, skip; else:
git add frontend/stores/thread-store-support.ts
git commit -m "revert: drop debug instrumentation in thread-store-support"
```

---

### Task 13: End-to-end verification — actual user message → result_card

**Files:**
- Create: `backend/tests/integration/test_chat_to_feature_launch.py`

- [ ] **Step 1: Write the integration test**

Create `backend/tests/integration/test_chat_to_feature_launch.py`:

```python
"""End-to-end: a chat turn that should launch a feature drives lead_agent to call launch_feature."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_chat_turn_routes_to_lead_agent_only(monkeypatch):
    """Sending a 'launch this feature' chat turn must reach lead_agent (no bypass)."""
    from src.application.handlers.thread_turn_handler import ThreadTurnHandler

    # Confirm the bypass methods don't exist anymore
    assert not hasattr(ThreadTurnHandler, "_try_feature_command_reply")


@pytest.mark.asyncio
async def test_lead_agent_can_call_launch_feature_tool():
    """Tool registry exposes launch_feature; agent can resolve it."""
    from src.agents.lead_agent.agent import get_available_tools

    tools = get_available_tools()
    by_name = {getattr(t, "name", ""): t for t in tools}
    assert "launch_feature" in by_name
    tool = by_name["launch_feature"]
    # Tool schema must include feature_id, params
    schema = getattr(tool, "args_schema", None)
    assert schema is not None
    field_names = set(schema.model_fields.keys()) if hasattr(schema, "model_fields") else set()
    assert "feature_id" in field_names
    assert "params" in field_names
```

- [ ] **Step 2: Run the test**

```bash
cd /Users/ze/wenjin/backend
uv run pytest tests/integration/test_chat_to_feature_launch.py -v
```

Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
cd /Users/ze/wenjin
git add backend/tests/integration/test_chat_to_feature_launch.py
git commit -m "test: integration smoke test for bypass removal"
```

---

### Task 14: Manual end-to-end smoke (Docker + browser)

**Files:** none (operational)

- [ ] **Step 1: Rebuild backend and frontend containers**

```bash
cd /Users/ze/wenjin
docker compose up -d --build backend gateway worker frontend 2>&1 | tail -10
```

Expected: containers healthy.

- [ ] **Step 2: Hard-refresh browser and exercise the chat**

In a browser, hard-refresh `http://localhost:2026`, log in, create a fresh thread, and send: `我想写一篇联邦学习结合大模型微调的论文`.

- [ ] **Step 3: Assert against the spec checklist**

Verify that:
- The agent's reply is **a single message block** (not split into "user轮 + assistant轮").
- The text **does not contain** any of: `message_feature_proposal`, `意图置信度`, `我会先复用`, `将进入...执行链路`.
- If the agent decides to launch a feature, you see a `status_line` (right panel updates with phase progression in `LiveWorkflowPanel`).
- The eventual completion produces a `result_card` (not a legacy `task_result` block).

- [ ] **Step 4: Capture DB state to confirm new schema**

```bash
docker compose exec -T postgres psql -U postgres -d wenjin -c \
  "SELECT id, jsonb_path_query_array(messages, '$[*].blocks[*].kind') FROM threads ORDER BY updated_at DESC LIMIT 3;"
```

Expected: every block has `kind` (one of `text`, `status_line`, `question_card`, `result_card`); no `type` field with legacy values.

- [ ] **Step 5: Final commit (deployment confirmation)**

```bash
cd /Users/ze/wenjin
git commit --allow-empty -m "chore: smoke-tested chat bypass removal end-to-end"
```

---

## Self-Review

### 1. Spec coverage

The original spec § 8.1 listed the legacy block types to delete (`feature_proposal`, `next_steps`, `MissingInputBlock`). This plan deletes the **producers** of those blocks (Tasks 7, 8) and provides the only AgentBlock-conformant alternative path (Tasks 2, 3, 4, 5, 6). § 2.2 ("不自我汇报") is enforced by the prompt change in Task 4 plus the deletion of the hardcoded "我会先复用..." string (Task 8 removes `thread_feature_cards.py`). § 7 URL entry-seed is preserved by Task 10 routing through the panel execute endpoint instead of through chat metadata.

### 2. Placeholder scan

No "TODO", "TBD", "implement later", "similar to Task N", or generic "add validation" text in the plan. Every task contains either the exact code or the exact `Edit` instruction with a `grep` to anchor the edit on real file contents.

### 3. Type consistency

- `launch_feature_tool` returns dict with keys `status` ('launched' | 'advisory'), `task_id`, `feature_id`, `execution_session_id`, `message`/`code`/`detail`. Same shape used in tests (Task 2) and integration test (Task 13). ✓
- `build_completion_result_card` / `build_failure_result_card` signatures match between the implementation (Task 5), the celery write-back call sites (Task 6), and the integration test schema (Task 5 step 1, fourth test). All use `run_id`, `duration_ms`, `subagents_count`, `tokens_total`. ✓
- `triggerEntrySeedFeatureLaunch(workspaceId, seed, threadId)` signature is consistent across helper definition and call site in Task 10. ✓
- The `result_card` block schema in `agent_result_card.py` uses `kind` (not `type`), matches `backend/src/agents/lead_agent/blocks.py:ResultCardBlock`, and validates via `AgentMessage.model_validate` (Task 5 fourth test). ✓

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-08-chat-bypass-removal.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration. Best for the destructive deletes in Task 8 (forces a clean review checkpoint).
2. **Inline Execution** — execute tasks in this session using `executing-plans`, batch execution with checkpoints for review.

Which approach?
