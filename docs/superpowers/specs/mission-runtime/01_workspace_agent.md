# 01 WorkspaceAgent Spec

Status: Implemented
Updated: 2026-07-15

Implementation outcome: `backend/src/agents/workspace_agent/` is the single agent entry; `backend/src/runtime/chat_turns/` owns transient turn transport. Strict structured mission actions are in production. No architectural blocker remains; real-provider browser acceptance is tracked by spec 13.
Depends on: `02_mission_runtime.md`, `05_capability_skill_lite.md`, `09_permission_pause.md`

## Goal

Replace the current two-agent product topology:

```text
Chat Agent -> launch_feature -> ExecutionRecord -> LeadAgentRuntime
```

with:

```text
WorkspaceAgent -> MissionRuntime -> SubagentRuntime / ToolOrchestrator
```

The user should experience one agent, "问津", that can chat, ask clarifying questions, start durable missions, continue paused missions, explain progress, and process review decisions.

## Cutover Baseline

The table records pre-cutover ownership and the completed target action; it is not a map of current runtime paths.

| Current file | Current responsibility | Target action |
|---|---|---|
| `backend/src/agents/chat_agent/agent.py` | Builds LangGraph ReAct chat agent, preloads capability route cards, exposes `launch_feature_tool` | Rename/reshape into WorkspaceAgent factory; keep useful middleware only if it feeds MissionContext |
| `backend/src/tools/builtins/launch_feature.py` | Creates/reuses ExecutionRecord and dispatches capability execution | Delete as execution launcher; replace with MissionRuntime start/resume tool boundary |
| `backend/src/application/handlers/thread_turn_handler.py` | Streams chat turn, extracts `launch_feature` invocation/result blocks, creates launch idempotency key | Replace launch block extraction with mission item/projection extraction |
| `backend/src/gateway/services/run_launch.py`, `run_lifecycle.py`, `run_http.py`, `run_views.py` | Chat run transport, SSE, cancel/wait, worker dispatch for a single thread turn | Rename/reshape as `ChatTurnRun` transport; keep short-lived flow control only |
| `backend/src/runtime/runs/*` | Redis/in-memory run registry for chat turn streaming | Keep as transport state with TTL; never project to Mission Console or Mission History |
| `backend/src/gateway/routers/runs.py`, `thread_runs.py` | Public chat turn run endpoints | Preserve chat streaming semantics, but rename contracts away from mission/run history concepts |
| `backend/src/agents/middlewares/capability_skill_preload.py` | Loads capability route cards into chat state | Reduce to MissionPolicy route hints; do not expose raw graph/skill prompts |
| `backend/src/agents/middlewares/mission_context.py` | Provides current mission/execution context to chat | Repoint to MissionRun snapshot and active review/pause state |
| `backend/src/agents/middlewares/execution.py` | Tool execution routing for chat tools | Remove execution-specific launcher responsibility |

## Target Responsibilities

WorkspaceAgent owns:

1. Intent understanding.
2. Direct advisory answers.
3. One-shot clarification when minimum context is missing.
4. Mission start request when task is durable and context is enough.
5. Mission resume when user replies to a paused mission.
6. Review turn interpretation: accept, reject, regenerate, continue, ask about evidence.
7. Natural language narration of mission state.

WorkspaceAgent does not own:

1. Mission lifecycle state.
2. Tool permission final decision.
3. Room writes.
4. Sandbox acquisition.
5. Subagent job polling.
6. Commit state.
7. ChatTurnRun persistence beyond transport TTL.

## ChatTurnRun Boundary

`ChatTurnRun` is not a mission. It exists only to stream, cancel, await, or recover one chat request while that request is in flight.

```text
ChatTurnRun owns: SSE stream id, disconnect mode, abort signal, worker task id, short TTL transport metadata
ChatTurnRun does not own: mission status, stage status, review state, evidence, artifacts, commits, Run History
```

`ThreadTurnBilling` is a separate financial aggregate, not an extension of ChatTurnRun. One required client `request_id`, bound to the authenticated actor, authorizes one bounded hold and user message before provider work; reconnects reuse it, while transient run ids and generated fallback keys are forbidden. Settlement atomically binds the assistant message, non-zero usage receipt, and one credit transaction. If an authorization commits but both responses are lost, compensation addresses it by the same idempotency key under the canonical user-row lock. Released/expired rows remain financial audit records but never appear in Mission history or Mission Console.

