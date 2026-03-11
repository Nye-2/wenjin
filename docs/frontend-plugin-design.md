# 前端可插拔通用模板设计准则

> 本文档描述 AcademiaGPT 前端的可插拔 Features 系统设计，以及前后端对接规范。

## 一、设计理念

### 核心原则

**Workspace 是通用空间，Features 决定功能差异**

```
┌─────────────────────────────────────────────────────────────────┐
│                    通用 Workspace 模板                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Workspace Type: thesis / sci / proposal / patent / ...       │
│                          ↓                                      │
│   GET /api/workspaces/{id}/features                            │
│                          ↓                                      │
│   { features: [                                                │
│       { id: "outline", name: "生成大纲", agent: "thesis_writer",│
│         icon: "list", panel: "outline_editor", stages: [...] },│
│       { id: "literature", name: "文献综述", agent: "librarian",│
│         icon: "book", panel: "literature_panel", stages: [...] },│
│       ...                                                      │
│     ] }                                                        │
│                          ↓                                      │
│   前端动态渲染:                                                 │
│   • QuickActions (从 features 渲染，无硬编码)                   │
│   • AgentStatusBar (通用，从 feature.stages 获取阶段)          │
│   • FeaturePanel (根据 feature.panel 动态切换)                 │
│   • ArtifactLibrary (通用)                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 设计优势

1. **扩展性强** - 新增 workspace 类型只需后端配置 features，无需修改前端代码
2. **维护成本低** - 前端组件通用，减少重复代码
3. **一致性** - 所有 workspace 共享相同的 UI 模式和交互体验
4. **动态性** - 可根据用户权限、workspace 状态动态调整可用功能

---

## 二、核心组件

### 2.1 文件结构

```
frontend/
├── lib/api.ts                    # API 类型和函数
├── stores/
│   ├── features.ts               # Features 状态管理
│   ├── task.ts                   # 任务执行状态管理
│   └── workspace.ts              # Workspace 状态管理
└── components/workspace/
    ├── QuickActions.tsx          # 动态快捷指令
    ├── AgentStatusBar.tsx        # Agent 执行状态栏
    ├── ArtifactLibrary.tsx       # 成果库
    └── index.ts                  # 组件导出
```

### 2.2 数据类型定义

```typescript
// lib/api.ts

// Feature 阶段定义
export interface FeatureStage {
  id: string;       // 阶段唯一标识
  label: string;    // 阶段显示名称
}

// Feature 定义
export interface WorkspaceFeature {
  id: string;           // 功能唯一标识，如 "outline"
  name: string;         // 显示名称，如 "生成大纲"
  description: string;  // 功能描述
  icon: string;         // 图标名称（前端映射到 Lucide Icon）
  agent: string;        // 后端 agent 类型标识
  agentLabel: string;   // Agent 显示名称
  panel?: string;       // 右侧面板类型（可选）
  stages: FeatureStage[]; // 执行阶段列表
  color?: string;       // 主题色（可选）
}
```

### 2.3 状态管理

#### Features Store (`stores/features.ts`)

```typescript
interface FeaturesState {
  features: WorkspaceFeature[];
  isLoading: boolean;
  error: string | null;

  // Actions
  fetchFeatures: (workspaceId: string) => Promise<void>;
  getFeatureById: (featureId: string) => WorkspaceFeature | undefined;
  clearFeatures: () => void;
}
```

#### Task Store (`stores/task.ts`)

```typescript
interface TaskStage extends FeatureStage {
  status: 'completed' | 'running' | 'pending';
}

interface CurrentTask {
  id: string;
  featureId: string;
  status: 'running' | 'completed' | 'cancelled' | 'failed';
  agent: string;
  agentLabel: string;
  thinking: string;         // Agent 当前思考内容
  stages: TaskStage[];      // 阶段进度
  currentStageIndex: number;
  startedAt: string;
  completedAt?: string;
}

interface TaskState {
  isExecuting: boolean;
  currentTask: CurrentTask | null;
  recentCompleted: CurrentTask | null;

