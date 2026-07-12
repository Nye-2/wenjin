# Agent Runtime Harness Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Implementation status:** This is the execution plan used for the 2026-06-24 runtime/harness optimization branch. The checkboxes preserve the original worker instructions; completion is tracked by the branch commits and verification results.

**Goal:** Repair and tighten Wenjin's academic harness, agent loop/runtime, chat launch ingress, execution projection, and result commit lifecycle so scholarly evidence, sandbox activity, and user-visible run state stay consistent and bounded.

**Architecture:** Keep the current two-agent topology: Chat Agent routes intent and calls `launch_feature`; Lead Agent / TeamKernel owns execution; harness tools produce bounded structured evidence; frontend displays only sanitized execution projections. The work focuses on closing gaps where side effects, evidence metadata, runtime state, and UI projection currently diverge.

**Tech Stack:** Python 3.13, FastAPI/DataService, SQLAlchemy async, Pydantic v2, LangGraph/LangChain, Celery, Next.js 16, React 19, TypeScript, Zustand, Vitest, Pytest.

---

## Scope And Guardrails

This plan is intentionally broad but split into independently testable tasks. Complete Task 1 through Task 5 first; those are the P0 safety and correctness fixes. Tasks 6 through 13 are runtime and UX hardening work that can follow after P0 is green.

Respect these non-negotiable project constraints:

- Chat Agent must not acquire sandbox state or call harness tools directly.
- `ExecutionRecord` and `ExecutionNodeRecord` remain execution facts; `runtime_state` is a bounded summary.
- Harness internal refs such as `/workspace/tmp/tasks/.harness/**` must not appear in default user UX.
- Capability/catalog seeds remain the runtime source of truth; avoid adding parallel routing or compatibility layers.
- Result commit must eventually become a backend fact, not three frontend-local booleans.

## File Structure Map

Backend launch and chat ingress:

- Modify `backend/src/application/handlers/thread_turn_handler.py`
  - Pass `PreparedThreadTurn.user_message_id` into `RunnableConfig`.
  - Normalize emitted tool blocks to canonical shape in a later task.
- Modify `backend/src/tools/builtins/launch_feature.py`
  - Add user-turn idempotency for feature launch.
  - Return the same execution/result for repeated launch calls from the same user turn.
- Modify `backend/src/agents/middlewares/capability_auto_launch.py`
  - Restrict auto-launch to explicit metadata/deep-link launch only.
  - Filter hidden/internal capability entries.
- Test `backend/tests/application/handlers/test_thread_turn_runtime_config.py`
- Test `backend/tests/tools/test_launch_feature_tool.py`
- Test `backend/tests/agents/chat_agent/test_capability_auto_launch.py`

Backend Lead/TeamKernel:

- Modify `backend/src/agents/lead_agent/v2/runtime.py`
  - Pass workspace context policy helpers to TeamKernel.
- Modify `backend/src/agents/lead_agent/v2/team/kernel.py`
  - Load TeamKernel workspace context with capability policy, explicit context requirements, and user id.
  - Make node recording and event publication best-effort.
  - Prefer latest successful invocation output when mapping graph outputs.
- Test `backend/tests/agents/lead_agent/v2/test_team_kernel.py`
- Test `backend/tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py`

Backend harness:

- Modify `backend/src/subagents/v2/types/sandbox.py`
  - Bridge old `sandbox_python` subagent output into new harness metadata contract.
- Modify `backend/src/agents/harness/langchain_adapter.py`
  - Classify policy/tool failures into structured `error_code`.
  - Record failed forbidden/unknown tool attempts when possible.
- Modify `backend/src/agents/harness/loop_guard.py`
  - Separate total tool-call budget from repeated-identical-call budget.
- Modify `backend/src/agents/harness/policy.py`
  - Add explicit `max_total_tool_calls` and `max_repeated_identical_tool_calls`.
- Modify `backend/src/agents/harness/sandbox_tools.py`
  - Bound glob/grep enumeration and regex scanning.
- Modify `backend/src/agents/harness/sandbox_execution_tools.py`
  - Split queue timeout from actual execution timeout in manifests.
- Modify `backend/src/agents/harness/diff_tracker.py`
  - Add generic `output_ref_summary`.
- Modify `backend/src/agents/harness/context_assembly.py`
  - Expose generic output-ref recovery from `output_ref_summary`.
- Test `backend/tests/agents/harness/test_langchain_adapter.py`
- Test `backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py`
- Test `backend/tests/agents/harness/test_sandbox_file_tools.py`
- Test `backend/tests/agents/harness/test_scheduler_and_python_tool.py`

Frontend projection and review:

- Modify `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/NodeInspector.tsx`
  - Remove raw `input/output` JSON from default UX.
- Modify `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/utils.ts`
  - Replace `formatJsonPreview(output)` fallback with sanitized summary.
- Modify `frontend/app/(workbench)/workspaces/[id]/components/CompletedView.tsx`
  - Replace raw result JSON fallback with product-language empty state.
- Modify `frontend/lib/execution-run-view.ts`
  - Move more evidence/result projection into one sanitized projection layer.
- Test `frontend/tests/execution-run-view.test.ts` or create `frontend/tests/live-workflow-sanitization.test.tsx`.

Backend/frontend commit state:

- Modify `backend/src/services/execution_commit_service.py`
  - Make commit idempotent by execution/output/actor, not just request key.
  - Return commit state that can be projected by runs/result cards.
- Modify execution projection contracts and serializers where current execution payloads are built.
- Modify `frontend/lib/execution-run-view.ts`, `ResultCard.tsx`, `CompletedView.tsx`, and `LiveWorkflowPanel.tsx`
  - Consume backend `commit_state`.
- Test `backend/tests/services/test_execution_commit_service.py`
- Test relevant frontend component tests.

Docs and release gates:

- Modify `docs/current/architecture.md`
- Modify `docs/current/workspace-current-state.md`
- Modify `docs/current/frontend-mission-contract.md`
- Modify `docs/current/release-gate-checklist.md`

---

## Task 1: Pass User Turn Idempotency Into Chat Runtime

**Files:**
- Modify: `backend/src/application/handlers/thread_turn_handler.py`
- Test: `backend/tests/application/handlers/test_thread_turn_runtime_config.py`

- [ ] **Step 1: Write the failing runtime-config test**

Add this test to `backend/tests/application/handlers/test_thread_turn_runtime_config.py`:

```python
from types import SimpleNamespace

from src.application.handlers.thread_turn_handler import build_thread_runtime_config
from src.application.results import ThreadTurnRequest


def test_thread_runtime_config_includes_user_message_id_for_launch_idempotency() -> None:
    request = ThreadTurnRequest(message="启动 SCI 文献定位", workspace_id="ws-1")
    thread = SimpleNamespace(id="thread-1", workspace_id="ws-1", skill=None, model=None)

    config = build_thread_runtime_config(
        request=request,
        thread=thread,
        actor_id="user-1",
        workspace_id="ws-1",
        effective_skill=None,
        effective_model="mimo-v2.5-pro",
        execution_id=None,
        user_message_id="msg-123",
    )

    assert config["configurable"]["user_message_id"] == "msg-123"
    assert config["configurable"]["launch_idempotency_key"] == "launch_feature:thread-1:msg-123"
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/application/handlers/test_thread_turn_runtime_config.py::test_thread_runtime_config_includes_user_message_id_for_launch_idempotency -q
```

Expected: fail with `TypeError: build_thread_runtime_config() got an unexpected keyword argument 'user_message_id'`.

- [ ] **Step 3: Implement runtime config propagation**

In `backend/src/application/handlers/thread_turn_handler.py`, change the function signature and configurable assembly:

```python
def build_thread_runtime_config(
    *,
    request: ThreadTurnRequest,
    thread: Thread,
    actor_id: str,
    workspace_id: str | None,
    effective_skill: str | None,
    effective_model: str,
    execution_id: str | None = None,
    user_message_id: str | None = None,
) -> RunnableConfig:
    configurable: dict[str, Any] = {
        "thread_id": thread.id,
        "workspace_id": workspace_id,
        "user_id": actor_id,
        "model_name": effective_model,
        "supports_vision": model_supports_vision(effective_model),
        "selected_skill": effective_skill,
        "thinking_enabled": request.thinking_enabled,
        "reasoning_effort": request.reasoning_effort,
    }
    if user_message_id:
        configurable["user_message_id"] = user_message_id
        configurable["launch_idempotency_key"] = f"launch_feature:{thread.id}:{user_message_id}"
```

Then update `_build_thread_agent_runtime` to accept `user_message_id` and pass it through:

```python
def _build_thread_agent_runtime(
    request: ThreadTurnRequest,
    thread: Thread,
    *,
    actor_id: str,
    execution_id: str | None = None,
    user_message_id: str | None = None,
    workspace_service: WorkspaceService | None = None,
    index_service: Any | None = None,
    artifact_service: ArtifactService | None = None,
    reference_service: Any | None = None,
    conversation_messages: list[dict[str, Any]] | None = None,
) -> _ThreadAgentRuntime:
    ...
    config = build_thread_runtime_config(
        request=request,
        thread=thread,
        actor_id=actor_id,
        workspace_id=workspace_id,
        effective_skill=effective_skill,
        effective_model=effective_model,
        execution_id=execution_id,
        user_message_id=user_message_id,
    )
```

