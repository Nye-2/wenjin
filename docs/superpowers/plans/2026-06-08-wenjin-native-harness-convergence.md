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

Current uncommitted slice is Task 11, the workspace sandbox filesystem usability pass:

- `backend/src/sandbox/workspace_layout.py`
- `backend/src/agents/harness/context_assembly.py`
- `backend/tests/sandbox/test_workspace_layout.py`
- `backend/tests/agents/harness/test_context_assembly.py`
- `docs/current/workspace-current-state.md`
- `docs/superpowers/plans/2026-06-08-wenjin-native-harness-convergence.md`

This slice makes the one-workspace sandbox easier for long-running research work:

- `ensure_workspace_sandbox_layout()` creates persistent user-facing guidance in `/workspace/main/README.md` without overwriting an existing README.
- The same layout initialization keeps `datasets`, `scripts`, `outputs`, and `reports` visible even when empty via `.gitkeep`.
- Harness context includes a bounded `workspace_file_summary` derived only from caller-provided facts, with protected/internal workspace refs filtered before entering model context.
- Context-budget trimming treats the file summary as optional context and removes it before exceeding `max_chars`.

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

- [x] **Step 1: Add failing member-context tests**

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

Observed red result: `ModuleNotFoundError: No module named 'src.agents.lead_agent.v2.team.member_context'`.

- [x] **Step 2: Implement `member_context.py` as a pure assembler**

The helper must:

- preserve explicit `brief.brief.topic/query/goal/raw_message` values when present.
- derive `query` from `query`, then `topic`, then English spans in `raw_message`, then compact raw message.
- attach `task_focus` based on template id only when the current payload lacks it.
- attach bounded `upstream_outputs` from `TeamBlackboard.phase_outputs`.
- never inject protected/internal `/workspace/.wenjin/**` or `/workspace/outputs/harness/**` refs.

Do not call DataService from this helper. TeamKernel passes already-loaded facts.

- [x] **Step 3: Wire TeamKernel through the assembler**

Replace the body of `_build_member_brief()` in `backend/src/agents/lead_agent/v2/team/kernel.py` with a call to `build_team_member_context()`.

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_member_context.py tests/agents/lead_agent/v2/test_team_kernel.py -q
```

Expected: all selected tests pass, and existing TeamKernel tests still see `team_role`, `team_blackboard`, `capability_name`, `workspace_id`, and `raw_message`.

Observed green result: `tests/agents/lead_agent/v2/test_team_member_context.py` passed, and the TeamKernel regression for SCI literature context passed.

- [x] **Step 4: Add failing business-tool resolution tests**

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

Observed red result: `React tools were requested but forbidden by harness policy: library_read, document_read, memory_read, prism_read, citation_parser, artifact_create`.

- [x] **Step 5: Implement bounded business tools**

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

- [x] **Step 6: Register business tools in the existing adapter**

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

Observed green result: `tests/agents/harness/test_business_tools.py` and `tests/subagents/v2/test_react_business_tools.py` passed. Additional red/green test added to ensure business tool calls append `_harness_tool_records` for node evidence.

- [x] **Step 7: Prove the SCI literature team no longer fails for the two known causes**

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

Observed green result:

```text
tests/agents/lead_agent/v2/test_team_member_context.py
tests/agents/lead_agent/v2/test_team_kernel.py
tests/agents/lead_agent/v2/test_team_quality_gates.py
tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py
tests/agents/harness/test_business_tools.py
tests/agents/harness/test_langchain_adapter.py
tests/subagents/v2/test_react_business_tools.py
tests/subagents/v2/test_registry.py
56 passed
```

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

- [x] **Step 1: Add layout readme/manifest tests**

Test that `ensure_workspace_sandbox_layout()` creates:

- `/workspace/main/README.md` if absent, with concise workspace-file guidance.
- `/workspace/datasets/.gitkeep`, `/workspace/scripts/.gitkeep`, `/workspace/outputs/.gitkeep`, `/workspace/reports/.gitkeep`.
- deterministic `.wenjin/manifest.json`.

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/sandbox/test_workspace_layout.py -q
```

Observed red result: missing `/workspace/main/README.md`; `.gitkeep` files were not created.

- [x] **Step 2: Implement stable workspace guidance files**

Keep the guidance short and operational:

- where to put datasets.
- where to write scripts.
- where to put generated outputs/reports.
- protected/internal paths agents must not touch.

Do not include user secrets, model config, or host paths.

- [x] **Step 3: Expose file tree summaries in harness context**

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

Observed red result: `workspace_file_summary` key was absent from the context bundle. After implementation, an existing budget test exposed that `_fit_budget()` also needed to compact the new file-summary field.

- [x] **Step 4: Verify file tools still hide internal state**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/sandbox/test_workspace_layout.py tests/agents/harness/test_context_assembly.py tests/agents/harness/test_sandbox_file_tools.py -q
```

Observed green result:

```text
tests/sandbox/test_workspace_layout.py
tests/agents/harness/test_context_assembly.py
tests/agents/harness/test_sandbox_file_tools.py
42 passed
```

- [x] **Step 5: Run fresh verification before commit**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/sandbox/test_workspace_layout.py tests/agents/harness/test_context_assembly.py tests/agents/harness/test_sandbox_file_tools.py -q
.venv/bin/ruff check src/sandbox/workspace_layout.py src/agents/harness/context_assembly.py tests/sandbox/test_workspace_layout.py tests/agents/harness/test_context_assembly.py
cd /Users/ze/wenjin
git diff --check
```

Observed result:

```text
pytest: 42 passed
ruff: All checks passed!
git diff --check: no output
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

- [x] **Step 1: Add policy decision tests**

Test these classifications:

- `python /workspace/scripts/analysis.py` under `/workspace` is allowed.
- dependency installation is allowed only for normalized package specs.
- `curl`, `wget`, `ssh`, `scp`, `docker`, `sudo`, shell redirection to protected paths, and host absolute paths are forbidden.
- policy decision and reason are recorded in command audit metadata.

Observed red result:

```text
tests/agents/harness/test_command_audit.py
14 failed, 6 passed
```

The failures showed missing `policy_decision`, unblocked `curl/wget/ssh/scp`, unblocked protected/internal workspace paths, and unblocked unsafe pip specs.

- [x] **Step 2: Implement command policy as audit-first guard**

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

- [x] **Step 3: Run verification**

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/harness/test_command_audit.py tests/agents/harness/test_scheduler_and_python_tool.py -q
```

Additional guard verification:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_sandbox_runtime.py::test_run_python_script_blocks_forbidden_command_policy_before_job -q
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_sandbox_runtime.py -q
.venv/bin/ruff check src/agents/harness/command_audit.py src/agents/lead_agent/v2/sandbox_job_runner.py src/agents/lead_agent/v2/sandbox_environment_installer.py tests/agents/harness/test_command_audit.py tests/agents/lead_agent/v2/test_sandbox_runtime.py
```

Observed green result:

```text
test_command_audit + test_scheduler_and_python_tool: 30 passed
test_sandbox_runtime: 19 passed
ruff: All checks passed!
```

- [x] **Step 4: Run fresh verification before commit**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/harness/test_command_audit.py tests/agents/harness/test_scheduler_and_python_tool.py tests/agents/lead_agent/v2/test_sandbox_runtime.py -q
.venv/bin/ruff check src/agents/harness/command_audit.py src/agents/lead_agent/v2/sandbox_job_runner.py src/agents/lead_agent/v2/sandbox_environment_installer.py tests/agents/harness/test_command_audit.py tests/agents/lead_agent/v2/test_sandbox_runtime.py
cd /Users/ze/wenjin
git diff --check
```

