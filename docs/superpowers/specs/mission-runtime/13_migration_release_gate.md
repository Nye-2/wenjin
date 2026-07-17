# 13 Migration / Release Gate Spec

Status: Implemented; production deployment acceptance pending
Updated: 2026-07-17

Implementation outcome: production paths were deleted/migrated, migrations 086-107 form one head, and the strict scanner reports zero findings. A clean Docker drop/reseed deployment is the only supported baseline; 107 rejects non-empty development data before installing cumulative Mission accounting and atomic chat billing. Release still requires the persisted live probe for all enabled models, complete backend/frontend suites, and a real-provider multi-turn browser chain covering chat authorization/settlement, Mission start, steer, subagents, stage acceptance, pause/resume, preview, user review, commit, evidence, artifacts, trace, and panel demand.
Depends on: all mission-runtime specs

## Goal

Cut over to MissionRuntime cleanly. Because the project is still in development, runtime compatibility layers are not allowed. Old execution data can be dropped/reseeded. Demo preservation, if required, must use one offline importer.

## Cutover Baseline

The following pre-cutover paths were deleted or reshaped. This list is migration history; `docs/current/architecture.md`, `AGENTS.md`, and the executable anti-compat scanner are the current authorities.

```text
backend/src/execution/engine.py
backend/src/services/execution_service.py
backend/src/services/execution_commit_service.py
backend/src/dataservice/review_api.py
backend/src/dataservice_client/contracts/review.py
backend/src/dataservice_client/execution_client.py
backend/src/dataservice_client/contracts/execution.py
backend/src/tools/builtins/launch_feature.py
backend/src/agents/lead_agent/v2/runtime.py
backend/src/agents/lead_agent/v2/compiler.py
backend/src/runtime/runs/*
backend/src/gateway/services/run_*
backend/src/gateway/routers/runs.py
backend/src/gateway/routers/thread_runs.py
backend/src/gateway/routers/workspace_rooms.py
backend/src/dataservice/domains/operations/outbox.py
backend/src/dataservice/domains/operations/models.py (DataServiceOutboxEvent)
backend/src/services/search/sources/model_web_search.py
backend/src/database/models/model_catalog.py
frontend/lib/execution-run-view.ts
frontend/stores/execution-store.ts
frontend/lib/execution-commit.ts
frontend/lib/change-set-view.ts
frontend/lib/api/v2/runs.ts
```

## Cutover Sequence

1. Freeze old execution/lead-agent feature work.
2. Rename/reshape existing gateway run transport as ChatTurnRun; keep it out of Mission history.
3. Add the four DataService Mission tables, bounded snapshot contract, immutable item ledger, lease epoch fencing, and mission client contracts.
4. Migrate execution-linked DataService domains: credit, sandbox, source/provenance, Prism, review, task, memory, rooms, run history.
5. Drop/reseed development execution data.
6. Implement MissionStore transaction boundary, domain-scoped idempotency keys, command cursors, `next_wakeup_at`, bounded MissionDriveSlice, reconciler, and stale-driver fencing; delete the unused DataService operations domain and all three tables.
7. Redesign Model Catalog around ModelCapabilityProfile and add real strict-tool/native-search probes.
8. Implement MissionRuntime start/resume/cancel and bounded continuation.
9. Change WorkspaceAgent to create/resume MissionRun.
10. Move useful LeadAgent/TeamKernel code into SubagentRuntime/ToolOrchestrator/StageQualityRuntime.
11. Implement atomic MissionReviewItem/MissionCommit, canonical review statuses, preview retention, partial batch outcomes, and delete runtime ReviewBatch/ChangeSet.
12. Harden short-lived Sandbox operation containers and content-addressed environments.
13. Switch frontend to MissionView.
14. Delete old execution runtime write paths.
15. Delete old launch_feature launcher and assistant-text tool-call parsing.
16. Delete old execution frontend projection/store.
17. Run anti-compat scan, live endpoint contract probes, and E2E.
18. Update `docs/current/*` to declare MissionRuntime current.

## Allowed Temporary Artifacts

- migration script for drop/reseed
- optional offline importer for demo execution history
- test fixture adapters
- historical docs

## Forbidden Temporary Artifacts