Update `_generate_prepared_reply` to pass `prepared.user_message_id` into `_generate_thread_response`, and update `_generate_thread_response` / `generate_thread_response` callers so the parameter reaches `_build_thread_agent_runtime`:

```python
return await self._generate_thread_response(
    prepared.request,
    prepared.thread,
    actor_id=actor_id,
    execution_id=prepared.request.metadata.get("orchestration", {}).get("execution_id")
    if isinstance(prepared.request.metadata, dict)
    else None,
    user_message_id=prepared.user_message_id,
)
```

- [ ] **Step 4: Run runtime-config tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/application/handlers/test_thread_turn_runtime_config.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/application/handlers/thread_turn_handler.py backend/tests/application/handlers/test_thread_turn_runtime_config.py
git commit -m "fix: pass launch idempotency through chat runtime"
```

---

## Task 2: Make `launch_feature` Idempotent Per User Turn

**Files:**
- Modify: `backend/src/tools/builtins/launch_feature.py`
- Test: `backend/tests/tools/test_launch_feature_tool.py`

- [ ] **Step 1: Write the failing launch idempotency test**

Add this test to `backend/tests/tools/test_launch_feature_tool.py`. Reuse the existing fake DataService and Celery monkeypatch helpers in that file; adapt names to the local fixtures already present:

```python
@pytest.mark.asyncio
async def test_launch_feature_reuses_execution_for_same_user_message(monkeypatch):
    dispatched: list[str] = []

    class FakeCelery:
        def send_task(self, name: str, args: list[str], task_id: str | None = None):
            dispatched.append(args[0])
            return SimpleNamespace(id=task_id or "task-1")

    fake_client = LaunchFeatureFakeDataService()
    monkeypatch.setattr("src.dataservice_client.provider.dataservice_client", lambda: fake_client)
    monkeypatch.setattr("src.task.celery_app.celery_app", FakeCelery())

    config = {
        "configurable": {
            "workspace_id": "ws-1",
            "thread_id": "thread-1",
            "user_id": "user-1",
            "user_message_id": "msg-1",
            "launch_idempotency_key": "launch_feature:thread-1:msg-1",
        }
    }

    first = await launch_feature_tool.ainvoke(
        {"feature_id": "sci_literature_positioning", "params": {"topic": "LLM agents"}},
        config=config,
    )
    second = await launch_feature_tool.ainvoke(
        {"feature_id": "sci_literature_positioning", "params": {"topic": "LLM agents"}},
        config=config,
    )

    assert first["status"] == "launched"
    assert second["status"] == "launched"
    assert second["execution_id"] == first["execution_id"]
    assert dispatched == [first["execution_id"]]
```

If the existing fake class has a different name, keep the assertions and wire the fake using the helper patterns already in the file.

- [ ] **Step 2: Run the failing test**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/tools/test_launch_feature_tool.py::test_launch_feature_reuses_execution_for_same_user_message -q
```

Expected: fail because the second launch returns `lead_busy` or dispatches again.

- [ ] **Step 3: Add idempotency helpers**

In `backend/src/tools/builtins/launch_feature.py`, add:

```python
def _launch_idempotency_key(config: RunnableConfig | None) -> str | None:
    key = _read_optional(config, "launch_idempotency_key")
    if key:
        return key
    thread_id = _read_optional(config, "thread_id")
    user_message_id = _read_optional(config, "user_message_id")
    if thread_id and user_message_id:
        return f"launch_feature:{thread_id}:{user_message_id}"
    return None


def _execution_launch_idempotency_key(execution: Any) -> str:
    params = getattr(execution, "params", None)
    if not isinstance(params, dict):
        params = getattr(execution, "task_brief_json", None)
    if not isinstance(params, dict):
        return ""
    billing = params.get("billing")
    orchestration = params.get("orchestration")
    candidates = [
        params.get("launch_idempotency_key"),
        orchestration.get("launch_idempotency_key") if isinstance(orchestration, dict) else None,
        billing.get("launch_idempotency_key") if isinstance(billing, dict) else None,
    ]
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text:
            return text
    return ""
```

- [ ] **Step 4: Reuse existing execution before lead-busy**

After resolving capability and before the lead-busy check, add:

```python
launch_idempotency_key = _launch_idempotency_key(config)
if launch_idempotency_key:
    existing_for_turn = await execution_service.list_executions(
        workspace_id=workspace_id,
        limit=20,
    )
    for existing in existing_for_turn:
        if (
            str(getattr(existing, "thread_id", "") or "") == thread_id
            and str(getattr(existing, "user_id", "") or "") == user_id
            and str(getattr(existing, "feature_id", "") or "") == feature_id
            and _execution_launch_idempotency_key(existing) == launch_idempotency_key
        ):
            return {
                "status": "launched",
                "execution_id": str(existing.id),
                "feature_id": feature_id,
                "capability_name": getattr(cap, "display_name", None),
                "detail": "该能力已在当前消息中启动，继续使用同一个执行。",
            }
```

When building `execution_params`, persist the key:

```python
if launch_idempotency_key:
    execution_params["launch_idempotency_key"] = launch_idempotency_key
    execution_params.setdefault("orchestration", {})["launch_idempotency_key"] = launch_idempotency_key
```

- [ ] **Step 5: Run launch tool tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/tools/test_launch_feature_tool.py -q
```

Expected: all launch feature tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/src/tools/builtins/launch_feature.py backend/tests/tools/test_launch_feature_tool.py
git commit -m "fix: make feature launch idempotent per chat turn"
```

---

## Task 3: Restrict Auto-Launch To Explicit Entry Metadata

**Files:**
- Modify: `backend/src/agents/middlewares/capability_auto_launch.py`
- Test: `backend/tests/agents/chat_agent/test_capability_auto_launch.py`
- Test: `backend/tests/agents/chat_agent/test_capability_route_cards.py`

- [ ] **Step 1: Write failing tests for hidden and text-trigger auto-launch**

In `backend/tests/agents/chat_agent/test_capability_auto_launch.py`, replace the expectation that hidden trigger phrases launch with these tests:

```python
@pytest.mark.asyncio
async def test_capability_auto_launch_does_not_launch_hidden_trigger_phrase(monkeypatch):
    launch = AsyncMock()
    monkeypatch.setattr(
        "src.agents.middlewares.capability_auto_launch._invoke_launch_feature",
        launch,
    )

    state = create_thread_state(
        {
            "messages": [HumanMessage(content="sandbox 自检")],
            "available_capabilities": [
                {
                    "id": "internal_sandbox_smoke",
                    "display_name": "内部实验环境自检",
                    "trigger_phrases": ["sandbox 自检"],
                    "entry_tier": "hidden",
                }
            ],
        }
    )

    updates = await CapabilityAutoLaunchMiddleware().before_model(
        state,
        {"configurable": {"workspace_id": "ws-1", "thread_id": "thread-1", "user_id": "user-1"}},
    )

    assert updates == {}
    launch.assert_not_awaited()


@pytest.mark.asyncio
async def test_capability_auto_launch_requires_explicit_runtime_feature_id(monkeypatch):
    launch = AsyncMock()
    monkeypatch.setattr(
        "src.agents.middlewares.capability_auto_launch._invoke_launch_feature",
        launch,
    )

    state = create_thread_state(
        {
            "messages": [HumanMessage(content="run reproducibility_audit")],
            "available_capabilities": [{"id": "reproducibility_audit", "display_name": "可复现性检查"}],
        }
    )

    updates = await CapabilityAutoLaunchMiddleware().before_model(
        state,
        {"configurable": {"workspace_id": "ws-1", "thread_id": "thread-1", "user_id": "user-1"}},
    )

    assert updates == {}
    launch.assert_not_awaited()
```

Add a positive explicit metadata test:

```python
@pytest.mark.asyncio
async def test_capability_auto_launch_allows_explicit_runtime_feature_id(monkeypatch):
    launch = AsyncMock(
        return_value={"status": "launched", "execution_id": "exec-1", "feature_id": "reproducibility_audit"}
    )
    monkeypatch.setattr(
        "src.agents.middlewares.capability_auto_launch._invoke_launch_feature",
        launch,
    )
    state = create_thread_state(
        {
            "messages": [HumanMessage(content="请开始这个入口任务")],
            "available_capabilities": [{"id": "reproducibility_audit", "display_name": "可复现性检查"}],
        }
    )

    updates = await CapabilityAutoLaunchMiddleware().before_model(
        state,
        {
            "configurable": {
                "workspace_id": "ws-1",
                "thread_id": "thread-1",
                "user_id": "user-1",
                "launch_feature_id": "reproducibility_audit",
            }
        },
    )

    assert updates["_skip_model_call"] is True
    assert updates["response_metadata"]["orchestration"]["execution_id"] == "exec-1"
    launch.assert_awaited_once()
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/chat_agent/test_capability_auto_launch.py -q
```

Expected: the new tests fail until the middleware is restricted.

- [ ] **Step 3: Implement explicit-only auto-launch**

