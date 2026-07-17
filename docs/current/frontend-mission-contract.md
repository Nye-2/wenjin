# Frontend Mission Contract

> Status: Current source of truth
> Updated: 2026-07-16

## Purpose

The frontend is chat-native. It renders conversation and a canonical `MissionView`; it does not choose or execute fixed workflows. Backend `MissionPolicy` and `WorkerSkill` records are runtime contracts, not user-facing plugin cards or an admin workflow builder.

## Launch and steering

The frontend sends user messages through thread run endpoints. `WorkspaceAgent` may return ordinary blocks or a mission receipt. The canonical mission id is read from `status_line.run_id`, while its typed `action` states whether the turn started, steered, reviewed, or committed a Mission. Only `action=start_mission` may trigger the Mission Console peek. The UI must not infer a launch from prose, a feature id, an existing Mission id, or local optimistic state.

Subsequent chat turns can start, steer, pause, resume, cancel, review, commit, or change review mode through the agent or explicit Mission actions. The focused mission is context, not a permanent right-panel route selection.

## Mission API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/missions/{mission_id}` | canonical MissionView |
| GET | `/api/workspaces/{workspace_id}/missions` | Mission history |
| GET | `/api/missions/{mission_id}/items` | lazy redacted trace |
| GET | `/api/workspaces/{workspace_id}/missions/events` | owner-scoped invalidation hints |
| POST | `/api/missions/{mission_id}/actions` | cancel, pause, resume, steer, review, commit, set review mode |
| POST | `/api/missions/{mission_id}/review-decisions` | atomic review decisions |
| POST | `/api/missions/{mission_id}/commits` | materialize accepted items |
| POST | `/api/missions/{mission_id}/permissions/{request_id}/resolve` | resolve a durable permission request |

All reads and writes are owner isolated. Unknown or cross-workspace ids are not projected.

## MissionView ownership

The MissionView response owns:

- summary: title, objective, status, stage, progress, timestamps;
- roster: active/recent subagents and user-safe activity;
- evidence/artifacts: bounded summaries and references;
- review: atomic preview state, decision state, and save eligibility;
- capability gaps and waiting request;
- commit results;
- last item sequence for reconnect.

The frontend may derive presentation-only labels, counts, grouping, and panel focus. It must not derive mission status, stage completion, review eligibility, risk policy, or commit success independently.

## SSE contract

`GET /api/workspaces/{workspace_id}/missions/events` accepts an opaque constant-size cursor over the indexed Mission update watermark. Events signal that canonical state changed. The client refetches; it does not replay events into a second state machine. Reconnect, visibility restore, or a malformed hint triggers a full refresh.

## Chat blocks

Conversation blocks remain ordered and streamable: `text`, `thinking`, `status_line`, `question_card`, `result_card`, `tool_invocation`, and `tool_result`. Thinking is progressive UI feedback, not hidden durable mission state. Result cards link to Mission outputs and use `run_id` as the durable Mission id.

Chat transport state is workspace-scoped. A workspace switch aborts the previous request, removes an empty optimistic assistant placeholder, and rejects every stale stream frame. Attachment upload is part of send readiness: the composer remains disabled until preprocessing returns the immutable thread attachment ref.

Provider or tool internals are mapped to user-safe language. Raw schema names, stack traces, sandbox paths, prompts, and unbounded logs do not appear in default chat.

## Mission Console behavior

- closed by default;
- peek after mission start, meaningful progress, or required attention;
- full expansion is user controlled;
- mobile uses a sheet, never a permanent split pane;
- refresh restores the focused Mission from canonical state;
- trace is fetched lazily;
- History lists MissionRuns only.

The console surfaces progress, current stage, team, evidence, artifacts, review, and saved results. Tool diagnostics remain behind a detail affordance.

Artifacts are acceptance-backed current outputs, not a dump of internal candidate revisions. DataService projects at most one current result per stable `output_key` or protected materialization destination; superseded, rejected, and unaccepted candidates remain trace-only. The artifact page total is therefore the user-visible result count, while internal Mission ledger counters stay diagnostic.

When execution is `waiting`, `MissionView.attention_request` is the only UI contract for the required response. It includes the durable request id, reason, user-facing summary and impact, required inputs, and allowed actions. Chat and Mission Console render this projection directly; they do not infer a request from timers, status labels, or raw snapshot fields.

## Review interaction

Protected outputs are presented as user confirmations, not automated reviewer verdicts. The UI explains why confirmation is useful in domain language and supports per-item selection, accept, skip, request more evidence, undo decision, and partial save. Content quality has already been handled inside generation; an optional audit is started only when the user asks or identifies a concrete concern. Commit buttons are enabled from server-projected eligibility.

A review or commit mutation can return `continuation_mission_id`. The client immediately fetches and focuses that child MissionView, so terminal feedback visibly resumes work instead of leaving the parent frozen on screen. A stable `continuation_error_code` is translated into actionable product language and never into raw schema/runtime wording.

Review modes are presented as user choices, but their semantics come from backend policy:

- review every write;
- balanced review;
- automatically stage low-risk drafts.

## Model menu

The current model list contains GPT-5.6 Sol, Terra, and Luna, with Terra as default. The combined menu presents model and reasoning effort; there is no speed option. Effort values are `low`, `medium`, `high`, and `xhigh`. Display labels may be localized, but wire values must remain exact.

## Admin boundary

Admin analytics uses `GET /api/dashboard/admin/analytics/mission-stats`. There is no admin UI for editing old workflow definitions. Policy and skill changes are versioned seed/catalog deployments and require runtime contract tests.

## Frontend invariants

1. Chat is the only task-navigation entry.
2. `MissionView` is the only durable task projection.
3. Events invalidate; APIs hydrate.
4. Review eligibility comes from the server.
5. The right panel is optional context, never a prerequisite to continue chatting.
6. No technical failure wording is shown when a concrete user action can be stated.
7. No retired workflow route, store, card grid, or dual projection may be reintroduced.
8. Only a typed `start_mission` status action may open or peek the Mission Console.
9. An aborted or stale chat stream cannot mutate another workspace.
