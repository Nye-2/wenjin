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
| Panel layout | Vertical card feed | Supports multiple executions, scrollable, information-dense |
| Graph visualization | Phase timeline (B-enhanced) | Zero auto-layout, no edge-routing, deterministic CSS flex layout |
| Node detail interaction | Inline expand within card | No drawer, stays in context |
| Thinking delivery | Real-time SSE delta stream | Frontend store already handles `execution.node.delta` events |
| Completed card | Summary + collapsible full result | Progressive disclosure |
| ReactFlow dependency | Remove entirely | Replaced by pure HTML/CSS phase timeline |

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
- Delete ReactFlow dependency (`@xyflow/react`)

## Section 2: Execution Card Component

### Card Header (always visible)

```
┌──────────────────────────────────────────────────┐
│ [icon] Capability Name                   status › │
│        type · N nodes · duration                  │
└──────────────────────────────────────────────────┘
```

- **Icon**: 32×32 rounded square. Completed = green gradient ✓. In-progress = purple gradient with pulse.
- **Title**: `capability.display_name`
- **Subtitle**: `workspace_type · node_count · duration_seconds`
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

- **Animation**: `max-height` 0→auto, 200ms spring ease (`--v2-ease-standard`)
- **Tabs**: Input / Output / Thinking (3 tabs; Tools merged into Output sub-section)
- **Data source**: `node_states[nodeId]` from store — no REST fetch needed
- **Only one expanded at a time**: clicking another pill collapses previous
- **Click outside**: collapses detail
- **Token usage bar**: `In:` and `Out:` monospace counts at bottom

## Section 4: Backend — Streaming Thinking (Phase 3)

### Current behavior

React subagent runs full LLM loop, returns `SubagentResult` only on completion. No intermediate data during execution.

### New data flow

```
React Subagent (MiMo LLM loop)
  │
  │  every thinking token chunk
  ▼
SubagentContext.emit_delta(thinking="...")
  │
  ▼
LeadAgentRuntime._emit(node_id, "delta", {thinking, output_preview})
  │
  ▼
publish_execution_event(exec_id, "execution.node.delta", payload)
  │
  ▼
Redis Stream → SSE → Frontend
                              ↓
         execution-store.applyStreamEvent("execution.node.delta")
                              ↓
         node_states[nodeId].thinking += delta (append)
```

### Files to modify

| Layer | File | Change |
|-------|------|--------|
| Subagent | `subagents/v2/base.py` | Add `emit_delta` callback to `SubagentContext` |
| Subagent | `subagents/v2/types/react.py` | Hook LLM streaming, call `emit_delta` every N tokens |
| Runtime | `agents/lead_agent/v2/runtime.py` | Wire `emit_delta` from runner factory to SubagentContext |
| Publisher | `services/execution_event_publisher.py` | No change — already supports arbitrary event_name |
| FE Store | `stores/execution-store.ts` | Verify `execution.node.delta` appends thinking |
| FE Hook | `hooks/useExecutionStreamV2.ts` | Reflect thinking delta to card component |

### Throttling

- Thinking delta emitted every **500ms** (batch accumulate, not per-token)
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

Reuse existing `execution-store` (Zustand). Changes:

- `activeExecutionId: string | null` → `activeExecutionIds: string[]` (support multiple concurrent executions)
- `selectedNodeId` scopes to card context (only one node detail expanded across all cards)
- SSE hooks handle multiple execution streams via workspace SSE multiplexing

### Data source mapping

| Data | Source | Event |
|------|--------|-------|
| Phase structure | `graph_structure.nodes[].phase` | `execution.graph_structure` |
| Node status | `node_states[nodeId].status` | `execution.node` |
| Node input/output | `node_states[nodeId].input/output` | DB write → SSE push |
| Thinking (real-time) | `node_states[nodeId].thinking` | `execution.node.delta` (Phase 3) |
| Summary/tags | `result_summary` + `outputs` | `execution.completed` |

## Scope

### Phase 2 (FE redesign — this implementation)

- Replace ReactFlow with card feed + phase timeline
- Full-width cards, vertical stacking
- In-progress card: progress bar + phase timeline + node pills + inline detail
- Completed card: summary + tags + collapsible full result
- Remove `@xyflow/react` dependency
- Remove `GraphCanvas.tsx`, `PhaseNode.tsx`, `NodeDetailDrawer.tsx`
- Update `execution-store` to support `activeExecutionIds: string[]`
- All styling via existing `--v2-*` CSS tokens

### Phase 3 (Streaming thinking — next implementation)

- Add `emit_delta` to `SubagentContext`
- Hook LLM streaming in react subagent
- Wire delta events through runtime → Redis → SSE
- 500ms throttled thinking batch
- FE: wire `execution.node.delta` to node inline detail + thinking preview