  // Actions
  startTask: (params) => string;
  updateTaskThinking: (thinking: string) => void;
  advanceStage: () => void;
  completeTask: () => void;
  cancelTask: () => void;
  failTask: (error: string) => void;
  clearRecentCompleted: () => void;
}
```

### 2.4 组件说明

#### QuickActions - 动态快捷指令

- **位置**: 输入框上方
- **数据来源**: `useFeaturesStore().features`
- **行为**:
  - 点击触发 `onAction(featureId)`
  - 任务执行时自动禁用
- **Icon 映射**:
  ```typescript
  const iconMap: Record<string, LucideIcon> = {
    list: ListOrdered,
    book: BookOpen,
    pen: PenTool,
    chart: BarChart3,
    file: FileText,
    download: Download,
    search: Search,
    flask: FlaskConical,
    edit: FileEdit,
    lightbulb: Lightbulb,
  };
  ```

#### AgentStatusBar - Agent 执行状态栏

- **位置**: 输入框上方，QuickActions 下方
- **状态**:
  1. **空闲** - 不显示
  2. **执行中** - 显示阶段进度和思考气泡
  3. **完成** - 显示成功提示（3秒后自动消失）
- **交互**:
  - 可展开/折叠
  - 可取消任务

#### ArtifactLibrary - 成果库

- **位置**: 左侧面板
- **数据来源**: `useWorkspaceStore().artifacts`
- **分组**: 按 artifact.type 分组显示
- **Icon/颜色映射**: 预定义映射表

---

## 三、前端扩展指南

### 3.1 添加新的 Icon 支持

编辑 `components/workspace/QuickActions.tsx`:

```typescript
import { NewIcon } from "lucide-react";

const iconMap: Record<string, LucideIcon> = {
  // ... existing icons
  new_icon: NewIcon,
};
```

### 3.2 添加新的成果类型

编辑 `components/workspace/ArtifactLibrary.tsx`:

```typescript
const artifactIconMap: Record<string, LucideIcon> = {
  // ... existing types
  new_type: NewIcon,
};

const artifactColorMap: Record<string, string> = {
  // ... existing types
  new_type: "text-orange-500 bg-orange-500/10",
};

const typeOrder = [
  // ... existing types
  "new_type",
];
```

### 3.3 添加新的 Feature Panel（右侧面板）

1. 创建新面板组件:

```typescript
// components/workspace/panels/NewFeaturePanel.tsx
export function NewFeaturePanel({ workspaceId, feature }: PanelProps) {
  // 实现面板逻辑
}
```

2. 在 Panel 映射中注册:

```typescript
// components/workspace/panels/index.tsx
import { NewFeaturePanel } from "./NewFeaturePanel";

const panelMap: Record<string, React.ComponentType<PanelProps>> = {
  // ... existing panels
  new_panel: NewFeaturePanel,
};
```

---

## 四、后端对接规范

### 4.1 Features API

**Endpoint**: `GET /api/workspaces/{workspace_id}/features`

**Response**:
```json
{
  "features": [
    {
      "id": "outline",
      "name": "生成大纲",
      "description": "根据研究主题生成论文大纲",
      "icon": "list",
      "agent": "thesis_writer",
      "agentLabel": "ThesisWriter",
      "panel": "outline_editor",
      "color": "purple",
      "stages": [
        { "id": "analyze", "label": "分析需求" },
        { "id": "generate", "label": "生成大纲" },
        { "id": "refine", "label": "优化调整" }
      ]
    },
    {
      "id": "literature",
      "name": "文献综述",
      "description": "搜索和整理相关文献",
      "icon": "book",
      "agent": "librarian",
      "agentLabel": "Librarian",
      "panel": "literature_panel",
      "color": "emerald",
      "stages": [
        { "id": "search", "label": "搜索文献" },
        { "id": "analyze", "label": "分析文献" },
        { "id": "synthesize", "label": "综合整理" }
      ]
    }
  ]
}
```

### 4.2 Feature 执行 API

**Endpoint**: `POST /api/workspaces/{workspace_id}/features/{feature_id}/execute`

**Request**:
```json
{
  "params": {
    // feature-specific parameters
  },
  "thread_id": "optional-thread-id"
}
```

**Response**:
```json
{
  "task_id": "task-xxx",
  "status": "running"
}
```

### 4.3 Task 状态更新 (SSE)

**Endpoint**: `GET /api/tasks/{task_id}/stream`

**SSE Events**:

```typescript
// 阶段变更
{ "type": "stage_change", "stage_index": 1, "stage_id": "generate" }