In `backend/src/agents/middlewares/capability_auto_launch.py`, add helpers:

```python
def _configurable(config: RunnableConfig | None) -> dict[str, Any]:
    raw = (config or {}).get("configurable") if isinstance(config, dict) else None
    return raw if isinstance(raw, dict) else {}


def _is_hidden_capability(capability: Mapping[str, Any]) -> bool:
    display = capability.get("display")
    display = display if isinstance(display, Mapping) else {}
    tier = str(
        capability.get("entry_tier")
        or capability.get("tier")
        or display.get("entry_tier")
        or display.get("tier")
        or ""
    ).strip().lower()
    return tier == "hidden"
```

At the start of `before_model`, require `launch_feature_id`:

```python
configurable = _configurable(config)
explicit_feature_id = str(configurable.get("launch_feature_id") or "").strip()
if not explicit_feature_id:
    return {}
```

When selecting a capability, require exact id and not hidden:

```python
capability = next(
    (
        item
        for item in available_capabilities
        if isinstance(item, Mapping)
        and str(item.get("id") or "").strip() == explicit_feature_id
        and not _is_hidden_capability(item)
    ),
    None,
)
if capability is None:
    return {}
```

Remove trigger-phrase and free-text id matching from auto-launch. Route-card model launch remains available for ordinary text.

- [ ] **Step 4: Run chat agent capability tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/chat_agent/test_capability_auto_launch.py tests/agents/chat_agent/test_capability_route_cards.py -q
```

Expected: all tests pass after updating any old tests that asserted trigger-phrase auto-launch.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/middlewares/capability_auto_launch.py backend/tests/agents/chat_agent/test_capability_auto_launch.py
git commit -m "fix: restrict capability auto launch to explicit entries"
```

---

## Task 4: Load Full Workspace Context In TeamKernel

**Files:**
- Modify: `backend/src/agents/lead_agent/v2/runtime.py`
- Modify: `backend/src/agents/lead_agent/v2/team/kernel.py`
- Test: `backend/tests/agents/lead_agent/v2/test_team_kernel.py`

- [ ] **Step 1: Write the failing TeamKernel context test**

Add this test to `backend/tests/agents/lead_agent/v2/test_team_kernel.py`:

```python
@pytest.mark.asyncio
async def test_team_kernel_passes_capability_policy_and_user_to_workspace_loader(monkeypatch):
    captured: dict[str, Any] = {}

    async def load_workspace_data(workspace_id: str, **kwargs: Any) -> dict[str, Any]:
        captured["workspace_id"] = workspace_id
        captured.update(kwargs)
        return {"library_context": {"allowed_citation_keys": ["smith2024"]}}

    runtime = TeamKernelRuntime(
        publish_event=AsyncMock(),
        record_node_event=AsyncMock(),
        abort_check=AsyncMock(return_value=False),
        load_workspace_data=load_workspace_data,
        needs_workspace_context=lambda policy, requirements: True,
        context_requirements_from_brief=lambda brief: {"include_related_documents": True},
        capability_policy_builder=lambda capability: {
            "citation_policy": {"source_scope": "workspace_library"},
            "context_policy": {"room_reads": {"library": True}},
        },
        collect_policy_memory_outputs=lambda capability, brief, outputs: [],
    )

    monkeypatch.setattr(runtime, "_load_templates", AsyncMock(return_value={}))
    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.build_capability_team_policy",
        lambda capability, templates: _minimal_team_policy_without_invocations(),
    )

    report = await runtime.run(
        execution_id="exec-1",
        brief=TaskBrief(
            capability_id="sci_literature_positioning",
            raw_message="position this topic",
            workspace_id="ws-1",
            user_id="user-1",
            brief={"topic": "LLM agents"},
        ),
        capability=SimpleNamespace(id="sci_literature_positioning", display_name="SCI 文献定位"),
        started_at=datetime.now(UTC),
    )

    assert report.status in {"completed", "failed_partial"}
    assert captured["workspace_id"] == "ws-1"
    assert captured["user_id"] == "user-1"
    assert captured["capability_policy"]["citation_policy"]["source_scope"] == "workspace_library"
    assert captured["context_requirements"]["include_related_documents"] is True
```

Add the helper in the same test module:

```python
def _minimal_team_policy_without_invocations():
    return CapabilityTeamPolicy(
        core_templates=[],
        optional_templates=[],
        capability_tools=[],
        capability_skills=[],
        quality_pipeline=[],
        limits=TeamPolicyLimits(max_iterations=1, max_parallel_invocations=1, max_invocations_total=1),
    )
```

Use the actual `CapabilityTeamPolicy` and `TeamPolicyLimits` imports already available in the test module, or import them from `src.agents.lead_agent.v2.team.policy`.

- [ ] **Step 2: Run the failing test**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_kernel.py::test_team_kernel_passes_capability_policy_and_user_to_workspace_loader -q
```

Expected: fail because `TeamKernelRuntime.__init__` does not accept `needs_workspace_context` and `context_requirements_from_brief`.

- [ ] **Step 3: Update TeamKernel constructor and run context load**

In `backend/src/agents/lead_agent/v2/team/kernel.py`, change constructor fields:

```python
def __init__(
    self,
    *,
    publish_event: Callable[[str, str, dict[str, Any]], Awaitable[None]],
    record_node_event: Callable[..., Awaitable[None]],
    abort_check: Callable[[str], Awaitable[bool]],
    load_workspace_data: Callable[..., Awaitable[dict[str, Any]]],
    needs_workspace_context: Callable[[dict[str, Any], dict[str, bool]], bool],
    context_requirements_from_brief: Callable[[TaskBrief], dict[str, bool]],
    capability_policy_builder: Callable[[Any], dict[str, Any]],
    collect_policy_memory_outputs: Callable[[Any, TaskBrief, list[ResultOutput]], list[ResultOutput]],
) -> None:
    ...
    self.load_workspace_data = load_workspace_data
    self.needs_workspace_context = needs_workspace_context
    self.context_requirements_from_brief = context_requirements_from_brief
```

In `run`, replace the current workspace load:

```python
context_requirements = self.context_requirements_from_brief(brief)
workspace_data = (
    await self.load_workspace_data(
        brief.workspace_id,
        capability_policy=capability_policy,
        context_requirements=context_requirements,
        user_id=brief.user_id,
    )
    if self.needs_workspace_context(capability_policy, context_requirements)
    else {}
)
```

In `backend/src/agents/lead_agent/v2/runtime.py`, update `TeamKernelRuntime(...)`:

```python
report = await TeamKernelRuntime(
    publish_event=self.publish_event,
    record_node_event=self.record_node_event,
    abort_check=self._check_abort,
    load_workspace_data=self.context_assembler.load_workspace_data,
    needs_workspace_context=self.context_assembler.needs_workspace_context,
    context_requirements_from_brief=self.context_assembler.context_requirements_from_brief,
    capability_policy_builder=self._capability_policy,
    collect_policy_memory_outputs=self._collect_policy_memory_outputs,
).run(...)
```

- [ ] **Step 4: Run TeamKernel tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_kernel.py tests/agents/lead_agent/v2/test_team_member_context.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/lead_agent/v2/runtime.py backend/src/agents/lead_agent/v2/team/kernel.py backend/tests/agents/lead_agent/v2/test_team_kernel.py
git commit -m "fix: pass workspace context policy into team kernel"
```

---

## Task 5: Bridge `sandbox_python` Into Harness Evidence Metadata

**Files:**
- Modify: `backend/src/subagents/v2/types/sandbox.py`
- Test: `backend/tests/subagents/v2/test_sandbox.py` or create `backend/tests/subagents/v2/test_sandbox_python_metadata.py`
- Test: `backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py`

- [ ] **Step 1: Write a failing metadata bridge test**

Create `backend/tests/subagents/v2/test_sandbox_python_metadata.py`:

```python
from __future__ import annotations

from src.subagents.v2.types.sandbox import _sandbox_python_tool_call


def test_sandbox_python_tool_call_carries_harness_metadata() -> None:
    output = {
        "status": "completed",
        "exit_code": 0,
        "docker_image": "python:3.13-slim",
        "script_hash": "sha256:abc",
        "output_refs": ["/workspace/tmp/tasks/.harness/outputs/exec/node/inv/sandbox.run_python-abc.txt"],
        "generated_artifacts": [{"path": "/workspace/outputs/result.json"}],
        "execution_manifest": {"schema": "wenjin.harness.run_python.execution_manifest.v1"},
        "reproducibility_manifest": {"schema": "wenjin.harness.run_python.reproducibility_manifest.v1"},
        "experiment_narrative": {"schema": "wenjin.harness.run_python.experiment_narrative.v1"},
    }
    billing = {"type": "sandbox_operation_billing", "credits_charged": 1}

    call = _sandbox_python_tool_call(operation="python_script", output=output, billing=billing)

    assert call["name"] == "sandbox.run_python"
    assert call["status"] == "completed"
    assert call["output_refs"] == output["output_refs"]
    assert call["metadata"]["execution_manifest"]["schema"] == "wenjin.harness.run_python.execution_manifest.v1"
    assert call["metadata"]["reproducibility_manifest"]["schema"] == "wenjin.harness.run_python.reproducibility_manifest.v1"
    assert call["metadata"]["generated_artifacts"] == output["generated_artifacts"]
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/subagents/v2/test_sandbox_python_metadata.py -q
```

