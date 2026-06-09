# Native Harness Member Transcript Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a compact member-level execution transcript to Wenjin native harness so Lead Agent and downstream subagents can understand what each team member actually did, without adding a second runtime, run table, SDK bridge, or fallback layer.

**Architecture:** Keep the execution path unchanged: `ChatAgent -> LeadAgent -> TeamKernel/static graph -> ReactSubagent -> Wenjin Harness -> DataService/Sandbox/Review`. The new transcript is only a projection over existing `tool_calls` and existing execution `node_metadata.harness`, then carried through `build_harness_context_bundle` as bounded context evidence. This borrows Codex/DeerFlow's transcript/journal idea while keeping Wenjin's data-driven capability/team architecture as the source of truth.

**Tech Stack:** Python 3.13, Pydantic-style plain dict contracts used by current harness metadata, pytest, ruff.

---

## Scope Boundary

This plan intentionally does not implement:

- Codex SDK integration.
- cc-switch or provider protocol bridges.
- DeerFlow runtime import.
- A new run journal table, task table, event stream, frontend store, or compatibility layer.
- Generic `sandbox.run_command`.
- Any `/mnt/user-data` alias or second sandbox filesystem convention.

The only new surface is a compact summary inside existing metadata/context:

```python
node_metadata["harness"]["member_execution_transcript"]
bundle["member_execution_transcript"]
bundle["recent_execution_evidence"][i]["harness"]["member_execution_transcript"]
```

## File Structure

- Modify `backend/src/agents/harness/diff_tracker.py`
  - Add `MEMBER_EXECUTION_TRANSCRIPT_SCHEMA`.
  - Add `build_member_execution_transcript_from_tool_calls(...)`.
  - Call it from `build_harness_node_metadata_from_tool_calls(...)`.
  - Keep sanitization strict: no raw script content, no raw stdout/stderr, no secret/internal paths.

- Modify `backend/src/agents/harness/context_assembly.py`
  - Add top-level `member_execution_transcript` via `_latest_harness_summary(...)`.
  - Preserve transcript under `_harness_summary(...)` so downstream members can see recent team activity.
  - Add it to `_fit_budget(...)` removal order before dropping heavier evidence.

- Modify `backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py`
  - Add tests for transcript schema, aggregation, token/duration normalization, and raw-content redaction.

- Modify `backend/tests/agents/harness/test_context_assembly.py`
  - Add tests proving the transcript flows into top-level context and recent execution evidence.

- Modify docs:
  - `docs/current/architecture.md`
  - `docs/current/workspace-current-state.md`
  - `docs/current/native-harness-convergence-audit.md`
  - `docs/current/native-harness-external-gap-matrix.md`

---

### Task 1: Baseline And Guardrails

**Files:**
- Inspect: `backend/src/agents/harness/diff_tracker.py`
- Inspect: `backend/src/agents/harness/context_assembly.py`
- Inspect: `backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py`
- Inspect: `backend/tests/agents/harness/test_context_assembly.py`

- [x] **Step 1: Confirm worktree is clean**

Run:

```bash
git status --short
```

Expected: no output, or only this plan file if planning has already been saved.

- [x] **Step 2: Confirm no forbidden harness drift exists**

Run:

```bash
rg -n "codex sdk|cc-switch|ccswitch|/mnt/user-data|run_command|RunJournal|deer-flow" backend/src backend/tests docs/current -g '!*.pyc'
```

Expected: only documentation references explaining why these are not imported, and no runtime implementation of those concepts.

