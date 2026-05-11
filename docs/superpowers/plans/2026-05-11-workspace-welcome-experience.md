# Workspace 欢迎体验 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add idle-state welcome experience to v2 workspace — left panel shows centered title + suggestion pills, right panel shows glass product intro cards. Both transition when execution begins.

**Architecture:** Static config for per-type metadata. Each panel accepts optional props with defaults, renders idle state internally. V2 page fetches workspace + features and passes as props. CSS opacity transitions handle state switches.

**Tech Stack:** React 19, TypeScript, v2 CSS tokens (`--v2-*`), existing API clients (`getWorkspace`, `getWorkspaceFeatures`)

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `frontend/lib/workspace-suggestions.ts` | CREATE | Static per-type config: icons, subtitles, display names, suggestions |
| `frontend/app/(workbench)/workspaces/[id]/v2/components/ChatPanel.tsx` | MODIFY | Add idle state: centered welcome + suggestion pills |
| `frontend/app/(workbench)/workspaces/[id]/v2/components/LiveWorkflowPanel.tsx` | MODIFY | Add ProductIntro: glass feature cards + rooms hint |
| `frontend/app/(workbench)/workspaces/[id]/v2/page.tsx` | MODIFY | Fetch workspace + features, pass as props to panels |

---

### Task 1: Create workspace-suggestions.ts

**Files:**
- Create: `frontend/lib/workspace-suggestions.ts`

- [ ] **Step 1: Create the static config file**

```typescript
import type { Workspace } from "@/lib/api/types";

export interface WorkspaceTypeConfig {
  icon: string;
  title: string;
  chatSubtitle: string;
  panelSubtitle: string;
  suggestions: string[];
}

export const WORKSPACE_TYPE_CONFIG: Record<
  Workspace["type"],
  WorkspaceTypeConfig
> = {
  thesis: {
    icon: "📝",
    title: "论文工作台",
    chatSubtitle: "告诉我你想做什么，我来帮你",
    panelSubtitle: "AI 驱动的学术研究与写作助手",
    suggestions: ["帮我做个大纲", "检索相关文献", "写文献综述", "深度调研"],
  },
  sci: {
    icon: "🔬",
    title: "SCI 论文工作台",
    chatSubtitle: "从检索到发表，全流程辅助",
    panelSubtitle: "AI 驱动的 SCI 论文发表助手",
    suggestions: ["检索文献", "分析这篇论文", "写文献综述", "生成论文框架"],
  },
  proposal: {
    icon: "📋",
    title: "申报书工作台",
    chatSubtitle: "从调研到申报，高效推进",
    panelSubtitle: "AI 驱动的项目申报助手",
    suggestions: ["生成申报书大纲", "做背景调研", "设计实验方案"],
  },
  software_copyright: {
    icon: "💻",
    title: "软著工作台",
    chatSubtitle: "软著材料准备与技术说明",
    panelSubtitle: "AI 驱动的软著申请助手",
    suggestions: ["准备软著材料", "写技术说明"],
  },
  patent: {
    icon: "🔧",
    title: "专利工作台",
    chatSubtitle: "专利框架与现有技术检索",
    panelSubtitle: "AI 驱动的专利申请助手",
    suggestions: ["生成专利框架", "检索现有技术"],
  },
};
```

- [ ] **Step 2: Run typecheck to verify**

Run: `cd /Users/ze/wenjin/frontend && npm run typecheck`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/workspace-suggestions.ts
git commit -m "feat: add per-workspace-type config with suggestions and display metadata"
```

---

### Task 2: Update ChatPanel — add idle state with welcome + pills

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/v2/components/ChatPanel.tsx`

- [ ] **Step 1: Add new imports and props**

At the top of `ChatPanel.tsx`, add the import for the config type:

```typescript
import type { WorkspaceTypeConfig } from "@/lib/workspace-suggestions";
```

Update the `ChatPanelProps` interface to accept optional idle-state props:

```typescript
interface ChatPanelProps {
  workspaceId: string;
  workspaceName?: string;
  typeConfig?: WorkspaceTypeConfig;
  className?: string;
  "data-testid"?: string;
}
```

Update the destructuring:

```typescript
export function ChatPanel({
  workspaceId,
  workspaceName,
  typeConfig,
  className,
  "data-testid": testId,
}: ChatPanelProps) {
```

- [ ] **Step 2: Add idle state rendering**

Replace the message list section (the `<div ref={scrollRef}>` block). Currently:

```tsx
{/* Message list */}
<div
  ref={scrollRef}
  style={{ flex: 1, overflowY: "auto", padding: "16px 12px" }}
>
  {messages.map((msg) => (
    <MessageRow key={msg.id} message={msg} />
  ))}
</div>
```

Replace with:

```tsx
{/* Message list / idle state */}
<div
  ref={scrollRef}
  style={{ flex: 1, overflowY: "auto", padding: "16px 12px" }}
>
  {messages.length === 0 && workspaceName && typeConfig ? (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100%",
        padding: "0 20px",
        opacity: 1,
        animation: "v2-glass-in 400ms var(--v2-ease-standard)",
      }}
    >
      <div style={{ fontSize: 36, marginBottom: 12 }}>{typeConfig.icon}</div>
      <div
        style={{
          fontSize: 18,
          fontWeight: 600,
          color: "var(--v2-text-primary)",
          marginBottom: 6,
          fontFamily: "var(--v2-font-sans)",
        }}
      >
        {workspaceName}
      </div>
      <div
        style={{
          fontSize: 13,
          color: "var(--v2-text-tertiary)",
          fontFamily: "var(--v2-font-sans)",
        }}
      >
        {typeConfig.chatSubtitle}
      </div>
    </div>
  ) : (
    messages.map((msg) => <MessageRow key={msg.id} message={msg} />)
  )}
</div>
```

- [ ] **Step 3: Add suggestion pills**

Between the scroll area and the input area, add the pills section. Insert this block right before the input area `{/* Input area */}` comment:

```tsx
{/* Suggestion pills — shown only before first message */}
{messages.length === 0 &&
  typeConfig &&
  typeConfig.suggestions.length > 0 && (
    <div
      style={{
        padding: "0 12px 8px",
        display: "flex",
        flexWrap: "wrap",
        gap: 6,
      }}
    >
      {typeConfig.suggestions.map((text) => (
        <button
          key={text}
          onClick={() => void sendMessage(workspaceId, text)}
          disabled={isSending}
          style={{
            padding: "6px 14px",
            borderRadius: "var(--v2-radius-pill)",
            border: "1px solid var(--v2-border-default)",
            background: "var(--v2-accent-purple-100)",
            color: "var(--v2-accent-purple-700)",
            fontSize: 12.5,
            fontWeight: 500,
            cursor: isSending ? "not-allowed" : "pointer",
            fontFamily: "var(--v2-font-sans)",
            transition: "background 150ms, border-color 150ms",
            opacity: isSending ? 0.5 : 1,
          }}
          onMouseEnter={(e) => {
            if (!isSending) {
              e.currentTarget.style.background =
                "var(--v2-accent-purple-300)";
              e.currentTarget.style.borderColor =
                "var(--v2-accent-purple-300)";
            }
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "var(--v2-accent-purple-100)";
            e.currentTarget.style.borderColor = "var(--v2-border-default)";
          }}
        >
          {text}
        </button>
      ))}
    </div>
  )}
```

- [ ] **Step 4: Run typecheck**

Run: `cd /Users/ze/wenjin/frontend && npm run typecheck`
Expected: PASS (new props are optional, existing callers still work)

- [ ] **Step 5: Commit**

```bash
git add frontend/app/\(workbench\)/workspaces/\[id\]/v2/components/ChatPanel.tsx
git commit -m "feat: add idle welcome state and suggestion pills to ChatPanel"
```

---

