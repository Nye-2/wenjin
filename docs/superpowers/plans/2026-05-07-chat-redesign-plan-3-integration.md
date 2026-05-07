# Chat Redesign · Plan 3: Integration + E2E + Legacy Cleanup

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Plan 1 (backend) and Plan 2 (frontend) into the live `/workspaces/[id]/chat` route — full URL-param flow, mount real `ArtifactLibrary` / `LiteraturePanel` / `KnowledgePanel` inside `WorkspaceAssets`, write Playwright e2e covering all spec §12 acceptance criteria, then delete every legacy file. Clean break, no fallback.

**Architecture:** The chat page becomes thin: it parses URL params, reads feature/skill metadata from the existing `useFeaturesStore`, and mounts `<ChatThread/>` (left) + `<LiveWorkflowPanel/>` (right). All `useExecutionStore` consumers migrate to `useWorkflowStore`. Playwright drives the dev backend with a stubbed LLM and asserts every spec §12 line.

**Tech Stack:** Playwright (new dev dep), Next.js 16, vitest, plus Plan 1/2 stack.

**Reference spec:** [docs/superpowers/specs/2026-05-07-chat-experience-redesign-design.md](../specs/2026-05-07-chat-experience-redesign-design.md). Section numbers below refer to that spec.

**Depends on:** Plan 1 + Plan 2 merged.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `frontend/playwright.config.ts` | **create** | Playwright config |
| `frontend/tests/e2e/fixtures/scripted-llm.ts` | **create** | Mock-LLM injection helper for backend |
| `frontend/tests/e2e/golden-path.spec.ts` | **create** | Spec §12 happy path |
| `frontend/tests/e2e/pause-resume.spec.ts` | **create** | Spec §12 pause |
| `frontend/tests/e2e/error-severity.spec.ts` | **create** | Spec §12 errors |
| `frontend/tests/e2e/iteration.spec.ts` | **create** | Spec §12 feedback → new run |
| `frontend/app/(workbench)/workspaces/[id]/chat/page.tsx` | **rewrite** | Mount new components, parse entrySeed |
| `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/WorkspaceAssets.tsx` | modify | Mount `ArtifactLibrary` / `LiteraturePanel` / `KnowledgePanel` |
| `frontend/app/(workbench)/workspaces/[id]/layout.tsx` | modify | Replace `useExecutionStore.hydrateWorkspace` with `useWorkflowStore` equivalents |
| `frontend/app/(workbench)/workspaces/[id]/page.tsx` | modify | Drop `useExecutionStore` consumption (or migrate to workflow store) |
| `frontend/lib/workspace-thread-entry.ts` | modify | Ensure entrySeed has `params.sourceArtifactId` field (spec §7) |
| `backend/src/agents/lead_agent/agent.py` | modify | Ingest `entrySeed` into the system context for the first turn |
| (delete) `frontend/app/(workbench)/workspaces/[id]/components/WorkspaceInspector.tsx` | **delete** | Replaced |
| (delete) `frontend/app/(workbench)/workspaces/[id]/components/ComputeStage.tsx` | **delete** | Replaced |
| (delete) `frontend/app/(workbench)/workspaces/[id]/components/KnowledgePanel.tsx` | **delete** (old container — sub-component reused by name) | See task 10 note |
| (delete) `frontend/app/(workbench)/workspaces/[id]/components/ThreadPanel.tsx` | **delete** | Replaced by `ChatThread` |
| (delete) `frontend/app/(workbench)/workspaces/[id]/components/WorkspaceThreadMessages.tsx` | **delete** | Replaced |
| (delete) `frontend/app/(workbench)/workspaces/[id]/components/thread-blocks/*` | **delete** | All 8 historical block files |
| (delete) `frontend/stores/execution.ts` | **delete** | Replaced by workflow-store |
| (delete) `backend/src/runtime/runs/worker.py` `assistant_message` SSE branch | **delete** | Already removed in Plan 1 Task 7 — verify here |

---

## Task 1: Set up Playwright

**Files:**
- Modify: `frontend/package.json` — add `@playwright/test` dev dep
- Create: `frontend/playwright.config.ts`
- Create: `frontend/tests/e2e/.gitkeep`

- [ ] **Step 1: Install**

```bash
cd frontend && npm install --save-dev @playwright/test
cd frontend && npx playwright install chromium
```

- [ ] **Step 2: Create config**

```ts
// frontend/playwright.config.ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  fullyParallel: false,
  retries: 0,
  workers: 1,
  use: {
    baseURL: "http://localhost:3001",
    trace: "on-first-retry",
    actionTimeout: 5_000,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    command: "npm run dev -- --port 3001",
    url: "http://localhost:3001",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
```

- [ ] **Step 3: Add npm script**

In `frontend/package.json`, add:

```json
{
  "scripts": {
    "test:e2e": "playwright test"
  }
}
```

- [ ] **Step 4: Verify**

