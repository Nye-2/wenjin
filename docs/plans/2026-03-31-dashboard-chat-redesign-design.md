# Dashboard & Chat Redesign + Single Thread Model

> 归档说明: 本文档为历史阶段性计划快照，可能包含已过时路由、线程模型或状态描述。当前实现请以 `docs/product/workspace-current-state.md` 与相关当前契约文档为准。

**Date:** 2026-03-31
**Status:** Approved
**Goal:** Redesign dashboard with hero guidance, fix feature icons, simplify chat panel to a one-line status bar, and migrate to a single-thread-per-workspace model.

## Core Architecture Change: Single Thread

Every workspace has exactly one conversation thread. No thread switching, no thread list, no branching.

```
之前: workspace → N threads → 用户管理多个分支
之后: workspace → 1 thread → 所有对话在一个上下文中
```

**Why this works:**
- SummarizationMiddleware compresses old messages at 80k tokens
- MemoryMiddleware persists key facts to long-term memory
- Knowledge/Literature Context injected via middleware, not dependent on chat history
- Users work on ONE project per workspace, not parallel tasks

**Backend:** Keep thread data model (no schema change). Each workspace auto-creates one thread on first chat. Subsequent messages append to the same thread.

**Frontend:** Remove all thread management UI.

## 1. Dashboard Redesign

### Hero Guidance Area (replaces header + recommendation card)

```
┌──────────────────────────────────────────────────────┐
│ ← 返回          学位论文 · 计算机科学     [进入对话 →] │
│                                                      │
│  我的硕士论文研究                                      │
│                                                      │
│  ┌─ 推荐下一步 ─────────────────────────────────┐    │
│  │ 🔍 开始深度调研                               │    │
│  │ 系统性检索相关文献，分析研究空白和创新方向      │    │
│  │                               [开始 →]        │    │
│  └───────────────────────────────────────────────┘    │
├──────────────────────────────────┬─ Inspector ────────┤
│ 工作模块 (按阶段, lucide 图标)  │                     │
│ 最近对话摘要 (如有)              │                     │
└──────────────────────────────────┴────────────────────┘
```

### Smart Recommendation Logic

```
No artifacts, no threads → "开始深度调研" (first research feature)
Has research artifacts  → "大纲设计" (structure feature)
Has outline artifact    → "开始写作" (writing feature)
Has draft chapters      → "同行评审" or "编译导出"
```

### Feature Icons: lucide

Backend feature registry `icon` field stores lucide icon name strings (e.g., "search", "pen", "list"). Frontend maps to lucide-react components via shared `iconMap` (same one used by SkillSelector).

## 2. Chat Panel Redesign

### Status Bar (replaces two-card panel)

```
┌─ 🟢 结构设计 · 大纲设计 ─── 产出 3 ──── [推荐：正文撰写 →] ── ▼ ─┐
└───────────────────────────────────────────────────────────────────┘
```

One line, collapsible:
- Current stage indicator (dot + name)
- Current skill label
- Stats summary (artifact count)
- Recommended next action button
- Expand/collapse toggle (▼/▲)

Expanded state shows the full detail (original content), collapsed by default.

### Recommendation list removed from chat

The "推荐下一步" card and "推荐动作" button list are moved to the dashboard. Chat keeps only the one-line status bar with a single recommended action.

## 3. Sidebar Redesign

### Remove thread list

```
┌─────────────────────────┐
│ Workspace 名称           │
│ [学术论文] [计算机]       │
├─────────────────────────┤
│ ● 背景调研               │
│ ● 资料收集               │
│ ◐ 结构设计  ← 当前       │
│ ○ 写作修订               │
│ ○ 评审交付               │
├─────────────────────────┤
│ [💬 进入对话]            │
│ [📊 工作总览]            │
├─────────────────────────┤
│ ← 全部 workspace         │
└─────────────────────────┘
```

- Thread list section completely removed
- "新对话" button → "进入对话" (always goes to the single thread)
- "总览" stays

## 4. Routing Changes

| Before | After |
|---|---|
| `/workspaces/{id}/chat/new` | `/workspaces/{id}/chat` |
| `/workspaces/{id}/chat/{threadId}` | `/workspaces/{id}/chat` |
| Feature card → `/chat/new?feature=xxx` | Feature card → `/chat?feature=xxx` |
| Onboarding → `/chat/new?onboarding=true` | `/chat?onboarding=true` |

The `[threadId]` dynamic route segment is no longer needed for user-facing navigation. Internally, the chat page resolves the workspace's single thread.

## 5. Single Thread Resolution

Frontend `ChatPage`:
```typescript
// On mount: load or create the workspace's single thread
const thread = threads[0]; // Always use first thread
if (!thread) {
  // Create thread on first visit (backend handles this)
  startNewThread();
}
```

Backend: no change needed. The `POST /chat/stream` endpoint already creates a thread if `thread_id` is null. The frontend just stops creating new threads.

## 6. Files to Modify

### Frontend
| File | Change |
|---|---|
| `app/(workbench)/workspaces/[id]/page.tsx` | Dashboard redesign: hero area, smart recommendation, lucide icons |
| `app/(workbench)/workspaces/[id]/chat/[threadId]/page.tsx` | Simplify to single-thread, rename route |
| `app/(workbench)/workspaces/[id]/components/ChatPanel.tsx` | Replace two-card panel with collapsible status bar |
| `components/workspace/AppShellSidebar.tsx` | Remove thread list, simplify to stepper + 2 buttons |
| `lib/workspace-feature-routes.ts` | Route to `/chat?feature=xxx` instead of `/chat/new?feature=xxx` |
| Backend feature registry | Change `icon` field values to lucide names |

### Backend (minimal)
| File | Change |
|---|---|
| `backend/src/workspace_features/registry.py` | Update icon values to lucide icon names |
