# Execution Panel V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the full-screen ReactFlow graph with a vertical card feed showing execution history, phase timelines, inline node detail, and real-time thinking streams.

**Architecture:** Right panel shows a scrollable list of full-width execution cards. In-progress cards display a phase-based timeline with node pills and thinking preview. Completed cards show result summaries. Clicking a node pill expands inline detail. Phase 3 adds streaming thinking from the react subagent via SSE deltas.

**Tech Stack:** Next.js 16, React 19, TypeScript, Tailwind, Zustand, FastAPI, SQLAlchemy, LangChain, Redis Streams, SSE

---

## File Structure

### Backend files to modify

| File | Responsibility |
|------|---------------|
| `backend/src/database/models/execution.py` | Add `display_name` column |
| `backend/alembic/versions/045_add_display_name.py` | New migration |
| `backend/src/services/execution_service.py` | Accept `display_name` in `create_execution` |
| `backend/src/tools/builtins/launch_feature.py` | Pass `display_name` from resolved capability |
| `backend/src/gateway/routers/executions.py` | Include `display_name` + `workspace_type` in GET response |
| `backend/src/subagents/v2/base.py` | Add `emit_delta` callback to `SubagentContext` |
| `backend/src/subagents/v2/types/react.py` | Switch to streaming, emit thinking deltas |
| `backend/src/agents/lead_agent/v2/compiler.py` | Accept and forward `emit_delta` to SubagentContext |
| `backend/src/agents/lead_agent/v2/runtime.py` | Wire `emit_delta` from persisting runner factory |

### Frontend files to modify

| File | Responsibility |
|------|---------------|
| `frontend/lib/api/types.ts` | Update `ExecutionGraphNode` with `phase`, `subagent_type`; update `ExecutionRecord` with `display_name` |
| `frontend/stores/execution-store.ts` | Fix thinking delta to append; fix phase mapping |
| `frontend/hooks/useExecutionStreamV2.ts` | Replace ReactFlow node/edge building with card-ready data shape |
| `frontend/hooks/useWorkspaceEventStream.ts` | Keep history of completed executions |

### Frontend files to create

| File | Responsibility |
|------|---------------|
| `frontend/app/(workbench)/workspaces/[id]/components/ExecutionCardList.tsx` | Scrollable card list container |
| `frontend/app/(workbench)/workspaces/[id]/components/ExecutionCard.tsx` | Single card with header + expand/collapse |
| `frontend/app/(workbench)/workspaces/[id]/components/InProgressView.tsx` | Phase timeline + progress bar for active executions |
| `frontend/app/(workbench)/workspaces/[id]/components/CompletedView.tsx` | Summary + tags + collapsible result |
| `frontend/app/(workbench)/workspaces/[id]/components/PhaseRow.tsx` | Single phase row with node pills |
| `frontend/app/(workbench)/workspaces/[id]/components/NodePill.tsx` | Clickable node status pill |
| `frontend/app/(workbench)/workspaces/[id]/components/NodeInlineDetail.tsx` | Inline detail with tabs (Input/Output/Thinking) |

### Frontend files to delete

| File | Reason |
|------|--------|
| `frontend/app/(workbench)/workspaces/[id]/components/GraphCanvas.tsx` | Replaced by InProgressView |
| `frontend/app/(workbench)/workspaces/[id]/components/PhaseNode.tsx` | Replaced by NodePill |
| `frontend/app/(workbench)/workspaces/[id]/components/NodeDetailDrawer.tsx` | Replaced by NodeInlineDetail |

---

## Phase 2: FE Redesign + Backend Metadata

### Task 1: Backend — Add display_name to ExecutionRecord

**Files:**
- Modify: `backend/src/database/models/execution.py`
- Create: `backend/alembic/versions/045_add_execution_display_name.py`
- Modify: `backend/src/services/execution_service.py`
- Modify: `backend/src/tools/builtins/launch_feature.py`
- Modify: `backend/src/gateway/routers/executions.py`
- Test: `backend/tests/test_execution_display_name.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_execution_display_name.py
"""Test that execution records store and return display_name."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.execution_service import ExecutionService


@pytest.mark.asyncio
async def test_create_execution_stores_display_name():
    """create_execution persists display_name onto the record."""
    db = AsyncMock()
    db.flush = AsyncMock()
    service = ExecutionService(db)

    record = await service.create_execution(
        execution_type="capability",
        user_id="user-1",
        workspace_id="ws-1",
        feature_id="lit_review",
        display_name="文献检索",
        workspace_type="sci",
        commit=False,
    )
    assert record.display_name == "文献检索"
    assert record.workspace_type == "sci"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_execution_display_name.py -v`
Expected: FAIL — `create_execution() got an unexpected keyword argument 'display_name'`

- [ ] **Step 3: Add display_name column to ExecutionRecord model**

In `backend/src/database/models/execution.py`, add after `workspace_type` column (around line 40):

```python
    display_name = Column(String(200), nullable=True)
```

- [ ] **Step 4: Update create_execution to accept display_name**

In `backend/src/services/execution_service.py`, add `display_name` parameter to `create_execution` (around line 38):

```python
    async def create_execution(
        self,
        *,
        execution_type: str,
        user_id: str,
        workspace_id: str | None = None,
        thread_id: str | None = None,
        feature_id: str | None = None,
        entry_skill_id: str | None = None,
        workspace_type: str | None = None,
        display_name: str | None = None,
        params: dict[str, Any] | None = None,
        parent_execution_id: str | None = None,
        commit: bool = True,
    ) -> ExecutionRecord:
        now = datetime.now(UTC)
        record = ExecutionRecord(
            id=generate_uuid(),
            user_id=user_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            execution_type=execution_type,
            feature_id=feature_id,
            entry_skill_id=entry_skill_id,
            workspace_type=workspace_type,
            display_name=display_name,
            status="pending",
            params=dict(params or {}),
            parent_execution_id=parent_execution_id,
            created_at=now,
            updated_at=now,
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_execution_display_name.py -v`
Expected: PASS

- [ ] **Step 6: Update launch_feature to pass display_name**

In `backend/src/tools/builtins/launch_feature.py`, the tool resolves the capability before creating the execution. Find where `execution_service.create_execution` is called (around line 116) and add `display_name` from the resolved capability:

```python
    # Get display_name from resolved capability
    cap_display_name = None
    if capability:
        cap_display_name = getattr(capability, "display_name", None)

    execution = await execution_service.create_execution(
        workspace_id=workspace_id,
        user_id=user_id,
        execution_type="capability",
        feature_id=feature_id,
        workspace_type=workspace_type,
        display_name=cap_display_name,
        params={
            "brief": {
                "capability_id": feature_id,
                "brief": dict(params or {}),
                "raw_message": str(params.get("query") or params.get("topic") or feature_id),
                "decisions": {},
                "workspace_id": workspace_id,
            },
        },
    )
```