```bash
cd frontend && npx playwright test --list
```
Expected: lists 0 tests (none yet) — exits 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/playwright.config.ts frontend/package.json frontend/package-lock.json frontend/tests/e2e/.gitkeep
git commit -m "chore(frontend): add Playwright for e2e tests"
```

---

## Task 2: Scripted-LLM fixture for e2e

> Backend already has a fixture pattern from Plan 1 Task 16 (`scripted_llm`). For e2e, expose a dev-only HTTP endpoint that lets the test queue scripted `AgentMessage` payloads.

**Files:**
- Create: `backend/src/gateway/routers/dev_test_hooks.py`
- Create: `frontend/tests/e2e/fixtures/scripted-llm.ts`
- Modify: `backend/src/gateway/app.py` — mount the dev router only in dev mode

- [ ] **Step 1: Backend dev hook**

```python
# backend/src/gateway/routers/dev_test_hooks.py
"""Dev-only endpoint for queueing scripted LLM responses during e2e.

Disabled in production (mounted only when settings.env == "dev").
"""
from collections import deque
from fastapi import APIRouter
from pydantic import BaseModel

from src.agents.lead_agent.blocks import AgentMessage

router = APIRouter(prefix="/__test__", tags=["dev"])

_queue: deque[AgentMessage] = deque()


class QueueIn(BaseModel):
    messages: list[AgentMessage]


@router.post("/llm/queue", status_code=204)
async def queue_llm_responses(payload: QueueIn) -> None:
    _queue.extend(payload.messages)


@router.post("/llm/clear", status_code=204)
async def clear_llm() -> None:
    _queue.clear()


def pop_next() -> AgentMessage | None:
    return _queue.popleft() if _queue else None
```

In `backend/src/gateway/app.py`:

```python
from src.gateway.routers import dev_test_hooks
if settings.env == "dev":
    app.include_router(dev_test_hooks.router)
```

In the structured-output path (where `parse_with_fallback` is called from `agent.py`), add a dev branch:

```python
if settings.env == "dev":
    from src.gateway.routers.dev_test_hooks import pop_next
    queued = pop_next()
    if queued is not None:
        return queued   # short-circuit, never call real LLM
```

- [ ] **Step 2: Frontend fixture**

```ts
// frontend/tests/e2e/fixtures/scripted-llm.ts
import type { Page } from "@playwright/test";

const BACKEND = process.env.WENJIN_BACKEND_URL ?? "http://localhost:8000";

interface AgentMessageJSON { blocks: Array<Record<string, unknown>>; }

export async function queueLLM(messages: AgentMessageJSON[]): Promise<void> {
  const r = await fetch(`${BACKEND}/__test__/llm/queue`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  if (!r.ok) throw new Error(`queueLLM failed: ${r.status}`);
}

export async function clearLLM(): Promise<void> {
  await fetch(`${BACKEND}/__test__/llm/clear`, { method: "POST" });
}

export async function setupCleanWorkspace(page: Page): Promise<{ workspaceId: string }> {
  // Hit a dev endpoint to mint a workspace; spec §12 baseline.
  const r = await fetch(`${BACKEND}/__test__/workspaces`, { method: "POST" });
  const { workspace_id } = await r.json();
  return { workspaceId: workspace_id };
}
```

> If `__test__/workspaces` doesn't exist, add it to `dev_test_hooks.py` similarly — minting a fresh workspace + first thread for the test.

- [ ] **Step 3: Commit**

```bash
git add backend/src/gateway/routers/dev_test_hooks.py backend/src/gateway/app.py \
        backend/src/agents/lead_agent/agent.py \
        frontend/tests/e2e/fixtures/scripted-llm.ts
git commit -m "feat(dev): scripted-LLM hook for Playwright e2e"
```

---

## Task 3: Wire entrySeed (URL params) into backend first-turn context

> Spec §7. The frontend already parses URL into `entrySeed` via `parseWorkspaceThreadEntrySeed()`. We pass it to the backend on thread create/resume, and the agent uses it as system context. No first-turn user message is auto-fabricated; the agent simply has the seed in its context.

**Files:**
- Modify: `frontend/lib/workspace-thread-entry.ts` — ensure `entrySeed.params.sourceArtifactId` is named exactly that
- Modify: `frontend/lib/api/thread.ts` (or equivalent) — POST entrySeed on thread create
- Modify: `backend/src/agents/lead_agent/agent.py` — read entrySeed from thread metadata + inject

- [ ] **Step 1: Test (frontend unit)**

```ts
// frontend/tests/unit/lib/workspace-thread-entry.test.ts (extend)
it("parses source_artifact_id into params.sourceArtifactId", () => {
  const seed = parseWorkspaceThreadEntrySeed(new URLSearchParams({
    feature: "paper_analysis",
    source_artifact_id: "art-1",
    paper_title: "x",
  }));
  expect(seed.featureId).toBe("paper_analysis");
  expect(seed.params.sourceArtifactId).toBe("art-1");
  expect(seed.params.paperTitle).toBe("x");
});
```

- [ ] **Step 2: Implement in frontend**

In `frontend/lib/workspace-thread-entry.ts`, ensure `parseWorkspaceThreadEntrySeed` populates `params.sourceArtifactId`, `params.paperTitle`, `params.paperAbstract` from the URL.

```ts
// snippet — within the existing parser
const params: Record<string, string> = {};
if (sp.get("source_artifact_id")) params.sourceArtifactId = sp.get("source_artifact_id")!;
if (sp.get("paper_title")) params.paperTitle = sp.get("paper_title")!;
if (sp.get("paper_abstract")) params.paperAbstract = sp.get("paper_abstract")!;
return { featureId, skillId, params, entry, onboarding };
```

In `frontend/lib/api/thread.ts` (or wherever thread creation lives), include `entrySeed` in the create payload:

```ts
export async function createThread(opts: { workspaceId: string; entrySeed: EntrySeed }) {
  const r = await fetch(`/api/workspaces/${opts.workspaceId}/threads`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ entry_seed: opts.entrySeed }),
  });
  if (!r.ok) throw new Error(`createThread failed: ${r.status}`);
  return r.json();
}
```

- [ ] **Step 3: Backend — read entrySeed from thread metadata**

In `backend/src/agents/lead_agent/agent.py`, when composing the system message:

```python
def _maybe_entry_seed_block(entry_seed: dict | None) -> str:
    if not entry_seed:
        return ""
    parts = []
    if (sa := entry_seed.get("params", {}).get("sourceArtifactId")):
        # Fetch the artifact body and inject (avoid restating to user)
        body = artifact_loader.fetch_text(sa)
        if body:
            parts.append(f"# 用户上下文（来自 artifact {sa}）\n{body}")
    if (pt := entry_seed.get("params", {}).get("paperTitle")):
        parts.append(f"# 论文标题\n{pt}")
    if (pa := entry_seed.get("params", {}).get("paperAbstract")):
        parts.append(f"# 论文摘要\n{pa}")
    return "\n\n".join(parts)