Expected: fail because `_sandbox_python_tool_call` does not exist.

- [ ] **Step 3: Implement the bridge helper**

In `backend/src/subagents/v2/types/sandbox.py`, add:

```python
def _sandbox_python_tool_call(
    *,
    operation: str,
    output: dict,
    billing: dict,
) -> dict:
    metadata: dict[str, object] = {}
    for key in (
        "execution_manifest",
        "reproducibility_manifest",
        "experiment_narrative",
        "failure_classification",
        "execution_lifecycle",
        "command_audit",
        "install_command_audits",
        "generated_artifacts",
    ):
        value = output.get(key)
        if value:
            metadata[key] = value
    if output.get("error_code"):
        metadata["error_code"] = output["error_code"]
    if output.get("failure_classification"):
        metadata["recoverable_error"] = str(output.get("failure_classification"))

    call = {
        "name": "sandbox.run_python",
        "args": {
            "operation": operation,
            "script_hash": output.get("script_hash"),
        },
        "status": output.get("status") or "completed",
        "exit_code": output.get("exit_code"),
        "docker_image": output.get("docker_image"),
        "billing": billing,
        "metadata": metadata,
    }
    output_refs = [str(ref) for ref in output.get("output_refs") or [] if str(ref).strip()]
    if output_refs:
        call["output_refs"] = output_refs
        metadata["output_refs"] = output_refs
    return call
```

Replace the inline `tool_calls=[{...}]` in `SandboxPythonSubagent.run` with:

```python
tool_calls=[_sandbox_python_tool_call(operation=operation, output=output, billing=billing_metadata)]
```

- [ ] **Step 4: Run sandbox metadata tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/subagents/v2/test_sandbox_python_metadata.py tests/agents/lead_agent/v2/test_sandbox_runtime.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/subagents/v2/types/sandbox.py backend/tests/subagents/v2/test_sandbox_python_metadata.py
git commit -m "fix: bridge sandbox python evidence into harness metadata"
```

---

## Task 6: Remove Raw Runtime Payloads From Default Frontend UX

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/NodeInspector.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/utils.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/CompletedView.tsx`
- Test: create `frontend/tests/live-workflow-sanitization.test.tsx`

- [ ] **Step 1: Write sanitization tests**

Create `frontend/tests/live-workflow-sanitization.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { buildEvidenceItems, buildSandboxSummary } from "@/app/(workbench)/workspaces/[id]/components/live-workflow/utils";

describe("live workflow sanitization", () => {
  it("does not expose raw stdout stderr or internal harness refs in sandbox summary", () => {
    const summary = buildSandboxSummary({
      status: "completed",
      output: {
        operation: "run_python",
        status: "completed",
        stdout: "secret stdout",
        stderr: "secret stderr",
        output_refs: ["/workspace/tmp/tasks/.harness/outputs/exec/node/inv/ref.txt"],
      },
      node_metadata: {},
    } as any);

    const text = summary?.join("\n") ?? "";
    expect(text).toContain("1 个可恢复引用");
    expect(text).not.toContain("secret stdout");
    expect(text).not.toContain("secret stderr");
    expect(text).not.toContain("/workspace/tmp/tasks/.harness");
  });

  it("uses product summaries instead of raw output fallback evidence", () => {
    const items = buildEvidenceItems({
      id: "exec-1",
      status: "completed",
      node_states: {
        node1: {
          status: "completed",
          node_type: "agent_invocation",
          label: "专家",
          output: { stdout: "raw output", nested: { token: "hidden" } },
          node_metadata: {},
        },
      },
      runtime_state: {},
    } as any);

    const text = items.map((item) => item.summary).join("\n");
    expect(text).not.toContain("raw output");
    expect(text).not.toContain("hidden");
  });
});
```

- [ ] **Step 2: Run the failing frontend test**

Run:

```bash
cd frontend && npx vitest run tests/live-workflow-sanitization.test.tsx
```

Expected: fail if `buildEvidenceItems` still falls back to raw JSON.

- [ ] **Step 3: Replace raw JSON fallback in `utils.ts`**

In `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/utils.ts`, replace the fallback that calls `formatJsonPreview(output)` with:

```ts
function buildSafeNodeOutputSummary(state: ExecutionNodeState): string | null {
  const harnessEvidence = buildHarnessEvidenceSummary(state);
  if (harnessEvidence?.length) {
    return harnessEvidence.join(" · ");
  }
  const sandbox = buildSandboxSummary(state);
  if (sandbox?.length) {
    return sandbox.join(" · ");
  }
  if (state.status === "completed") {
    return "该步骤已完成，详细结果已进入候选结果或审阅区。";
  }
  if (state.status === "failed") {
    return "该步骤未完成，错误摘要请查看运行状态。";
  }
  return null;
}
```

Use `buildSafeNodeOutputSummary(state)` where evidence summaries are built.

- [ ] **Step 4: Remove raw input/output panes from `NodeInspector`**

In `NodeInspector.tsx`, replace raw technical sections with sanitized status and harness summaries:

```tsx
const safeSummary = buildSandboxSummary(state)?.join(" · ") ?? state.output_preview ?? null;

<section>
  <h4>步骤摘要</h4>
  <p>{safeSummary ?? "该步骤暂无可展示摘要。"}</p>
</section>
```

Keep node id/status/label visible. Do not render `formatJsonPreview(state.input)` or `formatJsonPreview(state.output)` in default UX.

- [ ] **Step 5: Replace `CompletedView` raw result fallback**

In `CompletedView.tsx`, replace `JSON.stringify(result)` fallback with:

```tsx
const fallbackSummary = "本次运行已完成，结果已整理到候选结果、审阅项或运行记录中。";
```

Render that sentence when no preview is available.

- [ ] **Step 6: Run frontend checks**

Run:

```bash
cd frontend && npx vitest run tests/live-workflow-sanitization.test.tsx
cd frontend && npm run typecheck
```

Expected: Vitest and typecheck pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/app/(workbench)/workspaces/[id]/components/live-workflow/NodeInspector.tsx frontend/app/(workbench)/workspaces/[id]/components/live-workflow/utils.ts frontend/app/(workbench)/workspaces/[id]/components/CompletedView.tsx frontend/tests/live-workflow-sanitization.test.tsx
git commit -m "fix: remove raw runtime payloads from workflow ui"
```

---

## Task 7: Make TeamKernel Recording Best-Effort And Prefer Latest Output

**Files:**
- Modify: `backend/src/agents/lead_agent/v2/team/kernel.py`
- Test: `backend/tests/agents/lead_agent/v2/test_team_kernel.py`

- [ ] **Step 1: Write failing tests**

Add a test for latest output mapping:

```python
def test_team_kernel_output_mapping_prefers_latest_successful_invocation() -> None:
    runtime = _team_runtime_for_unit_tests()
    invocations = [
        AgentInvocation(
            id="inv-1",
            template_id="writer.v1",
            skill_id="writer",
            iteration=1,
            status="succeeded",
            output_report={"text": "old"},
        ),
        AgentInvocation(
            id="inv-2",
            template_id="writer.v1",
            skill_id="writer",
            iteration=2,
            status="succeeded",
            output_report={"text": "new"},
        ),
    ]

    output = runtime._output_for_graph_task(
        {"skill_id": "writer", "agent_template_id": "writer.v1"},
        invocations,
    )

    assert output == {"text": "new"}
```

Add a test for recorder failure:

```python
@pytest.mark.asyncio
async def test_team_kernel_record_invocation_failure_does_not_fail_invocation(monkeypatch):
    async def failing_record_node_event(**kwargs):
        raise RuntimeError("record failed")

    runtime = _team_runtime_for_unit_tests(record_node_event=failing_record_node_event)
    invocation = AgentInvocation(
        id="inv-1",
        execution_id="exec-1",
        template_id="writer.v1",
        display_name="Writer",
        assigned_role="writer",
        status="succeeded",
        output_report={"text": "done"},
    )

    await runtime._safe_record_invocation(invocation, status="succeeded")
```

Use existing test helpers where available; define `_team_runtime_for_unit_tests` in the test module if no helper exists.

- [ ] **Step 2: Run failing tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_kernel.py::test_team_kernel_output_mapping_prefers_latest_successful_invocation tests/agents/lead_agent/v2/test_team_kernel.py::test_team_kernel_record_invocation_failure_does_not_fail_invocation -q
```

Expected: latest-output test fails and `_safe_record_invocation` is missing.

- [ ] **Step 3: Implement safe recording and latest output selection**

In `kernel.py`, add:

```python
async def _safe_record_invocation(
    self,
    invocation: AgentInvocation,
    *,
    status: str,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> None:
    try:
        await self._record_invocation(
            invocation,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
        )
    except Exception:
        logger.warning("Failed to record team invocation node", exc_info=True)


async def _safe_publish_team_event(
    self,
    execution_id: str,
    event_name: str,
    payload: dict[str, Any],
) -> None:
    try:
        await self.publish_event(execution_id, event_name, payload)
    except Exception:
        logger.warning("Failed to publish team event %s", event_name, exc_info=True)
```

