# Chat-Driven Mission Console Design

Date: 2026-07-07
Status: Approved direction, pending implementation plan
Owner: Wenjin workspace experience

## Summary

Wenjin should stop presenting workspace capabilities as a default right-side button grid. The default user journey should be chat-first: the Chat Agent understands intent, asks the minimum needed clarification, chooses whether to answer inline or call `launch_feature`, and preserves conversation context across the launch. The right side becomes a minimal Mission Console that appears when there is execution state, review state, evidence state, or history state worth showing.

This design keeps `capability.v2` as the backend mission contract, not as a primary user-facing menu. Capability remains responsible for routing hints, required context, quality gates, sandbox policy, review policy, citation policy, pricing, and execution constraints. Users should not need to understand capability names or restart from a static workflow card.

## Problem

The current research workbench is too heavy for undergraduate and ordinary master's users. The right panel shows many capability cards, each card describes a formal workflow, and clicking a card sends a generic prompt such as "I want to use this capability, please confirm required information first." This creates three product failures.

First, the panel competes with chat. The user has already described a research intent in the conversation, but the right panel asks them to choose from a catalog again.

Second, capability launch feels like a fixed workflow from an older generation of AI products. The base model and Super Harness Agent are strong enough to dynamically plan, clarify, and route, but the current UI makes the user choose a static button before the system can adapt.

Third, right-side density is high even when no mission exists. Evidence, review, capability entry, and run history are valuable, but showing them all by default raises cognitive load before the user has a task.

## Product Decision

Use option C: an extremely light right-side panel by default. Task navigation belongs to the Chat Agent.

The product model becomes:

- Chat Agent: intent understanding, clarification, route choice, task navigation, and `launch_feature` calls.
- Lead Agent and TeamKernel: mission execution, expert orchestration, evidence, artifacts, review packets, and writeback staging.
- Capability: backend mission contract and governance. It is not the default user-facing entry grid.
- Mission Console: right-side state projection for active runs, review gates, evidence summaries, and history.

## Non-Goals

This redesign does not introduce a second router, embedding matcher, frontend capability classifier, or new execution stream. It does not add a separate feature slug page. It does not let the frontend bypass Chat Agent. It does not persist long-term change history for accepted/rejected drafts. Reviewable diffs and old versions remain temporary execution-backed material until accepted, rejected, or superseded.

## User Experience

### Idle State

When there is no active run, no pending review, and no meaningful selected history, the right side should be collapsed or visually quiet.

The right side should not show the capability grid. It may show a compact empty state:

"还没有正在执行的研究任务。直接在左侧描述你想推进的论文、实验或材料。"

Optional low-emphasis actions:

- 查看历史
- 证据库

These actions open existing rooms or drawers. They do not start a capability.

### Chat-Driven Task Navigation

The user describes intent in chat. The Chat Agent decides among four outcomes:

- Answer inline for lightweight questions.
- Ask one concise clarification when exactly one minimum context field is missing.
- Offer two natural-language choices when two mission paths are plausible.
- Call `launch_feature` when the user has requested a durable multi-step deliverable and enough context exists.

The Chat Agent must carry forward conversation history. If the user has already said "联邦学习结合大模型微调", selecting or confirming SCI draft work must reuse that topic without asking from scratch.

Capability ids, schema names, trigger phrases, and internal route-card labels must not appear in normal user-facing copy.

### Launch Receipt

When `launch_feature` returns `status == "launched"`, chat shows a concise launch receipt and the Mission Console opens automatically.

The receipt should answer:

- What mission started.
- What the first stage is.
- What the user can still change.

It should not expose raw tool JSON, capability schema, or full graph internals.

### Running State

The Mission Console focuses on the current mission, not a dashboard of everything.

Default running view:

- Mission title, derived from `RunView.title`.
- One-line current status.
- 2 to 5 stage markers, projected from the run view or TeamKernel phases.
- Current expert/team activity only when it helps the user understand progress.
- A natural-language intervention box for "补充要求 / 改方向 / 暂停后继续".

The default view should avoid raw logs, raw node JSON, full DAG diagrams, or always-on expert roster details. Users can expand details when needed.

### Review State

Review state is the strongest right-side state. If there are pending review items, the Mission Console should prioritize them over generic progress.

Rules:

- Low-risk outputs can be preselected.
- Evidence, citation, claim, and primary document writes are high-risk and unchecked by default.
- Bulk accept is disabled when high-risk items are present.
- Accept/reject writes through existing execution-backed review and commit services.
- Accepted old versions and temporary materialization progress are removed when no longer needed. No long-term change-history table is introduced.

