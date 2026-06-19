# Academic Harness v2 Implementation Plan

**Goal:** Implement the 1/2/5/6 slice from `2026-06-19-academic-harness-v2-brief-claim-map-prompt-design.md`: research brief, claim/evidence packet, academic workspace map, and Prompt Pack v2.

**Architecture:** Keep the current chain: Chat Agent -> `launch_feature` -> ExecutionRecord -> Lead Agent / TeamKernel -> `expert_report` -> `review_packet` -> ResultCard / rooms / Prism. Add structure inside existing contracts and projections. Do not add a new runner, execution stream, frontend store, embedding router, or commit path.

**Implementation rule:** Migrate SCI first-wave skills directly to the new contract. Do not add long-lived fallback prompt formats or parallel compatibility adapters.

---

## Scope

In scope:

- `research_brief.v1`
- `claim_inventory.v1`
- `evidence_packet.v1`
- `academic_workspace_map.v1`
- `ResearchStateV1` enrichment
- `ExpertReportV1` nested academic payloads
- deterministic claim/evidence validation
- SCI first-wave Prompt Pack v2 migration
- compact frontend projection for supported / needs-confirmation / blocker groups

Out of scope:

- capability-derived sandbox permission profiles
- full append-only tool trajectory
- embedding-based routing
- user-facing raw debug logs
- second save/commit channel for `review_packet`

---

## Phase 1: Contracts And Sanitizers

**Files**

- Create `backend/src/agents/harness/research_brief.py`
- Create `backend/src/agents/harness/claim_evidence.py`
- Create `backend/src/contracts/workspace_academic_map.py`
- Modify `backend/src/contracts/team_expert.py`
- Modify `backend/src/agents/harness/research_state.py`
- Modify `backend/src/agents/contracts/task_report.py` only if review packet needs claim grouping fields

**Tasks**

- [x] Add Pydantic models for `ResearchBriefV1`.
- [x] Add Pydantic models for `ClaimInventoryV1`, `EvidencePacketV1`, and gate decisions.
- [x] Add Pydantic models for `AcademicWorkspaceMapV1`.
- [x] Extend `ExpertReportV1` with optional `research_brief_delta`, `claim_inventory`, and `evidence_packet`.
- [x] Extend `sanitize_expert_report()` to accept nested structures and bound payload sizes.
- [x] Extend `ResearchStateV1` to carry `research_brief`, `workspace_map_summary`, `claim_inventory`, `evidence_packet`, and unresolved blockers.
- [x] Add deterministic helper `validate_claim_evidence_alignment()` for missing evidence refs, weak expert-only support, numeric artifact gaps, and blocker/warn/pass.

**Tests**

- Create `backend/tests/agents/harness/test_research_brief.py`
- Create `backend/tests/agents/harness/test_claim_evidence.py`
- Create `backend/tests/contracts/test_workspace_academic_map.py`
- Extend `backend/tests/contracts/test_team_expert.py`
- Extend `backend/tests/agents/harness/test_research_state.py`

**Acceptance**

- Invalid enums reject.
- Host paths and secrets are scrubbed by existing sanitizer boundaries.
- Large claim/evidence lists are bounded.
- Unsupported or broken evidence refs are converted into deterministic warnings/blockers.

---

## Phase 2: Workspace Map Builder

**Files**

- Create `backend/src/services/workspace_academic_map_service.py`
- Use existing workspace room services/models as read sources
- Modify TeamKernel run-start path to request a bounded map
- Optionally expose debug-only function for tests, not a default UI endpoint

**Tasks**

- [x] Build map from available Library/source metadata.
- [x] Include Prism project/section summary when available.
- [x] Include Memory, Decisions, Tasks summaries.
- [x] Include sandbox datasets/scripts/artifacts only from manifest/provenance metadata.
- [x] Enforce strict bounds and exclude full text/raw logs.
- [x] Add freshness timestamp and token budget hints.

**Tests**

- Create `backend/tests/services/test_workspace_academic_map_service.py`
- Verify map excludes full content and raw logs.
- Verify map includes stable ids, source metadata, section paths, and artifact provenance.
- Verify map stays bounded with large input collections.

**Acceptance**

- The map can be built for an empty workspace.
- The map can be built for a populated SCI workspace.
- The map is deterministic and small enough for every Lead run.

---

## Phase 3: TeamKernel Integration

**Files**

- Modify `backend/src/agents/lead_agent/v2/team/kernel.py`
- Modify `backend/src/agents/lead_agent/v2/team/member_context.py`
- Modify `backend/src/agents/lead_agent/v2/team/expert_runtime.py`
- Modify `backend/src/agents/lead_agent/v2/output_mapping.py`
- Modify `backend/src/agents/harness/research_task_eval.py`

**Tasks**