- [x] **Step 3: Run existing focused harness metadata tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py tests/agents/harness/test_context_assembly.py -q
```

Expected: all existing tests pass before adding the new red tests.

---

### Task 2: Member Transcript Metadata

**Files:**
- Modify: `backend/src/agents/harness/diff_tracker.py`
- Test: `backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py`

- [x] **Step 1: Write the failing transcript aggregation test**

Add this test to `backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py` after the existing reproducibility summary test:

```python
def test_harness_node_metadata_includes_member_execution_transcript() -> None:
    metadata = build_harness_node_metadata_from_tool_calls(
        [
            {
                "name": "sandbox.run_python",
                "status": "completed",
                "duration_ms": 1250,
                "usage": {"input_tokens": 1200, "output_tokens": 300, "total_tokens": 1500},
                "execution_manifest": {
                    "schema": "wenjin.harness.run_python.execution_manifest.v1",
                    "sandbox_job_id": "job-1",
                    "sandbox_environment_id": "env-1",
                    "task_scratch_path": "/workspace/tmp/tasks/exec-1/analysis_probe",
                },
                "generated_artifacts": [
                    {"path": "/workspace/outputs/result.json"},
                    {"path": "/workspace/reports/analysis.md"},
                ],
            },
            {
                "name": "sandbox.write_file",
                "status": "completed",
                "duration_ms": 100,
                "file_changes": [
                    build_file_change(
                        path="/workspace/reports/analysis.md",
                        before=None,
                        after="# Analysis\n",
                        operation="add",
                    )
                ],
            },
            {
                "name": "sandbox.read_file",
                "status": "failed",
                "args": {"path": "/workspace/.env", "content": "must not leak"},
                "error": "HarnessPathError: protected path is not accessible: /workspace/.env",
                "metadata": {"error_code": "tool_error"},
            },
        ]
    )

    transcript = metadata["harness"]["member_execution_transcript"]
    assert transcript == {
        "schema": "wenjin.harness.member_execution_transcript.v1",
        "tool_call_count": 3,
        "tool_names": ["sandbox.run_python", "sandbox.write_file", "sandbox.read_file"],
        "completed_tool_count": 2,
        "failed_tool_count": 1,
        "failed_tools": ["sandbox.read_file"],
        "changed_paths": ["/workspace/reports/analysis.md"],
        "sandbox_job_ids": ["job-1"],
        "sandbox_environment_ids": ["env-1"],
        "scratch_refs": ["/workspace/tmp/tasks/exec-1/analysis_probe"],
        "generated_artifact_count": 2,
        "usage": {"input_tokens": 1200, "output_tokens": 300, "total_tokens": 1500},
        "duration_ms": 1350,
    }
    assert "/workspace/.env" not in str(transcript)
    assert "must not leak" not in str(transcript)
```

- [x] **Step 2: Run red test**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py::test_harness_node_metadata_includes_member_execution_transcript -q
```

Expected: fail because `member_execution_transcript` does not exist yet.

- [x] **Step 3: Implement transcript builder**

Add these elements to `backend/src/agents/harness/diff_tracker.py`:

```python
MEMBER_EXECUTION_TRANSCRIPT_SCHEMA = "wenjin.harness.member_execution_transcript.v1"
```

Add a builder with this contract:

```python
def build_member_execution_transcript_from_tool_calls(
    tool_calls: list[dict[str, Any]] | None,
    *,
    file_change_summary: dict[str, Any] | None = None,
    sandbox_execution_summary: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    calls = [tool_call for tool_call in tool_calls or [] if isinstance(tool_call, dict)]
    if not calls:
        return None
    tool_names: list[str] = []
    failed_tools: list[str] = []
    scratch_refs: list[str] = []
    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    duration_ms = 0
    completed_tool_count = 0
    failed_tool_count = 0
    for tool_call in calls:
        name = str(tool_call.get("name") or "unknown_tool").strip() or "unknown_tool"
        _append_unique(tool_names, name)
        status = str(tool_call.get("status") or "").strip()
        if status == "failed":
            failed_tool_count += 1
            _append_unique(failed_tools, name)
        else:
            completed_tool_count += 1
        duration_ms += _int_value(tool_call.get("duration_ms"))
        raw_usage = tool_call.get("usage")
        raw_usage = raw_usage if isinstance(raw_usage, dict) else {}
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            usage[key] += _int_value(raw_usage.get(key))
        metadata = tool_call.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        manifest = _first_dict(tool_call.get("execution_manifest"), metadata.get("execution_manifest"))
        if manifest is not None:
            _append_safe_scratch_ref(scratch_refs, str(manifest.get("task_scratch_path") or ""))

    result = {
        "schema": MEMBER_EXECUTION_TRANSCRIPT_SCHEMA,
        "tool_call_count": len(calls),
        "tool_names": tool_names[:20],
        "completed_tool_count": completed_tool_count,
        "failed_tool_count": failed_tool_count,
        "failed_tools": failed_tools[:20],
        "changed_paths": _list_value((file_change_summary or {}).get("changed_paths"))[:50],
        "sandbox_job_ids": _list_value((sandbox_execution_summary or {}).get("sandbox_job_ids"))[:20],
        "sandbox_environment_ids": _list_value(
            (sandbox_execution_summary or {}).get("sandbox_environment_ids")
        )[:20],
        "scratch_refs": scratch_refs[:20],
        "generated_artifact_count": _int_value(
            (sandbox_execution_summary or {}).get("generated_artifact_count")
        ),
    }
    if any(usage.values()):
        result["usage"] = usage
    if duration_ms > 0:
        result["duration_ms"] = duration_ms
    return result
```