// 思考更新
{ "type": "thinking", "content": "正在分析论文结构..." }

// 进度更新
{ "type": "progress", "percent": 45, "message": "处理中..." }

// 完成事件
{
  "type": "completed",
  "result": { ... },
  "artifacts": [{ "id": "xxx", "type": "outline", ... }]
}

// 错误事件
{ "type": "error", "message": "错误描述" }
```

### 4.4 后端实现示例 (Python/FastAPI)

```python
# src/gateway/routers/features.py

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Literal

router = APIRouter(prefix="/workspaces/{workspace_id}/features", tags=["features"])

# Feature 配置（可从数据库或配置文件加载）
WORKSPACE_FEATURES = {
    "thesis": [
        {
            "id": "outline",
            "name": "生成大纲",
            "description": "根据研究主题生成论文大纲",
            "icon": "list",
            "agent": "thesis_writer",
            "agentLabel": "ThesisWriter",
            "panel": "outline_editor",
            "color": "purple",
            "stages": [
                {"id": "analyze", "label": "分析需求"},
                {"id": "generate", "label": "生成大纲"},
                {"id": "refine", "label": "优化调整"},
            ],
        },
        # ... more features
    ],
    "sci": [...],
    "proposal": [...],
}

@router.get("")
async def get_features(workspace_id: str, workspace_service = Depends(get_workspace_service)):
    """获取 workspace 可用的 features"""
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_type = workspace.type.value if workspace.type else "thesis"
    features = WORKSPACE_FEATURES.get(workspace_type, [])

    return {"features": features}


class ExecuteRequest(BaseModel):
    params: dict = {}
    thread_id: str | None = None


@router.post("/{feature_id}/execute")
async def execute_feature(
    workspace_id: str,
    feature_id: str,
    request: ExecuteRequest,
    task_service = Depends(get_task_service),
):
    """执行 feature，返回 task_id"""
    # 1. 获取 feature 配置
    # 2. 创建 task
    # 3. 调用对应的 subagent
    # 4. 返回 task_id

    task_id = await task_service.submit_task(
        user_id="current_user",  # 从 auth 获取
        task_type=f"feature:{feature_id}",
        payload={
            "workspace_id": workspace_id,
            "feature_id": feature_id,
            "params": request.params,
            "thread_id": request.thread_id,
        },
    )

    return {"task_id": task_id, "status": "running"}
```

---

## 五、前端调用流程

### 5.1 初始化流程

```typescript
// app/(workbench)/workspaces/[id]/page.tsx

useEffect(() => {
  if (workspaceId) {
    loadWorkspace(workspaceId);
    fetchFeatures(workspaceId);  // 加载 features
  }

  return () => {
    clearWorkspace();
    clearFeatures();
  };
}, [workspaceId]);
```

### 5.2 执行 Feature 流程

```typescript
// ChatPanel.tsx

