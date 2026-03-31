# Frontend Redesign — Chat-Centric Architecture

## Goal

Redesign the frontend from 21+ independent feature pages to a **Chat-as-center** architecture with a supporting Dashboard, where workspace-specific features are triggered through the chat agent via system prompts and skill selection.

## Architecture

Two primary views replace 21+ feature routes:
1. **Dashboard View** — Workspace overview with feature cards, active tasks, recent conversations
2. **Chat View** — Full-screen chat with inline TaskCards, expandable TaskDetailPanel

The backend already supports workspace-specific system prompts and feature routing via the existing middleware pipeline, chat skill catalog, and feature bridge.

## Design Decisions

| Aspect | Decision |
|--------|----------|
| Entry Point | Chat as center, Dashboard as auxiliary |
| Layout | Dashboard <-> Full-screen Chat dual-view toggle |
| Feature Trigger | Dashboard card click -> jump to Chat + skill param |
| Task Progress | Inline TaskCard in chat stream + expandable DetailPanel |
| System Prompts | Backend already implements workspace-specific skill injection |
| Routes | 21+ -> 3 |

---

## Module 1: App Shell & Routes

### Route Structure
```
/workspaces                        -> WorkspaceListPage
/workspaces/[id]                   -> WorkspaceDashboard
/workspaces/[id]/chat/[threadId]   -> ChatView (full-screen)
```

### Layout
```
┌──────────────────────────────────────────────────────┐
│  Logo   历史仓库                    [User Avatar] │
├────────┬─────────────────────────────────────────────┤
│        │                                             │
│ Sidebar│              Main Content                   │
│        │                                             │
│ [WS 1] │  (Dashboard or Chat View)                   │
│ [WS 2] │                                             │
│ [WS 3] │                                             │
│        │                                             │
│--------│                                             │
│ Threads│                                             │
│ [T 1]  │                                             │
│ [T 2]  │                                             │
│--------│                                             │
│[+ New] │                                             │
│[Dashbd]│  <- View switcher                           │
└────────┴─────────────────────────────────────────────┘
```

**Sidebar** (240px, collapsible):
- Top section: workspace list
- Middle section: chat thread list (for current workspace)
- Bottom section: view switcher (Dashboard / Chat) + "New Chat" button

---

## Module 2: Chat View

### Message Types
1. **UserMessage** — User text + optional attachments
2. **AITextMessage** — AI response with markdown rendering
3. **TaskCard** (inline) — Compact card showing task lifecycle
4. **ResultCard** — Final output of a completed task

### TaskCard Lifecycle
```
[pending]  ┌─────────────────────────────────┐
           │ 📊 Deep Research       ⏳ 排队中  │
           └─────────────────────────────────┘
               ↓
[running]  ┌─────────────────────────────────┐
           │ 📊 Deep Research     ████░░ 72%  │
           │ 当前阶段：综合分析                │
           │                        [查看详情] │
           └─────────────────────────────────┘
               ↓
[success]  ┌─────────────────────────────────┐
           │ ✅ Deep Research       完成      │
           │ 生成了 12 条研究思路              │
           │                  [展开结果] [详情]│
           └─────────────────────────────────┘
```

### TaskDetailPanel
- 380px right panel, slides in on "查看详情" click
- Shows full task runtime state: phases, blocks, streaming output
- Reuses existing TaskRuntimePanel rendering logic
- Closable, does not block chat interaction

### Input Bar
```
┌──────────────────────────────────────────────────┐
│ [深度研究] [文献搜索] [+]  ← Skill selector chips │
│                                                  │
│ 输入消息...                           [📎] [➤]  │
└──────────────────────────────────────────────────┘
```
- Skill chips from workspace features (loaded via API)
- Clicking a chip sets `selectedSkill` in chatStore
- Attachment button for file uploads
- Send button

---

## Module 3: Dashboard View

