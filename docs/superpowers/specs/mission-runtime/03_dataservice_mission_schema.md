# 03 DataService Mission Schema Spec

Status: Implemented
Updated: 2026-07-17

Implementation outcome: the four-table aggregate and typed DataService client/store are live; linked domains were migrated by 088, auxiliary tasks by 090, review/commit consistency by 091, physical index integrity by 095, aggregate references by 096, final workspace/runtime cutovers by 097-101, review policy projection by 102, DataService concurrency fencing by 103, required Mission budgets plus atomic chat billing by 107, the unused workspace discipline field removed by 108, stale snapshot-level subagent summaries removed by 109, and duplicate Mission evidence projections consolidated by 110. Development history is drop/reseed. A clean empty-database migration through 110 is the release baseline.
Depends on: `02_mission_runtime.md`, `07_review_commit_runtime.md`, `13_migration_release_gate.md`

## Goal

Bring DataService into the refactor and replace the execution aggregate with a compact Mission domain. The schema must optimize for performance and architecture convergence, not historical compatibility.

Development-stage execution history can be dropped/reseeded. If demo data must be preserved, use one offline importer. Runtime code must not hydrate old execution fields.

## Cutover Baseline

The table records pre-cutover ownership and the completed target action; it is not a map of current runtime paths.

| Current file | Current responsibility | Target action |
|---|---|---|
| `backend/src/dataservice_client/execution_client.py` | Client methods for executions, nodes, compute sessions, analytics | Replace execution methods with mission domain methods; compute session methods kept only if still needed outside mission |
| `backend/src/dataservice_client/client.py` | Mixin-heavy root DataService client | Prefer domain client composition for Mission; do not grow the root shell with another large mission mixin |
| `backend/src/dataservice_client/contracts/execution.py` | Execution payload contracts | Replace with mission contracts |
| `backend/src/dataservice_app/routers/execution.py` | Internal execution router and analytics | Replace with mission router; remove execution analytics or re-create mission analytics |
| `backend/src/services/execution_service.py` | Gateway-facing ExecutionService facade | Delete/replace with MissionService |
| DataService execution routers/domain | Stores executions, nodes, events, leases, commit state | Drop/reseed and create mission tables |
| `backend/src/dataservice/domains/operations/*` | Defines generic idempotency, outbox, and migration-report tables with no production consumers | Delete the domain, models, migrations, exports, and table-existence tests; mission/domain unique keys own idempotency and dispatch intent |
| execution-linked domains: credit, sandbox, source/provenance, Prism, review, task, memory, rooms, run history | Store `execution_id`, `source_execution_id`, `ingest_execution_id`, or `related_execution_ids` | Rename to mission provenance fields or delete if obsolete in the same cutover |
| `frontend/lib/api/types.ts` | ExecutionRecord/RunRecord types | Replace with MissionRun/MissionView types |

## Table Strategy

Use four core mission runtime tables:

```text
mission_runs
mission_items
mission_review_items
mission_commits
```

Do not create:

- one table per tool
- one table per subagent role
- one table per mission item type
- a DataService table for `ChatTurnRun`
- separate node state table
- separate event outbox table
- separate sandbox artifact table

Artifacts, sources, Prism files, rooms, assets, and memory remain in their existing domains.

`ChatTurnRun` is not part of this schema. It is Redis/memory transport state with short TTL; the durable recovery surface is canonical Thread messages, `ThreadTurnBilling`, and MissionRun. The billing table is financial authorization/settlement truth only. It must not acquire transport, Mission stage, evidence, review, or history fields.

No separate outbox is used. A durable command MissionItem plus MissionRun runnable/lease/`next_wakeup_at` state records dispatch intent before queue publish. Queue messages are at-least-once wake-up hints, and an indexed reconciler republishes runnable or expired-lease missions. The existing unused DataService operations domain (`dataservice_idempotency_keys`, `dataservice_outbox_events`, `dataservice_migration_reports`) is deleted. Mission creation, command append, tool operation, review, and commit use their own scoped unique keys instead of one generic idempotency table.

## `mission_runs`

Owns mission lifecycle and fast recovery snapshot.

Suggested columns:

```text
mission_id uuid primary key
parent_mission_id uuid null references mission_runs(mission_id)
workspace_id uuid not null
thread_id uuid null
user_id uuid not null
workspace_type text not null
mission_policy_id text not null
title text not null
objective text not null
status text not null
review_mode text not null default 'balanced_default'
active_stage_id text null
model_id text not null
reasoning_effort text not null
snapshot_json jsonb not null default '{}'
runtime_context_json jsonb not null default '{}'
context_checkpoint_ref text null
pending_review_count integer not null default 0
evidence_count integer not null default 0
artifact_count integer not null default 0
active_subagent_count integer not null default 0
mission_idempotency_key text null
last_command_seq bigint not null default 0
last_applied_command_seq bigint not null default 0
next_wakeup_at timestamptz null
lease_owner text null
lease_epoch bigint not null default 0
lease_expires_at timestamptz null
dispatch_owner text null
dispatch_epoch bigint not null default 0
dispatch_expires_at timestamptz null
state_version bigint not null default 0
last_item_seq bigint not null default 0
created_at timestamptz not null
updated_at timestamptz not null
started_at timestamptz null
completed_at timestamptz null
```