Replace direct `_record_invocation` and `publish_event("execution.team.invocation", ...)` calls in `_run_invocation` with safe helpers.

Change `_output_for_graph_task` to sort matching invocations by iteration and completion order:

```python
matches = [
    invocation
    for invocation in invocations
    if invocation.status == "succeeded"
    and self._invocation_matches_graph_task(invocation, task)
    and _has_meaningful_output(invocation.output_report)
]
if not matches:
    return None
latest = max(matches, key=lambda item: (int(item.iteration or 0), item.completed_at or datetime.min.replace(tzinfo=UTC), item.id))
return latest.output_report
```

- [ ] **Step 4: Run TeamKernel tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_kernel.py tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/lead_agent/v2/team/kernel.py backend/tests/agents/lead_agent/v2/test_team_kernel.py
git commit -m "fix: harden team kernel recording and output mapping"
```

---

## Task 8: Classify Harness Tool Failures And Split Tool Budgets

**Files:**
- Modify: `backend/src/agents/harness/contracts.py`
- Modify: `backend/src/agents/harness/policy.py`
- Modify: `backend/src/agents/harness/loop_guard.py`
- Modify: `backend/src/agents/harness/langchain_adapter.py`
- Modify: `backend/src/agents/harness/diff_tracker.py`
- Test: `backend/tests/agents/harness/test_langchain_adapter.py`
- Test: `backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py`

- [ ] **Step 1: Write failing budget and classification tests**

Add to `test_output_budget_loop_guard_and_diff_tracker.py`:

```python
def test_loop_guard_stops_total_tool_calls_independently_of_repeat_count() -> None:
    guard = HarnessLoopGuard(
        warn_threshold=3,
        repeated_hard_limit=5,
        total_hard_limit=3,
    )

    assert guard.record("sandbox.read_file", {"path": "/workspace/a.txt"}).allowed is True
    assert guard.record("sandbox.read_file", {"path": "/workspace/b.txt"}).allowed is True
    decision = guard.record("sandbox.read_file", {"path": "/workspace/c.txt"})

    assert decision.allowed is False
    assert decision.stop_reason == "tool_total_hard_stop"
```

Add to `test_langchain_adapter.py`:

```python
def test_format_tool_error_result_classifies_forbidden_tool() -> None:
    result = _format_tool_error_result(
        "sandbox.run_python",
        {"script_name": "analysis.py"},
        PermissionError("harness policy does not allow sandbox.run_python"),
    )
    payload = json.loads(result)

    assert payload["payload"]["error_code"] == "tool_forbidden"
    assert payload["payload"]["recoverable"] is False
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_langchain_adapter.py::test_format_tool_error_result_classifies_forbidden_tool tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py::test_loop_guard_stops_total_tool_calls_independently_of_repeat_count -q
```

Expected: fail because current guard has one `hard_limit` and error code is `tool_error`.

- [ ] **Step 3: Update policy contract**

In `backend/src/agents/harness/contracts.py`, add fields to `HarnessPolicy`:

```python
max_total_tool_calls: int = 30
max_repeated_identical_tool_calls: int = 5
```

In `policy.py`, resolve:

```python
max_total_tool_calls=int(sandbox_policy.get("max_total_tool_calls") or sandbox_policy.get("max_tool_calls") or 30),
max_repeated_identical_tool_calls=int(sandbox_policy.get("max_repeated_identical_tool_calls") or 5),
```

- [ ] **Step 4: Update loop guard**

In `loop_guard.py`, change the dataclass:

```python
class HarnessLoopGuard:
    warn_threshold: int = 3
    repeated_hard_limit: int = 5
    total_hard_limit: int = 30
    _counts: dict[str, int] | None = None
    _total_count: int = 0
```

Update `record`:

```python
self._total_count += 1
if self._total_count >= self.total_hard_limit:
    return LoopGuardDecision(
        allowed=False,
        count=self._total_count,
        should_warn=True,
        stop_reason="tool_total_hard_stop",
    )
...
if count >= self.repeated_hard_limit:
    return LoopGuardDecision(
        allowed=False,
        count=count,
        should_warn=True,
        stop_reason="tool_loop_hard_stop",
    )
```

In `langchain_adapter._loop_guard`, construct:

```python
guard = HarnessLoopGuard(
    warn_threshold=min(3, max(1, int(policy.max_repeated_identical_tool_calls or 1))),
    repeated_hard_limit=max(1, int(policy.max_repeated_identical_tool_calls or 1)),
    total_hard_limit=max(1, int(policy.max_total_tool_calls or 1)),
)
```

- [ ] **Step 5: Classify exceptions**

In `langchain_adapter.py`, add:

```python
def _harness_error_code(exc: Exception) -> tuple[str, bool]:
    message = str(exc).lower()
    if isinstance(exc, PermissionError) or "forbidden" in message or "not allow" in message:
        return "tool_forbidden", False
    if exc.__class__.__name__ == "UnknownHarnessToolError" or "unknown harness tool" in message:
        return "tool_unknown", False
    if "queue" in message and "timeout" in message:
        return "sandbox_queue_timeout", True
    if "timed out" in message or "timeout" in message:
        return "tool_timeout", True
    return "tool_error", True
```

Update `_format_tool_error_result`:

```python
error_code, recoverable = _harness_error_code(exc)
payload = {
    "preview": f"Tool {canonical_name} failed: {error}",
    "payload": {
        "tool": canonical_name,
        "args": args_summary,
        "error_code": error_code,
        "exception_type": exc.__class__.__name__,
        "recoverable": recoverable,
    },
    ...
}
```

- [ ] **Step 6: Run harness tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_langchain_adapter.py tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/src/agents/harness/contracts.py backend/src/agents/harness/policy.py backend/src/agents/harness/loop_guard.py backend/src/agents/harness/langchain_adapter.py backend/tests/agents/harness/test_langchain_adapter.py backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py
git commit -m "fix: classify harness failures and split tool budgets"
```

---

## Task 9: Bound Glob/Grep And Clarify Sandbox Timeout Manifests

**Files:**
- Modify: `backend/src/agents/harness/sandbox_tools.py`
- Modify: `backend/src/agents/harness/sandbox_execution_tools.py`
- Test: `backend/tests/agents/harness/test_sandbox_file_tools.py`
- Test: `backend/tests/agents/harness/test_scheduler_and_python_tool.py`

- [ ] **Step 1: Write failing glob/grep bounds tests**

Add to `backend/tests/agents/harness/test_sandbox_file_tools.py`:

```python
@pytest.mark.asyncio
async def test_glob_stops_after_match_limit_without_full_materialization(tmp_path):
    tools = _file_tools_for_tmp_workspace(tmp_path)
    for index in range(100):
        (tmp_path / f"file-{index}.txt").write_text("x", encoding="utf-8")

    result = await tools.glob({"pattern": "/workspace/*.txt", "max_matches": 5})

    assert result.structured_payload["returned_matches"] == 5
    assert result.structured_payload["match_limit"] == 5
    assert len(result.structured_payload["matches"]) == 5


@pytest.mark.asyncio
async def test_grep_literal_mode_handles_regex_metacharacters(tmp_path):
    tools = _file_tools_for_tmp_workspace(tmp_path)
    (tmp_path / "notes.txt").write_text("literal [abc\n", encoding="utf-8")

    result = await tools.grep({"pattern": "[abc", "literal": True, "max_matches": 5})

    assert result.structured_payload["returned_matches"] == 1
    assert result.error is None
```

- [ ] **Step 2: Write failing timeout manifest test**

Add to `backend/tests/agents/harness/test_scheduler_and_python_tool.py`:

```python
@pytest.mark.asyncio
async def test_run_python_manifest_separates_queue_and_execution_timeouts():
    result = await _run_python_tool_with_policy({"timeout_seconds": 900})
    manifest = result.structured_payload["execution_manifest"]

    assert manifest["queue_timeout_seconds"] == 30
    assert manifest["execution_timeout_seconds"] == 900
```

Use the existing helper in the test file that invokes `SandboxExecutionTools.run_python`; if the helper returns JSON, parse the JSON and assert on `payload.execution_manifest`.

- [ ] **Step 3: Run failing tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_sandbox_file_tools.py::test_glob_stops_after_match_limit_without_full_materialization tests/agents/harness/test_sandbox_file_tools.py::test_grep_literal_mode_handles_regex_metacharacters tests/agents/harness/test_scheduler_and_python_tool.py::test_run_python_manifest_separates_queue_and_execution_timeouts -q
```

Expected: fail until implementation is bounded and manifest keys exist.

- [ ] **Step 4: Implement bounded glob**

In `sandbox_tools.py`, replace full sorted materialization with incremental collection:

```python
matches: list[dict[str, Any]] = []
total_seen = 0
for path in base.glob(pattern):
    total_seen += 1
    if self._should_skip_path(path):
        continue
    matches.append(self._entry_payload(path))
    if len(matches) >= max_matches:
        break