Note: The `capability` variable is the resolved `Capability` ORM object available earlier in the function. The `workspace_type` variable is already available in the function scope.

- [ ] **Step 7: Update GET /executions/{id} to include display_name and workspace_type**

In `backend/src/gateway/routers/executions.py`, add to the response dict in the `get_execution` handler (around line 98):

```python
return {
    "id": record.id,
    "status": record.status,
    "execution_type": record.execution_type,
    "feature_id": record.feature_id,
    "workspace_id": record.workspace_id,
    "workspace_type": record.workspace_type,
    "display_name": record.display_name,
    "thread_id": record.thread_id,
    "params": record.params,
    "result": record.result,
    "error": record.error,
    "progress": record.progress,
    "message": record.message,
    "artifact_ids": record.artifact_ids,
    "next_actions": record.next_actions,
    "graph_structure": record.graph_structure,
    "node_states": record.node_states,
    "created_at": record.created_at.isoformat() if record.created_at else None,
    "started_at": record.started_at.isoformat() if record.started_at else None,
    "completed_at": record.completed_at.isoformat() if record.completed_at else None,
}
```

Also update the list endpoint response (around line 193) to include `display_name`, `workspace_type`, and `result_summary` in each item:

```python
items.append({
    "id": r.id,
    "status": r.status,
    "execution_type": r.execution_type,
    "feature_id": r.feature_id,
    "workspace_id": r.workspace_id,
    "workspace_type": r.workspace_type,
    "display_name": r.display_name,
    "thread_id": r.thread_id,
    "progress": r.progress,
    "message": r.message,
    "result_summary": r.result_summary,
    "created_at": r.created_at.isoformat() if r.created_at else None,
    "started_at": r.started_at.isoformat() if r.started_at else None,
    "completed_at": r.completed_at.isoformat() if r.completed_at else None,
})
```

- [ ] **Step 8: Create Alembic migration**

Run: `cd backend && .venv/bin/alembic revision --autogenerate -m "add_execution_display_name"`

Then edit the generated migration to be:

```python
"""add execution display_name

Revision ID: 045
"""
from alembic import op
import sqlalchemy as sa

revision = "045"
down_revision = "044"  # adjust to actual previous revision
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("executions", sa.Column("display_name", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("executions", "display_name")
```

- [ ] **Step 9: Run migration**

Run: `cd backend && .venv/bin/alembic upgrade head`
Expected: No errors

- [ ] **Step 10: Commit**

```bash
cd /Users/ze/wenjin && git add backend/src/database/models/execution.py backend/src/services/execution_service.py backend/src/tools/builtins/launch_feature.py backend/src/gateway/routers/executions.py backend/alembic/versions/045_add_execution_display_name.py backend/tests/test_execution_display_name.py
git commit -m "feat: denormalize display_name onto ExecutionRecord for card headers"
```

---

### Task 2: Frontend — Update types and store

**Files:**
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/stores/execution-store.ts`
- Modify: `frontend/hooks/useExecutionStreamV2.ts`
- Test: `frontend/stores/__tests__/execution-store.test.ts`

- [ ] **Step 1: Update ExecutionGraphNode type**

In `frontend/lib/api/types.ts`, replace `ExecutionGraphNode` (around line 1407):

```typescript
export interface ExecutionGraphNode {
  id: string;
  type: string;
  label?: string;
  phase?: string;
  task?: string;
  subagent_type?: string;
  metadata?: Record<string, unknown>;
}
```

Add `display_name` to `ExecutionRecord` (around line 1369):

```typescript
export interface ExecutionRecord {
  id: string;
  user_id: string;
  workspace_id?: string | null;
  thread_id?: string | null;
  execution_type: ExecutionType;
  feature_id?: string | null;
  entry_skill_id?: string | null;
  workspace_type?: string | null;
  display_name?: string | null;
  status: ExecutionStatus;
  params: Record<string, unknown>;
  result?: Record<string, unknown> | null;
  error?: string | null;
  result_summary?: string | null;
  graph_structure?: ExecutionGraphStructure | null;
  node_states: Record<string, ExecutionNodeState>;
  runtime_state?: Record<string, unknown> | null;
  progress: number;
  message?: string | null;
  artifact_ids: string[];
  next_actions: Record<string, unknown>[];
  advisory_code?: string | null;
  last_error?: string | null;
  parent_execution_id?: string | null;
  child_execution_ids: string[];
  dispatch_mode?: string | null;
  worker_task_id?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  updated_at: string;
}
```

Add `input` and `output` fields to `ExecutionNodeState` (around line 1420):

```typescript
export interface ExecutionNodeState {
  status?: string;
  input?: Record<string, unknown> | null;
  output?: Record<string, unknown> | null;
  output_preview?: string | null;
  token_usage?: Record<string, number> | null;
  thinking?: string | null;
  tool_calls?: Record<string, unknown>[] | null;
  started_at?: string | null;
  completed_at?: string | null;
}
```

- [ ] **Step 2: Fix thinking delta handler in execution-store**

In `frontend/stores/execution-store.ts`, change the `execution.node.delta` thinking handler (around line 146). Replace:

```typescript
if (typeof event.payload.thinking === "string") {
  nodeState.thinking = event.payload.thinking;
}
```

With append mode:

```typescript
if (typeof event.payload.thinking === "string") {
  nodeState.thinking = (nodeState.thinking || "") + event.payload.thinking;
}
```

Also, add `input` and `output` handling to the same block (for Phase 1 node state persistence):

```typescript
if (event.payload.input_data) {
  nodeState.input = event.payload.input_data as Record<string, unknown>;
}
if (event.payload.output_data) {
  nodeState.output = event.payload.output_data as Record<string, unknown>;
}
```

- [ ] **Step 3: Update useExecutionStreamV2 to expose card-ready data**

Replace `frontend/hooks/useExecutionStreamV2.ts` entirely. The hook no longer builds ReactFlow nodes/edges. Instead it exposes the execution record and computed phase groups:

```typescript
"use client";

import { useMemo, useState } from "react";
import { useExecutionStore } from "@/stores/execution-store";
import useExecutionStream from "./useExecutionStream";
import type { ExecutionGraphNode } from "@/lib/api/types";

export interface PhaseGroup {
  name: string;
  index: number;
  nodes: ExecutionGraphNode[];
}

export interface UseExecutionStreamV2Return {
  record: ReturnType<typeof useExecutionStore>["records"][string] | null;
  phases: PhaseGroup[];
  executionId: string | null;
  selectedNodeId: string | null;
  selectNode: (id: string | null) => void;
}

