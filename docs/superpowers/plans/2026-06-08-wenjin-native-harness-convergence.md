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

Current uncommitted slice already started:

- `backend/src/agents/harness/sandbox_execution_tools.py`
- `backend/src/agents/harness/langchain_adapter.py`
- `backend/tests/agents/harness/test_scheduler_and_python_tool.py`
- `backend/tests/agents/harness/test_langchain_adapter.py`
- `docs/current/architecture.md`
- `docs/current/workspace-current-state.md`

This slice adds `sandbox.run_python` execution manifests and recoverable user-code failure classification. Finish and commit it before starting the next slice.

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

- [ ] **Step 5: Commit current slice**

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

- [ ] **Step 1: Write failing layout manifest test**

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

- [ ] **Step 2: Implement deterministic layout data**

Keep the public helpers in `workspace_layout.py`; do not scatter path constants into providers. The manifest should contain stable schema/version/roots/protected/internal metadata and no timestamps.

- [ ] **Step 3: Add symlink/path-policy regression tests**

Add tests covering:

- visible symlink to `.wenjin/env/**` is not listed as readable content.
- visible symlink to external host path is rejected.
- direct `/workspace/outputs/harness/**` read is rejected.
- direct writes to `.wenjin/cache/**`, `.wenjin/env/**`, `.env`, `*.pem`, `*.key` are rejected.

- [ ] **Step 4: Run sandbox and harness path tests**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/sandbox/test_workspace_layout.py tests/agents/harness/test_sandbox_tools_path_policy.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

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
- Test: `backend/tests/agents/harness/test_diff_tracker.py`
- Test: `backend/tests/agents/lead_agent/v2/test_runtime_harness_metadata.py`

- [ ] **Step 1: Write failing summary test**

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

- [ ] **Step 2: Implement pure summary builder**

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

- [ ] **Step 3: Attach summary in static graph and TeamKernel paths**

Add the summary beside the existing `file_change_summary` and `tool_failure_summary` under `node_metadata.harness`.

- [ ] **Step 4: Run metadata tests**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/harness/test_diff_tracker.py tests/agents/lead_agent/v2/test_runtime_harness_metadata.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

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

- [ ] **Step 1: Write failing context-bundle tests**

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

- [ ] **Step 2: Implement pure assembler**

Create `context_assembly.py` with pure functions first:

```python
def build_harness_context_bundle(... ) -> dict[str, Any]:
    ...
```

Keep DataService access at caller boundaries. The assembler should accept already-loaded summaries so it stays easy to test.

- [ ] **Step 3: Inject context into ReactSubagent system prompt**

Add a compact "Sandbox workspace contract" section and a "Recent execution evidence" section. Do not dump raw tool JSON. Use summaries from `sandbox_execution_summary`, `file_change_summary`, and `tool_failure_summary`.

- [ ] **Step 4: Run context tests**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/harness/test_context_assembly.py tests/subagents/v2/test_react_harness_context.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

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

- [ ] **Step 1: Write failing tests for replan triggers**

Scenarios:

- `python_exit_nonzero` from a code agent should stay recoverable and be visible to Lead for bounded retry/recruitment.
- `sandbox_queue_timeout` should not trigger infinite reruns.
- `tool_forbidden` should not be solved by recruiting another member with the same forbidden tool request.

- [ ] **Step 2: Implement replan signal extraction**

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

- [ ] **Step 3: Wire signals into TeamKernel quality decision input**

Pass compact signals into the quality gate prompt/context. Do not expose raw stderr to users by default.

- [ ] **Step 4: Run TeamKernel tests**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

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

- [ ] **Step 1: Audit current template tool declarations**

Run:

```bash
cd /Users/ze/wenjin
rg "sandbox\\.|filesystem\\.|allowed_tools|tool_affinity|risk_profile" backend/seed backend/src/subagents -n
```

Record mismatches:

- unknown tool names.
- tools declared in prompts but absent from policy.
- broad write/exec claims without explicit permissions.

- [ ] **Step 2: Write failing registry validation tests**

Assert:

- declared tool names resolve exactly.
- capability policy is the maximum envelope.
- template/skill cannot widen tool access.
- role templates receive the sandbox workspace contract.

- [ ] **Step 3: Update role templates**

Use concrete, product-specific wording:

- Literature roles: prefer `sandbox.read_file`, `sandbox.glob`, `sandbox.grep`; write reports under `/workspace/reports`.
- Code/experiment roles: generate scripts under `/workspace/scripts`; generated plots/results under `/workspace/outputs`; handle dependency hints explicitly.
- Writing roles: do not mutate Prism files directly unless using approved review/staging flow.
- Utility/fill-in roles: read/search broadly, write only when capability grants `filesystem.write` and `filesystem.diff`.

- [ ] **Step 4: Run validation**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/subagents/v2/test_registry.py tests/agents/lead_agent/v2/test_capability_tool_policy.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

Commit message:

```bash
git commit -m "chore: align role templates with harness tools"
```

---

### Task 6: Add Minimal Product-Facing Harness UX Projection

**Files:**

- Modify: `frontend/lib/execution-run-view.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`
- Modify: `frontend/stores/run-ui-store.ts`
- Test: `frontend/lib/execution-run-view.test.ts`

- [ ] **Step 1: Write failing projection tests**

Default user-facing execution projection should show:

- team member name.
- concise activity label such as "正在运行实验" or "已生成实验结果".
- generated artifact candidates if reviewable.
- no raw JSON args, no full stdout/stderr, no debug-only command details.

- [ ] **Step 2: Implement projection only from existing execution events**

Do not add a new frontend harness store. `execution-run-view.ts` remains the shared projection source.

- [ ] **Step 3: Run frontend tests and browser smoke**

Run:

```bash
cd /Users/ze/wenjin/frontend
npm run typecheck
npx vitest run frontend/lib/execution-run-view.test.ts
```

Then run a browser smoke against Docker/local stack for:

- create workspace.
- trigger team-agent task.
- observe LiveWorkflowPanel.
- open run details.
- confirm debug details are collapsed.

- [ ] **Step 4: Commit**

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

- [ ] **Step 1: Create a mock sandbox E2E test**

The test should simulate:

1. Lead dispatches a code/experiment subagent.
2. Subagent receives bounded `/workspace` contract.
3. Subagent writes `/workspace/scripts/analysis.py`.
4. Subagent runs `sandbox.run_python`.
5. Python run returns execution manifest.
6. Generated `/workspace/outputs/result.json` is discovered as an artifact candidate.
7. Node metadata contains file change summary, sandbox execution summary, and no protected/internal refs.

- [ ] **Step 2: Run E2E and relevant backend tests**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/integration/test_harness_mock_sandbox_e2e.py -q
.venv/bin/python -m pytest tests/agents/harness tests/agents/lead_agent/v2/test_sandbox_runtime.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run full backend test suite before broader merge**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/ -q
```

Expected: all backend tests pass.

- [ ] **Step 4: Commit**

Commit message:

```bash
git commit -m "test: cover harness mock sandbox workflow"
```

---

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
