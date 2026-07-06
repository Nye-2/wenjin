# Wenjin Review Modes and Harness Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Wenjin from a runnable academic workbench into a safer, deeper, student-friendly research production system with user-selectable write modes, Codex-style expandable changes, strong evidence gates, and reliable execution/commit semantics.

**Architecture:** Introduce a durable ChangeSet/ChangeUnit layer between execution output and workspace rooms. Sandbox execution remains approval-free; room writes are governed by workspace/run write mode plus server-side risk policy. Research outputs become trustworthy only after final evidence gates, claim/evidence validation, and explicit confirmation for high-risk changes.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, LangGraph, TeamKernel, Next.js 16, React 19, Zustand, Tailwind, existing Wenjin DataService and execution stores.

## Implementation Status

Completed in this branch:

- Phase 0 safety patch: frontend auto-commit removed, backend unsafe `accept_all` guarded, Review tab restored, hidden/background outputs no longer silently save.
- Phase 1.1 ChangeSet contracts.
- Phase 1.2 workspace/run write-mode storage through settings and launch metadata.
- Phase 1.3 server-side change policy.
- Phase 1.4 ChangeSet projection from TaskReport/review packets/sandbox artifacts into execution result.
- Phase 1.5 ChangeSet review APIs: get, accept, reject, undo.
- Phase 1.6 core Review & Changes UI: ChangeSet projection, expandable unit detail, accept/reject/undo actions, and accepted-unit commit payloads.
- WriteModeSelector UI in Settings and launch receipt, including persisted workspace write mode and run launch metadata display.
- Backend review hardening from code review: ChangeSet acceptance is now enforced before historical output-id commits, blocked units cannot be bridged into commits, review/commit payload updates preserve each other, workspace membership is checked on commit/review mutation, and commit/review id lists are bounded.
- Phase 2.2 claim/evidence validation: core academic claims require evidence refs, `supported` claims require verified or explicitly reviewable evidence, result interpretation claims require artifact refs, and shallow expert-judgment-only support is blocked or warned.
- Phase 2.1 final-report gate: after TeamKernel assembles `TaskReport` and `review_packet`, required `claim_evidence_alignment` / `review_packet_completeness` surfaces now run as deterministic final gates; failures downgrade the run to `failed_partial` and mark outputs unchecked. `review_packet_completeness` also now requires a committable non-warning deliverable instead of treating previewable warning text as complete.
- Frontend review follow-up: ChangeSet-to-output commit bridging now requires all units for an output to be accepted and rejects any blocked unit; ResultCard, CompletedView, and LiveWorkflowPanel use the same visible-output/default-checked rule when no ChangeSet exists; Review tab remains visible after pending review count reaches zero; `draft_applied` units are inspectable but read-only.
- Atomic review-state patch foundation: DataService now exposes a locked `execution.result` patch endpoint limited to `change_set_review_state`; `ChangeSetReviewService` uses this path when available, preserving concurrent `commit_state` updates instead of rewriting the whole result payload. The patch contract rejects high-risk keys such as `commit_state`.
- Frontend projection convergence: ChangeSet response patches now include fresh `unit_states`, commit-state precedence is centralized with local responses taking priority, output default-check normalization is shared, and ChangeSet pending/actionable predicates live in `change-set-view` instead of view components. `LiveWorkflowPanel` writeback state was extracted to a focused hook to keep the panel under the architecture size guard.
- ChangeSet retention convergence: accepted/discarded writeback now compacts temporary review payloads after `commit_state` is durable. Full `change_set`, `change_set_review_state`, and `unit_states` are deleted through a DataService finalize whitelist, while a small `change_set_receipt` keeps schema, summary, unit ids, output ids, commit time, and compact room targets without full diff or rollback content.
- Native ChangeUnit materialization: ChangeUnits now carry explicit `materialization.operation/payload`; ChangeSet commits must use `accepted_unit_ids`; blocked or unaccepted units cannot be saved; accepted units write directly to Library, Documents/Prism, Memory, Decisions, Tasks, Sandbox, and Settings through typed DataService room APIs. ChangeSet executions reject the stale `accepted_ids` bridge.
- Commit path bridge cleanup: the remaining no-ChangeSet historical output path no longer stages decision/task `RoomCandidatePayload`s. It writes decisions/tasks through typed room APIs, so production commit code no longer depends on `stage_and_apply_room_candidates`.
- ChangeUnit commit recovery: `ExecutionCommitService` now keeps a temporary `change_unit_materialization` progress payload while a commit is in flight. Each completed unit patches its actual room targets; failed commits record only completed materializations; retry after recovery skips completed units and resumes remaining ones. Successful finalize deletes the temporary progress with full ChangeSet review payloads, leaving only compact receipt/commit state. Decision/task direct writes use stable `execution:{execution_id}:unit:{change_unit_id}` provenance keys and DataService room replay to avoid duplicate records.
- Commit undo consistency: Sandbox and Settings targets, which currently have no automatic reverse API, are recorded as explicit `revert_skipped` manual-revert targets instead of silently reporting zero reverted writes.
- Runtime reliability foundation: DataService protects durable `commit_state` and compact `change_set_receipt` from late ordinary result writes, and prevents compacted ChangeSet blobs from being resurrected after commit. `ExecutionService` now respects cancellation/terminal states on start/complete, and `ExecutionEngineV2` stops before runtime if `start_execution` acknowledges a pre-run cancellation.
- Execution CAS foundation: `ExecutionUpdateCommand` / `ExecutionUpdatePayload` now support `expected_status`; DataService locks and conditionally applies updates when this field is present. `start_execution` and `complete_execution` use this guard and read back the latest record if a concurrent cancellation or terminal transition wins.
- Execution worker lease hardening: capability workers now claim `runtime_state.execution_lease` through DataService before running, heartbeat while `ExecutionEngineV2` is active, abort on lost ownership, and startup reconciliation skips live leases while reclaiming missing/expired leases. Terminal reconciliation clears stale lease runtime state instead of retaining obsolete worker history.
- React subagent failure convergence: transient model-provider failures no longer synthesize manuscript-like degraded drafts. They now return a structured, retryable, non-committable failure result with `default_checked=false`.
- Harness Phase 2 depth hardening: nested `claim_inventory` / `evidence_packet` refs are projected into ReviewPacket summaries; final `claim_evidence_alignment` now requires the quality surface marker rather than only non-empty ref fields; `review_packet_completeness` now requires an anchored substantive deliverable, not just title/summary text.
- Frontend review convergence: writeback sends `accepted_unit_ids` for ChangeSet runs; low/medium-risk bulk selection excludes blocked/high-risk units; review/change UI is Chinese-first; workflow surfaces no longer reference `--v2-*` tokens and ChangeSet labels are localized.
- Frontend materialized-unit convergence: no-output Sandbox/Settings ChangeUnits are saved through `accepted_unit_ids` only when they carry explicit `materialization`; review-only units are not bridged into commit, and frontend commit-state parsing/test mocks now use the full write-room set including Sandbox and Settings.
- No-preview writeback convergence: CompletedView and chat ResultCard now expose workspace-save controls for accepted materialized ChangeUnits without visible result previews and submit `accepted_unit_ids`, so Settings/Sandbox changes are not stranded behind preview-only UI conditions.
- Figure preview UX hardening: result preview projection now carries safe `previewUrl` values when available, rejects unsafe inline/script URLs, and the renderer displays real images for HTTPS or same-origin API/workspace URLs while retaining the workspace-path placeholder fallback.
- Frontend run projection cleanup: live/historical run merging now trusts the latest authoritative review projection instead of preserving stale pending-review maxima, preventing completed review badges from reappearing after acceptance.
- Cross-workspace seed harness normalization: representative thesis, proposal, patent, software copyright, and math modeling main workflows now declare `research_evidence` surfaces and enforcement, with architecture tests preventing regression to shallow evidence-only tags.
- Student-side review UX cleanup: ChangeSet detail panels now show localized target/action/write-route summaries and readable change/provenance rows instead of raw diff/provenance JSON; result cards use student-facing copy for document files and run labels.
- Release-gate convergence: Phase 6 core gate now explicitly runs ChangeSet writeback/review tests, execution worker lease/CAS tests, and frontend Review & Changes projection/writeback tests, so the 1-5 optimization surfaces are protected by a visible release check instead of only ad hoc targeted commands.
- Final-gate evidence visibility: failed final research-evidence gates now create non-committable warning review items, which the ChangeSet builder projects into blocked Review & Changes units alongside the report error.
- Execution-node durability convergence: `execution_nodes` now has a database uniqueness boundary on `(execution_id, node_id)` and DataService writes nodes through dialect-aware upsert, leaving `ExecutionRecord.node_states_json` as a derived projection rather than a competing source of truth.
- Review accessibility/token cleanup: Review & Changes controls now expose explicit aria labels, saving/review transitions announce through polite live regions, save-copy is student-facing across run/result/completed surfaces, and risk badges use `--wjn-risk-*` / `--wjn-change-*` tokens rather than hard-coded purple risk colors.

