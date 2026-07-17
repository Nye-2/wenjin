# 02 MissionRuntime Spec

Status: Implemented
Updated: 2026-07-16

Implementation outcome: bounded drive slices, leases/epochs, ordered commands, wakeups, reconciliation, Mission billing, cumulative resource accounting, events, production composition, and the dedicated `long_running` worker are implemented. No runtime compatibility path remains.
Depends on: `03_dataservice_mission_schema.md`, `06_subagent_runtime.md`, `07_review_commit_runtime.md`, `09_permission_pause.md`

## Goal

MissionRuntime replaces `ExecutionEngineV2 + LeadAgentRuntime` as the product execution runtime. It owns durable mission lifecycle, agent loop boundaries, pause/resume, state snapshot, item ledger, projection events, and cutover to subagents/tools/review/commit.

## Cutover Baseline

The table records pre-cutover ownership and the completed target action; it is not a map of current runtime paths.

| Current file | Current responsibility | Target action |
|---|---|---|
| `backend/src/execution/engine.py` | Fetches ExecutionRecord, calls LeadAgentRuntime, completes execution, appends execution events | Replace with MissionRuntime runner and MissionStore transaction boundary |
| `backend/src/services/execution_service.py` | Execution CRUD, node hydration, commit state, lease, event append | Delete or replace with MissionService backed by DataService Mission domain |
| `backend/src/agents/lead_agent/v2/runtime.py` | Resolves capability, compiles graph/team, returns TaskReport | Split useful execution logic into WorkspaceAgent planning, SubagentRuntime, ToolOrchestrator, StageQualityRuntime |
| `backend/src/agents/contracts/task_brief.py` | Capability launch brief | Replace/rename as MissionSpec |
| `backend/src/agents/contracts/task_report.py` | Runtime output envelope | Replace with MissionOutput / MissionReviewItem candidate / MissionItem payloads |
| `backend/src/task/tasks/execution.py` | Celery entry for execution id | Replace with mission worker entry keyed by mission_id |

## Runtime Model

MissionRuntime uses:

```text
MissionRun scalar + bounded snapshot
immutable MissionItem semantic ledger
transient MissionEvent projection
```

`MissionRun` scalar columns own lifecycle, lease, versions, counters, and timestamps. `snapshot_json` is a bounded recovery payload that does not duplicate those columns. `MissionItem` is the durable ordered semantic ledger. `MissionEvent` is emitted as a transient SSE/UI invalidation hint; reconnect uses MissionView plus MissionItems after the last sequence, not event replay.

`ChatTurnRun` is outside this runtime model. It is a short-lived chat transport record for SSE/cancel/wait and can expire without mission data loss. MissionRuntime may be called from a chat turn, but its durable idempotency and recovery are owned by MissionRun.

## Mission Status

```text
created
planning
running
waiting
completed
failed
cancelled
```

Status is stored once in `mission_runs.status`. Terminal statuses:

```text
completed
failed
cancelled
```

Review and commit are separate status axes:

- A final research execution can be `completed` while MissionReviewItems remain pending.
- In-loop review or clarification that must precede more research uses `status=waiting` plus a durable pending request.
- Commit progress and failures live on MissionCommit and its MissionView summary, not on MissionRun status.
- A recoverable blocker is `waiting`; an unrecoverable stop is `failed` with partial outputs and a structured failure reason.
- Terminal execution status is immutable. Post-terminal review/commit may append audit MissionItems and update review/commit counters or summaries, but it cannot reacquire an agent-loop lease or change execution terminal timestamps.

Use structured detail fields instead of multiplying status values:

```text
waiting_reason: clarification | approval | user_input | permission | external_data | budget | review
degraded_reason: tool_partial | evidence_gap | timeout | rate_limited | budget_capped
failure_reason: repeated_failure | missing_required_source | policy_forbidden | incompatible_runtime | external_state_required
```

