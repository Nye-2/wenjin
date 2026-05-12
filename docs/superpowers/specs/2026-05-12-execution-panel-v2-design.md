# Execution Panel V2 — Card Feed + Phase Timeline + Streaming Thinking

Date: 2026-05-12

## Overview

Redesign the right panel from a single full-screen ReactFlow graph into a vertical card feed. Each card represents one execution. In-progress cards show a phase-based timeline with real-time thinking. Completed cards show result summaries with expandable full output.

## Background

The current implementation uses `@xyflow/react` (ReactFlow) to render execution nodes as a full-screen graph. Problems:

1. Two nodes fill the entire panel — layout waste
2. Curved edges look crooked and unprofessional
3. No progress context — users stare at "running" dots with no information
4. No real-time thinking — node results only visible after completion
5. Only one execution visible at a time
6. NodeDetailDrawer is a separate overlay, disconnected from the graph

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Panel layout | Vertical card feed | Information-dense, scrollable history |
| Graph visualization | Phase timeline (B-enhanced) | Zero auto-layout, no edge-routing, deterministic CSS flex layout |
| Node detail interaction | Inline expand within card | No drawer, stays in context |
| Thinking delivery | Real-time SSE delta stream (append mode) | Frontend store already handles `execution.node.delta` events |
| Completed card | Summary + collapsible full result | Progressive disclosure |
| ReactFlow dependency | Remove entirely | Replaced by pure HTML/CSS phase timeline |
| Concurrency model | Single execution at a time | `launch_feature` tool already blocks concurrent triggers with `lead_busy` advisory |
| Card title source | Denormalized on ExecutionRecord | Write `display_name` + `workspace_type` at creation time |

## Code Review Findings (pre-implementation audit)

### Finding 1: Thinking delta is replaced, not appended (CRITICAL)

**Current store behavior** (`execution-store.ts:146`):
```typescript
nodeState.thinking = event.payload.thinking;  // full replacement
```

**Decision**: Change store to **append mode**. Backend sends incremental chunks, store concatenates:
```typescript
nodeState.thinking = (nodeState.thinking || "") + event.payload.thinking;
```

This means:
- Backend sends incremental text fragments (cheaper payload)
- Store accumulates on each delta
- No need for backend to maintain accumulated state

### Finding 2: Card title data missing (CRITICAL)

`ExecutionRecord` stores `feature_id` but not the capability `display_name`. `GET /executions/{id}` does not return `workspace_type` either (field exists on model but omitted from endpoint).

**Decision**: Denormalize at creation time. In `execution_service.create_execution()`, add `display_name` and `workspace_type` parameters. Write them onto the record. The `launch_feature` tool has access to the resolved Capability object at dispatch time.

### Finding 3: Single execution architecture is sufficient

The chat agent's `launch_feature` tool (`backend/src/tools/builtins/launch_feature.py:100-114`) already queries for active executions per workspace and returns `lead_busy` advisory if one exists. No concurrent executions are possible through the normal chat flow.

**Decision**: Keep `currentExecutionId: string | null` as-is. The card list shows completed history + one active execution. No multi-subscription needed.

### Finding 4: Phase info mapping gap

Backend `_to_panel_graph` sends nodes with `{id, phase, task, subagent_type, label}` — `phase` is a string field. But the frontend type `ExecutionGraphNode` only declares `{id, type, label?, metadata?}`. The `phase` field is extra data not captured by the type.

Current `useExecutionStreamV2` reads `n.metadata?.phase_index` (a number), but backend never puts phase info in metadata — it's a top-level field.

**Decision**: When processing `execution.graph_structure` in the store, map `node.phase` → `node.metadata.phase` and compute `metadata.phase_index` from the phase order. The new components read directly from the raw node data (TypeScript can use the actual shape without relying on the narrow type).

### Finding 5: Redis Stream maxlen=512

`publish_execution_event` caps streams at 512 entries. High-frequency delta events could trim older events for slow consumers.