Observed result:

```text
pytest: 49 passed
ruff: All checks passed!
git diff --check: no output
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
- Modify: `backend/src/agents/harness/diff_tracker.py`
- Modify: `frontend/lib/execution-run-view.ts`
- Test: `backend/tests/agents/harness/test_events.py`
- Test: `backend/tests/agents/lead_agent/v2/test_team_kernel.py`
- Test: `frontend/tests/unit/lib/execution-run-view.test.ts`

- [x] **Step 1: Add journal event schema tests**

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

Observed red result:

```text
test_events: missing journal envelope
test_team_kernel: missing node_metadata.harness.run_journal_summary
execution-run-view: ignored run_journal_summary.summary
```

- [x] **Step 2: Publish concise journal events through existing execution event path**

Keep this as a product-facing summary stream:

- no new run table.
- no second frontend subscription.
- raw tool args/logs remain in node detail/debug payloads.

- [x] **Step 3: Update frontend projection only through `execution-run-view.ts`**

Run:

```bash
cd /Users/ze/wenjin/frontend
npx vitest run tests/unit/lib/execution-run-view.test.ts
```

Observed green result:

```text
backend: test_events + test_output_budget_loop_guard_and_diff_tracker + test_team_kernel => 32 passed
frontend: execution-run-view.test.ts => 13 passed
frontend typecheck: passed
ruff: All checks passed!
```

- [x] **Step 4: Run fresh verification before commit**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/harness/test_events.py tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py tests/agents/lead_agent/v2/test_team_kernel.py -q
.venv/bin/ruff check src/agents/harness/events.py src/agents/harness/diff_tracker.py tests/agents/harness/test_events.py tests/agents/lead_agent/v2/test_team_kernel.py
cd /Users/ze/wenjin/frontend
npx vitest run tests/unit/lib/execution-run-view.test.ts
npm run typecheck
cd /Users/ze/wenjin
git diff --check
```

Observed result:

```text
backend pytest: 32 passed
ruff: All checks passed!
frontend vitest: 13 passed
frontend typecheck: passed
git diff --check: no output
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

- [x] **Step 1: Rebuild stack**

```bash
cd /Users/ze/wenjin
docker compose -f docker-compose.yml -f docker-compose.local-build.yml up -d --build frontend gateway worker
docker compose ps
```

Expected: all core services healthy.

- [x] **Step 2: Browser-test Workbench team task**

Use `http://localhost:2026`:

- confirm logged-in session survives Workbench/Prism switches.
- launch `文献定位与创新点` with raw text only.
- verify `research_scout` query is non-empty in node detail/debug.
- verify `literature_synthesizer` no longer fails because of unresolved business tools.
- verify LiveWorkflowPanel shows member names, quality gates, artifacts/review actions, not raw JSON.

Observed 2026-06-08:

- Docker local-build stack rebuilt successfully; frontend production build and TypeScript passed inside Docker.
- `docker compose ps` showed dataservice, frontend, gateway, and worker healthy; `http://localhost:2026` and `/api/models?purpose=chat` responded.
- Browser verified logged-in workspace did not redirect to login after reload.
- Workbench showed launch receipt and completed `文献定位与创新点` result card with 20 literature items, 1 document output, 1 memory item, and pending review actions.
- Browser regression found a projection bug: TeamKernel progress showed `5/8` while every process step was `待处理`, and synthetic `team_template_*` nodes appeared as vague `工作步骤`.
- Fixed with tests: TeamKernel graph now keeps member templates out of progress nodes, RunView derives five-step progress from team member / quality gate / run status, and quality gates are deduplicated by gate id for default team display.
- Browser re-test verified progress now shows five steps: `准备上下文` completed, `组建团队` completed, `成员执行` partial, `质量闭环` partial, `整理结果` completed; no raw tool JSON appears in default view.

- [x] **Step 3: Browser-test Prism task continuity**

- open Prism.
- compile and open PDF contrast.
- trigger AI 改稿.
- confirm the panel does not auto-open from compile, does not block editing, and uses product-facing copy.

Observed 2026-06-08:

- Browser opened `/workspaces/{workspace_id}/prism` without login redirect.
- Compile did not auto-open AI assist; it opened PDF contrast and changed the state copy to `正在显示 PDF 对照`.
- Browser regression found the floating AI entry became only `待应用修改` when pending changes existed, hiding the AI rewrite affordance.
- Fixed with test: the floating entry keeps `AI 改稿` as the main label and appends state as `AI 改稿，待应用修改`.
- Browser re-test verified clicking the floating entry opens the `AI 改稿` dialog; the dialog uses product-facing copy and keeps pending writes in the review queue.

- [x] **Step 4: Fix regressions with tests**

Only make code changes for reproducible bugs. Every fix needs a targeted backend/frontend test before another browser pass.

Regression tests added:

- `backend/tests/agents/lead_agent/v2/test_team_kernel.py::test_team_panel_graph_keeps_member_templates_out_of_progress_steps`
- `frontend/tests/unit/lib/execution-run-view.test.ts` team progress projection and quality gate dedupe cases

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

- [x] **Step 1: External-reference regression scan**

```bash
cd /Users/ze/wenjin
rg "codex|cc-switch|ccswitch|deer-flow|deerflow|Codex SDK|sandbox\\.run_command" backend/src frontend -n
```

Expected: no production dependency/reference except intentional documentation.

Observed 2026-06-08: production scan returned no matches in `backend/src` or `frontend` for Codex SDK, cc-switch, deer-flow runtime, or `sandbox.run_command`.

- [x] **Step 2: Full targeted verification**

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

- [x] **Step 3: Write final audit**

The audit must answer:

- Which Codex patterns were adopted: command policy, approval-style audit, bounded tool output, session facts, explicit unresolved-tool failure.
- Which DeerFlow patterns were adopted: sandbox filesystem, skill/tool declarative contracts, run journal, middleware-like bounded context.
- Which Wenjin-specific choices remain different: one workspace/one sandbox, capability DataService SSOT, review-first artifacts, Prism/rooms integration.
- Remaining weaknesses by severity, especially model reliability, source quality, tool latency, sandbox install experience, and frontend complexity.

Observed 2026-06-08:

- Backend targeted pytest: 269 passed.
- Backend targeted ruff: all checks passed.
- Frontend typecheck: passed.
- Frontend targeted vitest: 37 passed.
- Docker browser smoke covered Workbench team task, TeamKernel five-step progress, quality gate dedupe, Prism compile/PDF contrast, and Prism AI assist discoverability.

Final audit written to `docs/current/native-harness-convergence-audit.md` and linked from `docs/current/documentation-map.md`.

Commit boundary:

```bash
git commit -m "docs: audit native harness convergence"
```

Do not call the active goal complete unless Task 10 through Task 16 are verified, browser-tested where relevant, and the final audit has no unresolved P0/P1 gaps.