# When building the prompt:
sys = _build_system_prompt(workspace_type, skill_id)
seed_block = _maybe_entry_seed_block(thread.entry_seed)
composed = [
    {"role": "system", "content": f"{sys}\n\n{seed_block}".strip()},
    *messages,
]
```

- [ ] **Step 4: Test backend behavior**

```python
# backend/tests/agents/lead_agent/test_entry_seed.py
"""Spec §7 — entrySeed lands in system context, not as a user message."""
import pytest

@pytest.mark.asyncio
async def test_source_artifact_injected_as_system_context(make_lead_agent, captured_prompt):
    seed = {"featureId": "paper_analysis", "params": {"sourceArtifactId": "art-1"}}
    agent = make_lead_agent(workspace_type="sci", entry_seed=seed)
    await agent.handle_user_message("hi")
    sys_msg = next(m for m in captured_prompt if m["role"] == "system")
    assert "art-1" in sys_msg["content"] or "用户上下文" in sys_msg["content"]


@pytest.mark.asyncio
async def test_no_synthetic_user_message_for_resume(make_lead_agent, captured_prompt):
    seed = {"entry": "resume"}
    agent = make_lead_agent(workspace_type="sci", entry_seed=seed)
    # On resume, agent does not fabricate a user message
    n_user = sum(1 for m in captured_prompt if m["role"] == "user")
    assert n_user == 0
```

- [ ] **Step 5: Run + Commit**

```bash
cd backend && uv run pytest tests/agents/lead_agent/test_entry_seed.py -v
cd frontend && npx vitest run tests/unit/lib/workspace-thread-entry.test.ts
git add backend/src/agents/lead_agent/agent.py backend/tests/agents/lead_agent/test_entry_seed.py \
        frontend/lib/workspace-thread-entry.ts frontend/lib/api/thread.ts \
        frontend/tests/unit/lib/workspace-thread-entry.test.ts
git commit -m "feat(entry-seed): pass URL params through to lead_agent system context"
```

---

## Task 4: Mount real `ArtifactLibrary` / `LiteraturePanel` / `KnowledgePanel` into `WorkspaceAssets`

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/WorkspaceAssets.tsx`
- Modify: existing `ArtifactLibrary.tsx`, `LiteraturePanel.tsx`, `KnowledgePanel.tsx` — they currently live as siblings of `WorkspaceInspector.tsx`. Move them into the `live-workflow/assets/` subfolder OR keep in place and just re-import.
- Test: `frontend/tests/unit/components/live-workflow/WorkspaceAssets.test.tsx` (new)

- [ ] **Step 1: Test**

```tsx
// frontend/tests/unit/components/live-workflow/WorkspaceAssets.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { WorkspaceAssets } from "@/app/(workbench)/workspaces/[id]/components/live-workflow/WorkspaceAssets";

describe("WorkspaceAssets", () => {
  it("starts collapsed when defaultOpen=false", () => {
    render(<WorkspaceAssets workspaceId="ws1" defaultOpen={false} />);
    expect(screen.queryByRole("tab", { name: /成果/ })).not.toBeInTheDocument();
  });

  it("opens and shows 3 tabs when expanded", () => {
    render(<WorkspaceAssets workspaceId="ws1" defaultOpen={true} />);
    expect(screen.getByRole("tab", { name: /成果/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /文献/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /上下文/ })).toBeInTheDocument();
  });

  it("switches active tab on click", () => {
    render(<WorkspaceAssets workspaceId="ws1" defaultOpen={true} />);
    fireEvent.click(screen.getByRole("tab", { name: /文献/ }));
    expect(screen.getByRole("tab", { name: /文献/ })).toHaveAttribute("aria-selected", "true");
  });
});
```

- [ ] **Step 2: Implement**

