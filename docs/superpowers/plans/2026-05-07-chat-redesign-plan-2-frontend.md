# Chat Redesign · Plan 2: Frontend State + Components

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **For UI tasks (T4 onwards), invoke `superpowers:frontend-design` skill before writing JSX/Tailwind.**

**Goal:** Build the new frontend pieces of the chat redesign — TypeScript mirrors of Plan 1's `AgentBlock` types, a `useWorkflowStore` (zustand) bound to live SSE events, and the new `LiveWorkflowPanel` (right) and `ChatThread` (left) components with all 4 block renderers.

**Architecture:** State lives in `useWorkflowStore` and is updated by `subscribeWorkspaceEvents` (existing) for `subagent.updated` events plus a new `block` event handler in the thread stream consumer. Right panel is a single `LiveWorkflowPanel` with phases, parallel subagent grid, and a folded `WorkspaceAssets` housing the existing artifact/literature/knowledge components (re-homed in Plan 3). Left panel is `ChatThread` with `RunContainer` grouping, `EmptyState`, and 4 block renderers.

**Tech Stack:** Next.js 16, React 19, TypeScript, Tailwind, zustand, Vitest + Testing Library, i18n via existing `useI18n()`.

**Reference spec:** [docs/superpowers/specs/2026-05-07-chat-experience-redesign-design.md](../specs/2026-05-07-chat-experience-redesign-design.md). Section numbers below refer to that spec.

