# 毕业论文 Workspace 前端设计方案

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to create the implementation plan.

**Goal:** 设计本科毕业论文workspace的前端交互体验，突出多智能体协作可视化亮点，平衡自由度与结构化引导。

**Design Principles:**
- 精简展示，不堆砌信息
- 多智能体执行过程可视化（核心亮点）
- 单任务执行，允许页面切换
- 动态面板，根据上下文切换

---

## 一、整体布局

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ← 返回    [毕业论文] 我的毕业论文 - 深度学习推荐系统研究      [计算机科学]  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────┐   ┌────────────────────────────────┐   ┌───────────────┐   │
│  │          │   │                            │   │               │   │
│  │  成果库  │   │       对话工作区            │   │   工具面板     │   │
│  │          │   │                            │   │   (动态切换)   │   │
│  │  📄 大纲  │   │  ┌──────────────────────┐ │   │               │   │
│  │  📝 摘要  │   │  │  消息历史...         │ │   │  [大纲编辑器]  │   │
│  │  📚 综述  │   │  │                      │ │   │  [文献列表]    │   │
│  │  📊 图表  │   │  │                      │ │   │  [LaTeX预览]   │   │
│  │  📦 导出  │   │  └──────────────────────┘ │   │  [执行日志]     │   │
│  │          │   │                            │   │               │   │
│  └──────────┘   │  ┌──────────────────────────┐│   └───────────────┘   │
│                 │  │ ⚡ Agent执行状态栏       ││                       │
│                 │  │ [ThesisWriter] → [Librarian] │                     │
│                 │  │ 💭 正在搜索相关文献...   ││                       │
│                 │  └──────────────────────────┘│                       │
│                 │  ┌──────────────────────────┐│                       │
│                 │  │ [生成大纲][文献综述][章节写作]│ ← 快捷指令         │
│                 │  │ 请输入你的需求...        ││                       │
│                 │  └──────────────────────────┘│                       │
│                 └────────────────────────────────┘                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、Agent执行状态栏（核心亮点）

**位置：** 固定在输入框上方，始终可见

**设计原则：** 只显示关键信息，精简不堆砌

### 三种状态

#### 1. 空闲状态
```
┌─────────────────────────────────────────────────────────────┐
│  💡 选择快捷指令或直接描述你的需求                            │
└─────────────────────────────────────────────────────────────┘
```

#### 2. 执行中状态
```
┌─────────────────────────────────────────────────────────────┐
│  ⚡ ThesisWriter 正在工作...              [详情] [取消]     │
│                                                             │
│  ┌───────┐     ┌───────┐     ┌───────┐                    │
│  │  ✅   │────▶│  🔄  │────▶│  ⏳  │                    │
│  │规划   │     │写作  │     │润色  │                    │
│  └───────┘     └───────┘     └───────┘                    │
│   已完成        正在执行       等待中                        │
│                                                             │
│  💭 "正在根据大纲生成第三章内容..."   ← 当前思考（单行滚动）  │
└─────────────────────────────────────────────────────────────┘
```