```tsx
// frontend/app/(workbench)/workspaces/[id]/components/live-workflow/WorkspaceAssets.tsx
"use client";
import { useState } from "react";
import { ArtifactLibrary } from "../ArtifactLibrary";       // keep import path
import { LiteraturePanel } from "../LiteraturePanel";
import { KnowledgePanel } from "../KnowledgePanel";
import { useI18n } from "@/hooks/use-i18n";

type Tab = "artifacts" | "literature" | "knowledge";

export function WorkspaceAssets({
  workspaceId,
  defaultOpen,
}: {
  workspaceId: string;
  defaultOpen: boolean;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(defaultOpen);
  const [tab, setTab] = useState<Tab>("artifacts");

  return (
    <div data-testid="workspace-assets" className="rounded-lg bg-white/[0.02] mt-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2 text-[12px]"
      >
        <span>{t("blocks.workspace_assets.header")}</span>
        <span className="opacity-50">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <>
          <div role="tablist" className="flex gap-2 border-b border-white/10 px-3 pt-1">
            {(["artifacts", "literature", "knowledge"] as Tab[]).map((id) => (
              <button
                key={id}
                role="tab"
                aria-selected={tab === id}
                onClick={() => setTab(id)}
                className={`pb-1.5 text-[11.5px] ${tab === id ? "border-b border-white" : "opacity-60"}`}
              >
                {t(`blocks.workspace_assets.tab_${id}`)}
              </button>
            ))}
          </div>
          <div className="px-3 py-3">
            {tab === "artifacts" && <ArtifactLibrary workspaceId={workspaceId} />}
            {tab === "literature" && <LiteraturePanel workspaceId={workspaceId} />}
            {tab === "knowledge" && <KnowledgePanel workspaceId={workspaceId} />}
          </div>
        </>
      )}
    </div>
  );
}
```

Add tab labels to `frontend/locales/cn.json`:

```json
"workspace_assets": {
  "header": "📚 文献 · 📦 成果 · 🧠 上下文",
  "tab_artifacts": "成果",
  "tab_literature": "文献",
  "tab_knowledge": "上下文"
}
```

- [ ] **Step 3: Verify the existing components accept `workspaceId` prop**

If they previously took different props (e.g., consumed via context), add a `workspaceId` prop pass-through. Keep this minimal — do not refactor the children themselves.

- [ ] **Step 4: Run + Commit**

```bash
cd frontend && npx vitest run tests/unit/components/live-workflow/WorkspaceAssets.test.tsx
git add frontend/app/\(workbench\)/workspaces/\[id\]/components/live-workflow/WorkspaceAssets.tsx \
        frontend/tests/unit/components/live-workflow/WorkspaceAssets.test.tsx \
        frontend/locales/
git commit -m "feat(live-workflow): mount real ArtifactLibrary/LiteraturePanel/KnowledgePanel inside WorkspaceAssets"
```

---

## Task 5: Rewrite chat page entry (mount new components)

**Files:**
- Rewrite: `frontend/app/(workbench)/workspaces/[id]/chat/page.tsx`
- Test: `frontend/tests/unit/components/chat/page.test.tsx` (new) + e2e covers the rest

- [ ] **Step 1: Rewrite the page**

```tsx
// frontend/app/(workbench)/workspaces/[id]/chat/page.tsx
"use client";
import { useEffect, useMemo } from "react";
import { useParams, useSearchParams } from "next/navigation";

import { ChatThread } from "../components/chat-thread/ChatThread";
import { LiveWorkflowPanel } from "../components/live-workflow/LiveWorkflowPanel";
import { useWorkflowSubscription } from "../components/live-workflow/useWorkflowSubscription";
import { parseWorkspaceThreadEntrySeed } from "@/lib/workspace-thread-entry";
import { useFeaturesStore } from "@/stores/features";
import { useThreadStore } from "@/stores/thread";

export default function ChatPage() {
  const { id } = useParams<{ id: string }>();
  const sp = useSearchParams();
  const entrySeed = useMemo(() => parseWorkspaceThreadEntrySeed(new URLSearchParams(sp.toString())), [sp]);

  const features = useFeaturesStore((s) => s.features);
  const skills = useFeaturesStore((s) => s.skills);
  const messages = useThreadStore((s) => s.messages);
  const currentRunId = useThreadStore((s) => s.currentRunId);
  const submitMessage = useThreadStore((s) => s.submit);

  useWorkflowSubscription(id);

  // First-turn auto-send
  useEffect(() => {
    if (entrySeed.entry === "open" && messages.length === 0) {
      submitMessage({ entrySeed, workspaceId: id });
    }
    // resume / onboarding: do not auto-send
  }, [entrySeed, id, messages.length, submitMessage]);

  const feature = features.find((f) => f.id === entrySeed.featureId) ?? null;
  const starter = feature ? deriveStarterPrompts(feature, skills, entrySeed.skillId) : [];

  return (
    <div className="grid h-full grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(430px,520px)]">
      <ChatThread
        workspaceId={id}
        messages={messages}
        currentRunId={currentRunId}
        feature={feature}
        starterPrompts={starter}
        onSubmit={(text) => submitMessage({ text, workspaceId: id })}
      />
      <LiveWorkflowPanel workspaceId={id} />
    </div>
  );
}

function deriveStarterPrompts(feature: any, skills: any[], skillId?: string): string[] {
  // 3 starters from feature.guidancePrompt or skill.guidancePrompt header.
  const skill = skillId ? skills.find((s) => s.id === skillId) : null;
  const src: string = (skill?.guidancePrompt ?? feature?.followUpPrompt ?? "") as string;
  return src.split(/\n+/).filter((l) => l.startsWith("- ") || l.startsWith("• ")).slice(0, 3).map((l) => l.replace(/^[-•]\s+/, ""));
}
```

