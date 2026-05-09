# 实时工作台彻底重构设计文档（方案 B）

> 状态：细节确认中，未冻结

---

## 1. 总体方向

从 "Run → Phase → Subagent" 的三层树形模型，彻底迁移到 **"TaskRun → Graph"** 的扁平图模型。

- **TaskRun** = 一次任务执行（对应一个 execution_session）
- **Graph** = 该任务内部的 LangGraph 数据流图
- **Node** = 图中的一个执行节点（对应一个 subagent）
- **Edge** = 节点间的数据依赖关系

---

## 2. 数据模型（彻底重构）

### 2.1 删除的概念

- ~~`PhaseSnap`~~ — 不再存在
- ~~`PhaseList`~~ — 不再存在
- ~~`SubagentGrid`~~ — 不再存在
- ~~`SubagentCard`~~ — 不再存在
- ~~phase index -1 的 task 伪节点~~ — task 信息提升到 TaskRun 级别

### 2.2 新建的数据结构

```typescript
// stores/workflow-store-support.ts

interface TaskMeta {
  task_id: string;
  task_type: string;
  feature_id: string | null;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  progress: number;           // 0-100
  message: string | null;     // 当前状态描述
  current_step: string | null;
  error: string | null;
  started_at: string;
  completed_at?: string;
}

interface GraphNode {
  id: string;                 // subagent.task_id
  label: string;              // subagent.subagent_type || "node"
  status: "pending" | "running" | "completed" | "failed" | "waiting" | "cancelled";
  layer: number;              // 继承自 workflow_phase_index，用于垂直分层布局
  // 详情数据（后端逐步补齐）
  input?: string | null;
  output?: string | null;
  output_preview?: string | null;
  thinking?: string | null;
  tool_calls?: ToolCall[];
  token_usage?: { total: number };
  model_name?: string | null;
  duration_ms?: number;
  // 样式覆盖
  accent_color?: string;      // 如 "#BDD836"
}

interface GraphEdge {
  from: string;               // source node id
  to: string;                 // target node id
  // 可选：边类型（数据流 / 控制流）
  type?: "data" | "control";
}

interface TaskRun {
  id: string;                 // execution_session_id
  thread_id: string;
  title: string;              // feature_name or task_type
  meta: TaskMeta;
  nodes: GraphNode[];
  edges: GraphEdge[];         // 依赖关系（后端提供或前端推断）
}

interface ToolCall {
  tool: string;
  input: unknown;
  output: unknown;
  duration_ms?: number;
}
```

### 2.3 Reducer 重构

```typescript
// reduceTaskEvent → 更新 TaskRun.meta，不创建节点
// reduceSubagentEvent → 创建/更新 GraphNode（放入对应 layer）
// reduceEdgeEvent → 新增（如果后端提供边信息）
```

---

## 3. UI 组件结构（彻底重写）

```
LiveWorkflowPanel
├── PanelHeader              // "实时工作台" + 活跃/完成计数 + 一键展开/折叠
├── TaskRunList              // 垂直堆叠的 TaskRunCard
│   └── TaskRunCard
│       ├── CardHeader       // 可点击折叠/展开
│       │   ├── StatusLight  // 脉冲指示灯
│       │   ├── Title        // Feature 名称
│       │   ├── ProgressBar  // 整体进度
│       │   └── Actions      // 折叠按钮 / 暂停 / 删除
│       └── CardBody (展开时)
│           ├── TaskMetaBar   // task message + current_step
│           └── TaskGraphCanvas
│               ├── SVG Layer (连线 + 动画)
│               └── NodeLayer
│                   └── TaskNode[] (网格/自由布局)
│                       └── clickable → NodeDetailDrawer
├── NodeDetailDrawer         // 右侧滑出详情面板
│   ├── NodeHeader           // 名称 + 状态 + 时间
│   ├── InputSection         // 节点输入
│   ├── OutputSection        // 节点输出
│   ├── ThinkingSection      // 思考过程（可折叠）
│   └── ToolCallsSection     // 工具调用列表（可折叠）
└── WorkspaceAssets          // 底部资产抽屉（保持现有）
```

---

## 4. 待确认的关键细节（Checklist）

- [ ] 图的拓扑结构：固定网格 vs 自由拓扑 vs 固定层+层内网格
- [ ] 边的来源：后端提供 `depends_on` / `parent_id` vs 前端按 layer 顺序推断
- [ ] NodeDetail 数据来源：后端补齐哪些字段？优先级？
- [ ] 任务卡片生命周期：completed 自动折叠？保留多久？可手动删除？
- [ ] 视觉风格：深色/浅色？毛玻璃强度？动画复杂度？
- [ ] 布局算法：自研 CSS Grid vs dagre.js vs 其他图布局库
- [ ] 实时更新策略：节点状态变化时的动画过渡方式