export default function useExecutionStreamV2(
  _workspaceId: string,
  executionId?: string | null,
): UseExecutionStreamV2Return {
  const currentId =
    executionId ?? useExecutionStore((s) => s.currentExecutionId) ?? null;
  useExecutionStream(currentId);

  const record = useExecutionStore((s) =>
    currentId ? s.records[currentId] : null,
  );

  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const phases = useMemo<PhaseGroup[]>(() => {
    if (!record?.graph_structure?.nodes) return [];
    const phaseMap = new Map<string, { index: number; nodes: ExecutionGraphNode[] }>();
    let idx = 0;
    for (const node of record.graph_structure.nodes) {
      const phaseName = (node as Record<string, unknown>).phase as string || "default";
      if (!phaseMap.has(phaseName)) {
        phaseMap.set(phaseName, { index: idx++, nodes: [] });
      }
      phaseMap.get(phaseName)!.nodes.push(node);
    }
    return Array.from(phaseMap.entries()).map(([name, data]) => ({
      name,
      index: data.index,
      nodes: data.nodes,
    }));
  }, [record?.graph_structure?.nodes]);

  return {
    record,
    phases,
    executionId: currentId,
    selectedNodeId,
    selectNode: setSelectedNodeId,
  };
}
```

- [ ] **Step 4: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS (no type errors from the changes above)

- [ ] **Step 5: Commit**

```bash
cd /Users/ze/wenjin && git add frontend/lib/api/types.ts frontend/stores/execution-store.ts frontend/hooks/useExecutionStreamV2.ts
git commit -m "feat: update execution types, store thinking append, phase grouping"
```

---

### Task 3: Frontend — Build ExecutionCard and InProgressView

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/components/NodePill.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/NodeInlineDetail.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/PhaseRow.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/InProgressView.tsx`

- [ ] **Step 1: Create NodePill component**

```typescript
// frontend/app/(workbench)/workspaces/[id]/components/NodePill.tsx
"use client";

import type { ExecutionNodeState } from "@/lib/api/types";

interface NodePillProps {
  id: string;
  label: string;
  state: ExecutionNodeState | undefined;
  isSelected: boolean;
  onClick: () => void;
}

const STATUS_STYLES: Record<string, { bg: string; border: string; dot: string; text: string }> = {
  completed: {
    bg: "rgba(22,163,74,0.08)",
    border: "1px solid rgba(22,163,74,0.18)",
    dot: "#16A34A",
    text: "#16A34A",
  },
  running: {
    bg: "rgba(124,58,237,0.08)",
    border: "1.5px solid rgba(124,58,237,0.25)",
    dot: "#7C3AED",
    text: "#7C3AED",
  },
  failed: {
    bg: "rgba(220,38,38,0.08)",
    border: "1px solid rgba(220,38,38,0.18)",
    dot: "#DC2626",
    text: "#DC2626",
  },
  pending: {
    bg: "rgba(20,20,30,0.02)",
    border: "1px dashed rgba(20,20,30,0.1)",
    dot: "rgba(20,20,30,0.12)",
    text: "rgba(20,20,30,0.35)",
  },
};

export default function NodePill({ id, label, state, isSelected, onClick }: NodePillProps) {
  const status = state?.status || "pending";
  const style = STATUS_STYLES[status] || STATUS_STYLES.pending;
  const isRunning = status === "running";

  return (
    <button
      onClick={onClick}
      data-testid={`node-pill-${id}`}
      style={{
        padding: "4px 10px",
        borderRadius: 7,
        background: style.bg,
        border: isSelected ? `2px solid rgba(124,58,237,0.5)` : style.border,
        fontSize: 11,
        color: style.text,
        fontWeight: 500,
        cursor: "pointer",
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        fontFamily: "inherit",
        transition: "border-color 0.15s ease",
      }}
    >
      <span
        style={{
          width: 5,
          height: 5,
          borderRadius: "50%",
          background: style.dot,
          display: "inline-block",
          animation: isRunning ? "v2-pulse-soft 1.6s ease-in-out infinite" : "none",
        }}
      />
      {label}
    </button>
  );
}
```

- [ ] **Step 2: Create NodeInlineDetail component**

```typescript
// frontend/app/(workbench)/workspaces/[id]/components/NodeInlineDetail.tsx
"use client";

import { useState } from "react";
import type { ExecutionNodeState } from "@/lib/api/types";

interface NodeInlineDetailProps {
  state: ExecutionNodeState;
}

type TabKey = "input" | "output" | "thinking";

const TABS: { key: TabKey; label: string }[] = [
  { key: "input", label: "Input" },
  { key: "output", label: "Output" },
  { key: "thinking", label: "Thinking" },
];

export default function NodeInlineDetail({ state }: NodeInlineDetailProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("input");

  const content = (() => {
    switch (activeTab) {
      case "input":
        return state.input ? JSON.stringify(state.input, null, 2) : null;
      case "output":
        return state.output ? JSON.stringify(state.output, null, 2) : null;
      case "thinking":
        return state.thinking || null;
      default:
        return null;
    }
  })();

  const tokenUsage = state.token_usage;

  return (
    <div
      style={{
        marginTop: 6,
        borderRadius: 8,
        background: "rgba(255,255,255,0.45)",
        border: "1px solid rgba(20,20,30,0.06)",
        overflow: "hidden",
      }}
    >
      {/* Tabs */}
      <div style={{ display: "flex", borderBottom: "1px solid rgba(20,20,30,0.06)" }}>
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            style={{
              padding: "6px 14px",
              fontSize: 11,
              fontWeight: activeTab === tab.key ? 600 : 400,
              color: activeTab === tab.key ? "#7C3AED" : "rgba(20,20,30,0.45)",
              borderBottom: activeTab === tab.key ? "2px solid #7C3AED" : "2px solid transparent",
              background: "transparent",
              border: "none",
              borderBottomLeftRadius: 0,
              borderBottomRightRadius: 0,
              cursor: "pointer",
              fontFamily: "inherit",
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{ padding: "8px 12px", maxHeight: 200, overflow: "auto" }}>
        {content ? (
          <pre
            style={{
              fontSize: 11,
              color: "rgba(20,20,30,0.7)",
              fontFamily: "'JetBrains Mono', 'SF Mono', monospace",
              margin: 0,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {content}
          </pre>
        ) : (
          <p style={{ fontSize: 11, color: "rgba(20,20,30,0.3)", textAlign: "center", margin: 0 }}>
            No data available
          </p>
        )}
      </div>

      {/* Token usage */}
      {tokenUsage && (
        <div
          style={{
            padding: "4px 12px",
            borderTop: "1px solid rgba(20,20,30,0.04)",
            fontSize: 10,
            color: "rgba(20,20,30,0.4)",
            fontFamily: "'JetBrains Mono', 'SF Mono', monospace",
          }}
        >
          In: {(tokenUsage as Record<string, number>).input?.toLocaleString() ?? 0} · Out:{" "}
          {(tokenUsage as Record<string, number>).output?.toLocaleString() ?? 0}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create PhaseRow component**

```typescript
// frontend/app/(workbench)/workspaces/[id]/components/PhaseRow.tsx
"use client";