> Adjust `useThreadStore.submit` signature to match what your existing thread store expects. If `useThreadStore` doesn't exist in this exact shape, identify the existing thread/message store and adapt — the goal is one `submit(text)` function that posts the user message and triggers the agent.

- [ ] **Step 2: Smoke test**

```tsx
// frontend/tests/unit/components/chat/page.test.tsx
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
// Use Next.js router mocks; if your project already provides a helper for testing pages, use that.
```

> Page-level rendering tests are fragile under Next 16 RSC; the substantive test is the e2e in Tasks 6-9. Keep the unit test minimal (just verify the page imports and exports a default function).

- [ ] **Step 3: Commit**

```bash
git add frontend/app/\(workbench\)/workspaces/\[id\]/chat/page.tsx
git commit -m "refactor(chat): rewrite chat page to mount ChatThread + LiveWorkflowPanel"
```

---

## Task 6: Migrate `useExecutionStore` consumers to `useWorkflowStore`

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/layout.tsx:35-36`
- Modify: `frontend/app/(workbench)/workspaces/[id]/page.tsx:24, 301`

> Targets: 5 files. Plan 2 already migrated chat-related ones. The remaining are workspace-overview consumers. They likely tracked active executions for non-chat views — replace with `useWorkflowStore.runs`.

- [ ] **Step 1: Audit**

```bash
cd frontend && grep -rn "useExecutionStore" --include="*.tsx" --include="*.ts" | grep -v node_modules | grep -v test
```

For each hit, identify what data is read and decide:
- If it's "current execution session" → replace with `useWorkflowStore((s) => s.runs.find((r) => r.id === s.currentRunId))`
- If it's "list of dismissed execution IDs" → if no longer needed, drop
- If it's hydration calls (`hydrateWorkspace`) → replace with no-op or workflow-store equivalent (the new store doesn't need hydration; SSE feeds it)

- [ ] **Step 2: Migrate `layout.tsx`**

```tsx
// remove
import { useExecutionStore } from "@/stores/execution";
const hydrateExecutions = useExecutionStore((s) => s.hydrateWorkspace);
const clearExecutions = useExecutionStore((s) => s.clearWorkspace);
useEffect(() => { hydrateExecutions(workspaceId); return () => clearExecutions(workspaceId); }, ...);

// nothing replaces this — workflow-store doesn't need explicit hydration
```

Just delete the calls. The test of correctness: workspace pages still load.

- [ ] **Step 3: Migrate `page.tsx`** (workspace overview, NOT chat)

The `executionSessions` list at line 301 is used for surface-level summary. Replace with:

```tsx
import { useWorkflowStore } from "@/stores/workflow-store";
const recentRuns = useWorkflowStore((s) => s.runs.slice(-3));
// adjust the JSX consuming this list to use Run shape
```

- [ ] **Step 4: Run all tests**

```bash
cd frontend && npx vitest run
```
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/\(workbench\)/workspaces/\[id\]/layout.tsx \
        frontend/app/\(workbench\)/workspaces/\[id\]/page.tsx
git commit -m "refactor(workspace): migrate non-chat useExecutionStore consumers to workflow-store"
```

---

## Task 7: Playwright e2e — golden path

**Files:**
- Create: `frontend/tests/e2e/golden-path.spec.ts`

Spec §12 verifies: agent emits clean blocks, phase transitions surface as status_lines, result_card appears with TL;DR + findings + recommend + feedback.

- [ ] **Step 1: Write the test**

