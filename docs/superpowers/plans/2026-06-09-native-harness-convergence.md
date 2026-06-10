# Native Harness Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Wenjin's native research harness into a coherent, workspace-scoped execution layer that can reliably read/write sandbox files, run experiments, collect evidence, and feed high-quality outputs back into the existing ChatAgent -> LeadAgent -> TeamKernel -> ReactSubagent pipeline.

**Architecture:** Keep the current Wenjin topology as the source of truth: ChatAgent dispatches intent, LeadAgent plans and recruits the team, TeamKernel/ReactSubagent executes skills, and the native harness owns sandbox actions through DataService/Sandbox/Review contracts. Borrow concepts from Codex and DeerFlow only as design patterns, not runtime dependencies, and avoid compatibility bridges, fallback routers, or a second execution system.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, Pydantic v2, LangGraph, existing Wenjin sandbox providers, pytest, ruff.

---

## File Structure

- `backend/src/agents/lead_agent/v2/sandbox_script_executor.py`: converts a `run_python` plan step into a sandbox command, installs missing packages, and now must execute inside invocation-scoped task scratch.
- `backend/src/agents/lead_agent/v2/sandbox_job_runner.py`: builds auditable harness jobs and job metadata for sandbox execution.
- `backend/src/agents/lead_agent/v2/sandbox_artifact_collector.py`: turns sandbox execution outputs into result payloads, markdown reports, and review artifacts.
- `backend/src/agents/harness/sandbox_execution_tools.py`: produces experiment manifests and narrative reports from sandbox outputs.
- `backend/src/sandbox/base.py`: defines provider interface for sandbox command execution.
- `backend/src/sandbox/providers/local.py`: local sandbox provider used by tests and development.
- `backend/src/sandbox/providers/docker.py`: Docker sandbox provider used by production-like execution.
- `backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py`: runtime tests for sandbox execution, artifact discovery, policy, and scratch behavior.
- `docs/current/architecture.md`: current architecture source of truth.
- `docs/current/workspace-current-state.md`: current workspace, sandbox, Prism, and execution behavior.
- `docs/current/native-harness-convergence-audit.md`: implementation audit trail for native harness convergence.
- `docs/current/native-harness-external-gap-matrix.md`: comparison with Codex/DeerFlow and remaining gaps.

---

### Task 1: Close the Current Invocation Scratch Slice

**Files:**
- Modify: `backend/src/agents/lead_agent/v2/sandbox_script_executor.py`
- Modify: `backend/src/agents/lead_agent/v2/sandbox_job_runner.py`
- Modify: `backend/src/agents/lead_agent/v2/sandbox_artifact_collector.py`
- Modify: `backend/src/agents/harness/sandbox_execution_tools.py`
- Modify: `backend/src/sandbox/base.py`
- Modify: `backend/src/sandbox/providers/local.py`
- Modify: `backend/src/sandbox/providers/docker.py`
- Test: `backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py`

- [ ] **Step 1: Verify the red-test contract is present**

Check that `backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py` contains:

```python
async def test_run_python_script_uses_invocation_scoped_scratch_options() -> None:
    ...


async def test_run_python_script_local_provider_executes_inside_task_scratch(tmp_path) -> None:
    ...
```

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/agents/lead_agent/v2/test_sandbox_runtime.py::test_run_python_script_uses_invocation_scoped_scratch_options \
  tests/agents/lead_agent/v2/test_sandbox_runtime.py::test_run_python_script_local_provider_executes_inside_task_scratch -q
```

Expected after implementation: `2 passed`.

- [ ] **Step 2: Verify provider execution contract**

Check that `Sandbox.execute_command` in `backend/src/sandbox/base.py` accepts:

```python
cwd: str | None = None,
env: dict[str, str] | None = None,
```

Check that `LocalSandbox.execute_command` resolves virtual workspace paths into host paths while rejecting protected/internal directories.

Check that `DockerSandbox.execute_command` passes `working_dir` and `environment` into `DockerClient.run_container`.

- [ ] **Step 3: Verify run_python cwd/env propagation**

Check that `sandbox_script_executor.py` exposes:

```python
def sandbox_script_execution_env(task_scratch_path: str) -> dict[str, str]:
    return {
        "WENJIN_TASK_SCRATCH": task_scratch_path,
        "WENJIN_WORKSPACE_ROOT": WORKSPACE_ROOT,
    }