Partially complete and intentionally left as follow-up:

- Pending ChangeSet durability remains `execution.result` based for now. This is intentional for the current product stage: unresolved review gates survive refresh/restart, but full review details are not retained after writeback. A future Redis/TTL-backed pending cache can replace or augment this if result payload size becomes a bottleneck.
- Run History is written through execution events rather than reviewable ChangeUnits; the direct room-write path now covers all reviewable durable rooms, while Run History remains the automatic execution ledger.
- Full review-changes component split (`ChangeGroup`, `DocumentDiffPreview`, `EvidenceRiskBadge`) after the API contract settles.
- Phase 2 academic harness hardening beyond current final gates: skill migration, broader final-gate surfaces, and extending research-evidence surface declarations from the representative main workflows to every capability in each workspace type.
- Runtime reliability beyond current guards: undo/retry conditional transitions and broader stuck-run observability.
- Student-facing UX pass beyond review/writeback wording: denser evidence previews and document diff preview.

Not fully executed in this branch:

- Phase 6 broad release-gate suite is configured but not fully run end-to-end in this working session; use the release gate CLI or CI before launch because it includes long frontend build and broad backend integration checks.

---

## Product Decision

Wenjin should support user-selectable write modes, similar in spirit to Codex permission modes:

1. `auto_draft`
   - Sandbox execution and low-risk draft writes happen automatically.
   - The user sees a Codex-style "changed X items" panel and can expand diffs.
   - High-risk academic trust changes still require explicit confirmation.