**Decision**: Increase `maxlen` to 2048 for execution streams. Low priority, defer to Phase 3 implementation.

## Section 1: Panel Architecture

The `LiveWorkflowPanel` renders three zones:

```
┌─────────────────────────┐
│  Header zone             │
│  - Idle: ProductIntro    │
│  - Active: progress line │
├─────────────────────────┤
│  Card list (scrollable)  │
│  - Full-width cards      │
│  - Newest on top         │
│  - Only one expanded     │
├─────────────────────────┤
│  Footer: load history    │
└─────────────────────────┘
```

- Cards are full-width, stacked vertically, scrollable
- Only one card's detail view is expanded at a time (click another to collapse)
- Idle state (ProductIntro) and active cards coexist
- New execution auto-expands its card and collapses any previously expanded card
- Delete ReactFlow dependency (`@xyflow/react`) — only used in 3 files (GraphCanvas, PhaseNode, 1 test)

## Section 2: Execution Card Component

### Card Header (always visible)

```
┌──────────────────────────────────────────────────┐
│ [icon] Capability Name                   status › │
│        type · N nodes · duration                  │
└──────────────────────────────────────────────────┘
```

- **Icon**: 32×32 rounded square. Completed = green gradient ✓. In-progress = purple gradient with pulse.
- **Title**: `record.display_name` (denormalized onto ExecutionRecord at creation)
- **Subtitle**: `record.workspace_type · node_count · duration_seconds`
- **Status badge**: pill tag — 已完成 (green) / 进行中 (purple) / 失败 (red)
- **Expand arrow**: rotates on toggle

### In-Progress Card (expanded)

```
┌──────────────────────────────────────────────────┐
│ header row                                        │
├──────────────────────────────────────────────────┤
│ [progress bar: ■ ■ ■ □ □ □]  2/6 · generating    │
│                                                   │
│ ● Phase 1 · Research                              │
│   [✓ Search 28s] [✓ Analyze 45s]                 │
│   │                                               │
│ ● Phase 2 · Generate  ↺ loop 1/3                 │
│   [⟳ Generate] ↔ [QA]                            │
│   ┌ THINKING ──────────────────────┐             │
│   │ Generating draft based on...   │             │
│   └────────────────────────────────┘             │
│   │                                               │
│ ○ Phase 3 · Finalize                              │
│   [Polish] [Output]                               │
└──────────────────────────────────────────────────┘
```

**Progress bar**: colored segments at card top. Green = completed, Purple (pulsing) = running, Gray = pending. Equal width per segment.

**Timeline**: left vertical rail with phase number dots. Dot styles:
- Completed: green gradient with checkmark SVG
- Running: purple gradient with clock SVG, pulse animation
- Pending: gray with number

**Node pills**: horizontal flex within each phase row. Click to expand inline detail.

**Loop label**: yellow `↺ 循环 N/M` tag next to phase title. No curved lines.

**Thinking preview**: below the currently running node pill, monospace font, max 3 lines, purple-tinted background with left border.

### Failed Card (expanded)

Same layout as in-progress card but all phases/nodes show final state. Error node highlighted in red with error message displayed inline. No thinking preview.

### Completed Card (expanded)