```

Check that both first execution and missing-module retry call `sandbox.execute_command(..., cwd=task_scratch_path, env=execution_env, network_profile="none")`.

- [ ] **Step 4: Verify scratch evidence reaches review output**

Check that `sandbox_artifact_collector.py` adds `task_scratch_path` to the script output payload and markdown report.

Check that `sandbox_execution_tools.py` includes `task_scratch_path` in manifests only when a real value exists, so mock/no-op test outputs do not gain empty fields.

- [ ] **Step 5: Run the focused runtime test file**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_sandbox_runtime.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Run the sandbox/provider/harness regression set**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/sandbox/test_local_sandbox.py \
  tests/sandbox/test_integration.py \
  tests/sandbox/test_workspace_layout.py \
  tests/agents/harness/test_scheduler_and_python_tool.py \
  tests/agents/harness/test_langchain_adapter.py \
  tests/agents/lead_agent/v2/test_sandbox_runtime.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit the closed slice**

Run:

```bash
git status --short
git add backend/src/agents/harness/sandbox_execution_tools.py \
  backend/src/agents/lead_agent/v2/sandbox_artifact_collector.py \
  backend/src/agents/lead_agent/v2/sandbox_job_runner.py \
  backend/src/agents/lead_agent/v2/sandbox_script_executor.py \
  backend/src/sandbox/base.py \
  backend/src/sandbox/providers/docker.py \
  backend/src/sandbox/providers/local.py \
  backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py
git commit -m "feat: run python inside scoped sandbox scratch"
```

Expected: commit succeeds and worktree no longer contains code changes from this slice.

---

### Task 2: Update Current Architecture Docs

**Files:**
- Modify: `docs/current/architecture.md`
- Modify: `docs/current/workspace-current-state.md`
- Modify: `docs/current/native-harness-convergence-audit.md`
- Modify: `docs/current/native-harness-external-gap-matrix.md`

- [ ] **Step 1: Document the scratch execution contract**

In `docs/current/architecture.md`, update the sandbox `run_python` section to state:

```markdown
`run_python` creates `/workspace/tmp/tasks/{execution_id}/{node_id}` before execution, runs the script with that directory as cwd, and injects `WENJIN_TASK_SCRATCH` plus `WENJIN_WORKSPACE_ROOT`. Outputs still flow through the artifact collector and curated result_card review.
```

- [ ] **Step 2: Document workspace filesystem behavior**

In `docs/current/workspace-current-state.md`, add:

```markdown
Invocation scratch lives under `/workspace/tmp/tasks/{execution_id}/{node_id}`. It is task-scoped working space for intermediate experiment files, not a user-facing document room. The final report, manifest, and selected artifacts still go through review before they are committed.
```

- [ ] **Step 3: Update the convergence audit**

In `docs/current/native-harness-convergence-audit.md`, add an entry:

```markdown
### 2026-06-09: run_python task scratch execution slice

- Added invocation-scoped cwd/env propagation for sandbox `run_python`.
- Local and Docker providers now accept audited `cwd` and `env` options.
- Artifact collector and experiment manifests expose `task_scratch_path` when present.
- Verification:
  - `test_sandbox_runtime.py -q`
  - sandbox/provider/harness regression set
  - `ruff check` on touched backend files