---

### Task 16: Add Sandbox Experiment Reproducibility Evidence

**Goal:** make every `sandbox.run_python` experiment leave enough bounded evidence for a user, Lead Agent, or future team member to understand what ran, where it ran, what environment/dependencies were used, what artifacts appeared, and whether the run is reproducible.

**Architecture:** extend the existing `execution_manifest` and `sandbox_execution_summary` path only. Do not create a new harness runtime, table, event stream, frontend store, or generic command tool. The evidence should remain attached to `HarnessToolResult.structured_payload`, LangChain tool-call metadata, `ExecutionNodeRecord.node_metadata.harness`, and existing run journal projection.

**External reference patterns being adopted:**

- From Codex: explicit command/session policy shape, bounded stdout/stderr, audit trail, sandbox policy as part of execution evidence.
- From DeerFlow: predictable output roots, artifact-aware run reports, skill/task outputs that are readable by the next agent.
- Wenjin-specific constraint: one workspace has one active sandbox; `/workspace` virtual paths are the only user-facing paths.

**Files:**

- Modify: `backend/src/agents/harness/sandbox_execution_tools.py`
- Modify: `backend/src/agents/harness/langchain_adapter.py`
- Modify: `backend/src/agents/harness/diff_tracker.py`
- Modify: `backend/src/agents/harness/context_assembly.py`
- Test: `backend/tests/agents/harness/test_scheduler_and_python_tool.py`
- Test: `backend/tests/agents/harness/test_langchain_adapter.py`
- Test: `backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py`
- Test: `backend/tests/agents/harness/test_context_assembly.py`
- Test: `backend/tests/agents/lead_agent/v2/test_runtime.py`
- Docs: `docs/current/native-harness-convergence-audit.md`
- Docs: `docs/current/workspace-current-state.md`
- Docs: `docs/superpowers/specs/2026-06-06-wenjin-native-agent-harness-design.md`
- Docs: `docs/superpowers/plans/2026-06-08-wenjin-native-harness-convergence.md`

- [x] **Step 1: Write failing tool-result reproducibility manifest test**

Add this test to `backend/tests/agents/harness/test_scheduler_and_python_tool.py`:

```python
@pytest.mark.asyncio
async def test_run_python_returns_reproducibility_manifest() -> None:
    class ArtifactRunner:
        async def run_python_script(self, **kwargs):
            return {
                "status": "completed",
                "stdout": "{\"ok\": true}",
                "stderr": "",
                "parsed_stdout": {"ok": True},
                "sandbox_environment_id": "env-1",
                "sandbox_job_id": "job-1",
                "script_name": kwargs["script_name"],
                "script_path": f"/workspace/scripts/{kwargs['script_name']}",
                "dependency_hints": ["pandas", "numpy"],
                "generated_artifacts": [
                    {
                        "path": "/workspace/reports/analysis.md",
                        "name": "analysis.md",
                        "kind": "markdown",
                        "size_bytes": 128,
                    }
                ],
                "command_audit": {
                    "verdict": "pass",
                    "risk_level": "low",
                    "reasons": [],
                    "command": {
                        "argv": [
                            "/workspace/.wenjin/env/python/bin/python",
                            "/workspace/scripts/analysis.py",
                        ],
                        "shell_command": None,
                        "cwd": "/workspace",
                        "env": {},
                        "network_profile": "none",
                        "timeout_seconds": 30,
                        "output_bytes_cap": 20000,
                    },
                },
                "install_job_ids": ["install-1"],
                "install_command_audits": [
                    {
                        "verdict": "pass",
                        "risk_level": "low",
                        "reasons": [],
                        "command": {
                            "argv": [
                                "/workspace/.wenjin/env/python/bin/python",
                                "-m",
                                "pip",
                                "install",
                                "pandas",
                                "numpy",
                            ],
                            "shell_command": None,
                            "cwd": "/workspace",
                            "env": {},
                            "network_profile": "package_install",
                            "timeout_seconds": 120,
                            "output_bytes_cap": 20000,
                        },
                    }
                ],
            }

    tool = SandboxExecutionTools(
        context=_ctx(),
        policy=HarnessPolicy(
            permissions=frozenset({"sandbox.run_python"}),
            allow_package_install=True,
            max_sandbox_seconds=60,
        ),
        runner=ArtifactRunner(),
        scheduler=WorkspaceToolScheduler(),
    )

    result = await tool.run_python(
        script="print({'ok': True})",
        script_name="analysis.py",
        dependency_hints=["pandas", "numpy"],
    )

    manifest = result.structured_payload["reproducibility_manifest"]
    assert manifest == {
        "schema": "wenjin.harness.run_python.reproducibility_manifest.v1",
        "tool": "sandbox.run_python",
        "workspace_id": "ws-1",
        "execution_id": "exec-1",
        "node_id": "node-1",
        "invocation_id": "invocation-1",
        "script": {
            "name": "analysis.py",
            "path": "/workspace/scripts/analysis.py",
        },
        "sandbox": {
            "environment_id": "env-1",
            "run_job_id": "job-1",
            "install_job_ids": ["install-1"],
            "network_profile": "none",
            "timeout_seconds": 30,
        },
        "dependencies": {
            "requested": ["pandas", "numpy"],
            "installed": ["pandas", "numpy"],
        },
        "artifacts": [
            {
                "path": "/workspace/reports/analysis.md",
                "name": "analysis.md",
                "kind": "markdown",
                "size_bytes": 128,
            }
        ],
        "command_audit": {
            "run_verdict": "pass",
            "run_risk_level": "low",
            "install_verdicts": ["pass"],
            "install_risk_levels": ["low"],
        },
    }
```

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/harness/test_scheduler_and_python_tool.py::test_run_python_returns_reproducibility_manifest -q
```

Expected before implementation:

```text
KeyError: 'reproducibility_manifest'
```

- [x] **Step 2: Implement bounded reproducibility manifest on `sandbox.run_python`**

In `backend/src/agents/harness/sandbox_execution_tools.py`, add a helper beside `_execution_manifest()` and call it after `execution_manifest` is built:

```python
payload["reproducibility_manifest"] = _reproducibility_manifest(
    context=self.context,
    execution_manifest=payload["execution_manifest"],
    payload=payload,
)
```

The helper must:

- use only `/workspace` virtual paths, not host paths.
- include no raw stdout/stderr, environment variables, API keys, or shell text.
- cap artifact records to 20.
- cap dependency names to 50.
- summarize command audits as verdict/risk only.
- keep install evidence optional so no-install runs still have a valid manifest.

Target helper shape:

```python
def _reproducibility_manifest(
    *,
    context: HarnessRunContext,
    execution_manifest: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "wenjin.harness.run_python.reproducibility_manifest.v1",
        "tool": "sandbox.run_python",
        "workspace_id": context.workspace_id,
        "execution_id": context.execution_id,
        "node_id": context.node_id,
        "invocation_id": context.invocation_id,
        "script": {
            "name": str(execution_manifest.get("script_name") or ""),
            "path": _workspace_path(execution_manifest.get("script_path")),
        },
        "sandbox": {
            "environment_id": str(execution_manifest.get("sandbox_environment_id") or ""),
            "run_job_id": str(execution_manifest.get("sandbox_job_id") or ""),
            "install_job_ids": _string_list(payload.get("install_job_ids"), limit=20),
            "network_profile": str(execution_manifest.get("network_profile") or "none"),
            "timeout_seconds": _positive_int(execution_manifest.get("timeout_seconds")),
        },
        "dependencies": {
            "requested": _dependency_hints(execution_manifest.get("dependency_hints")),
            "installed": _dependency_hints(payload.get("installed_packages")),
        },
        "artifacts": _artifact_manifest(payload.get("generated_artifacts")),
        "command_audit": _command_audit_manifest(
            payload.get("command_audit"),
            payload.get("install_command_audits"),
        ),
    }