```
┌──────────────────────────────────────────────────┐
│ header row                                        │
├──────────────────────────────────────────────────┤
│ Result Summary                                     │
│ Found 23 papers covering federated learning ×     │
│ LoRA, adaptive rank allocation, and...            │
│                                                   │
│ [23 papers] [3 directions] [8 high-relevance]     │
│                                                   │
│ ▸ View full result                                │
│ ┌──────────────────────────────────────────────┐ │
│ │ (expanded: full output, scrollable)           │ │
│ └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

- **Summary**: from `TaskReport.narrative` or `result_summary`
- **Tags**: extracted from `TaskReport.outputs` key fields (auto-generated)
- **Full result**: collapsible section, shows all outputs
- **Action buttons**: if result_card exists, show "View/Commit" buttons

## Section 3: Inline Node Detail

Clicking a node pill expands detail **below that phase row**:

```
  ● Phase 2 · Generate  ↺ loop 1/3
    [⟳ Generate]  ← highlighted border
    ┌────────────────────────────────────┐
    │  Input  │  Output  │  Thinking     │  ← 3 tabs
    │ ┌────────────────────────────────┐ │
    │ │ query: "federated LoRA"        │ │
    │ │ year_min: 2019                 │ │
    │ └────────────────────────────────┘ │
    │ In: 1,240 · Out: 856              │  ← token usage
    └────────────────────────────────────┘
```

- **Animation**: CSS Grid `grid-template-rows: 0fr → 1fr`, 200ms spring ease (`--v2-ease-standard`). (Not `max-height: auto` which doesn't animate.)
- **Tabs**: Input / Output / Thinking (3 tabs; Tools merged into Output sub-section)
- **Data source**: `node_states[nodeId]` from store — no REST fetch needed
- **Only one expanded at a time**: clicking another pill collapses previous
- **Click outside**: collapses detail
- **Token usage bar**: `In:` and `Out:` monospace counts at bottom

## Section 4: Backend — Streaming Thinking (Phase 3)

### Current behavior

React subagent runs full LLM loop via `ainvoke()` (not streaming). Returns `SubagentResult` only on completion. `SubagentContext` is a pure data container with no callback fields. No intermediate data during execution.

### New data flow

```
React Subagent (MiMo LLM loop)
  │
  │  every thinking token chunk
  ▼
SubagentContext.emit_delta(thinking="...chunk...")
  │
  ▼
LeadAgentRuntime._emit(node_id, "delta", {thinking: "chunk"})
  │
  ▼
publish_execution_event(exec_id, "execution.node.delta", payload)
  │
  ▼
Redis Stream → SSE → Frontend
                              ↓
         execution-store.applyStreamEvent("execution.node.delta")
                              ↓
         node_states[nodeId].thinking += delta  (APPEND mode)
```

### Backend changes

| Layer | File | Change |
|-------|------|--------|
| **Subagent** | `subagents/v2/base.py` | Add `emit_delta: Callable[[str, str], Awaitable[None]] \| None = None` to `SubagentContext` dataclass |
| **Subagent** | `subagents/v2/types/react.py` | Switch `ainvoke()` → `astream()`. Pass `thinking_enabled=True` to `create_chat_model`. Extract thinking chunks from stream, call `ctx.emit_delta("thinking", chunk)` |
| **Runtime** | `agents/lead_agent/v2/runtime.py` | In `_build_persisting_runner_factory`, create `emit_delta` closure that calls `_emit(node_id, "delta", {thinking: chunk})`. Pass it to `SubagentContext` in `_default_runner_factory` |
| **Compiler** | `agents/lead_agent/v2/compiler.py` | Accept optional `emit_delta` param in `_default_runner_factory` and forward to `SubagentContext` |
| **Publisher** | `services/execution_event_publisher.py` | No change — supports arbitrary event_name |
| **Model** | `models/factory.py` | No change — already supports `thinking_enabled=True` parameter |

### Frontend store change

In `execution-store.ts`, change `execution.node.delta` handler from replacement to append:
```typescript
// Before (replacement):
nodeState.thinking = event.payload.thinking;