import { useState } from "react";
import type { ExecutionGraphNode, ExecutionNodeState } from "@/lib/api/types";
import NodePill from "./NodePill";
import NodeInlineDetail from "./NodeInlineDetail";

interface PhaseRowProps {
  phaseName: string;
  phaseIndex: number;
  nodes: ExecutionGraphNode[];
  nodeStates: Record<string, ExecutionNodeState>;
  isLast: boolean;
  loopInfo?: string | null;  // e.g. "↺ 循环 1/3"
}

function getPhaseStatus(
  nodes: ExecutionGraphNode[],
  nodeStates: Record<string, ExecutionNodeState>,
): "completed" | "running" | "pending" {
  const statuses = nodes.map((n) => nodeStates[n.id]?.status || "pending");
  if (statuses.every((s) => s === "completed")) return "completed";
  if (statuses.some((s) => s === "running" || s === "failed")) return "running";
  return "pending";
}

export default function PhaseRow({
  phaseName,
  phaseIndex,
  nodes,
  nodeStates,
  isLast,
  loopInfo,
}: PhaseRowProps) {
  const [expandedNodeId, setExpandedNodeId] = useState<string | null>(null);

  const phaseStatus = getPhaseStatus(nodes, nodeStates);
  const isCompleted = phaseStatus === "completed";
  const isRunning = phaseStatus === "running";

  // Dot colors
  const dotBg = isCompleted
    ? "linear-gradient(135deg, #4ADE80, #16A34A)"
    : isRunning
      ? "linear-gradient(135deg, #A78BFA, #7C3AED)"
      : "rgba(20,20,30,0.06)";
  const dotColor = isCompleted || isRunning ? "white" : "rgba(20,20,30,0.25)";

  return (
    <div style={{ display: "flex", gap: 10 }}>
      {/* Timeline rail */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          paddingTop: 2,
          minWidth: 22,
        }}
      >
        <div
          style={{
            width: 22,
            height: 22,
            borderRadius: 7,
            background: dotBg,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 10,
            color: dotColor,
            animation: isRunning ? "v2-pulse-soft 1.6s ease-in-out infinite" : "none",
            boxShadow: isRunning ? "0 1px 6px rgba(124,58,237,0.3)" : isCompleted ? "0 1px 4px rgba(22,163,74,0.3)" : "none",
          }}
        >
          {isCompleted ? "✓" : phaseIndex + 1}
        </div>
        {!isLast && (
          <div
            style={{
              width: 2,
              flex: 1,
              minHeight: 28,
              background: isCompleted
                ? "linear-gradient(to bottom, rgba(22,163,74,0.4), rgba(22,163,74,0.1))"
                : "rgba(20,20,30,0.06)",
              marginTop: 3,
            }}
          />
        )}
      </div>

      {/* Content */}
      <div style={{ flex: 1, paddingBottom: 4 }}>
        <div
          style={{
            fontSize: 10,
            color: isCompleted || isRunning ? "rgba(20,20,30,0.4)" : "rgba(20,20,30,0.25)",
            fontWeight: 600,
            letterSpacing: 0.3,
            textTransform: "uppercase",
            marginBottom: 5,
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          Phase {phaseIndex + 1} · {phaseName}
          {loopInfo && (
            <span
              style={{
                fontSize: 9,
                padding: "1px 5px",
                borderRadius: 3,
                background: "rgba(245,158,11,0.08)",
                color: "rgba(245,158,11,0.8)",
                fontWeight: 500,
                border: "1px solid rgba(245,158,11,0.15)",
                textTransform: "none",
              }}
            >
              {loopInfo}
            </span>
          )}
        </div>

        {/* Node pills */}
        <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
          {nodes.map((node) => (
            <div key={node.id}>
              <NodePill
                id={node.id}
                label={node.label || node.id}
                state={nodeStates[node.id]}
                isSelected={expandedNodeId === node.id}
                onClick={() =>
                  setExpandedNodeId(expandedNodeId === node.id ? null : node.id)
                }
              />
              {/* Inline detail */}
              {expandedNodeId === node.id && nodeStates[node.id] && (
                <NodeInlineDetail state={nodeStates[node.id]} />
              )}
            </div>
          ))}
        </div>

        {/* Thinking preview for running node */}
        {isRunning &&
          nodes
            .filter((n) => nodeStates[n.id]?.status === "running" && nodeStates[n.id]?.thinking)
            .map((n) => (
              <div
                key={`thinking-${n.id}`}
                style={{
                  marginTop: 8,
                  padding: "6px 10px",
                  background: "rgba(124,58,237,0.03)",
                  borderRadius: 6,
                  borderLeft: "2px solid rgba(124,58,237,0.2)",
                }}
              >
                <div
                  style={{
                    fontSize: 9,
                    color: "rgba(124,58,237,0.45)",
                    fontWeight: 600,
                    letterSpacing: 0.3,
                  }}
                >
                  THINKING
                </div>
                <div
                  style={{
                    fontSize: 11,
                    color: "rgba(20,20,30,0.55)",
                    fontFamily: "'JetBrains Mono', 'SF Mono', monospace",
                    marginTop: 2,
                    lineHeight: 1.4,
                    display: "-webkit-box",
                    WebkitLineClamp: 3,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                  }}
                >
                  {nodeStates[n.id]!.thinking}
                </div>
              </div>
            ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create InProgressView component**

```typescript
// frontend/app/(workbench)/workspaces/[id]/components/InProgressView.tsx
"use client";

import type { PhaseGroup } from "@/hooks/useExecutionStreamV2";
import type { ExecutionNodeState } from "@/lib/api/types";
import PhaseRow from "./PhaseRow";

interface InProgressViewProps {
  phases: PhaseGroup[];
  nodeStates: Record<string, ExecutionNodeState>;
}

function getNodeStatusCounts(
  phases: PhaseGroup[],
  nodeStates: Record<string, ExecutionNodeState>,
) {
  let completed = 0;
  let running = 0;
  let total = 0;
  for (const phase of phases) {
    for (const node of phase.nodes) {
      total++;
      const status = nodeStates[node.id]?.status;
      if (status === "completed") completed++;
      else if (status === "running" || status === "failed") running++;
    }
  }
  return { completed, running, total };
}

export default function InProgressView({ phases, nodeStates }: InProgressViewProps) {
  const { completed, running, total } = getNodeStatusCounts(phases, nodeStates);

  return (
    <div>
      {/* Progress bar */}
      <div style={{ display: "flex", gap: 3, marginBottom: 14 }}>
        {phases.flatMap((phase) =>
          phase.nodes.map((node) => {
            const status = nodeStates[node.id]?.status || "pending";
            const isRunning = status === "running" || status === "failed";
            const isCompleted = status === "completed";
            return (
              <div
                key={node.id}
                style={{
                  flex: 1,
                  height: 3,
                  borderRadius: 2,
                  background: isCompleted
                    ? "#16A34A"
                    : isRunning
                      ? "#7C3AED"
                      : "rgba(20,20,30,0.08)",
                  animation: isRunning ? "v2-pulse-soft 1.6s ease-in-out infinite" : "none",
                }}
              />
            );
          }),
        )}
      </div>

      {/* Status line */}
      <div
        style={{
          fontSize: 11,
          color: "rgba(20,20,30,0.4)",
          marginBottom: 12,
        }}
      >
        {completed}/{total} nodes{running > 0 ? " · processing…" : completed === total ? " · done" : ""}
      </div>

      {/* Phase timeline */}
      {phases.map((phase, i) => (
        <PhaseRow
          key={phase.name}
          phaseName={phase.name}
          phaseIndex={phase.index}
          nodes={phase.nodes}
          nodeStates={nodeStates}
          isLast={i === phases.length - 1}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 5: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/ze/wenjin && git add frontend/app/\(workbench\)/workspaces/\[id\]/components/NodePill.tsx frontend/app/\(workbench\)/workspaces/\[id\]/components/NodeInlineDetail.tsx frontend/app/\(workbench\)/workspaces/\[id\]/components/PhaseRow.tsx frontend/app/\(workbench\)/workspaces/\[id\]/components/InProgressView.tsx
git commit -m "feat: add InProgressView with phase timeline, node pills, inline detail"
```

---

### Task 4: Frontend — Build CompletedView and ExecutionCard

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/components/CompletedView.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/ExecutionCard.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/ExecutionCardList.tsx`

- [ ] **Step 1: Create CompletedView component**

```typescript
// frontend/app/(workbench)/workspaces/[id]/components/CompletedView.tsx
"use client";

import { useState } from "react";

interface CompletedViewProps {
  resultSummary?: string | null;
  result?: Record<string, unknown> | null;
  outputs?: unknown[];
}

export default function CompletedView({ resultSummary, result, outputs }: CompletedViewProps) {
  const [showFull, setShowFull] = useState(false);

  const summary = resultSummary || "Execution completed.";
  const fullResult = result ? JSON.stringify(result, null, 2) : null;

  return (
    <div>
      {/* Summary */}
      <div
        style={{
          fontSize: 13,
          color: "#14141E",
          lineHeight: 1.6,
          marginBottom: 8,
        }}
      >
        {summary}
      </div>

      {/* Tags from outputs */}
      {outputs && outputs.length > 0 && (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
          {outputs.slice(0, 5).map((output, i) => {
            const o = output as Record<string, unknown>;
            const label = o.title || o.name || o.id || `Output ${i + 1}`;
            return (
              <span
                key={i}
                style={{
                  fontSize: 11,
                  padding: "2px 8px",
                  borderRadius: 4,
                  background: "rgba(124,58,237,0.08)",
                  color: "#7C3AED",
                }}
              >
                {String(label)}
              </span>
            );
          })}
        </div>
      )}

      {/* Full result toggle */}
      {fullResult && (
        <div>
          <button
            onClick={() => setShowFull(!showFull)}
            style={{
              fontSize: 11,
              color: "#7C3AED",
              background: "none",
              border: "none",
              cursor: "pointer",
              fontFamily: "inherit",
              padding: 0,
            }}
          >
            {showFull ? "▾ Hide full result" : "▸ View full result"}
          </button>
          {showFull && (
            <pre
              style={{
                marginTop: 8,
                padding: 12,
                borderRadius: 8,
                background: "rgba(255,255,255,0.4)",
                border: "1px solid rgba(20,20,30,0.06)",
                fontSize: 11,
                color: "rgba(20,20,30,0.7)",
                fontFamily: "'JetBrains Mono', 'SF Mono', monospace",
                maxHeight: 300,
                overflow: "auto",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {fullResult}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create ExecutionCard component**

```typescript
// frontend/app/(workbench)/workspaces/[id]/components/ExecutionCard.tsx
"use client";

import { useState } from "react";
import type { ExecutionRecord, ExecutionNodeState } from "@/lib/api/types";
import type { PhaseGroup } from "@/hooks/useExecutionStreamV2";
import InProgressView from "./InProgressView";
import CompletedView from "./CompletedView";

interface ExecutionCardProps {
  record: ExecutionRecord;
  phases: PhaseGroup[];
  isExpanded: boolean;
  onToggle: () => void;
  selectedNodeId: string | null;
  selectNode: (id: string | null) => void;
}

function getDuration(record: ExecutionRecord): string {
  if (!record.started_at) return "";
  const start = new Date(record.started_at).getTime();
  const end = record.completed_at
    ? new Date(record.completed_at).getTime()
    : Date.now();
  const seconds = Math.round((end - start) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

export default function ExecutionCard({
  record,
  phases,
  isExpanded,
  onToggle,
}: ExecutionCardProps) {
  const nodeCount =
    record.graph_structure?.nodes?.length ?? 0;
  const isActive =
    record.status === "running" || record.status === "pending";
  const isCompleted = record.status === "completed";
  const isFailed =
    record.status === "failed" ||
    record.status === "failed_partial" ||
    record.status === "cancelled";

  const nodeStates = record.node_states || {};

  // Icon
  const iconBg = isCompleted
    ? "linear-gradient(135deg, #4ADE80, #16A34A)"
    : isFailed
      ? "linear-gradient(135deg, #F87171, #DC2626)"
      : "linear-gradient(135deg, #A78BFA, #7C3AED)";
  const iconSymbol = isCompleted ? "✓" : isFailed ? "✕" : "⟳";
  const iconPulse = isActive ? "v2-pulse-soft 1.6s ease-in-out infinite" : "none";

  // Status badge
  const statusLabel = isCompleted
    ? "已完成"
    : isFailed
      ? "失败"
      : "进行中";
  const statusColor = isCompleted
    ? "#16A34A"
    : isFailed
      ? "#DC2626"
      : "#7C3AED";
  const statusBg = isCompleted
    ? "rgba(22,163,74,0.1)"
    : isFailed
      ? "rgba(220,38,38,0.1)"
      : "rgba(124,58,237,0.1)";

  return (
    <div
      style={{
        background: "rgba(255,255,255,0.7)",
        backdropFilter: "blur(20px)",
        borderRadius: 16,
        border: `1px solid ${isActive ? "rgba(167,139,250,0.3)" : "rgba(255,255,255,0.6)"}`,
        padding: "16px 20px",
        cursor: "pointer",
        boxShadow: isActive
          ? "0 2px 12px rgba(124,58,237,0.08)"
          : "0 2px 8px rgba(20,20,30,0.04)",
        transition: "box-shadow 0.2s ease, border-color 0.2s ease",
      }}
      onClick={onToggle}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 10,
              background: iconBg,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "white",
              fontSize: 14,
              fontWeight: 600,
              animation: iconPulse,
            }}
          >
            {iconSymbol}
          </div>
          <div>
            <div style={{ fontWeight: 600, fontSize: 14, color: "#14141E" }}>
              {record.display_name || record.feature_id || "Execution"}
            </div>
            <div style={{ fontSize: 12, color: "rgba(20,20,30,0.5)", marginTop: 2 }}>
              {record.workspace_type || ""}{record.workspace_type ? " · " : ""}{nodeCount} nodes{record.started_at ? ` · ${getDuration(record)}` : ""}
            </div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            style={{
              fontSize: 11,
              padding: "3px 8px",
              borderRadius: 6,
              background: statusBg,
              color: statusColor,
              fontWeight: 500,
            }}
          >
            {statusLabel}
          </span>
          <span
            style={{
              color: "rgba(20,20,30,0.3)",
              fontSize: 18,
              transition: "transform 0.2s ease",
              transform: isExpanded ? "rotate(90deg)" : "none",
              display: "inline-block",
            }}
          >
            ›
          </span>
        </div>
      </div>

      {/* Expanded body */}
      {isExpanded && (
        <div
          style={{ marginTop: 14, borderTop: "1px solid rgba(20,20,30,0.06)", paddingTop: 14 }}
          onClick={(e) => e.stopPropagation()}
        >
          {isActive ? (
            <InProgressView phases={phases} nodeStates={nodeStates} />
          ) : isCompleted ? (
            <CompletedView
              resultSummary={record.result_summary}
              result={record.result}
              outputs={
                (record.result as Record<string, unknown>)?.outputs as unknown[]
              }
            />
          ) : isFailed ? (
            <InProgressView phases={phases} nodeStates={nodeStates} />
          ) : null}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create ExecutionCardList component**

```typescript
// frontend/app/(workbench)/workspaces/[id]/components/ExecutionCardList.tsx
"use client";

import { useState, useEffect, useCallback } from "react";
import type { ExecutionRecord } from "@/lib/api/types";
import { useExecutionStore } from "@/stores/execution-store";
import useExecutionStreamV2, { type PhaseGroup } from "@/hooks/useExecutionStreamV2";
import ExecutionCard from "./ExecutionCard";

interface ExecutionCardListProps {
  workspaceId: string;
}

interface CardEntry {
  id: string;
  record: ExecutionRecord;
  phases: PhaseGroup[];
}

export default function ExecutionCardList({ workspaceId }: ExecutionCardListProps) {
  const { record, phases, executionId } = useExecutionStreamV2(workspaceId);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [history, setHistory] = useState<CardEntry[]>([]);

  // When a new active execution arrives, auto-expand and add to history when done
  useEffect(() => {
    if (!record) return;
    const id = record.id;

    // Auto-expand new execution
    if (record.status === "running" || record.status === "pending") {
      setExpandedId(id);
    }

    // When completed, freeze into history
    if (
      record.status === "completed" ||
      record.status === "failed" ||
      record.status === "cancelled" ||
      record.status === "failed_partial"
    ) {
      setHistory((prev) => {
        if (prev.some((e) => e.id === id)) return prev;
        return [{ id, record, phases }, ...prev];
      });
    }
  }, [record?.id, record?.status]);

  // Build combined list: active execution (if running) + history
  const cards: CardEntry[] = [];
  if (record && (record.status === "running" || record.status === "pending")) {
    cards.push({ id: record.id, record, phases });
  }
  // Add history that's not the active one
  for (const entry of history) {
    if (!cards.some((c) => c.id === entry.id)) {
      cards.push(entry);
    }
  }

  const handleToggle = useCallback(
    (id: string) => {
      setExpandedId(expandedId === id ? null : id);
    },
    [expandedId],
  );

  if (cards.length === 0) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {cards.map((entry) => (
        <ExecutionCard
          key={entry.id}
          record={entry.record}
          phases={entry.phases}
          isExpanded={expandedId === entry.id}
          onToggle={() => handleToggle(entry.id)}
          selectedNodeId={null}
          selectNode={() => {}}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/ze/wenjin && git add frontend/app/\(workbench\)/workspaces/\[id\]/components/CompletedView.tsx frontend/app/\(workbench\)/workspaces/\[id\]/components/ExecutionCard.tsx frontend/app/\(workbench\)/workspaces/\[id\]/components/ExecutionCardList.tsx
git commit -m "feat: add ExecutionCard, CompletedView, and ExecutionCardList"
```

---

### Task 5: Frontend — Replace LiveWorkflowPanel, delete old components

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`
- Delete: `frontend/app/(workbench)/workspaces/[id]/components/GraphCanvas.tsx`
- Delete: `frontend/app/(workbench)/workspaces/[id]/components/PhaseNode.tsx`
- Delete: `frontend/app/(workbench)/workspaces/[id]/components/NodeDetailDrawer.tsx`

- [ ] **Step 1: Rewrite LiveWorkflowPanel to use card list**

Replace the entire content of `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`:

```typescript
"use client";

import type { WorkspaceTypeConfig, WorkspaceFeature } from "@/lib/api/types";
import ExecutionCardList from "./ExecutionCardList";

interface LiveWorkflowPanelProps {
  workspaceId: string;
  typeConfig?: WorkspaceTypeConfig;
  features?: WorkspaceFeature[];
  className?: string;
  "data-testid"?: string;
}

export default function LiveWorkflowPanel({
  workspaceId,
  typeConfig,
  features = [],
  className,
  "data-testid": testId,
}: LiveWorkflowPanelProps) {
  return (
    <div
      className={className}
      data-testid={testId}
      style={{
        position: "relative",
        height: "100%",
        background:
          "linear-gradient(135deg, #E0EFFF 0%, #F0F4FF 50%, #E8E0FF 100%)",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Decorative light orbs */}
      <div
        style={{
          position: "absolute",
          top: -80,
          left: -80,
          width: 300,
          height: 300,
          borderRadius: "50%",
          background: "rgba(139,92,246,0.4)",
          filter: "blur(50px)",
          pointerEvents: "none",
        }}
      />
      <div
        style={{
          position: "absolute",
          bottom: -60,
          right: -60,
          width: 250,
          height: 250,
          borderRadius: "50%",
          background: "rgba(56,189,248,0.35)",
          filter: "blur(45px)",
          pointerEvents: "none",
        }}
      />

      {/* Content area */}
      <div
        style={{
          position: "relative",
          flex: 1,
          overflow: "auto",
          padding: "20px 24px",
        }}
      >
        {/* Card list (shows when executions exist) */}
        <ExecutionCardList workspaceId={workspaceId} />

        {/* ProductIntro always visible at bottom when no active execution */}
        {/* For now, feature cards remain as idle state */}
        <ProductIntro typeConfig={typeConfig} features={features} />
      </div>
    </div>
  );
}

/* ---------- ProductIntro (kept from original, simplified) ---------- */

interface ProductIntroProps {
  typeConfig?: WorkspaceTypeConfig;
  features: WorkspaceFeature[];
}

function iconToEmoji(icon: string): string {
  const map: Record<string, string> = {
    search: "🔍",
    book: "📚",
    brain: "🧠",
    lightbulb: "💡",
    pen: "✍️",
    chart: "📊",
    document: "📄",
    check: "✅",
    code: "💻",
    globe: "🌐",
  };
  return map[icon] || icon || "✨";
}

function ProductIntro({ typeConfig, features }: ProductIntroProps) {
  return (
    <div style={{ marginTop: 16 }}>
      {typeConfig && (
        <div style={{ marginBottom: 16 }}>
          <h2
            style={{
              fontSize: 20,
              fontWeight: 600,
              color: "#14141E",
              marginBottom: 4,
            }}
          >
            {typeConfig.title}
          </h2>
          {typeConfig.subtitle && (
            <p style={{ fontSize: 13, color: "rgba(20,20,30,0.5)", margin: 0 }}>
              {typeConfig.subtitle}
            </p>
          )}
        </div>
      )}
      {features.length > 0 && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(2, 1fr)",
            gap: 10,
          }}
        >
          {features.slice(0, 6).map((f) => (
            <div
              key={f.id}
              style={{
                padding: "14px 16px",
                borderRadius: 12,
                background: "rgba(255,255,255,0.7)",
                backdropFilter: "blur(20px)",
                border: "1px solid rgba(255,255,255,0.6)",
                boxShadow: "0 2px 8px rgba(20,20,30,0.04)",
              }}
            >
              <div style={{ fontSize: 20, marginBottom: 6 }}>
                {iconToEmoji(f.icon || "")}
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#14141E" }}>
                {f.name}
              </div>
              {f.description && (
                <div
                  style={{
                    fontSize: 12,
                    color: "rgba(20,20,30,0.45)",
                    marginTop: 2,
                    lineHeight: 1.4,
                  }}
                >
                  {f.description}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Delete old components**

```bash
rm frontend/app/\(workbench\)/workspaces/\[id\]/components/GraphCanvas.tsx
rm frontend/app/\(workbench\)/workspaces/\[id\]/components/PhaseNode.tsx
rm frontend/app/\(workbench\)/workspaces/\[id\]/components/NodeDetailDrawer.tsx
```

- [ ] **Step 3: Remove @xyflow/react dependency**

```bash
cd frontend && npm uninstall @xyflow/react
```

- [ ] **Step 4: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS — no references to deleted files or @xyflow/react remain

- [ ] **Step 5: Run build**

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/ze/wenjin && git add -A frontend/app/\(workbench\)/workspaces/\[id\]/components/ frontend/package.json frontend/package-lock.json
git commit -m "feat: replace ReactFlow with card feed, remove @xyflow/react"
```

---

## Phase 3: Streaming Thinking

### Task 6: Backend — Add emit_delta to SubagentContext

**Files:**
- Modify: `backend/src/subagents/v2/base.py`
- Test: `backend/tests/subagents/v2/test_emit_delta.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/subagents/v2/test_emit_delta.py
"""Test emit_delta callback on SubagentContext."""
import asyncio
from unittest.mock import AsyncMock

from src.subagents.v2.base import SubagentContext


def test_subagent_context_has_emit_delta():
    """SubagentContext accepts an optional emit_delta callback."""
    ctx = SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="test",
        inputs={},
        tools=[],
    )
    assert ctx.emit_delta is None


@pytest.mark.asyncio
async def test_subagent_context_emit_delta_callable():
    """emit_delta can be called to emit events."""
    calls = []
    async def recorder(event_type: str, content: str) -> None:
        calls.append((event_type, content))

    ctx = SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="test",
        inputs={},
        tools=[],
        emit_delta=recorder,
    )
    await ctx.emit_delta("thinking", "hello ")
    await ctx.emit_delta("thinking", "world")
    assert calls == [("thinking", "hello "), ("thinking", "world")]


import pytest
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/subagents/v2/test_emit_delta.py -v`
Expected: FAIL — `SubagentContext.__init__() got an unexpected keyword argument 'emit_delta'`

- [ ] **Step 3: Add emit_delta to SubagentContext**

In `backend/src/subagents/v2/base.py`, add to the `SubagentContext` dataclass (after `skill` field):

```python
from collections.abc import Awaitable, Callable

@dataclass
class SubagentContext:
    workspace_id: str
    execution_id: str
    prompt: str
    inputs: dict
    tools: list[str]
    workspace_data: dict = field(default_factory=dict)
    skill: CapabilitySkill | None = None
    emit_delta: Callable[[str, str], Awaitable[None]] | None = None
```

Also add an `emit` helper method:

```python
    async def emit(self, event_type: str, content: str) -> None:
        """Emit a delta event if emit_delta is configured."""
        if self.emit_delta is not None:
            await self.emit_delta(event_type, content)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/subagents/v2/test_emit_delta.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/ze/wenjin && git add backend/src/subagents/v2/base.py backend/tests/subagents/v2/test_emit_delta.py
git commit -m "feat: add emit_delta callback to SubagentContext"
```

---

### Task 7: Backend — Switch react subagent to streaming

**Files:**
- Modify: `backend/src/subagents/v2/types/react.py`
- Test: `backend/tests/subagents/v2/test_react_streaming.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/subagents/v2/test_react_streaming.py
"""Test that react subagent emits thinking deltas when streaming."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.subagents.v2.base import SubagentContext
from src.subagents.v2.types.react import ReactSubagent


@pytest.mark.asyncio
async def test_react_emits_thinking_deltas():
    """React subagent calls ctx.emit_delta for thinking chunks."""
    deltas = []
    async def recorder(event_type: str, content: str) -> None:
        deltas.append((event_type, content))

    ctx = SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="test",
        inputs={"topic": "test"},
        tools=[],
        skill=MagicMock(
            prompt="You are a test agent.",
            config={"user_template": "Write about {topic}"},
        ),
        emit_delta=recorder,
    )

    # Mock the model to produce a streamed response with thinking
    mock_chunk_1 = MagicMock()
    mock_chunk_1.content = "Thinking step 1"
    mock_chunk_1.additional_kwargs = {"type": "thinking"}

    mock_chunk_2 = MagicMock()
    mock_chunk_2.content = "Thinking step 2"
    mock_chunk_2.additional_kwargs = {"type": "thinking"}

    mock_final = MagicMock()
    mock_final.content = "Final answer"

    with patch("src.subagents.v2.types.react.create_chat_model") as mock_factory:
        mock_model = AsyncMock()
        mock_model.astream.return_value = async_iterator([mock_chunk_1, mock_chunk_2, mock_final])
        mock_factory.return_value = mock_model

        agent = ReactSubagent()
        result = await agent.run(ctx)

    # Should have emitted thinking deltas
    assert len(deltas) >= 1
    thinking_events = [d for d in deltas if d[0] == "thinking"]
    assert len(thinking_events) >= 1
    assert result.output is not None


async def async_iterator(items):
    for item in items:
        yield item
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/subagents/v2/test_react_streaming.py -v`
Expected: FAIL — react subagent doesn't use streaming or emit_delta yet

- [ ] **Step 3: Modify _run_react_loop to accept and use emit_delta**

In `backend/src/subagents/v2/types/react.py`, modify `_run_react_loop` to accept an optional `emit_delta` callback and use `astream()`:

```python
async def _run_react_loop(
    system_prompt: str,
    user_message: str,
    tools: list[str] | None = None,
    emit_delta: Callable[[str, str], Awaitable[None]] | None = None,
) -> str:
    from collections.abc import Awaitable, Callable

    model = create_chat_model("mimo-v2.5-pro", thinking_enabled=True)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    if tools:
        from langgraph.prebuilt import create_react_agent
        resolved_tools = _resolve_tools(tools)
        if resolved_tools:
            agent = create_react_agent(
                model=model,
                tools=resolved_tools,
                state_modifier=system_prompt,
            )
            result = await agent.ainvoke({"messages": [HumanMessage(content=user_message)]})
            msgs = result.get("messages", [])
            for msg in reversed(msgs):
                if hasattr(msg, "content") and msg.content:
                    return msg.content
            return ""

    # No tools — stream the response
    final_text = ""
    thinking_buffer = ""
    last_flush = 0.0
    import time
    async for chunk in model.astream(messages):
        content = chunk.content if hasattr(chunk, "content") else str(chunk)
        if not content:
            continue

        # Check if this is a thinking chunk
        is_thinking = False
        if hasattr(chunk, "additional_kwargs"):
            is_thinking = chunk.additional_kwargs.get("type") == "thinking"

        if is_thinking and emit_delta:
            thinking_buffer += content
            now = time.monotonic()
            if now - last_flush >= 0.5:
                await emit_delta("thinking", thinking_buffer)
                last_flush = now
        else:
            final_text += content

    # Flush remaining thinking
    if thinking_buffer and emit_delta:
        await emit_delta("thinking", thinking_buffer)

    return final_text
```

Update the `run()` method to pass `ctx.emit_delta`:

```python
    async def run(self, ctx: SubagentContext) -> SubagentResult:
        # ... existing skill resolution ...
        final_text = await _run_react_loop(
            system_prompt, user_message, ctx.tools, emit_delta=ctx.emit_delta
        )
        # ... rest of method ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/subagents/v2/test_react_streaming.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/ze/wenjin && git add backend/src/subagents/v2/types/react.py backend/tests/subagents/v2/test_react_streaming.py
git commit -m "feat: switch react subagent to streaming with thinking delta emission"
```

---

### Task 8: Backend — Wire emit_delta through runtime

**Files:**
- Modify: `backend/src/agents/lead_agent/v2/compiler.py`
- Modify: `backend/src/agents/lead_agent/v2/runtime.py`
- Test: `backend/tests/agents/lead_agent/v2/test_runtime.py` (update existing)

- [ ] **Step 1: Update _default_runner_factory to accept and pass emit_delta**

In `backend/src/agents/lead_agent/v2/compiler.py`, update `_default_runner_factory` signature and SubagentContext creation:

```python
def _default_runner_factory(
    subagent_cls: type[SubagentBase],
    task_spec: dict,
    emit_delta: Callable[[str, str], Awaitable[None]] | None = None,
) -> Callable:
```

And in the SubagentContext creation (around line 147):

```python
    ctx = SubagentContext(
        workspace_id=state.get("workspace_id", ""),
        execution_id=state.get("execution_id", ""),
        prompt=task_spec.get("prompt_template", ""),
        inputs=rendered_inputs,
        tools=task_spec.get("tools", []),
        workspace_data=state.get("workspace_data", {}),
        skill=task_spec.get("_skill"),
        emit_delta=emit_delta,
    )
```

- [ ] **Step 2: Update runtime's persisting runner factory to create emit_delta**

In `backend/src/agents/lead_agent/v2/runtime.py`, inside `_build_persisting_runner_factory`, after the `_emit` helper, create an `emit_delta` closure:

```python
        # Throttled thinking delta emitter
        _thinking_buffers: dict[str, str] = {}
        _last_flush: dict[str, float] = {}

        async def _emit_delta(node_id: str, content: str) -> None:
            """Accumulate thinking content and flush every 500ms."""
            import time
            buf = _thinking_buffers.get(node_id, "") + content
            _thinking_buffers[node_id] = buf
            now = time.monotonic()
            last = _last_flush.get(node_id, 0.0)
            if now - last >= 0.5:
                await publish(
                    execution_id,
                    "execution.node.delta",
                    {"node_id": node_id, "thinking": buf},
                )
                _last_flush[node_id] = now
                _thinking_buffers[node_id] = ""
```

Then in the `factory` function, create a node-scoped emit_delta:

```python
        def factory(subagent_cls: Any, task_spec: dict) -> Callable:
            inner = _default_runner_factory(subagent_cls, task_spec)
            task_name = task_spec["name"]
            # ... existing meta ...

            # Create emit_delta scoped to this node
            async def _node_emit_delta(event_type: str, content: str) -> None:
                if event_type == "thinking":
                    await _emit_delta(meta["node_id"], content)

            inner_with_delta = _default_runner_factory(subagent_cls, task_spec, emit_delta=_node_emit_delta)

            async def persisting_run(state: dict) -> dict:
                # ... use inner_with_delta instead of inner for the actual run ...
```

- [ ] **Step 3: Update existing runtime tests**

In `backend/tests/agents/lead_agent/v2/test_runtime.py`, update the test to verify that delta events are emitted. The existing tests should still pass since `emit_delta` is optional (None by default).

Run: `cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_runtime.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/ze/wenjin && git add backend/src/agents/lead_agent/v2/compiler.py backend/src/agents/lead_agent/v2/runtime.py backend/tests/agents/lead_agent/v2/test_runtime.py
git commit -m "feat: wire emit_delta through runtime with 500ms throttled thinking flush"
```

---

### Task 9: Integration test and docker verification

**Files:** No new files — integration verification

- [ ] **Step 1: Run full backend test suite**

Run: `cd backend && .venv/bin/python -m pytest tests/ -v --timeout=60`
Expected: All tests PASS

- [ ] **Step 2: Run frontend typecheck + build**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: PASS

- [ ] **Step 3: Rebuild docker and smoke test**

Run: `docker compose up -d --build`
Then trigger a "文献检索" from the chat interface and verify:
- Right panel shows a card with the execution name
- Card expands to show phase timeline with node pills
- Node pills show status colors (running/completed)
- Clicking a node pill expands inline detail
- Completed card shows result summary

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: integration fixes for execution panel v2"
```