```

- [x] **Step 3: Keep LangChain metadata aligned**

Add a failing assertion to `backend/tests/agents/harness/test_langchain_adapter.py` so completed `sandbox.run_python` tool-call metadata includes:

```python
assert metadata["reproducibility_manifest"]["schema"] == (
    "wenjin.harness.run_python.reproducibility_manifest.v1"
)
assert metadata["reproducibility_manifest"]["sandbox"]["run_job_id"] == "job-1"
```

Then update `backend/src/agents/harness/langchain_adapter.py` so `_command_audit_metadata()` or the existing structured-payload metadata extraction copies `reproducibility_manifest` the same way it already copies `execution_manifest`.

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/harness/test_langchain_adapter.py -q
```

Expected after implementation: all selected adapter tests pass.

- [x] **Step 4: Add node-level reproducibility summary without adding a new record type**

Add this test to `backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py`:

```python
def test_harness_node_metadata_includes_reproducibility_summary() -> None:
    metadata = build_harness_node_metadata_from_tool_calls(
        [
            {
                "name": "sandbox.run_python",
                "status": "completed",
                "reproducibility_manifest": {
                    "schema": "wenjin.harness.run_python.reproducibility_manifest.v1",
                    "tool": "sandbox.run_python",
                    "workspace_id": "ws-1",
                    "execution_id": "exec-1",
                    "node_id": "node-1",
                    "invocation_id": "invocation-1",
                    "script": {
                        "name": "analysis.py",
                        "path": "/workspace/scripts/analysis.py",
                    },
                    "sandbox": {
                        "environment_id": "env-1",
                        "run_job_id": "job-1",
                        "install_job_ids": ["install-1"],
                        "network_profile": "none",
                        "timeout_seconds": 30,
                    },
                    "dependencies": {
                        "requested": ["pandas"],
                        "installed": ["pandas"],
                    },
                    "artifacts": [
                        {
                            "path": "/workspace/reports/analysis.md",
                            "name": "analysis.md",
                            "kind": "markdown",
                            "size_bytes": 128,
                        }
                    ],
                    "command_audit": {
                        "run_verdict": "pass",
                        "run_risk_level": "low",
                        "install_verdicts": ["pass"],
                        "install_risk_levels": ["low"],
                    },
                },
            }
        ]
    )

    summary = metadata["harness"]["reproducibility_summary"]
    assert summary == {
        "schema": "wenjin.harness.reproducibility_summary.v1",
        "python_runs": 1,
        "manifest_count": 1,
        "script_paths": ["/workspace/scripts/analysis.py"],
        "artifact_paths": ["/workspace/reports/analysis.md"],
        "dependency_names": ["pandas"],
        "sandbox_environment_ids": ["env-1"],
        "sandbox_job_ids": ["job-1"],
        "install_job_ids": ["install-1"],
        "command_risk_levels": ["low"],
    }
```

Implement `build_reproducibility_summary_from_tool_calls()` in `backend/src/agents/harness/diff_tracker.py` and call it from `build_harness_node_metadata_from_tool_calls()`. Keep the summary compact:

- max 20 script paths.
- max 50 artifact paths.
- max 50 dependency names.
- max 20 job/environment ids.
- no raw command argv.
- no stdout/stderr.

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py::test_harness_node_metadata_includes_reproducibility_summary -q
```

Expected after implementation: pass.

- [x] **Step 5: Include reproducibility in bounded team context**

Add or extend a test in `backend/tests/agents/harness/test_context_assembly.py` verifying that when prior node metadata contains `harness.reproducibility_summary`, the assembled context includes a short `reproducibility_summary` entry and drops it under budget before core task fields.

Expected context fragment:

```python
assert context["previous_execution_context"]["reproducibility_summary"] == {
    "python_runs": 1,
    "manifest_count": 1,
    "script_paths": ["/workspace/scripts/analysis.py"],
    "artifact_paths": ["/workspace/reports/analysis.md"],
    "dependency_names": ["pandas"],
}
```

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/harness/test_context_assembly.py -q
```

Expected after implementation: all selected context tests pass.

- [x] **Step 6: Verify Lead runtime node metadata persists the new summary**

Add or extend one runtime test in `backend/tests/agents/lead_agent/v2/test_runtime.py` so a completed harness node event records:

```python
node_metadata = completed[-1]["node_metadata"]
assert node_metadata["harness"]["reproducibility_summary"]["manifest_count"] == 1
assert node_metadata["harness"]["reproducibility_summary"]["script_paths"] == [
    "/workspace/scripts/analysis.py"
]
```

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_runtime.py::test_node_recording_adds_harness_sandbox_execution_summary_metadata -q
```

Expected after implementation: pass with the existing node recording path; no new runtime persistence code should be necessary unless the adapter metadata is incomplete.

- [x] **Step 7: Update docs to make the contract explicit**

Update:

- `docs/current/workspace-current-state.md`
- `docs/current/native-harness-convergence-audit.md`
- `docs/superpowers/specs/2026-06-06-wenjin-native-agent-harness-design.md`

Required wording:

- `sandbox.run_python` returns both `execution_manifest` and `reproducibility_manifest`.
- `execution_manifest` is the run identity contract.
- `reproducibility_manifest` is the bounded evidence contract for script, dependencies, sandbox job/environment, generated artifacts, and command audit risk.
- `reproducibility_summary` is node-level metadata for Lead/team context and run review.
- This does not introduce a generic shell or Codex/deer-flow dependency.

- [x] **Step 8: Run targeted verification**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/harness/test_scheduler_and_python_tool.py tests/agents/harness/test_langchain_adapter.py tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py tests/agents/harness/test_context_assembly.py tests/agents/lead_agent/v2/test_runtime.py -q
.venv/bin/ruff check src/agents/harness tests/agents/harness tests/agents/lead_agent/v2/test_runtime.py
cd /Users/ze/wenjin
git diff --check
```

Expected:

```text
pytest: all selected tests pass
ruff: All checks passed!
git diff --check: no output
```

- [x] **Step 9: Commit the slice**

Run:

```bash
cd /Users/ze/wenjin
git status --short
git add backend/src/agents/harness/sandbox_execution_tools.py backend/src/agents/harness/langchain_adapter.py backend/src/agents/harness/diff_tracker.py backend/src/agents/harness/context_assembly.py backend/tests/agents/harness/test_scheduler_and_python_tool.py backend/tests/agents/harness/test_langchain_adapter.py backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py backend/tests/agents/harness/test_context_assembly.py backend/tests/agents/lead_agent/v2/test_runtime.py docs/current/native-harness-convergence-audit.md docs/current/workspace-current-state.md docs/superpowers/specs/2026-06-06-wenjin-native-agent-harness-design.md docs/superpowers/plans/2026-06-08-wenjin-native-harness-convergence.md
git commit -m "feat: add sandbox reproducibility evidence"
```

