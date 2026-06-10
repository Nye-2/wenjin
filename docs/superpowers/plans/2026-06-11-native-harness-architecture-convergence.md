# Native Harness Architecture Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 收敛 native harness 大改后的架构边界，避免 Prism 合同、research eval、TeamKernel runtime state 继续漂移。

**Architecture:** 这次只做纯重构和文档整理，不改变 Lead Agent、TeamKernel、Prism review 的业务语义。核心方向是把 Prism review 合同变成单一源头，把 research eval 拆成更窄的模块边界，把 TeamKernel 的 runtime state 持久化入口命名和职责收口，并把 context budget 策略从 context assembly 主文件拆出。

**Tech Stack:** Python 3.13, FastAPI/DataService, Pydantic v2, LangGraph TeamKernel, pytest.

---

### Task 1: Prism Review Contract Single Source

**Files:**
- Create: `backend/src/services/prism_review_contracts.py`
- Modify: `backend/src/services/prism_file_content.py`
- Modify: `backend/src/dataservice/prism_review_api.py`
- Modify: `backend/src/agents/harness/research_task_eval.py`

- [x] Extract academic style schema ids, bounded sanitize helpers, and style delta validation into one shared service module.
- [x] Update DataService persistence to use the shared sanitizer before storing upstream contracts.
- [x] Update Prism projection/content summarizer to use the same sanitizer and delta builder.
- [x] Update deterministic eval to validate style deltas through the same contract helper.
- [x] Run Prism review projection, workspace prism, and research eval tests.

### Task 2: Research Eval Module Boundary

**Files:**
- Create: `backend/src/agents/harness/research_eval_surfaces.py`
- Modify: `backend/src/agents/harness/research_task_eval.py`
- Modify: `backend/src/agents/harness/research_task_eval_pack.py`

- [x] Move `ResearchSurface`, defaults, known surface set, and capability-policy parsing into the shared surface module.
- [x] Keep `research_task_eval.py` as the public evaluator entry point for now to avoid risky behavior movement.
- [x] Update imports in Team quality gates and pack tests.
- [x] Run harness eval and Team quality-gate tests.

### Task 3: TeamKernel Runtime State Convergence

**Files:**
- Modify: `backend/src/agents/lead_agent/v2/team/kernel.py`
- Keep: `backend/src/agents/lead_agent/v2/team/episode.py`

- [x] Rename the persistence helper from quality-gate-specific wording to runtime-state wording.
- [x] Keep the existing branch behavior unchanged.
- [x] Run TeamKernel runtime, replan, and cancellation tests.

### Task 4: Context Budget Policy Boundary

**Files:**
- Create: `backend/src/agents/harness/context_budget_policy.py`
- Modify: `backend/src/agents/harness/context_assembly.py`

- [x] Move budget trimming, protected evidence summary ordering, and structural fallback trimming into a dedicated policy module.
- [x] Keep `context_assembly.py` responsible for bundle construction and renderer injection.
- [x] Run context assembly tests.

### Task 5: Verification, Review, Merge

**Files:**
- Modify docs only if current-state or architecture docs need updated names.

- [ ] Run focused backend tests for all changed surfaces.
- [ ] Run code review over the final diff.
- [ ] Merge the feature branch into `master` after tests pass.
- [ ] Commit and push the consolidated result.