```ts
// frontend/tests/e2e/golden-path.spec.ts
import { test, expect } from "@playwright/test";
import { clearLLM, queueLLM, setupCleanWorkspace } from "./fixtures/scripted-llm";

test("paper analysis golden path", async ({ page }) => {
  const { workspaceId } = await setupCleanWorkspace(page);
  await clearLLM();

  // Script the agent's responses for a single full run.
  await queueLLM([
    { blocks: [
      { kind: "text", content: "好，方向挺新。我先去扫这个交叉的文献版图。" },
      { kind: "status_line", label: "启动 phase 1 · 检索文献", run_id: "r1", phase_index: 0, tone: "info" },
    ]},
    { blocks: [
      { kind: "status_line", label: "phase 1 完成 · 12 篇高相关 → 启动 phase 2", run_id: "r1", phase_index: 1, tone: "info" },
    ]},
    { blocks: [
      { kind: "status_line", label: "phase 2 完成 → 启动 phase 3 · 提炼", run_id: "r1", phase_index: 2, tone: "info" },
    ]},
    { blocks: [
      { kind: "status_line", label: "正在汇总结果（约 10-20s）", run_id: "r1", tone: "info" },
      { kind: "result_card", run_id: "r1", title: "📑 论文分析 · 完成", tldr: "3 个角度可切，最有价值是通信效率 ↔ 隐私强度",
        findings: [
          { id: "1", text: "异构客户端缺口" },
          { id: "2", text: "联邦预训练 vs 联邦微调供需错位" },
          { id: "3", text: "trade-off 量化空白" },
        ],
        recommend: { label: "推荐切入", body: "三维 trade-off 曲线" },
        links: [{ icon: "📄", label: "详细报告", href: "#" }],
        feedback: { question: "这个结论你怎么看？", pills: [
          { kind: "primary", label: "进入选题", intent: "next" },
          { kind: "warn", label: "换方向", intent: "redirect" },
        ], allow_free_input: true },
        stats: { duration_ms: 102000, subagents: 13, tokens: 8400 },
      },
    ]},
  ]);

  await page.goto(`/workspaces/${workspaceId}/chat?feature=paper_analysis&skill=paper-analyst&entry=open&paper_title=${encodeURIComponent("联邦学习+大模型")}`);

  // First text bubble appears
  await expect(page.getByText(/方向挺新/)).toBeVisible();

  // Status lines appear in chat for each phase
  await expect(page.getByText(/phase 1 完成/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/phase 2 完成/)).toBeVisible();
  await expect(page.getByText(/正在汇总结果/)).toBeVisible();

  // Result card with TL;DR + findings + recommend + feedback
  await expect(page.getByText(/3 个角度可切/)).toBeVisible();
  await expect(page.getByText(/异构客户端缺口/)).toBeVisible();
  await expect(page.getByText(/推荐切入/)).toBeVisible();
  await expect(page.getByRole("button", { name: /进入选题/ })).toBeVisible();

  // No jargon / debug tokens leaked
  for (const t of ["message_feature_proposal", "意图置信度", "我会先复用"]) {
    await expect(page.getByText(t)).toHaveCount(0);
  }

  // Right panel shows phase progression
  await expect(page.getByTestId("phase-header-0")).toBeVisible();
  await expect(page.getByTestId("phase-header-1")).toBeVisible();
  await expect(page.getByTestId("phase-header-2")).toBeVisible();
});
```

- [ ] **Step 2: Run, fix until green**

```bash
cd frontend && npx playwright test golden-path.spec.ts
```

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/e2e/golden-path.spec.ts
git commit -m "test(e2e): paper analysis golden path — blocks, status, result, no jargon"
```

---

## Task 8: Playwright e2e — pause / resume / cancel

**Files:**
- Create: `frontend/tests/e2e/pause-resume.spec.ts`

- [ ] **Step 1: Test**

```ts
// frontend/tests/e2e/pause-resume.spec.ts
import { test, expect } from "@playwright/test";
import { clearLLM, queueLLM, setupCleanWorkspace } from "./fixtures/scripted-llm";

test("pause stops at next phase boundary; resume continues", async ({ page }) => {
  const { workspaceId } = await setupCleanWorkspace(page);
  await clearLLM();
  await queueLLM([
    { blocks: [
      { kind: "text", content: "开始" },
      { kind: "status_line", label: "phase 1 启动", run_id: "r1", phase_index: 0, tone: "info" },
    ]},
    { blocks: [
      { kind: "status_line", label: "phase 1 完成", run_id: "r1", phase_index: 1, tone: "info" },
    ]},
    // phase 2 will only be appended after resume
  ]);

  await page.goto(`/workspaces/${workspaceId}/chat?feature=paper_analysis&skill=paper-analyst&entry=open&paper_title=x`);
  await expect(page.getByText(/phase 1 启动/)).toBeVisible();

  // Click pause
  await page.getByRole("button", { name: /在下个安全点暂停/ }).click();
  await expect(page.getByRole("button", { name: /继续/ })).toBeVisible();

  // Queue phase 2 result, click resume
  await queueLLM([{ blocks: [{ kind: "status_line", label: "phase 2 完成", run_id: "r1", phase_index: 2, tone: "info" }] }]);
  await page.getByRole("button", { name: /继续/ }).click();
  await expect(page.getByText(/phase 2 完成/)).toBeVisible({ timeout: 5000 });
});

test("cancel mid-run stops execution and returns to idle composer", async ({ page }) => {
  const { workspaceId } = await setupCleanWorkspace(page);
  await clearLLM();
  await queueLLM([{ blocks: [
    { kind: "text", content: "正在跑" },
    { kind: "status_line", label: "phase 1 启动", run_id: "r1", phase_index: 0, tone: "info" },
  ]}]);

  await page.goto(`/workspaces/${workspaceId}/chat?feature=paper_analysis&skill=paper-analyst&entry=open&paper_title=x`);
  await expect(page.getByText(/正在跑/)).toBeVisible();
  await page.getByRole("button", { name: /中断当前任务/ }).click();
  await expect(page.getByRole("button", { name: /中断当前任务/ })).toHaveCount(0);
});
```

- [ ] **Step 2: Run + Commit**

```bash
cd frontend && npx playwright test pause-resume.spec.ts
git add frontend/tests/e2e/pause-resume.spec.ts
git commit -m "test(e2e): pause/resume at phase boundary; cancel terminates run"
```

---

## Task 9: Playwright e2e — error severity

**Files:**
- Create: `frontend/tests/e2e/error-severity.spec.ts`

- [ ] **Step 1: Test**

```ts
// frontend/tests/e2e/error-severity.spec.ts
import { test, expect } from "@playwright/test";
import { clearLLM, queueLLM, setupCleanWorkspace } from "./fixtures/scripted-llm";