2. `ask_workspace_write`
   - Sandbox execution still runs without approval.
   - Any write into Documents, Library, Decisions, Memory, Tasks, or Settings asks before applying.
   - Useful for cautious users, supervisors, and high-stakes thesis/patent work.

3. `strict_review`
   - Every room mutation is staged only.
   - Nothing becomes canonical until explicitly accepted.
   - Useful for institutional review, demonstrations, or debugging.

The important distinction is not "agent can run" versus "agent cannot run"; it is "agent can compute in sandbox" versus "agent can modify durable workspace knowledge." Sandbox should not ask during execution. Durable workspace changes should obey mode and risk policy.

## Review Granularity

Do not make review run-level or result-card-level. The durable review unit is `ChangeUnit`:

- Documents: file version, section patch, LaTeX diff, protected-section proposal.
- Library: source import, metadata update, duplicate merge, citation key assignment.
- Evidence/Claims: claim creation, evidence link, support status, citation audit result.
- Memory: single long-term memory fact.
- Decisions: one research decision candidate.
- Tasks: one actionable task candidate.
- Sandbox: script, result table, figure, notebook, trace, dependency lock, hash record.
- Settings: capability/runtime setting change.

`ResultCard` becomes a summary of a `ChangeSet`, not the commit primitive.

## Risk Policy

Server-side policy is authoritative. Frontend projection may improve UX, but must never be the only safety boundary.

Always approval-free:

- Sandbox planning and execution inside configured isolation.
- Reading existing bounded workspace context.
- Producing transient run events, traces, logs, and intermediate node state.

Auto-apply in `auto_draft` if reversible and low risk:

- New draft document versions.
- Generated outline sections that are clearly marked as draft.
- Sandbox artifacts with provenance and hashes.
- Non-canonical preview summaries.

Always requires explicit confirmation before canonical trust:

- Citation correctness, DOI/BibTeX/venue/year metadata if imported from model output.
- Claim support status, novelty claims, numerical findings, method superiority claims.
- Thesis/paper final text replacing protected or user-authored sections.
- Workspace Memory facts.
- Decisions that affect research direction.
- Patent novelty/inventiveness/legal conclusions.
- Software copyright evidence that asserts real screenshots, real authorship, or real dates.

## File Responsibility Map

### Backend Contracts

- Modify `backend/src/agents/contracts/task_report.py`
  - Add risk and commit-policy fields to output/change contracts.
  - Keep backward compatibility only as a migration path inside validators; do not add a second runtime protocol.

- Create `backend/src/contracts/change_set.py`
  - Define `ChangeSet`, `ChangeUnit`, `ChangeTarget`, `ChangeRisk`, `WriteMode`, `ApplyState`, and validation helpers.

- Modify `backend/src/contracts/team_presentation.py`
  - Add presentation fields for Review & Changes: grouped status, risk reasons, expandable diff metadata.

### Backend Services