matches.sort(key=lambda item: str(item.get("path") or ""))
```

If deterministic ordering over all matches is required by tests, use `itertools.islice(sorted(iterator), max_matches)` only after confirming the iterator is already constrained by root and ignore rules. Prefer streaming when directories can be large.

- [ ] **Step 5: Implement safe grep**

In `sandbox_tools.py`, ensure literal mode compiles escaped pattern:

```python
needle = str(pattern or "")
compiled = re.compile(re.escape(needle) if literal else needle)
```

Add a scanned-file cap and stop once `returned_matches >= max_matches`:

```python
if returned_matches >= max_matches:
    break
```

Keep invalid regex recoverable JSON behavior for `literal=False`.

- [ ] **Step 6: Split timeout manifest keys**

In `sandbox_execution_tools.py`, change `_execution_manifest` to accept both timeouts:

```python
payload["execution_manifest"] = _execution_manifest(
    context=self.context,
    sandbox_policy=self._sandbox_policy(),
    script_name=safe_script_name,
    dependency_hints=dependency_hints,
    payload=payload,
    queue_timeout_seconds=timeout_seconds,
    execution_timeout_seconds=int(self._sandbox_policy().get("timeout_seconds") or self.policy.max_sandbox_seconds),
)
```

Update manifest payload:

```python
"queue_timeout_seconds": _positive_int(queue_timeout_seconds),
"execution_timeout_seconds": _positive_int(execution_timeout_seconds),
"timeout_seconds": _positive_int(execution_timeout_seconds),
```

Keep `timeout_seconds` for current readers, but make it equal execution timeout. This is current semantics, not a compatibility branch.

- [ ] **Step 7: Run harness file and scheduler tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_sandbox_file_tools.py tests/agents/harness/test_scheduler_and_python_tool.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/src/agents/harness/sandbox_tools.py backend/src/agents/harness/sandbox_execution_tools.py backend/tests/agents/harness/test_sandbox_file_tools.py backend/tests/agents/harness/test_scheduler_and_python_tool.py
git commit -m "fix: bound sandbox search and clarify python timeouts"
```

---

## Task 10: Backend Commit State As Execution Fact

**Files:**
- Modify: `backend/src/services/execution_commit_service.py`
- Modify: execution DataService update/projection files that expose `ExecutionRecord.result` or `runtime_state`
- Modify: `frontend/lib/execution-run-view.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/ResultCard.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/CompletedView.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`
- Test: `backend/tests/services/test_execution_commit_service.py`
- Test: frontend result-card/live-workflow tests

- [ ] **Step 1: Write backend idempotent commit test**

Add to `backend/tests/services/test_execution_commit_service.py`:

```python
@pytest.mark.asyncio
async def test_commit_outputs_is_idempotent_by_execution_output_and_actor(fake_dataservice):
    service = ExecutionCommitService(dataservice=fake_dataservice)

    first = await service.commit_outputs(
        execution_id="exec-1",
        actor_id="user-1",
        output_ids=["doc-1"],
        idempotency_key="request-a",
    )
    second = await service.commit_outputs(
        execution_id="exec-1",
        actor_id="user-1",
        output_ids=["doc-1"],
        idempotency_key="request-b",
    )

    assert first["commit_state"]["accepted_output_ids"] == ["doc-1"]
    assert second["commit_state"]["accepted_output_ids"] == ["doc-1"]
    assert fake_dataservice.document_create_count("doc-1") == 1
```

- [ ] **Step 2: Run failing backend test**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/services/test_execution_commit_service.py::test_commit_outputs_is_idempotent_by_execution_output_and_actor -q
```

Expected: fail because commit state is local to idempotency key.

- [ ] **Step 3: Implement commit state merge**

In `execution_commit_service.py`, define:

```python
def _commit_state_from_execution(execution: Any) -> dict[str, Any]:
    result = getattr(execution, "result", None)
    result = result if isinstance(result, dict) else {}
    state = result.get("commit_state")
    if isinstance(state, dict):
        return {
            "accepted_output_ids": [str(item) for item in state.get("accepted_output_ids") or []],
            "rejected_output_ids": [str(item) for item in state.get("rejected_output_ids") or []],
            "room_links": [dict(item) for item in state.get("room_links") or [] if isinstance(item, dict)],
        }
    return {"accepted_output_ids": [], "rejected_output_ids": [], "room_links": []}
```

Before writing each output, skip if already accepted:

```python
commit_state = _commit_state_from_execution(execution)
accepted = set(commit_state["accepted_output_ids"])
requested_output_ids = [str(item) for item in output_ids or []]
output_ids_to_write = [item for item in requested_output_ids if item not in accepted]
```

After successful writes, persist merged state into execution result:

```python
commit_state["accepted_output_ids"] = sorted(accepted.union(output_ids_to_write))
commit_state["room_links"] = _merge_room_links(commit_state["room_links"], links)
result_payload = dict(getattr(execution, "result", None) or {})
result_payload["commit_state"] = commit_state
await self.execution_service.update_execution(execution_id, result=result_payload, commit=True)
```

Return:

```python
response["commit_state"] = commit_state
```

- [ ] **Step 4: Update frontend projection**

In `frontend/lib/execution-run-view.ts`, add `commitState` to `RunView`:

```ts
export interface RunViewCommitState {
  acceptedOutputIds: string[];
  rejectedOutputIds: string[];
  roomLinks: CommittedRoomLink[];
}
```

Map from execution result:

```ts
function commitStateFromExecution(record: ExecutionRecord): RunViewCommitState {
  const state = objectValue(objectValue(record.result)?.commit_state);
  return {
    acceptedOutputIds: stringArrayValue(state?.accepted_output_ids),
    rejectedOutputIds: stringArrayValue(state?.rejected_output_ids),
    roomLinks: arrayValue(state?.room_links)
      .map((item) => objectValue(item))
      .filter((item): item is Record<string, unknown> => Boolean(item))
      .map((item) => ({
        room: stringValue(item.room) ?? "",
        id: stringValue(item.id) ?? "",
        title: stringValue(item.title) ?? "",
      })),
  };
}
```

Use `view.commitState.acceptedOutputIds` in ResultCard/CompletedView/LiveWorkflowPanel instead of isolated `committed` booleans when an execution record is available.

- [ ] **Step 5: Run backend and frontend tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/services/test_execution_commit_service.py -q
cd frontend && npm run typecheck
cd frontend && npx vitest run
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/src/services/execution_commit_service.py frontend/lib/execution-run-view.ts frontend/app/(workbench)/workspaces/[id]/components/ResultCard.tsx frontend/app/(workbench)/workspaces/[id]/components/CompletedView.tsx frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx backend/tests/services/test_execution_commit_service.py
git commit -m "feat: persist execution commit state"
```

---

## Task 11: Canonicalize Chat Block Protocol

**Files:**
- Modify: `backend/src/application/handlers/thread_turn_handler.py`
- Modify: `backend/src/agents/chat_agent/blocks.py`
- Test: `backend/tests/application/handlers/test_thread_turn_handler.py`
- Test: `backend/tests/dataservice/test_conversation_domain.py`

- [ ] **Step 1: Write block roundtrip tests**

Add to `backend/tests/application/handlers/test_thread_turn_handler.py`:

```python
def test_launch_feature_blocks_use_canonical_kind_and_tool_payload_shape():
    messages = [
        AIMessage(
            content="",
            tool_calls=[{"name": "launch_feature", "args": {"feature_id": "sci_literature_positioning"}, "id": "call-1"}],
        ),
        ToolMessage(
            content=json.dumps({"status": "launched", "feature_id": "sci_literature_positioning", "execution_id": "exec-1"}),
            tool_call_id="call-1",
            name="launch_feature",
        ),
    ]

    blocks = _extract_launch_feature_blocks(messages)

    assert blocks[0]["kind"] == "tool_invocation"
    assert blocks[0]["tool"] == "launch_feature"
    assert blocks[0]["input"]["feature_id"] == "sci_literature_positioning"
    assert blocks[1]["kind"] == "tool_result"
    assert blocks[1]["tool"] == "launch_feature"
    assert blocks[1]["status"] == "launched"
    assert blocks[1]["output"]["execution_id"] == "exec-1"
```

Add a reasoning order test:

```python
def test_reasoning_block_is_appended_in_arrival_order():
    result = {
        "messages": [AIMessage(content="正文", additional_kwargs={"reasoning": "思考"})],
    }

    reply = _reply_from_agent_result(result, thread_id="thread-1")

    assert [block["kind"] for block in reply.blocks] == ["thinking"]
```

Use actual imports and helper access pattern from existing tests.