### Evidence State

Evidence is summarized by default and expanded on demand.

Default copy should be short, for example:

"本轮使用 6 条文献证据，2 条需要确认。"

Expanded evidence view can show source title, evidence strength, citation risk, and related claim. It must not expose raw stdout, internal harness refs, raw schema ids, or unbounded tool output.

### Completed State

After a mission completes and there are no pending review decisions, the Mission Console should collapse back toward a light summary:

- Final status.
- Main outputs.
- Review status.
- Open generated document or history.

The user should naturally continue in chat, for example: "继续深化方法部分" or "把这个改成综述方向". The Chat Agent should treat that as follow-up mission context, not as a new cold start.

## Information Architecture

The default workspace should have three layers:

1. Primary layer: chat conversation and user intent.
2. Mission layer: right-side current run, review, evidence, or completion summary.
3. Detail layer: expandable run history, evidence ledger, expert trace, and room writeback details.

The capability catalog is not part of the primary layer. It can remain available to admin/catalog surfaces and possibly a low-emphasis advanced drawer, but not as the default workspace panel.

## Frontend Design

### LiveWorkflowPanel

`LiveWorkflowPanel` should stop rendering the feature grid in the default overview. Its responsibilities should narrow to mission projection:

- idle summary
- current run
- review queue
- evidence summary
- run history access
- intervention affordance

`handleLaunchFeature(feature)` should be removed from the default panel path. If a route seed or history action needs to resume a capability, it should enter through ChatPanel metadata and Chat Agent orchestration, not through a local panel button.

### OverviewView

The existing `OverviewView` should be redesigned or replaced. It should not be a capability launcher.

New state order:

1. Pending review
2. Active run
3. Selected/completed run summary
4. Idle empty state

This state order means the panel always answers "what needs attention now?" rather than "what features exist?"

### Workbench Header

The header should use fewer tabs by default.

Visible by default:

- Current mission label or "研究任务"
- Expand/collapse action

Conditional tabs:

- Review appears only with pending review items.
- Evidence appears only with evidence items.
- Progress appears only with active or selected run.
- History appears as a small secondary action, not a primary tab when idle.

### Layout

Desktop:

- Idle: right side collapsed to a narrow rail or a visually quiet summary.
- Active/review: right side expands to a useful width.
- Fullscreen remains available for review-heavy states.

Mobile:

- Mission Console is a bottom sheet or drawer.
- Chat remains the primary surface.

The visual system should keep `--wjn-*` tokens and reduce card nesting, borders, status chips, and repeated metadata labels. This is a density reduction, not a decorative redesign.

## Backend and Agent Design

### Chat Agent

The Chat Agent is the only user-facing task navigator. It should use DB-backed route cards and conversation history to decide whether to answer, clarify, offer choices, or launch.

Required behavior:

- Reuse explicit user context from recent turns.
- Do not ask for a topic if it is already present.
- When launching, pass extracted params into `launch_feature`, such as `topic`, `goal`, `target_journal`, `existing_materials_summary`, and `raw_message` when available.
- Keep choices natural-language. Do not expose capability ids.
- Do not launch when the user only asks a concept question or local writing edit.

### Capability

Capability remains the mission contract:

- routing hints
- minimum context
- methodology
- sandbox policy
- citation policy
- review policy
- quality gates
- pricing policy
- result staging rules

Capability display metadata may still exist for admin and advanced browsing, but the default workspace does not render it as a grid of launch buttons.

### Launch Feature

`launch_feature` remains the execution creation boundary. It must continue to return advisory when required context is missing, and launched when execution starts.

No frontend direct execution endpoint should be added.

### Follow-Up and Intervention

Follow-up should be chat-first. A user saying "继续", "换成综述方向", "先做 gap", or "暂停这个，补充一个约束" should be interpreted by Chat Agent with active execution context.

The Mission Console intervention box remains useful during active runs, but it should send natural-language instructions through the same chat/orchestration path.

## Data Flow

Idle:

```text
Workspace load
  -> hydrate chat + executions
  -> LiveWorkflowPanel projects state
  -> no active/review/evidence state
  -> collapsed Mission Console
```

Launch:

```text
User chat message
  -> Chat Agent with capability route cards
  -> answer / clarify / offer choices / launch_feature
  -> launch_feature creates ExecutionRecord when context is enough
  -> tool_result launched
  -> execution store receives run
  -> Mission Console opens current run
```

Review:

```text
Lead Agent produces TaskReport / review packet
  -> ExecutionRecord projection
  -> RunView derives review items and evidence items
  -> LiveWorkflowViewModel selects pending review state
  -> Mission Console prioritizes review
  -> user accepts/rejects
  -> ExecutionCommitService writes selected units
  -> temporary old-version materialization state is cleared
```

Follow-up:

```text
User sends follow-up in chat
  -> Chat Agent receives recent conversation and active/selected execution context
  -> may resume same execution, launch a child mission, or answer inline
  -> Mission Console updates from execution projection
```

## Error Handling

Missing context:

- Chat asks one concise question.
- Mission Console does not open a fake run.

Lead busy:

- Chat explains that a mission is running and offers to add instructions, wait, or stop at a safe point.
- Mission Console shows the active mission.

Launch failure:

- Chat shows a plain-language failure with next action.
- Mission Console only opens if there is an execution record to inspect.

Review failure:

- Keep the failed review item visible.
- Show retry/action feedback inline.
- Do not mutate local review state as the source of truth.

Evidence risk:

- High-risk evidence blocks bulk accept.
- Unsupported claims require user decision or revision.

## Accessibility and Interaction Requirements

- All controls must be keyboard reachable.
- Collapsed Mission Console must have an accessible label and clear expand action.
- Tab labels and badges must not depend on icon-only meaning.
- Loading state must be visible while the model is thinking or a mission is starting.
- Reduced-motion users receive instant or minimal transitions.
- No text should overflow in the right rail, review items, or stage labels.

## Technical Debt to Remove

- Remove default capability grid from `OverviewView`.
- Remove default right-panel direct `handleLaunchFeature(feature)` workflow.
- Remove UI copy that tells users to click a capability before the team can work.
- Remove any front-end local capability matching introduced for the panel.
- Keep `run-ui-store` focused on UI focus/badges only. Do not add mission state there.
- Keep `LiveWorkflowViewModel` as the projection boundary. Do not parse raw harness schemas in view components.
- Do not add compatibility wrappers named legacy, compat, or fallback.

## Implementation Boundaries

Likely frontend files:

- `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/OverviewView.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/WorkbenchHeader.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/useLiveWorkflowViewModel.ts`
- `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`
- `frontend/stores/workbench-layout-store.ts`
- `frontend/lib/execution-run-view.ts`

Likely backend and prompt files:

- `backend/src/agents/chat_agent/agent.py`
- `backend/src/agents/chat_agent/prompts/`
- `backend/src/tools/builtins/launch_feature.py`
- `backend/src/agents/middlewares/capability_skill_preload.py`
- capability seed files under `backend/seed/capabilities/`

Backend changes should be limited to Chat Agent routing quality if current prompts still ask from scratch. The primary UI change should not create new backend execution concepts.

## Testing Plan

Frontend unit tests:

- Idle `LiveWorkflowPanel` does not render capability launch cards.
- Idle state renders a compact mission empty state.
- Pending review state takes priority over idle and progress.
- Active run opens progress state automatically.
- Evidence tab appears only when evidence exists.
- Feature buttons are not available in default overview.
- Model thinking and launch pending states remain visible.

Chat and integration tests:

- Given prior user context "联邦学习结合大模型微调", asking to start SCI draft launches with topic params and does not ask topic again.
- Lightweight concept questions answer inline without launch.
- Ambiguous durable intent offers natural-language choices without capability ids.
- Missing required context returns advisory and does not create execution.
- `tool_result.status == "launched"` still anchors run receipt and Mission Console state.

Regression tests:

- `RunView` remains the only execution projection used by LiveWorkflowPanel.
- No raw tool JSON appears in chat or Mission Console.
- High-risk review items block bulk accept.
- Accepted change-unit temporary materialization state is cleared after finalize.

Commands:

```bash
cd frontend && npm run typecheck
cd frontend && npx vitest run
cd backend && .venv/bin/python -m pytest tests/integration/test_chat_to_feature_launch.py tests/tools/test_launch_feature_tool.py -v
```

## Acceptance Criteria

The redesign is successful when:

- A new user can ignore the right side and start naturally from chat.
- The right side no longer looks like a catalog of workflows.
- Existing conversation context is reused when launching a mission.
- Capability remains powerful in the backend but mostly invisible to normal users.
- The Mission Console appears only when there is state worth reviewing.
- Review and evidence remain stricter than ordinary progress UI.
- No new execution fact source, route bypass, compatibility layer, or frontend matcher is introduced.