`paused`, `needs_input`, `degraded`, `blocked`, `awaiting_user_review`, and `committing` are not MissionRun statuses after cutover. They are represented by `waiting`/`failed`, review/commit summaries, reason fields, and MissionItems.

## Child Mission Continuation

A terminal Mission is immutable. A materially new chat continuation or terminal review rework creates a child `MissionRun(parent_mission_id=...)`; it never reacquires the parent lease. Workspace, thread, user, workspace type, MissionPolicy id, policy content hash, model, effort, and review mode remain server-pinned.

Ordinary continuation inherits passed stage receipts and their canonical accepted lineage. Review-driven continuation additionally carries a server-authored `MissionContinuationDirective` with the source review item ids and exact reset stage ids. MissionRuntime resolves pinned stage instances, invalidates the reset stages plus their transitive downstream dependency closure, and copies only unaffected passes. Dynamic all-item dependencies use the explicit contract count source. A missing, unpassed, or unresolvable source stage rejects creation; the runtime never falls back to replaying every stage.

## MissionStore Transaction

Every state-changing operation must use one MissionStore transaction:

```text
append immutable MissionItem(s)
update MissionRun scalar columns and bounded snapshot_json
update counters/status/version/last_item_seq
commit database transaction
publish transient MissionEvent after commit
```

The database transaction commits before the transient event publish. If event publish fails, `MissionRun` and `MissionItem` remain authoritative; frontend recovers via snapshot refresh and item cursor.

Required optimistic fields:

```text
state_version
last_item_seq
last_command_seq
last_applied_command_seq
next_wakeup_at
lease_owner
lease_epoch
lease_expires_at
mission_idempotency_key
```

One thread can have at most one non-terminal foreground MissionRun. One MissionRun can have only one active driver. Every driver write validates both `state_version` and `lease_epoch`; a stale worker cannot publish a valid result after lease takeover.

Queue delivery is at-least-once. A queue message carries only mission/command identity, and a reconciler re-enqueues runnable or expired-lease missions. Stable command ids and operation keys make duplicate dispatch safe. Mission state/command commit always precedes best-effort queue publish; `mission_runs.next_wakeup_at` makes the publish-after-commit crash window recoverable without an outbox.

Command append and command application are distinct immutable facts. Appending a command advances `last_command_seq`; the active driver polls after `last_applied_command_seq` at every safe loop boundary and advances the cursor only in the same transaction as the resulting state change/audit item. A queue/event hint may wake work sooner but cannot make a command visible or applied by itself.

## MissionDriveSlice

One Celery delivery owns one bounded `MissionDriveSlice`, not the whole MissionRun lifecycle.

```text
claim lease with database time and increment lease_epoch
load bounded snapshot + unapplied commands
drive up to slice wall-time / model-turn / tool-step budget
checkpoint at a safe boundary
release lease and set next_wakeup_at when more work remains
best-effort enqueue continuation
```

Rules:

- Slice wall-time is strictly below the Celery soft/hard limit and Redis broker visibility timeout, with measured shutdown margin.
- A dedicated mission-worker consumes the `long_running` queue with late ack, reject-on-worker-lost, and prefetch multiplier `1`; do not impose its scheduling profile on short chat and preprocessing jobs. Task/result backend state is operational telemetry only.
- A clean yield cannot leave untracked in-process model calls or subagent tasks alive. In-process children finish/cancel first; external sandbox/provider jobs must already have a stable operation id and durable receipt reference that a later slice can adopt.
- Only the current lease holder writes MissionRun/MissionItems. External workers/providers never callback directly into mission state; a current driver collects and normalizes their receipt.
- Reconciler claims batches with `FOR UPDATE SKIP LOCKED`; direct queue consumers claim one mission by id. Lease expiry uses database time to avoid worker clock skew.
- Crash recovery waits for lease expiry or explicit worker-lost handling, acquires a higher epoch, and continues from bounded state. It does not mark an otherwise recoverable mission failed.

