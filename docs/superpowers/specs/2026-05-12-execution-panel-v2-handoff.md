# Execution Panel V2 — 完整设计记录与交接文档

Date: 2026-05-12

---

## 1. 项目背景

wenjin (问津) 是一个学术 AI 工作台，左侧聊天面板 + 右侧执行面板（两 Agent 拓扑）。用户通过 chat agent 发起功能（如"文献检索"、"框架设计"），chat agent 通过 `launch_feature` tool 派发执行到 lead agent，lead agent 运行 LangGraph 编排 subagent（searcher / react）。

### 问题

右侧面板使用 `@xyflow/react` (ReactFlow) 渲染执行图，存在以下问题：
1. 两个节点占满整个屏幕，布局浪费
2. 连接线歪扭
3. 无进度上下文——用户只能盯着 "running" 圆点
4. 无实时 thinking
5. 一次只能看一个执行
6. NodeDetailDrawer 是脱离图的 overlay

---

## 2. 设计决策

通过多轮头脑风暴（含浏览器视觉 mockup）确定：

| 决策 | 选择 | 原因 |
|------|------|------|
| 面板布局 | 纵向卡片流 | 信息密度高，可滚动历史 |
| 图可视化 | Phase Timeline (B-enhanced) | 零自动布局，纯 CSS flex，线永远不会穿框 |
| 节点详情 | 卡片内展开（inline） | 不用 drawer，保持上下文 |
| Thinking | 实时 SSE delta 流式推送 | 前端 store 已预留 `execution.node.delta` |
| 已完成卡片 | 摘要 + 可折叠完整结果 | 渐进式披露 |
| 并发模型 | 单执行，chat agent 阻塞并发 | `launch_feature` 已有 `lead_busy` advisory |
| 卡片标题 | 创建时 denormalize display_name | `ExecutionRecord` 只存 feature_id 不存名称 |

### Phase Timeline 设计（B-enhanced）

选择原因：自动布局图（方案 C）在小画布里线容易穿框，且需要 dagre/elkjs 依赖。Phase Timeline 是纯 CSS flexbox 竖排：
- 每个 Phase 是一行（左侧 timeline dot + 右侧节点药片）
- 环用黄色标签 `↺ 循环 N/M`，不画回折线
- 顶部彩色进度条（每节点一段）

---

## 3. 代码审查发现（5 个关键问题）

实现前对代码库做了深度审查，发现以下问题：

### Finding 1: Thinking delta 是替换不是追加（CRITICAL）

**文件**: `frontend/stores/execution-store.ts:146`

```typescript
// 原来（替换）：
nodeState.thinking = event.payload.thinking;

// 修改为（追加）：
nodeState.thinking = (nodeState.thinking || "") + event.payload.thinking;
```

**决策**: 改 store 为 append 模式，后端发增量片段。

### Finding 2: 卡片标题数据缺失（CRITICAL）

`ExecutionRecord` 只存 `feature_id`，不存 capability `display_name`。`GET /executions/{id}` 也不返回 `workspace_type`。

**决策**: 在 `ExecutionRecord` 上新增 `display_name` 列，创建时从 resolved Capability 写入。

### Finding 3: 单执行架构够用

`launch_feature.py:100-114` 已有 DB 查询检查 active execution per workspace，返回 `lead_busy` advisory。无需多并发。

**决策**: 保持 `currentExecutionId: string | null`，不改数组。

### Finding 4: Phase 信息映射断裂

后端 `_to_panel_graph` 发送 `{id, phase: "outline_phase", task, subagent_type, label}`，但前端类型 `ExecutionGraphNode` 只声明 `{id, type, label?, metadata?}`。`phase` 是额外字段，`useExecutionStreamV2` 从 `metadata.phase_index`（数字）读，但后端从不写这个字段。

**决策**: 更新前端类型加入 `phase?` 字段，hook 直接从 `node.phase` 读取。

### Finding 5: Redis Stream maxlen=512

高频 delta 事件可能丢弃。低优先级，Phase 3 时处理。

