# 07 ReviewCommitRuntime Spec

Status: Implemented
Updated: 2026-07-17

Implementation outcome: item-level decisions, review modes, conflict checks, partial commit, receipts, and four explicit materialization operations are implemented. Old batch/change review ownership and unimplemented target branches were deleted.
Depends on: `03_dataservice_mission_schema.md`, `08_mission_console_frontend.md`, `10_sandbox_vnext.md`

## Goal

Replace `ExecutionCommitService` and result-card commit semantics with mission-native review and commit:

```text
MissionOutput / ResearchToolOutcome
  -> MissionReviewItem
  -> ReviewDecision
  -> MissionCommit
  -> Prism write / Source import / WorkspaceAsset write
```

Review is item-level in storage. Frontend can batch low-risk actions.

`ReviewBatch` and `ChangeSet` are not retained as runtime review facts. Their useful duties move as follows:

| Old duty | New owner |
|---|---|
| batch grouping | MissionView projection / frontend selection |
| accepted/rejected item truth | MissionReviewItem decision fields |
| change application | MissionCommit orchestrating one registered domain operation |
| apply handlers | Prism / Source / Asset domain services |
| audit trail | MissionItem + MissionCommit |
| idempotency | one MissionCommit per atomic MissionReviewItem with stable commit key |

## Cutover Baseline

The table records pre-cutover ownership and the completed target action; it is not a map of current runtime paths.

| Current file | Current responsibility | Target action |
|---|---|---|
| `backend/src/services/execution_commit_service.py` | Commits accepted TaskReport outputs using `accepted_ids` / `accepted_unit_ids` | Replace with ReviewCommitRuntime over mission review items |
| `backend/src/services/change_unit_materializer.py` | Materializes ChangeUnit into rooms | Move useful apply logic behind MissionCommit; remove execution-temp state and ChangeUnit runtime identity |
| `backend/src/services/change_unit_materializer.py` / `frontend/lib/change-set-view.ts` | Change set review projection | Fold into MissionReviewItem projection |
| `backend/src/dataservice/review_api.py`, `backend/src/dataservice_client/contracts/review.py` | ReviewBatch / ReviewItem domain tied to execution/runtime review | Remove as task review SSOT; move necessary apply handlers into room/domain services |
| `frontend/app/(workbench)/workspaces/[id]/components/review-changes/ChangeSetReviewPanel.tsx` | Review UI | Rebind to mission review items and user review modes |
| `frontend/lib/execution-commit.ts` | Commit state using accepted ids | Replace with mission review decision/commit client |

## Review Modes

Workspace/mission review mode:

```text
review_all
balanced_default
auto_draft
```

Rules:

- `review_all`: every candidate waits for confirmation.
- `balanced_default`: low-risk organization/summaries are suggested-selected in MissionView/UI but still wait for confirmation; high-risk stays unselected and manual.
- `auto_draft`: eligible low-risk draft-only content receives an auditable policy acceptance and ordinary draft-target MissionCommit automatically; high-risk still manual.

Non-bypassable high risk:

```text
citation
claim
evidence
experiment conclusion
statistical result
Prism structural edit
patent claim
long-term memory
external data access
```

## MissionReviewItem Fields

```text
review_item_id
mission_id
source_item_seq
output_key
target_kind
target_room
target_ref
base_revision_ref
base_hash
title
summary
risk_level
status
review_required_reason
preview_json
preview_ref
preview_hash
preview_expires_at
decision_json
decided_by
decided_at
```

`checkbox` and batch selection are UI only. The decision fields on MissionReviewItem are the current review fact; every decision command also appends an immutable MissionItem for audit.

Canonical row statuses are:

```text
pending | accepted | rejected | needs_more_evidence | committed | superseded
```

`auto_draft` is policy, `regenerate`/`save_draft_only` are actions, and suggested/default checkbox state is a MissionView projection. They are not persisted as additional statuses.

MissionView can derive `suggestedSelected` and a selection revision from review mode/risk. The frontend owns only the user's temporary checkbox selection; acceptance still requires a decision command or an auditable `auto_draft` policy decision.

Storage, API, and user-facing runtime names use `MissionReviewItem`. Generic `ReviewItem` may survive only as an internal room-domain object that neither owns mission review state nor appears in mission APIs.

Large diff/version content is stored behind `preview_ref` with TTL. Once an item is accepted, rejected, superseded, or committed and its grace period ends, preview content is deleted; decision metadata, target, hashes, and commit audit remain.

For an existing target, MissionReviewItem captures the base revision/hash used to build the preview. Room/domain apply performs an optimistic precondition check. A mismatch marks the old item `superseded` and produces a new candidate from the current target; it never overwrites a newer user or mission edit.

## MissionCommit