- dual-write MissionRun and ExecutionRecord
- old execution API redirecting to mission API
- frontend "if mission else execution" fallback
- old provider enum mapped to new web search
- ChatTurnRun persisted as DataService mission/run truth
- ReviewBatch or ChangeSet retained as mission review/commit truth
- accepted_ids bridge
- node_states_json bridge
- runtime serializer hydrating old fields
- second execution stream
- second commit channel
- MissionTurn or MissionEvent persistence table
- mutable MissionItem lifecycle rows
- MissionRun status duplicated inside snapshot JSON
- raw trace/token/stdout history stored as semantic MissionItems
- DataService operations outbox/generic-idempotency/migration-report domain retained beside mission/domain truth
- long-lived sandbox container/session treated as mission truth
- text/XML/Markdown parsed as an executable model tool call
- manually asserted native-search capability without a live receipt probe
- old LLM `provider_protocol`/`supports_*` flags mirrored beside ModelCapabilityProfile

## Anti-Compat Scan

Release gate should fail production runtime code on these patterns unless allowlisted in migration/tests/docs:

```text
ExecutionRecord
ExecutionNodeRecord
node_states_json
accepted_ids
accepted_unit_ids
launch_feature
LeadAgentRuntime
compile_graph
TaskReport.review_packet as commit
ReviewBatch runtime
ChangeSet runtime
Semantic Scholar
curated_academic
deep_search
source_type provider enum history
MissionRunStatus.awaiting_user_review
MissionRunStatus.committing
MissionRunStatus.blocked
DataServiceOutboxEvent
DataServiceIdempotencyKey
DataServiceMigrationReport
append_outbox_event
chat/completions + tools.web_search_preview
assistant text -> runtime tool call
MissionReviewItem.status=auto_staged|regenerate|save_draft_only
ModelCatalog LLM supports_tools/supports_json_* compatibility hydration
```

Do not use broad raw-string bans such as `fallback`, `legacy`, or `compat` across the whole repository. They create false positives for normal error handling and OpenAI-compatible model support. The release gate should scan semantic runtime patterns in production code only, with explicit allowlists.

Allowlist locations:

```text
docs/**
tests/**
scripts/migration/**
scripts/offline_import/**
generated/**
.next/**
node_modules/**
__pycache__/**
```

Even in allowlisted locations, wording should make clear the old path is historical.

## Release Gates

Backend:

- MissionRun is the only durable long-task creation path.
- ChatTurnRun is short-lived transport only and is not persisted to DataService mission tables; `thread_turn_billings` persists financial authorization only, survives thread deletion as audit truth, and never enters Mission history.
- Canonical conversation messages are never bulk rebuilt; attachment metadata uses one atomic DataService patch, and long-task context stays in Mission checkpoints.
- A required actor-bound client `request_id` survives reconnect; duplicate HTTP launch is deduplicated before interruption/dispatch, payload drift conflicts, no run-id/random billing-key fallback exists, and dual authorization response loss is compensated by that stable key.
- Chat admission persists an actor-global request index and dispatch intent before broker publication; gateway crash, ambiguous publication, replay, and reconciler republish remain at-least-once without duplicate durable effects. Gateway hydration is read-only, execution-owner lease loss fences stale terminal effects, and Redis unavailability causes bounded worker retry.
- Chat authorization, user-message append, hold, exact non-zero usage, assistant append, capped settlement, release/expiry, rollback, and settled replay pass atomic lifecycle tests.
- Mission cumulative accounting is DataService-owned and cannot be reset by runtime snapshots.
- MissionStore transaction tests pass.
- One non-terminal foreground mission per thread and one active driver per mission are enforced.
- Lease epoch fencing, duplicate queue/command delivery, reconciler recovery, and stable operation idempotency tests pass.
- MissionDriveSlice continuation, safe-yield, command polling, DB-time lease, prefetch=1, and broker visibility/hard-limit margin tests pass.
- Publish-after-commit queue loss recovers from `next_wakeup_at`; no unused operations model/table/repository remains.
- Snapshot bound and scalar/snapshot non-duplication tests pass; MissionItem immutability tests pass.
- Context checkpoint restores stage/evidence/pending state without full transcript, and stale memory is excluded from mission context.
- ToolCatalog is the only runtime descriptor source; unknown tools fail explicitly, all calls use ToolOrchestrator, and no subagent/harness path bypasses operation identity or policy.
- ModelCapabilityProfile live probes gate strict tools and native search; provider prose/URLs without structured receipts fail.
- ReviewCommitRuntime idempotency tests pass.
- Protected domain writes validate `MissionWriteAuthority` inside the target transaction.
- Terminal review rework creates a stage-scoped child Mission and preserves unaffected passed stages.
- Item-level batch partial-success and preview TTL cleanup tests pass.
- Existing-target commits enforce base revision/hash and stale previews cannot overwrite newer content.
- Sandbox manifest tests pass.
- Sandbox production preflight proves rootless/equivalent daemon, non-root/cap-drop/no-new-privileges/read-only-root/resource/network controls, and protected control mounts.
- Permission pause/resume tests pass.
- No old execution write path imported by runtime.
- No ReviewBatch/ChangeSet runtime review path remains.
- No old source provider enum or deep-search import route remains in runtime.
- MissionReviewItem persists only `pending/accepted/rejected/needs_more_evidence/committed/superseded`; policy/actions/UI selection are separate.

