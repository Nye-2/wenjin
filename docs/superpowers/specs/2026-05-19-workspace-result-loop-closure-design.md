# Workspace Result Loop Closure Design

Date: 2026-05-19

## Overview

Workspace 当前最差的一段体验，不是“样式不够精致”，而是结果链路没有形成稳定的产品闭环。

用户完成一次 capability 运行后，会同时遇到三类问题：

1. 右侧 execution completed 态只给粗糙 summary，进一步只能看 raw JSON
2. chat async `result_card` 只支持勾选提交，不支持先预览结果再决定接受
3. `Documents` / `Library` room 只有列表，没有可消费的详情预览，所以“打开结果”并不真的打开结果

本设计的目标，是把 workspace 下的“结果生成 → 结果预览 → 选择接受 → 房间沉淀 → 房间再消费”收敛成一套新的统一架构，并用同一组交互 contract 贯通 chat、execution panel、rooms。

## Problem Statement

### Current failure mode

以“论文框架大纲”类任务为例，现状是：

1. capability 执行成功，`ExecutionRecord.result.task_report.outputs` 已有结构化输出
2. chat 里显示 async `ResultCard`，但只有 checkbox + accept/discard
3. 右侧 `CompletedView` 只能显示摘要、output pills、raw JSON
4. 点击打开文档房间，只能看到文件名列表，没有正文、outline、markdown preview

结果是：

- 用户不能在 commit 前真正判断结果质量
- 用户 commit 后也不能顺滑继续消费结果
- “Documents / Library / ResultCard / ExecutionCard”各自都是半成品，不构成完整体验

### Root cause

根因不是单个组件缺功能，而是缺了一个统一的结果展示架构：

- **Execution 层**只关心 `ResultOutput[]`，不关心用户如何消费
- **Chat 层**把 staged outputs 当成“待提交清单”，不是“待阅读结果”
- **Rooms 层**把 item 当成列表项，不是“可打开实体”
- **前端缺共享 projection**，同一份结果在不同入口被重复、粗糙、彼此不一致地渲染

## Goals

- G1. 用户在 commit 前就能读取和预览主要结果，不需要先接受再盲开房间
- G2. execution completed 态成为“结果消费面”，不是 JSON 调试面
- G3. chat `result_card` 与 execution `CompletedView` 共享同一组结果预览 contract
- G4. `Documents` / `Library` room 支持 list + detail，不再停留在 list-only
- G5. 对 markdown / text / outline / abstract 这类高频可读结果，首版就提供高质量直接渲染
- G6. 所有“打开结果”动作都有确定语义：打开预览、打开房间、聚焦某项、进入已提交项

## Non-Goals

- N1. 首版不做富文本在线编辑器，也不做 docx / pdf 原位渲染器
- N2. 首版不要求所有 artifact kind 都有专属 preview；只先覆盖 document / library_item / outline/text/markdown
- N3. 首版不做多列 room workspace dashboard，也不引入新的全局状态管理层
- N4. 不重写 result output schema；优先在现有 `ResultOutput` 基础上补 projection 和 detail endpoint

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Result architecture | 3-surface model | 把 staged、reviewable、committed 三种状态拆开，避免一个组件包打天下 |
| Primary review surface | Execution panel completed card | 右侧本来就是“run 的工作台”，应该成为默认结果消费面 |
| Chat result card role | 轻量入口 + staged selection | chat 保持对话节奏，不承载大段正文阅读 |
| Room model | List + detail split view | “打开结果”必须能看到内容，而不是只看到名称 |
| Shared frontend contract | `WorkspaceResultPreview` projection | 同一份 output 在 chat / panel / room 用同一套渲染模型 |
| Backend extension strategy | 补 detail/read endpoints + preview metadata | 尽量沿用现有 rooms service，不额外发明新持久层 |
| Commit interaction | Preview first, accept second | 用户先判断质量，再决定落房间 |

## New Architecture

### 1. Three Result Surfaces

结果闭环统一为三个 surface：

#### Surface A: Staged Result Surface

来源：`ExecutionRecord.result.task_report.outputs`

用途：

- capability 刚跑完但尚未 commit 时的可预览结果
- execution panel completed 态主展示面
- chat async result card 的详细抽屉/展开内容

特点：

- 数据仍然属于 execution，不属于 rooms
- 可以 preview、compare、select、accept
- 必须支持“先读后收”

#### Surface B: Commit Review Surface

来源：Surface A + 用户选择状态

用途：

- 管理哪些 outputs 会落到 rooms
- 支持 accept-all、accept-one、accept-selected
- commit 完成后生成 room focus handoff

特点：

- 是交互层，不是新的存储层
- 必须和 preview 紧邻，避免用户在预览和接受之间跳界面

#### Surface C: Room Detail Surface

来源：已写入 Documents / Library 的 room item

用途：

- commit 后继续阅读、引用、复用结果
- 支持从 execution / chat follow-up 深跳进来

