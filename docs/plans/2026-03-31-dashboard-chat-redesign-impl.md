# Dashboard & Chat Redesign Implementation Plan

> 归档说明: 本文档为历史阶段性计划快照，可能包含已过时路由、线程模型或状态描述。当前实现请以 `docs/product/workspace-current-state.md` 与相关当前契约文档为准。

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Redesign the workspace dashboard with a hero guidance area, simplify the chat panel to a collapsible status bar, switch to a single-thread-per-workspace model, and fix feature icons to use lucide.

**Architecture:** Dashboard gets a merged hero section (header + smart recommendation). Chat panel's two-card area becomes a one-line collapsible status bar. All thread management UI is removed — one workspace, one conversation. Feature icons change from arbitrary strings to lucide icon names shared with the SkillSelector iconMap. Routing simplifies from `/chat/[threadId]` to `/chat`.

**Tech Stack:** Next.js 16, React 19, TypeScript, TailwindCSS, Framer Motion, lucide-react

---

### Task 1: Update feature icon values in backend registry

**Files:**
- Modify: `backend/src/workspace_features/registry.py`

**Step 1: Update icon values**

Change the `icon` field in every `WorkspaceFeatureDefinition` to use lucide-compatible kebab-case names matching the existing `iconMap` in SkillSelector. The mapping:

```
THESIS:
  deep_research        → "search"        (already correct)
  literature_management → "book-open"     (was "book")
  opening_research     → "file-text"     (was "clipboard")
  thesis_writing       → "pen"           (already correct)
  figure_generation    → "image"         (was "chart")
  compile_export       → "package"       (was "download")

SCI:
  literature_search    → "search"        (already correct)
  paper_analysis       → "microscope"    (was "flask")
  writing              → "pen"           (already correct)
  literature_review    → "book-open"     (was "book")
  framework_outline    → "list"          (already correct)
  peer_review          → "shield-check"  (was "flask")
  journal_recommend    → "compass"       (was "lightbulb")

PROPOSAL:
  proposal_outline     → "file-text"     (was "list")
  background_research  → "search"        (was "book")
  experiment_design    → "flask-conical" (was "flask")

SOFTWARE_COPYRIGHT:
  copyright_materials  → "file-text"     (was "list")
  technical_description → "code"         (was "file")

PATENT:
  patent_outline       → "lightbulb"     (was "list")
  prior_art_search     → "search"        (already correct)
```

Find each `icon=` field in the registry and replace. Do NOT change any other fields.

**Step 2: Commit**
```bash
git add backend/src/workspace_features/registry.py
git commit -m "feat: update feature icons to lucide-compatible names"
```

---

### Task 2: Create shared icon resolver utility

**Files:**
- Create: `frontend/lib/icon-map.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/SkillSelector.tsx`

**Step 1: Extract iconMap to shared module**

Create `frontend/lib/icon-map.ts`:

```typescript
import {
  BookOpen,
  Code,
  Compass,
  FileText,
  FlaskConical,
  Image,
  Lightbulb,
  List,
  Microscope,
  Package,
  Pen,
  Search,
  ShieldCheck,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export const iconMap: Record<string, LucideIcon> = {
  search: Search,
  "book-open": BookOpen,
  "file-text": FileText,
  list: List,
  pen: Pen,
  image: Image,
  package: Package,
  microscope: Microscope,
  "shield-check": ShieldCheck,
  compass: Compass,
  "flask-conical": FlaskConical,
  lightbulb: Lightbulb,
  code: Code,
};

export const defaultIcon: LucideIcon = Search;

export function resolveIcon(name: string | undefined | null): LucideIcon {
  if (!name) return defaultIcon;
  return iconMap[name] ?? defaultIcon;
}
```

**Step 2: Update SkillSelector to import from shared module**

Replace the local `iconMap` and imports in `SkillSelector.tsx` with:
```typescript
import { resolveIcon } from "@/lib/icon-map";
```

Remove the local iconMap definition and lucide-react icon imports that are now in the shared module.

**Step 3: Commit**
```bash
git add frontend/lib/icon-map.ts frontend/app/\(workbench\)/workspaces/\[id\]/components/SkillSelector.tsx
git commit -m "feat: extract icon map to shared module"
```

---

### Task 3: Create chat route without threadId

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/chat/page.tsx`
- Modify: `frontend/lib/workspace-feature-routes.ts`

**Step 1: Create `/chat/page.tsx` (single thread)**

```typescript
"use client";

import { useEffect } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { useChatStore } from "@/stores/chat";
import { useWorkspaceStore } from "@/stores/workspace";
import { ChatPanel } from "../components/ChatPanel";
import { parseWorkspaceChatEntrySeed } from "@/lib/workspace-chat-entry";
import { WorkspaceInspector } from "../components/WorkspaceInspector";