---

## 4. 架构

### 数据流

```
Chat Agent → launch_feature tool → ExecutionRecord (DB) → Celery task
                                                          ↓
                                              LeadAgentRuntime.run_session()
                                                          ↓
                                              compile_graph() → LangGraph
                                                          ↓
                                              Subagent (searcher/react) per node
                                                          ↓
                                              _record_node_event → update_node_state (DB)
                                              _emit → publish_execution_event (Redis Stream)
                                                          ↓
                                              SSE → Frontend execution-store
                                                          ↓
                                              ExecutionCard → PhaseRow → NodePill
```

### SSE 事件类型

| 事件 | 何时 | 载荷 |
|------|------|------|
| `execution.status` | 任务开始时 | `{status: "running"}` |
| `execution.graph_structure` | 能力解析后 | `{nodes, edges}` |
| `execution.node` | 每节点 running/completed/failed | `{node_id, status}` |
| `execution.node.delta` | Phase 3: thinking 流式 | `{node_id, thinking}` |
| `execution.completed` | 图执行完 | 完整 TaskReport |

### 前端组件树

```
LiveWorkflowPanel
  ├── ExecutionCardList (scrollable)
  │     └── ExecutionCard (×N, full-width)
  │           ├── CardHeader (icon + title + status badge)
  │           └── CardBody (expanded)
  │                 ├── InProgressView (running)
  │                 │     ├── ProgressBar (colored segments)
  │                 │     └── PhaseRow (×N)
  │                 │           ├── NodePill (×N, clickable)
  │                 │           └── NodeInlineDetail (expanded)
  │                 │                 └── DetailTabs (Input/Output/Thinking)
  │                 └── CompletedView (completed)
  │                       ├── ResultSummary
  │                       └── FullResultSection (collapsible)
  └── ProductIntro (idle fallback)
```

### 后端文件清单

| 文件 | 职责 |
|------|------|
| `database/models/execution.py` | ExecutionRecord + `display_name` 列 |
| `services/execution_service.py` | CRUD, `update_node_state`, `create_execution(display_name=...)` |
| `tools/builtins/launch_feature.py` | 传递 display_name + workspace_type |
| `gateway/routers/executions.py` | GET 返回 display_name + workspace_type |
| `agents/lead_agent/v2/runtime.py` | `run_session`, `_build_persisting_runner_factory`, `_emit_delta` |
| `agents/lead_agent/v2/compiler.py` | `compile_graph`, `_default_runner_factory(emit_delta=...)` |
| `agents/lead_agent/v2/template.py` | Jinja-subset 模板渲染器 |
| `subagents/v2/base.py` | `SubagentContext(emit_delta=...)`, `SubagentResult` |
| `subagents/v2/types/react.py` | `astream()` + thinking delta |
| `subagents/v2/types/searcher.py` | 纯 API 调用，无 LLM |
| `services/execution_event_publisher.py` | 双通道发布（Redis Stream + Pub/Sub） |

### 前端文件清单

| 文件 | 职责 |
|------|------|
| `lib/api/types.ts` | ExecutionRecord, ExecutionGraphNode (+phase), ExecutionNodeState (+input/output) |
| `stores/execution-store.ts` | Zustand store, thinking append, node delta handling |
| `hooks/useExecutionStreamV2.ts` | Phase grouping from graph_structure, record exposure |
| `hooks/useExecutionStream.ts` | SSE subscription, reconnect |
| `hooks/useWorkspaceEventStream.ts` | Workspace SSE → execution stream trigger |
| `components/LiveWorkflowPanel.tsx` | 面板容器（卡片流 + ProductIntro） |
| `components/ExecutionCardList.tsx` | 卡片列表 + 历史管理 |
| `components/ExecutionCard.tsx` | 单卡片（header + expanded body） |
| `components/InProgressView.tsx` | 进度条 + PhaseTimeline |
| `components/PhaseRow.tsx` | Phase 行（dot + rail + node pills + thinking preview） |
| `components/NodePill.tsx` | 节点药片（状态色 + 点击） |
| `components/NodeInlineDetail.tsx` | 内联详情（Input/Output/Thinking tabs） |
| `components/CompletedView.tsx` | 结果摘要 + 可折叠完整输出 |