- [ ] **Step 2: Run failing tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/application/handlers/test_thread_turn_handler.py::test_launch_feature_blocks_use_canonical_kind_and_tool_payload_shape tests/application/handlers/test_thread_turn_handler.py::test_reasoning_block_is_appended_in_arrival_order -q
```

Expected: fail because current blocks use nested `data` and `type=reasoning/warning`.

- [ ] **Step 3: Normalize tool blocks**

In `thread_turn_handler.py`, change `_extract_launch_feature_blocks` to output top-level canonical fields:

```python
blocks.append(
    {
        "kind": "tool_invocation",
        "tool": invocation["tool"],
        "input": invocation.get("args") or {},
    }
)
...
blocks.append(
    {
        "kind": "tool_result",
        "tool": "launch_feature",
        "status": str(result.get("status") or ""),
        "output": result,
    }
)
```

Keep frontend stream compatibility by updating stream consumers if they currently read `data`.

- [ ] **Step 4: Normalize thinking/warning blocks**

Replace `_build_reasoning_block` output with:

```python
return {"kind": "thinking", "text": reasoning_text}
```

Replace warning block output with:

```python
{
    "kind": "status_line",
    "status": "warning",
    "text": "能力未启动",
    "data": {...},
}
```

Do not prepend thinking blocks ahead of tool blocks. Append in the order the handler observes them.

- [ ] **Step 5: Run conversation block tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/application/handlers/test_thread_turn_handler.py tests/dataservice/test_conversation_domain.py -q
```

Expected: all tests pass after frontend stream consumers are updated if necessary.

- [ ] **Step 6: Commit**

```bash
git add backend/src/application/handlers/thread_turn_handler.py backend/src/agents/chat_agent/blocks.py backend/tests/application/handlers/test_thread_turn_handler.py backend/tests/dataservice/test_conversation_domain.py
git commit -m "fix: canonicalize chat tool blocks"
```

---

## Task 12: Consolidate RunView Evidence Projection

**Files:**
- Modify: `frontend/lib/execution-run-view.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/useLiveWorkflowViewModel.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/utils.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/ReviewView.tsx`
- Test: `frontend/tests/execution-run-view.test.ts`

- [ ] **Step 1: Write projection tests**

Add to `frontend/tests/execution-run-view.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { runViewFromExecution } from "@/lib/execution-run-view";

describe("runViewFromExecution evidence projection", () => {
  it("projects result previews and evidence from a single sanitized layer", () => {
    const view = runViewFromExecution({
      id: "exec-1",
      status: "completed",
      workspace_id: "ws-1",
      feature_id: "sci_empirical_package",
      progress: 100,
      node_states: {
        "member-1": {
          status: "completed",
          node_type: "agent_invocation",
          label: "实验专家",
          node_metadata: {
            team: true,
            harness: {
              reproducibility_summary: {
                script_paths: ["/workspace/scripts/analysis.py"],
                dataset_paths: ["/workspace/datasets/panel.csv"],
                artifact_paths: ["/workspace/outputs/result.json"],
              },
            },
          },
        },
      },
      runtime_state: {},
      result: { data: { outputs: [{ id: "doc-1", kind: "document", preview: "报告" }] } },
      review_items: [],
    } as any);

    expect(view.evidenceItems.map((item) => item.summary).join("\n")).toContain("analysis.py");
    expect(view.evidenceItems.map((item) => item.summary).join("\n")).not.toContain("/workspace/tmp/tasks/.harness");
    expect(view.resultPreviews[0].id).toBe("doc-1");
  });
});
```

- [ ] **Step 2: Run failing test**

Run:

```bash
cd frontend && npx vitest run tests/execution-run-view.test.ts
```

Expected: fail because `RunView` lacks `evidenceItems` and `resultPreviews`.

- [ ] **Step 3: Extend `RunView`**

In `frontend/lib/execution-run-view.ts`, add:

```ts
export interface RunViewEvidenceItem {
  id: string;
  title: string;
  kind: "team" | "sandbox" | "citation" | "review" | "output";
  summary: string;
  nodeId?: string;
}

export interface RunViewResultPreview {
  id: string;
  kind: string;
  title: string;
  preview: string;
  canCommit: boolean;
}
```

Add fields to `RunView`:

```ts
evidenceItems: RunViewEvidenceItem[];
resultPreviews: RunViewResultPreview[];
pendingReviewCount: number;
```

Move sanitized evidence builders from `live-workflow/utils.ts` into this file or a new `frontend/lib/execution-evidence-view.ts`. Keep the public entry point through `runViewFromExecution`.

- [ ] **Step 4: Remove duplicate projection from view model**

In `useLiveWorkflowViewModel.ts`, replace local calls:

```ts
const view = runViewFromExecution(record);
const previews = view.resultPreviews;
const evidenceItems = view.evidenceItems;
```

Keep UI-only selection logic in the view model.

- [ ] **Step 5: Run frontend checks**

Run:

```bash
cd frontend && npx vitest run tests/execution-run-view.test.ts
cd frontend && npm run typecheck
```

Expected: tests and typecheck pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/execution-run-view.ts frontend/app/(workbench)/workspaces/[id]/components/live-workflow/useLiveWorkflowViewModel.ts frontend/app/(workbench)/workspaces/[id]/components/live-workflow/utils.ts frontend/app/(workbench)/workspaces/[id]/components/live-workflow/ReviewView.tsx frontend/tests/execution-run-view.test.ts
git commit -m "refactor: centralize execution evidence projection"
```

---

## Task 13: Strengthen Research Evidence Surfaces And Output Ref Recovery

**Files:**
- Modify: `backend/src/agents/harness/diff_tracker.py`
- Modify: `backend/src/agents/harness/context_assembly.py`
- Modify: `backend/src/contracts/research_evidence.py`
- Modify: SCI/thesis/proposal capability seed files under `backend/seed/capabilities/`
- Test: `backend/tests/agents/harness/test_context_assembly.py`
- Test: `backend/tests/agents/harness/test_research_eval_surfaces.py`
- Test: `backend/tests/seed/test_capability_seeds_load.py`

- [ ] **Step 1: Write output ref summary test**

Add to `backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py`:

```python
def test_harness_node_metadata_collects_generic_output_ref_summary() -> None:
    metadata = build_harness_node_metadata_from_tool_calls(
        [
            {
                "name": "sandbox.read_file",
                "status": "completed",
                "metadata": {
                    "output_refs": [
                        "/workspace/tmp/tasks/.harness/outputs/exec/node/inv/sandbox.read_file-abc.txt"
                    ],
                    "externalized": True,
                },
            },
            {
                "name": "sandbox.run_python",
                "status": "completed",
                "metadata": {
                    "output_refs": [
                        "/workspace/tmp/tasks/.harness/outputs/exec/node/inv/sandbox.run_python-def.txt"
                    ],
                    "externalized": True,
                },
            },
        ]
    )

    summary = metadata["harness"]["output_ref_summary"]
    assert summary["schema"] == "wenjin.harness.output_ref_summary.v1"
    assert summary["output_ref_count"] == 2
```

- [ ] **Step 2: Write context recovery test**

Add to `backend/tests/agents/harness/test_context_assembly.py`:

```python
def test_context_assembly_uses_generic_output_ref_summary_for_recovery() -> None:
    bundle = build_harness_context_bundle(
        workspace_id="ws-1",
        task={"inputs": {"goal": "reuse outputs"}},
        workspace_data={
            "recent_execution_evidence": [
                {
                    "node_metadata": {
                        "harness": {
                            "output_ref_summary": {
                                "schema": "wenjin.harness.output_ref_summary.v1",
                                "output_refs": [
                                    "/workspace/tmp/tasks/.harness/outputs/exec/node/inv/sandbox.read_file-abc.txt"
                                ],
                            }
                        }
                    }
                }
            ]
        },
        allowed_tools=["sandbox.read_output_ref"],
    )

    assert bundle["output_ref_recovery"]["refs"][0]["output_ref"].endswith("sandbox.read_file-abc.txt")
```

- [ ] **Step 3: Run failing tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py::test_harness_node_metadata_collects_generic_output_ref_summary tests/agents/harness/test_context_assembly.py::test_context_assembly_uses_generic_output_ref_summary_for_recovery -q
```

Expected: fail because `output_ref_summary` is not produced.

- [ ] **Step 4: Implement generic output ref summary**

In `diff_tracker.py`, add:

```python
def build_output_ref_summary_from_tool_calls(tool_calls: Any) -> dict[str, Any]:
    refs: list[str] = []
    for tool_call in _tool_call_dicts(tool_calls):
        metadata = tool_call.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        for value in (*_list_value(tool_call.get("output_refs")), *_list_value(metadata.get("output_refs"))):
            _append_safe_output_ref(refs, str(value or ""))
    if not refs:
        return {}
    return {
        "schema": "wenjin.harness.output_ref_summary.v1",
        "output_ref_count": len(refs),
        "output_refs": refs[:20],
    }
```

In `build_harness_node_metadata_from_tool_calls`, add:

```python
output_ref_summary = build_output_ref_summary_from_tool_calls(tool_calls)
if output_ref_summary:
    harness["output_ref_summary"] = output_ref_summary
```

- [ ] **Step 5: Update context assembly recovery**

In `context_assembly.py`, update `_output_ref_recovery` to accept both sandbox execution summary and output ref summary:

```python
output_ref_summary = _latest_harness_summary(safe_workspace_data, "output_ref_summary")
...
"output_ref_recovery": _output_ref_recovery(sandbox_execution_summary, output_ref_summary),
```

Update function:

```python
def _output_ref_recovery(
    sandbox_execution_summary: dict[str, Any],
    output_ref_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_refs = [
        *list(sandbox_execution_summary.get("output_refs") or []),
        *list((output_ref_summary or {}).get("output_refs") or []),
    ]
```