export default function ChatPage() {
  const { id: workspaceId } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const skillFromUrl = searchParams.get("skill");
  const entrySeed = parseWorkspaceChatEntrySeed(searchParams);
  const isOnboarding = searchParams.get("onboarding") === "true";

  const { workspace } = useWorkspaceStore();
  const { threads, loadThreads, loadThread, startNewThread, setCurrentSkill } =
    useChatStore();

  // If onboarding and no feature seed, create synthetic onboarding seed
  const effectiveEntrySeed = entrySeed ?? (isOnboarding && workspace ? {
    featureId: "__onboarding__",
    skillId: null,
    params: { __onboarding_type: workspace.type },
  } : null);

  // Single thread: load existing or create new
  useEffect(() => {
    void loadThreads(workspaceId).then(() => {
      const currentThreads = useChatStore.getState().threads;
      if (currentThreads.length > 0) {
        void loadThread(currentThreads[0].id);
      } else {
        startNewThread();
      }
      if (skillFromUrl) {
        setCurrentSkill(skillFromUrl);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  return (
    <div className="flex h-full flex-col overflow-hidden p-4 sm:p-6 atmosphere-mesh">
      <div className="grid h-full min-h-0 grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="chat-container min-h-0 overflow-hidden rounded-[1.75rem]">
          <ChatPanel workspaceId={workspaceId} entrySeed={effectiveEntrySeed} />
        </div>
        <div className="min-h-0 overflow-hidden rounded-[1.75rem]">
          <WorkspaceInspector workspaceId={workspaceId} />
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Update routes to use `/chat` instead of `/chat/new`**

In `workspace-feature-routes.ts`, change `getWorkspaceFeatureChatRoute`:

Replace the pathname from:
```typescript
const pathname = `/workspaces/${workspaceId}/chat/new`;
```
to:
```typescript
const pathname = `/workspaces/${workspaceId}/chat`;
```

**Step 3: Commit**
```bash
git add "frontend/app/(workbench)/workspaces/[id]/chat/page.tsx" frontend/lib/workspace-feature-routes.ts
git commit -m "feat: add single-thread chat route, update feature routes to /chat"
```

---

### Task 4: Simplify sidebar — remove thread list

**Files:**
- Modify: `frontend/components/workspace/AppShellSidebar.tsx`

**Step 1: Remove thread list and simplify**

Key changes:
1. Remove all thread-related imports and state: `threads`, `activeThreadId`, `isThreadsLoading`, `startNewThread`, `deleteThread`, `goToThread`, `handleDeleteThread`
2. Remove the entire thread list section (the `<div className="flex-1 overflow-y-auto">` block with thread items)
3. Change "新对话" button to "进入对话" → navigates to `/workspaces/${workspaceId}/chat`
4. Remove the `Plus` icon for thread creation
5. The sidebar becomes: workspace info → stage stepper → 2 buttons (进入对话 + 总览) → back link

The `goToNewChat` function changes:
```typescript
const goToChat = () => router.push(`/workspaces/${workspaceId}/chat`);
```

No more `startNewThread()` call.

**Step 2: Commit**
```bash
git add frontend/components/workspace/AppShellSidebar.tsx
git commit -m "feat: remove thread list from sidebar, simplify to single chat entry"
```

---

### Task 5: Redesign dashboard with hero guidance

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/page.tsx`

**Step 1: Rewrite dashboard**

Key changes:

1. **Hero section** — merge header and recommendation into one area:
   - Top line: back button + type/discipline tags + "进入对话" CTA
   - Workspace name as large title
   - Smart recommendation card embedded in hero (uses stage-based logic, not `features[0]`)
   - Background: `route-card-featured atmosphere-mesh`

2. **Smart recommendation logic**:
```typescript
function inferRecommendedFeature(features, artifacts, threads) {
  // Map artifact types to stages
  const hasResearch = artifacts.some(a => ["DEEP_RESEARCH_REPORT", "LITERATURE_SEARCH_RESULTS", "BACKGROUND_RESEARCH"].includes(a.type));
  const hasOutline = artifacts.some(a => ["FRAMEWORK_OUTLINE", "ABSTRACT"].includes(a.type));
  const hasDraft = artifacts.some(a => ["THESIS_CHAPTER", "PAPER_DRAFT"].includes(a.type));

  if (hasDraft) return features.find(f => ["peer_review", "compile_export", "journal_recommend"].includes(f.id));
  if (hasOutline) return features.find(f => ["thesis_writing", "writing"].includes(f.id));
  if (hasResearch) return features.find(f => ["framework_outline", "proposal_outline", "patent_outline"].includes(f.id));
  return features[0]; // Default: first feature (usually research)
}
```

3. **Feature cards** — use `resolveIcon` from shared module instead of rendering `feature.icon` as text

4. **Routing** — all feature cards and CTA go to `/chat` not `/chat/new`:
   - "进入对话" → `/workspaces/${id}/chat`
   - Feature card → `/workspaces/${id}/chat?feature=xxx`

5. **Onboarding redirect** — change target from `/chat/new?onboarding=true` to `/chat?onboarding=true`

6. **Remove "最近对话" section** — no more thread list, this section was showing recent threads

**Step 2: Commit**
```bash
git add "frontend/app/(workbench)/workspaces/[id]/page.tsx"
git commit -m "feat: redesign dashboard with hero guidance, smart recommendations, lucide icons"
```

---

### Task 6: Simplify chat panel — collapsible status bar

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`

**Step 1: Replace the two-card panel with a collapsible status bar**

Find the section between `<WorkspaceChatHeader>` and the messages container (lines ~680-789). Replace the entire `<div className="border-b ... bg-[rgba(251,248,242,0.88)]">` block with a compact status bar.

The status bar shows:
- Current stage dot + name
- Current skill label (if any)
- Artifact count
- Recommended next action button
- Expand/collapse toggle

```tsx
const [statusExpanded, setStatusExpanded] = useState(false);

// Collapsed status bar:
<div className="border-b border-[var(--border-default)] bg-[rgba(251,248,242,0.92)] px-4 py-2">
  <div className="flex items-center gap-3">
    <div className="flex items-center gap-2">
      <div className="h-2 w-2 rounded-full bg-[var(--brand-brass)]" />
      <span className="text-sm font-medium text-[var(--text-primary)]">
        {currentPhaseTitle}
      </span>
    </div>

    {currentSkillLabel && (
      <span className="rounded-full border border-[var(--accent-primary)]/18 bg-[var(--accent-primary)]/8 px-2 py-0.5 text-[10px] font-medium text-[var(--accent-primary)]">
        {currentSkillLabel}
      </span>
    )}

    <span className="text-xs text-[var(--text-muted)]">
      产出 {artifacts.length}
    </span>

    <div className="ml-auto flex items-center gap-2">
      {nextStepAction?.feature_id && (
        <button
          onClick={() => {
            const route = getWorkspaceFeatureRoute(workspaceId, nextStepAction.feature_id);
            if (route) router.push(route);
          }}
          className="text-xs font-medium text-[var(--brand-navy)] hover:underline"
        >
          推荐：{nextStepAction.title} →
        </button>
      )}
      <button
        onClick={() => setStatusExpanded(!statusExpanded)}
        className="rounded-lg p-1 text-[var(--text-muted)] hover:bg-[var(--bg-surface)]"
      >
        {statusExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
      </button>
    </div>
  </div>

  {/* Expanded detail (original content) */}
  {statusExpanded && (
    <div className="mt-3 grid gap-3 xl:grid-cols-2">
      {/* Original phase card + recommendation card content */}
    </div>
  )}
</div>
```

Add `ChevronUp` and `ChevronDown` to lucide-react imports.

**Step 2: Commit**
```bash
git add "frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx"
git commit -m "feat: replace chat panel two-card area with collapsible status bar"
```

---

### Task 7: Update workspaces page and layout onboarding redirects

**Files:**
- Modify: `frontend/app/workspaces/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/layout.tsx`

**Step 1: Update workspace creation redirect**

In `workspaces/page.tsx`, change:
```typescript
router.push(`/workspaces/${created.id}/chat/new?onboarding=true`);
```
to:
```typescript
router.push(`/workspaces/${created.id}/chat?onboarding=true`);
```

**Step 2: Update layout**

In `layout.tsx`, remove `loadThreads` from the useEffect if it was being used for thread list population. The chat page now handles its own thread loading.

Actually — keep `loadThreads` in layout since chat page needs the threads data. Just verify it works.

**Step 3: Commit**
```bash
git add frontend/app/workspaces/page.tsx frontend/app/\(workbench\)/workspaces/\[id\]/layout.tsx
git commit -m "feat: update onboarding redirects to /chat route"
```

---

### Task 8: Keep old [threadId] route as redirect

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/chat/[threadId]/page.tsx`

**Step 1: Convert to redirect for backward compatibility**

Replace the entire file with a redirect to `/chat`:

```typescript
"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

export default function ThreadRedirect() {
  const router = useRouter();
  const { id: workspaceId } = useParams<{ id: string }>();

  useEffect(() => {
    router.replace(`/workspaces/${workspaceId}/chat`);
  }, [router, workspaceId]);

  return null;
}
```

**Step 2: Commit**
```bash
git add "frontend/app/(workbench)/workspaces/[id]/chat/[threadId]/page.tsx"
git commit -m "feat: convert threadId route to redirect for backward compatibility"
```

---

### Task 9: TypeScript check and build verification

**Step 1:** `cd frontend && npx tsc --noEmit`
**Step 2:** `cd frontend && npx next build`
**Step 3:** Fix any errors
**Step 4:** Final commit if needed