// After (append):
nodeState.thinking = (nodeState.thinking || "") + (event.payload.thinking || "");
```

### Throttling

- Thinking delta emitted every **500ms** (batch accumulate, not per-token)
- Runtime accumulates chunks in a buffer, flushes every 500ms via `asyncio` timer
- `output_preview` sent once on node completion (not streamed)
- If LLM produces no thinking (e.g. searcher = pure API call), no delta events

## Section 5: Frontend Component Architecture

### Component tree

```
LiveWorkflowPanel
  ├── ProductIntro (shown when idle)
  └── ExecutionCardList
        ├── ExecutionCard (×N)
        │     ├── CardHeader
        │     └── CardBody (expanded content)
        │           ├── InProgressView
        │           │     ├── ProgressBar
        │           │     ├── PhaseTimeline
        │           │     │     └── PhaseRow (×N)
        │           │     │           ├── NodePill (×N)
        │           │     │           └── NodeInlineDetail
        │           │     │                 ├── DetailTabs (Input/Output/Thinking)
        │           │     │                 └── TokenUsageBar
        │           │     └── ThinkingPreview
        │           └── CompletedView
        │                 ├── ResultSummary
        │                 ├── ResultTags
        │                 └── FullResultSection (collapsible)
        └── LoadMoreButton
```

### Deleted components

- `GraphCanvas.tsx` — ReactFlow canvas, removed entirely
- `PhaseNode.tsx` — ReactFlow custom node, removed entirely
- `NodeDetailDrawer.tsx` — slide-in drawer, replaced by NodeInlineDetail

### State management

Reuse existing `execution-store` (Zustand). Keep `currentExecutionId: string | null` as single-ID (no multi-concurrent). Changes:

- Add `executionRecords: Map<string, ExecutionRecord>` to store completed execution history for card list
- `selectedNodeId` remains local state in `ExecutionCardList` (only one node detail expanded across all cards)
- SSE hooks unchanged — single subscription to active execution

### Phase mapping in store

When processing `execution.graph_structure` event, map backend node shape to frontend-usable form:

```typescript
// Backend sends: { id, phase: "outline_phase", task: "search", subagent_type: "searcher", label: "检索" }
// Store maps to: { id, label, phase: "outline_phase", phaseIndex: <computed from order>, subagentType: "searcher" }
```

Phase index is computed by iterating `graph_structure.nodes` in order, assigning sequential indices per unique `phase` value.

### Data source mapping

| Data | Source | Event |
|------|--------|-------|
| Phase structure | `graph_structure.nodes[].phase` (string) | `execution.graph_structure` |
| Node status | `node_states[nodeId].status` | `execution.node` |
| Node input/output | `node_states[nodeId].input/output` | DB write → SSE push |
| Thinking (real-time) | `node_states[nodeId].thinking` (append) | `execution.node.delta` (Phase 3) |
| Summary/tags | `result_summary` + `outputs` | `execution.completed` |
| Card title | `record.display_name` (denormalized) | `GET /executions/{id}` |
| Card subtitle | `record.workspace_type` (denormalized) | `GET /executions/{id}` |

## Scope

### Phase 2 (FE redesign + backend metadata fix)

**Backend:**
- Denormalize `display_name` + `workspace_type` onto `ExecutionRecord` at creation time
- Add both fields to `GET /executions/{id}` response
- Add `GET /executions?workspace_id=X&limit=20` list endpoint support for card history

**Frontend:**
- Replace ReactFlow with card feed + phase timeline
- Full-width cards, vertical stacking
- In-progress card: progress bar + phase timeline + node pills + inline detail
- Completed card: summary + tags + collapsible full result
- Fix phase mapping: read `node.phase` from backend data, compute `phaseIndex`
- Remove `@xyflow/react` dependency
- Remove `GraphCanvas.tsx`, `PhaseNode.tsx`, `NodeDetailDrawer.tsx`
- All styling via existing `--v2-*` CSS tokens

### Phase 3 (Streaming thinking)

**Backend:**
- Add `emit_delta` callback to `SubagentContext`
- Switch react subagent from `ainvoke()` to `astream()`
- Pass `thinking_enabled=True` to model factory
- 500ms throttled thinking batch via asyncio timer
- Wire delta events through runtime → Redis → SSE

**Frontend:**
- Change `execution.node.delta` handler to append mode
- Wire thinking delta to NodeInlineDetail + ThinkingPreview components
