# Workspace Current State

> Status: Current source of truth
> Updated: 2026-07-11

## Product model

Each workspace is a durable academic project with a type-specific `MissionPolicy`: `sci`, `thesis`, `proposal`, `software_copyright`, `math_modeling`, or `patent`. The primary surface is conversation. Users describe a need, upload context, ask follow-ups, and steer work in ordinary language; they do not select a fixed workflow from a grid.

The workspace has two visible surfaces:

- **Workbench**: chat plus an on-demand Mission Console;
- **Prism writing desk**: document editing, compilation, feedback, and reviewed mission writes.

The workspace rooms remain domain views for Library, Documents, Decisions, Memory, Tasks, Settings, Sandbox, and Mission History. They are not independent orchestration systems.

## Welcome state

An empty thread displays a non-persisted, workspace-type welcome state. It speaks as Wenjin, suggests three or four suitable starting points, and invites the user to state a goal. SCI guidance may ask for a research direction; math modeling prioritizes uploading the problem PDF. Once a real message exists, the welcome state disappears and is never written into conversation history.

## Conversation path

1. The frontend creates a `ChatTurnRun` and streams one assistant turn.
2. `WorkspaceAgent` reads the thread, workspace context, focused mission, and user message.
3. It either answers directly or emits a strict mission action.
4. A mission start returns a chat-native receipt with `mission_id`; steering appends an ordered mission command.
5. The Mission Console peeks and canonical Mission state is fetched.

`ChatTurnRun` is transport state only. Research history is a list of `MissionRun`s. A follow-up such as “继续深化实验设计” stays in chat and is routed to the focused mission when appropriate.

## Mission path

At start, the runtime validates and pins policy, stages, tools, model profile, review mode, budget, and intake. The long-running worker then advances bounded slices:

1. claim a due mission lease;
2. apply ordered user commands;
3. ask the mission loop for the next structured action;
4. call a canonical tool, spawn scoped subagents, assess a stage, propose review items, pause, or finish;
5. append semantic `MissionItem`s and update the bounded snapshot;
6. release the lease and publish completion or the next wakeup.

Dynamic subagents receive isolated context, allowed tool ids, explicit deliverables, and stop conditions. Their user-facing names are chosen by the main agent and may be playful but should remain legible and professionally relevant. The UI shows who is working and what each member is doing without exposing raw prompts or tool JSON.

## Quality progression

Stages come from the pinned `MissionPolicy` and resolved `StageAcceptanceContract`s. A stage can advance only when required artifacts, evidence refs, minimum criteria, blocker checks, and iteration rules pass. An assessment may use model judgment, but every supporting ref must belong to the current operation. A failed first question in math modeling is revised before question two; an SCI topic or experiment design is similarly refined before downstream writing.

The stage result is recorded in Mission items and reflected in the Mission snapshot. The UI translates internal outcomes into calm user language such as “正在补充证据” or “需要你确认”, not alarming infrastructure terminology.

## Tools and evidence

The frozen production catalog currently covers workspace assets/documents/source text, source candidate import, source-code reads, sandbox compute and manifests, artifact candidate creation, model-native web search, and review candidate staging. Tool calls produce started/completed/failed receipts with operation ids and bounded summaries.

Model-native web search is accepted only with source and citation receipts. Search results remain candidates until imported into the workspace Library. Claims, citation keys, numeric results, scripts, datasets, and generated artifacts retain Mission provenance.

## Review and save

The user chooses one of three review modes:

- `review_all`: every proposed workspace mutation is reviewed;
- `balanced_default`: drafts may flow more freely, while claims, citations, evidence, memory, and protected documents require confirmation;
- `auto_draft`: low-risk draft material may be staged automatically, with protected truth still reviewed.

Review items are atomic previews with a target, base revision/hash, risk reason, and expiry. The user may accept, reject, ask for more evidence, or save an accepted subset. Commit materialization is idempotent and records receipts. A stale base revision yields a conflict and requires regeneration; it is not silently overwritten.

## Pause and resume

A mission may wait for user input, a specific permission, review, budget, or an external dependency. The pause request is durable and appears in chat and Mission Console. Resolving it appends a command and wakes the mission. Cancelling is terminal; pausing is not.

## Frontend projection

`MissionView` is the only research-task projection. It contains:

- mission identity, status, stage, and progress;
- active and recent subagents;
- evidence and artifacts;
- review items and commit state;
- user-safe capability gaps and next action;
- a lazy, redacted trace.

The right panel is closed by default, peeks when work starts or needs attention, and expands on demand. SSE messages are invalidation hints. The client always refetches Mission state, and a sequence jump forces a full refresh. Refresh and reconnect recover from DataService, not Zustand-only state.

Mission History lists only durable missions. Chat turn transport records, raw sandbox logs, and internal tool traces do not appear as separate user tasks.

## Workspace domain writes

Accepted commits may materialize into Documents/Prism, Library, Decisions, Memory, Tasks, or artifact storage. Linked records carry Mission provenance. Agent output that has not passed the applicable review policy remains a candidate and cannot masquerade as workspace truth.

## Operational facts

- DataService owns mission and linked-domain transactions.
- The default worker handles chat turns and short jobs.
- The long-running worker handles mission slices with concurrency 1 and prefetch 1.
- Leases and versions fence duplicate workers.
- Redis/Celery delivery and SSE are non-authoritative hints.
- Due waiting/running missions can be reconciled after worker loss.
- The model baseline is GPT-5.6 Sol/Terra/Luna, with Terra as default; reasoning efforts are `low`, `medium`, `high`, `xhigh`.

## Current limitations

- Native search availability depends on a current Responses SSE probe with complete receipts; a search-required mission fails closed when the provider does not satisfy that contract.
- Full production confidence still requires a real-provider, real-Docker, multi-turn browser run after deployment configuration is available.
- Historical pre-Mission development records are intentionally not migrated; development environments are reseeded.

## Canonical references

- Runtime architecture: `docs/current/architecture.md`
- Frontend/API contract: `docs/current/frontend-mission-contract.md`
- Policy/skill catalog: `docs/current/workspace-mission-catalog.md`
- UX language: `docs/current/wenjin-research-navigation-uiux.md`
- Migration specs: `docs/superpowers/specs/mission-runtime/00_index.md`
