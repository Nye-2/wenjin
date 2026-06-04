# UX Content Quality Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the review findings that most affect workspace UX and generated-content quality while keeping Wenjin's Chat Agent -> Lead Agent -> DataService -> review/commit architecture converged.

**Architecture:** Keep changes inside existing boundaries: frontend Zustand stores and live-workflow view model, backend Team Kernel quality gates/contracts, existing capability/skill seed files, and current docs. Do not introduce a parallel workflow engine or compatibility layer.

**Tech Stack:** Next.js/React/Zustand/Vitest on the frontend; Python 3.13/Pydantic/Pytest/LangGraph team runtime on the backend.

---

### Task 1: Workspace-Scoped Chat State

**Files:**
- Modify: `frontend/stores/chat-store.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`
- Test: `frontend/tests/unit/stores/chat-store.test.ts`
- Test: `frontend/tests/unit/v2/ChatPanel.test.tsx`

- [x] Add a failing store test proving `loadHistory("workspace-b")` loads workspace B even when workspace A already has messages.
- [x] Add a failing ChatPanel test proving a feature entry seed can auto-launch in an empty target workspace after another workspace has messages.
- [x] Change the chat store to track messages by workspace and expose selectors/actions for the active workspace without changing the persisted block protocol.
- [x] Update ChatPanel to read/write only the current workspace message set.
- [x] Run `cd frontend && ./node_modules/.bin/vitest run tests/unit/stores/chat-store.test.ts tests/unit/v2/ChatPanel.test.tsx`.

### Task 2: Quality-Gate Evidence Strength

**Files:**
- Modify: `backend/src/agents/lead_agent/v2/team/quality_gates.py`
- Modify: `backend/src/subagents/v2/types/react.py`
- Test: `backend/tests/agents/lead_agent/v2/test_team_quality_gates.py`
- Test: `backend/tests/subagents/v2/test_react_output_contract.py` or nearest existing React subagent test file

- [x] Add a failing quality-gate test where an evidence-dependent output has claims but no `claim_evidence_map`; the gate must fail instead of pass/warn.
- [x] Add a failing React parser test proving required schema fields are not silently fabricated as empty arrays/objects when JSON parsing fails for a strict quality contract.
- [x] Implement stricter gate evaluation for claim/citation/evidence contracts using existing output fields and quality contract metadata.
- [x] Update React fallback parsing so strict quality contracts surface a parse/contract error payload instead of a fake compliant report.
- [x] Run `cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_quality_gates.py -q`.

### Task 3: Team Blackboard And Internal Output Safety

**Files:**
- Modify: `backend/src/agents/lead_agent/v2/team/contracts.py`
- Modify: `backend/src/agents/lead_agent/v2/team/kernel.py`
- Test: `backend/tests/agents/lead_agent/v2/test_team_kernel.py` or nearest existing team kernel test file

- [x] Add a failing test proving mapped graph outputs are required for user-checked deliverables; invocation fallback reports must be diagnostic and not default checked.
- [x] Add a failing test proving blackboard evidence/gap/risk fields accumulate from member outputs between dynamic recruitment iterations.
- [x] Implement a focused blackboard merge helper that consumes known fields only: `confirmed_findings`, `evidence_items`, `citation_gaps`, `experiment_gaps`, `data_gaps`, `writing_risks`, `pending_decisions`, and `rejected_claims`.
- [x] Change invocation fallback output to `doc_kind="team_diagnostic_report"` and `default_checked=false`.
- [x] Run the team kernel target tests.

### Task 4: Skill Schemas And Capability Seeds

**Files:**
- Modify: `backend/seed/skills/claim-verifier.yaml`
- Modify: `backend/seed/skills/citation-auditor.yaml`
- Modify: `backend/seed/capabilities/sci/research_question_to_paper.yaml`
- Test: `backend/tests/services/test_capability_schema.py`
- Test: `backend/tests/services/test_skill_loader.py`

- [x] Strengthen claim/citation item schemas with required fields that the Evidence Ledger can render.
- [x] Remove the hardcoded federated instruction tuning sandbox probe from the generic SCI paper capability; replace it with a generic method-probe scaffold that requires topic-specific assumptions from upstream context.
- [x] Run capability schema/loader tests.

### Task 5: Evidence Ledger And Risk-Aware Review

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/types.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/utils.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/EvidenceView.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/ReviewView.tsx`
- Test: `frontend/tests/unit/v2/live-workflow-view-model.test.ts`

- [x] Add failing view-model tests proving evidence items include claim/citation status and high-risk outputs are not default accepted.
- [x] Extend `EvidenceItem` using existing execution result/runtime payloads; avoid fetching new API data in this pass.
- [x] Surface citation keys, evidence refs, and verification status in EvidenceView.
- [x] Disable or downgrade "全部接受" when selected outputs include unresolved high-risk evidence/citation gates.
- [x] Run the live-workflow frontend target tests.

### Task 6: Design Source Convergence And Verification

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/current/wenjin-research-navigation-uiux.md`
- Modify: `docs/superpowers/specs/2026-05-09-v2-design-language.md`
- Modify: `docs/current/architecture.md`
- Modify: `docs/current/workspace-current-state.md`

- [x] Update docs so evidence-first research navigation is the current UI source of truth.
- [x] Retire stale default-all-checked design guidance; no `globals.css` token churn was needed for this behavior-only convergence.
- [x] Update current architecture/workspace docs with workspace-scoped chat state and stronger quality gate behavior.
- [x] Run `cd frontend && npm run typecheck`, backend target pytest, and browser smoke for the workspace page.

### Baseline Evidence

- Backend baseline: `cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_quality_gates.py tests/services/test_capability_schema.py -q` -> 30 passed.
- Frontend baseline: `cd frontend && ./node_modules/.bin/vitest run tests/unit/stores/chat-store.test.ts tests/unit/v2/live-workflow-view-model.test.ts tests/unit/v2/ChatPanel.test.tsx` -> 34 passed.

### Final Verification

- `git diff --check` -> passed.
- `cd backend && .venv/bin/python -m pytest tests/ -q` -> 2259 passed.
- `cd backend && .venv/bin/python -m ruff check src tests` -> passed.
- `cd frontend && npm run typecheck` -> passed.
- `cd frontend && ./node_modules/.bin/vitest run` -> 253 passed.
- `cd frontend && npm run build` -> passed.
- `cd frontend && npx playwright test deep-research-flow.spec.ts --project=v2` -> 8 passed.
- Browser smoke: `/workspaces` route guard redirected to `/login?redirect=%2Fworkspaces`; login page rendered.