**Depends on:** Plan 1 must be merged first (TypeScript types mirror Plan 1's Pydantic schema).

**Out of scope for this plan:** URL entry seed flow + WorkspaceAssets actual relocation + Playwright e2e + legacy deletion (Plan 3).

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `frontend/lib/api/blocks.ts` | **create** | TypeScript mirrors of `AgentBlock` (text/status_line/question_card/result_card) |
| `frontend/lib/api/types.ts` | modify | Add `BlockEvent` to thread-stream event union; add new event type |
| `frontend/lib/api/streams.ts` | modify | Handle `type: "block"` in thread stream subscriber |
| `frontend/lib/api/runs.ts` | **create** | Wrappers for `pause/resume/cancel/delete` endpoints |
| `frontend/stores/workflow-store.ts` | **create** | `useWorkflowStore` zustand |
| `frontend/stores/workflow-store-support.ts` | **create** | reducer helpers for `subagent.updated` ingest |
| `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/LiveWorkflowPanel.tsx` | **create** | Top-level right panel |
| `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/RunList.tsx` | **create** | Run list w/ folded completed runs |
| `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/PhaseList.tsx` | **create** | Phase grouping inside a run |
| `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/SubagentGrid.tsx` | **create** | 2-col grid w/ done-folded/running-expanded |
| `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/SubagentCard.tsx` | **create** | Single card |
| `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/WorkspaceAssets.tsx` | **create** | Folded shell (Plan 3 wires real children) |
| `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/ChatThread.tsx` | **create** | Top-level left panel |
| `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/EmptyState.tsx` | **create** | First-time placeholder |
| `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/MessageList.tsx` | **create** | Message + RunContainer ordering |
| `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/RunContainer.tsx` | **create** | Folded completed-run wrapper |
| `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/TextBlock.tsx` | **create** | Renderer |
| `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/StatusLineBlock.tsx` | **create** | Renderer |
| `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/QuestionCardBlock.tsx` | **create** | Renderer + pill click handler |
| `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/ResultCardBlock.tsx` | **create** | Renderer + feedback pill handler |
| `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/InputArea.tsx` | **create** | wraps existing composer + interrupt button |
| `frontend/locales/cn.json` | modify | Add `blocks.*` keys |
| `frontend/locales/en.json` | modify | Add `blocks.*` keys |
| `frontend/tests/unit/stores/workflow-store.test.ts` | **create** | Reducer tests |
| `frontend/tests/unit/components/live-workflow/*.test.tsx` | **create** | Component tests (5 files) |
| `frontend/tests/unit/components/chat-thread/*.test.tsx` | **create** | Component tests (6 files) |

---

## Task 1: TypeScript `AgentBlock` types

**Files:**
- Create: `frontend/lib/api/blocks.ts`
- Modify: `frontend/lib/api/types.ts` (add new event type)
- Test: `frontend/tests/unit/lib/blocks.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/tests/unit/lib/blocks.test.ts
import { describe, expect, it } from "vitest";
import {
  AgentBlock, AgentMessage, isQuestionCard, isResultCard,
  isStatusLine, isText,
} from "@/lib/api/blocks";

describe("AgentBlock type guards", () => {
  it("narrows by kind", () => {
    const b: AgentBlock = { kind: "text", content: "hi" };
    expect(isText(b)).toBe(true);
    expect(isStatusLine(b)).toBe(false);
  });

  it("AgentMessage type accepts mixed blocks", () => {
    const m: AgentMessage = {
      blocks: [
        { kind: "text", content: "hi" },
        { kind: "status_line", label: "phase 1 done", run_id: "r1", tone: "info" },
      ],
    };
    expect(m.blocks).toHaveLength(2);
  });

  it("question_card pills are typed", () => {
    const q: AgentBlock = {
      kind: "question_card",
      label: "需要你拍一下",
      question: "?",
      pills: [{ label: "A", intent: "go" }],
    };
    expect(isQuestionCard(q)).toBe(true);
    if (isQuestionCard(q)) {
      expect(q.pills[0].label).toBe("A");
    }
  });

  it("result_card requires feedback + stats", () => {
    const r: AgentBlock = {
      kind: "result_card",
      run_id: "r1",
      title: "done",
      tldr: "x",
      findings: [{ id: "1", text: "a" }],
      links: [],
      feedback: { question: "?", pills: [], allow_free_input: true },
      stats: { duration_ms: 1000, subagents: 3, tokens: 100 },
    };
    expect(isResultCard(r)).toBe(true);
  });
});
```

- [ ] **Step 2: Run test, expect FAIL**

```bash
cd frontend && npx vitest run tests/unit/lib/blocks.test.ts
```
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```ts
// frontend/lib/api/blocks.ts
// Mirror of backend/src/agents/lead_agent/blocks.py — keep field names in sync.

export interface TextBlock {
  kind: "text";
  content: string;
}

export type StatusTone = "info" | "warn" | "error";

export interface StatusLineBlock {
  kind: "status_line";
  label: string;
  run_id: string;
  phase_index?: number | null;
  tone: StatusTone;
}

export interface Pill {
  label: string;
  intent: string;
}

export interface QuestionCardBlock {
  kind: "question_card";
  label: string;
  question: string;
  pills: Pill[];                            // 0-3
  context_ref_subagent_task_id?: string | null;
  context_ref_phase_index?: number | null;
}

export interface Finding { id: string; text: string; }
export interface Recommend { label: string; body: string; }
export interface Link { icon: string; label: string; href: string; }

export type FeedbackPillKind = "primary" | "normal" | "warn";
export interface FeedbackPill { kind: FeedbackPillKind; label: string; intent: string; }

export interface FeedbackBlock {
  question: string;
  pills: FeedbackPill[];
  allow_free_input: boolean;
}

export interface RunStats {
  duration_ms: number;
  subagents: number;
  tokens: number;
}

export interface ResultCardBlock {
  kind: "result_card";
  run_id: string;
  title: string;
  tldr: string;
  findings: Finding[];
  recommend?: Recommend | null;
  links: Link[];
  feedback: FeedbackBlock;
  stats: RunStats;
}

export type AgentBlock =
  | TextBlock
  | StatusLineBlock
  | QuestionCardBlock
  | ResultCardBlock;

export interface AgentMessage { blocks: AgentBlock[]; }

export const isText = (b: AgentBlock): b is TextBlock => b.kind === "text";
export const isStatusLine = (b: AgentBlock): b is StatusLineBlock => b.kind === "status_line";
export const isQuestionCard = (b: AgentBlock): b is QuestionCardBlock => b.kind === "question_card";
export const isResultCard = (b: AgentBlock): b is ResultCardBlock => b.kind === "result_card";
```

In `frontend/lib/api/types.ts`, add the SSE event type:

```ts
// near the existing thread-stream events
import type { AgentBlock } from "./blocks";

export interface ThreadBlockEvent {
  type: "block";
  message_id: string;
  block: AgentBlock;
}

// Find the thread-stream event union and add ThreadBlockEvent to it.
// Remove `assistant_message` from the union (Plan 3 cleans up consumers).
```

- [ ] **Step 4: Run test, expect PASS**

```bash
cd frontend && npx vitest run tests/unit/lib/blocks.test.ts
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api/blocks.ts frontend/lib/api/types.ts frontend/tests/unit/lib/blocks.test.ts
git commit -m "feat(api): TypeScript AgentBlock mirrors of backend pydantic schema"
```

---

## Task 2: `runs.ts` API wrappers

**Files:**
- Create: `frontend/lib/api/runs.ts`
- Test: `frontend/tests/unit/lib/runs.test.ts`

- [ ] **Step 1: Write the test**

```ts
// frontend/tests/unit/lib/runs.test.ts
import { describe, expect, it, vi } from "vitest";
import { pauseRun, resumeRun, cancelRun, deleteRun } from "@/lib/api/runs";

describe("runs API wrappers", () => {
  it("POSTs to /pause", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );
    await pauseRun("ws1", "r1");
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/workspaces/ws1/runs/r1/pause",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("POSTs to /resume", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );
    await resumeRun("ws1", "r1");
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/workspaces/ws1/runs/r1/resume",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("POSTs to /cancel", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );
    await cancelRun("ws1", "r1");
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/workspaces/ws1/runs/r1/cancel",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("DELETEs runs", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );
    await deleteRun("ws1", "r1");
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/workspaces/ws1/runs/r1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("throws on non-2xx", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("err", { status: 500 }),
    );
    await expect(pauseRun("ws1", "r1")).rejects.toThrow(/500/);
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

```bash
cd frontend && npx vitest run tests/unit/lib/runs.test.ts
```
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```ts
// frontend/lib/api/runs.ts
async function postNoBody(url: string): Promise<void> {
  const res = await fetch(url, { method: "POST" });
  if (!res.ok) throw new Error(`POST ${url} failed: ${res.status}`);
}

export const pauseRun = (wsId: string, runId: string) =>
  postNoBody(`/api/workspaces/${wsId}/runs/${runId}/pause`);

export const resumeRun = (wsId: string, runId: string) =>
  postNoBody(`/api/workspaces/${wsId}/runs/${runId}/resume`);

export const cancelRun = (wsId: string, runId: string) =>
  postNoBody(`/api/workspaces/${wsId}/runs/${runId}/cancel`);

export async function deleteRun(wsId: string, runId: string): Promise<void> {
  const res = await fetch(`/api/workspaces/${wsId}/runs/${runId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`DELETE run failed: ${res.status}`);
}
```

- [ ] **Step 4: Run, expect PASS** + **Commit**

```bash
cd frontend && npx vitest run tests/unit/lib/runs.test.ts
git add frontend/lib/api/runs.ts frontend/tests/unit/lib/runs.test.ts
git commit -m "feat(api): runs.ts wrappers — pause/resume/cancel/delete"
```

---

## Task 3: `useWorkflowStore` skeleton + reducer for `subagent.updated`

**Files:**
- Create: `frontend/stores/workflow-store.ts`
- Create: `frontend/stores/workflow-store-support.ts`
- Test: `frontend/tests/unit/stores/workflow-store.test.ts`

- [ ] **Step 1: Write the test**

```ts
// frontend/tests/unit/stores/workflow-store.test.ts
import { describe, expect, it, beforeEach } from "vitest";
import { useWorkflowStore } from "@/stores/workflow-store";
import type { WorkspaceSubagentUpdatedEvent } from "@/lib/api/types";

const baseEv = (overrides: Partial<WorkspaceSubagentUpdatedEvent["subagent"]>): WorkspaceSubagentUpdatedEvent => ({
  type: "subagent.updated",
  workspace_id: "ws1",
  subagent: {
    task_id: "t1", thread_id: "th1", execution_session_id: "es1",
    status: "running", workflow_phase: "p1", workflow_phase_index: 0,
    workflow_task_index: 0, output_preview: null,
    ...overrides,
  },
});

describe("workflow store", () => {
  beforeEach(() => useWorkflowStore.setState({ runs: [], currentRunId: null,
    pausedRunIds: new Set(), followCurrent: true,
    collapsedPhaseIds: new Set(), collapsedRunIds: new Set() }));

  it("ingesting first event creates a run + phase + subagent", () => {
    useWorkflowStore.getState().upsertSubagentEvent(baseEv({}));
    const { runs } = useWorkflowStore.getState();
    expect(runs).toHaveLength(1);
    expect(runs[0].phases).toHaveLength(1);
    expect(runs[0].phases[0].subagents).toHaveLength(1);
    expect(runs[0].phases[0].subagents[0].task_id).toBe("t1");
  });

  it("updates existing subagent in place when status changes", () => {
    const s = useWorkflowStore.getState();
    s.upsertSubagentEvent(baseEv({}));
    s.upsertSubagentEvent(baseEv({ status: "completed", output_preview: "done" }));
    const sub = useWorkflowStore.getState().runs[0].phases[0].subagents[0];
    expect(sub.status).toBe("completed");
    expect(sub.output_preview).toBe("done");
  });

  it("groups by phase_index", () => {
    const s = useWorkflowStore.getState();
    s.upsertSubagentEvent(baseEv({ task_id: "a", workflow_phase_index: 0 }));
    s.upsertSubagentEvent(baseEv({ task_id: "b", workflow_phase_index: 1, workflow_phase: "p2" }));
    const phases = useWorkflowStore.getState().runs[0].phases;
    expect(phases).toHaveLength(2);
    expect(phases[0].subagents[0].task_id).toBe("a");
    expect(phases[1].subagents[0].task_id).toBe("b");
  });

  it("toggleRun adds/removes from collapsedRunIds", () => {
    const s = useWorkflowStore.getState();
    s.upsertSubagentEvent(baseEv({}));
    const runId = useWorkflowStore.getState().runs[0].id;
    s.toggleRun(runId);
    expect(useWorkflowStore.getState().collapsedRunIds.has(runId)).toBe(true);
    s.toggleRun(runId);
    expect(useWorkflowStore.getState().collapsedRunIds.has(runId)).toBe(false);
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

```bash
cd frontend && npx vitest run tests/unit/stores/workflow-store.test.ts
```
Expected: FAIL — module not found.

- [ ] **Step 3: Implement support helpers**

```ts
// frontend/stores/workflow-store-support.ts
import type { WorkspaceSubagentUpdatedEvent } from "@/lib/api/types";

export type SubagentStatus =
  | "pending" | "running" | "completed" | "failed" | "waiting" | "cancelled" | "timed_out";

export interface SubagentSnap {
  task_id: string;
  status: SubagentStatus | string;
  subagent_type?: string | null;
  output_preview?: string | null;
  error?: string | null;
  token_usage?: { total?: number } | null;
  model_name?: string | null;
  duration_ms?: number;
}

export interface PhaseSnap {
  index: number;
  name: string;                              // workflow_phase string
  subagents: SubagentSnap[];
}

export interface Run {
  id: string;                                // execution_session_id (the langgraph run id)
  thread_id: string;
  title: string;                             // first phase name; agent may rename via result_card
  phases: PhaseSnap[];
  status: "running" | "paused" | "completed" | "cancelled" | "failed";
  started_at: string;
}

export function asNumber(v: unknown): number | null {
  if (typeof v === "number") return v;
  if (typeof v === "string" && v !== "") return Number(v);
  return null;
}

export function reduceSubagentEvent(runs: Run[], ev: WorkspaceSubagentUpdatedEvent): Run[] {
  const sa = ev.subagent;
  const runId = sa.execution_session_id;
  const phaseIdx = asNumber(sa.workflow_phase_index) ?? 0;
  const phaseName = sa.workflow_phase ?? `phase ${phaseIdx}`;

  const next = [...runs];
  let run = next.find((r) => r.id === runId);
  if (!run) {
    run = {
      id: runId,
      thread_id: sa.thread_id,
      title: phaseName,
      phases: [],
      status: "running",
      started_at: ev.timestamp ?? new Date().toISOString(),
    };
    next.push(run);
  }

  let phase = run.phases.find((p) => p.index === phaseIdx);
  if (!phase) {
    phase = { index: phaseIdx, name: phaseName, subagents: [] };
    run.phases.push(phase);
    run.phases.sort((a, b) => a.index - b.index);
  }

  const existingIdx = phase.subagents.findIndex((s) => s.task_id === sa.task_id);
  const snap: SubagentSnap = {
    task_id: sa.task_id,
    status: sa.status,
    subagent_type: sa.subagent_type ?? null,
    output_preview: sa.output_preview ?? null,
    error: sa.error ?? null,
    token_usage: sa.token_usage ?? null,
    model_name: sa.model_name ?? null,
  };
  if (existingIdx === -1) phase.subagents.push(snap);
  else phase.subagents[existingIdx] = { ...phase.subagents[existingIdx], ...snap };

  return next;
}
```

```ts
// frontend/stores/workflow-store.ts
import { create } from "zustand";
import type { WorkspaceSubagentUpdatedEvent } from "@/lib/api/types";
import { type Run, reduceSubagentEvent } from "./workflow-store-support";
import { pauseRun as apiPause, resumeRun as apiResume, deleteRun as apiDelete } from "@/lib/api/runs";

interface WorkflowState {
  runs: Run[];
  currentRunId: string | null;
  pausedRunIds: Set<string>;
  followCurrent: boolean;
  collapsedPhaseIds: Set<string>;            // key = `${runId}:${phaseIndex}`
  collapsedRunIds: Set<string>;

  upsertSubagentEvent: (ev: WorkspaceSubagentUpdatedEvent) => void;
  toggleRun: (runId: string) => void;
  togglePhase: (runId: string, phaseIndex: number) => void;
  setFollow: (enabled: boolean) => void;
  pauseRun: (workspaceId: string, runId: string) => Promise<void>;
  resumeRun: (workspaceId: string, runId: string) => Promise<void>;
  deleteRun: (workspaceId: string, runId: string) => Promise<void>;
}

export const useWorkflowStore = create<WorkflowState>((set, get) => ({
  runs: [],
  currentRunId: null,
  pausedRunIds: new Set(),
  followCurrent: true,
  collapsedPhaseIds: new Set(),
  collapsedRunIds: new Set(),

  upsertSubagentEvent(ev) {
    set((state) => {
      const runs = reduceSubagentEvent(state.runs, ev);
      const currentRunId = ev.subagent.execution_session_id;
      return { runs, currentRunId };
    });
  },

  toggleRun(runId) {
    set((s) => {
      const next = new Set(s.collapsedRunIds);
      if (next.has(runId)) next.delete(runId); else next.add(runId);
      return { collapsedRunIds: next };
    });
  },

  togglePhase(runId, phaseIndex) {
    const key = `${runId}:${phaseIndex}`;
    set((s) => {
      const next = new Set(s.collapsedPhaseIds);
      if (next.has(key)) next.delete(key); else next.add(key);
      return { collapsedPhaseIds: next };
    });
  },

  setFollow(enabled) { set({ followCurrent: enabled }); },

  async pauseRun(workspaceId, runId) {
    await apiPause(workspaceId, runId);
    set((s) => ({ pausedRunIds: new Set([...s.pausedRunIds, runId]) }));
  },

  async resumeRun(workspaceId, runId) {
    await apiResume(workspaceId, runId);
    set((s) => {
      const next = new Set(s.pausedRunIds); next.delete(runId);
      return { pausedRunIds: next };
    });
  },

  async deleteRun(workspaceId, runId) {
    await apiDelete(workspaceId, runId);
    set((s) => ({ runs: s.runs.filter((r) => r.id !== runId) }));
  },
}));
```

- [ ] **Step 4: Run, expect PASS** + **Commit**

```bash
cd frontend && npx vitest run tests/unit/stores/workflow-store.test.ts
git add frontend/stores/workflow-store*.ts frontend/tests/unit/stores/workflow-store.test.ts
git commit -m "feat(stores): useWorkflowStore — runs/phases/subagents reduced from SSE"
```

---

## Task 4: `SubagentCard` component (start of UI)

> **REMINDER:** Invoke `superpowers:frontend-design` skill before writing JSX/Tailwind.

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/SubagentCard.tsx`
- Test: `frontend/tests/unit/components/live-workflow/SubagentCard.test.tsx`

- [ ] **Step 1: Write the test**

```tsx
// frontend/tests/unit/components/live-workflow/SubagentCard.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SubagentCard } from "@/app/(workbench)/workspaces/[id]/components/live-workflow/SubagentCard";

const base = {
  task_id: "t1",
  status: "running",
  subagent_type: "reader",
  output_preview: "正在读 §3 方法",
  token_usage: { total: 1200 },
};

describe("SubagentCard", () => {
  it("renders status, type, preview", () => {
    render(<SubagentCard subagent={base as any} />);
    expect(screen.getByText(/reader/i)).toBeInTheDocument();
    expect(screen.getByText(/正在读 §3 方法/)).toBeInTheDocument();
  });

  it("shows token + duration in corner", () => {
    render(<SubagentCard subagent={{ ...base, duration_ms: 14000 } as any} />);
    expect(screen.getByText(/1\.2k tokens/i)).toBeInTheDocument();
    expect(screen.getByText(/14s/i)).toBeInTheDocument();
  });

  it("waiting status shows pointer back to chat", () => {
    render(<SubagentCard subagent={{ ...base, status: "waiting" } as any} />);
    expect(screen.getByText(/在 chat 里问了你/)).toBeInTheDocument();
  });

  it("failed status shows error", () => {
    render(<SubagentCard subagent={{ ...base, status: "failed", error: "PDF 解析超时" } as any} />);
    expect(screen.getByText(/失败/)).toBeInTheDocument();
    expect(screen.getByText(/PDF 解析超时/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

```bash
cd frontend && npx vitest run tests/unit/components/live-workflow/SubagentCard.test.tsx
```

- [ ] **Step 3: Implement**

```tsx
// frontend/app/(workbench)/workspaces/[id]/components/live-workflow/SubagentCard.tsx
"use client";
import type { SubagentSnap } from "@/stores/workflow-store-support";

type Status = "pending" | "running" | "completed" | "waiting" | "failed" | "cancelled" | "timed_out";

const PILL_STYLE: Record<string, string> = {
  pending:   "bg-white/5 text-white/50",
  running:   "bg-blue-400/15 text-blue-200",
  completed: "bg-green-400/15 text-green-200",
  waiting:   "bg-amber-400/15 text-amber-200",
  failed:    "bg-red-400/15 text-red-200",
  cancelled: "bg-white/5 text-white/40",
  timed_out: "bg-red-400/15 text-red-200",
};

const PILL_LABEL: Record<string, string> = {
  pending: "待启动",
  running: "运行中",
  completed: "完成",
  waiting: "需要你回答",
  failed: "失败 · 重试",
  cancelled: "已取消",
  timed_out: "超时",
};

function formatTokens(n?: number): string {
  if (!n) return "";
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k tokens`;
  return `${n} tokens`;
}
function formatDur(ms?: number): string {
  if (!ms) return "";
  return `${Math.round(ms / 1000)}s`;
}

export function SubagentCard({ subagent }: { subagent: SubagentSnap }) {
  const s = (subagent.status as Status) ?? "pending";
  const pillCls = PILL_STYLE[s] ?? PILL_STYLE.pending;
  const pillTxt = PILL_LABEL[s] ?? s;

  return (
    <div
      className={`rounded-lg border border-white/10 bg-white/[0.03] p-2.5 ${
        s === "running" ? "border-blue-400/30" : ""
      } ${s === "waiting" ? "border-amber-400/30 bg-amber-400/5" : ""}`}
      data-testid={`subagent-card-${subagent.task_id}`}
    >
      <div className="flex items-center justify-between text-[11px]">
        <span className="opacity-50">{subagent.subagent_type ?? "subagent"} · #{subagent.task_id.slice(0, 6)}</span>
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${pillCls}`}>{pillTxt}</span>
      </div>

      {subagent.output_preview && (
        <div className="mt-1.5 rounded bg-black/25 p-1.5 text-[11px] opacity-75">
          {subagent.output_preview}
        </div>
      )}

      {s === "waiting" && (
        <div className="mt-1.5 rounded-r border-l-2 border-amber-400/50 bg-amber-400/[0.06] p-1.5 text-[11px]">
          ↩︎ 在 chat 里问了你一个问题
        </div>
      )}

      {s === "failed" && subagent.error && (
        <div className="mt-1.5 text-[11px] opacity-70">{subagent.error}</div>
      )}

      <div className="mt-1.5 flex gap-2 text-[10px] opacity-50">
        {subagent.token_usage?.total ? <span>{formatTokens(subagent.token_usage.total)}</span> : null}
        {subagent.duration_ms ? <span>{formatDur(subagent.duration_ms)}</span> : null}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run, expect PASS** + **Commit**

```bash
cd frontend && npx vitest run tests/unit/components/live-workflow/SubagentCard.test.tsx
git add frontend/app/\(workbench\)/workspaces/\[id\]/components/live-workflow/SubagentCard.tsx \
        frontend/tests/unit/components/live-workflow/SubagentCard.test.tsx
git commit -m "feat(live-workflow): SubagentCard with status pill, preview, waiting/failed states"
```

---

## Task 5: `SubagentGrid` (2-col + nested fold for many)

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/SubagentGrid.tsx`
- Test: `frontend/tests/unit/components/live-workflow/SubagentGrid.test.tsx`

- [ ] **Step 1: Test**

```tsx
import { describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SubagentGrid } from "@/app/(workbench)/workspaces/[id]/components/live-workflow/SubagentGrid";

const make = (n: number, status = "running") => Array.from({ length: n }, (_, i) => ({
  task_id: `t${i}`, status, subagent_type: "reader",
}));

describe("SubagentGrid", () => {
  it("renders all when count < 6", () => {
    render(<SubagentGrid subagents={make(3) as any} />);
    expect(screen.getAllByTestId(/subagent-card-/)).toHaveLength(3);
  });

  it("nested fold: when count >= 6, completed are collapsed by default", () => {
    const list = [...make(4, "completed"), ...make(3, "running")];
    render(<SubagentGrid subagents={list as any} />);
    // Only the 3 running are visible
    expect(screen.getAllByTestId(/subagent-card-/)).toHaveLength(3);
    // A "show 4 done" button is present
    expect(screen.getByRole("button", { name: /4 个已完成/ })).toBeInTheDocument();
  });

  it("clicking 'show done' expands them", () => {
    const list = [...make(4, "completed"), ...make(3, "running")];
    render(<SubagentGrid subagents={list as any} />);
    fireEvent.click(screen.getByRole("button", { name: /4 个已完成/ }));
    expect(screen.getAllByTestId(/subagent-card-/)).toHaveLength(7);
  });
});
```

- [ ] **Step 2: Run, expect FAIL** then **Step 3: Implement**

```tsx
// frontend/app/(workbench)/workspaces/[id]/components/live-workflow/SubagentGrid.tsx
"use client";
import { useState } from "react";
import type { SubagentSnap } from "@/stores/workflow-store-support";
import { SubagentCard } from "./SubagentCard";

const FOLD_THRESHOLD = 6;
const TERMINAL = new Set(["completed", "failed", "cancelled", "timed_out"]);

export function SubagentGrid({ subagents }: { subagents: SubagentSnap[] }) {
  const [showDone, setShowDone] = useState(false);
  const useFold = subagents.length >= FOLD_THRESHOLD;

  const done = subagents.filter((s) => TERMINAL.has(s.status));
  const live = subagents.filter((s) => !TERMINAL.has(s.status));

  const visible = useFold && !showDone ? live : subagents;

  return (
    <div>
      <div className={`grid gap-2 ${visible.length > 1 ? "grid-cols-2" : "grid-cols-1"}`}>
        {visible.map((s) => <SubagentCard key={s.task_id} subagent={s} />)}
      </div>
      {useFold && !showDone && done.length > 0 && (
        <button
          type="button"
          onClick={() => setShowDone(true)}
          className="mt-2 w-full rounded bg-white/5 py-1 text-[11px] opacity-60 hover:opacity-90"
        >
          ▾ {done.length} 个已完成（点开查看）
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run, PASS** + **Commit**

```bash
cd frontend && npx vitest run tests/unit/components/live-workflow/SubagentGrid.test.tsx
git add frontend/app/\(workbench\)/workspaces/\[id\]/components/live-workflow/SubagentGrid.tsx \
        frontend/tests/unit/components/live-workflow/SubagentGrid.test.tsx
git commit -m "feat(live-workflow): SubagentGrid with nested fold for >=6 items"
```

---

## Task 6: `PhaseList` (collapse done, expand current)

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/PhaseList.tsx`
- Test: `frontend/tests/unit/components/live-workflow/PhaseList.test.tsx`

- [ ] **Step 1: Test**

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PhaseList } from "@/app/(workbench)/workspaces/[id]/components/live-workflow/PhaseList";

const phase = (idx: number, sas: any[]) => ({ index: idx, name: `phase ${idx}`, subagents: sas });

describe("PhaseList", () => {
  it("collapses phases whose all subagents are completed", () => {
    const phases = [
      phase(0, [{ task_id: "a", status: "completed" }]),
      phase(1, [{ task_id: "b", status: "running" }]),
    ];
    render(<PhaseList runId="r1" phases={phases as any} />);
    // Phase 0 header visible but body hidden
    expect(screen.queryByTestId("subagent-card-a")).not.toBeInTheDocument();
    expect(screen.getByTestId("subagent-card-b")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, expect FAIL** then **Step 3: Implement**

```tsx
// frontend/app/(workbench)/workspaces/[id]/components/live-workflow/PhaseList.tsx
"use client";
import type { PhaseSnap } from "@/stores/workflow-store-support";
import { useWorkflowStore } from "@/stores/workflow-store";
import { SubagentGrid } from "./SubagentGrid";

const TERMINAL = new Set(["completed", "failed", "cancelled", "timed_out"]);

function phaseStatus(phase: PhaseSnap): "done" | "running" | "pending" {
  if (phase.subagents.length === 0) return "pending";
  if (phase.subagents.every((s) => TERMINAL.has(s.status))) return "done";
  return "running";
}

export function PhaseList({ runId, phases }: { runId: string; phases: PhaseSnap[] }) {
  const collapsed = useWorkflowStore((s) => s.collapsedPhaseIds);
  const togglePhase = useWorkflowStore((s) => s.togglePhase);

  return (
    <div className="space-y-2">
      {phases.map((p) => {
        const status = phaseStatus(p);
        const key = `${runId}:${p.index}`;
        const userCollapsed = collapsed.has(key);
        const isCollapsed = userCollapsed || (status === "done" && !collapsed.has(key) ? true : false);
        // Default: done collapsed; running expanded; pending collapsed.
        const showBody = status === "running" ? !userCollapsed : !isCollapsed && userCollapsed === false ? status === "running" : false;
        // Simplify: by default collapse done; user can toggle.
        const open = status === "running" ? true : userCollapsed === true ? false : status === "running";

        // Real logic:
        const defaultOpen = status === "running";
        const reallyOpen = userCollapsed ? !defaultOpen : defaultOpen;

        return (
          <div key={p.index} className={status === "running" ? "rounded-lg border border-blue-400/20 bg-blue-400/5" : "rounded-lg"}>
            <button
              type="button"
              onClick={() => togglePhase(runId, p.index)}
              className="flex w-full items-center gap-2 px-2.5 py-2 text-left"
              data-testid={`phase-header-${p.index}`}
            >
              <span className={`flex h-[18px] w-[18px] items-center justify-center rounded-full text-[10px] font-semibold ${
                status === "done" ? "bg-green-400/15 text-green-300"
                : status === "running" ? "bg-blue-400/25 text-white"
                : "bg-white/5 text-white/40"
              }`}>
                {status === "done" ? "✓" : status === "running" ? "◐" : p.index + 1}
              </span>
              <span className={`flex-1 font-semibold ${status === "pending" ? "opacity-40" : ""}`}>
                {p.name}
              </span>
              <span className="text-[11px] opacity-55">
                {p.subagents.filter((s) => TERMINAL.has(s.status)).length}/{p.subagents.length}
              </span>
            </button>
            {reallyOpen && (
              <div className="px-2.5 pb-2.5">
                <SubagentGrid subagents={p.subagents} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 4: Run, PASS** + **Commit**

```bash
cd frontend && npx vitest run tests/unit/components/live-workflow/PhaseList.test.tsx
git add frontend/app/\(workbench\)/workspaces/\[id\]/components/live-workflow/PhaseList.tsx \
        frontend/tests/unit/components/live-workflow/PhaseList.test.tsx
git commit -m "feat(live-workflow): PhaseList with done-collapsed/running-expanded behavior"
```

---

## Task 7: `RunList` + `LiveWorkflowPanel` shell + `WorkspaceAssets` placeholder

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/RunList.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/LiveWorkflowPanel.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/WorkspaceAssets.tsx`
- Test: `frontend/tests/unit/components/live-workflow/LiveWorkflowPanel.test.tsx`

- [ ] **Step 1: Test**

```tsx
// frontend/tests/unit/components/live-workflow/LiveWorkflowPanel.test.tsx
import { describe, expect, it, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useWorkflowStore } from "@/stores/workflow-store";
import { LiveWorkflowPanel } from "@/app/(workbench)/workspaces/[id]/components/live-workflow/LiveWorkflowPanel";

describe("LiveWorkflowPanel", () => {
  beforeEach(() => useWorkflowStore.setState({
    runs: [], currentRunId: null, pausedRunIds: new Set(),
    followCurrent: true, collapsedPhaseIds: new Set(), collapsedRunIds: new Set(),
  }));

  it("renders empty + WorkspaceAssets when no run", () => {
    render(<LiveWorkflowPanel workspaceId="ws1" />);
    expect(screen.getByTestId("workspace-assets")).toBeInTheDocument();
    expect(screen.queryByTestId("run-list")).not.toBeInTheDocument();
  });

  it("renders run list when there are runs", () => {
    useWorkflowStore.setState({
      runs: [{ id: "r1", thread_id: "t", title: "phase 0", phases: [],
               status: "running", started_at: "2026-05-07" }],
      currentRunId: "r1",
    } as any);
    render(<LiveWorkflowPanel workspaceId="ws1" />);
    expect(screen.getByTestId("run-list")).toBeInTheDocument();
  });

  it("pause button calls store.pauseRun", async () => {
    useWorkflowStore.setState({
      runs: [{ id: "r1", thread_id: "t", title: "x", phases: [], status: "running", started_at: "" }],
      currentRunId: "r1",
    } as any);
    let called = "";
    useWorkflowStore.setState({ pauseRun: async (_w, r) => { called = r; } } as any);
    render(<LiveWorkflowPanel workspaceId="ws1" />);
    fireEvent.click(screen.getByRole("button", { name: /在下个安全点暂停/ }));
    expect(called).toBe("r1");
  });
});
```

- [ ] **Step 2: Implement**

```tsx
// frontend/app/(workbench)/workspaces/[id]/components/live-workflow/WorkspaceAssets.tsx
"use client";
import { useState } from "react";

// Plan 3 wires the real ArtifactLibrary / LiteraturePanel / KnowledgePanel
// into this shell; for now we ship a placeholder with the right structure.
export function WorkspaceAssets({ defaultOpen }: { defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div data-testid="workspace-assets" className="rounded-lg bg-white/[0.02] mt-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2 text-[12px]"
      >
        <span>📚 文献 · 📦 成果 · 🧠 上下文</span>
        <span className="opacity-50">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="px-3 pb-3 text-[11px] opacity-60">
          {/* Plan 3 mounts ArtifactLibrary / LiteraturePanel / KnowledgePanel here */}
          <p>（在 Plan 3 中接入真实子组件）</p>
        </div>
      )}
    </div>
  );
}
```

```tsx
// frontend/app/(workbench)/workspaces/[id]/components/live-workflow/RunList.tsx
"use client";
import { useWorkflowStore } from "@/stores/workflow-store";
import type { Run } from "@/stores/workflow-store-support";
import { PhaseList } from "./PhaseList";

export function RunList() {
  const runs = useWorkflowStore((s) => s.runs);
  const currentRunId = useWorkflowStore((s) => s.currentRunId);
  const collapsedRunIds = useWorkflowStore((s) => s.collapsedRunIds);
  const toggleRun = useWorkflowStore((s) => s.toggleRun);

  return (
    <div data-testid="run-list" className="space-y-3">
      {runs.map((run: Run, i: number) => {
        const isCurrent = run.id === currentRunId;
        const userToggled = collapsedRunIds.has(run.id);
        const open = isCurrent ? !userToggled : userToggled;
        return (
          <div key={run.id} className="rounded-lg bg-white/[0.02]">
            <button
              type="button"
              onClick={() => toggleRun(run.id)}
              className="flex w-full items-center justify-between px-3 py-2 text-[12px]"
            >
              <span className={isCurrent ? "font-semibold" : "opacity-65"}>
                轮 {i + 1} · {run.title} {run.status === "completed" ? "✓" : ""}
              </span>
              <span className="opacity-50">{open ? "▾" : "▸"}</span>
            </button>
            {open && <div className="px-3 pb-3"><PhaseList runId={run.id} phases={run.phases} /></div>}
          </div>
        );
      })}
    </div>
  );
}
```

```tsx
// frontend/app/(workbench)/workspaces/[id]/components/live-workflow/LiveWorkflowPanel.tsx
"use client";
import { useWorkflowStore } from "@/stores/workflow-store";
import { RunList } from "./RunList";
import { WorkspaceAssets } from "./WorkspaceAssets";

export function LiveWorkflowPanel({ workspaceId }: { workspaceId: string }) {
  const runs = useWorkflowStore((s) => s.runs);
  const currentRunId = useWorkflowStore((s) => s.currentRunId);
  const isPaused = useWorkflowStore((s) => currentRunId ? s.pausedRunIds.has(currentRunId) : false);
  const pauseRun = useWorkflowStore((s) => s.pauseRun);
  const resumeRun = useWorkflowStore((s) => s.resumeRun);

  const hasActive = runs.some((r) => r.status === "running");

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-3 py-2 border-b border-white/8">
        <div className="text-[12px] opacity-65">实时工作台</div>
        {currentRunId && (
          <button
            type="button"
            onClick={() => isPaused ? resumeRun(workspaceId, currentRunId) : pauseRun(workspaceId, currentRunId)}
            className="rounded bg-white/[0.05] px-2 py-1 text-[11px] hover:bg-white/[0.10]"
          >
            {isPaused ? "继续" : "在下个安全点暂停"}
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3">
        {runs.length > 0 && <RunList />}
        <WorkspaceAssets defaultOpen={!hasActive} />
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Run + Commit**

```bash
cd frontend && npx vitest run tests/unit/components/live-workflow/
git add frontend/app/\(workbench\)/workspaces/\[id\]/components/live-workflow/ \
        frontend/tests/unit/components/live-workflow/
git commit -m "feat(live-workflow): LiveWorkflowPanel + RunList + WorkspaceAssets placeholder"
```

---

## Task 8: SSE wiring — subscribe `subagent.updated` and feed store

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/useWorkflowSubscription.ts`
- Test: `frontend/tests/unit/components/live-workflow/useWorkflowSubscription.test.tsx`

- [ ] **Step 1: Test**

```tsx
import { describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";
import { useWorkflowStore } from "@/stores/workflow-store";
import { useWorkflowSubscription } from "@/app/(workbench)/workspaces/[id]/components/live-workflow/useWorkflowSubscription";

// Mock the existing subscriber from streams.ts
vi.mock("@/lib/api/streams", () => ({
  subscribeWorkspaceEvents: (wsId: string, cb: (ev: any) => void) => {
    cb({
      type: "subagent.updated",
      workspace_id: wsId,
      subagent: { task_id: "t1", thread_id: "th", execution_session_id: "r1",
                  status: "running", workflow_phase: "p1", workflow_phase_index: 0 },
    });
    return () => {};
  },
}));

describe("useWorkflowSubscription", () => {
  it("ingests events into the store", () => {
    useWorkflowStore.setState({ runs: [] } as any);
    renderHook(() => useWorkflowSubscription("ws1"));
    expect(useWorkflowStore.getState().runs).toHaveLength(1);
    expect(useWorkflowStore.getState().runs[0].id).toBe("r1");
  });
});
```

- [ ] **Step 2: Implement**

```ts
// frontend/app/(workbench)/workspaces/[id]/components/live-workflow/useWorkflowSubscription.ts
import { useEffect } from "react";
import { subscribeWorkspaceEvents } from "@/lib/api/streams";
import type { WorkspaceEvent } from "@/lib/api/types";
import { useWorkflowStore } from "@/stores/workflow-store";

export function useWorkflowSubscription(workspaceId: string): void {
  useEffect(() => {
    const upsert = useWorkflowStore.getState().upsertSubagentEvent;
    const unsub = subscribeWorkspaceEvents(workspaceId, (ev: WorkspaceEvent) => {
      if (ev.type === "subagent.updated") upsert(ev);
    });
    return () => { unsub?.(); };
  }, [workspaceId]);
}
```

- [ ] **Step 3: Mount in LiveWorkflowPanel**

Edit `LiveWorkflowPanel.tsx`, near the top of the component body:

```tsx
useWorkflowSubscription(workspaceId);
```

- [ ] **Step 4: Run + Commit**

```bash
cd frontend && npx vitest run tests/unit/components/live-workflow/
git add frontend/app/\(workbench\)/workspaces/\[id\]/components/live-workflow/useWorkflowSubscription.ts \
        frontend/tests/unit/components/live-workflow/useWorkflowSubscription.test.tsx \
        frontend/app/\(workbench\)/workspaces/\[id\]/components/live-workflow/LiveWorkflowPanel.tsx
git commit -m "feat(live-workflow): subscribe to subagent.updated SSE and reduce into store"
```

---

## Task 9: Block renderers — `TextBlock` + `StatusLineBlock`

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/TextBlock.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/StatusLineBlock.tsx`
- Tests: under `frontend/tests/unit/components/chat-thread/blocks/`

- [ ] **Step 1: Tests**

```tsx
// frontend/tests/unit/components/chat-thread/blocks/TextBlock.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { TextBlock } from "@/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/TextBlock";

describe("TextBlock", () => {
  it("renders content", () => {
    render(<TextBlock block={{ kind: "text", content: "好，先扫文献" }} />);
    expect(screen.getByText("好，先扫文献")).toBeInTheDocument();
  });
});
```

```tsx
// frontend/tests/unit/components/chat-thread/blocks/StatusLineBlock.test.tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { StatusLineBlock } from "@/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/StatusLineBlock";

describe("StatusLineBlock", () => {
  it("renders label", () => {
    render(<StatusLineBlock block={{ kind: "status_line", label: "phase 1 完成", run_id: "r1", tone: "info" }} />);
    expect(screen.getByText(/phase 1 完成/)).toBeInTheDocument();
  });

  it("invokes onJumpToPhase on click", () => {
    const onJump = vi.fn();
    render(<StatusLineBlock
      block={{ kind: "status_line", label: "x", run_id: "r1", phase_index: 2, tone: "info" }}
      onJumpToPhase={onJump}
    />);
    fireEvent.click(screen.getByRole("button"));
    expect(onJump).toHaveBeenCalledWith("r1", 2);
  });

  it("warn tone has different color class", () => {
    const { container } = render(
      <StatusLineBlock block={{ kind: "status_line", label: "x", run_id: "r1", tone: "warn" }} />,
    );
    expect(container.firstChild).toHaveClass(/amber|warn/);
  });
});
```

- [ ] **Step 2: Implement**

```tsx
// frontend/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/TextBlock.tsx
"use client";
import type { TextBlock as T } from "@/lib/api/blocks";

export function TextBlock({ block }: { block: T }) {
  return <div className="whitespace-pre-wrap text-[13px] leading-relaxed">{block.content}</div>;
}
```

```tsx
// frontend/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/StatusLineBlock.tsx
"use client";
import type { StatusLineBlock as S } from "@/lib/api/blocks";

const TONE: Record<string, string> = {
  info:  "border-blue-400/30 text-blue-200/80",
  warn:  "border-amber-400/40 text-amber-200/85",
  error: "border-red-400/40 text-red-200/85",
};

export function StatusLineBlock({
  block,
  onJumpToPhase,
}: {
  block: S;
  onJumpToPhase?: (runId: string, phaseIndex: number) => void;
}) {
  const cls = TONE[block.tone] ?? TONE.info;
  return (
    <button
      type="button"
      className={`my-2 ml-1 flex items-center gap-2 border-l-2 px-2.5 py-1 text-[11px] opacity-75 ${cls}`}
      onClick={() => block.phase_index != null && onJumpToPhase?.(block.run_id, block.phase_index)}
    >
      <span className="opacity-70">→</span>
      <span>{block.label}</span>
    </button>
  );
}
```

- [ ] **Step 3: Run + Commit**

```bash
cd frontend && npx vitest run tests/unit/components/chat-thread/blocks/
git add frontend/app/\(workbench\)/workspaces/\[id\]/components/chat-thread/blocks/TextBlock.tsx \
        frontend/app/\(workbench\)/workspaces/\[id\]/components/chat-thread/blocks/StatusLineBlock.tsx \
        frontend/tests/unit/components/chat-thread/blocks/
git commit -m "feat(chat-thread): TextBlock + StatusLineBlock renderers"
```

---

## Task 10: `QuestionCardBlock` renderer

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/QuestionCardBlock.tsx`
- Test: `frontend/tests/unit/components/chat-thread/blocks/QuestionCardBlock.test.tsx`

- [ ] **Step 1: Test**

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QuestionCardBlock } from "@/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/QuestionCardBlock";

const block = {
  kind: "question_card" as const,
  label: "需要你拍一下",
  question: "更想看哪条线？",
  pills: [
    { label: "单客户端", intent: "single" },
    { label: "多客户端", intent: "multi" },
  ],
};

describe("QuestionCardBlock", () => {
  it("renders question + pills", () => {
    render(<QuestionCardBlock block={block} />);
    expect(screen.getByText("需要你拍一下")).toBeInTheDocument();
    expect(screen.getByText("更想看哪条线？")).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(2);
  });

  it("invokes onPillClick with intent", () => {
    const onPill = vi.fn();
    render(<QuestionCardBlock block={block} onPillClick={onPill} />);
    fireEvent.click(screen.getByRole("button", { name: "单客户端" }));
    expect(onPill).toHaveBeenCalledWith("single", "单客户端");
  });

  it("renders without pills when empty", () => {
    render(<QuestionCardBlock block={{ ...block, pills: [] }} />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});
```

- [ ] **Step 2: Implement**

```tsx
// frontend/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/QuestionCardBlock.tsx
"use client";
import type { QuestionCardBlock as Q } from "@/lib/api/blocks";

export function QuestionCardBlock({
  block,
  onPillClick,
}: {
  block: Q;
  onPillClick?: (intent: string, label: string) => void;
}) {
  return (
    <div className="rounded-xl border border-amber-400/20 bg-amber-400/[0.04] p-3">
      <div className="text-[10.5px] uppercase tracking-wide text-amber-300/85">{block.label}</div>
      <div className="mt-1 text-[13px]">{block.question}</div>
      {block.pills.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {block.pills.map((p) => (
            <button
              key={p.intent}
              type="button"
              onClick={() => onPillClick?.(p.intent, p.label)}
              className="rounded border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[12px] hover:bg-white/[0.08]"
            >
              {p.label}
            </button>
          ))}
        </div>
      )}
      <div className="mt-2 text-[11px] opacity-55">或者直接打字告诉我你的想法。</div>
    </div>
  );
}
```

- [ ] **Step 3: Run + Commit**

```bash
cd frontend && npx vitest run tests/unit/components/chat-thread/blocks/QuestionCardBlock.test.tsx
git add frontend/app/\(workbench\)/workspaces/\[id\]/components/chat-thread/blocks/QuestionCardBlock.tsx \
        frontend/tests/unit/components/chat-thread/blocks/QuestionCardBlock.test.tsx
git commit -m "feat(chat-thread): QuestionCardBlock renderer with pill click handler"
```

---

## Task 11: `ResultCardBlock` renderer

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/ResultCardBlock.tsx`
- Test: under same blocks/ tests dir

- [ ] **Step 1: Test**

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ResultCardBlock } from "@/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/ResultCardBlock";

const block = {
  kind: "result_card" as const,
  run_id: "r1",
  title: "论文分析 · 完成",
  tldr: "3 个角度可切",
  findings: [
    { id: "1", text: "异构客户端缺口" },
    { id: "2", text: "trade-off 量化空白" },
  ],
  recommend: { label: "推荐切入", body: "通信效率 × 隐私强度" },
  links: [{ icon: "📄", label: "详细报告", href: "#" }],
  feedback: {
    question: "这个结论你怎么看？",
    pills: [
      { kind: "primary" as const, label: "进入选题", intent: "next" },
      { kind: "warn" as const, label: "换方向", intent: "redirect" },
    ],
    allow_free_input: true,
  },
  stats: { duration_ms: 102000, subagents: 13, tokens: 8400 },
};

describe("ResultCardBlock", () => {
  it("renders TL;DR + findings + recommend + links", () => {
    render(<ResultCardBlock block={block} />);
    expect(screen.getByText(/3 个角度可切/)).toBeInTheDocument();
    expect(screen.getByText(/异构客户端缺口/)).toBeInTheDocument();
    expect(screen.getByText(/推荐切入/)).toBeInTheDocument();
    expect(screen.getByText(/详细报告/)).toBeInTheDocument();
  });

  it("renders findings with numeric labels (① ② …)", () => {
    render(<ResultCardBlock block={block} />);
    expect(screen.getByText(/①/)).toBeInTheDocument();
    expect(screen.getByText(/②/)).toBeInTheDocument();
  });

  it("primary pill has special styling", () => {
    render(<ResultCardBlock block={block} />);
    const primary = screen.getByRole("button", { name: "进入选题" });
    expect(primary.className).toMatch(/green|primary/);
  });

  it("invokes onFeedback with intent", () => {
    const onFeedback = vi.fn();
    render(<ResultCardBlock block={block} onFeedback={onFeedback} />);
    fireEvent.click(screen.getByRole("button", { name: "换方向" }));
    expect(onFeedback).toHaveBeenCalledWith("redirect", "换方向");
  });
});
```

- [ ] **Step 2: Implement**

```tsx
// frontend/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/ResultCardBlock.tsx
"use client";
import type { ResultCardBlock as R, FeedbackPill } from "@/lib/api/blocks";

const NUM_BADGE = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨"];

const PILL_CLASS: Record<FeedbackPill["kind"], string> = {
  primary: "bg-green-400/10 border-green-400/40 text-green-200",
  normal:  "bg-white/[0.04] border-white/10 text-white",
  warn:    "bg-amber-400/[0.06] border-amber-400/30 text-amber-300/90",
};

function formatDur(ms: number): string {
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

export function ResultCardBlock({
  block,
  onFeedback,
}: {
  block: R;
  onFeedback?: (intent: string, label: string) => void;
}) {
  return (
    <div className="rounded-xl border border-green-400/25 bg-gradient-to-b from-green-400/[0.06] to-green-400/[0.02] p-4">
      <div className="flex items-center justify-between border-b border-dashed border-green-400/20 pb-2">
        <div>
          <div className="text-[14px] font-semibold">📑 {block.title}</div>
          <div className="text-[11px] opacity-55">
            {block.stats.subagents} subagents · {formatDur(block.stats.duration_ms)} · {block.stats.tokens.toLocaleString()} tokens
          </div>
        </div>
        <span className="rounded bg-green-400/15 px-2 py-0.5 text-[11px] text-green-200">已完成</span>
      </div>

      <div className="mt-3 rounded bg-white/[0.04] p-2.5 text-[12.5px]">
        <span className="text-green-300">TL;DR：</span>{block.tldr}
      </div>

      <div className="mt-3">
        <div className="mb-1 text-[11px] uppercase tracking-wide opacity-60">关键发现</div>
        {block.findings.map((f, i) => (
          <div key={f.id} className="flex gap-2 py-1 text-[12.5px]">
            <span className="text-green-300 font-semibold">{NUM_BADGE[i] ?? `(${i + 1})`}</span>
            <span>{f.text}</span>
          </div>
        ))}
      </div>

      {block.recommend && (
        <div className="mt-3 rounded-r border-l-2 border-blue-400/50 bg-blue-400/[0.06] py-2 pl-3 pr-2">
          <div className="text-[10.5px] uppercase tracking-wide text-blue-200/80">{block.recommend.label}</div>
          <div className="mt-0.5 text-[12.5px]">{block.recommend.body}</div>
        </div>
      )}

      {block.links.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {block.links.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="inline-flex items-center gap-1 rounded border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[11.5px]"
            >
              <span className="opacity-60">{l.icon}</span>{l.label}
            </a>
          ))}
        </div>
      )}

      <div className="mt-3 border-t border-dashed border-green-400/15 pt-3">
        <div className="text-[12.5px] opacity-85">{block.feedback.question}</div>
        <div className="mt-2 flex flex-wrap gap-2">
          {block.feedback.pills.map((p) => (
            <button
              key={p.intent}
              type="button"
              onClick={() => onFeedback?.(p.intent, p.label)}
              className={`rounded border px-2.5 py-1 text-[12px] ${PILL_CLASS[p.kind]}`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Run + Commit**

```bash
cd frontend && npx vitest run tests/unit/components/chat-thread/blocks/ResultCardBlock.test.tsx
git add frontend/app/\(workbench\)/workspaces/\[id\]/components/chat-thread/blocks/ResultCardBlock.tsx \
        frontend/tests/unit/components/chat-thread/blocks/ResultCardBlock.test.tsx
git commit -m "feat(chat-thread): ResultCardBlock renderer with feedback pills"
```

---

## Task 12: `MessageList` + `RunContainer` (folded completed runs)

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/MessageList.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/RunContainer.tsx`
- Test: `frontend/tests/unit/components/chat-thread/MessageList.test.tsx`

- [ ] **Step 1: Test**

```tsx
import { describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MessageList } from "@/app/(workbench)/workspaces/[id]/components/chat-thread/MessageList";

const msgs = [
  { id: "u1", role: "user", run_id: "r1", text: "hi" },
  { id: "a1", role: "agent", run_id: "r1", blocks: [{ kind: "text", content: "好" }] },
  { id: "a2", role: "agent", run_id: "r1", blocks: [{ kind: "result_card", run_id: "r1",
      title: "完成", tldr: "x", findings: [{ id: "1", text: "a" }], links: [],
      feedback: { question: "?", pills: [], allow_free_input: true },
      stats: { duration_ms: 1000, subagents: 1, tokens: 100 } }] },
  { id: "u2", role: "user", run_id: "r2", text: "深入第 1" },
  { id: "a3", role: "agent", run_id: "r2", blocks: [{ kind: "text", content: "好的" }] },
];

describe("MessageList", () => {
  it("groups messages by run_id and folds completed runs", () => {
    render(<MessageList messages={msgs as any} currentRunId="r2" />);
    // r1 is completed → folded by default → text "好" not visible
    expect(screen.queryByText("好")).not.toBeInTheDocument();
    expect(screen.getByText("好的")).toBeInTheDocument();
    // Header for r1 is visible
    expect(screen.getByRole("button", { name: /轮 1/ })).toBeInTheDocument();
  });

  it("clicking a folded run header expands it", () => {
    render(<MessageList messages={msgs as any} currentRunId="r2" />);
    fireEvent.click(screen.getByRole("button", { name: /轮 1/ }));
    expect(screen.getByText("好")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Implement**

```tsx
// frontend/app/(workbench)/workspaces/[id]/components/chat-thread/RunContainer.tsx
"use client";
import { useState } from "react";

export function RunContainer({
  index,
  title,
  isCurrent,
  children,
}: {
  index: number;
  title: string;
  isCurrent: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(isCurrent);

  if (isCurrent) {
    return <div className="space-y-2">{children}</div>;
  }

  return (
    <div className="rounded-lg bg-white/[0.02]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-[12px] opacity-65"
      >
        <span>轮 {index} · {title} ✓</span>
        <span className="opacity-50">{open ? "▾" : "▸"}</span>
      </button>
      {open && <div className="space-y-2 px-3 pb-3">{children}</div>}
    </div>
  );
}
```

```tsx
// frontend/app/(workbench)/workspaces/[id]/components/chat-thread/MessageList.tsx
"use client";
import type { AgentBlock } from "@/lib/api/blocks";
import { isText, isStatusLine, isQuestionCard, isResultCard } from "@/lib/api/blocks";
import { TextBlock } from "./blocks/TextBlock";
import { StatusLineBlock } from "./blocks/StatusLineBlock";
import { QuestionCardBlock } from "./blocks/QuestionCardBlock";
import { ResultCardBlock } from "./blocks/ResultCardBlock";
import { RunContainer } from "./RunContainer";

export interface ChatMessage {
  id: string;
  role: "user" | "agent";
  run_id: string;
  text?: string;
  blocks?: AgentBlock[];
}

function groupByRun(messages: ChatMessage[]): { run_id: string; messages: ChatMessage[] }[] {
  const out: { run_id: string; messages: ChatMessage[] }[] = [];
  for (const m of messages) {
    const last = out[out.length - 1];
    if (last && last.run_id === m.run_id) last.messages.push(m);
    else out.push({ run_id: m.run_id, messages: [m] });
  }
  return out;
}

function renderBlock(b: AgentBlock, key: number) {
  if (isText(b)) return <TextBlock key={key} block={b} />;
  if (isStatusLine(b)) return <StatusLineBlock key={key} block={b} />;
  if (isQuestionCard(b)) return <QuestionCardBlock key={key} block={b} />;
  if (isResultCard(b)) return <ResultCardBlock key={key} block={b} />;
  return null;
}

export function MessageList({
  messages,
  currentRunId,
}: {
  messages: ChatMessage[];
  currentRunId: string | null;
}) {
  const groups = groupByRun(messages);
  return (
    <div className="space-y-4">
      {groups.map((g, i) => {
        const isCurrent = g.run_id === currentRunId;
        const title = (() => {
          const result = g.messages.flatMap((m) => m.blocks ?? []).find(isResultCard);
          if (result) return result.title.replace(/^📑\s*/, "");
          const firstUser = g.messages.find((m) => m.role === "user");
          return firstUser?.text?.slice(0, 24) ?? "运行";
        })();

        return (
          <RunContainer key={g.run_id} index={i + 1} title={title} isCurrent={isCurrent}>
            {g.messages.map((m) => (
              <div key={m.id} className={m.role === "user" ? "flex justify-end" : ""}>
                {m.role === "user" ? (
                  <div className="rounded-2xl rounded-br-sm bg-blue-500/15 px-3 py-2 text-[13px]">{m.text}</div>
                ) : (
                  <div className="max-w-[95%] rounded-2xl rounded-bl-sm bg-white/[0.04] px-3 py-2 space-y-2">
                    {(m.blocks ?? []).map((b, j) => renderBlock(b, j))}
                  </div>
                )}
              </div>
            ))}
          </RunContainer>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: Run + Commit**

```bash
cd frontend && npx vitest run tests/unit/components/chat-thread/
git add frontend/app/\(workbench\)/workspaces/\[id\]/components/chat-thread/MessageList.tsx \
        frontend/app/\(workbench\)/workspaces/\[id\]/components/chat-thread/RunContainer.tsx \
        frontend/tests/unit/components/chat-thread/MessageList.test.tsx
git commit -m "feat(chat-thread): MessageList groups by run; completed runs fold"
```

---

## Task 13: `ChatThread` shell + `EmptyState` + `InputArea` interrupt button

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/ChatThread.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/EmptyState.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/InputArea.tsx`

- [ ] **Step 1: Tests**

```tsx
// frontend/tests/unit/components/chat-thread/ChatThread.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChatThread } from "@/app/(workbench)/workspaces/[id]/components/chat-thread/ChatThread";

describe("ChatThread", () => {
  it("renders EmptyState when no messages", () => {
    render(<ChatThread workspaceId="ws1" messages={[]} currentRunId={null}
                       feature={{ id: "paper_analysis", name: "论文分析", description: "x" } as any}
                       starterPrompts={["a", "b", "c"]} />);
    expect(screen.getByText(/论文分析/)).toBeInTheDocument();
    expect(screen.getByText("a")).toBeInTheDocument();
  });

  it("renders message list when there are messages", () => {
    render(<ChatThread workspaceId="ws1"
                       messages={[{ id: "u", role: "user", run_id: "r1", text: "hi" }] as any}
                       currentRunId="r1"
                       feature={null}
                       starterPrompts={[]} />);
    expect(screen.getByText("hi")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Implement**

```tsx
// frontend/app/(workbench)/workspaces/[id]/components/chat-thread/EmptyState.tsx
"use client";

export function EmptyState({
  feature,
  starterPrompts,
  onPick,
}: {
  feature: { id: string; name: string; description: string } | null;
  starterPrompts: string[];
  onPick?: (text: string) => void;
}) {
  if (!feature) return <div className="p-6 text-[12px] opacity-50">输入开始对话。</div>;
  return (
    <div className="space-y-4 p-6">
      <div>
        <div className="text-[15px] font-semibold">{feature.name}</div>
        <div className="mt-1 text-[12.5px] opacity-65">{feature.description}</div>
      </div>
      {starterPrompts.length > 0 && (
        <div>
          <div className="mb-1.5 text-[10.5px] uppercase tracking-wide opacity-50">想这样开始？</div>
          <div className="space-y-1.5">
            {starterPrompts.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => onPick?.(p)}
                className="block w-full rounded border border-white/10 bg-white/[0.04] px-3 py-2 text-left text-[12.5px] hover:bg-white/[0.07]"
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

```tsx
// frontend/app/(workbench)/workspaces/[id]/components/chat-thread/InputArea.tsx
"use client";
import { useWorkflowStore } from "@/stores/workflow-store";
import { cancelRun } from "@/lib/api/runs";

// NOTE: in Plan 3, the existing WorkspaceThreadComposer is mounted inside.
// For now, a thin shell: text + interrupt button.
export function InputArea({
  workspaceId,
  onSubmit,
}: {
  workspaceId: string;
  onSubmit: (text: string) => void;
}) {
  const currentRunId = useWorkflowStore((s) => s.currentRunId);
  const isPaused = useWorkflowStore((s) => currentRunId ? s.pausedRunIds.has(currentRunId) : false);

  return (
    <div className="border-t border-white/8 p-3">
      {currentRunId && !isPaused && (
        <button
          type="button"
          onClick={() => cancelRun(workspaceId, currentRunId)}
          className="mb-2 rounded border border-red-400/30 bg-red-400/[0.05] px-2 py-1 text-[11px] text-red-300/85"
        >
          中断当前任务
        </button>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const fd = new FormData(e.currentTarget);
          const text = String(fd.get("text") ?? "").trim();
          if (text) onSubmit(text);
          (e.currentTarget as HTMLFormElement).reset();
        }}
      >
        <input
          name="text"
          className="w-full rounded bg-white/[0.04] px-3 py-2 text-[13px] outline-none"
          placeholder={currentRunId ? "或者直接说想法..." : "输入开始对话..."}
          autoComplete="off"
        />
      </form>
    </div>
  );
}
```

```tsx
// frontend/app/(workbench)/workspaces/[id]/components/chat-thread/ChatThread.tsx
"use client";
import type { ChatMessage } from "./MessageList";
import { MessageList } from "./MessageList";
import { EmptyState } from "./EmptyState";
import { InputArea } from "./InputArea";

interface FeatureMeta { id: string; name: string; description: string; }

export function ChatThread({
  workspaceId,
  messages,
  currentRunId,
  feature,
  starterPrompts,
  onSubmit,
}: {
  workspaceId: string;
  messages: ChatMessage[];
  currentRunId: string | null;
  feature: FeatureMeta | null;
  starterPrompts: string[];
  onSubmit?: (text: string) => void;
}) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0
          ? <EmptyState feature={feature} starterPrompts={starterPrompts} onPick={onSubmit} />
          : <MessageList messages={messages} currentRunId={currentRunId} />
        }
      </div>
      <InputArea workspaceId={workspaceId} onSubmit={onSubmit ?? (() => {})} />
    </div>
  );
}
```

- [ ] **Step 3: Run + Commit**

```bash
cd frontend && npx vitest run tests/unit/components/chat-thread/
git add frontend/app/\(workbench\)/workspaces/\[id\]/components/chat-thread/ \
        frontend/tests/unit/components/chat-thread/ChatThread.test.tsx
git commit -m "feat(chat-thread): ChatThread + EmptyState + InputArea with cancel button"
```

---

## Task 14: Auto-scroll & follow-current behavior

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/LiveWorkflowPanel.tsx`
- Test: `frontend/tests/unit/components/live-workflow/LiveWorkflowPanel.test.tsx` (extend)

- [ ] **Step 1: Test**

```tsx
// append to LiveWorkflowPanel.test.tsx
it("auto-scrolls to current phase when followCurrent=true", async () => {
  const scrollSpy = vi.fn();
  Element.prototype.scrollIntoView = scrollSpy;

  useWorkflowStore.setState({
    runs: [{ id: "r1", thread_id: "t", title: "x", phases: [
      { index: 0, name: "p0", subagents: [{ task_id: "a", status: "completed" }] },
      { index: 1, name: "p1", subagents: [{ task_id: "b", status: "running" }] },
    ], status: "running", started_at: "" }],
    currentRunId: "r1",
    followCurrent: true,
  } as any);

  render(<LiveWorkflowPanel workspaceId="ws1" />);
  expect(scrollSpy).toHaveBeenCalled();
});

it("user-scroll up disables followCurrent", async () => {
  useWorkflowStore.setState({
    runs: [{ id: "r1", thread_id: "t", title: "x", phases: [], status: "running", started_at: "" }],
    currentRunId: "r1", followCurrent: true,
  } as any);
  const { container } = render(<LiveWorkflowPanel workspaceId="ws1" />);
  const scroller = container.querySelector(".overflow-y-auto") as HTMLElement;
  fireEvent.scroll(scroller, { target: { scrollTop: 0, scrollHeight: 1000, clientHeight: 200 } });
  expect(useWorkflowStore.getState().followCurrent).toBe(false);
});
```

- [ ] **Step 2: Implement**

In `LiveWorkflowPanel.tsx`, add:

```tsx
import { useEffect, useRef } from "react";

// inside component:
const scrollerRef = useRef<HTMLDivElement>(null);
const followCurrent = useWorkflowStore((s) => s.followCurrent);
const setFollow = useWorkflowStore((s) => s.setFollow);

// Auto-scroll to the running phase's element
useEffect(() => {
  if (!followCurrent || !scrollerRef.current) return;
  const el = scrollerRef.current.querySelector("[data-phase-status='running']");
  el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}, [followCurrent, /* re-trigger on store updates */ runs]);

// On user scroll up, pause follow
function onScroll(ev: React.UIEvent<HTMLDivElement>) {
  const el = ev.currentTarget;
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  if (!atBottom && followCurrent) setFollow(false);
  if (atBottom && !followCurrent) setFollow(true);
}
```

Then attach `ref={scrollerRef}`, `onScroll={onScroll}` on the scroller div.

In `PhaseList.tsx`, add `data-phase-status={status}` on each phase wrapper.

- [ ] **Step 3: Run + Commit**

```bash
cd frontend && npx vitest run tests/unit/components/live-workflow/LiveWorkflowPanel.test.tsx
git add frontend/app/\(workbench\)/workspaces/\[id\]/components/live-workflow/LiveWorkflowPanel.tsx \
        frontend/app/\(workbench\)/workspaces/\[id\]/components/live-workflow/PhaseList.tsx
git commit -m "feat(live-workflow): auto-scroll to running phase + user-scroll pauses follow"
```

---

## Task 15: i18n locale keys for blocks

**Files:**
- Modify: `frontend/locales/cn.json` and `en.json`
- Modify: each block renderer to use `useI18n()` for user-facing strings

- [ ] **Step 1: Add keys**

In `frontend/locales/cn.json`:

```json
{
  "blocks": {
    "subagent_card": {
      "status": {
        "pending": "待启动",
        "running": "运行中",
        "completed": "完成",
        "waiting": "需要你回答",
        "failed": "失败 · 重试",
        "cancelled": "已取消",
        "timed_out": "超时"
      },
      "waiting_pointer": "↩︎ 在 chat 里问了你一个问题"
    },
    "live_workflow": {
      "title": "实时工作台",
      "pause": "在下个安全点暂停",
      "resume": "继续"
    },
    "chat_thread": {
      "input_placeholder_idle": "输入开始对话...",
      "input_placeholder_running": "或者直接说想法...",
      "interrupt": "中断当前任务"
    },
    "question_card": {
      "free_input_hint": "或者直接打字告诉我你的想法。"
    },
    "result_card": {
      "completed_pill": "已完成",
      "tldr_label": "TL;DR：",
      "findings_label": "关键发现"
    },
    "workspace_assets": {
      "header": "📚 文献 · 📦 成果 · 🧠 上下文"
    }
  }
}
```

In `frontend/locales/en.json`, mirror (translate to English).

- [ ] **Step 2: Replace hard-coded strings in renderers**

Locate each hard-coded literal in `SubagentCard.tsx`, `LiveWorkflowPanel.tsx`, `QuestionCardBlock.tsx`, `ResultCardBlock.tsx`, `InputArea.tsx`, `WorkspaceAssets.tsx` — replace with `t("blocks...")`. Pattern:

```tsx
import { useI18n } from "@/hooks/use-i18n";    // existing hook

// inside component:
const { t } = useI18n();
// "运行中" → t("blocks.subagent_card.status.running")
```

- [ ] **Step 3: Run all unit tests; expect pass after the literal-tests are updated**

Update tests that asserted literal strings to use the same `t(key)` call or wrap in matcher.

```bash
cd frontend && npx vitest run
```

- [ ] **Step 4: Commit**

```bash
git add frontend/locales/ frontend/app/\(workbench\)/workspaces/\[id\]/components/ frontend/tests/unit/components/
git commit -m "feat(i18n): wire all new chat blocks through useI18n; add cn/en keys"
```

---

## Task 16: Wire QuestionCard pill click + ResultCard feedback to chat submit

**Files:**
- Modify: `ChatThread.tsx` to plumb `onPillClick` / `onFeedback` through `MessageList` → block renderers
- Test: `frontend/tests/unit/components/chat-thread/ChatThread.test.tsx` (extend)

- [ ] **Step 1: Test**

```tsx
it("clicking a question pill submits its intent as a user message", () => {
  const onSubmit = vi.fn();
  const msgs = [
    { id: "a", role: "agent", run_id: "r1",
      blocks: [{ kind: "question_card", label: "需要你拍", question: "?",
                 pills: [{ label: "选 A", intent: "select-a" }] }] },
  ] as any;
  render(<ChatThread workspaceId="ws1" messages={msgs} currentRunId="r1"
                     feature={null} starterPrompts={[]} onSubmit={onSubmit} />);
  fireEvent.click(screen.getByRole("button", { name: "选 A" }));
  expect(onSubmit).toHaveBeenCalledWith("select-a");
});

it("clicking a result feedback pill submits its intent", () => {
  const onSubmit = vi.fn();
  const msgs = [
    { id: "a", role: "agent", run_id: "r1",
      blocks: [{ kind: "result_card", run_id: "r1", title: "x", tldr: "y",
                 findings: [], links: [],
                 feedback: { question: "?", pills: [
                   { kind: "primary", label: "进入选题", intent: "next" }
                 ], allow_free_input: true },
                 stats: { duration_ms: 1, subagents: 1, tokens: 1 } }] },
  ] as any;
  render(<ChatThread workspaceId="ws1" messages={msgs} currentRunId="r1"
                     feature={null} starterPrompts={[]} onSubmit={onSubmit} />);
  fireEvent.click(screen.getByRole("button", { name: "进入选题" }));
  expect(onSubmit).toHaveBeenCalledWith("next");
});
```

- [ ] **Step 2: Plumb props**

Modify `MessageList` to accept `onSubmit?: (text: string) => void` and pass to `QuestionCardBlock` (`onPillClick={(intent) => onSubmit?.(intent)}`) and `ResultCardBlock` (`onFeedback={(intent) => onSubmit?.(intent)}`). Threaded down from `ChatThread.props.onSubmit`.

- [ ] **Step 3: Run + Commit**

```bash
cd frontend && npx vitest run tests/unit/components/chat-thread/ChatThread.test.tsx
git add frontend/app/\(workbench\)/workspaces/\[id\]/components/chat-thread/MessageList.tsx \
        frontend/app/\(workbench\)/workspaces/\[id\]/components/chat-thread/ChatThread.tsx \
        frontend/tests/unit/components/chat-thread/ChatThread.test.tsx
git commit -m "feat(chat-thread): plumb pill clicks → onSubmit(intent) for re-prompting"
```

---

## Self-Review Checklist

- [ ] **Spec coverage:**
  - §4.1 LiveWorkflowPanel — Tasks 4, 5, 6, 7, 8, 14 ✓
  - §4.2 ChatThread / EmptyState / RunContainer — Tasks 9, 10, 11, 12, 13 ✓
  - §4.3 useWorkflowStore — Task 3 ✓
  - §5.1 AgentBlock TS mirror — Task 1 ✓
  - §5.2 SSE block event consumed — Task 1, 8 ✓
  - §6.1 pause/cancel UI hooks — Tasks 7 (pause btn), 13 (cancel btn) ✓
  - §6.2 deleteRun — Task 2 ✓
  - §8.3 i18n — Task 15 ✓
- [ ] **Placeholder scan** — none ✓
- [ ] **Type consistency:** `Run` / `PhaseSnap` / `SubagentSnap` types defined in Task 3 are used identically across Tasks 4-8, 12. `AgentBlock` from Task 1 used in Tasks 9-12, 16.