## Billing / Budget Boundary

The old `launch_feature` path performs credit checks and reservation before execution. MissionRuntime absorbs that responsibility:

```text
preflight_budget(user_id, workspace_id, mission_policy_id)
freeze_mission_model_global_pricing(mission_id)
reserve_mission_credits(mission_id, mission_idempotency_key, pricing_snapshot)
attach reservation_id to MissionRun.snapshot_json.billing
settle or release on terminal status
```

Rules:

- No billable mission starts without a MissionRun-bound reservation or explicit free policy.
- Every pinned MissionPolicy contains one cumulative execution budget. DataService derives model-call, tool-operation, subagent-job, and token usage only from immutable MissionItems under the Mission row lock; runtime snapshots cannot overwrite it.
- Count ceilings fail before dispatch. `stop_after_total_tokens` is a post-response stop threshold: the exact provider receipt is retained even when one bounded response crosses it, and all later dispatch is rejected while terminal/audit writes remain available.
- Sandbox and tool usage is accounted through receipt-backed Mission settlement; there are no standalone sandbox or item-level credit reservations.
- Admission resolves `MissionRun.model_id -> ModelCatalogEntry.pricing_policy_id` and freezes the validated Mission/model/global policy ids, versions, and configs in the immutable admission receipt and reservation. Settlement never rereads mutable active pricing. The public catalog uses the same DataService resolver for new work.
- ChatTurnRun never owns feature-task credits.
- Billing failure pauses the mission with `status=waiting` and `waiting_reason=budget`; it does not create an ExecutionRecord fallback.

## Main Loop

```text
observe
apply_unapplied_commands
plan_or_replan
act
normalize_outcome
verify
stage_or_continue
```

The model can dynamically choose research path, but cannot bypass:

- permission checks
- stage acceptance contracts
- tool result normalization
- review/commit boundary
- sandbox manifest requirements
- budget/loop guard

## MissionItem Types

Initial set:

```text
user_message_ref
assistant_message_ref
command_received
plan
stage_started
stage_completed
tool_call
tool_result
subagent_spawned
subagent_progress
subagent_completed
model_call_started
usage_receipt
model_call_terminal
quality_check
review_candidate_created
review_decision_audit
commit_started
commit_completed
pause_request
resume_input
context_checkpoint
status_update
error
```

Each item has:

```text
mission_id
seq
item_type
operation_id
phase: started | progress | completed | failed | cancelled
stage_id
producer
payload_json
payload_ref
summary
risk_level
created_at
```

MissionItems are immutable after append. One operation lifecycle is represented by multiple items sharing `operation_id`; terminal phases are stable projection facts. Each `model_call_started` is paired with exactly one terminal item carrying the same model-call id, model, turn, attempt, producer, stage, and optional parent-operation/job binding. A measured provider response uses a non-zero `usage_receipt`; a call known not to have incurred usage uses `model_call_terminal=failed|cancelled`; any ambiguity uses `model_call_terminal=unresolved`. Receipt and non-receipt terminals are mutually exclusive and idempotent only under exact content replay.

MissionRuntime checks the DataService model-call projection at recovery, before each drive-loop boundary, after subagent execution, and before terminalization. It converts a recovered open call to `unresolved` before another dispatch and terminates with `model_usage_reconciliation_required`. Open or unresolved calls cannot be bypassed by a new model, tool, subagent, or stage dispatch. Raw reasoning, token streams/deltas, line-by-line logs, and subagent wire output are not durable MissionItems.

## MissionRun Snapshot

`snapshot_json` should include:

```text
user_constraints
plan_summary
stage_state_summaries
context_checkpoint_summary
evidence_ledger_summary
subagent_summary
review_summary
commit_summary
budgets
waiting_reason
degraded_reason
failure_reason
last_error
next_actions
pending_request
```