Expected: one clean commit for reproducibility evidence only.

**Stop condition for this task:** do not expand into `sandbox.run_command`, frontend UI redesign, new sandbox lifecycle policy, or model-routing work. If the tests reveal a real integration issue, fix only the existing `sandbox.run_python`/adapter/node-metadata path.

---

### Task 17: Make Sandbox Python Reports User-Readable

**Goal:** turn existing sandbox `report_markdown` into a readable experiment handoff that explains how to reproduce the run and what to do when dependency installation fails.

**Architecture:** keep the report inside the existing Lead-owned `SandboxArtifactCollector` / installer output path. Do not add a new report table, new review item kind, frontend stream, or generic shell command surface.

**External reference patterns adopted:**

- From Codex: keep command/policy evidence summarized, not dumped as raw argv or environment.
- From deer-flow: present generated output paths as a concise user-facing artifact section.
- Wenjin-specific constraint: use `/workspace` paths, existing `report_markdown`, and DataService sandbox jobs only.

**Files:**

- Modify: `backend/src/agents/lead_agent/v2/sandbox_artifact_collector.py`
- Modify: `backend/src/agents/lead_agent/v2/sandbox_environment_installer.py`
- Test: `backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py`
- Docs: `docs/current/native-harness-convergence-audit.md`
- Docs: `docs/current/workspace-current-state.md`
- Docs: `docs/superpowers/specs/2026-06-06-wenjin-native-agent-harness-design.md`
- Docs: `docs/superpowers/plans/2026-06-08-wenjin-native-harness-convergence.md`

- [x] **Step 1: Add failing report tests**

Added tests requiring successful Python runs with dependency installation to include:

```text
## Reproducibility
Script path
Requested dependencies
Installed dependencies
Install job ids
Retry count
Run command audit
```

Added tests requiring dependency-install failure output to include:

```text
## Recovery guidance
Dependency installation failed before the Python script could be retried.
Check dependency_hints for a valid pinned package spec
Install job ids
```

Verified both tests failed before implementation.

- [x] **Step 2: Implement report sections in the existing collector path**

`SandboxArtifactCollector.script_output()` now appends a bounded Reproducibility section to `report_markdown` with script path, dependency hints, installed packages, install job ids, retry count, run/install command audit risk summaries, and reviewable artifact paths.

The report intentionally excludes raw command argv, environment variables, API keys, host paths, and protected/internal refs.

- [x] **Step 3: Add dependency-install failure reports**

`SandboxEnvironmentInstaller.install_dependencies()` now includes bounded `report_markdown` in `SandboxCommandExecutionError.output` when pip install fails. The report includes requested packages, run/install job ids, exit code, stdout/stderr, and recovery guidance.

- [x] **Step 4: Update docs**

Updated current state, convergence audit, and harness design spec to state that `report_markdown` now includes human-readable reproducibility evidence and install-failure recovery guidance.