```text
commit_id
mission_id
review_item_id
commit_key
actor_user_id
targets_json
status
error_json
attempt_count
attempt_token
attempt_started_at
attempt_expires_at
created_at
completed_at
```

One MissionCommit applies one atomic MissionReviewItem. Idempotency is based on a stable item-scoped commit key; duplicate requests return the existing result instead of writing the domain twice.

MissionCommit status is `pending | applying | committed | failed | cancelled`. The row stores current apply truth; every attempt/result also appends an immutable MissionItem audit entry. A failed row may retry under the same commit key and increments `attempt_count`.

Frontend batch acceptance submits multiple independent items. Successful commits remain successful if another item fails, and only failed items are retried. There is no batch-level all-or-nothing claim and no distributed transaction across target domains.

Review and commit may continue after MissionRun execution is terminal. They append audit MissionItems and update review/commit summaries, but cannot reopen the agent loop or mutate the terminal execution status/timestamp. During a non-terminal Mission, rework is an ordered `review_feedback` command. After terminal completion, `needs_more_evidence`, `regenerate`, or a stale-target commit creates an idempotent linked child Mission. The source stage is resolved from the reviewed ledger item; the child invalidates that stage and its transitive dependency closure while inheriting unaffected passed stages. Missing lineage fails closed rather than replaying every stage.

Every target-domain write receives one `MissionWriteAuthority` containing Mission, review item, commit, and attempt token. The target DataService transaction revalidates accepted review state, applying commit lease/expiry, workspace ownership, and token before materialization. No domain infers authority from provenance strings or a commit id alone.

## Commit Targets

The active surface is closed and explicit:

| Operation | Target | Commit boundary |
|---|---|---|
| `documents.upsert_prism_file` | new or existing Prism file | Prism DataService transaction |
| `documents.insert_visual_asset` | existing Prism selection | Prism DataService transaction |
| `library.import_source` | new Library source | Source DataService transaction |
| `assets.create_from_preview` | new WorkspaceAsset | Asset DataService transaction plus content-addressed preview copy |

ReviewCommitRuntime orchestrates these accepted write requests and does not implement domain internals. Memory, Room, Task, and Sandbox materializers are absent until a complete producer, preview contract, target transaction, receipt, and test chain exists; placeholder branches are forbidden.

## Rejected / Needs Evidence

User actions and their persisted effects:

| Action | Persisted effect |
|---|---|
| accept | item -> `accepted`; optional MissionCommit |
| reject | item -> `rejected` |
| needs more evidence | item -> `needs_more_evidence`; create/resume research command |
| regenerate | old item -> `superseded`; create a stage command and later a new candidate |
| save draft only | accept an already draft-target item, or supersede it and create a new draft-target candidate before commit |

`needs_more_evidence` is not a commit. For a non-terminal Mission it appends durable feedback and wakes the same loop; for a terminal Mission it creates a linked child MissionRun scoped to the exact source stage and dependency closure.

## Deletions

- `accepted_ids`
- `accepted_unit_ids`
- runtime `ReviewBatch`
- runtime `ChangeSet`
- execution change-set review endpoints
- result-card local committed truth
- review packet item id as commit id
- execution temp `change_unit_materialization` as long-lived recovery path
- Redis-only commit truth

Best-effort locks can remain, but MissionCommit is durable truth.

## Migration

1. Create mission_review_items and mission_commits tables.
2. Replace execution commit endpoint with mission review decision endpoint.
3. Build MissionReviewItem creation from MissionOutput/ResearchToolOutcome.
4. Wire only complete producer-to-target operations through an item-scoped MissionCommit; delete incomplete targets.
5. Update frontend review panels to operate on review item ids.
6. Delete execution commit code path.
7. Delete runtime ReviewBatch / ChangeSet code paths instead of wrapping them.

## Tests

- `balanced_default` blocks high-risk accept-all.
- `auto_draft` cannot auto-commit claim/evidence/citation.
- Review status validation rejects policy/action/UI values such as `auto_draft`, `regenerate`, `save_draft_only`, and `default_checked`.
- Duplicate commit key is idempotent.
- Rejected item never writes a target domain.
- Needs-more-evidence resumes an in-loop waiting stage or creates a linked child mission after terminal execution.
- Terminal continuation never guesses a source stage, preserves unaffected passed stages, and returns the child Mission id to chat/frontend.
- Every protected target rejects missing, stale, expired, mismatched, or cross-workspace `MissionWriteAuthority`.
- Prism item requires preview/apply boundary.
- Commit failure records failed MissionCommit and does not fake success in UI.
- A batch with mixed outcomes preserves successful items and retries only failed items.
- Expired preview content can be regenerated from the current target without reviving old version compatibility data.
- Stale base revision/hash cannot overwrite a newer target and requires a newly reviewed candidate.
- No runtime API exposes ReviewBatch or ChangeSet as mission review truth.