### Layout (workspace-type-specific features)
```
┌─────────────────────────────────────────────────┐
│  🔬 我的毕业论文  ▾                      [Chat] │
├─────────────────────────────────────────────────┤
│                                                 │
│  ▸ Running Tasks (only shown when active)       │
│  ┌──────────────────────────────────────────┐   │
│  │ 📊 Deep Research · Running 72%    [View] │   │
│  └──────────────────────────────────────────┘   │
│                                                 │
│  Features                                       │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │ 📚 Deep │ │ 📖 Lit  │ │ ✍️ Open │          │
│  │Research │ │ Mgmt    │ │Research │          │
│  └─────────┘ └─────────┘ └─────────┘          │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │ 📝 Write│ │ 📈 Figs │ │ 📦 Export│          │
│  └─────────┘ └─────────┘ └─────────┘          │
│                                                 │
│  Click feature card = navigate to Chat with     │
│  selected_skill pre-filled                      │
│                                                 │
│  Recent Conversations                           │
│  · "Search transformer papers" — 2h ago         │
│  · "Generate thesis outline" — yesterday        │
└─────────────────────────────────────────────────┘
```

**Key behaviors:**
- Feature cards have NO status indicators (no linear workflow implied)
- All features are equal tool entries — user can use any at any time
- Cards come from `GET /workspaces/:id/features` which reads the feature registry
- Clicking a feature card navigates to `/workspaces/[id]/chat/new?skill={feature_id}`
- Running tasks section only visible when there are active (pending/running) tasks
- Recent conversations show latest threads for quick access

### Workspace-Specific Features
Different workspace types show different feature cards:
- **thesis**: deep_research, literature_management, opening_research, thesis_writing, figure_generation, compile_export (6)
- **sci**: literature_search, paper_analysis, writing, literature_review, framework_outline, peer_review, journal_recommend (7)
- **proposal**: proposal_outline, background_research, experiment_design (3)
- **software_copyright**: copyright_materials, technical_description (2)
- **patent**: patent_outline, prior_art_search (2)

---

## Module 4: Data Flow & Integration

### Feature Trigger Flow
```
User clicks Feature card ("Deep Research")
    │
    ▼
Frontend route: /workspaces/[id]/chat/new?skill=deep-research
    │
    ▼
ChatInput auto-fills skill chip: [Deep Research]
    │
    ▼  User types message + clicks send
    │
POST /chat/stream { message, workspace_id, thread_id, selected_skill: "deep-research" }
    │
    ▼
Feature Bridge -> resolve intent -> submit workspace_feature task
    │
    ▼
SSE stream: task.created -> task.progress -> task.completed
    │
    ▼
Chat message flow: [AI text] -> [TaskCard inline] -> [Result card]
```

### New API Endpoint
`GET /workspaces/:id/features` — Returns available features for the workspace type.
Response: `[{ id, name, description, icon, color }]`
(Data from existing `workspace_features/registry.py`)

### Zustand Store Changes
- `workspaceStore` — Add `features: WorkspaceFeature[]`, fetched on workspace load
- `chatStore` — Add `selectedSkill: string | null`
- Remove standalone feature stores (thesis-writing, etc.) as features run through chat

### Backend (Already Implemented)
- `chat_skill_catalog.py` — Workspace-type -> chat skill mappings
- `_render_workspace_available_skills()` — Injects skills into system prompt
- Feature Bridge — Routes `selected_skill` to workspace feature execution
- Middleware pipeline — Injects workspace type, discipline, norms into agent context

---

## Module 5: Migration Strategy

### Route Redirects
Old feature routes redirect to chat with skill parameter:
```
/workspaces/[id]/deep-research      -> /workspaces/[id]/chat/new?skill=deep-research
/workspaces/[id]/literature-management -> /workspaces/[id]/chat/new?skill=literature-management
/workspaces/[id]/thesis-writing     -> /workspaces/[id]/chat/new?skill=thesis-writing
... (all 21 routes)
```

### Phased Approach
1. Build new components (App Shell, Chat View, Dashboard) alongside existing pages
2. Add route redirects from old routes to new Chat view
3. Verify all features work through chat-centric flow
4. Remove old feature page code and standalone feature stores

### Component Reuse
- `TaskRuntimePanel` rendering logic -> reuse in `TaskDetailPanel`
- `LazyChatPanel` (current sidebar chat) -> evolve into full `ChatView`
- `FeatureWorkbenchShell` -> replace with new `AppShell`