ChatTurn admission atomically stores the private actor-global request key, canonical payload fingerprint, serialized dispatch payload, and due dispatch intent in TTL Redis transport state before broker publication. Duplicate HTTP launches return the indexed transport before multitask handling; reusing the key with a different payload is a conflict. Gateway publication is best effort and a Celery-beat reconciler republishes due intents at least once with a deterministic task id. Worker execution is owner-fenced: lease loss cancels the local provider task, temporary Redis failure retries through Celery, and stale workers cannot publish terminal status, billing cleanup, or stream completion. Gateway hydration is read-only. Terminal state uses Redis TTL and amortized index pruning rather than process-local sleeper cleanup. The request key is serialized explicitly to the worker and never smuggled through user metadata.

Production rule:

- Chat turn transport can live in Redis/memory and expire.
- Chat messages persist through Thread / ChatBlock; production user/assistant append is owned by the atomic billing transaction.
- Long tasks persist through MissionRun / MissionItem.
- If a chat stream dies after mission creation, recovery comes from MissionRun lookup by idempotency key or workspace mission list.
- Frontend must not display ChatTurnRun as a research run.

## Tool Boundary

Replace `launch_feature` semantics with a small typed AgentAction boundary:

```text
answer
ask_user
start_mission
steer_mission
propose_review
request_commit
```

MissionRuntime APIs implement the mission actions; WorkspaceAgent does not call room or commit services directly. Hard rule: the model cannot claim a mission started unless MissionRuntime returns a successful MissionRun id. The current guard in `thread_turn_handler.py` that catches "said started but no launch_feature result" should become a mission-start guard.

## Mission Start Contract

The provider sends only model-owned intent:

```text
title: concise user-facing navigation label
objective
mission_policy_id
initial_params
input_refs: mission-input:<sha256>[]
```

`title` and `objective` are separate contracts. The title should identify the task in the Mission Console; it must never be produced by truncating the complete objective.

The authenticated application boundary injects:

```text
workspace_id / thread_id / user_id / workspace_type
raw_user_message_id / mission_idempotency_key
user-selected review_mode
model_id
reasoning_effort
model_capability_profile_hash
validated MissionInput manifests and runtime_context_refs
```

MissionRuntime returns:

```text
mission_id
status
visible_title
current_stage
chat_receipt_blocks
mission_console_hint
```

No `ExecutionRecord`, `feature_id`, graph-template node ids, or ChatTurnRun ids should appear in the public mission start response.

## Attachment and MissionInput Boundary

- The upload API returns the complete typed attachment contract; the frontend must not reduce it to name/path pairs.
- `ThreadTurnHandler` validates the canonical thread-local path and seals readable PDF, preprocessed Markdown, or plain text through `MissionInputService` before persisting the user turn.
- Message metadata stores `mission_inputs` and bounded `attachment_contexts`; attachment content is never injected into a synthetic `<uploaded_files>` message.
- If preprocessing was pending, a later turn may promote that same server-owned attachment to a sealed input. The user does not need to re-upload it.
- WorkspaceAgent may answer a small question from the verified excerpt. For long work it selects exact related refs; MissionRuntime pins those manifests in the Mission snapshot.
- Mission and subagents read full bounded content only through canonical `workspace.read_input`. The reader revalidates workspace, thread, hash, and size, and rejects any ref not pinned to the Mission.
- No compatibility middleware, alternate path resolver, duplicate preprocessing field, or raw client filesystem path participates in this flow.

Concurrency rules:

- One thread has at most one non-terminal foreground mission. A clearly related request becomes a durable steer/context command. A clearly unrelated long task does not silently queue or replace work: Chat offers “切换到新任务 / 当前任务完成后继续 / 保持当前任务” and waits for an explicit choice.
- When no foreground mission exists, the handler resolves exactly one bounded continuation target. A Mission id explicitly referenced as a continuation in the current message takes precedence after workspace, thread, user, terminal-status, and policy validation; otherwise the latest terminal Mission from the same authenticated thread is used. Raw Mission ledgers and review queues are not chat context.
- An explicit continuation start must copy that exact target id into `parent_mission_id`; an explicit new task must leave it null. Invalid, unauthorized, non-terminal, or ambiguous explicit ids fail without falling back to the latest Mission. The server validates equality before Mission creation, so the model cannot select an arbitrary historical parent.
- User input during an active mission is classified as `steer`, `context`, `correction`, `pause`, `cancel`, `review`, or `advisory` before it reaches MissionRuntime.
- Mission-affecting input gets a stable command id and is applied at a safe loop boundary. Advisory side questions may use a separate ChatTurnRun but cannot mutate mission state.
- A terminal MissionRun is not reopened. A materially new continuation creates a linked child mission and inherits only passed stage receipts, their server-owned dynamic cardinality, and canonical refs used by accepted work. It never inherits failure counters, leases, pending review state, or unaccepted drafts.

Mission preflight rules:

- Resolve the selected model to a live-probed ModelCapabilityProfile before creating MissionRun.
- A mission that needs tools requires valid provider-structured function name and schema-conformant arguments. Text/XML/Markdown tool imitation is rejected.
- If the selected model lacks a required capability, WorkspaceAgent explains the concrete limitation and asks whether to switch to a verified model or narrow the task. It never silently reroutes.
- Effort remains the user's `low | medium | high | xhigh` selection. Stage quality is evaluated from outputs; effort is raised only after explicit confirmation.

## Route Hints

Capability route cards should be reduced into bounded route hints:

```text
mission_policy_id
when_to_use
not_for
minimum_context
clarifying_question_template
quality_promise
review_risk_notes
```

Do not inject:

- raw `graph_template`
- raw subagent prompt
- tool schema internals
- admin-only capability ids
- old workflow step ids

## Review Turns

WorkspaceAgent should treat user review messages as first-class mission input:

```text
accept selected
reject selected
save draft only
regenerate this stage
continue with stronger evidence
explain why this needs review
```

These update MissionReviewItem decision fields or create MissionRuntime stage commands; they do not call room services directly. A completed mission stays completed while its pending review/commit axes continue independently.

## Migration Steps

1. Add MissionRuntime start/resume API and client boundary.
2. Change `agent.py` tool set from `launch_feature_tool` to mission tools.
3. Rename current gateway/runtime run contracts to ChatTurnRun transport contracts or equivalent wording.
4. Replace `launch_feature_params` metadata handling in `thread_turn_handler.py` with mission seed metadata.
5. Replace launch result blocks with `mission.receipt` / `mission.status_line` blocks.
6. Delete `backend/src/tools/builtins/launch_feature.py` once callers are migrated.
7. Delete text guards tied to `launch_feature` and replace with mission-start guard.
8. Remove Chat -> Lead vocabulary from prompts and module docstrings.
9. Replace model-name/boolean capability guesses with ModelCapabilityProfile preflight; delete text tool-call parsing from the mission path.

## Tests

Backend:

- Advisory answer does not create MissionRun.
- Missing context returns clarification and no MissionRun.
- Durable task creates exactly one MissionRun per idempotency key.
- Duplicate model tool call returns existing MissionRun.
- Review reply updates MissionReviewItem decision state, not room write.
- WorkspaceAgent cannot access sandbox tools directly.
- ChatTurnRun expiration does not delete Thread messages or MissionRun state.
- A second durable task in the same thread is not started while a non-terminal foreground mission exists.
- Advisory input during a mission cannot silently alter the mission without a durable command item.
- A tool-requiring mission cannot start on a model whose strict tool-argument probe failed.
- WorkspaceAgent never parses assistant text as a mission action and never silently switches models.
- An unrelated second task produces an explicit switch/queue/keep choice instead of replacing the active mission.

Frontend/browser:

- User says "开始梳理文献空白" and sees mission receipt only after real mission id is returned.
- User refreshes after receipt; chat anchors to MissionRun.
- User says "先别保存，继续补证"; an in-loop waiting mission resumes, while a completed mission creates a linked child mission without rewriting its terminal history.