### Task 3: Update LiveWorkflowPanel — add ProductIntro

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/v2/components/LiveWorkflowPanel.tsx`

- [ ] **Step 1: Add new imports and props**

At the top of `LiveWorkflowPanel.tsx`, add imports:

```typescript
import type { WorkspaceTypeConfig } from "@/lib/workspace-suggestions";
import type { WorkspaceFeature } from "@/lib/api/types";
```

Update the props interface:

```typescript
interface LiveWorkflowPanelProps {
  workspaceId: string;
  typeConfig?: WorkspaceTypeConfig;
  features?: WorkspaceFeature[];
  className?: string;
  "data-testid"?: string;
}
```

Update the destructuring:

```typescript
export function LiveWorkflowPanel({
  workspaceId,
  typeConfig,
  features = [],
  className,
  "data-testid": testId,
}: LiveWorkflowPanelProps) {
```

- [ ] **Step 2: Add ProductIntro inline component**

Add a `ProductIntro` function component inside the file (before the closing of the file, after `LiveWorkflowPanel`). This renders the glass feature cards grid:

```tsx
function ProductIntro({
  typeConfig,
  features,
}: {
  typeConfig: WorkspaceTypeConfig;
  features: WorkspaceFeature[];
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100%",
        padding: "32px 24px",
        animation: "v2-glass-in 500ms var(--v2-ease-standard)",
      }}
    >
      {/* Title */}
      <div
        style={{
          fontSize: 22,
          fontWeight: 700,
          color: "var(--v2-text-primary)",
          marginBottom: 6,
          fontFamily: "var(--v2-font-sans)",
        }}
      >
        文津{typeConfig.title}
      </div>
      <div
        style={{
          fontSize: 13,
          color: "var(--v2-text-tertiary)",
          marginBottom: 28,
          fontFamily: "var(--v2-font-sans)",
        }}
      >
        {typeConfig.panelSubtitle}
      </div>

      {/* Feature cards — 2-column grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 10,
          width: "100%",
          maxWidth: 420,
        }}
      >
        {features.slice(0, 6).map((f) => (
          <div
            key={f.id}
            style={{
              padding: "14px 16px",
              borderRadius: "var(--v2-radius-lg)",
              background: "var(--v2-glass-bg-elevated)",
              backdropFilter: "blur(10px)",
              WebkitBackdropFilter: "blur(10px)",
              border: "1px solid var(--v2-glass-border)",
              boxShadow: "var(--v2-glass-shadow)",
            }}
          >
            <div
              style={{
                fontSize: 14,
                fontWeight: 600,
                color: "var(--v2-text-primary)",
                marginBottom: 4,
                fontFamily: "var(--v2-font-sans)",
              }}
            >
              {f.icon} {f.name}
            </div>
            <div
              style={{
                fontSize: 11.5,
                color: "var(--v2-text-tertiary)",
                lineHeight: 1.4,
                fontFamily: "var(--v2-font-sans)",
              }}
            >
              {f.description}
            </div>
          </div>
        ))}
      </div>

      {/* Rooms hint */}
      <div
        style={{
          marginTop: 24,
          fontSize: 11,
          color: "var(--v2-text-disabled)",
          textAlign: "center",
          fontFamily: "var(--v2-font-sans)",
        }}
      >
        顶部工具栏提供 8 个工作房间：
        <br />
        Library · Documents · Decisions · Memory · Tasks · Runs · Sandbox ·
        Settings
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Replace the "No active execution" placeholder with ProductIntro**

Currently the content area inside the graph content `<div>` is:

```tsx
{nodes.length > 0 ? (
  <GraphCanvas
    nodes={nodes}
    edges={edges}
    onNodeClick={selectNode}
  />
) : (
  <div
    className="flex items-center justify-center h-full text-sm"
    style={{ color: "var(--v2-text-tertiary)" }}
  >
    No active execution
  </div>
)}
```

Replace with:

```tsx
{(() => {
  const hasExecution = nodes.length > 0 || executionId !== null;
  return (
    <>
      {/* ProductIntro — idle state */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          opacity: hasExecution ? 0 : 1,
          transition: "opacity 200ms var(--v2-ease-standard)",
          pointerEvents: hasExecution ? "none" : "auto",
        }}
      >
        {typeConfig && <ProductIntro typeConfig={typeConfig} features={features} />}
      </div>

      {/* Graph / loading — active state */}
      {hasExecution && (
        <div
          style={{
            opacity: nodes.length > 0 ? 1 : 0,
            transition: "opacity 200ms var(--v2-ease-standard)",
            width: "100%",
            height: "100%",
          }}
        >
          {nodes.length > 0 ? (
            <GraphCanvas
              nodes={nodes}
              edges={edges}
              onNodeClick={selectNode}
            />
          ) : (
            <div
              className="flex items-center justify-center h-full"
              style={{ color: "var(--v2-text-tertiary)", fontSize: 13 }}
            >
              准备中...
            </div>
          )}
        </div>
      )}
    </>
  );
})()}
```

Note: The IIFE (`{(() => { ... })()}`) is used to compute `hasExecution` once and avoid variable hoisting issues in JSX. The graph content wrapper `<div>` needs `position: relative` for the absolute positioning of ProductIntro to work. Verify the parent div already has `position: "relative"` — it does (line 59-64 in current code).

- [ ] **Step 4: Run typecheck**

Run: `cd /Users/ze/wenjin/frontend && npm run typecheck`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/app/\(workbench\)/workspaces/\[id\]/v2/components/LiveWorkflowPanel.tsx
git commit -m "feat: add ProductIntro glass cards to LiveWorkflowPanel idle state"
```

---

### Task 4: Update page.tsx — wire everything together

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/v2/page.tsx`

- [ ] **Step 1: Add new imports**

Update the React import (line 3):

```typescript
// Before:
import { use, useState } from "react";
// After:
import { use, useEffect, useState } from "react";
```

Add after the `useChatStream` import (after line 13):

```typescript
import { getWorkspace, getWorkspaceFeatures } from "@/lib/api/workspace";
import { WORKSPACE_TYPE_CONFIG } from "@/lib/workspace-suggestions";
import type { WorkspaceFeature } from "@/lib/api/types";
```

- [ ] **Step 2: Add data fetching**

Inside the component, after `const [compactToastVisible, setCompactToastVisible] = useState(false);` (line 31), add:

```typescript
const [workspace, setWorkspace] = useState<{
  name: string;
  type: string;
} | null>(null);
const [features, setFeatures] = useState<WorkspaceFeature[]>([]);

useEffect(() => {
  getWorkspace(id).then((w) => setWorkspace({ name: w.name, type: w.type }));
  getWorkspaceFeatures(id).then((res) => setFeatures(res.features));
}, [id]);

const typeConfig = workspace
  ? WORKSPACE_TYPE_CONFIG[workspace.type as keyof typeof WORKSPACE_TYPE_CONFIG]
  : null;
```

- [ ] **Step 3: Pass props to ChatPanel**

Change (line 52-56):

```tsx
<ChatPanel
  workspaceId={id}
  className="w-[42%] border-r"
  data-testid="chat-panel"
/>
```

To:

```tsx
<ChatPanel
  workspaceId={id}
  workspaceName={workspace?.name}
  typeConfig={typeConfig ?? undefined}
  className="w-[42%] border-r"
  data-testid="chat-panel"
/>
```

- [ ] **Step 4: Pass props to LiveWorkflowPanel**

Change (line 57-61):

```tsx
<LiveWorkflowPanel
  workspaceId={id}
  className="flex-1"
  data-testid="workflow-panel"
/>
```

To:

```tsx
<LiveWorkflowPanel
  workspaceId={id}
  typeConfig={typeConfig ?? undefined}
  features={features}
  className="flex-1"
  data-testid="workflow-panel"
/>
```

- [ ] **Step 5: Run typecheck**

Run: `cd /Users/ze/wenjin/frontend && npm run typecheck`
Expected: PASS

- [ ] **Step 6: Run dev server and verify visually**

Run: `cd /Users/ze/wenjin/frontend && npm run dev`

Open a v2 workspace page. Verify:
1. Left panel shows centered workspace name + subtitle + suggestion pills
2. Right panel shows glass feature cards with workspace type title
3. Clicking a pill sends a chat message
4. When execution starts, right panel transitions to graph view
5. After execution completes, right panel returns to product intro

- [ ] **Step 7: Commit**

```bash
git add frontend/app/\(workbench\)/workspaces/\[id\]/v2/page.tsx
git commit -m "feat: wire workspace welcome experience — fetch data, pass to panels"
```