test("low-severity subagent failure surfaces as warn status_line, run continues", async ({ page }) => {
  const { workspaceId } = await setupCleanWorkspace(page);
  await clearLLM();
  await queueLLM([
    { blocks: [
      { kind: "status_line", label: "phase 2 启动", run_id: "r1", phase_index: 1, tone: "info" },
      { kind: "status_line", label: "phase 2 有 1 篇文献无法解析，已跳过", run_id: "r1", phase_index: 1, tone: "warn" },
      { kind: "status_line", label: "phase 2 完成", run_id: "r1", phase_index: 2, tone: "info" },
    ]},
  ]);

  await page.goto(`/workspaces/${workspaceId}/chat?feature=paper_analysis&skill=paper-analyst&entry=open&paper_title=x`);
  await expect(page.getByText(/已跳过/)).toBeVisible();
  await expect(page.getByText(/phase 2 完成/)).toBeVisible();
  // Run not paused
  await expect(page.getByRole("button", { name: /继续/ })).toHaveCount(0);
});

test("high-severity failure pauses run with question_card asking how to proceed", async ({ page }) => {
  const { workspaceId } = await setupCleanWorkspace(page);
  await clearLLM();
  await queueLLM([
    { blocks: [
      { kind: "status_line", label: "phase 2 启动", run_id: "r1", phase_index: 1, tone: "info" },
      { kind: "question_card", label: "需要你拍一下", question: "无法解析 PrivateFL-GPT，要继续不读它，还是手动给我 PDF？",
        pills: [
          { label: "跳过这篇", intent: "skip" },
          { label: "换一篇", intent: "swap" },
          { label: "上传 PDF", intent: "upload" },
        ] },
    ]},
  ]);

  await page.goto(`/workspaces/${workspaceId}/chat?feature=paper_analysis&skill=paper-analyst&entry=open&paper_title=x`);
  await expect(page.getByText(/无法解析/)).toBeVisible();
  await expect(page.getByRole("button", { name: /跳过这篇/ })).toBeVisible();
  // Run paused — resume button visible OR pause flag set in store
  await expect(page.getByRole("button", { name: /继续|在下个安全点暂停/ })).toBeVisible();
});
```

- [ ] **Step 2: Run + Commit**

```bash
cd frontend && npx playwright test error-severity.spec.ts
git add frontend/tests/e2e/error-severity.spec.ts
git commit -m "test(e2e): error severity — low warns silently, high pauses with question"
```

---

## Task 10: Playwright e2e — feedback iteration creates new run

**Files:**
- Create: `frontend/tests/e2e/iteration.spec.ts`

- [ ] **Step 1: Test**

```ts
// frontend/tests/e2e/iteration.spec.ts
import { test, expect } from "@playwright/test";
import { clearLLM, queueLLM, setupCleanWorkspace } from "./fixtures/scripted-llm";