Indexes:

```text
primary key (mission_id)
unique (workspace_id, mission_idempotency_key) where mission_idempotency_key is not null
index (workspace_id, updated_at, mission_id)
index (user_id, updated_at, mission_id)
index (thread_id, created_at desc)
partial index (next_wakeup_at, dispatch_expires_at) for runnable statuses
partial index (lease_expires_at, dispatch_expires_at) for active leased statuses
partial unique (thread_id) where status in ('created', 'planning', 'running', 'waiting')
```

Avoid JSON indexes unless a query proves necessary. Workspace and user keyset-history indexes serve the two canonical history projections; do not add alternate history indexes. Scalar columns are canonical and must not be duplicated in `snapshot_json`. `model_id` and `reasoning_effort` are scalar truth; `runtime_context_json` stores prompt, policy, exemplar, ModelCapabilityProfile, tool-schema, and sandbox-image refs/hashes. It is immutable after mission start except through an explicit runtime-context migration.

`last_command_seq` advances when a durable command is appended. `last_applied_command_seq` advances only with the state/audit transaction that applies it. `next_wakeup_at` is the reconciler cursor for initial dispatch, continuation, retry, and lease recovery; it is cleared for waiting-without-resume and terminal missions. Lease claim/recovery comparisons use PostgreSQL time, not worker clocks.

`snapshot_json.resource_usage` is the bounded, DataService-owned cumulative projection. Only append of `model_call_started`, `operation_claim`, `subagent_spawned`, and `usage_receipt` changes it. Any supplied replacement snapshot must omit it or match the current projection exactly; DataService reinstalls the latest projection after every item batch.

Model-call lifecycle is projected from append-only `mission_items`, not a separate table. `model_call_started` increments the dispatch count; exactly one later `usage_receipt` or `model_call_terminal` closes that identity. DataService validates the complete binding and item phase, adopts only exact replay after a lost response ACK, and rejects orphan, duplicate, divergent, or cross-terminal writes. `GET /internal/v1/missions/{mission_id}/model-calls` is the canonical typed projection with `open | receipt | failed | cancelled | unresolved` state.

Operation claim, model/subagent dispatch, stage advancement, waiting transition, voluntary lease release, and terminal mutation all consult this projection under the Mission row lock. Open calls block terminalization. Open and unresolved calls block later dispatch, stage advancement, waiting, or voluntary release. A terminal Mission with exact receipts settles their measured usage regardless of success or failure. A terminal Mission with unresolved calls records `billing_reconciliation_required`; an existing reservation remains `reserved`, its expiry is removed, and no settlement transaction or `billing_settled` item is written until explicit reconciliation exists.

## `thread_turn_billings` (financial, not Mission)

One row owns a stable actor-bound chat-turn idempotency key, request hash, user/thread/workspace/model identity, user and assistant message ids, frozen pricing/authorization quote, reserved free tokens and credits, exact normalized usage, settlement transaction, expiry, and `authorized | settled | released | expired` state. User counters and holds live on the locked user row. Authorization writes the user message and hold in one transaction; completion writes the assistant, exact usage, capped charge, ledger transaction, and terminal state in one transaction. Authorization retry and release-by-idempotency-key use the same user-first lock order, so response-loss compensation observes any concurrent commit. The settled charge can never exceed the reserved hold, settlement is forbidden at or after expiry, and a settled row must reference its immutable credit transaction. Expiry/release and exact trailing-message rollback are idempotent.

This table has unique idempotency/message/transaction constraints, a partial `(expires_at, id)` index for active authorization cleanup, and covering indexes for `user_id`, `thread_id`, and `workspace_id`. `thread_id` is intentionally a soft audit reference: thread deletion atomically releases active holds but never deletes financial history. Message references become null only when the containing thread is intentionally deleted. It is not included in the four-table Mission aggregate and is never projected as a run.

Canonical `thread_messages` rows are append-oriented conversation history and must never be replaced wholesale. Attachment preprocessing patches message metadata atomically under the same thread lock used by chat writes. Research-task context compaction belongs to Mission checkpoints; Chat has no parallel context state machine.

## `mission_items`

Owns append-only process ledger.

Suggested columns:

```text
id uuid primary key
mission_id uuid not null references mission_runs(mission_id) on delete cascade
seq bigint not null
item_type text not null
operation_id text null
phase text not null
stage_id text null
producer text null
summary text null
risk_level text null
payload_json jsonb not null default '{}'
payload_ref text null
created_at timestamptz not null
```

Indexes:

```text
unique (mission_id, seq)
index (mission_id, item_type, stage_id, seq desc)
index (mission_id, operation_id, seq) where operation_id is not null
```

The unique `(mission_id, seq)` index already serves item pagination; do not duplicate it with a created-at index. Rows are immutable after append. Operation lifecycle uses multiple rows sharing `operation_id`; terminal phases are `completed`, `failed`, or `cancelled`. Large payloads externalize to `payload_ref`; token deltas, raw reasoning, stdout/stderr, and wire logs are not semantic MissionItems. The main UI should not need full payload JSON.

## `mission_review_items`

Owns staged review state and user decisions. This table replaces `accepted_ids` and review-packet-as-commit behavior.

Suggested columns:

```text
review_item_id uuid primary key
mission_id uuid not null references mission_runs(mission_id) on delete cascade
source_item_seq bigint null
output_key text not null
target_kind text not null
target_room text null
target_ref text null
base_revision_ref text null
base_hash text null
title text not null
summary text null
risk_level text not null
status text not null
review_required_reason text null
preview_json jsonb not null default '{}'
preview_ref text null
preview_hash text null
preview_expires_at timestamptz null
decision_json jsonb null
decided_by uuid null
decided_at timestamptz null
created_at timestamptz not null
updated_at timestamptz not null
```

Indexes:

```text
index (mission_id, status, risk_level)
index (mission_id, target_room)
```

The composite unique `(mission_id, review_item_id)` is intentional: `mission_commits` uses it as a composite foreign-key target so a commit cannot reference a review item from another Mission. It is an ownership constraint, not a query-optimization duplicate.

Statuses:

```text
pending
accepted
rejected
needs_more_evidence
committed
superseded
```

`auto_draft` is a review policy, `regenerate`/`save_draft_only` are user actions, and checkbox/default selection is projection/UI state; none is an additional row status. Under `auto_draft`, an eligible low-risk item receives an auditable policy decision to `accepted` and an ordinary draft-target MissionCommit. One MissionReviewItem is one atomic domain-write candidate. Existing-target writes carry `base_revision_ref` and/or `base_hash`; room/domain apply rejects a stale precondition and the runtime creates a new candidate from the current target. Large diff/version content is stored behind `preview_ref` with TTL. After accept/reject/commit and the configured grace period, preview content is deleted while decision metadata, preview hash, target, and commit audit remain.

## `mission_commits`

Owns idempotent write records.

Suggested columns:

```text
commit_id uuid primary key
mission_id uuid not null references mission_runs(mission_id) on delete cascade
review_item_id uuid not null references mission_review_items(review_item_id)
commit_key text not null
status text not null
actor_user_id uuid not null
targets_json jsonb not null default '{}'
error_json jsonb null
attempt_count integer not null default 0
attempt_token text null
attempt_started_at timestamptz null
attempt_expires_at timestamptz null
created_at timestamptz not null
completed_at timestamptz null
```

Indexes:

```text
unique (mission_id, commit_key)
unique (review_item_id)
index (mission_id, status)
```

Batch UI actions create independent MissionCommit rows for the selected items. Successful rows remain committed when another item fails; retries reuse the same stable commit key and cannot duplicate domain writes.

## Mission DataService API

Internal endpoints should replace `/internal/v1/executions*` for mission runtime:

```text
POST   /internal/v1/missions
GET    /internal/v1/missions/{mission_id}
GET    /internal/v1/workspaces/{workspace_id}/missions
POST   /internal/v1/missions/{mission_id}/items/append
POST   /internal/v1/missions/{mission_id}/pause
POST   /internal/v1/missions/{mission_id}/resume
POST   /internal/v1/missions/{mission_id}/review-items
POST   /internal/v1/missions/{mission_id}/review-decisions
POST   /internal/v1/missions/{mission_id}/commits
GET    /internal/v1/missions/{mission_id}/items
POST   /internal/v1/missions/{mission_id}/items/by-seqs
```

Client shape:

```text
dataservice.missions.create(...)
dataservice.missions.append_items(...)
dataservice.missions.apply_review_decisions(...)
dataservice.missions.commit(...)
```

Do not add a giant `MissionDataServiceClientMixin` to the root client if composition is available. The root client may expose a `missions` domain client factory, but runtime modules should not import execution client contracts after cutover.

## Execution-Linked Domain Migration

The mission cutover includes every DataService field that currently stores execution provenance:

| Current pattern | Target |
|---|---|
| `execution_id` for product long task | `mission_id` |
| `execution_node_id` / node id | `mission_item_seq` or `stage_id` depending on provenance |
| `source_execution_id` | `source_mission_id` |
| `ingest_execution_id` | `ingest_mission_id` |
| `related_execution_ids` | `related_mission_ids` |
| `holder_execution_id` | `holder_mission_id`, or delete when the lease is chat-transport-only |
| polymorphic credit reservation scopes | one Mission-owned reservation with unique `mission_id` |
| `run_history.execution_id` | delete; mission list reads `mission_runs` |

Domain-specific requirements:

- Credit reservations attach to a required, unique `mission_id`; the table has no polymorphic scope or item-level ownership fields. Each Mission reservation carries the frozen Mission/model/global pricing snapshot copied from the immutable admission receipt, and terminal settlement reads no mutable active policy. `ChatTurnRun` never owns feature-task credits.
- Sandbox jobs attach to `mission_id` and optional `mission_item_seq`; sandbox leases use mission or sandbox job ownership, not execution ownership.
- Source/provenance records use `ingest_mission_id` / `ingest_mission_commit_id` and domain source kinds; `source_run_id`, `source_artifact_id`, and old provider-only history values are absent from runtime projections.
- Prism, task, memory, and room write provenance use `source_mission_id` or `mission_commit_id`.
- Workspace memory keeps source, observed time, confidence, and staleness metadata; only reviewed, non-stale facts enter mission context.
- Existing `ReviewBatch` rows are dropped/reseeded; runtime review state lives in `mission_review_items`.
- Run History table is removed or archived; user-facing history reads `mission_runs` summary.

No runtime code may hydrate old execution fields into mission fields. Demo preservation, if needed, is one offline importer.

Client mixin:

```text
backend/src/dataservice_client/mission_client.py
backend/src/dataservice_client/contracts/mission.py
```

Do not keep mission methods in `AsyncDataServiceClient` main shell.

## MissionStore API

Runtime-facing service:

```text
create_run()
apply_initial_admission()
load_run_snapshot()
find_by_mission_idempotency_key()
claim_run_lease()
heartbeat_run_lease()
release_run_lease()
claim_runnable_batch_skip_locked()
release_dispatch_claim()
append_items_and_update_snapshot()
append_command_once()
list_unapplied_commands()
apply_commands_and_advance_cursor()
pause_run()
resume_run()
claim_operation()
get_operation()
finish_operation()
checkpoint_run()
create_review_items()
apply_review_decisions()
start_commit()
finish_commit()
list_runs_summary()
list_items_page()
list_items_by_seqs()
get_view()
```

## Cutover Rules

Delete same cutover:

- execution client write methods
- execution node endpoints
- node state hydration
- execution commit endpoints
- execution run history endpoints
- execution analytics that are not mission-backed
- `backend/src/dataservice/domains/operations/*`, its three tables, exports, migrations, and table-existence tests

If analytics are still needed, rebuild on mission tables after cutover.

## Tests

DataService:

- workspace-scoped unique mission idempotency key.
- only one non-terminal foreground mission per thread.
- `(mission_id, seq)` ordering and uniqueness.
- transaction appends items and updates snapshot/version.
- MissionItem rows cannot be updated after append.
- snapshot rejects duplicated scalar lifecycle fields and oversized payloads.
- snapshot rejects any caller attempt to replace DataService-owned cumulative resource usage.
- cumulative count ceilings block the next dispatch before a model/tool/subagent side effect; a token receipt crossing `stop_after_total_tokens` is preserved and blocks subsequent dispatch.
- stale lease epochs cannot update MissionRun or attach terminal operation results.
- review decisions update only matching mission review items.
- commit key is idempotent per atomic MissionReviewItem.
- stale base revision/hash cannot overwrite a newer room/domain version.
- list workspace missions uses `(workspace_id, updated_at)` index; scheduler uses `(status, next_wakeup_at, lease_expires_at)`.
- reconciler claims due rows with `SKIP LOCKED`, database time, and bounded batches.
- command append and apply cursors survive a dropped queue hint.
- publish-after-commit recovery works from `next_wakeup_at` with no outbox table.
- review item statuses exclude `auto_draft`, `regenerate`, `save_draft_only`, and checkbox selection state.
- chat authorization/message/hold and assistant/usage/transaction settlement are each atomic and idempotent; release, expiry, rollback, and settled replay do not double-charge.

Migration:

- dev drop/reseed removes execution tables or old data paths; migration 107 fails fast on non-empty users, pricing, Mission, or credit data.
- old execution client methods are not imported by runtime.
- anti-compat scan fails on `accepted_ids`, `node_states_json`, execution-node writes, `deep_search`, `Semantic Scholar`, and `curated_academic` runtime provider paths.