- [x] **Step 5: Verify**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_sandbox_runtime.py tests/agents/harness/test_scheduler_and_python_tool.py -q
.venv/bin/ruff check src/agents/lead_agent/v2/sandbox_artifact_collector.py src/agents/lead_agent/v2/sandbox_environment_installer.py tests/agents/lead_agent/v2/test_sandbox_runtime.py
```

Observed:

```text
29 passed
All checks passed!
```

---

### Task 18: Add Dataset Provenance to the Workspace Sandbox Contract

**Goal:** make the `/workspace/datasets` filesystem contract explicit enough for long-running experiments to keep track of reusable data inputs and let later team members see bounded dataset provenance.

**Architecture:** keep dataset provenance inside the existing workspace layout and harness context bundle. Do not add a new runtime, table, frontend stream, or sandbox reader. Context assembly only projects caller-provided facts.

**External reference patterns adopted:**

- From Codex: summarize sandbox-visible filesystem permissions and hide internal/protected roots.
- From deer-flow: only treat deliberately scoped virtual paths as deliverable or attachable; reject paths outside the allowed root.
- Wenjin-specific constraint: one workspace uses `/workspace/datasets/**`, not deer-flow's thread-local `/mnt/user-data`.

**Files:**

- Modify: `backend/src/sandbox/workspace_layout.py`
- Modify: `backend/src/agents/harness/context_assembly.py`
- Test: `backend/tests/sandbox/test_workspace_layout.py`
- Test: `backend/tests/agents/harness/test_context_assembly.py`
- Docs: `docs/current/architecture.md`
- Docs: `docs/current/native-harness-convergence-audit.md`
- Docs: `docs/current/workspace-current-state.md`
- Docs: `docs/superpowers/specs/2026-06-06-wenjin-native-agent-harness-design.md`
- Docs: `docs/superpowers/plans/2026-06-08-wenjin-native-harness-convergence.md`

- [x] **Step 1: Add failing layout tests**

Added tests requiring layout initialization to create:

```text
/workspace/datasets/README.md
/workspace/datasets/manifest.json
```

The default dataset manifest uses:

```json
{
  "schema": "wenjin.workspace_sandbox.dataset_provenance.v1",
  "version": 1,
  "root": "/workspace/datasets",
  "datasets": [],
  "rules": []
}
```

Also added a preservation test proving an existing dataset manifest is not overwritten by provider acquire.

- [x] **Step 2: Implement dataset guidance and manifest helpers**

`backend/src/sandbox/workspace_layout.py` now defines the dataset provenance schema, dataset manifest virtual path, dataset README text, default manifest builder, and manifest path in the main workspace sandbox manifest.

Layout initialization creates the dataset manifest only when missing.

- [x] **Step 3: Add failing context projection test**

Added a context test requiring `workspace_file_summary.dataset_provenance` to retain only safe `/workspace/datasets/**` refs and drop non-dataset/protected paths.

- [x] **Step 4: Implement bounded dataset provenance projection**

`backend/src/agents/harness/context_assembly.py` now projects caller-provided dataset provenance entries with bounded fields such as `source_kind`, `source_id`, `title`, `content_hash`, `license`, and `preparation`.

It accepts only `/workspace/datasets/**` virtual paths and continues to filter protected/internal refs.

- [x] **Step 5: Update docs and verify**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/sandbox/test_workspace_layout.py tests/agents/harness/test_context_assembly.py -q
.venv/bin/ruff check src/sandbox/workspace_layout.py src/agents/harness/context_assembly.py tests/sandbox/test_workspace_layout.py tests/agents/harness/test_context_assembly.py
```

Observed:

```text
14 passed
All checks passed!
```

### Task 12: DataService Dataset Provenance Projection

**Goal:** make dataset provenance visible to harness agents from existing DataService source page asset facts, without inventing a second dataset registry, adding per-source scans, or widening file access.

**Files:**
- Modified: `backend/src/agents/lead_agent/v2/runtime.py`
- Modified: `backend/tests/agents/lead_agent/v2/test_runtime.py`
- Modified: `docs/current/architecture.md`
- Modified: `docs/current/workspace-current-state.md`
- Modified: `docs/superpowers/specs/2026-06-06-wenjin-native-agent-harness-design.md`

- [x] **Step 1: Add regression for explicit `/workspace/datasets/**` source assets**

Added `test_load_workspace_data_projects_dataset_assets_into_file_summary`.

The test verifies:

- DataService source context still produces `related_documents` and `library_context`.
- Only a source asset whose explicit path is `/workspace/datasets/raw/survey.csv` becomes `workspace_file_summary.dataset_provenance`.
- Regular `references/...` uploads and `/workspace/outputs/**` paths are not treated as datasets.
- Provenance keeps bounded fields: path, source id, name, title, description, format, mime type, size, hash, license, preparation, and timestamps.

Observed red before implementation:

```text
KeyError: 'workspace_file_summary'
```

- [x] **Step 2: Add regression against source asset N+1 scans**

Added `test_load_workspace_data_uses_source_page_assets_without_n_plus_one_calls`.

The test verifies:

- Runtime uses `list_sources_page().items[].assets` as the source context entry point.
- Runtime does not call `list_sources` or per-source `list_source_assets`.
- Dict-shaped source page projections and object-shaped source projections both feed the same source context builder.

Observed red before implementation:

```text
KeyError: 'related_documents'
```

- [x] **Step 3: Implement the converged projection boundary**

`LeadAgentRuntime._load_source_records_for_workspace_context()` now uses DataService source page projection and returns both source records and dataset provenance. It does not add a fallback source-list compatibility path.

`_build_source_context()` now accepts both object-shaped DataService client records and dict-shaped source page records. Excluded sources are filtered in runtime before entering related documents, citation context, or dataset provenance.

`_dataset_provenance_ref_from_source_asset()` only accepts paths normalized by `workspace_layout.normalize_workspace_virtual_path()` that are explicitly under `/workspace/datasets/**`. It rejects `/workspace/datasets/manifest.json`, guidance files, protected paths, internal paths, non-workspace paths, `references/...`, and `/workspace/outputs/**`.

- [x] **Step 4: Verify targeted tests**

Run:

```bash
cd /Users/ze/wenjin
backend/.venv/bin/python -m pytest backend/tests/agents/lead_agent/v2/test_runtime.py::test_load_workspace_data_projects_dataset_assets_into_file_summary backend/tests/agents/lead_agent/v2/test_runtime.py::test_load_workspace_data_uses_source_page_assets_without_n_plus_one_calls -q
backend/.venv/bin/python -m pytest backend/tests/agents/lead_agent/v2/test_runtime.py -q
backend/.venv/bin/python -m pytest backend/tests/agents/harness/test_context_assembly.py backend/tests/sandbox/test_workspace_layout.py -q
```

Observed:

```text
2 passed
25 passed
14 passed
```

### Task 12A: Sync Dataset Provenance Into the Sandbox Manifest

**Goal:** close the gap between context-visible `workspace_file_summary.dataset_provenance` and the actual long-lived `/workspace/datasets/manifest.json` inside the workspace sandbox.

**Architecture:** keep the merge rules in `backend/src/sandbox/workspace_layout.py`, pass context provenance through the existing harness `sandbox.run_python` wrapper, and sync the manifest inside the existing `SandboxJobRunner` workspace lease before script execution. Do not add a second dataset registry, source scanner, sandbox job, frontend stream, or compatibility layer.

**Files:**
- Modified: `backend/src/sandbox/workspace_layout.py`
- Modified: `backend/src/agents/harness/sandbox_execution_tools.py`
- Modified: `backend/src/agents/lead_agent/v2/sandbox_job_runner.py`
- Modified: `backend/src/agents/lead_agent/v2/sandbox_runtime.py`
- Modified: `backend/tests/sandbox/test_workspace_layout.py`
- Modified: `backend/tests/agents/harness/test_scheduler_and_python_tool.py`
- Modified: `backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py`
- Modified: `docs/current/architecture.md`
- Modified: `docs/current/workspace-current-state.md`
- Modified: `docs/current/native-harness-convergence-audit.md`
- Modified: `docs/superpowers/specs/2026-06-06-wenjin-native-agent-harness-design.md`
- Modified: `docs/superpowers/plans/2026-06-08-wenjin-native-harness-convergence.md`

- [x] **Step 1: Add RED tests for manifest merge and runner propagation**

Added:

- `test_merge_dataset_provenance_manifest_adds_safe_refs_without_overwriting_existing`
- `test_merge_dataset_provenance_manifest_rejects_non_dataset_and_guidance_refs`
- `test_run_python_passes_dataset_provenance_from_context_bundle`
- `test_run_python_script_syncs_dataset_manifest_before_script_execution`

Observed RED:

```text
AttributeError: module 'src.sandbox.workspace_layout' has no attribute 'merge_dataset_provenance_manifest'
KeyError: 'dataset_provenance'
TypeError: run_python_script() got an unexpected keyword argument 'dataset_provenance'
```

- [x] **Step 2: Implement append-only safe manifest merge**

`merge_dataset_provenance_manifest()` now preserves existing user-authored dataset rows, appends only safe runtime rows by path, and stores a bounded allowlist of fields. It accepts only `/workspace/datasets/**` data files and rejects dataset manifest/README/.gitkeep, protected/internal paths, non-workspace refs, ordinary outputs, host-ish paths, non-scalar values, and fields that look like secrets or credentials.

- [x] **Step 3: Wire context provenance into `sandbox.run_python`**

`SandboxExecutionTools.run_python()` now extracts `context.context_bundle.workspace_file_summary.dataset_provenance` and passes it to `SandboxJobRunner.run_python_script(...)`. The runner reads or creates `/workspace/datasets/manifest.json`, merges the safe rows, and writes the manifest before `SandboxScriptExecutor.execute()` writes/runs the script in the same lease.

- [x] **Step 4: Verify targeted behavior**

Run:

```bash
cd /Users/ze/wenjin
backend/.venv/bin/python -m pytest backend/tests/sandbox/test_workspace_layout.py::test_merge_dataset_provenance_manifest_adds_safe_refs_without_overwriting_existing backend/tests/sandbox/test_workspace_layout.py::test_merge_dataset_provenance_manifest_rejects_non_dataset_and_guidance_refs -q
backend/.venv/bin/python -m pytest backend/tests/agents/harness/test_scheduler_and_python_tool.py::test_run_python_passes_dataset_provenance_from_context_bundle -q
backend/.venv/bin/python -m pytest backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py::test_run_python_script_syncs_dataset_manifest_before_script_execution -q
backend/.venv/bin/python -m pytest backend/tests/sandbox/test_workspace_layout.py backend/tests/agents/harness/test_scheduler_and_python_tool.py backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py -q
backend/.venv/bin/ruff check backend/src/sandbox/workspace_layout.py backend/src/agents/harness/sandbox_execution_tools.py backend/src/agents/lead_agent/v2/sandbox_job_runner.py backend/src/agents/lead_agent/v2/sandbox_runtime.py backend/tests/sandbox/test_workspace_layout.py backend/tests/agents/harness/test_scheduler_and_python_tool.py backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py
```

Observed:

```text
2 passed
1 passed
1 passed
43 passed
All checks passed!
```

The broader dataset/source-context verification also passed:

```bash
backend/.venv/bin/python -m pytest backend/tests/agents/lead_agent/v2/test_runtime.py::test_load_workspace_data_projects_dataset_assets_into_file_summary backend/tests/agents/lead_agent/v2/test_runtime.py::test_load_workspace_data_uses_source_page_assets_without_n_plus_one_calls backend/tests/agents/harness/test_context_assembly.py backend/tests/sandbox/test_workspace_layout.py backend/tests/agents/harness/test_scheduler_and_python_tool.py backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py -q
```

Observed:

```text
50 passed
```

### Task 12B: Surface Dataset Provenance in Sandbox Experiment Evidence

**Goal:** make long-running experiment handoffs show the dataset inputs that were synchronized into `/workspace/datasets/manifest.json`, without exposing raw manifest internals, host paths, secrets, or debug payloads.

**Architecture:** reuse the existing runner payload, `report_markdown`, and `reproducibility_manifest` paths. Do not add a new report table, UI store, or sandbox reader.

**Files:**
- Modified: `backend/src/agents/lead_agent/v2/sandbox_job_runner.py`
- Modified: `backend/src/agents/lead_agent/v2/sandbox_artifact_collector.py`
- Modified: `backend/src/agents/harness/sandbox_execution_tools.py`
- Modified: `backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py`
- Modified: `backend/tests/agents/harness/test_scheduler_and_python_tool.py`
- Modified: `docs/current/architecture.md`
- Modified: `docs/current/native-harness-convergence-audit.md`
- Modified: `docs/current/workspace-current-state.md`
- Modified: `docs/superpowers/specs/2026-06-06-wenjin-native-agent-harness-design.md`
- Modified: `docs/superpowers/plans/2026-06-08-wenjin-native-harness-convergence.md`

- [x] **Step 1: Add RED tests for dataset evidence in reports/manifests**

Added:

- `test_run_python_script_reports_synced_dataset_provenance`
- `test_run_python_reproducibility_manifest_includes_dataset_provenance`

Observed RED:

```text
KeyError: 'dataset_provenance'
KeyError: 'datasets'
```

- [x] **Step 2: Return safe synced dataset entries from the runner**

`SandboxJobRunner._sync_dataset_manifest()` now returns the accepted safe runtime dataset rows after applying the same merge/filter rules used to update `/workspace/datasets/manifest.json`. Invalid output refs are filtered before the collector sees them.

- [x] **Step 3: Add user-readable Dataset provenance report section**

`SandboxArtifactCollector.script_output()` now preserves `dataset_provenance` in the runner payload and appends a bounded `## Dataset provenance` section with the dataset manifest path, accepted dataset paths, source ids, and content hashes.

- [x] **Step 4: Carry datasets into reproducibility manifest**

`SandboxExecutionTools._reproducibility_manifest()` now adds a bounded `datasets` field only when safe dataset provenance exists. Existing no-dataset manifests stay unchanged.

- [x] **Step 5: Verify**

Run:

```bash
cd /Users/ze/wenjin
backend/.venv/bin/python -m pytest backend/tests/agents/harness/test_scheduler_and_python_tool.py backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py backend/tests/sandbox/test_workspace_layout.py -q
backend/.venv/bin/ruff check backend/src/agents/harness/sandbox_execution_tools.py backend/src/agents/lead_agent/v2/sandbox_job_runner.py backend/src/agents/lead_agent/v2/sandbox_artifact_collector.py backend/src/agents/lead_agent/v2/sandbox_runtime.py backend/src/sandbox/workspace_layout.py backend/tests/agents/harness/test_scheduler_and_python_tool.py backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py backend/tests/sandbox/test_workspace_layout.py
git diff --check
```

Observed:

```text
45 passed
All checks passed!
git diff --check: no output
```

The broader dataset/source-context verification also passed after this change:

```text
52 passed
```

### Task 13: Claim Evidence Grounding Gate

**Goal:** make TeamKernel evidence quality gates reject claim-evidence maps that describe evidence in prose but cannot be traced back to a workspace source or citation key.

**Files:**
- Modified: `backend/src/agents/lead_agent/v2/team/quality_gates.py`
- Modified: `backend/tests/agents/lead_agent/v2/test_team_quality_gates.py`
- Modified: `docs/current/architecture.md`
- Modified: `docs/current/workspace-current-state.md`
- Modified: `docs/superpowers/specs/2026-06-06-wenjin-native-agent-harness-design.md`

- [x] **Step 1: Add red test for ungrounded claim map**

Added `test_quality_gates_fail_claim_evidence_map_without_source_refs`.

The test verifies:

- `claim_evidence_map_required` is not satisfied by a non-empty list alone.
- A supported claim entry with `claim` and prose `evidence`, but without `source_id` or `citation_key`, fails.
- The gate asks for `revise_existing`, not broad recruitment or a new runtime path.

Observed red before implementation:

```text
StopIteration
```

- [x] **Step 2: Add pass test for citation-key grounded claim map**

Added `test_quality_gates_accept_claim_evidence_map_with_citation_keys`.

The test verifies:

- A claim map entry with claim text and `citation_key` satisfies the gate.

- [x] **Step 3: Implement structural grounding validation**

`_foundation_field_gates()` now gives `claim_evidence_map_required` a narrow structural validator after the existing presence check. `_invalid_claim_evidence_entries()` accepts list-shaped maps, `{"claims": [...]}` maps, and simple dictionary maps, but every supported claim entry must expose claim text plus at least one `source_id`, `source_ids`, `source_ref`, `source_refs`, `citation_key`, or `citation_keys` value.

Unsupported claims remain a separate output field; they should not be disguised as grounded claim-evidence entries.

- [x] **Step 4: Verify targeted tests**

Run:

```bash
cd /Users/ze/wenjin
backend/.venv/bin/python -m pytest backend/tests/agents/lead_agent/v2/test_team_quality_gates.py::test_quality_gates_fail_claim_evidence_map_without_source_refs backend/tests/agents/lead_agent/v2/test_team_quality_gates.py::test_quality_gates_accept_claim_evidence_map_with_citation_keys -q
backend/.venv/bin/python -m pytest backend/tests/agents/lead_agent/v2/test_team_quality_gates.py -q
backend/.venv/bin/ruff check backend/src/agents/lead_agent/v2/team/quality_gates.py backend/tests/agents/lead_agent/v2/test_team_quality_gates.py
```

Observed:

```text
2 passed
10 passed
All checks passed!
```

### Task 14: Workspace-Scoped Claim Evidence Refs

**Goal:** prevent team members from satisfying claim evidence grounding with citation keys or source ids that do not belong to the current workspace Library/source context.

**Files:**
- Modified: `backend/src/agents/lead_agent/v2/team/quality_contract.py`
- Modified: `backend/src/agents/lead_agent/v2/team/kernel.py`
- Modified: `backend/src/agents/lead_agent/v2/team/quality_gates.py`
- Modified: `backend/tests/agents/lead_agent/v2/test_team_quality_contract.py`
- Modified: `backend/tests/agents/lead_agent/v2/test_team_kernel.py`
- Modified: `backend/tests/agents/lead_agent/v2/test_team_quality_gates.py`
- Modified: `docs/current/architecture.md`
- Modified: `docs/current/workspace-current-state.md`
- Modified: `docs/superpowers/specs/2026-06-06-wenjin-native-agent-harness-design.md`

- [x] **Step 1: Add red test for QualityContract source allowlist**

Updated `test_quality_contract_resolver_merges_existing_catalog_records` to pass workspace data with `library_context.citation_keys` and `related_documents`, then assert:

- `allowed_citation_keys == ["smith2026", "doe2025"]`
- `allowed_source_ids == ["source-1", "source-2"]`

Observed red before implementation:

```text
TypeError: QualityContractResolver.resolve() got an unexpected keyword argument 'workspace_data'
```

- [x] **Step 2: Implement QualityContract allowlist projection**

`ResolvedQualityContract` now has bounded `allowed_citation_keys` and `allowed_source_ids` fields. `QualityContractResolver.resolve(..., workspace_data=...)` derives them from:

- `workspace_data.library_context.citation_keys`
- `workspace_data.related_documents[].id`
- `workspace_data.related_documents[].citation_key`

- [x] **Step 3: Add red test for TeamKernel injection**

Added `test_team_kernel_quality_contract_includes_workspace_source_allowlist`.

Observed red before implementation:

```text
TypeError: TeamKernelRuntime._inject_quality_contracts() got an unexpected keyword argument 'workspace_data'
```

- [x] **Step 4: Pass workspace_data through TeamKernel contract injection**

`TeamKernelRuntime._run_invocation_batch()` now passes the same bounded workspace data already used by subagents into `_inject_quality_contracts()`, so each invocation sees the current workspace source allowlist in its `input_brief.quality_contract`.

- [x] **Step 5: Add red test for unknown citation key**

Added `test_quality_gates_fail_claim_evidence_map_with_unknown_citation_key`.

The test verifies:

- If `allowed_citation_keys=["smith2026"]`, a claim map entry using `citation_key="missing2026"` fails.
- The gate asks for revision rather than treating the claim as grounded.

Observed red before implementation:

```text
StopIteration
```

- [x] **Step 6: Validate claim refs against the allowlist**

`claim_evidence_map_required` now still requires claim text plus a source/citation ref, and when `allowed_source_ids` / `allowed_citation_keys` are present, refs must come from that allowlist. Missing refs and unknown refs are reported as structured `invalid_entries`.

- [x] **Step 7: Verify related tests**

Run:

```bash
cd /Users/ze/wenjin
backend/.venv/bin/python -m pytest backend/tests/agents/lead_agent/v2/test_team_quality_contract.py::test_quality_contract_resolver_merges_existing_catalog_records -q
backend/.venv/bin/python -m pytest backend/tests/agents/lead_agent/v2/test_team_kernel.py::test_team_kernel_quality_contract_includes_workspace_source_allowlist -q
backend/.venv/bin/python -m pytest backend/tests/agents/lead_agent/v2/test_team_quality_gates.py::test_quality_gates_fail_claim_evidence_map_without_source_refs backend/tests/agents/lead_agent/v2/test_team_quality_gates.py::test_quality_gates_accept_claim_evidence_map_with_citation_keys backend/tests/agents/lead_agent/v2/test_team_quality_gates.py::test_quality_gates_fail_claim_evidence_map_with_unknown_citation_key -q
backend/.venv/bin/python -m pytest backend/tests/agents/lead_agent/v2/test_team_quality_gates.py backend/tests/agents/lead_agent/v2/test_team_quality_contract.py backend/tests/agents/lead_agent/v2/test_team_kernel.py -q
backend/.venv/bin/ruff check backend/src/agents/lead_agent/v2/team/quality_gates.py backend/src/agents/lead_agent/v2/team/quality_contract.py backend/src/agents/lead_agent/v2/team/kernel.py backend/tests/agents/lead_agent/v2/test_team_quality_gates.py backend/tests/agents/lead_agent/v2/test_team_quality_contract.py backend/tests/agents/lead_agent/v2/test_team_kernel.py
```

Observed:

```text
1 passed
1 passed
3 passed
40 passed
All checks passed!
```

### Task 14B: Source and Citation Auditor Structural Gates

**Goal:** make `source-quality-auditor` and `citation-auditor` outputs influence TeamKernel quality decisions through structured audit fields, not only prose summaries or `quality_gates_checked` acknowledgements.

**Architecture:** extend the existing pure `quality_gates.py` evaluator. Do not add a new review table, runtime, subagent loop, or frontend state. QualityContract already carries workspace `allowed_source_ids` and `allowed_citation_keys`; reuse that allowlist.

**Files:**
- Modified: `backend/src/agents/lead_agent/v2/team/quality_gates.py`
- Modified: `backend/tests/agents/lead_agent/v2/test_team_quality_gates.py`
- Modified: `docs/current/architecture.md`
- Modified: `docs/current/native-harness-convergence-audit.md`
- Modified: `docs/current/workspace-current-state.md`
- Modified: `docs/superpowers/specs/2026-06-06-wenjin-native-agent-harness-design.md`
- Modified: `docs/superpowers/plans/2026-06-08-wenjin-native-harness-convergence.md`

- [x] **Step 1: Add RED tests**

Added:

- `test_quality_gates_fail_source_quality_audit_without_structured_fields`
- `test_quality_gates_accept_grounded_citation_readiness_audit`
- `test_quality_gates_fail_citation_readiness_audit_with_unknown_refs`

Observed RED:

```text
source-quality structured gate returned pass instead of fail
unknown citation/source refs returned pass instead of fail
```

- [x] **Step 2: Add structural field requirements for source/citation gates**

`source_authority_checked`, `metadata_completeness_checked`, `weak_support_flagged`, `no_fabricated_citations`, `claim_source_binding_checked`, and `style_consistency_checked` now require structured fields such as `citation_key_audit`, `missing_sources`, `fabrication_risks`, or `bibtex_projection_notes`. Empty arrays are allowed so an auditor can explicitly say no risks were found.

- [x] **Step 3: Validate audit refs against workspace allowlists**

`citation_key_audit` and `bibtex_projection_notes` entries are checked against `allowed_source_ids` and `allowed_citation_keys` when those allowlists are present. Unknown refs produce structured `invalid_entries` and a `revise_existing` gate result.

- [x] **Step 4: Verify**

Run:

```bash
cd /Users/ze/wenjin
backend/.venv/bin/python -m pytest backend/tests/agents/lead_agent/v2/test_team_quality_gates.py::test_quality_gates_fail_source_quality_audit_without_structured_fields backend/tests/agents/lead_agent/v2/test_team_quality_gates.py::test_quality_gates_accept_grounded_citation_readiness_audit backend/tests/agents/lead_agent/v2/test_team_quality_gates.py::test_quality_gates_fail_citation_readiness_audit_with_unknown_refs -q
backend/.venv/bin/python -m pytest backend/tests/agents/lead_agent/v2/test_team_quality_gates.py -q
backend/.venv/bin/ruff check backend/src/agents/lead_agent/v2/team/quality_gates.py backend/tests/agents/lead_agent/v2/test_team_quality_gates.py
```

Observed:

```text
3 passed
14 passed
All checks passed!
```

Broader TeamKernel verification also passed:

```text
43 passed
```

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
