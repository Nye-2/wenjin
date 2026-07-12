# 06 SubagentRuntime Spec

Status: Implemented
Updated: 2026-07-11

Implementation outcome: isolated bounded jobs, concurrency limits, tool narrowing, structured reports, stop reasons, and MissionItem lifecycle projection are implemented. Subagents have no separate persistence table or room-write authority.
Depends on: `02_mission_runtime.md`, `04_stage_acceptance_contract.md`, `10_sandbox_vnext.md`, `12_tool_orchestrator.md`

## Goal

Make subagents first-class runtime jobs with isolated context, stable lifecycle, stop reasons, and a step ledger. Subagents are not a second user-facing product surface and do not write rooms directly.

## Current Code Anchors

| Current file | Current responsibility | Target action |
|---|---|---|
| `backend/src/subagents/v2/registry.py` | Subagent registry and callable resolution | Keep useful registry concepts, but connect to SubagentRuntime |
| `backend/src/subagents/v2/types/searcher.py` | Searcher subagent type | Convert output to MissionItem/ResearchToolOutcome |
| `backend/src/agents/lead_agent/v2/team/kernel.py` | TeamKernel member execution, quality gates, snapshots | Split into SubagentRuntime + StageQualityRuntime pieces |
| `backend/src/contracts/team_presentation.py` | Expert presentation data | Keep as display sanitizer; not runtime SSOT |
| `backend/src/contracts/team_expert.py` | Expert runtime snapshot contracts | Keep as subagent preview payload contract |
| `backend/src/database/models/subagent_task.py` | Durable subagent task table bound to `executions.id` | Delete/reseed; subagent lifecycle is MissionItem + MissionRun summary |
| `frontend/lib/execution-run-view.ts` | Hydrates team from ExecutionRecord.node_states | Replace with MissionView projection from SubagentActivity/MissionItem |

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
subagent_id
mission_id
stage_id
display_name
role_label
task_summary
input_scope
context_checkpoint_ref
allowed_tools
allowed_rooms
risk_profile
commit_targets
status
stop_reason
budget
started_at
completed_at
result_brief
result_sha256
step_ledger_ref
```

The main chat receives only `result_brief`, preview items, and reviewable outputs. Detailed step ledger is lazy-loaded.

Storage rule:

- Do not create `subagent_jobs` or keep `subagent_task_records` as runtime SSOT.
- Active worker-local bookkeeping lives in a mission-scoped in-process registry owned by the current MissionDriveSlice; it is not queue or database truth.
- Durable lifecycle is represented by immutable `subagent_spawned`, bounded `subagent_progress`, and terminal `subagent_completed` MissionItems sharing a stable operation id.
- Fast UI summary is stored in `MissionRun.snapshot_json.subagent_summary`.
- Semantic lifecycle is paginated from MissionItems. Raw wire logs, token deltas, and verbose tool traces are external payload refs with redaction and TTL; they are not copied into the durable ledger.
- Mission queue delivery is at-least-once. Spawn uses a stable operation key, and terminal results are accepted only by the current parent mission lease holder.

Execution topology:

- First cutover runs subagent model loops as bounded async child tasks inside the active MissionDriveSlice. There is no independent Celery subagent queue, callback writer, or `subagent_jobs` table.
- A root-scoped registry enforces mission-level max concurrency, total spawn budget, per-child wall time, and cancellation. Horizontal scale comes from multiple missions/workers, not distributed ownership of one small research team.
- Default max spawn depth is `1`: WorkspaceAgent/MissionRuntime may spawn children; children cannot recursively create more subagents. A later depth change is a policy/version change, not prompt freedom.
- Child context is fresh and bounded by default. Full parent-history fork is forbidden; only the explicit mission checkpoint, stage contract, selected refs, task, tools, and exit criteria are provided.
- Parent-mediated coordination is the default. Children return structured results to MissionRuntime and do not message siblings or share an unowned mutable scratch bus.
- A clean drive-slice yield waits for or cancels all in-process children. Work that must outlive a slice is represented as an external tool/sandbox operation with a durable operation id, not a detached subagent thread.

## Context Isolation

Subagent context includes:

- mission objective summary
- current stage contract
- relevant room/source refs
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
- MissionOutput candidate
- MissionReviewItem candidate
- ArtifactManifest ref
- StageQuality evidence

## Migration

1. Extract TeamKernel member execution into SubagentRuntime jobs.
2. Replace `record_node_event` with MissionItem appends.
3. Convert `expert_snapshots` and `expert_preview_items` to SubagentActivity projection payloads.
4. Delete node-state-based team roster hydration.
5. Update frontend MissionView to read subagent summary from mission snapshot and full ledger from item pagination.
6. Enforce stop reason on every terminal subagent.
7. Delete `subagent_task_records` runtime dependency and any `execution_id` foreign key for subagent state.

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
- No runtime query reads `subagent_task_records` after cutover.
