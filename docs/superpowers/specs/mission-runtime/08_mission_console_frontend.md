# 08 Mission Console Frontend Spec

Status: Implemented
Updated: 2026-07-11

Implementation outcome: MissionView is the sole task projection; console peek/closed/expanded states, history, roster, evidence, artifacts, review, partial save, SSE refetch, model/effort menu, and mobile tests are implemented. A deployed real-backend visual pass remains part of spec 13 acceptance.
Depends on: `02_mission_runtime.md`, `07_review_commit_runtime.md`, `11_mission_trace_run_history.md`

## Goal

Replace Execution/RunView projection with MissionView projection. The right panel becomes a Mission Console: closed by default, peek during running missions, expanded for review, evidence, preview, and trace.

## Cutover Baseline

The table records pre-cutover ownership and the completed target action; it is not a map of current runtime paths.

| Current file | Current responsibility | Target action |
|---|---|---|
| `frontend/lib/execution-run-view.ts` | Converts ExecutionRecord/RunRecord/result_card into RunView, team/evidence/review projections | Replace with `frontend/lib/mission-view.ts` |
| `frontend/stores/execution-store.ts` | Stores ExecutionRecord map and handles execution SSE | Replace with mission read cache; no lifecycle ownership |
| `frontend/stores/run-ui-store.ts` | Stores active/focused/highlighted run ids | Keep but rename concepts to mission focus; UI-only |
| `frontend/lib/api/runs.ts`, `frontend/lib/api/v2/runs.ts` | Workspace run history API and chat/run naming | Rebind user-facing history to MissionRun; keep chat transport APIs out of Mission Console |
| `frontend/app/(workbench)/workspaces/[id]/components/rooms/RunsDrawer.tsx` | Merges persisted run records with live ExecutionRecord | Replace with MissionRun summary list only |
| `frontend/app/(workbench)/workspaces/[id]/page.tsx` | Opens/closes mission panel based on execution store | Rebind to MissionView demand |
| `LiveWorkflowPanel.tsx` and `live-workflow/*` | Current run, evidence, review panels | Rename/reshape to MissionConsole components |
| `ResultCard.tsx`, `CompletedView.tsx` | Chat result card and writeback UI | Use MissionReviewItem/MissionOutput projections |

## Target Frontend State

Frontend may store:

```text
focusedMissionId
highlightedMissionId
focusedPreviewItemId
expandedPanel
selectedReviewItemIds
composerDraft
```

Frontend must not store:

```text
mission lifecycle
stage status
subagent lifecycle
tool result status
review decision truth
commit state
room write state
ChatTurnRun lifecycle as mission state
```

## MissionView Shape

```text
missionId
workspaceId
threadId
title
executionStatus
statusLabel
duration
activeStage
stages[]
teamSummary
subagents[]
evidenceItems[]
reviewItems[]
reviewSummary
reviewMode
reviewSelectionRevision
resultPreviews[]
qualityHighlights[]
commitSummary
pauseRequest
primaryActions[]
secondaryActions[]
```

MissionView is a read model from DataService/gateway. The frontend may merge live SSE deltas only as optimistic display, but the next snapshot refresh wins.

`artifactItems` contains only the current user-facing result for each stable output or materialization destination. Internal candidate freezes and failed revisions remain in the immutable trace; they never appear as parallel "original" or "revised" results. A candidate enters Artifacts only after stage acceptance creates its `MissionReviewItem`.

`executionStatus` is only `created | planning | running | waiting | completed | failed | cancelled`. Pending review and commit progress come from `reviewSummary` and `commitSummary`; the frontend must not synthesize `awaiting_user_review`, `committing`, or `blocked` mission statuses.

Each review item may carry a derived `suggestedSelected` value plus `reviewSelectionRevision`. This is a server projection from review mode/risk, not persisted review truth. Frontend initializes local checkbox selection once per revision; it never posts that suggestion back as status or treats it as acceptance.

Run naming rule:

- `MissionRun` is the only user-facing research run.
- `ChatTurnRun` is transport-only and never appears in Mission Console, Run History, evidence, review, or artifacts.
- If chat streaming endpoints keep the word `run` during internal migration, frontend Mission code must not import those contracts.

## Panel States

```text
Closed    no mission demand or user dismissed
Peek      mission running / waiting / completed with light summary
Expanded  review, evidence, preview, diff, trace, or user-opened details
```

Open demand comes from MissionView:

- running mission
- waiting approval/user/review
- completed mission with pending review
- user clicked status/receipt/result

Starting a new Mission from chat replaces the panel focus even when an older Mission is already expanded. Explicit history navigation may focus an older Mission again.

The right panel does not launch capability tasks.

## Chat Projection

Chat shows:

- welcome state
- advisory answers
- mission receipt
- stage summary
- review prompts
- final summary
- pointers to Mission Console detail

Chat does not show:

- raw subagent logs
- raw tool args
- schema ids
- blocked/high-risk internal labels
- full trace

## Mission Console Surfaces

Recommended tabs/surfaces:

```text
Progress
Review
Evidence
Artifacts
Trace
```

Default surface selection:

- pending review or in-loop review wait -> Review
- running -> Progress
- completed with evidence -> Evidence/Review depending pending count
- sandbox artifact preview -> Artifacts
- debug/developer action -> Trace

## API / SSE

Replace execution endpoints with mission endpoints:

```text
GET /api/workspaces/{workspace_id}/missions
GET /api/missions/{mission_id}
GET /api/missions/{mission_id}/items
POST /api/missions/{mission_id}/review-decisions
POST /api/missions/{mission_id}/actions
```

Chat streaming endpoints may continue separately as ChatTurnRun endpoints:

```text
POST /api/chat-turns/{thread_id}/stream
POST /api/chat-turns/{turn_run_id}/cancel
```

They are not Mission Console APIs.

SSE event names:

```text
mission.created
mission.updated
mission.item.appended
mission.review.updated
mission.commit.updated
mission.terminal
```

Frontend must treat SSE as a hint to refresh/patch MissionView, not as a second truth.

## Migration

1. Add MissionView types in the cutover branch; do not ship a runtime "MissionView else RunView" fallback.
2. Replace panel data path to MissionView.
3. Delete `runViewFromExecution`, `runViewFromRunRecord`, and execution-node parsing after cutover.
4. Replace execution store with mission read cache.
5. Rename user-facing "run" labels to task/mission/研究任务 as appropriate.
6. Remove capability launcher grid and right-side ability buttons.
7. Delete any merge between historical MissionRun records and live ExecutionRecord/ChatTurnRun records.

## Tests

- No mission -> panel closed.
- Running mission -> peek opens.
- Waiting review -> review surface opens.
- Completed mission with pending review remains completed and opens the review surface from reviewSummary.
- User closes panel -> stays closed until new demand key.
- Refresh restores MissionView from backend.
- Frontend does not compute stage status from local timers.
- High-risk review item disables batch accept in UI.
- Trace tab lazy-loads semantic items; raw trace refs are separate, redacted, and fetched only in developer detail.
- ChatTurnRun stream state never appears as a Mission Console item.
