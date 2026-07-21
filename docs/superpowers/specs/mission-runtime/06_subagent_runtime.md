# 06 SubagentRuntime Spec

Status: Implemented
Updated: 2026-07-21

Implementation outcome: isolated bounded jobs, concurrency limits, pinned WorkerSkill contracts, canonical tool narrowing, strict structured reports, exact receipt references, terminal recovery, and MissionItem lifecycle projection are implemented. Subagents have no separate persistence table, recursive spawn authority, or room-write authority.
Depends on: `02_mission_runtime.md`, `04_stage_acceptance_contract.md`, `10_sandbox_vnext.md`, `12_tool_orchestrator.md`

## Goal

Make subagents first-class runtime jobs with isolated context, stable lifecycle, stop reasons, and a step ledger. Subagents are not a second user-facing product surface and do not write rooms directly.

## Implementation Anchors

| File | Authoritative responsibility |
|---|---|
| `backend/src/subagent_runtime/contracts.py` | Frozen job, budget, action, tool-result, lifecycle, and terminal-result contracts |
| `backend/src/subagent_runtime/runtime.py` | Bounded child loops, concurrency, cancellation, retry budgets, in-slice idempotency, and result validation |
| `backend/src/mission_runtime/adapters.py` | Mission lease fencing, pinned WorkerSkill resolution, selected-ref hydration, strict provider schemas, receipt binding, durable terminal recovery, and Mission projection |
| `backend/src/mission_runtime/runtime.py` | Spawn/completion ledger boundaries, parent operation ownership, and snapshot updates |
| `backend/src/mission_runtime/reference_authority.py` | Prefix-routed canonical reads for immutable Mission inputs, Prism files, artifact candidates, and Sandbox artifacts |
| `backend/src/dataservice/domains/mission/service.py` | MissionItem persistence and sanitized `MissionView.subagents` projection |
| `frontend/app/(workbench)/workspaces/[id]/components/mission-console/` | Lazy user-facing collaborator status from MissionView only |

## Lifecycle

```text
queued
running
completed
failed
cancelled
timed_out
```

`status` and `stop_reason` are separate:

```text
completed + normal
completed + token_capped
completed + turn_capped
completed + loop_capped
failed + tool_unavailable
failed + permission_denied
timed_out + partial_result_available
```

Partial useful output can be staged with a warning instead of hard failed.

## Subagent Job Contract

```text
job_id
operation_id
mission_id
workspace_id
model_id
reasoning_effort
lease_owner
lease_epoch
stage_id
display_name
role_label
task_summary
objective
input_scope
context_checkpoint_ref
context_checkpoint
selected_refs
context_reads
prior_output_briefs
allowed_tools
tool_input_schemas
worker_skill
output_schema
exit_criteria
budget
depth = 1
```

Lifecycle state, stop reason, result hash, evidence/artifact refs, and usage counters belong to the terminal `SubagentJobResult`; they are outputs, not model-owned job input.

The parent Mission receives only the structured terminal result, bounded brief, and exact refs. Chat and Mission Console consume sanitized Mission projections; the detailed semantic ledger is lazy-loaded.

Storage rule:

- Do not create `subagent_jobs` or keep `subagent_task_records` as runtime SSOT.
- Active worker-local bookkeeping lives in the composed SubagentRuntime registry and is bounded by the current MissionDriveSlice; it is not queue or database truth.
- Durable lifecycle is represented by immutable `subagent_spawned`, bounded `subagent_progress`, and terminal `subagent_completed` MissionItems sharing a stable operation id.
- Terminal UI summary is stored in `MissionRun.snapshot_json.subagent_summary`. While a batch is active, DataService projects each worker from its newest durable `subagent_progress` item so Mission Console does not wait for terminal aggregation.
- Semantic lifecycle is paginated from MissionItems. Raw wire logs, token deltas, and verbose tool traces are external payload refs with redaction and TTL; they are not copied into the durable ledger.
- Mission queue delivery is at-least-once. Spawn uses a stable operation key, and terminal results are accepted only by the current parent mission lease holder.

Execution topology:

- Production runs subagent model loops as bounded async child tasks inside the active MissionDriveSlice. Ordinary planning/tool work retains the 180-second slice window; a subagent batch receives one runtime-owned 900-second operation window capped from the original delivery start. There is no independent Celery subagent queue, callback writer, or `subagent_jobs` table.
- A root-scoped registry enforces mission-level max concurrency, total spawn budget, per-child wall time, and cancellation. Horizontal scale comes from multiple missions/workers, not distributed ownership of one small research team.
- Default max spawn depth is `1`: WorkspaceAgent/MissionRuntime may spawn children; children cannot recursively create more subagents. A later depth change is a policy/version change, not prompt freedom.
- Child context is fresh and bounded by default. Full parent-history fork is forbidden; only the explicit mission checkpoint, stage contract, selected refs, task, tools, and exit criteria are provided.
- Parent-mediated coordination is the default. Children return structured results to MissionRuntime and do not message siblings or share an unowned mutable scratch bus.
- A clean drive-slice yield waits for or cancels all in-process children. Work that must outlive a slice is represented as an external tool/sandbox operation with a durable operation id, not a detached subagent thread.

## Context Isolation

Subagent context includes:

- mission objective summary
- current stage contract
- selected canonical Mission input, Prism, candidate, evidence, or Sandbox refs
- bounded prior outputs
- allowed tools
- output schema
- explicit exit criteria