- [x] Build `research_brief.v1` at TeamKernel run start from launch params, capability metadata, workspace map, and user objective.
- [x] Put brief + workspace map summary into member context.
- [x] Normalize nested claim/evidence packets from expert reports.
- [x] Merge claim/evidence state after each member.
- [x] Preserve current result output mapping and Prism review item path.
- [x] Update review packet mapping to produce warning/blocker preview items from claim/evidence gate decisions.
- [x] Add final eval for claim/evidence packet alignment.

**Tests**

- Extend `backend/tests/agents/lead_agent/v2/test_team_member_context.py`
- Extend `backend/tests/agents/lead_agent/v2/test_team_kernel.py`
- Extend `backend/tests/agents/lead_agent/v2/test_output_mapping.py`
- Extend `backend/tests/agents/harness/test_research_task_eval.py`

**Acceptance**

- Later members receive compact brief and current evidence state.
- Unsupported claims become review packet warnings/blockers.
- Review packet remains read-only preview unless backed by `outputs[]` or canonical `review_items`.

---

## Phase 4: Prompt Pack v2 Migration

**Files**

- Modify SCI first-wave skill seeds:
  - `backend/seed/skills/query-planner.yaml`
  - `backend/seed/skills/research-scout.yaml`
  - `backend/seed/skills/source-screener.yaml`
  - `backend/seed/skills/literature-synthesizer.yaml`
  - `backend/seed/skills/citation-auditor.yaml`
  - `backend/seed/skills/method-design.yaml`
  - `backend/seed/skills/evidence-analyst.yaml`
  - `backend/seed/skills/reproducibility-auditor.yaml`
  - `backend/seed/skills/manuscript-architect.yaml`
  - `backend/seed/skills/manuscript-writer.yaml`
  - `backend/seed/skills/review-critic.yaml`
- Modify `backend/tests/architecture/test_academic_harness_catalog.py`

**Tasks**

- [x] Add global Prompt Pack v2 instructions.
- [x] Add skill-specific output obligations from the spec.
- [x] Require nested `claim_inventory` and `evidence_packet` in the declared output contract.
- [x] Keep persona/user-facing public profile free of schema ids and raw harness internals.
- [x] Remove vague instructions that encourage unsupported summaries.

**Tests**

- Seed architecture test validates required prompt contract phrases.
- Seed architecture test validates required output schema fields.
- Existing integration seed tests still pass.

**Acceptance**

- SCI first-wave skills instruct experts to mark `insufficient_evidence` instead of fabricating.
- Literature, citation, method, evidence, reproducibility, writing, and review skills all emit claim/evidence-ready reports.

---

## Phase 5: Frontend Projection

**Files**

- Modify `frontend/lib/execution-run-view.ts`
- Modify `frontend/lib/workspace-result-preview.ts`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/useLiveWorkflowViewModel.ts`
- Modify relevant LiveWorkflowPanel views only if projection needs new grouped copy

**Tasks**

- [x] Project brief summary into right-panel run detail when present.
- [x] Group claim/evidence packet preview into "已支持 / 需确认 / 阻断".
- [x] Show evidence preview with source title, year/source key, excerpt, and limitation.
- [x] Keep diagnostic packet items non-commit by default.
- [x] Avoid raw schema names and internal ids in default UI.

**Tests**

- Extend `frontend/tests/unit/lib/execution-run-view.test.ts`
- Extend `frontend/tests/unit/lib/workspace-result-preview.test.ts`
- Extend `frontend/tests/unit/v2/live-workflow-view-model.test.ts`
- Extend `frontend/tests/e2e/golden-path.spec.ts`

**Acceptance**

- Users can see what is supported, what needs confirmation, and what blocks progress.
- Save buttons still operate only on real result outputs or canonical review items.

---

## Phase 6: Verification And Review

**Backend**

```bash
cd backend && uv run --extra dev pytest \
  tests/agents/harness/test_research_brief.py \
  tests/agents/harness/test_claim_evidence.py \
  tests/contracts/test_workspace_academic_map.py \
  tests/contracts/test_team_expert.py \
  tests/agents/harness/test_research_state.py \
  tests/agents/lead_agent/v2/test_output_mapping.py \
  tests/agents/lead_agent/v2/test_team_member_context.py \
  tests/agents/lead_agent/v2/test_team_kernel.py \
  tests/agents/harness/test_research_task_eval.py \
  tests/architecture/test_academic_harness_catalog.py \
  tests/integration/test_capability_skill_seeds.py -v
```

**Frontend**

```bash
cd frontend && npm run test:unit -- \
  tests/unit/lib/execution-run-view.test.ts \
  tests/unit/lib/workspace-result-preview.test.ts \
  tests/unit/v2/live-workflow-view-model.test.ts
cd frontend && npm run typecheck
cd frontend && WENJIN_E2E_BROWSER_CHANNEL=chrome npx playwright test tests/e2e/golden-path.spec.ts -g "review packet" --project=chromium
```

**Review**

- Rebuild code-review graph.
- Inspect impact radius.
- Confirm no second runner/store/commit path was introduced.
- Confirm docs/current facts are updated only after implementation is real.