Frontend:

- MissionView is the only workbench mission projection.
- No lifecycle facts in UI stores.
- Mission Console never imports ChatTurnRun API contracts.
- Mission Console closed/peek/expanded browser tests pass.
- Review mode UI cannot batch-accept high-risk items.
- Trace tab lazy-loads item pages.
- Review/commit summaries never mutate completed MissionRun execution status.

Docs:

- `docs/current/architecture.md` updated after code cutover.
- `docs/current/workspace-current-state.md` updated after code cutover.
- Overview and specs do not contradict current docs after cutover.

## Drop/ReSeed Plan

Development:

```text
stop workers
drop old execution-related tables/data
create mission tables
rename/delete execution-linked fields in credit/sandbox/source/provenance/Prism/review/task/memory/rooms/run-history domains
seed mission policies/stage contracts
restart DataService/gateway/worker
run E2E smoke
```

Demo preservation if needed:

```text
read old execution rows offline
write archived MissionRun summary rows
do not import node_states_json as active ledger
do not enable runtime reads of old execution tables
```

## E2E Acceptance

One browser case must cover:

1. Enter SCI workspace.
2. Welcome state appears.
3. User asks for literature gap and innovation direction.
4. WorkspaceAgent starts MissionRun.
5. Mission Console opens in peek/running state.
6. Subagent activity appears with stable display names.
7. Evidence/search/tool failures are product-language, not raw provider errors.
8. Mission produces review items.
9. User switches review mode or accepts selected items.
10. High-risk evidence/claim cannot be accepted by batch.
11. Commit writes selected low-risk item.
12. Refresh restores MissionView.
13. Trace can be opened lazily.
14. SSE disconnect or dropped projection event restores from MissionView plus item cursor.
15. Worker lease takeover rejects stale writes and does not duplicate tool/sandbox/commit effects.
16. A failed quality loop returns safe partial outputs and does not advance the stage.
17. A command sent during a running slice is applied after its durable cursor even when the notification is dropped.
18. A selected model with malformed strict tool args cannot start a tool-requiring mission and is not silently replaced.
19. When a native-search endpoint is configured, the case asserts a real search receipt plus clickable citation/source metadata; otherwise the literature release gate remains explicitly blocked by OQ1.

## Done Definition

The migration is done only when:

1. New mission tests pass.
2. Browser E2E passes.
3. Anti-compat scan passes.
4. Old execution write paths are deleted.
5. `docs/current/*` are updated.
6. No user-visible UI says capability grid, lead agent, execution node, blocked/high risk, provider error, or schema id in the default flow.
7. ChatTurnRun appears only in transport code and diagnostics, never in Mission Console or Mission History.
8. ReviewBatch / ChangeSet do not appear in runtime review or commit APIs.
9. MissionRun uses only `created/planning/running/waiting/completed/failed/cancelled`; review and commit are separate axes.
10. MissionEvent/ChatTurnRun/queue loss is recoverable without a second persistent event or run store.
11. Raw trace and old review preview content follow bounded, redacted TTL storage; accepted artifacts and audit metadata remain.
12. MissionRun records resolved model, `low/medium/high/xhigh` effort, and prompt/policy/tool/sandbox version refs.
13. ToolOrchestrator owns every runtime tool call; no legacy search registry, direct room-write tool, or unknown-tool LLM downgrade remains.
14. Every production tool/search action comes from a provider-structured frame under a versioned, probed ModelCapabilityProfile.
15. Long missions survive multiple bounded drive slices; no Celery task or long-lived container owns the mission lifecycle.
16. DataService operations scaffolding is removed; MissionStore/domain unique keys are the sole dispatch/idempotency authorities.