Identity, title/objective, workspace/thread/type, model/effort, policy id, review mode, lifecycle status, lease, version, item sequence, active stage, counters, context checkpoint ref, and timestamps are scalar columns and must not be duplicated in `snapshot_json`. Summary objects must not repeat scalar counters. High-frequency list fields are summarized; full detail stays in `mission_items`, review/commit tables, or bounded external payload refs. Snapshot byte limits are specified and tested in the DataService spec.

## Context Checkpoint

Compaction appends a terminal `context_checkpoint` MissionItem and updates `context_checkpoint_ref`. The versioned checkpoint retains objective/user-decision refs, active stage and quality snapshot, evidence/artifact refs, pending review/request state, failed attempts, next actions, and resolved runtime-context refs. It is not a chat summary and must restore the mission without replaying the full transcript.

Workspace memory remains a reviewed room fact. MissionRuntime may read only current, permitted memory entries; stale candidates are excluded or surfaced for staleness review rather than silently injected.

## Pause / Resume

MissionRuntime can pause for:

- user clarification
- approval
- review
- external data access
- permission escalation
- budget/cost confirmation

Pause writes:

```text
MissionItem(type=pause_request)
MissionRun.status=waiting
snapshot_json.waiting_reason
snapshot_json.pending_request
```

Resume must use a stable request id and must be idempotent. Replaying a resume payload cannot re-execute prior tool side effects.

Final MissionReviewItems do not force the completed MissionRun back into `waiting`. Only a review decision required before additional agent work creates an in-loop pause.

## Subagent Integration

MissionRuntime does not poll subagents through model text. It calls SubagentRuntime:

```text
spawn_subagent()
wait_or_background()
collect_result()
append semantic lifecycle items and optional trace refs
```

Subagent completion appends a terminal `subagent_completed` MissionItem and updates `MissionRun.snapshot_json.subagent_summary`.

## Replacement of ExecutionEngineV2

Delete/replace:

- `ExecutionEngineV2.run(execution_id)`
- `ExecutionService.start_execution/complete_execution/fail_execution`
- `ExecutionService.record_node_event/upsert_execution_node`
- `execution.graph_structure` events
- `ExecutionRecord.node_states` hydration

New runner:

```text
MissionRuntime.run(mission_id)
MissionRuntime.resume(mission_id, resume_payload)
MissionRuntime.cancel(mission_id)
```

Worker queue task should receive only `mission_id`.

The task returns after one drive slice with `completed | yielded | waiting | terminal` telemetry. That return value is never MissionRun truth; the next action is derived from the committed MissionRun.

## Tests

- MissionRun starts from created to running.
- MissionStore transaction appends item and increments `last_item_seq`.
- Duplicate resume request is idempotent.
- Event publish failure does not corrupt snapshot.
- Semantic ledger pagination returns ordered MissionItems; raw trace refs are separate and TTL-managed.
- Cancel sets terminal state and stops future subagent/tool dispatch.
- Restart recovery reads MissionRun scalar columns plus bounded `snapshot_json`, not chat transcript.
- Stale lease epoch writes are rejected after worker takeover.
- Duplicate queue/command delivery does not duplicate tool, sandbox, subagent, or commit side effects.
- A publish-after-commit crash is recovered from `next_wakeup_at` without an outbox row.
- A long mission completes through multiple bounded drive slices without hitting Celery hard limits.
- Review-driven child continuation invalidates only the source-stage dependency closure and preserves unaffected passed stages.
- `prefetch=1`, broker visibility margin, safe-yield, DB-time lease, and `SKIP LOCKED` reconciler behavior are covered by integration tests.
- A command appended while a valid driver is running is observed at the next safe boundary even when its queue/event hint is dropped.
- Completed MissionRun can expose pending MissionReviewItems without changing execution status.
- Compaction recovery preserves stage/evidence/pending state without loading the full Thread transcript.
- Stale workspace memory is not silently injected into a new mission.
