# Native Harness Acceptance Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Wenjin's native research harness from "structurally runnable" to "acceptance-reviewable" without adding external agent runtimes.

**Architecture:** Keep the harness native to Wenjin: capability policy drives TeamKernel recruitment, sandbox/file tools remain behind Wenjin's workspace contract, and deterministic quality checks stay in `backend/src/agents/harness` plus `backend/src/agents/lead_agent/v2/team`. This pass adds small acceptance infrastructure rather than another compatibility layer.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, FastAPI/DataService contracts, LangGraph-backed Lead Agent runtime.

---

### Task 1: Real-Task Evaluation Pack

**Files:**
- Create: `backend/src/agents/harness/research_task_eval_pack.py`
- Test: `backend/tests/agents/harness/test_research_task_eval_pack.py`
- Modify: `backend/src/agents/harness/__init__.py`

- [x] Write failing tests for a curated SCI acceptance case that evaluates one passing fixture and one failing fixture through `evaluate_research_task_evidence()`.
- [x] Implement a small `ResearchTaskEvalCase` / `ResearchTaskEvalPackResult` API that accepts already-built `TaskReport`, node events and required surfaces.
- [x] Ensure failures are grouped by case id and surface so release gates can report what to tune.
- [x] Run `backend/tests/agents/harness/test_research_task_eval_pack.py`.

### Task 2: TeamKernel Replan Episode State

**Files:**
- Create: `backend/src/agents/lead_agent/v2/team/episode.py`
- Modify: `backend/src/agents/lead_agent/v2/team/contracts.py`
- Modify: `backend/src/agents/lead_agent/v2/team/kernel.py`
- Test: `backend/tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py`

- [x] Write failing tests showing `runtime_state_json.harness_episode` records iteration decisions, selected recruits and stop reason.
- [x] Add a bounded episode projection with schema `wenjin.team.harness_episode.v1`.
- [x] Persist the episode beside existing `quality_gates` without raw tool payloads.
- [x] Run the TeamKernel harness replan tests.

### Task 3: Context Acceptance Guard

**Files:**
- Modify: `backend/tests/agents/harness/test_context_assembly.py`

- [x] Add a budget-stress regression test proving required research-evidence context is preserved longer than generic context.
- [x] Keep the implementation unchanged unless the test exposes drift.
- [x] Run `backend/tests/agents/harness/test_context_assembly.py`.

### Task 4: Documentation and Release Gate

**Files:**
- Modify: `docs/current/native-harness-convergence-audit.md`
- Modify: `docs/current/release-gate-checklist.md`

- [x] Record that acceptance closeout now includes real-task eval pack, replan episode state and context budget guards.
- [x] Run the focused harness tests, `ruff`, and `git diff --check`.
- [x] If frontend/browser verification is blocked by local services, report that explicitly instead of claiming it.