Subagent context must not include:

- full chat transcript
- raw tool logs
- hidden internal prompts
- unrestricted sandbox paths
- unrelated room data

## Step Ledger

Subagent steps are MissionItems:

```text
subagent_spawned
subagent_progress
tool_call
tool_result
subagent_completed
```

These are semantic milestones, not every model/tool delta. Each item carries `operation_id` and an immutable lifecycle phase. Detailed trace uses bounded external refs and can expire without losing mission recovery state.

A worker may explicitly report one `finding`, `formula`, `file`, `figure`, or `checkpoint` milestone after it has a concrete, checkable result. The summary is user-visible and must state the result itself; private reasoning, tentative plans, and filler are forbidden. Duplicate milestone summaries are not persisted twice. Canonical tool results continue to publish their own semantic progress automatically, so workers should not restate them.

`MissionRuntime` owns `subagent_spawned` and `subagent_completed`. The child ledger appends bounded `subagent_progress` items with `lifecycle_phase`; a terminal progress item contains the result hash, job fingerprint, and structured result so an interrupted parent slice can recover it without rerunning the worker.

The parent driver renews the Mission lease throughout the extended operation and publishes an invalidation hint on the 30-second heartbeat cadence. The hint carries no progress body; clients refetch `MissionView`, whose facts remain DataService-owned.

Every progress item carries a deterministic `progress_id` and SHA-256 over its canonical summary and payload. A job terminal uses the fixed identity `subagent-terminal:{job_id}`. Before writing and after every append exception, the adapter queries durable progress by parent operation and identity, recomputes the hash, and adopts only one exact match; duplicate or divergent content is a hard error. This makes a committed terminal authoritative even when its response ACK is lost.

The adapter reconstructs a terminal result only after validating lifecycle phase, producer/job identity, job fingerprint, frozen budget, result hash, and progress hash. If child execution raises, both the adapter and the parent MissionRuntime probe this durable terminal projection. The parent performs its final probe immediately before persisting a failed `subagent_completed`; an adopted terminal therefore cannot be overwritten as failed or have its inflight state cleared by an ACK-loss path.

## Display Names

WorkspaceAgent or SubagentRuntime generates names using the overview naming rules. Names are user-facing labels only; they are not identifiers.

Examples:

```text
文献猎手 · Nora
证据哨兵 · Gu
方法雕刻师 · Lin
实验管家 · Chen
风险挑刺官 · Yan
```

No `Nora B`, `Max C`, template ids, or schema ids.

## Tool Boundary

Subagent tools must go through ToolOrchestrator. A subagent cannot call:

- room write APIs
- Prism apply
- memory write
- DataService commit
- unrestricted shell

It can produce:

- ResearchToolOutcome
- bounded structured findings or draft material
- internal artifact candidate refs through permitted canonical tools
- ArtifactManifest ref
- evidence refs for WorkspaceAgent consideration

It cannot create user-review items or decide StageAcceptance. MissionRuntime and the main WorkspaceAgent retain those boundaries.

### Result-reference authority

- Tool results are the only source of refs a worker may return.
- `evidence_refs` and `artifact_refs` remain separate categories; a ref from one category cannot satisfy the other.
- Before every `subagent_complete` decision, the provider schema recursively binds each reference field to an enum of exact receipts observed in the current worker loop.
- When a category has no receipts, its array has `maxItems: 0`; placeholder, invented, stale, or copied refs are invalid provider output.
- Runtime validation repeats the category-specific subset check before accepting the terminal result. Schema binding improves generation, while server validation remains the authority.
- Selected context is hydrated once through the canonical prefix router before the first model turn. Successful identical reads are not delegated back to the model.

## Cutover Invariants

- There is no TeamKernel, subagent registry catalog, `subagent_jobs` table, `subagent_task_records`, ExecutionRecord hydration, callback writer, or independent subagent queue.
- Worker identity and tool/output contracts come only from the Mission-pinned WorkerSkill snapshot; a model action cannot override them.
- Every terminal result has a stop reason and content hash. Reusing a `job_id` with different semantics or accepting a divergent duplicate terminal result fails closed.
- The parent Mission lease fences every child tool call and ledger append. A stale child cannot mutate Mission truth.
- Subagents never determine stage acceptance or user review. They return bounded evidence and artifacts to the WorkspaceAgent loop.
- A clean drive-slice boundary leaves no detached in-process child task.

## Tests

- Subagent terminal state requires stop_reason.
- Subagent with tools cannot silently downgrade to plain model invocation.
- Failed tool call creates structured tool result meta and a semantic ledger entry.
- Main chat does not receive raw subagent transcript.
- Child context never receives full parent history by default, and subagents cannot recursively spawn at depth 1.
- Mission-level concurrency/turn/time budgets prevent one team from exhausting the worker.
- A MissionDriveSlice cannot cleanly yield while an untracked child task remains live.
- Mission Console can show summary without loading full ledger.
- Semantic ledger can be paginated and is ordered by MissionItem seq; raw trace is lazy and TTL-managed.
- Duplicate spawn delivery does not create a second subagent job or duplicate its accepted terminal result.
- Complete-action schemas enum-bind evidence and artifact fields to their exact category-specific tool receipts.
- A worker cannot return an artifact receipt as evidence, an evidence receipt as an artifact, or any receipt it did not observe.
- Static architecture scans reject reintroduction of TeamKernel, subagent persistence tables, and execution-owned worker state.