### 已删除的文件

- `GraphCanvas.tsx` — ReactFlow 画布
- `PhaseNode.tsx` — ReactFlow 自定义节点
- `NodeDetailDrawer.tsx` — 右侧滑入抽屉
- `@xyflow/react` 依赖已移除

---

## 5. 已知 Bug（待修）

### BUG-1: execution.completed 事件硬编码 status="completed"

**严重度**: 高
**文件**: `frontend/stores/execution-store.ts:177`

```typescript
case "execution.completed": {
  updated.status = "completed";  // ← 硬编码！忽略了 payload 里的真实 status
```

**问题**: 后端 `execution.completed` SSE 事件的 payload 包含完整的 `TaskReport`，其中 `status` 可能是 `"failed_partial"` 或 `"cancelled"`。但 store 硬编码为 `"completed"`，导致前端卡片永远显示"已完成"。

**修复**:
```typescript
case "execution.completed": {
  updated.status = (event.payload.status as ExecutionStatus) || "completed";
```

### BUG-2: 已完成卡片无内容

**严重度**: 中
**原因**: `CompletedView` 从 `result_summary` 取摘要，但 `execution.completed` 事件的 payload 是 `TaskReport.model_dump()`，其中字段名是 `result_summary`。需要确认 payload 结构是否匹配。

同时 `outputs` 提取逻辑 `record.result?.outputs` 需要验证实际数据结构。

### BUG-3: Semantic Scholar 429

**严重度**: 低（外部 API 限制）
**现状**: Semantic Scholar 免费 API 有严格的速率限制。连续测试时容易触发 429。
**可能的改进**: 加 API key、加 retry backoff、或换用其他学术搜索源。

---

## 6. Design Spec + Implementation Plan 位置

- **Design Spec**: `docs/superpowers/specs/2026-05-12-execution-panel-v2-design.md`
- **Implementation Plan**: `docs/superpowers/plans/2026-05-12-execution-panel-v2.md`
- **此交接文档**: `docs/superpowers/specs/2026-05-12-execution-panel-v2-handoff.md`

---

## 7. Commits

| Commit | 内容 |
|--------|------|
| `74fbbfd` | Design spec 初始版本 |
| `cf5a75b` | 补充 failed card + auto-expand |
| `767208f` | 代码审查发现更新 spec |
| `a35925b` | Implementation plan |
| `c9eca37` | **Task 1**: display_name denormalization + migration |
| `73f9663` | **Task 2**: FE types, store thinking append, phase grouping |
| `6d5e06c` | **Task 3**: NodePill, NodeInlineDetail, PhaseRow, InProgressView |
| `0965d55` | **Task 4**: CompletedView, ExecutionCard, ExecutionCardList |
| `2ace421` | **Task 5**: Replace LiveWorkflowPanel, delete ReactFlow |
| `bff8a4a` | **Task 6**: emit_delta on SubagentContext |
| (latest) | **Tasks 7+8**: React streaming + runtime emit_delta wiring |

---

## 8. 待做（Next Steps）

1. **修 BUG-1**: execution-store.ts `execution.completed` handler 读 payload.status
2. **修 BUG-2**: 验证 CompletedView 数据映射
3. **UI 打磨**: 卡片展开/收起动画（CSS Grid grid-template-rows 过渡）
4. **Loop 标签**: PhaseRow 的 `loopInfo` prop 需要从 graph_template 的循环配置中提取并传入
5. **历史加载**: 当前 ExecutionCardList 的历史只保存在内存。需要 `GET /executions?workspace_id=X&limit=20` 端点加载历史
6. **Redis maxlen**: 增大到 2048（低优先级）
7. **React subagent tools 路径流式**: 当前只有 no-tools 路径用 astream，tools 路径仍用 ainvoke
8. **前端测试**: 为新组件补充 unit test