- Create `backend/src/services/change_policy.py`
  - Central server-side decision function: mode + room + operation + risk + reversibility -> apply/stage/block.

- Create `backend/src/services/change_set_service.py`
  - Build change sets from `TaskReport.outputs`, review packets, sandbox artifacts, and room candidates.
  - Apply low-risk draft changes.
  - Stage high-risk or mode-blocked changes.
  - Provide idempotent accept/reject/undo operations.

- Modify `backend/src/services/execution_commit_service.py`
  - Replace blind `accept_all`.
  - Require explicit `accepted_ids` for high-risk units.
  - Use ChangeSet materialization targets.

- Modify `backend/src/services/execution_service.py`
  - Add expected-status/CAS support for start/complete/cancel.
  - Stop overwriting terminal states without ownership checks.

- Modify `backend/src/dataservice/domains/execution/service.py`
  - Reconcile only stale lease-expired executions.
  - Add worker lease/heartbeat fields or equivalent.

- Modify `backend/src/dataservice/domains/review/service.py`
  - Apply review units with row locks or conditional status transitions.

### Backend Runtime and Harness

- Modify `backend/src/agents/lead_agent/v2/runtime.py`
  - Run final evidence gates after full `TaskReport` assembly.
  - Stage partial outputs as non-default, high-risk review units.
  - Fail missing skill/tool preflight instead of returning empty output.

- Modify `backend/src/agents/lead_agent/v2/team/kernel.py`
  - Add final evidence validation before completed status.
  - Preserve partial review artifacts when quality gates fail.
  - Bind token collector consistently with static graph.

- Modify `backend/src/agents/lead_agent/v2/compiler.py`
  - Resolve tools from capability policy and task spec.
  - Add per-node timeout and cancellation propagation.

- Modify `backend/src/subagents/v2/types/react.py`
  - Remove manuscript-like degraded fallback for transient model failure.
  - Treat missing skill as configuration error.

- Modify `backend/src/agents/harness/claim_evidence.py`
  - Require evidence refs for core academic claims.
  - Reject `supported` claims with no evidence.

- Modify `backend/src/agents/harness/research_task_eval.py`
  - Make `review_packet_completeness` require a task-matched committable deliverable, not just previewable warning text.

- Modify `backend/src/agents/harness/policy.py`
  - Map sandbox mode to required read/list/grep tools as well as run/render tools.

### Seed and Catalog

- Modify `backend/seed/capabilities/math_modeling/math_modeling_paper_pack.yaml`
- Modify `backend/seed/capabilities/thesis/thesis_research_pack.yaml`
- Modify `backend/seed/capabilities/patent/invention_to_patent_draft.yaml`
- Modify `backend/seed/capabilities/patent/prior_art_and_novelty_pack.yaml`
- Modify `backend/seed/capabilities/software_copyright/software_copyright_application_pack.yaml`
- Modify `backend/seed/capabilities/sci/*.yaml`
  - Add or normalize `research_evidence.required_surfaces`.
  - Add explicit tool requirements for tasks that need sandbox/read tools.
  - Add write-risk hints for outputs.

- Modify `backend/seed/skills/*.yaml`
  - Migrate evidence/citation/claim-related skills to `expert_report`.

### Frontend

- Create `frontend/lib/change-set-view.ts`
  - Project backend ChangeSets into UI groups: applied draft, staged, blocked, accepted, rejected.

- Create `frontend/stores/change-set-store.ts`
  - Cache change sets, optimistic accept/reject/undo state, and per-run write mode.

- Modify `frontend/stores/execution-store.ts`
  - Attach change set summaries to execution records.

- Modify `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`
  - Remove auto-commit.
  - Restore Review tab as `Review & Changes`.
  - Show mode snapshot and change summary.

- Modify `frontend/app/(workbench)/workspaces/[id]/components/CompletedView.tsx`
  - Remove automatic `accept_all`.
  - Render expandable change groups.

- Modify `frontend/app/(workbench)/workspaces/[id]/components/ResultCard.tsx`
  - Treat cards as summaries; actions route through ChangeSet APIs.

- Create `frontend/app/(workbench)/workspaces/[id]/components/review-changes/`
  - `ReviewChangesPanel.tsx`
  - `ChangeGroup.tsx`
  - `ChangeUnitRow.tsx`
  - `DocumentDiffPreview.tsx`
  - `EvidenceRiskBadge.tsx`
  - `WriteModeSelector.tsx`

- Modify `frontend/lib/execution-run-view.ts`
  - Unify pending-review counts from ChangeSet projection.