Also add `_append_safe_scratch_ref(...)` that accepts only `/workspace/tmp/tasks/{execution_id}/{node_id}` style refs and rejects `.harness`, `.wenjin`, `.env`, and non-workspace paths.

- [x] **Step 4: Wire transcript into node metadata**

In `build_harness_node_metadata_from_tool_calls(...)`, after `sandbox_execution_summary` is built and before `run_journal_summary`, add:

```python
member_execution_transcript = build_member_execution_transcript_from_tool_calls(
    tool_calls,
    file_change_summary=file_change_summary,
    sandbox_execution_summary=sandbox_execution_summary,
)
if member_execution_transcript is not None:
    harness["member_execution_transcript"] = member_execution_transcript
```

- [x] **Step 5: Run transcript test and full metadata test file**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py -q
```

Expected: pass.

---

### Task 3: Context Bundle Propagation

**Files:**
- Modify: `backend/src/agents/harness/context_assembly.py`
- Test: `backend/tests/agents/harness/test_context_assembly.py`

- [x] **Step 1: Write failing context propagation assertions**

Extend `test_harness_context_bundle_exposes_team_member_execution_package` with this harness metadata:

```python
"member_execution_transcript": {
    "schema": "wenjin.harness.member_execution_transcript.v1",
    "tool_call_count": 2,
    "tool_names": ["sandbox.run_python", "sandbox.write_file"],
    "completed_tool_count": 2,
    "failed_tool_count": 0,
    "changed_paths": ["/workspace/main/paper.tex"],
    "sandbox_job_ids": ["job-1"],
    "sandbox_environment_ids": ["env-1"],
    "scratch_refs": ["/workspace/tmp/tasks/exec-1/research_scout"],
    "generated_artifact_count": 1,
}
```

Then assert:

```python
assert bundle["member_execution_transcript"] == {
    "schema": "wenjin.harness.member_execution_transcript.v1",
    "tool_call_count": 2,
    "tool_names": ["sandbox.run_python", "sandbox.write_file"],
    "completed_tool_count": 2,
    "failed_tool_count": 0,
    "changed_paths": ["/workspace/main/paper.tex"],
    "sandbox_job_ids": ["job-1"],
    "sandbox_environment_ids": ["env-1"],
    "scratch_refs": ["/workspace/tmp/tasks/exec-1/research_scout"],
    "generated_artifact_count": 1,
}
assert bundle["recent_execution_evidence"][0]["harness"]["member_execution_transcript"]["tool_call_count"] == 2
```

- [x] **Step 2: Run red context test**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_context_assembly.py::test_harness_context_bundle_exposes_team_member_execution_package -q
```

Expected: fail because `member_execution_transcript` is not included in the context bundle yet.

- [x] **Step 3: Add top-level transcript context**

In `build_harness_context_bundle(...)`, after `reproducibility_summary`, add:

```python
"member_execution_transcript": _latest_harness_summary(
    safe_workspace_data,
    "member_execution_transcript",
),
```

- [x] **Step 4: Preserve transcript inside recent execution evidence**

In `_harness_summary(...)`, include the transcript key:

```python
for key in (
    "file_change_summary",
    "tool_failure_summary",
    "sandbox_execution_summary",
    "reproducibility_summary",
    "member_execution_transcript",
):
```

- [x] **Step 5: Budget handling**

In `_fit_budget(...)`, add:

```python
("member_execution_transcript", {}),
```

after `reproducibility_summary`, so the bundle can still shrink deterministically.

- [x] **Step 6: Run context tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_context_assembly.py -q
```

Expected: pass.

---

### Task 4: Documentation Convergence

**Files:**
- Modify: `docs/current/architecture.md`
- Modify: `docs/current/workspace-current-state.md`
- Modify: `docs/current/native-harness-convergence-audit.md`
- Modify: `docs/current/native-harness-external-gap-matrix.md`

- [x] **Step 1: Update architecture source of truth**

Add one concise paragraph to `docs/current/architecture.md` near the native harness / execution metadata section:

```markdown
Harness member transcript is a metadata projection, not a separate runtime. Each ReactSubagent invocation records compact `member_execution_transcript` evidence from existing tool calls: tools used, failures, changed files, sandbox job IDs, scratch refs, generated artifact counts, token usage, and duration. LeadAgent and downstream members consume it through the bounded context bundle; raw stdout, raw scripts, protected paths, and internal harness output refs are not promoted.
```

- [x] **Step 2: Update workspace current behavior**

Add one concise paragraph to `docs/current/workspace-current-state.md` near execution evidence / workspace history:

```markdown
Workspace history now carries member-level harness transcripts inside existing node metadata. This gives later team members enough context to continue a long-running sandbox task without creating a second journal store: they can see which tools ran, which files changed, whether Python execution failed, which scratch directory is relevant, and which artifacts were generated.
```

- [x] **Step 3: Update convergence audit**

Add a dated entry:

```markdown
## 2026-06-09 — Member Transcript Projection

