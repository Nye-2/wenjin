# Workspace UX Simplification Design

> 归档说明: 本文档为历史阶段性计划快照，可能包含已过时路由、线程模型或状态描述。当前实现请以 `docs/product/workspace-current-state.md` 与相关当前契约文档为准。

**Date:** 2026-03-30
**Status:** Approved
**Goal:** Simplify the post-entry workspace experience while preserving the premium feel. Reduce cognitive load for new users, streamline the feature execution flow, and add guided onboarding.

## Core Principles

- Simplify without downgrading — keep the visual richness and information hierarchy
- Conversation-first — the primary interaction mode is chat, not forms
- Progressive disclosure — show complexity only when the user needs it
- Concept reduction — users should only need to understand: Workspace → 工作模块 → 对话 → 产出

## 1. Dashboard 瘦身

### Remove
- **5-stage path overview card** (the large "当前路径概览" section) — stage info moves to sidebar only
- **4 statistics cards** ("运行中任务/功能模块/对话分支/已沉淀产出") — zeros are a negative signal for new users, low value for experienced users

### Keep & Optimize
- **Header**: workspace name + type tag + discipline tag. Remove description text (sidebar has it). Change "继续当前任务" button:
  - Has threads → label "继续上次对话", navigates to most recent thread
  - No threads → label "新对话", navigates to `/chat/new`
- **推荐下一步 (Recommended Next Step)**: keep, upgrade logic to align with stage progression
- **Feature Cards ("可继续的模块")**: keep, but **group by stage** instead of flat list. Section titles use stage names ("背景调研", "资料收集", etc.)
- **正在推进的任务 (Running Tasks)**: keep, show only when tasks exist
- **最近对话 (Recent Conversations)**: keep, below feature cards
- **WorkspaceInspector (right panel)**: keep as-is

### New Layout
```
┌─ Header (名称 + 类型tag + 智能按钮) ─────────────┐
├─ 推荐下一步 (突出卡片) ───────────┬─ Inspector ───┤
├─ 正在推进的任务 (条件显示) ───────┤               │
├─ 工作模块 (按阶段分组) ───────────┤               │
├─ 最近对话 ────────────────────────┤               │
└───────────────────────────────────┴───────────────┘
```

## 2. Feature Flow Redesign (Form → Conversational Guidance)

### Remove
- **`/features/[featureId]` parameter form page** — the entire intermediate page with parameter editing and dual "执行模块" / "进入主线" buttons

### New Flow
```
User clicks feature card (e.g., "深度调研")
    ↓
router.push(`/workspaces/${id}/chat/new?feature=deep_research`)
    ↓
Chat page opens, skill auto-matched (invisible to user)
    ↓
LLM sends first message with conversational parameter collection
```

### Conversational Guidance
Instead of a form, the LLM collects parameters through natural dialogue:
- Entry prompt constructed client-side based on `featureId` and workspace context
- Sent as system-level context (invisible to user)
- LLM responds with a guided opening message asking for required inputs
- If URL already carries params (e.g., from recommendation card), LLM skips those questions

### Feature Execution
- No standalone "执行模块" button
- Feature execution becomes a natural outcome of the conversation — LLM triggers backend tasks after collecting sufficient context
- Task progress visible via existing TaskRuntimePanel mechanism

### Route Changes
- `getWorkspaceFeatureRoute()` returns chat route (`/chat/new?feature=xxx`) instead of feature page route
- `/features/[featureId]` page becomes a redirect to the chat route for backward compatibility
- `getWorkspaceFeatureChatRoute()` becomes the primary routing function

### Concept Merge: Feature + Stage → "工作模块"
- UI no longer distinguishes between feature and stage
- Feature cards grouped by their parent stage
- User-facing concepts reduced to: Workspace → 工作模块 → 对话 → 产出

## 3. Sidebar Redesign