- Modify `frontend/app/(workbench)/workspaces/[id]/components/result-preview/ResultPreviewRenderer.tsx`
  - Render real image/document previews where safe URLs exist.

- Modify `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`
  - Add workspace-type-specific guidance and accessible button labels.

- Modify `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/styles.ts`
  - Replace `--v2-*` and hard-coded risk colors with `--wjn-*` semantic tokens.

---

## Phase 0: Safety Patch

**Purpose:** Stop silent high-risk writes before building the full ChangeSet model.

### Task 0.1: Remove frontend auto-commit

**Files:**
- Modify `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/CompletedView.tsx`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/ResultCard.tsx`
- Test `frontend/tests/live-workflow-review-gate.test.tsx`

- [x] Add failing tests that render completed executions with committable previews and assert `commitExecutionOutputs` is not called automatically.
- [x] Remove `useEffect` blocks that call commit on completion.
- [x] Replace automatic save copy with explicit review/save actions.
- [x] Run targeted frontend review/writeback unit suites.
- [x] Run `cd frontend && npm run typecheck`.

### Task 0.2: Make backend reject unsafe `accept_all`

**Files:**
- Modify `backend/src/services/execution_commit_service.py`
- Modify `backend/src/agents/contracts/task_report.py`
- Test `backend/tests/services/test_execution_commit_service.py`

- [x] Add tests:
  - `accept_all` rejects outputs where `default_checked is False`.
  - `accept_all` rejects evidence/citation/claim/manual-review outputs.
  - explicit `accepted_ids` still works for allowed outputs.
- [x] Add centralized bulk-accept safety policy for result outputs.
- [x] In `accept_all`, select only if every output is bulk-safe; otherwise raise a user-safe error.
- [x] Run targeted execution commit service tests.

### Task 0.3: Restore visible Review tab

**Files:**
- Modify `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/WorkbenchHeader.tsx`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/useLiveWorkflowViewModel.ts`

- [x] Add `review` as a first-class tab.
- [x] Remove mapping from `review` to `run`.
- [x] When a completed run has staged items, focus Review & Changes by default.
- [x] Verify pending count is visible and consistent.

---

## Phase 1: ChangeSet and User Write Modes

**Purpose:** Replace checkbox result cards with Codex-style expandable changes and user-selectable write behavior.

### Task 1.1: Add ChangeSet contracts

**Files:**
- Create `backend/src/contracts/change_set.py`
- Test `backend/tests/contracts/test_change_set.py`

- [x] Define `WriteMode = Literal["auto_draft", "ask_workspace_write", "strict_review"]`.
- [x] Define `ChangeRisk = Literal["low", "medium", "high", "critical"]`.
- [x] Define `ApplyState = Literal["draft_applied", "staged", "accepted", "rejected", "blocked", "undone"]`.
- [x] Define `ChangeTarget` with `room`, `object_type`, `object_id`, `path`, `section_id`.
- [x] Define `ChangeUnit` with `id`, `target`, `action`, `risk`, `risk_reasons`, `default_apply_state`, `requires_confirmation`, `diff`, `provenance`, `rollback`.
- [x] Define `ChangeSet` with `execution_id`, `workspace_id`, `write_mode`, `units`, `summary`, `created_at`.
- [x] Add model validation tests for high-risk units requiring a risk reason.

### Task 1.2: Add write mode storage

**Files:**
- Modify existing workspace settings model/service, or create migration-backed workspace preference field if no suitable field exists.
- Modify `backend/src/dataservice/domains/workspace/*`
- Test workspace settings service.

- [x] Add workspace-level default write mode.
- [x] Add run-level mode snapshot into execution launch metadata.
- [x] Default new workspaces to `auto_draft`.
- [x] Expose update/get APIs through existing settings flow.

### Task 1.3: Implement server-side change policy

**Files:**
- Create `backend/src/services/change_policy.py`
- Test `backend/tests/services/test_change_policy.py`

- [x] Implement `decide_change_apply_state(mode, target, action, risk, reversible, protected)`.
- [x] Assert sandbox artifacts can be draft-applied in `auto_draft`.
- [x] Assert memory facts require confirmation in all modes unless explicitly system-owned and low-risk.
- [x] Assert claim/citation/evidence trust changes require confirmation in all modes.
- [x] Assert `strict_review` stages every durable room write.

### Task 1.4: Build ChangeSets from TaskReports

**Files:**
- Create `backend/src/services/change_set_service.py`
- Modify `backend/src/execution/engine.py`
- Modify `backend/src/services/execution_commit_service.py`
- Test `backend/tests/services/test_change_set_service.py`

