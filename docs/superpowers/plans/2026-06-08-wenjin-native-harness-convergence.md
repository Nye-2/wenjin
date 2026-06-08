# Wenjin Native Harness Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Continue converging Wenjin's self-developed agent harness until workspace-scoped sandbox work, file operations, Python execution, team-agent context, and execution evidence are reliable enough for research/writing/experiment workflows without Codex SDK or deer-flow runtime dependencies.

**Architecture:** Keep the existing Wenjin chain as the only execution path: Chat Agent -> Lead Agent -> TeamKernel/static graph -> ReactSubagent -> Wenjin Harness -> DataService sandbox/execution/review domains. Codex and deer-flow remain reference systems only; the implementation must converge around `ExecutionRecord`, `ExecutionNodeRecord`, one active sandbox per workspace, capability/skill policy, and review-first artifact staging.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, Pydantic v2, LangGraph/LangChain adapter edge, DataService sandbox domain, pytest, ruff.

---

## Scope Guard

Do this:

- Strengthen the Wenjin-native harness under `backend/src/agents/harness/`.
- Preserve one active sandbox environment per workspace.
- Treat `/workspace` and `backend/src/sandbox/workspace_layout.py` as the sandbox filesystem source of truth.
- Keep all harness facts attached to existing execution events and node records.
- Continue TDD: failing test, minimal implementation, targeted verification, then broader verification.
- Commit in small slices after each stable behavior boundary.

Do not do this:

- Do not add Codex SDK, cc-switch, deer-flow runtime, or protocol compatibility layers.
- Do not introduce a second execution table, harness run table, frontend stream, or router bypass.
- Do not expose generic `sandbox.run_command` until Python execution, file tools, policy, output budgets, and audit summaries are stable.
- Do not make debug-only tool details part of the default user-facing UI.

## Current Working Slice

Current uncommitted slice is the final product-closure pass for the native harness:

- `backend/src/agents/lead_agent/v2/team/quality_gates.py`
- `backend/tests/agents/lead_agent/v2/test_team_quality_gates.py`
- `backend/src/agents/lead_agent/v2/team/kernel.py`
- `backend/tests/agents/lead_agent/v2/test_team_kernel.py`
- `backend/src/services/execution_service.py`
- `backend/tests/services/test_execution_service_node_state.py`
- `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/useLiveWorkflowViewModel.ts`
- `frontend/tests/unit/v2/live-workflow-view-model.test.ts`
- `docs/current/architecture.md`
- `docs/current/workspace-current-state.md`
- `docs/current/frontend-feature-plugin-contract.md`
- `docs/superpowers/plans/2026-06-08-wenjin-native-harness-convergence.md`

This slice fixes four browser-review findings:

- The team quality gate should describe optional replacement recruits as standby members, not implementation fallback.
- LiveWorkflowPanel must prioritize the active/running execution over stale persisted history selection so a newly launched team run is visible immediately.
- TeamKernel quality gates must persist into `ExecutionRecord.runtime_state.quality_gates` so refresh/history views can restore quality-check summaries.
- Execution list/detail API must hydrate `ExecutionRecord.node_states` from `ExecutionNodeRecord` rows so team members and harness metadata survive fast terminal runs and history reads.

Finish this slice with Docker/browser verification before committing.

---

### Task 0: Close Current `sandbox.run_python` Manifest Slice

**Files:**

- Modify: `backend/src/agents/harness/sandbox_execution_tools.py`
- Modify: `backend/src/agents/harness/langchain_adapter.py`
- Modify: `backend/tests/agents/harness/test_scheduler_and_python_tool.py`
- Modify: `backend/tests/agents/harness/test_langchain_adapter.py`
- Modify: `docs/current/architecture.md`
- Modify: `docs/current/workspace-current-state.md`
- Modify: `docs/superpowers/specs/2026-06-06-wenjin-native-agent-harness-design.md`

- [x] **Step 1: Confirm the behavior contract**

The final `sandbox.run_python` tool result must include:

```json
{
  "execution_manifest": {
    "schema": "wenjin.harness.run_python.execution_manifest.v1",
    "tool": "sandbox.run_python",
    "workspace_id": "ws-1",
    "execution_id": "exec-1",
    "node_id": "node-1",
    "invocation_id": "inv-1",
    "script_name": "analysis.py",
    "script_path": "/workspace/scripts/analysis.py",
    "dependency_hints": ["pandas"],
    "sandbox_job_id": "job-1",
    "sandbox_environment_id": "env-1",
    "network_profile": "none",
    "timeout_seconds": 30
  }
}
```

Nonzero Python exits must return a bounded tool result instead of aborting the agent loop:

```json
{
  "failure_classification": {
    "schema": "wenjin.harness.run_python.failure_classification.v1",
    "category": "user_code",
    "reason": "nonzero_exit",
    "failure_code": "python_exit_nonzero",
    "exit_code": 2,
    "stderr_preview": "boom",
    "recoverable": true
  },
  "error_code": "python_exit_nonzero"
}
```

- [x] **Step 2: Finish documentation sync**

Update `docs/current/workspace-current-state.md` and `docs/superpowers/specs/2026-06-06-wenjin-native-agent-harness-design.md` so they state:

- `sandbox.run_python` always returns `execution_manifest`.
- User-code nonzero exits are recoverable tool errors with `failure_classification`.
- LangChain adapter metadata exposes `execution_manifest`, `failure_classification`, `error_code`, and `recoverable_error`.
- Node records and completed tool events preserve this evidence.

- [x] **Step 3: Run targeted tests**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/harness/test_scheduler_and_python_tool.py tests/agents/harness/test_langchain_adapter.py -q
```

Expected:

```text
12 passed
```

- [x] **Step 4: Run harness tests and lint**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/harness -q
.venv/bin/ruff check src/agents/harness/sandbox_execution_tools.py src/agents/harness/langchain_adapter.py tests/agents/harness/test_scheduler_and_python_tool.py tests/agents/harness/test_langchain_adapter.py
cd /Users/ze/wenjin
git diff --check
```

Expected:

```text
pytest: all selected tests pass
ruff: All checks passed!
git diff --check: no output
```

- [x] **Step 5: Commit current slice**

Run:

```bash
cd /Users/ze/wenjin
git status --short
git add backend/src/agents/harness/sandbox_execution_tools.py backend/src/agents/harness/langchain_adapter.py backend/tests/agents/harness/test_scheduler_and_python_tool.py backend/tests/agents/harness/test_langchain_adapter.py docs/current/architecture.md docs/current/workspace-current-state.md docs/superpowers/specs/2026-06-06-wenjin-native-agent-harness-design.md
git commit -m "feat: classify sandbox python failures"
```

Expected: one clean commit with only the manifest/failure-classification slice.

---

### Task 1: Harden Workspace Sandbox Filesystem Contract

**Files:**

- Modify: `backend/src/sandbox/workspace_layout.py`
- Modify: `backend/src/sandbox/docker_provider.py`
- Modify: `backend/src/sandbox/local_provider.py`
- Test: `backend/tests/sandbox/test_workspace_layout.py`
- Test: `backend/tests/agents/harness/test_sandbox_tools_path_policy.py`
- Docs: `docs/current/workspace-current-state.md`
- Docs: `docs/superpowers/specs/2026-06-06-wenjin-native-agent-harness-design.md`

- [x] **Step 1: Write failing layout manifest test**

Add or extend a test asserting the canonical layout is deterministic:

```python
def test_workspace_layout_manifest_is_deterministic(tmp_path):
    ensure_workspace_sandbox_layout(tmp_path)
    first = (tmp_path / ".wenjin" / "manifest.json").read_text()

    ensure_workspace_sandbox_layout(tmp_path)
    second = (tmp_path / ".wenjin" / "manifest.json").read_text()

    assert first == second
    assert "/workspace/main" in first
    assert "/workspace/datasets" in first
    assert "/workspace/scripts" in first
    assert "/workspace/outputs" in first
    assert "/workspace/reports" in first
    assert "/workspace/tmp" in first
```

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/sandbox/test_workspace_layout.py::test_workspace_layout_manifest_is_deterministic -q
```

Expected before implementation: fail if manifest content or deterministic behavior is incomplete.

- [x] **Step 2: Implement deterministic layout data**

Keep the public helpers in `workspace_layout.py`; do not scatter path constants into providers. The manifest should contain stable schema/version/roots/protected/internal metadata and no timestamps.

- [x] **Step 3: Add symlink/path-policy regression tests**

Add tests covering:

- visible symlink to `.wenjin/env/**` is not listed as readable content.
- visible symlink to external host path is rejected.
- direct `/workspace/outputs/harness/**` read is rejected.
- direct writes to `.wenjin/cache/**`, `.wenjin/env/**`, `.env`, `*.pem`, `*.key` are rejected.
- root and nested `.env` / `.env.*` files are protected, hidden from list/search, and rejected by direct file reads.

- [x] **Step 4: Run sandbox and harness path tests**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/sandbox/test_workspace_layout.py tests/agents/harness/test_sandbox_tools_path_policy.py -q
```

Expected: all selected tests pass.

- [x] **Step 5: Commit**

Commit message:

```bash
git commit -m "feat: harden workspace sandbox layout contract"
```

---

### Task 2: Add Sandbox Execution Evidence Summary to Node Metadata

**Files:**

- Modify: `backend/src/agents/harness/diff_tracker.py`
- Modify: `backend/src/agents/lead_agent/v2/runtime.py`
- Modify: `backend/src/agents/lead_agent/v2/team/kernel.py`
- Test: `backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py`
- Test: `backend/tests/agents/lead_agent/v2/test_runtime.py`
- Test: `backend/tests/agents/lead_agent/v2/test_team_kernel.py`

- [x] **Step 1: Write failing summary test**

Expected node metadata shape:

```json
{
  "harness": {
    "sandbox_execution_summary": {
      "schema": "wenjin.harness.sandbox_execution_summary.v1",
      "python_runs": 1,
      "failed_python_runs": 1,
      "recoverable_failures": 1,
      "sandbox_job_ids": ["job-1"],
      "sandbox_environment_ids": ["env-1"],
      "failure_codes": ["python_exit_nonzero"],
      "generated_artifact_count": 2
    }
  }
}
```

The summary should be derived from existing tool records, not a new persistence model.

- [x] **Step 2: Implement pure summary builder**

Add a pure function near the existing metadata aggregation logic:

```python
def build_sandbox_execution_summary_from_tool_calls(tool_calls: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    ...
```

Rules:

- Only inspect `sandbox.run_python` tool calls.
- Deduplicate job/environment IDs.
- Count recoverable failures from metadata, not raw preview text.
- Bound all string lists.
- Return `None` when no sandbox execution evidence exists.

- [x] **Step 3: Attach summary in static graph and TeamKernel paths**

Add the summary beside the existing `file_change_summary` and `tool_failure_summary` under `node_metadata.harness`.

- [x] **Step 4: Run metadata tests**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/harness/test_diff_tracker.py tests/agents/lead_agent/v2/test_runtime_harness_metadata.py -q
```

Expected: all selected tests pass.

- [x] **Step 5: Commit**

Commit message:

```bash
git commit -m "feat: summarize sandbox execution evidence"
```

---

### Task 3: Build Bounded Harness Context Assembly for Team Members

**Files:**

- Create: `backend/src/agents/harness/context_assembly.py`
- Modify: `backend/src/subagents/v2/types/react.py`
- Modify: `backend/src/agents/lead_agent/v2/team/kernel.py`
- Test: `backend/tests/agents/harness/test_context_assembly.py`
- Test: `backend/tests/subagents/v2/test_react_harness_context.py`
- Docs: `docs/current/architecture.md`
- Docs: `docs/current/workspace-current-state.md`

- [x] **Step 1: Write failing context-bundle tests**

Expected compact context:

```json
{
  "schema": "wenjin.harness.context_bundle.v1",
  "workspace_id": "ws-1",
  "workspace_type": "sci",
  "task": {"goal": "run experiment"},
  "sandbox": {
    "root": "/workspace",
    "standard_dirs": ["/workspace/main", "/workspace/scripts", "/workspace/outputs", "/workspace/reports", "/workspace/tmp"],
    "protected_paths": ["/workspace/.wenjin/**", "/workspace/.git/**"],
    "artifact_roots": ["/workspace/outputs", "/workspace/reports"]
  },
  "recent_execution_evidence": [],
  "budget": {"max_chars": 12000, "truncated": false}
}
```

The test should prove protected/internal paths never enter the context bundle.

- [x] **Step 2: Implement pure assembler**

Create `context_assembly.py` with pure functions first:

```python
def build_harness_context_bundle(... ) -> dict[str, Any]:
    ...
```

Keep DataService access at caller boundaries. The assembler should accept already-loaded summaries so it stays easy to test.

- [x] **Step 3: Inject context into ReactSubagent system prompt**

Add a compact `Harness context bundle` section and recent execution evidence. Do not dump raw tool JSON. Use summaries from `sandbox_execution_summary`, `file_change_summary`, and `tool_failure_summary`.

- [x] **Step 4: Run context tests**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/harness/test_context_assembly.py tests/subagents/v2/test_react_harness_context.py -q
```

Expected: all selected tests pass.

- [x] **Step 5: Commit**

Commit message:

```bash
git commit -m "feat: assemble bounded harness context"
```

---

### Task 4: Add Harness Replan Signals Without Adding a New Workflow Engine

**Files:**

- Modify: `backend/src/agents/lead_agent/v2/team/kernel.py`
- Modify: `backend/src/agents/lead_agent/v2/team/recruitment.py`
- Modify: `backend/src/agents/lead_agent/v2/runtime.py`
- Test: `backend/tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py`

- [x] **Step 1: Write failing tests for replan triggers**

Scenarios:

- `python_exit_nonzero` from a code agent should stay recoverable and be visible to Lead for bounded retry/recruitment.
- `sandbox_queue_timeout` should not trigger infinite reruns.
- `tool_forbidden` should not be solved by recruiting another member with the same forbidden tool request.

- [x] **Step 2: Implement replan signal extraction**

Represent signals as execution metadata only:

```json
{
  "schema": "wenjin.harness.replan_signal.v1",
  "trigger": "recoverable_tool_failure",
  "failure_codes": ["python_exit_nonzero"],
  "recommended_action": "revise_script_or_recruit_code_agent",
  "max_extra_iterations": 1
}
```

No new run loop. TeamKernel quality gates and existing bounded iterations remain the mechanism.

- [x] **Step 3: Wire signals into TeamKernel quality decision input**

Pass compact signals into the quality gate prompt/context. Do not expose raw stderr to users by default.

- [x] **Step 4: Run TeamKernel tests**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py -q
```

Expected: all selected tests pass.

- [x] **Step 5: Commit**

Commit message:

```bash
git commit -m "feat: feed harness failures into team replanning"
```

---

### Task 5: Migrate Role Templates to Use the Harness Contract

**Files:**

- Modify: `backend/seed/capabilities/sci/*.yaml`
- Modify: `backend/seed/capabilities/thesis/*.yaml`
- Modify: `backend/src/subagents/v2/registry.py`
- Test: `backend/tests/subagents/v2/test_registry.py`
- Test: `backend/tests/agents/lead_agent/v2/test_capability_tool_policy.py`
- Docs: `docs/current/architecture.md`

- [x] **Step 1: Audit current template tool declarations**

Run:

```bash
cd /Users/ze/wenjin
rg "sandbox\\.|filesystem\\.|allowed_tools|tool_affinity|risk_profile" backend/seed backend/src/subagents -n
```

Record mismatches:

- unknown tool names.
- tools declared in prompts but absent from policy.
- broad write/exec claims without explicit permissions.

- [x] **Step 2: Write failing registry validation tests**

Assert:

- declared tool names resolve exactly.
- capability policy is the maximum envelope.
- template/skill cannot widen tool access.
- role templates receive the sandbox workspace contract.

- [x] **Step 3: Update role templates**

Use concrete, product-specific wording:

- Literature roles: prefer `sandbox.read_file`, `sandbox.glob`, `sandbox.grep`; write reports under `/workspace/reports`.
- Code/experiment roles: generate scripts under `/workspace/scripts`; generated plots/results under `/workspace/outputs`; handle dependency hints explicitly.
- Writing roles: do not mutate Prism files directly unless using approved review/staging flow.
- Utility/fill-in roles: read/search broadly, write only when capability grants `filesystem.write` and `filesystem.diff`.

- [x] **Step 4: Run validation**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/subagents/v2/test_registry.py tests/agents/lead_agent/v2/test_capability_tool_policy.py -q
```

Expected: all selected tests pass.

- [x] **Step 5: Commit**

Commit message:

```bash
git commit -m "chore: align role templates with harness tools"
```

---

## Focused Execution Plan From Current State

The next work must stay on the Wenjin-native harness path. Codex SDK, cc-switch, deer-flow runtime, and protocol compatibility layers are out of scope. External projects are references only; implementation converges around Wenjin's existing Chat Agent -> Lead Agent -> TeamKernel -> ReactSubagent -> Harness -> DataService path.

### Phase A: Role Template and Tool Policy Convergence

Goal: make team实名制成员模板 match the real harness tool contract, so roles can act autonomously inside `/workspace` without hidden prompt-only assumptions.

Execution order:

1. Audit all capability seeds and subagent registry declarations:

   ```bash
   rg "sandbox\\.|filesystem\\.|allowed_tools|tool_affinity|risk_profile" backend/seed backend/src/subagents -n
   ```

2. Add failing tests proving:

   - sandbox tool names used by templates resolve to canonical harness tools.
   - capability policy is the maximum permission envelope.
   - role templates and skills cannot widen tool access by prompt wording.
   - React subagents always receive `wenjin.harness.context_bundle.v1`.

3. Update `sci` and `thesis` role wording to use the canonical `/workspace` contract:

   - literature/research roles read and synthesize, write reports only under `/workspace/reports`.
   - code/experiment roles write scripts under `/workspace/scripts` and outputs under `/workspace/outputs`.
   - writing/revision roles stage suggested changes instead of directly mutating Prism source files unless an approved review flow grants it.
   - utility roles default to read/search, only write when capability policy explicitly grants it.

4. Run targeted backend validation:

   ```bash
   cd /Users/ze/wenjin/backend
   .venv/bin/python -m pytest tests/subagents/v2/test_registry.py tests/agents/lead_agent/v2/test_capability_tool_policy.py -q
   ```

Commit boundary: `chore: align role templates with harness tools`.

### Phase B: One-Workspace-One-Sandbox E2E Contract

Goal: prove the new harness can complete a realistic research/experiment slice in one workspace sandbox, without creating another runtime path.

Execution order:

1. Add an integration test with a mock sandbox provider:

   - Lead dispatches a code/experiment team member.
   - Subagent receives bounded `/workspace` contract.
   - Subagent writes `/workspace/scripts/analysis.py`.
   - Harness runs `sandbox.run_python`.
   - Execution manifest records job/environment IDs.
   - Generated `/workspace/outputs/result.json` is discovered as an artifact candidate.
   - Node metadata contains file change summary, sandbox execution summary, tool failure summary when relevant.
   - Protected paths such as `/workspace/.wenjin/**`, `.env`, keys, and internal harness outputs never enter user-facing context.

2. Keep this test inside existing execution records and node records. No new harness run table.

3. Run:

   ```bash
   cd /Users/ze/wenjin/backend
   .venv/bin/python -m pytest tests/integration/test_harness_mock_sandbox_e2e.py -q
   .venv/bin/python -m pytest tests/agents/harness tests/agents/lead_agent/v2 -q
   ```

Commit boundary: `test: cover harness mock sandbox workflow`.

### Phase C: Product-Facing Execution UX Projection

Goal: make the harness visible to users as a clear team workflow, not as tool JSON or debug noise.

Execution order:

1. Add frontend projection tests in `frontend/lib/execution-run-view.test.ts`.

2. Update `frontend/lib/execution-run-view.ts` only as the source of truth for run display:

   - Show member display name and concise task state.
   - Show generated artifacts and review actions.
   - Collapse stdout/stderr, args, raw manifests, and debug payloads by default.
   - Keep LiveWorkflowPanel, Runs drawer, and chat launch receipt consistent through the same projection.

3. Run:

   ```bash
   cd /Users/ze/wenjin/frontend
   npm run typecheck
   npx vitest run frontend/lib/execution-run-view.test.ts
   ```

Commit boundary: `feat: simplify harness execution projection`.

### Phase D: Browser and Docker Smoke Test

Goal: verify product behavior through the actual stack, not only unit tests.

Execution order:

1. Start with Docker Compose or the current documented local stack.

2. Browser-test the main flows:

   - login/session remains valid when switching Wenjin/Prism.
   - create/open workspace.
   - trigger a team-agent research or experiment task.
   - observe LiveWorkflowPanel showing real member names and clean progress states.
   - open run details and confirm debug details are collapsed.
   - open Prism, use AI 改稿, compile/open PDF contrast, ensure panels do not obscure core editing flow.

3. Fix functional/UI regressions immediately if found, with focused tests where possible.

Commit boundary: one commit per fixed regression, or `fix: stabilize harness browser flow` if changes are tightly related.

### Phase E: Final Architecture Review and Docs

Goal: leave the branch mergeable and understandable.

Execution order:

1. Update:

   - `docs/current/architecture.md`
   - `docs/current/workspace-current-state.md`
   - `docs/current/frontend-feature-plugin-contract.md` if frontend projection contract changes
   - `docs/superpowers/specs/2026-06-06-wenjin-native-agent-harness-design.md`

2. Run final verification:

   ```bash
   cd /Users/ze/wenjin/backend
   .venv/bin/python -m pytest tests/ -q
   .venv/bin/ruff check

   cd /Users/ze/wenjin/frontend
   npm run typecheck
   npx vitest run

   cd /Users/ze/wenjin
   git diff --check
   ```

3. Final review checklist:

   - no Codex SDK or deer-flow runtime dependency.
   - no extra router/runtime/table/store for harness.
   - one workspace maps to one active sandbox.
   - all sandbox files use `/workspace` virtual paths.
   - user-facing UI is concise; debug data remains inspectable but not default.
   - role templates, tool policy, runtime context, execution metadata, and UI projection point to one contract.

Commit boundary: `docs: update harness architecture state`.

---

### Task 6: Add Minimal Product-Facing Harness UX Projection

**Files:**

- Modify: `frontend/lib/execution-run-view.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`
- Modify: `frontend/stores/run-ui-store.ts`
- Test: `frontend/lib/execution-run-view.test.ts`

- [x] **Step 1: Write failing projection tests**

Default user-facing execution projection should show:

- team member name.
- concise activity label such as "正在运行实验" or "已生成实验结果".
- generated artifact candidates if reviewable.
- no raw JSON args, no full stdout/stderr, no debug-only command details.

- [x] **Step 2: Implement projection only from existing execution events**

Do not add a new frontend harness store. `execution-run-view.ts` remains the shared projection source.

- [x] **Step 3: Run frontend tests**

Run:

```bash
cd /Users/ze/wenjin/frontend
npm run typecheck
npx vitest run frontend/lib/execution-run-view.test.ts
```

Browser smoke stays in Phase D against the Docker/local stack for:

- create workspace.
- trigger team-agent task.
- observe LiveWorkflowPanel.
- open run details.
- confirm debug details are collapsed.

- [x] **Step 4: Commit**

Commit message:

```bash
git commit -m "feat: simplify harness execution projection"
```

---

### Task 7: End-to-End Mock Sandbox Verification

**Files:**

- Test: `backend/tests/integration/test_harness_mock_sandbox_e2e.py`
- Modify only if needed: `backend/tests/fakes/*`
- Docs: `docs/current/workspace-current-state.md`

- [x] **Step 1: Create a mock sandbox E2E test**

The test should simulate:

1. Lead dispatches a code/experiment subagent.
2. Subagent receives bounded `/workspace` contract.
3. Subagent writes `/workspace/scripts/analysis.py`.
4. Subagent runs `sandbox.run_python`.
5. Python run returns execution manifest.
6. Generated `/workspace/outputs/result.json` is discovered as an artifact candidate.
7. Node metadata contains file change summary, sandbox execution summary, and no protected/internal refs.

- [x] **Step 2: Run E2E and relevant backend tests**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/integration/test_harness_mock_sandbox_e2e.py -q
.venv/bin/python -m pytest tests/agents/harness tests/agents/lead_agent/v2/test_sandbox_runtime.py -q
```

Expected: all selected tests pass.

- [x] **Step 3: Run full backend test suite before broader merge**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/ -q
```

Expected: all backend tests pass.

- [x] **Step 4: Commit**

Commit message:

```bash
git commit -m "test: cover harness mock sandbox workflow"
```

---

### Task 8: Stabilize Active Team Run Visibility

**Files:**

- Modify: `backend/src/agents/lead_agent/v2/team/quality_gates.py`
- Test: `backend/tests/agents/lead_agent/v2/test_team_quality_gates.py`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/useLiveWorkflowViewModel.ts`
- Test: `frontend/tests/unit/v2/live-workflow-view-model.test.ts`

- [x] **Step 1: Write failing backend terminology regression**

Add:

```python
def test_quality_gates_use_standby_reason_for_optional_replacement() -> None:
    invocation = _invocation(status="failed", output_report=None)

    gates = evaluate_quality_gates(
        ["evidence_traceability"],
        [invocation],
        team_policy=CapabilityTeamPolicy(
            core_templates=["research_scout.v1"],
            optional_templates=["generalist_assistant.v1"],
            recruitment_triggers={},
        ),
        counts=Counter({"research_scout.v1": 1}),
        latest_invocations=[invocation],
    )

    pipeline_gate = next(gate for gate in gates if gate.gate_id == "evidence_traceability")
    assert pipeline_gate.next_action == "recruit_more"
    assert pipeline_gate.suggested_recruits == [
        {
            "template_id": "generalist_assistant.v1",
            "reason": "standby_member",
        }
    ]
```

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_quality_gates.py::test_quality_gates_use_standby_reason_for_optional_replacement -q
```

Expected before implementation: fail because the old reason is `optional_fallback`.

- [x] **Step 2: Rename optional recruit reason**

Change `_replacement_recruits()` so optional replacements use:

```python
(template_id, "standby_member")
```

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_quality_gates.py -q
```

Expected:

```text
8 passed
```

- [x] **Step 3: Write failing frontend selection regression**

Add tests proving these two cases:

- active running execution wins over stale selected history run.
- newly running execution remains visible even when persisted selection points to an old run.

Run:

```bash
cd /Users/ze/wenjin/frontend
npx vitest run tests/unit/v2/live-workflow-view-model.test.ts -t "stale|active running"
```

Expected before implementation: fail because the old selected run remains selected.

- [x] **Step 4: Prioritize nonterminal executions in the view model**

Make `resolveSelectedLiveWorkflowRecord()` select in this order:

```text
active nonterminal record
focused nonterminal record
any nonterminal record
persisted selected record
focused record
active record
first record
```

Run:

```bash
cd /Users/ze/wenjin/frontend
npx vitest run tests/unit/v2/live-workflow-view-model.test.ts
npx vitest run tests/unit/lib/execution-run-view.test.ts
```

Expected:

```text
live-workflow-view-model: 5 passed
execution-run-view: 13 passed
```

- [x] **Step 5: Rebuild frontend stack and browser-test the actual flow**

Run:

```bash
cd /Users/ze/wenjin
docker compose -f docker-compose.yml -f docker-compose.local-build.yml up -d --build frontend
docker compose ps
```

Expected: `frontend`, `gateway`, `dataservice`, `worker`, `postgres`, `redis`, and `nginx` are healthy.

Browser-test at `http://localhost:2026`:

- logged-in session stays valid when switching Workbench and Prism.
- Prism compile opens PDF contrast without silently hiding the result.
- Prism AI 改稿 no longer exposes internal labels such as `同步小改` or `异步大改`.
- launching `文献定位与创新点` selects the new running execution in LiveWorkflowPanel, not a stale failed Prism run.
- LiveWorkflowPanel shows product-facing role/member language and keeps technical/debug details collapsed by default.

Observed verification result:

- Docker stack rebuilt with `docker compose -f docker-compose.yml -f docker-compose.local-build.yml up -d --build frontend gateway worker`.
- Browser Workbench/Prism switching kept the logged-in session.
- Prism compile opened the PDF contrast surface; AI 改稿 no longer showed internal `同步小改` / `异步大改` labels.
- A team-kernel run selected the active execution over stale history and restored six real-name team members from hydrated node records.
- LiveWorkflowPanel default view showed product-facing member/progress language and did not expose raw JSON.

- [x] **Step 6: Verify seeded capability runtime for the browser-tested flow**

Run:

```bash
cd /Users/ze/wenjin
docker compose exec -T postgres psql -U postgres -d wenjin -c "select id, runtime->>'mode' as mode from capability_definitions where id='sci_literature_positioning';"
```

Expected: `mode` is `team_kernel`. If the local dev database is stale, use the existing admin seed import path rather than changing production bootstrap overwrite behavior.

Observed verification result:

```text
sci_literature_positioning | team_kernel
```

Commit message:

```bash
git commit -m "fix: keep active team runs visible"
```

---

### Task 9: Final Harness Closure Review

**Files:**

- Docs only if the implemented state changed:
  - `docs/current/architecture.md`
  - `docs/current/workspace-current-state.md`
  - `docs/current/frontend-feature-plugin-contract.md`
  - `docs/superpowers/specs/2026-06-06-wenjin-native-agent-harness-design.md`

- [x] **Step 1: Residual architecture scan**

Run:

```bash
cd /Users/ze/wenjin
rg "codex|cc-switch|ccswitch|deer-flow|deerflow|kimi-for-coding|api\\.kimi\\.com/coding|Codex SDK|Responses-to-Chat|sandbox\\.run_command" backend/src frontend -n
```

Expected: no production references.

Observed verification result: no production references were found in `backend/src` or `frontend`.

- [x] **Step 2: Backend verification**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_quality_gates.py tests/agents/lead_agent/v2/test_team_kernel.py tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py -q
.venv/bin/python -m pytest tests/agents/harness tests/integration/test_harness_mock_sandbox_e2e.py -q
```

Expected: all selected tests pass.

Observed verification result:

```text
tests/agents/lead_agent/v2/test_team_quality_gates.py
tests/agents/lead_agent/v2/test_team_kernel.py
tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py
tests/services/test_execution_service_node_state.py
tests/gateway/test_executions_node_detail.py
41 passed

tests/agents/harness
tests/integration/test_harness_mock_sandbox_e2e.py
73 passed
```

- [x] **Step 3: Frontend verification**

Run:

```bash
cd /Users/ze/wenjin/frontend
npm run typecheck
npx vitest run tests/unit/v2/live-workflow-view-model.test.ts tests/unit/lib/execution-run-view.test.ts
```

Expected: typecheck passes and selected tests pass.

Observed verification result:

```text
npm run typecheck: passed
tests/unit/v2/live-workflow-view-model.test.ts
tests/unit/lib/execution-run-view.test.ts
tests/unit/stores/execution-store.test.ts
26 passed
```

- [x] **Step 4: Diff hygiene and docs check**

Run:

```bash
cd /Users/ze/wenjin
git diff --check
git status --short
```

Expected: no whitespace errors; only the planned files are modified unless browser testing found a real regression that was fixed with tests.

Observed verification result: `git diff --check` returned no output. Current diff also includes execution node hydration and quality gate runtime-state persistence because browser testing found those projection gaps.

- [ ] **Step 5: Commit and report remaining risk honestly**

Run:

```bash
cd /Users/ze/wenjin
git add backend/src/agents/lead_agent/v2/team/quality_gates.py backend/tests/agents/lead_agent/v2/test_team_quality_gates.py frontend/app/\(workbench\)/workspaces/\[id\]/components/live-workflow/useLiveWorkflowViewModel.ts frontend/tests/unit/v2/live-workflow-view-model.test.ts docs/superpowers/plans/2026-06-08-wenjin-native-harness-convergence.md
git commit -m "fix: keep active team runs visible"
```

Expected: clean commit. Do not claim the whole harness is complete unless Docker/browser and targeted backend/frontend tests all pass.

---

### Task 10: Close Team Member Input and Business Tool Gaps

**Why this is next:**

Browser testing proved the execution projection is stable, but it also exposed two real product-quality blockers in `sci_literature_positioning`:

- `research_scout.v1` can receive an empty `query` when TeamKernel launches from a raw user message without a parsed `topic/query`.
- `literature_synthesizer.v1` can receive business tools such as `library_read`, `document_read`, `citation_parser`, and `artifact_create` even though ReactSubagent currently resolves only registered harness callables.

This task fixes the team execution contract itself, not the UI symptom.

**Files:**

- Create: `backend/src/agents/lead_agent/v2/team/member_context.py`
- Create: `backend/src/agents/harness/business_tools.py`
- Modify: `backend/src/agents/lead_agent/v2/team/kernel.py`
- Modify: `backend/src/subagents/v2/types/react.py`
- Modify: `backend/src/agents/harness/langchain_adapter.py`
- Test: `backend/tests/agents/lead_agent/v2/test_team_member_context.py`
- Test: `backend/tests/agents/harness/test_business_tools.py`
- Test: `backend/tests/subagents/v2/test_react_business_tools.py`
- Docs: `docs/current/architecture.md`
- Docs: `docs/current/workspace-current-state.md`

- [ ] **Step 1: Add failing member-context tests**

Add tests proving `build_team_member_context()` produces a non-empty query and role-specific task package from raw user input:

```python
def test_research_scout_context_derives_query_from_raw_message() -> None:
    payload = build_team_member_context(
        brief=TaskBrief(
            capability_id="sci_literature_positioning",
            workspace_id="ws-1",
            raw_message="联邦学习结合大模型 (Federated Learning combined with Large Language Models)",
            brief={},
        ),
        capability_name="文献定位与创新点",
        template_id="research_scout.v1",
        display_role="文献检索员",
        blackboard=TeamBlackboard(mission_summary="文献定位与创新点"),
    )

    assert payload["query"] == "Federated Learning combined with Large Language Models"
    assert payload["raw_message"].startswith("联邦学习")
    assert payload["task_focus"]
    assert payload["workspace_id"] == "ws-1"
```

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_member_context.py::test_research_scout_context_derives_query_from_raw_message -q
```

Expected before implementation: fail because the helper does not exist.

- [ ] **Step 2: Implement `member_context.py` as a pure assembler**

The helper must:

- preserve explicit `brief.brief.topic/query/goal/raw_message` values when present.
- derive `query` from `query`, then `topic`, then English spans in `raw_message`, then compact raw message.
- attach `task_focus` based on template id only when the current payload lacks it.
- attach bounded `upstream_outputs` from `TeamBlackboard.phase_outputs`.
- never inject protected/internal `/workspace/.wenjin/**` or `/workspace/outputs/harness/**` refs.

Do not call DataService from this helper. TeamKernel passes already-loaded facts.

- [ ] **Step 3: Wire TeamKernel through the assembler**

Replace the body of `_build_member_brief()` in `backend/src/agents/lead_agent/v2/team/kernel.py` with a call to `build_team_member_context()`.

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_member_context.py tests/agents/lead_agent/v2/test_team_kernel.py -q
```

Expected: all selected tests pass, and existing TeamKernel tests still see `team_role`, `team_blackboard`, `capability_name`, `workspace_id`, and `raw_message`.

- [ ] **Step 4: Add failing business-tool resolution tests**

Add a ReactSubagent tool resolution test proving these tool names resolve to bounded callables instead of failing as forbidden:

```python
def test_react_resolves_business_tools_from_workspace_context() -> None:
    ctx = SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="",
        inputs={"raw_message": "test"},
        tools=["library_read", "document_read", "memory_read", "prism_read", "citation_parser"],
        workspace_data={
            "library": {"items": [{"title": "Paper A", "citation_key": "paper_a_2026"}]},
            "documents": [{"name": "notes.md", "excerpt": "method notes"}],
            "memory": [{"text": "prefer conservative claims"}],
            "prism": {"outline": ["Introduction"]},
        },
        capability_policy={},
        skill=None,
    )

    resolved = _resolve_tools(ctx.tools, ctx)
    assert {tool.name for tool in resolved} == {
        "library_read",
        "document_read",
        "memory_read",
        "prism_read",
        "citation_parser",
    }
```

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/subagents/v2/test_react_business_tools.py::test_react_resolves_business_tools_from_workspace_context -q
```

Expected before implementation: fail because only sandbox harness tools are resolved.

- [ ] **Step 5: Implement bounded business tools**

Create `backend/src/agents/harness/business_tools.py` with callables backed by `SubagentContext.workspace_data`:

- `library_read(query: str | None = None, limit: int = 20)` returns bounded Library summaries and citation keys.
- `document_read(query: str | None = None, limit: int = 10)` returns bounded document excerpts.
- `memory_read(query: str | None = None, limit: int = 10)` returns bounded workspace memory facts.
- `prism_read(section: str | None = None)` returns lightweight outline / protected section summary, not full manuscript text.
- `citation_parser(text: str)` extracts citation-like keys and DOI/URL-like tokens without fabricating sources.
- `artifact_create(title: str, markdown: str, kind: str = "review_report")` returns a staged artifact payload in the tool result only; it must not write canonical rooms directly.

Rules:

- All outputs use bounded previews and counts.
- No raw DataService calls inside the tool functions.
- No direct room commit, Prism apply, or canonical artifact materialization.
- Protected/internal workspace paths are filtered before returning.

- [ ] **Step 6: Register business tools in the existing adapter**

Extend `build_langchain_tools()` in `backend/src/agents/harness/langchain_adapter.py` so:

- sandbox tools continue to resolve through the existing sandbox registry.
- business tools resolve through `business_tools.py`.
- unknown tool names still fail explicitly.
- no plain-model fallback is introduced.

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/harness/test_business_tools.py tests/subagents/v2/test_react_business_tools.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Prove the SCI literature team no longer fails for the two known causes**

Add or extend a TeamKernel test using `sci_literature_positioning` policy/template inputs to assert:

- research scout receives a non-empty query from raw message.
- literature synthesizer receives resolvable tools.
- node metadata no longer includes `tool_forbidden` for business tool names.

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_kernel.py tests/subagents/v2/test_react_business_tools.py -q
```

Expected: selected tests pass.

Commit boundary:

```bash
git commit -m "fix: resolve team member context and business tools"
```

---

### Task 11: Make Workspace Sandbox Filesystem Useful for Long-Running Research Work

**Goal:** turn the current layout contract into a practical workspace filesystem that agents can reason about across tasks without seeing internal noise.

**Files:**

- Modify: `backend/src/sandbox/workspace_layout.py`
- Modify: `backend/src/agents/harness/context_assembly.py`
- Modify: `backend/src/agents/harness/sandbox_tools.py`
- Test: `backend/tests/sandbox/test_workspace_layout.py`
- Test: `backend/tests/agents/harness/test_context_assembly.py`
- Test: `backend/tests/agents/harness/test_sandbox_file_tools.py`
- Docs: `docs/current/workspace-current-state.md`

- [ ] **Step 1: Add layout readme/manifest tests**

Test that `ensure_workspace_sandbox_layout()` creates:

- `/workspace/main/README.md` if absent, with concise workspace-file guidance.
- `/workspace/datasets/.gitkeep`, `/workspace/scripts/.gitkeep`, `/workspace/outputs/.gitkeep`, `/workspace/reports/.gitkeep`.
- deterministic `.wenjin/manifest.json`.

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/sandbox/test_workspace_layout.py -q
```

- [ ] **Step 2: Implement stable workspace guidance files**

Keep the guidance short and operational:

- where to put datasets.
- where to write scripts.
- where to put generated outputs/reports.
- protected/internal paths agents must not touch.

Do not include user secrets, model config, or host paths.

- [ ] **Step 3: Expose file tree summaries in harness context**

Update `build_harness_context_bundle()` to include a bounded `workspace_file_summary`:

```json
{
  "visible_roots": ["/workspace/main", "/workspace/datasets", "/workspace/scripts", "/workspace/outputs", "/workspace/reports"],
  "recent_outputs": [],
  "recent_scripts": [],
  "truncated": false
}
```

The summary must be derived from already-loaded file facts or explicit caller input. It must not scan the filesystem inside the pure assembler.

- [ ] **Step 4: Verify file tools still hide internal state**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/sandbox/test_workspace_layout.py tests/agents/harness/test_context_assembly.py tests/agents/harness/test_sandbox_file_tools.py -q
```

Commit boundary:

```bash
git commit -m "feat: clarify workspace sandbox file contract"
```

---

### Task 12: Add Codex-Style Command Policy Without Adding Generic Shell

**Goal:** borrow Codex's command-policy discipline while staying inside Wenjin's task-specific Python/sandbox tools.

**Files:**

- Modify: `backend/src/agents/harness/command_audit.py`
- Modify: `backend/src/agents/lead_agent/v2/sandbox_job_runner.py`
- Modify: `backend/src/agents/lead_agent/v2/sandbox_environment_installer.py`
- Test: `backend/tests/agents/harness/test_command_audit.py`
- Test: `backend/tests/agents/harness/test_scheduler_and_python_tool.py`
- Docs: `docs/current/architecture.md`

- [ ] **Step 1: Add policy decision tests**

Test these classifications:

- `python /workspace/scripts/analysis.py` under `/workspace` is allowed.
- dependency installation is allowed only for normalized package specs.
- `curl`, `wget`, `ssh`, `scp`, `docker`, `sudo`, shell redirection to protected paths, and host absolute paths are forbidden.
- policy decision and reason are recorded in command audit metadata.

- [ ] **Step 2: Implement command policy as audit-first guard**

Extend command audit with:

```json
{
  "schema": "wenjin.harness.command_policy_decision.v1",
  "decision": "allow|forbid",
  "reason": "workspace_python|dependency_install|network_forbidden|host_path_forbidden",
  "command_preview": "python /workspace/scripts/analysis.py"
}
```

Do not expose a generic `sandbox.run_command` tool. This policy only guards Wenjin-owned Python/install/smoke jobs.

- [ ] **Step 3: Run verification**

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/harness/test_command_audit.py tests/agents/harness/test_scheduler_and_python_tool.py -q
```

Commit boundary:

```bash
git commit -m "feat: add harness command policy audit"
```

---

### Task 13: Add DeerFlow-Style Run Journal Signals Inside Existing Execution Events

**Goal:** learn from DeerFlow's run manager/journal idea, but keep `ExecutionRecord` and `ExecutionNodeRecord` as Wenjin's only execution facts.

**Files:**

- Modify: `backend/src/agents/harness/events.py`
- Modify: `backend/src/agents/lead_agent/v2/team/kernel.py`
- Modify: `backend/src/services/execution_event_publisher.py`
- Test: `backend/tests/agents/harness/test_events.py`
- Test: `backend/tests/agents/lead_agent/v2/test_team_kernel.py`
- Test: `frontend/tests/unit/lib/execution-run-view.test.ts`

- [ ] **Step 1: Add journal event schema tests**

Expected event payload:

```json
{
  "schema": "wenjin.harness.journal_event.v1",
  "phase": "member_started|tool_started|tool_completed|member_completed|quality_gate",
  "member": {"id": "team.1.research_scout_v1.1", "display_name": "文献检索员"},
  "summary": "文献检索员开始检索来源",
  "debug_ref": null
}
```

- [ ] **Step 2: Publish concise journal events through existing execution event path**

Keep this as a product-facing summary stream:

- no new run table.
- no second frontend subscription.
- raw tool args/logs remain in node detail/debug payloads.

- [ ] **Step 3: Update frontend projection only through `execution-run-view.ts`**

Run:

```bash
cd /Users/ze/wenjin/frontend
npx vitest run tests/unit/lib/execution-run-view.test.ts
```

Commit boundary:

```bash
git commit -m "feat: summarize harness run journal events"
```

---

### Task 14: Docker Browser E2E for the Harness User Journey

**Goal:** verify the full product loop after the member-context/business-tool fixes.

**Files:**

- Modify only if regressions are found.
- Test/docs update only when behavior changes.

- [ ] **Step 1: Rebuild stack**

```bash
cd /Users/ze/wenjin
docker compose -f docker-compose.yml -f docker-compose.local-build.yml up -d --build frontend gateway worker
docker compose ps
```

Expected: all core services healthy.

- [ ] **Step 2: Browser-test Workbench team task**

Use `http://localhost:2026`:

- confirm logged-in session survives Workbench/Prism switches.
- launch `文献定位与创新点` with raw text only.
- verify `research_scout` query is non-empty in node detail/debug.
- verify `literature_synthesizer` no longer fails because of unresolved business tools.
- verify LiveWorkflowPanel shows member names, quality gates, artifacts/review actions, not raw JSON.

- [ ] **Step 3: Browser-test Prism task continuity**

- open Prism.
- compile and open PDF contrast.
- trigger AI 改稿.
- confirm the panel does not auto-open from compile, does not block editing, and uses product-facing copy.

- [ ] **Step 4: Fix regressions with tests**

Only make code changes for reproducible bugs. Every fix needs a targeted backend/frontend test before another browser pass.

Commit boundary:

```bash
git commit -m "fix: stabilize native harness browser flow"
```

---

### Task 15: Final Standing-Alone Harness Audit

**Goal:** decide honestly whether Wenjin's harness is independent enough for the next product milestone.

**Files:**

- Docs:
  - `docs/current/architecture.md`
  - `docs/current/workspace-current-state.md`
  - `docs/current/frontend-feature-plugin-contract.md`
  - `docs/superpowers/specs/2026-06-06-wenjin-native-agent-harness-design.md`

- [ ] **Step 1: External-reference regression scan**

```bash
cd /Users/ze/wenjin
rg "codex|cc-switch|ccswitch|deer-flow|deerflow|Codex SDK|sandbox\\.run_command" backend/src frontend -n
```

Expected: no production dependency/reference except intentional documentation.

- [ ] **Step 2: Full targeted verification**

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/harness tests/agents/lead_agent/v2 tests/subagents/v2 tests/integration/test_harness_mock_sandbox_e2e.py -q
.venv/bin/ruff check src/agents/harness src/agents/lead_agent/v2 src/subagents/v2 tests/agents/harness tests/agents/lead_agent/v2 tests/subagents/v2

cd /Users/ze/wenjin/frontend
npm run typecheck
npx vitest run tests/unit/lib/execution-run-view.test.ts tests/unit/v2/live-workflow-view-model.test.ts tests/unit/stores/execution-store.test.ts

cd /Users/ze/wenjin
git diff --check
```

- [ ] **Step 3: Write final audit**

The audit must answer:

- Which Codex patterns were adopted: command policy, approval-style audit, bounded tool output, session facts, explicit unresolved-tool failure.
- Which DeerFlow patterns were adopted: sandbox filesystem, skill/tool declarative contracts, run journal, middleware-like bounded context.
- Which Wenjin-specific choices remain different: one workspace/one sandbox, capability DataService SSOT, review-first artifacts, Prism/rooms integration.
- Remaining weaknesses by severity, especially model reliability, source quality, tool latency, sandbox install experience, and frontend complexity.

Commit boundary:

```bash
git commit -m "docs: audit native harness convergence"
```

Do not call the active goal complete unless Task 10 through Task 15 are verified, browser-tested, and the final audit has no unresolved P0/P1 gaps.

## Review Checklist After Each Task

Use this checklist before every commit:

- The change stays inside current Wenjin execution architecture.
- No new compatibility layer, fallback router, or second runtime source of truth.
- File paths use `/workspace` virtual paths only.
- Protected/internal paths are blocked at the tool boundary, not just hidden in prompts.
- Large outputs are bounded or externalized.
- Recoverable tool failures remain structured and do not abort the agent loop.
- User-facing UX receives concise summaries; debug-only payloads stay collapsed.
- Tests include at least one regression for the behavior being added.
- Docs describe the behavior as implemented, not as aspiration.

## Final Verification Before Merge

Run from `/Users/ze/wenjin`:

```bash
cd backend
.venv/bin/python -m pytest tests/ -q
.venv/bin/ruff check src tests
cd ../frontend
npm run typecheck
npx vitest run
cd ..
git diff --check
git status --short
```

Then run browser/Docker smoke for:

- Workbench task dispatch.
- Team real-name agent execution display.
- Sandbox-backed experiment task.
- Prism deep rewrite path if touched by context changes.
- Run history/detail drawer.

## Self-Review

Spec coverage:

- Codex/deer-flow learning is captured as borrowed concepts only: command contract, output budget, error recovery, loop guard, file evidence, and run journal style events.
- Current Wenjin architecture remains authoritative: ExecutionRecord/NodeRecord, DataService sandbox, TeamKernel, capability policy, review-first artifact staging.
- Workspace sandbox filesystem contract is explicitly included.
- Dynamic team/replan behavior is included through compact signals, not a new workflow engine.
- UX projection is included but intentionally constrained to the existing execution projection store.

Placeholder scan:

- No task relies on "TBD" or "implement later".
- Each task has exact files, expected contract, test command, and commit boundary.

Type/name consistency:

- `execution_manifest`, `failure_classification`, `sandbox_execution_summary`, and `replan_signal` are named consistently with existing `wenjin.harness.*.v1` schemas.
- Existing `file_change_summary` and `tool_failure_summary` remain unchanged and are extended by separate summaries rather than overloaded.