test("clicking a result_card pill triggers new run; previous run folds", async ({ page }) => {
  const { workspaceId } = await setupCleanWorkspace(page);
  await clearLLM();
  await queueLLM([
    { blocks: [
      { kind: "text", content: "开始" },
      { kind: "result_card", run_id: "r1", title: "📑 完成", tldr: "x",
        findings: [{ id: "1", text: "a" }],
        links: [],
        feedback: { question: "下一步？", pills: [
          { kind: "normal", label: "深入第 ① 点", intent: "deep-dive-1" },
        ], allow_free_input: true },
        stats: { duration_ms: 1000, subagents: 1, tokens: 100 },
      },
    ]},
  ]);

  await page.goto(`/workspaces/${workspaceId}/chat?feature=paper_analysis&skill=paper-analyst&entry=open&paper_title=x`);
  await expect(page.getByText(/x/)).toBeVisible();

  // Queue the second run BEFORE clicking
  await queueLLM([
    { blocks: [
      { kind: "text", content: "好，深入分析中…" },
      { kind: "status_line", label: "phase 1 启动", run_id: "r2", phase_index: 0, tone: "info" },
    ]},
  ]);

  await page.getByRole("button", { name: /深入第 ① 点/ }).click();

  // New run starts
  await expect(page.getByText(/深入分析中/)).toBeVisible();

  // Old run folded — its result_card text not visible (in a folded RunContainer)
  await expect(page.getByRole("button", { name: /轮 1/ })).toBeVisible();
  await expect(page.getByText(/开始/).first()).not.toBeVisible();

  // Expanding it shows the old content again
  await page.getByRole("button", { name: /轮 1/ }).click();
  await expect(page.getByText(/开始/)).toBeVisible();
});
```

- [ ] **Step 2: Run + Commit**

```bash
cd frontend && npx playwright test iteration.spec.ts
git add frontend/tests/e2e/iteration.spec.ts
git commit -m "test(e2e): pill-feedback creates new run; previous run folds"
```

---

## Task 11: Delete legacy code (verified by passing test suite)

**Files (delete):**
- `frontend/app/(workbench)/workspaces/[id]/components/WorkspaceInspector.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/ComputeStage.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/ThreadPanel.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/WorkspaceThreadMessages.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/thread-blocks/` (entire dir, 8 .tsx files + index.ts + shared.tsx)
- `frontend/stores/execution.ts`

**Note:** `ArtifactLibrary.tsx`, `LiteraturePanel.tsx`, `KnowledgePanel.tsx`, `WorkspaceThreadComposer.tsx` are **kept** — they're consumed by Plan 2 / Task 4 above.

- [ ] **Step 1: Verify nothing remaining imports the to-be-deleted files**

```bash
cd frontend
grep -rn "WorkspaceInspector\|ComputeStage\|ThreadPanel\|WorkspaceThreadMessages\|thread-blocks/\|stores/execution" --include="*.tsx" --include="*.ts" | grep -v node_modules | grep -v ".next/"
```
Expected: only matches inside the files themselves and their tests. Resolve any stragglers (rename imports, remove unused references).

- [ ] **Step 2: Delete**

```bash
cd frontend
rm app/\(workbench\)/workspaces/\[id\]/components/WorkspaceInspector.tsx
rm app/\(workbench\)/workspaces/\[id\]/components/ComputeStage.tsx
rm app/\(workbench\)/workspaces/\[id\]/components/ThreadPanel.tsx
rm app/\(workbench\)/workspaces/\[id\]/components/WorkspaceThreadMessages.tsx
rm -rf app/\(workbench\)/workspaces/\[id\]/components/thread-blocks/
rm stores/execution.ts
```

- [ ] **Step 3: Find and delete legacy tests**

```bash
cd frontend
find tests -name "*WorkspaceInspector*" -o -name "*ComputeStage*" -o -name "*ThreadPanel*" -o -name "*thread-blocks*" -o -name "*execution-store*" -delete
```

- [ ] **Step 4: Run all unit + e2e tests**

```bash
cd frontend && npx vitest run
cd frontend && npx playwright test
```
Expected: all green. Any failure points to a missed migration — fix before proceeding.

- [ ] **Step 5: Confirm backend `assistant_message` SSE path is gone (Plan 1 Task 7)**

```bash
cd backend && grep -rn "assistant_message" src/ --include="*.py"
```
Expected: zero matches.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: delete legacy chat-redesign components — clean break, no fallback"
```

---

## Task 12: Acceptance criteria walkthrough (spec §12)

**Files:**
- Create: `docs/superpowers/specs/2026-05-07-chat-experience-redesign-acceptance.md` (sign-off log)

- [ ] **Step 1: Run through each spec §12 item against the running app**

```bash
cd backend && uv run python -m src.main &  # backend
cd frontend && npm run dev -- --port 3001 &  # frontend
```

Then in browser, navigate to `http://localhost:3001/workspaces/<some-id>/chat?feature=paper_analysis&skill=paper-analyst&entry=open&paper_title=...`. Send the canonical input "我想写一篇论文，联邦学习结合大模型方向" against a real LLM (not the scripted one).

Walk through and check off each spec §12 line:

```markdown
# Acceptance Sign-off · 2026-05-07

- [ ] Agent 不输出 jargon、不重复按钮、不自我汇报
- [ ] Agent 在合适时机用 question_card 提一个聚焦问题
- [ ] 右面板显示 phase 1 → 2 → 3 实时变化
- [ ] phase 切换时 chat 出现一条 status_line
- [ ] result_card 包含 TL;DR + 关键发现 + 推荐 + 反馈区
- [ ] 点反馈 pill 触发新 run，上一轮整体折叠
- [ ] 暂停按钮在下个 phase 边界停下；resume 继续
- [ ] 单 subagent 失败 → status_line warn；关键路径失败 → 阻塞 question_card
- [ ] LLM 返回 invalid JSON → 降级 TextBlock，前端无报错
- [ ] 用户上滑后 auto-follow 暂停，浮按钮回到当前进度出现
- [ ] WorkspaceAssets 在没有 active run 时默认展开
```

- [ ] **Step 2: For any unchecked item, file a follow-up task and fix before declaring done**

- [ ] **Step 3: Commit the sign-off**

```bash
git add docs/superpowers/specs/2026-05-07-chat-experience-redesign-acceptance.md
git commit -m "docs(spec): chat redesign acceptance sign-off"
```

---

## Self-Review Checklist

- [ ] **Spec coverage:**
  - §3.1 cleanup of legacy paths — Task 11 ✓
  - §4.1 WorkspaceAssets real children — Task 4 ✓
  - §4.3 useExecutionStore migration — Task 6 ✓
  - §7 URL entry seed flow — Task 3 ✓
  - §10 testing (e2e portion) — Tasks 7, 8, 9, 10 ✓
  - §12 acceptance — Task 12 ✓
- [ ] **Placeholder scan** — none ✓
- [ ] **Type consistency:** `entrySeed.params.{sourceArtifactId, paperTitle, paperAbstract}` consistent across Task 3's frontend parser, backend reader, and tests. `Run` shape used in Task 6 migration matches the one defined in Plan 2 Task 3.