```

- [ ] **Step 4: Refresh the external gap matrix**

In `docs/current/native-harness-external-gap-matrix.md`, update the workspace filesystem gap to say:

```markdown
Status: partially closed. `run_python` now executes inside invocation scratch with cwd/env propagation. Remaining work is real-task tuning: deciding which intermediates become review artifacts, which stay scratch-only, and how much scratch context later team members should receive.
```

- [ ] **Step 5: Scan docs for stale terms**

Run:

```bash
rg -n "task_scratch_path|WENJIN_TASK_SCRATCH|WENJIN_WORKSPACE_ROOT|tmp/tasks|Codex SDK|cc-switch|fallback|compat" docs/current -g '*.md'
```

Expected: scratch terms are current; Codex SDK/cc-switch references appear only in historical/audit sections or explicit "do not reintroduce" guidance.

- [ ] **Step 6: Commit docs**

Run:

```bash
git add docs/current/architecture.md \
  docs/current/workspace-current-state.md \
  docs/current/native-harness-convergence-audit.md \
  docs/current/native-harness-external-gap-matrix.md \
  docs/superpowers/plans/2026-06-09-native-harness-convergence.md
git commit -m "docs: document native harness scratch execution"
```

Expected: commit succeeds.

---

### Task 3: Rebuild the Native Harness Regression Gate

**Files:**
- Read: `backend/tests/agents/harness/`
- Read: `backend/tests/agents/lead_agent/v2/`
- Read: `backend/tests/sandbox/`
- Read: `backend/tests/architecture/test_native_harness_boundaries.py`

- [ ] **Step 1: Run the native harness gate**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/agents/harness/test_scheduler_and_python_tool.py \
  tests/agents/harness/test_sandbox_file_tools.py \
  tests/agents/harness/test_command_audit.py \
  tests/agents/harness/test_policy_and_registry.py \
  tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py \
  tests/agents/harness/test_research_task_eval.py \
  tests/agents/harness/test_langchain_adapter.py \
  tests/agents/harness/test_context_assembly.py \
  tests/unit/subagents/test_react.py \
  tests/subagents/v2/test_registry.py \
  tests/agents/lead_agent/v2/test_team_policy.py \
  tests/agents/lead_agent/v2/test_sandbox_runtime.py \
  tests/agents/lead_agent/v2/test_workspace_sandbox_manager.py \
  tests/agents/lead_agent/v2/test_runtime.py::test_run_session_prism_review_items_satisfy_writing_evidence_eval \
  tests/architecture/test_native_harness_boundaries.py \
  tests/dataservice/test_sandbox_domain.py \
  tests/sandbox/test_workspace_layout.py \
  tests/agents/lead_agent/v2/test_sandbox_artifact_discovery.py \
  tests/agents/lead_agent/v2/test_citation_source_audit.py \
  tests/agents/lead_agent/v2/test_team_quality_gates.py \
  tests/services/test_workspace_prism_service.py::test_surface_projection_includes_review_provenance_and_protection \
  tests/services/test_prism_review_projection.py \
  tests/integration/test_harness_mock_sandbox_e2e.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run lint and whitespace checks**

Run:

```bash
cd backend && .venv/bin/ruff check \
  src/sandbox/base.py \
  src/sandbox/providers/local.py \
  src/sandbox/providers/docker.py \
  src/agents/lead_agent/v2/sandbox_script_executor.py \
  src/agents/lead_agent/v2/sandbox_job_runner.py \
  src/agents/lead_agent/v2/sandbox_artifact_collector.py \
  src/agents/harness/sandbox_execution_tools.py \
  tests/agents/lead_agent/v2/test_sandbox_runtime.py