- [x] Convert existing `ResultOutput` kinds into `ChangeUnit`s.
- [x] Convert review packet items into non-committable or confirmation-required units.
- [x] Convert sandbox artifacts into draft-applied units when provenance is present.
- [x] Persist change set into execution result first; use a table-backed store in the next task if result payload size becomes risky.
- [x] Return change set summary in execution API responses.

### Task 1.5: Add ChangeSet APIs

**Files:**
- Modify gateway execution/review router files.
- Add router tests.

- [x] `GET /executions/{id}/changeset`.
- [x] `POST /executions/{id}/changeset/accept` with explicit unit ids.
- [x] `POST /executions/{id}/changeset/reject` with explicit unit ids.
- [x] `POST /executions/{id}/changeset/undo` with explicit unit ids.
- [x] Ensure all mutations are idempotent.

### Task 1.6: Build Review & Changes UI

**Files:**
- Create `frontend/lib/change-set-view.ts`
- Create `frontend/stores/change-set-store.ts`
- Create `frontend/app/(workbench)/workspaces/[id]/components/review-changes/*`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`

- [x] Render groups: Draft applied, Needs confirmation, Blocked, Saved, Rejected.
- [x] Render expandable unit details and diff/provenance.
- [x] Add "Accept selected", "Reject selected", and "Undo" actions.
- [x] Add `WriteModeSelector` in Settings and run launch receipt.
- [x] Make mode copy user-facing: "自动写入草稿", "写入前询问", "严格审阅".

---

## Phase 2: Academic Harness Hardening

**Purpose:** Prevent shallow academic outputs from being marked complete or trusted.

### Task 2.1: Run final evidence gates after report assembly

**Files:**
- Modify `backend/src/agents/lead_agent/v2/runtime.py`
- Modify `backend/src/agents/lead_agent/v2/team/kernel.py`
- Modify `backend/src/agents/harness/research_task_eval.py`
- Test TeamKernel and static runtime report completion.

- [x] Add final gate evaluation after `TaskReport` has outputs, review items, and review packet for final-report surfaces.
- [x] If required final-report gate fails, set status `failed_partial`.
- [x] Include final gate failures in report errors.
- [x] Add deterministic tests that missing or warning-only review packets fail completeness.
- [x] Add runtime/kernel tests for failed claim alignment downgrading completion.
- [x] Surface final gate evidence as first-class blocked Review & Changes units.

### Task 2.2: Strengthen claim/evidence validation

**Files:**
- Modify `backend/src/agents/harness/claim_evidence.py`
- Modify `backend/src/contracts/team_expert.py`
- Test claim/evidence validators.

- [x] Core claim types require at least one evidence ref.
- [x] `supported` claims require verified or explicitly reviewable evidence.
- [x] Artifact-required claim types require artifact refs.
- [x] Evidence refs cannot point only to background or expert judgment for high-risk claims.

### Task 2.3: Migrate critical skills to `expert_report`

**Files:**
- Modify `backend/seed/skills/source-quality-auditor.yaml`
- Modify `backend/seed/skills/claim-verifier.yaml`
- Modify `backend/seed/skills/patent-strategist.yaml`
- Modify related proposal, software, math modeling, and thesis skills.
- Test seed/catalog lint.

- [x] Each migrated skill outputs `wenjin.expert_report.v1`.
- [x] Each prompt says no evidence -> `insufficient_evidence`.
- [x] Each schema includes bounded claims, evidence refs, artifact refs, and warnings.

### Task 2.4: Extend research evidence surfaces beyond SCI

**Files:**
- Modify capability YAML files listed in Seed and Catalog section.
- Test catalog loading.

- [x] Math modeling: add data/code/figure consistency, reproducibility, statistical robustness, AI-use disclosure.
- [x] Thesis: add citation strength, semantic preservation, argument chain, protected-section safety.
- [x] Patent: add prior-art provenance, claim support, enablement, drawing consistency.
- [x] Proposal: add feasibility evidence, risk evidence, milestone realism.
- [x] Software copyright: add real screenshot/source provenance and non-fabrication gates.

---

## Phase 3: Agent Runtime Reliability

**Purpose:** Make missing config, long tasks, cancellation, and provider failures visible and recoverable.

### Task 3.1: Add capability preflight

**Files:**
- Modify `backend/src/agents/lead_agent/v2/runtime.py`
- Modify `backend/src/agents/lead_agent/v2/team/policy.py`
- Test runtime preflight.

- [x] Validate every core task has a resolvable skill unless explicitly `allow_skillless`.
- [x] Validate required tools resolve to callable tools.
- [x] Validate required research surfaces are known.
- [x] Fail launch with configuration error before spending credits if preflight fails.

### Task 3.2: Fix static graph tool resolution

**Files:**
- Modify `backend/src/agents/lead_agent/v2/compiler.py`
- Modify `backend/src/agents/harness/policy.py`
- Test math modeling sandbox task gets read/run/render tools.

- [x] Merge task `tools`, capability runtime tools, sandbox policy tools, and skill-declared tools through one policy resolver.
- [x] Include read/list/glob/grep when sandbox mode is required.
- [x] Keep denylist and isolation policy authoritative.

### Task 3.3: Remove manuscript-like degraded fallback

**Files:**
- Modify `backend/src/subagents/v2/types/react.py`
- Test transient provider failure behavior.

- [x] Replace degraded manuscript with structured failure output.
- [x] Mark output as non-committable and high risk.
- [x] Preserve retry context and user-safe explanation.

### Task 3.4: Add node timeouts and cancellation propagation

**Files:**
- Modify `backend/src/agents/lead_agent/v2/compiler.py`
- Modify `backend/src/agents/lead_agent/v2/team/kernel.py`
- Modify harness tool context objects.
- Test cancellation.

- [x] Wrap subagent nodes in `asyncio.wait_for`.
- [x] Race long tool calls against abort signal.
- [x] Persist `cancelled` node state.
- [x] Release lead-busy promptly.

---

## Phase 4: Execution, Commit, and Data Consistency

**Purpose:** Make production recovery and room materialization durable.

### Task 4.1: Add execution lease and CAS

**Files:**
- Use existing `ExecutionRecord.runtime_state` / `worker_task_id`; no new compatibility columns or migration.
- Modify `backend/src/services/execution_service.py`
- Modify `backend/src/dataservice/domains/execution/service.py`
- Test recovery races.

- [x] Add worker lease owner and heartbeat timestamp.
- [x] `start_execution` requires expected status `pending`.
- [x] `complete_execution` requires active lease or expected running status.
- [x] Reconcile only lease-expired executions and missing-lease historical in-flight rows.

### Task 4.2: Make node state durable and unique

**Files:**
- Modify `backend/src/database/models/execution_node.py`
- Modify DataService node upsert code.
- Add migration and tests.

- [x] Add unique constraint `(execution_id, node_id)`.
- [x] Use database upsert.
- [x] Treat `node_states_json` as derived projection, not source of truth.

### Task 4.3: Harden room commit saga

**Files:**
- Modify `backend/src/services/execution_commit_service.py`
- Modify relevant DataService room APIs.
- Test half-commit retry.

- [x] Track actual materialized targets per unit.
- [x] Add idempotency keys `(execution_id, change_unit_id)` for room writes.
- [x] Failed commit records only completed materializations.
- [x] Retry resumes remaining units.

### Task 4.4: Lock review item apply

**Files:**
- Modify `backend/src/dataservice/domains/review/repository.py`
- Modify `backend/src/dataservice/domains/review/service.py`
- Test concurrent apply.

- [x] Use row locks or conditional update from `pending` to `applying`.
- [x] Add provenance unique keys for decisions/tasks.
- [x] Return idempotent success for already-applied units.

---

## Phase 5: Student-Facing UX and Research Guidance

**Purpose:** Make the system feel like a research coach, not an execution dashboard.

### Task 5.1: Rewrite progress language

**Files:**
- Modify `frontend/lib/execution-run-view.ts`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/RunView.tsx`

