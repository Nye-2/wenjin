# 11 Mission Trace / Run History Spec

Status: Implemented
Updated: 2026-07-11

Implementation outcome: Mission summaries and lazy redacted items back History and Console; ChatTurnRun is excluded. SSE is an invalidation hint with sequence-gap refetch. Replay-as-new-mission remains a non-blocking future product enhancement.
Depends on: `02_mission_runtime.md`, `08_mission_console_frontend.md`

## Goal

Provide fast mission history summary and lazy-loaded full trace without making trace the runtime SSOT. Users should see understandable progress and evidence; developers can inspect structured trace when needed.

## Cutover Baseline

The table records pre-cutover ownership and the completed target action; it is not a map of current runtime paths.

| Current file | Current responsibility | Target action |
|---|---|---|
| `backend/src/services/execution_service.py` | Appends execution events and run history payloads | Replace with immutable semantic MissionItems plus transient MissionEvent hints |
| `frontend/lib/execution-run-view.ts` | Merges live execution and RunRecord into RunView | Replace with MissionView summary/full split |
| `backend/src/database/models/run_history.py` | Historical execution run table | Delete/archive; mission history reads `mission_runs` |
| `backend/src/gateway/routers/workspace_rooms.py` runs room | Projects executions into workspace Runs room | Replace with MissionRun summary endpoint |
| Runs drawer components | Lists historical runs | Rebind to MissionRun summary endpoint; do not merge ChatTurnRun or ExecutionRecord |
| `frontend/stores/run-ui-store.ts` | Focus/selection | Keep UI-only mission focus |

## Summary View

Mission list reads only `mission_runs`:

```text
mission_id
title
status
workspace_id
thread_id
updated_at
duration
active_stage
pending_review_count
evidence_count
artifact_count
risk_summary
```

No MissionItem scan for normal list.

ChatTurnRun and MissionDriveSlice are excluded from user-facing history. They are short-lived transport/worker-tenure records and may appear only in developer diagnostics; repeated slices never look like repeated missions.

## Detail View

Mission detail reads:

- MissionRun snapshot
- current review items
- current commit summary
- recent items page
- subagent summary

MissionRun execution status is independent from review/commit summaries. A completed mission may have pending reviews, partial commits, or failed commits without reopening its execution lifecycle.

Semantic ledger is paginated:

```text
GET /api/missions/{mission_id}/items?cursor=...&limit=...
```

Raw token deltas, reasoning, stdout/stderr, verbose subagent wire logs, and large tool payloads are external refs with TTL; they are not promoted into MissionItems merely to support a developer trace screen.

## Trace Item Redaction

Default trace view cannot show:

- secrets
- raw API keys
- raw stdout/stderr beyond preview
- full paper PDFs/text dumps
- internal output refs content
- host paths
- hidden prompts

Advanced/developer view may show structured metadata and internal refs, not raw secrets.

## Replay

Replay is for debugging/evals, not user workflow. It can consume semantic MissionItems but cannot blindly re-run external side effects or mutate accepted room state. Reruns create a new linked MissionRun and new candidate MissionReviewItems with new stable operation keys.

## History Lifecycle

Short-lived:

- old draft diff
- tool raw output refs
- failed transient attempts
- ChatTurnRun transport records
- raw model/subagent trace and token deltas

Durable:

- MissionRun summary
- semantic MissionItem ledger
- MissionReviewItem decision metadata and accepted MissionCommits
- committed room content
- manifest provenance for accepted artifacts

## Tests

- Mission list does not query full item ledger.
- Full trace pagination is ordered and bounded.
- MissionEvent loss is repaired from MissionView plus MissionItems after `last_item_seq`.
- Redaction removes secrets and host paths.
- Refresh restores Mission Console from summary/detail endpoints.
- Rerun creates new candidate and does not overwrite accepted artifact.
- Completed mission with pending review remains discoverable.
- Review/commit progress does not mutate completed MissionRun execution status.
- ChatTurnRun is never listed as a historical mission.
- Run History list does not query old `run_history` or execution projection.