特点：

- room 不再只是列表容器，而是“可打开实体视图”
- list 是索引，detail 才是内容消费面

### 2. Shared Frontend Projection

新增前端 projection 层：

```ts
type WorkspaceResultPreview = {
  id: string;
  source: "staged_output" | "document_room" | "library_room";
  kind: "document" | "library_item" | "memory_fact" | "decision" | "task";
  title: string;
  subtitle: string | null;
  badge: string | null;
  previewMode: "markdown" | "plain_text" | "outline" | "citation" | "json_fallback";
  previewText: string | null;
  metadataLines: string[];
  canCommit: boolean;
  canOpenRoom: boolean;
  roomTarget?: {
    room: "documents" | "library";
    itemId?: string | null;
    query?: string | null;
  };
};
```

说明：

- `ResultOutput` 不直接被 UI 组件四处消费
- chat / execution / rooms 先都转成 `WorkspaceResultPreview`
- 这样同一类内容只写一套 renderer，避免现在 `CompletedView`、`ResultCard`、`DocumentsDrawer` 各讲各的

### 3. Detail-first Room Model

`DocumentsDrawer` 和 `LibraryDrawer` 从“单列列表”升级为“列表 + 详情”。

布局：

```text
┌──────────────────────────────────────────────┐
│ Header / Search                              │
├───────────────────┬──────────────────────────┤
│ List pane         │ Detail pane              │
│ - item rows       │ - title/meta             │
│ - filter          │ - preview body           │
│ - focus highlight │ - actions                │
└───────────────────┴──────────────────────────┘
```

约束：

- 桌面端固定 split-view
- 移动端保留 sheet/stack fallback
- 用户点击 item 后，右侧 detail 立即更新
- 路由 seed `room + item_id + query` 直接驱动初始选中

## UX Flows

### Flow 1: Capability completed

1. execution 完成
2. 右侧 `ExecutionCard` 自动展开
3. `CompletedView` 显示：
   - narrative / summary
   - 关键结果卡片
   - 结果预览列表
   - commit actions
4. 用户可先读内容，再选择：
   - 接受全部
   - 只接受某几项
   - 打开结果所在房间继续看

### Flow 2: Chat async result card

chat 中的 async `ResultCard` 改为“轻量回执 + 展开预览”：

- 默认只显示 capability 名、完成状态、摘要、结果计数
- 点击“查看结果”后展开 staged previews
- 展开内容和 `CompletedView` 使用同一 renderer
- commit action 文案改成“保存到工作区”，不再只给机械的“全部接受/全弃”

### Flow 3: Open document after commit

1. 用户在 execution completed view 里点击“打开文档”
2. workspace route 带 `room=documents&item_id=...`
3. `DocumentsDrawer` 打开
4. 左侧聚焦目标 document
5. 右侧 detail pane 直接显示正文 preview / outline preview

用户到这一步看到的是结果本身，不是文件名。

## Component Design

### CompletedView

`CompletedView` 升级为 workspace 结果消费面：

#### Replace

- 删除“View full result → raw JSON”作为主交互
- JSON 退居调试 fallback，仅在 preview 无法解析时可折叠展示

#### Add

- `ResultSummarySection`
- `ResultPreviewList`
- `ResultPreviewDetail`
- `CommitActionBar`

推荐布局：

```text
Summary
Key outputs
--------------------------------
Preview list        | Detail view
--------------------------------
Commit actions
```

### ResultCard

`ResultCard` 不再默认只显示 checkbox list。

改成：

- header: status + capability + summary
- body: grouped preview rows
- detail toggle per row
- footer: save actions

具体变化：

- checkbox 从结果主视觉降级为辅助选择控件
- 每个 output row 至少有标题、preview snippet、open/preview action
- `document` 和 `library_item` 不再只展示 `output.preview`

### DocumentsDrawer

新增 detail pane，支持以下 previewMode：

- `markdown`: `react-markdown`
- `plain_text`: `pre-wrap text`
- `outline`: 标题层级列表 / 段落块
- `json_fallback`: 结构化字段卡片

首版 detail 数据来源：

- room item 本身已有可读字段时直接渲染
- 对 document，增加 detail fetch 读取正文/preview 内容

### LibraryDrawer

`Library` detail pane 显示：

- title
- authors / year / DOI / URL
- abstract
- source metadata

Library 本质上是 citation/detail view，不需要大篇幅自定义 renderer，但必须不是只有标题行。

## Backend Contract Changes

### 1. Documents detail endpoint

新增：

```text
GET /api/workspaces/{ws_id}/documents/{doc_id}
```

返回：

```json
{
  "id": "...",
  "name": "...",
  "doc_kind": "outline",
  "mime_type": "text/markdown",
  "size_bytes": 1234,
  "updated_at": "...",
  "preview_text": "# 标题\\n\\n正文...",
  "preview_mode": "markdown",
  "storage_path": "...",
  "metadata": {}
}
```