- [x] Replace technical progress with task-language stages: preparing materials, searching evidence, drafting, checking quality, waiting for confirmation.
- [x] Completed state says either "N items need confirmation" or "Saved to X rooms."

### Task 5.2: Add guided intake per workspace

**Files:**
- Modify `backend/src/agents/chat_agent/prompts/system.py`
- Modify routing/minimum context seed fields.
- Modify `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`

- [x] Add math modeling prompt boundary.
- [x] Add intake chips/checklists for thesis, math modeling, patent, software copyright.
- [x] Keep model selector secondary; prioritize task guidance.

### Task 5.3: Improve previews

**Files:**
- Modify `frontend/app/(workbench)/workspaces/[id]/components/result-preview/ResultPreviewRenderer.tsx`
- Add preview API if required.

- [x] Render actual images via safe resource URLs.
- [x] Render document excerpts and diffs.
- [x] Explain unavailable previews in Chinese with next action.

### Task 5.4: Mobile and accessibility pass

**Files:**
- Modify `frontend/app/(workbench)/workspaces/[id]/page.tsx`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`
- Modify review changes components.

- [x] Mobile uses Chat / Run / Review segmented navigation instead of split half-screen.
- [x] Add aria labels for icon buttons.
- [x] Add keyboard support for split resizing.
- [x] Add `aria-live` for saving and review status.

### Task 5.5: Token and visual system cleanup

**Files:**
- Modify `frontend/app/globals.css`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/styles.ts`
- Modify result preview styles.