- Added `wenjin.harness.member_execution_transcript.v1` as a compact projection over existing harness tool calls.
- Kept the architecture converged: no new run table, runtime, protocol bridge, SDK dependency, or frontend stream.
- Closed the immediate Codex/DeerFlow-inspired gap around member-level execution memory while preserving Wenjin's LeadAgent/team-capability flow.
```

- [x] **Step 4: Update external gap matrix**

Change the member transcript gap from open to partially closed/closed with this point:

```markdown
Wenjin now exposes member-level execution transcript metadata through existing node metadata and context bundles. Remaining gap: richer frontend visualization can be designed later, but backend execution memory is no longer dependent on raw run logs.
```

---

### Task 5: Verification And Commit

**Files:**
- Verify all modified files.

- [x] **Step 1: Run focused tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py tests/agents/harness/test_context_assembly.py -q
```

Expected: pass.

- [x] **Step 2: Run native harness gate**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_scheduler_and_python_tool.py tests/agents/harness/test_sandbox_file_tools.py tests/agents/harness/test_command_audit.py tests/agents/harness/test_policy_and_registry.py tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py tests/agents/harness/test_research_task_eval.py tests/agents/harness/test_langchain_adapter.py tests/agents/harness/test_context_assembly.py tests/unit/subagents/test_react.py tests/subagents/v2/test_registry.py tests/agents/lead_agent/v2/test_team_policy.py tests/agents/lead_agent/v2/test_sandbox_runtime.py tests/agents/lead_agent/v2/test_workspace_sandbox_manager.py tests/agents/lead_agent/v2/test_runtime.py::test_run_session_prism_review_items_satisfy_writing_evidence_eval tests/architecture/test_native_harness_boundaries.py tests/dataservice/test_sandbox_domain.py tests/sandbox/test_workspace_layout.py tests/agents/lead_agent/v2/test_sandbox_artifact_discovery.py tests/agents/lead_agent/v2/test_citation_source_audit.py tests/agents/lead_agent/v2/test_team_quality_gates.py tests/services/test_workspace_prism_service.py::test_surface_projection_includes_review_provenance_and_protection tests/services/test_prism_review_projection.py tests/integration/test_harness_mock_sandbox_e2e.py -q
```

Expected: pass.

- [x] **Step 3: Run ruff on changed backend files**

Run:

```bash
cd backend && .venv/bin/ruff check src/agents/harness/diff_tracker.py src/agents/harness/context_assembly.py tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py tests/agents/harness/test_context_assembly.py
```

Expected: pass.

- [x] **Step 4: Check whitespace and worktree**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only intentional modified files.

- [x] **Step 5: Commit**

Run:

```bash
git add backend/src/agents/harness/diff_tracker.py backend/src/agents/harness/context_assembly.py backend/tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py backend/tests/agents/harness/test_context_assembly.py docs/current/architecture.md docs/current/workspace-current-state.md docs/current/native-harness-convergence-audit.md docs/current/native-harness-external-gap-matrix.md docs/superpowers/plans/2026-06-09-native-harness-member-transcript.md
git commit -m "feat: add member harness transcript summary"
```

Expected: commit succeeds.

---

## Self-Review

- Spec coverage: The plan covers the next weakest native harness gap: per-member execution memory modeled as metadata/context projection. It does not cover frontend rendering because the user's current goal is harness independence and backend architecture convergence.
- Placeholder scan: No task contains `TBD`, `TODO`, fallback wording, or deferred implementation.
- Type consistency: The same key name is used everywhere: `member_execution_transcript`; schema is `wenjin.harness.member_execution_transcript.v1`.
- Architecture convergence: The plan keeps a single execution runtime, single context assembly path, single sandbox filesystem convention, and single metadata projection surface.