const handleQuickAction = async (featureId: string) => {
  if (isExecuting) return;

  const feature = getFeatureById(featureId);
  if (!feature) return;

  // 1. 启动前端任务状态
  startTask({
    featureId: feature.id,
    agent: feature.agent,
    agentLabel: feature.agentLabel,
    stages: feature.stages,
    initialThinking: `正在准备执行 ${feature.name}...`,
  });

  // 2. 调用后端 API
  try {
    const response = await fetch(`/api/workspaces/${workspaceId}/features/${featureId}/execute`, {
      method: 'POST',
      body: JSON.stringify({ params: {} }),
    });
    const { task_id } = await response.json();

    // 3. 监听 SSE 更新
    subscribeToTask(task_id);
  } catch (error) {
    failTask(error.message);
  }
};
```

### 5.3 SSE 监听示例

```typescript
const subscribeToTask = (taskId: string) => {
  const eventSource = new EventSource(`/api/tasks/${taskId}/stream`);

  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);

    switch (data.type) {
      case 'stage_change':
        advanceStage();
        break;
      case 'thinking':
        updateTaskThinking(data.content);
        break;
      case 'completed':
        completeTask();
        eventSource.close();
        break;
      case 'error':
        failTask(data.message);
        eventSource.close();
        break;
    }
  };
};
```

---

## 六、约定与规范

### 6.1 Icon 命名规范

使用小写下划线命名，对应 Lucide React 图标库:

| icon 值 | Lucide 组件 | 适用场景 |
|---------|-------------|----------|
| `list` | ListOrdered | 大纲、列表类 |
| `book` | BookOpen | 文献、阅读类 |
| `pen` | PenTool | 写作、编辑类 |
| `chart` | BarChart3 | 图表、数据类 |
| `file` | FileText | 文档、报告类 |
| `download` | Download | 导出、下载类 |
| `search` | Search | 搜索、查询类 |
| `flask` | FlaskConical | 实验、分析类 |
| `edit` | FileEdit | 修改、更新类 |
| `lightbulb` | Lightbulb | 创意、想法类 |

### 6.2 Color 命名规范

使用 Tailwind 颜色名:

- `purple` - 论文大纲类
- `blue` - 摘要、总结类
- `emerald` - 文献、综述类
- `amber` - 章节、内容类
- `rose` - 图表、可视化类
- `cyan` - 表格、数据类
- `indigo` - 方法、框架类

### 6.3 Feature ID 命名规范

使用小写下划线命名:

- `outline` - 生成大纲
- `abstract` - 撰写摘要
- `literature` - 文献综述
- `methodology` - 研究方法
- `results` - 结果分析
- `discussion` - 讨论部分
- `conclusion` - 结论

---

## 七、注意事项

1. **单任务执行** - 同时只能有一个 feature 在执行，新任务需等待当前任务完成或取消

2. **错误处理** - 所有 API 调用需要 try-catch，错误信息通过 `failTask()` 显示

3. **状态同步** - SSE 连接断开时需要重连机制，确保状态不丢失

4. **类型安全** - 所有 API 响应使用 TypeScript 类型定义

5. **性能优化** - Features 列表在 workspace 切换时清理，避免状态污染

---

## 八、可插拔性说明

### 8.1 核心思想

**前端零修改，后端配置即可扩展**

```
┌────────────────────────────────────────────────────────────────┐
│                    添加新 Workspace 类型                        │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  传统方式（需要修改前端）:                                       │
│  ❌ 新增路由                                                    │
│  ❌ 新增组件                                                    │
│  ❌ 新增状态管理                                                │
│  ❌ 重新部署前端                                                │
│                                                                │
│  可插拔方式（只需后端配置）:                                     │
│  ✅ 后端添加 WORKSPACE_FEATURES["new_type"] = [...]            │
│  ✅ 完成！前端自动渲染                                          │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 8.2 添加新 Workspace 类型的步骤

**只需后端修改，前端零改动：**

```python
# 后端: src/gateway/routers/features.py

WORKSPACE_FEATURES = {
    # 现有类型
    "thesis": [...],
    "sci": [...],

    # 新增类型 - 只需添加配置！
    "patent": [
        {
            "id": "patent_search",
            "name": "专利检索",
            "description": "检索相关专利技术",
            "icon": "search",           # 前端已有 icon 映射
            "agent": "patent_agent",    # 后端 subagent
            "agentLabel": "PatentAgent",
            "panel": "patent_list",     # 如需新面板，前端添加
            "color": "cyan",            # 前端已有颜色映射
            "stages": [
                {"id": "search", "label": "检索专利"},
                {"id": "analyze", "label": "分析技术"},
                {"id": "report", "label": "生成报告"},
            ],
        },
        # ... 更多 features
    ],
}
```

### 8.3 可插拔边界

| 层级 | 可插拔 | 需要前端修改 |
|------|--------|--------------|
| Workspace 类型 | ✅ 纯配置 | ❌ |
| Feature 列表 | ✅ 纯配置 | ❌ |
| Feature 阶段 (stages) | ✅ 纯配置 | ❌ |
| Icon 颜色 | ✅ 纯配置 | ❌ |
| **新 Icon** | ❌ | ✅ 添加 iconMap |
| **新 Panel** | ❌ | ✅ 创建面板组件 |
| **新 Artifact 类型** | ❌ | ✅ 添加映射 |