### New Structure (top to bottom)
```
┌─────────────────────────┐
│ Workspace 名称           │  Compact: name + type/discipline tags only
│ [学术论文] [计算机]       │  Remove description and brand text
├─────────────────────────┤
│ ● 背景调研               │  5-stage stepper: compact single-line each
│ ● 资料收集               │  Clickable: scrolls to stage group on dashboard
│ ◐ 结构设计  ← 当前       │  or navigates back to dashboard from chat
│ ○ 写作修订               │  No description text, just dot + title
│ ○ 评审交付               │
├─────────────────────────┤
│ [+ 新对话]               │  Two compact buttons replacing the
│ [📊 工作总览]             │  verbose "继续主线" and "工作总览" entries
├─────────────────────────┤
│ 对话记录                 │  Existing thread list, now gets more
│ ┌─ 深度调研：大模型...   │  visible space due to reduced sections above
│ ├─ 论文框架讨论          │
│ └─ ...                   │
├─────────────────────────┤
│ ← 返回全部 workspace     │
└─────────────────────────┘
```

### Key Changes
1. **Workspace info**: one line name + tags, remove description and "问津 / Wenjin" brand text
2. **5-stage path**: compact clickable stepper (dot + title per line, no descriptions)
   - Only location for stage display (removed from dashboard)
   - Click on dashboard → scroll to stage group anchor
   - Click from chat page → navigate to dashboard at that stage
3. **Work entries**: two compact buttons ("新对话" + "工作总览")
4. **Thread list**: unchanged, benefits from reclaimed vertical space
5. **Collapsed mode**: unchanged (icon-only)

## 4. New Workspace Onboarding

### Auto-redirect to Chat
```typescript
// In workspace dashboard page.tsx
if (workspace && threads.length === 0 && artifacts.length === 0) {
  router.replace(`/workspaces/${workspaceId}/chat/new?onboarding=true`);
  return null;
}
```

### LLM Guided Opening
When `onboarding=true`, construct a special entry prompt containing workspace type and context. LLM responds with a type-specific welcome:

**thesis example:**
> 欢迎开始你的学位论文工作区。
> 我可以帮你完成从选题调研到终稿交付的全过程。我们先从最重要的事情开始：
> **你的论文题目或研究方向是什么？**

**patent example:**
> 欢迎开始你的专利申请工作区。
> 我可以帮你完成技术交底、权利要求书撰写和现有技术检索。先告诉我：
> **你要申请专利的技术方案是什么？**

### Return to Dashboard
- User can always return via sidebar "工作总览"
- After at least one thread exists, subsequent entries show dashboard normally

## 5. Edge Cases & Compatibility

### Smart "Continue" Button
- Has threads → "继续上次对话" → navigate to most recent thread
- No threads → "新对话" → navigate to `/chat/new`

### Feature Cards with null skill mapping
- `figure_generation`, `compile_export`, etc. still navigate to `/chat/new?feature=xxx` without skill param
- Chat uses default skill, LLM guides based on feature context

### Backward Compatibility
- `/features/[featureId]` route preserved as redirect → `getWorkspaceFeatureChatRoute(...)`
- Bookmarked URLs and history entries won't 404

### Sidebar Stepper Click Behavior
- On dashboard page → scroll to stage group anchor
- On chat page → navigate to dashboard, positioned at stage

### CommandPalette
- Unchanged. Feature list still searchable via Cmd+K, clicks go through new chat route

## Files to Modify

### Frontend Changes
1. `app/(workbench)/workspaces/[id]/page.tsx` — Dashboard overhaul
2. `app/(workbench)/workspaces/[id]/features/[featureId]/page.tsx` — Convert to redirect
3. `components/workspace/AppShellSidebar.tsx` — Sidebar redesign
4. `lib/workspace-feature-routes.ts` — Route functions point to chat
5. `app/(workbench)/workspaces/[id]/chat/[threadId]/page.tsx` — Handle onboarding & feature entry prompts
6. `app/workspaces/page.tsx` — Create workspace redirects to chat for new workspaces
7. `components/workspace/CommandPalette.tsx` — Update feature click routes

### No Backend Changes Required
All changes are frontend-only. The conversational guidance is achieved by constructing entry prompts client-side.