- [ ] **Step 6: Strengthen default research evidence surfaces**

In `backend/src/contracts/research_evidence.py`, make the default for paper-oriented tasks include stronger evidence:

```python
DEFAULT_RESEARCH_EVIDENCE_SURFACES = (
    "literature",
    "citation_strength",
    "paper_relevance",
    "experiment",
    "writing",
)
```

For empirical/reproducibility SCI seed files, ensure:

```yaml
research_evidence:
  required_surfaces:
    - workflow_trace
    - output_ref_reuse
    - experiment_interpretation
    - statistical_robustness
```

For literature-heavy SCI/thesis/proposal seed files, ensure:

```yaml
research_evidence:
  required_surfaces:
    - workflow_trace
    - citation_strength
    - paper_relevance
```

- [ ] **Step 7: Run evidence and seed tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_context_assembly.py tests/agents/harness/test_research_eval_surfaces.py tests/seed/test_capability_seeds_load.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/src/agents/harness/diff_tracker.py backend/src/agents/harness/context_assembly.py backend/src/contracts/research_evidence.py backend/seed/capabilities backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py backend/tests/agents/harness/test_context_assembly.py
git commit -m "feat: strengthen research evidence recovery"
```

---

## Task 14: Remove Catalog Context Fallbacks And Use Routing Clarification Copy

**Files:**
- Modify: `backend/src/application/services/feature_launch_context.py`
- Modify: `backend/src/tools/builtins/launch_feature.py`
- Test: `backend/tests/tools/test_launch_feature_tool.py`
- Test: `backend/tests/services/test_mission_policy_schema.py`

- [ ] **Step 1: Write fallback removal test**

Add to `backend/tests/tools/test_launch_feature_tool.py`:

```python
def test_missing_context_uses_capability_minimum_context_not_hardcoded_fallback():
    cap = SimpleNamespace(
        routing={
            "minimum_context": {"existing_materials_summary": "required"},
            "clarification": {"ask_when_missing": "请发已有材料摘要。"},
        },
        definition_json={},
    )

    missing = resolve_missing_context_fields(
        feature_id="sci_literature_positioning",
        params={"topic": "LLM agents"},
        launch_source="tool",
        minimum_context=extract_capability_minimum_context(cap),
    )

    assert missing == ["existing_materials_summary"]
```

- [ ] **Step 2: Run missing context tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/tools/test_launch_feature_tool.py -q
```

Expected: current behavior may pass for explicit minimum context; continue to Step 3 to remove fallback after confirming seed coverage.

- [ ] **Step 3: Remove static fallback for production path**

In `feature_launch_context.py`, change `resolve_missing_context_fields` so missing `minimum_context` returns no runtime requirement and does not consult `FEATURE_CONTEXT_REQUIREMENTS`:

```python
requirements = _context_requirements_from_minimum_context(minimum_context)
if not requirements:
    return []
```

Keep `FEATURE_CONTEXT_FIELD_LABELS` and `CONTEXT_FIELD_ALIASES`. Remove `FEATURE_CONTEXT_REQUIREMENTS` only after all tests that import it are updated.

- [ ] **Step 4: Use `clarification.ask_when_missing` in advisory**

Extend `build_missing_context_advisory`:

```python
def build_missing_context_advisory(
    *,
    feature_id: str,
    missing_fields: list[str],
    feature_name: str | None = None,
    clarification_prompt: str | None = None,
) -> FeatureExecutionAdvisory:
    prompt = (
        str(clarification_prompt).strip()
        if clarification_prompt and str(clarification_prompt).strip()
        else f"继续执行「{display_name}」前，还需要你补充：{missing_fields_str}。请直接回复补充信息，我会在当前执行会话继续。"
    )
```

In `launch_feature.py`, extract:

```python
clarification_prompt = None
routing = getattr(cap, "routing", None)
if isinstance(routing, dict):
    clarification = routing.get("clarification")
    if isinstance(clarification, dict):
        clarification_prompt = str(clarification.get("ask_when_missing") or "").strip() or None
```

Pass it into `build_missing_context_advisory`.

- [ ] **Step 5: Run launch and schema tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/tools/test_launch_feature_tool.py tests/services/test_mission_policy_schema.py tests/seed/test_capability_seeds_load.py -q
```

Expected: all tests pass and visible capability seeds provide routing minimum context.

- [ ] **Step 6: Commit**

```bash
git add backend/src/application/services/feature_launch_context.py backend/src/tools/builtins/launch_feature.py backend/tests/tools/test_launch_feature_tool.py
git commit -m "refactor: rely on capability routing context contract"
```

---

## Task 15: Documentation And Release Gate Alignment

**Files:**
- Modify: `docs/current/architecture.md`
- Modify: `docs/current/workspace-current-state.md`
- Modify: `docs/current/frontend-mission-contract.md`
- Modify: `docs/current/release-gate-checklist.md`

- [ ] **Step 1: Update architecture runtime constraints**

In `docs/current/architecture.md`, update the Agent Harness and Runtime sections with these exact points:

```markdown
- `launch_feature` is idempotent per persisted user message id. Agent retry may repeat the tool call, but repeated calls for the same `launch_idempotency_key` must return the original execution rather than creating a second execution or reporting unrelated lead-busy state.
- TeamKernel workspace context loading must pass `capability_policy`, explicit `TaskBrief.context_requirements`, and `user_id` into `RuntimeContextAssembler`; citation/library allowlists must not be empty because policy was dropped.
- Legacy deterministic `sandbox_python` subagents must emit the same harness metadata surfaces as React harness `sandbox.run_python`: execution manifest, reproducibility manifest, execution lifecycle, output refs, generated artifacts, and failure classification when available.
- Default frontend workflow UX must never render raw node input, raw node output, raw stdout/stderr, raw tool args, or internal harness refs. Diagnostics may expose sanitized summaries only.
```

- [ ] **Step 2: Update frontend contract**

In `docs/current/frontend-mission-contract.md`, add:

```markdown
Commit state is execution-backed. ResultCard, CompletedView, LiveWorkflowPanel, and Runs drawer must read accepted/rejected output state from execution projection when available; local `committed` state is only an optimistic pending indicator during the current request.
```

- [ ] **Step 3: Update release gates**

In `docs/current/release-gate-checklist.md`, add or update commands:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/tools/test_launch_feature_tool.py \
  tests/agents/chat_agent/test_capability_auto_launch.py \
  tests/agents/lead_agent/v2/test_team_kernel.py \
  tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py \
  tests/agents/harness \
  tests/subagents/v2/test_sandbox_python_metadata.py \
  tests/services/test_execution_commit_service.py -q

cd frontend && npm run typecheck
cd frontend && npx vitest run
```

- [ ] **Step 4: Run docs grep checks**

Run:

```bash
rg -n "raw stdout|raw stderr|sandbox console|fallback resolver|compat|legacy" docs/current backend/src frontend -S
```

Expected: remaining matches are either explicit prohibitions, migration history, tests, or intentionally named historical references. Production source should not introduce new stale `legacy` / `compat` paths.

- [ ] **Step 5: Commit**

```bash
git add docs/current/architecture.md docs/current/workspace-current-state.md docs/current/frontend-mission-contract.md docs/current/release-gate-checklist.md
git commit -m "docs: align runtime harness optimization contract"
```

---

## Final Verification

Run the focused release gate:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/tools/test_launch_feature_tool.py \
  tests/agents/chat_agent/test_capability_auto_launch.py \
  tests/application/handlers/test_thread_turn_runtime_config.py \
  tests/application/handlers/test_thread_turn_handler.py \
  tests/agents/lead_agent/v2/test_team_kernel.py \
  tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py \
  tests/agents/harness \
  tests/subagents/v2 \
  tests/services/test_execution_commit_service.py \
  tests/seed/test_capability_seeds_load.py -q
```

Run frontend verification:

```bash
cd frontend && npm run typecheck
cd frontend && npx vitest run
```

Run full backend suite when focused tests are green:

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
```

## Rollout Notes

Use small commits in the task order above. If Task 10 commit state requires DataService schema changes, split it into:

1. Backend projection-only commit state stored inside current execution result payload.
2. Dedicated DataService table or domain field if product needs audit-grade accepted/rejected output history.

Do not start Task 10 before Task 6 is merged; otherwise duplicate commit UX may still expose stale local state.

## Self-Review

Spec coverage:

- Chat launch ingress: Tasks 1, 2, 3, 11, 14.
- Lead/TeamKernel runtime: Tasks 4, 7.
- Academic harness evidence: Tasks 5, 8, 9, 13.
- Frontend execution projection and raw payload safety: Tasks 6, 10, 12.
- Commit lifecycle: Task 10.
- Documentation and release gate: Task 15.

Gap scan:

- The plan avoids open-ended implementation gaps. Each task identifies exact files, tests, commands, and concrete code shapes. Where existing fake names differ in tests, the step says to reuse the existing helper pattern while preserving assertions.

Type consistency:

- `launch_idempotency_key` is consistently stored in runtime config and execution params.
- `commit_state` uses `accepted_output_ids`, `rejected_output_ids`, and `room_links` across backend and frontend.
- Harness output refs use `output_ref_summary` and `output_ref_recovery`.