### 8.4 设计约束

1. **Icon 限制** - 只能使用预定义的 icon（见 6.1），新增需前端改动
2. **Panel 限制** - 只能使用预定义的 panel，新增需前端开发
3. **颜色限制** - 只能使用预定义颜色（见 6.2）

**建议**: 如果新功能需要新的 Icon/Panel，先与前端团队确认

---

## 九、前后端对接清单

### 9.1 后端必须实现的 API

| API | 方法 | 用途 | 优先级 |
|-----|------|------|--------|
| `/api/workspaces/{id}/features` | GET | 返回可用 features | **必须** |
| `/api/workspaces/{id}/features/{fid}/execute` | POST | 执行 feature | **必须** |
| `/api/tasks/{id}/stream` | GET | SSE 实时推送状态 | **必须** |
| `/api/tasks/{id}` | DELETE | 取消任务 | 推荐 |
| `/api/workspaces/{id}/artifacts` | GET | 获取成果列表 | 推荐 |

### 9.2 后端 API 响应格式检查

```bash
# 测试 Features API
curl http://localhost:8001/api/workspaces/{workspace_id}/features

# 期望响应
{
  "features": [
    {
      "id": "string",           # ✅ 必须
      "name": "string",         # ✅ 必须
      "description": "string",  # ✅ 必须
      "icon": "string",         # ✅ 必须
      "agent": "string",        # ✅ 必须
      "agentLabel": "string",   # ✅ 必须
      "panel": "string",        # ⚪ 可选
      "color": "string",        # ⚪ 可选
      "stages": [               # ✅ 必须（可为空数组）
        { "id": "string", "label": "string" }
      ]
    }
  ]
}
```

### 9.3 前端状态检查

```typescript
// 在浏览器控制台检查
useFeaturesStore.getState()
// 期望: { features: [...], isLoading: false, error: null }

useTaskStore.getState()
// 期望: { isExecuting: false, currentTask: null, ... }
```

### 9.4 SSE 事件格式检查

```bash
# 测试 SSE 流
curl -N http://localhost:8001/api/tasks/{task_id}/stream

# 期望事件格式
data: {"type": "stage_change", "stage_index": 1}
data: {"type": "thinking", "content": "正在处理..."}
data: {"type": "completed", "result": {...}}
```

### 9.5 对接调试流程

```
1. 后端实现 GET /features API
   ↓
2. 前端打开 workspace 页面，检查 QuickActions 是否显示
   ↓
3. 后端实现 POST /execute API 和 SSE
   ↓
4. 前端点击快捷指令，检查 AgentStatusBar 是否显示
   ↓
5. 检查 SSE 事件是否正确更新 thinking 和 stages
   ↓
6. 任务完成后检查 recentCompleted 提示
```

---

## 十、常见问题

### Q1: QuickActions 不显示？

检查：
1. `GET /features` API 是否返回数据
2. `features` 数组是否为空
3. 浏览器控制台是否有错误

### Q2: 点击快捷指令没反应？

检查：
1. `isExecuting` 是否为 true（任务执行中会禁用）
2. `getFeatureById` 是否返回 undefined
3. `startTask` 是否被调用

### Q3: AgentStatusBar 不显示阶段进度？

检查：
1. feature.stages 是否为空数组
2. SSE 是否发送 `stage_change` 事件
3. `advanceStage()` 是否被调用

### Q4: 如何添加新的 workspace 类型？

只需后端配置：
```python
WORKSPACE_FEATURES["new_type"] = [...]
```
前端会自动渲染，无需修改代码。

### Q5: 如何添加新的功能模块？

1. 后端添加 feature 配置到对应 workspace 类型
2. 如需新 Icon，前端修改 `iconMap`
3. 如需新 Panel，前端创建面板组件并注册

---

## 十一、更新日志

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2026-03-11 | v1.0 | 初始版本，定义可插拔 Features 系统 |
| 2026-03-11 | v1.1 | 新增可插拔性说明、对接清单、常见问题 |