#### 3. 完成状态（3秒后自动消失）
```
┌─────────────────────────────────────────────────────────────┐
│  ✅ 大纲生成完成！已保存到成果库                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、快捷指令设计

**位置：** 输入框上方，chip按钮形式

### 毕业论文专用指令

| 指令 | 触发的Agent | 右侧面板切换 |
|-----|------------|-------------|
| 生成大纲 | thesis_writer | 大纲编辑器 |
| 文献综述 | librarian + thesis_writer | 文献列表 + 编辑器 |
| 章节写作 | thesis_writer | 章节编辑器 |
| 图表规划 | figure_planner | 图表预览 |
| 编译预览 | sandbox (latex) | LaTeX预览 + PDF |
| 导出PDF | sandbox | 下载面板 |

### 执行中的禁用逻辑

- 有任务执行时，所有快捷指令变为灰色
- Tooltip显示 "请等待当前任务完成"
- 输入框仍可用，但发送时提示 "请先完成或取消当前任务"

---

## 四、右侧工具面板（动态切换）

### 大纲编辑器
```
┌───────────────────────┐
│  📝 大纲编辑器         │
├───────────────────────┤
│  第一章 绪论          ▼│
│    1.1 研究背景        │
│    1.2 研究意义        │
│  第二章 文献综述      ▼│
│    2.1 国内研究现状    │
│    2.2 国外研究现状    │
│  ...                   │
│  [编辑] [重新生成]     │
└───────────────────────┘
```

### 文献列表
```
┌───────────────────────┐
│  📚 文献列表           │
├───────────────────────┤
│  ☑ Smith et al. 2023  │
│    Deep Learning...   │
│  ☑ Wang et al. 2022   │
│    Recommendation...  │
│  ☐ Li et al. 2021     │
│    Neural Network...  │
│  ──────────────────── │
│  已选: 2/15  [添加更多]│
└───────────────────────┘
```

### LaTeX预览
```
┌───────────────────────┐
│  📄 LaTeX预览          │
├───────────────────────┤
│  ┌─────────────────┐  │
│  │                 │  │
│  │   PDF 预览      │  │
│  │                 │  │
│  └─────────────────┘  │
│  编译状态: ✅ 成功     │
│  [全屏] [下载PDF]     │
└───────────────────────┘
```

---

## 五、任务队列机制

### 核心原则

**单任务执行，允许页面切换**
- 同时只能有一个Agent任务在执行
- 用户可以切换查看其他页面（如查看已生成的成果）
- 想启动新任务时，需先完成或取消当前任务

### 前端状态管理

```typescript
interface TaskState {
  isExecuting: boolean;
  currentTask: {
    id: string;
    type: 'outline' | 'literature' | 'chapter' | 'figure' | 'compile';
    status: 'running' | 'completed' | 'cancelled';
    agent: string;
    thinking: string;  // 当前思考（单行）
    stages: Stage[];   // 阶段进度
  } | null;
}

interface Stage {
  id: string;
  label: string;
  status: 'completed' | 'running' | 'pending';
}

// 启动新任务时检查
function startTask(taskType: string) {
  if (taskState.isExecuting) {
    toast.warning('请先完成或取消当前任务');
    return;
  }
  // ... 启动任务
}
```

---

## 六、后端API设计（新增）

### 获取Workspace功能列表
```
GET /api/workspaces/{id}/features

Response:
{
  "features": [
    {
      "id": "outline",
      "name": "生成大纲",
      "description": "根据研究主题生成论文大纲",
      "icon": "list",
      "agent_type": "thesis_writer"
    },
    ...
  ]
}
```

### 任务管理
```
POST /api/workspaces/{id}/tasks
Request: { "type": "outline", "params": {...} }
Response: { "task_id": "xxx", "status": "running" }

GET /api/workspaces/{id}/tasks/current
Response: { "task": {...}, "thinking": "...", "stages": [...] }

POST /api/workspaces/{id}/tasks/cancel
Response: { "success": true }
```

### 成果管理
```
GET /api/workspaces/{id}/artifacts
GET /api/workspaces/{id}/artifacts/{artifactId}
```

---

## 七、成果库（左侧面板）

只显示**已生成**的内容，按类型分类：

- 📄 **论文大纲** - 点击展开/编辑
- 📝 **摘要** - 中英文摘要
- 📚 **文献综述** - 已完成的综述
- 📊 **图表** - 已生成的图表
- 📦 **导出** - PDF/Word导出入口

---

## 八、技术实现要点

### 前端
- React 19 + Next.js 16
- Framer Motion 动画
- Zustand 状态管理
- SSE 实时推送Agent状态

### 后端
- FastAPI + LangGraph
- SubagentRegistry (已实现)
- Memory系统 (已实现)
- Sandbox执行器 (已实现)

---

## 九、待实现文件清单

### 前端新建文件
1. `components/thesis/AgentStatusBar.tsx` - Agent执行状态栏
2. `components/thesis/QuickActions.tsx` - 快捷指令
3. `components/thesis/OutlineEditor.tsx` - 大纲编辑器
4. `components/thesis/LiteraturePanel.tsx` - 文献列表面板
5. `components/thesis/LatexPreview.tsx` - LaTeX预览
6. `components/thesis/ArtifactLibrary.tsx` - 成果库
7. `stores/task.ts` - 任务状态管理

### 前端修改文件
1. `app/(workbench)/workspaces/[id]/page.tsx` - 主页面布局
2. `app/(workbench)/workspaces/[id]/components/ChatPanel.tsx` - 集成状态栏
3. `lib/api.ts` - 新增API调用

### 后端新建文件
1. `src/gateway/routers/tasks.py` - 任务管理API
2. `src/gateway/routers/artifacts.py` - 成果管理API

---

## Approval

- User approved on: 2026-03-11