git diff --check
```

Expected: ruff passes and `git diff --check` prints no whitespace errors.

- [ ] **Step 3: Inspect final diff for architectural drift**

Run:

```bash
git diff --stat
rg -n "codex sdk|cc-switch|deer-flow|fallback|compat|/mnt/user-data|sandbox.run_command" backend/src backend/tests docs/current -S
```

Expected: no new runtime dependency on external harnesses, no fallback router, no `/mnt/user-data` alias, no generic `sandbox.run_command` skill.

---

### Task 4: Add the Next Small Harness Capability Only After the Scratch Slice Is Clean

**Files:**
- Modify: `backend/src/agents/harness/sandbox_execution_tools.py`
- Modify: `backend/src/agents/harness/context_assembly.py` or nearest existing context module after inspection
- Modify: `backend/src/agents/lead_agent/v2/sandbox_job_runner.py`
- Test: `backend/tests/agents/harness/test_context_assembly.py`
- Test: `backend/tests/agents/harness/test_scheduler_and_python_tool.py`

- [ ] **Step 1: Write a failing test for scratch-aware context assembly**

Add a test that creates a completed upstream sandbox output with:

```python
payload = {
    "task_scratch_path": "/workspace/tmp/tasks/exec-1/analysis_probe",
    "artifacts": [
        {"path": "/workspace/artifacts/result.csv", "kind": "dataset"}
    ],
}
```

Expected behavior:

```python
assert "task_scratch_path" in assembled_context
assert "/workspace/tmp/tasks/exec-1/analysis_probe" in assembled_context
assert "/workspace/artifacts/result.csv" in assembled_context
```

The test must also assert that protected/internal paths are not surfaced as editable user artifacts.

- [ ] **Step 2: Run the new test and verify failure**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_context_assembly.py::test_context_includes_scratch_reference_without_promoting_it_to_artifact -q
```

Expected: FAIL because scratch references are not yet represented in assembled context.

- [ ] **Step 3: Implement minimal context projection**

Add a small, typed context field such as:

```python
scratch_refs: list[WorkspacePathRef]
```

or reuse the existing path-ref type if already present. Keep the distinction:

```python
review_artifacts = user-facing files that can be accepted
scratch_refs = internal working directories that help later agents continue work
```

- [ ] **Step 4: Run context and scheduler tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/agents/harness/test_context_assembly.py \
  tests/agents/harness/test_scheduler_and_python_tool.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit the capability**

Run:

```bash
git add backend/src/agents/harness backend/src/agents/lead_agent/v2 backend/tests/agents/harness
git commit -m "feat: carry sandbox scratch refs in harness context"
```

Expected: commit succeeds.

---

### Task 5: Learn From Codex and DeerFlow Without Importing Their Runtime

**Files:**
- Read: `/Users/ze/codex`
- Read: `/Users/ze/deer-flow`
- Modify: `docs/current/native-harness-external-gap-matrix.md`
- Modify: `docs/current/native-harness-convergence-audit.md`

- [ ] **Step 1: Review Codex for reusable patterns**

Inspect only architectural units relevant to Wenjin:

```bash
rg -n "sandbox|apply_patch|exec|approval|cwd|env|diff|plan|session|turn" /Users/ze/codex -g '*.rs' -g '*.py' -g '*.ts' -g '*.md'
```

Extract patterns, not code:

```markdown
- command governance and audit
- patch/diff-first file modification
- task-local cwd/env discipline
- concise execution evidence
- user approval boundaries
```

- [ ] **Step 2: Review DeerFlow for reusable patterns**

Inspect orchestration and planning units:

```bash
rg -n "graph|state|planner|research|report|artifact|workflow|human|interrupt|checkpoint" /Users/ze/deer-flow -g '*.py' -g '*.ts' -g '*.md'
```

Extract patterns, not code:

```markdown
- graph state shape
- planner/reporter separation
- research evidence packaging
- long-running workflow checkpoints
- human-in-the-loop interruption
```

- [ ] **Step 3: Update the gap matrix**

For each pattern, classify:

```markdown
Adopt now | Adopt later | Reject
```

Rules:

```markdown
Adopt now: improves current native harness without new runtime layer.
Adopt later: useful but needs product decision or broad UI change.
Reject: conflicts with Wenjin's fixed ChatAgent -> LeadAgent -> TeamKernel pipeline.
```

- [ ] **Step 4: Add an audit note**

Record what was inspected and why no external runtime dependency was introduced.

- [ ] **Step 5: Commit docs**

Run:

```bash
git add docs/current/native-harness-external-gap-matrix.md docs/current/native-harness-convergence-audit.md
git commit -m "docs: refresh native harness external gap review"
```