说明：

- 首版不要求真实文件下载流，只要求 detail 可读
- `preview_text` 允许来自 DB 字段、artifact 解析、或 storage best-effort 读取

### 2. Library detail endpoint

新增：

```text
GET /api/workspaces/{ws_id}/library/{item_id}
```

返回完整文献信息，避免前端只靠 list payload 硬撑 detail。

### 3. Preview metadata on staged outputs

在 execution completed payload 上，允许 document / library_item output 带轻量 preview metadata：

- `preview_text`
- `preview_mode`
- `artifact_kind`
- `room_hint`

这不是新的持久化 schema 要求，而是 `TaskReport.outputs[].data` 允许多带的 UI 友好字段。

### 4. Commit response handoff

`POST /executions/{id}/commit` 响应补充：

```json
{
  "committed": {...},
  "room_targets": [
    {"kind": "document", "room": "documents", "item_id": "doc-1"},
    {"kind": "library_item", "room": "library", "item_id": "lib-1"}
  ]
}
```

这样 commit 后前端能直接聚焦新沉淀结果，而不是再靠模糊 query 猜。

## Frontend File Changes

### New

- `frontend/lib/workspace-result-preview.ts`
  - staged output / room item → `WorkspaceResultPreview`
- `frontend/app/(workbench)/workspaces/[id]/components/result-preview/`
  - `ResultPreviewList.tsx`
  - `ResultPreviewDetail.tsx`
  - `ResultPreviewRenderer.tsx`
  - `CommitActionBar.tsx`

### Modify

- `CompletedView.tsx`
- `ResultCard.tsx`
- `DocumentsDrawer.tsx`
- `LibraryDrawer.tsx`
- `frontend/lib/api/v2/documents.ts`
- `frontend/lib/api/v2/library.ts`
- `frontend/lib/block-actions.ts`

## Backend File Changes

### New / Expand

- `backend/src/gateway/routers/workspace_rooms.py`
  - add detail endpoints
- `backend/src/services/rooms/documents_service.py`
  - add document detail / preview extraction
- `backend/src/services/rooms/library_service.py`
  - add item detail getter
- `backend/src/services/execution_commit_service.py`
  - include `room_targets` in commit response

## Error Handling

- preview 内容缺失时，不隐藏结果，退化到 `json_fallback`
- room detail fetch 失败时，仍保留 list pane，不阻断整个 drawer
- commit 成功但 room target 缺失时，显示“已保存”，但不自动 deep-link
- staged output 无法识别 previewMode 时，仍允许提交，但 detail 用 raw structured fields 渲染

## Testing Strategy

### Frontend

- `CompletedView`：
  - 渲染 preview list
  - detail pane 切换
  - JSON fallback 只在无法 preview 时出现
- `ResultCard`：
  - 结果先预览后提交
  - document/library row 展示 detail summary
- `DocumentsDrawer` / `LibraryDrawer`：
  - split view
  - route seed 初始聚焦
  - detail fetch success/failure

### Backend

- document detail endpoint
- library detail endpoint
- commit response room target mapping
- preview metadata extraction fallback

### Browser / E2E

Golden path:

1. 跑一个 framework outline capability
2. 在 completed view 看见 outline preview
3. 点击保存到工作区
4. 自动进入 Documents room
5. 右侧 detail pane 看见 outline 内容

## Migration Strategy

这次收敛是 **架构内替换**，不是旁路兼容。

原则：

- 不保留“旧 JSON 主视图”和“新 preview 主视图”双轨长期并存
- JSON 只保留为 fallback/debug affordance
- `CompletedView` 直接升级，不再新增 `CompletedViewV2`
- `DocumentsDrawer` / `LibraryDrawer` 原地升级为 split view

## Risks

### Risk 1: preview 数据来源不统一

缓解：

- 前端统一 projection
- 后端 detail endpoint 提供最终兜底

### Risk 2: staged output 和 committed room item 内容不一致

缓解：

- commit 时返回 room target
- preview contract 尽量复用相同字段

### Risk 3: room detail fetch 带来更多请求

缓解：

- 只在 drawer open + item selected 时请求
- first paint 先用 list data / staged preview data 占位

## Implementation Order

1. 前端测试先写：`CompletedView` / `ResultCard` / `DocumentsDrawer`
2. 建立 `WorkspaceResultPreview` projection 与 renderer
3. 升级 `CompletedView`
4. 升级 `ResultCard`
5. 补 documents/library detail API
6. 升级 drawers 为 split-view
7. 补 commit response room targets
8. 做 golden path E2E

## Final Recommendation

不要继续把 execution、chat、documents 各修一点。

这条线应该收敛到一个明确的新架构：

**Execution panel 负责 review，chat 负责回执，rooms 负责沉淀后再消费，三者通过统一 preview projection 和明确的 room handoff contract 串起来。**

这才是干净、稳定、可继续扩展的 workspace 结果闭环。