- [x] Add `--wjn-risk-*`, `--wjn-review-*`, and `--wjn-change-*` tokens.
- [x] Remove new-surface usage of `--v2-*`.
- [x] Remove hard-coded purple risk colors.

---

## Phase 6: Testing, Evaluation, and Release Gates

### Task 6.1: Backend test suite

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/services/test_execution_commit_service.py -v
cd backend && .venv/bin/python -m pytest tests/services/test_change_policy.py -v
cd backend && .venv/bin/python -m pytest tests/services/test_change_set_service.py -v
cd backend && .venv/bin/python -m pytest tests/agents/harness -v
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2 -v
cd backend && .venv/bin/python -m pytest tests/quality -v
```

Expected:

- High-risk `accept_all` tests fail before patch and pass after patch.
- Final evidence gate tests fail shallow outputs.
- Static graph sandbox tool tests prove math modeling can read/run/render.
- Release gate configuration includes ChangeSet writeback, worker lease/CAS, and frontend Review & Changes checks.

### Task 6.2: Frontend test suite

Run:

```bash
cd frontend && npx vitest run
cd frontend && npm run typecheck
cd frontend && npm run build
```

Expected:

- No automatic commit on completion.
- Review & Changes tab renders staged/high-risk/draft-applied groups.
- Write mode selector affects launch payload and UI copy.

### Task 6.3: Integration scenarios

Create integration tests for:

- Completed low-risk run in `auto_draft`: draft document version is applied, high-risk memory remains staged.
- Same run in `ask_workspace_write`: no room writes apply without confirmation.
- Same run in `strict_review`: every unit staged.
- Model provider transient failure: no manuscript-like draft is created.
- Gateway restarts while worker still runs: execution does not flip failed then completed.
- Commit half-fails then retries: no duplicate room objects.

### Task 6.4: Product acceptance checklist

Before release, verify manually:

- A student can run math modeling without approving sandbox steps.
- The student sees "草稿已写入" plus expandable changes.
- A citation/claim cannot become trusted without explicit confirmation.
- Undo works for draft document changes.
- Failed evidence gates explain what is missing.
- Mobile review flow is usable without half-screen trapping.

---

## Recommended Execution Order

1. Phase 0 first. It removes the dangerous behavior immediately.
2. Phase 1 second. It creates the correct product primitive: ChangeSet/ChangeUnit.
3. Phase 2 third. It makes academic trust real.
4. Phase 3 fourth. It prevents shallow or empty runs from looking successful.
5. Phase 4 fifth. It hardens production consistency.
6. Phase 5 can run in parallel after Phase 1 API shapes stabilize.
7. Phase 6 runs continuously, with full release gate after Phase 4 and Phase 5.

## Non-Goals

- Do not expose sandbox as a user console.
- Do not make every sandbox action require approval.
- Do not preserve the old `accept_all` semantics as a compatibility layer.
- Do not add a second router or keyword-routing layer.
- Do not make result cards the durable commit primitive.

## Open Product Choices

1. Whether `auto_draft` should be the default for all users or only new non-institutional workspaces.
2. Whether supervisors/admins can force `strict_review` for managed workspaces.
3. Whether Library imports from external APIs can auto-apply when DOI/source metadata is verified.
4. Whether protected thesis sections should allow draft patch auto-apply or always stage.

## Definition of Done

- Users can choose write mode at workspace and run level.
- Sandbox execution never asks for permission under normal configured policies.
- Durable room writes are represented as ChangeUnits with risk, provenance, diff, and rollback metadata.
- Low-risk draft writes can auto-apply and be expanded/undone.
- High-risk academic trust changes require explicit confirmation server-side.
- No frontend code path can bypass backend risk policy with `accept_all`.
- Required final research evidence gates run on the complete report.
- Missing skill/tool/provider failure cannot produce silent empty or manuscript-like trusted output.
- Execution recovery is lease/CAS protected.
- Core student workflows are understandable without reading raw logs or internal ids.