Expected: commit succeeds.

---

### Task 6: Define the Workspace Sandbox Filesystem Contract

**Files:**
- Modify: `docs/current/architecture.md`
- Modify: `docs/current/workspace-current-state.md`
- Test: `backend/tests/sandbox/test_workspace_layout.py`
- Test: `backend/tests/dataservice/test_sandbox_domain.py`

- [ ] **Step 1: Write the contract**

Document this filesystem shape:

```text
/workspace
  /documents        user-authored manuscripts and source documents
  /library          imported papers, citations, metadata snapshots
  /experiments      durable experiment projects
  /artifacts        accepted or reviewable outputs
  /tmp/tasks        invocation-scoped scratch, never directly user-facing
  /logs             execution logs and summaries
```

Document these rules:

```markdown
- One workspace owns at most one sandbox.
- Task scratch is recreated or reused per execution/node, not per subagent identity.
- Agents may read prior accepted artifacts and selected scratch refs when included in context.
- Agents may not treat `/tmp/tasks` as a committed output room.
- Review acceptance is the boundary between scratch/artifact and workspace rooms.
```

- [ ] **Step 2: Add tests if the layout contract is not already covered**

Add assertions to `backend/tests/sandbox/test_workspace_layout.py`:

```python
assert workspace_task_scratch_path(execution_id="exec-1", node_id="analysis") == "/workspace/tmp/tasks/exec-1/analysis"
assert workspace_artifact_path("result.csv") == "/workspace/artifacts/result.csv"
```

- [ ] **Step 3: Run layout tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/sandbox/test_workspace_layout.py tests/dataservice/test_sandbox_domain.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit the contract**

Run:

```bash
git add docs/current/architecture.md docs/current/workspace-current-state.md backend/tests/sandbox/test_workspace_layout.py backend/tests/dataservice/test_sandbox_domain.py
git commit -m "docs: define workspace sandbox filesystem contract"
```

Expected: commit succeeds.

---

### Task 7: Final Review Gate Before Expanding Scope

**Files:**
- Read: full changed diff
- Read: relevant tests
- Read: docs/current harness docs

- [ ] **Step 1: Run architecture boundary tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/architecture/test_native_harness_boundaries.py -q
```

Expected: pass.

- [ ] **Step 2: Run the native harness gate again**

Run the same command from Task 3 Step 1.

Expected: all selected tests pass.

- [ ] **Step 3: Run a mock sandbox E2E**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/integration/test_harness_mock_sandbox_e2e.py -q
```

Expected: pass.

- [ ] **Step 4: Summarize remaining gaps honestly**

Update `docs/current/native-harness-external-gap-matrix.md` with remaining gaps against Codex and DeerFlow:

```markdown
- stronger command transcript UX
- richer diff/apply-review flow for sandbox-written files
- more realistic long-running scientific task evals
- better team-memory handoff between sequential agents
```

- [ ] **Step 5: Stop only at a clean boundary**

Run:

```bash
git status --short
```

Expected: either clean, or only intentional uncommitted docs/plan edits that are explicitly reported.

---

## Self-Review

Spec coverage:
- Current uncommitted scratch execution slice is covered by Tasks 1-3.
- Continued external learning from Codex and DeerFlow is covered by Task 5.
- Workspace sandbox filesystem standardization is covered by Task 6.
- Architecture convergence and no-drift review is covered by Tasks 3 and 7.

Placeholder scan:
- The plan avoids TBD/TODO/fallback language.
- Each code-facing task has concrete files, test commands, and expected outcomes.

Type consistency:
- `task_scratch_path`, `WENJIN_TASK_SCRATCH`, and `WENJIN_WORKSPACE_ROOT` are used consistently.
- Scratch refs are separate from review artifacts and workspace rooms.

Execution rule:
- Do not start Task 4 until Tasks 1-3 are clean and committed.
- Do not start any Codex SDK, cc-switch, ACP, or external runtime bridge work under this plan.
