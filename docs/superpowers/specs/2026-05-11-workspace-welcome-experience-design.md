# Workspace 欢迎体验设计

## Context

进入 workspace 后当前 UI 是两个空白面板：左侧只有输入框，右侧只显示 "No active execution"。没有问候、没有引导、没有功能提示。用户不知道能做什么、怎么做。

本设计为 v2 workspace 的空闲态（idle state）添加两层引导：

1. **左侧 ChatPanel**：居中 workspace 标题 + 快捷 suggestion pill
2. **右侧 LiveWorkflowPanel**：产品说明书（玻璃态功能卡片）

执行开始后，右侧直接淡入 workflow graph。

## Design Decisions

- **Chat 不主动发消息**：保持输入框的静默状态，用 suggestion pill 引导
- **Suggestion pill 点击直接发送**：低摩擦启动对话
- **右侧是产品说明书**：展示该 workspace type 的核心功能 + rooms 提示
- **切换方式**：执行开始后直接淡出说明书、淡入 graph，不保留折叠按钮

## Left: ChatPanel Idle State

### 居中欢迎区

当 `messages.length === 0` 时，消息滚动区域显示居中内容：

```
        [workspace type icon / emoji]

        论文工作台
        告诉我你想做什么，我来帮你
```

- workspace 名称来自 `getWorkspace(id).name` 或按 type 的固定文案
- 副标题是固定文案，按 workspace type 不同：
  - thesis: "告诉我你想做什么，我来帮你"
  - sci: "从检索到发表，全流程辅助"
  - proposal: "从调研到申报，高效推进"
  - software_copyright: "软著材料准备与技术说明"
  - patent: "专利框架与现有技术检索"

### Suggestion Pills

输入框上方显示 4-5 个 pill，内容来自该 workspace type 的 feature `follow_up_prompt` 或预定义文案。

| Workspace Type | Pills |
|---|---|
| thesis | 帮我做个大纲 · 检索相关文献 · 写文献综述 · 深度调研 |
| sci | 检索文献 · 分析论文 · 写综述 · 生成框架 |
| proposal | 生成申报书大纲 · 背景调研 · 设计实验 |
| software_copyright | 准备材料 · 技术说明 |
| patent | 生成专利框架 · 检索现有技术 |

**Pill 样式**：圆角胶囊，背景色对应 feature 的 `color`（`#f5f3ff` / `#f0fdf4` 等），文字色为对应深色。

**点击行为**：调用 `chatStore.sendMessage(workspaceId, pillText)` 直接发送消息。

**消失时机**：用户发送第一条消息后 pill 区域隐藏（`messages.length > 0`）。

### 所需数据

v2 page 需要：
1. 调用 `getWorkspace(id)` 获取 workspace `type` 和 `name`
2. 根据 `type` 确定欢迎文案和 suggestion pills

通过 props 传递给 ChatPanel：`workspaceType`, `workspaceName`, `suggestions`。

## Right: LiveWorkflowPanel Product Intro

### 空闲态内容

当没有 active execution 时（`nodes.length === 0`），右侧显示：

```
        [Glass orb background]

        文津论文工作台
        AI 驱动的学术研究与写作助手

        ┌──────────────┐  ┌──────────────┐
        │ 🔍 深度调研    │  │ 📚 文献管理    │
        │ 自动检索、分析  │  │ 整理、引用、管理 │
        └──────────────┘  └──────────────┘
        ┌──────────────┐  ┌──────────────┐
        │ ✍️ 论文写作    │  │ 📊 图表生成    │
        │ 大纲、撰写、修订│  │ 可视化、流程图  │
        └──────────────┘  └──────────────┘

        顶部工具栏提供 8 个工作房间：
        Library · Documents · Decisions · Memory · Tasks · Runs · Sandbox · Settings
```

### 功能卡片

- 2 列网格，数据来自 `getWorkspaceFeatures(workspaceId)`
- 每张卡片：feature icon + name（标题）+ description（一行说明）
- 卡片样式：玻璃态（`backdrop-filter: blur(10px)`，白色半透明背景，细微边框）
- 标题颜色对应 feature 的 `color`（紫色 / 绿色 / 蓝色 / 橙色）
- 底部一行提示 rooms 工具栏的 8 个房间名称

### 切换到工作流

当 execution stream 产生第一个节点事件时：
- 产品说明书整体 `opacity 0 → 1` 淡出（200ms）
- Workflow graph `opacity 0 → 1` 淡入（200ms）
- 说明书组件卸载（不再渲染）

切换条件：`nodes.length > 0 || currentExecutionId !== null`

### 回到空闲态

execution 完成后 5 秒（现有的 `setActiveExecutionId(null)` 逻辑），右侧回到产品说明书。

## Data Flow

```
V2 page mount
    ├── getWorkspace(id) → { type: "thesis", name: "我的论文" }
    ├── getWorkspaceFeatures(id) → [{ id, name, description, icon, color, ... }, ...]
    ├── workspace type → suggestion pills mapping
    │
    ├── ChatPanel props:
    │     workspaceType, workspaceName, suggestions
    │
    └── LiveWorkflowPanel props:
          workspaceType, features
```

## Component Changes

| Component | Change |
|---|---|
| `page.tsx` | ADD: fetch workspace + features, pass as props |
| `ChatPanel.tsx` | ADD: idle state rendering (centered title + pills) |
| `LiveWorkflowPanel.tsx` | ADD: ProductIntro component for idle state |

## Suggestion Mapping

Suggestion 文案是静态配置（不需要 API 调用），按 workspace type 索引：

```typescript
const WORKSPACE_SUGGESTIONS: Record<string, string[]> = {
  thesis: ["帮我做个大纲", "检索相关文献", "写文献综述", "深度调研"],
  sci: ["检索文献", "分析这篇论文", "写文献综述", "生成论文框架"],
  proposal: ["生成申报书大纲", "做背景调研", "设计实验方案"],
  software_copyright: ["准备软著材料", "写技术说明"],
  patent: ["生成专利框架", "检索现有技术"],
};
```

每个 suggestion 对应的 feature handler 会被 chat_agent 自动路由，无需前端硬编码映射。

## Style Tokens

使用现有 `--v2-*` CSS tokens：
- Chat idle 背景：纯白 `#fff`
- Pill 背景：按 feature color 的 5% 透明度变体
- Panel 卡片背景：`rgba(255,255,255,0.7)` + `backdrop-filter: blur(10px)`
- Panel 标题：`var(--v2-text-primary)`
- Panel 副文字：`var(--v2-text-tertiary)`

## Files

| File | Action |
|---|---|
| `frontend/app/(workbench)/workspaces/[id]/v2/page.tsx` | MODIFY — fetch workspace + features |
| `frontend/app/(workbench)/workspaces/[id]/v2/components/ChatPanel.tsx` | MODIFY — add idle state |
| `frontend/app/(workbench)/workspaces/[id]/v2/components/LiveWorkflowPanel.tsx` | MODIFY — add ProductIntro |
| `frontend/lib/workspace-suggestions.ts` | CREATE — static suggestion mapping |
