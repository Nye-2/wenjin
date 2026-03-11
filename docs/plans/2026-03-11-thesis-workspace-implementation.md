# 通用 Workspace 前端实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现通用Workspace前端模板，支持可插拔的Features系统。不同workspace类型（thesis/sci/proposal/patent等）通过后端配置的功能模块来区分，前端根据动态获取的features渲染UI。

**Architecture:**
- 通用Workspace模板 + 可插拔Features
- 后端API返回workspace可用的skills/agents/features
- 前端动态渲染QuickActions、面板等组件
- 使用Zustand管理任务执行状态，SSE实时推送Agent状态

**Tech Stack:** React 19, Next.js 16, Zustand, Framer Motion, Tailwind CSS, SSE

---

## 核心设计理念

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
│   • QuickActions (从features渲染，无硬编码)                     │
│   • FeaturePanel (根据feature.panel动态切换)                   │
│   • AgentStatusBar (通用，从feature.stages获取阶段)            │
│   • ArtifactLibrary (通用)                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Task 1: 添加 Features API

**Files:**
- Modify: `frontend/lib/api.ts`

**Step 1: 添加 Features 类型定义和 API 函数**

在 `lib/api.ts` 中添加：

```typescript
// ============ Feature Types ============

export interface FeatureStage {
  id: string;
  label: string;
}

export interface WorkspaceFeature {
  id: string;
  name: string;
  description: string;
  icon: string;  // icon name string, to be resolved by frontend
  agent: string;
  agentLabel: string;
  panel?: string;  // which panel to show in right sidebar
  stages: FeatureStage[];
  color?: string;
}

// ============ Features API ============

export async function getWorkspaceFeatures(
  workspaceId: string
): Promise<{ features: WorkspaceFeature[] }> {
  const response = await apiClient.get(`/workspaces/${workspaceId}/features`);
  return response.data;
}
```

**Step 2: 运行类型检查**

Run: `cd /home/cjz/academiagpt-v2/frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat: add workspace features API types and function"
```

---

## Task 2: 创建任务状态管理 Store

**Files:**
- Create: `frontend/stores/task.ts`

**Step 1: 创建任务状态 Store**

```typescript
// frontend/stores/task.ts

import { create } from 'zustand';
import type { FeatureStage } from '@/lib/api';

// 任务阶段状态
export interface TaskStage extends FeatureStage {
  status: 'completed' | 'running' | 'pending';
}

// 当前执行的任务
export interface CurrentTask {
  id: string;
  featureId: string;  // 对应的feature id
  status: 'running' | 'completed' | 'cancelled' | 'failed';
  agent: string;
  agentLabel: string;
  thinking: string;
  stages: TaskStage[];
  currentStageIndex: number;
  startedAt: string;
  completedAt?: string;
}

// 任务状态
interface TaskState {
  isExecuting: boolean;
  currentTask: CurrentTask | null;
  recentCompleted: CurrentTask | null;

  // Actions
  startTask: (params: {
    featureId: string;
    agent: string;
    agentLabel: string;
    stages: FeatureStage[];
    initialThinking?: string;
  }) => string;
  updateTaskThinking: (thinking: string) => void;
  advanceStage: () => void;
  completeTask: () => void;
  cancelTask: () => void;
  failTask: (error: string) => void;
  clearRecentCompleted: () => void;
}

export const useTaskStore = create<TaskState>((set, get) => ({
  isExecuting: false,
  currentTask: null,
  recentCompleted: null,

  startTask: (params) => {
    const id = `task-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    const stagesWithStatus: TaskStage[] = params.stages.map((s, i) => ({
      ...s,
      status: i === 0 ? 'running' : 'pending',
    }));

    set({
      isExecuting: true,
      currentTask: {
        id,
        featureId: params.featureId,
        status: 'running',
        agent: params.agent,
        agentLabel: params.agentLabel,
        thinking: params.initialThinking || '',
        stages: stagesWithStatus,
        currentStageIndex: 0,
        startedAt: new Date().toISOString(),
      },
      recentCompleted: null,
    });
    return id;
  },

  updateTaskThinking: (thinking) => {
    set((state) => ({
      currentTask: state.currentTask
        ? { ...state.currentTask, thinking }
        : null,
    }));
  },

  advanceStage: () => {
    set((state) => {
      if (!state.currentTask) return state;
      const nextIndex = state.currentTask.currentStageIndex + 1;
      const stages = state.currentTask.stages.map((s, i) => {
        if (i < nextIndex) return { ...s, status: 'completed' as const };
        if (i === nextIndex) return { ...s, status: 'running' as const };
        return { ...s, status: 'pending' as const };
      });
      return {
        currentTask: {
          ...state.currentTask,
          stages,
          currentStageIndex: nextIndex,
        },
      };
    });
  },

  completeTask: () => {
    const { currentTask } = get();
    if (!currentTask) return;

    const completedTask = {
      ...currentTask,
      status: 'completed' as const,
      completedAt: new Date().toISOString(),
      stages: currentTask.stages.map((s) => ({
        ...s,
        status: 'completed' as const,
      })),
    };

    set({
      isExecuting: false,
      currentTask: null,
      recentCompleted: completedTask,
    });

    setTimeout(() => {
      set({ recentCompleted: null });
    }, 3000);
  },

  cancelTask: () => {
    set({
      isExecuting: false,
      currentTask: null,
      recentCompleted: null,
    });
  },

  failTask: (error) => {
    set((state) => ({
      isExecuting: false,
      currentTask: state.currentTask
        ? {
            ...state.currentTask,
            status: 'failed',
            thinking: `错误: ${error}`,
          }
        : null,
    }));
  },

  clearRecentCompleted: () => {
    set({ recentCompleted: null });
  },
}));

export default useTaskStore;
```

**Step 2: 运行类型检查**

Run: `cd /home/cjz/academiagpt-v2/frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/stores/task.ts
git commit -m "feat: add task state management store with dynamic stages"
```

---

## Task 3: 创建 Workspace Features Store

**Files:**
- Create: `frontend/stores/features.ts`

**Step 1: 创建 Features Store**

```typescript
// frontend/stores/features.ts

import { create } from 'zustand';
import { getWorkspaceFeatures, WorkspaceFeature } from '@/lib/api';

interface FeaturesState {
  features: WorkspaceFeature[];
  isLoading: boolean;
  error: string | null;

  // Actions
  fetchFeatures: (workspaceId: string) => Promise<void>;
  getFeatureById: (featureId: string) => WorkspaceFeature | undefined;
  clearFeatures: () => void;
}

export const useFeaturesStore = create<FeaturesState>((set, get) => ({
  features: [],
  isLoading: false,
  error: null,

  fetchFeatures: async (workspaceId: string) => {
    set({ isLoading: true, error: null });
    try {
      const response = await getWorkspaceFeatures(workspaceId);
      set({ features: response.features, isLoading: false });
    } catch (error) {
      set({
        error: (error as Error).message,
        isLoading: false,
        features: [],
      });
    }
  },

  getFeatureById: (featureId: string) => {
    return get().features.find((f) => f.id === featureId);
  },

  clearFeatures: () => {
    set({ features: [], error: null });
  },
}));

export default useFeaturesStore;
```

**Step 2: Commit**

```bash
git add frontend/stores/features.ts
git commit -m "feat: add workspace features store"
```

---

## Task 4: 创建动态快捷指令组件

**Files:**
- Create: `frontend/components/workspace/QuickActions.tsx`

**Step 1: 创建完全动态的快捷指令组件**

```typescript
// frontend/components/workspace/QuickActions.tsx

"use client";

import { motion } from "framer-motion";
import {
  ListOrdered,
  BookOpen,
  PenTool,
  BarChart3,
  FileText,
  Download,
  Search,
  FlaskConical,
  FileEdit,
  Lightbulb,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTaskStore } from "@/stores/task";
import { useFeaturesStore } from "@/stores/features";

// Icon映射表 - 将icon name string映射到组件
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

// 颜色映射表
const colorMap: Record<string, string> = {
  purple: "text-purple-500",
  blue: "text-blue-500",
  emerald: "text-emerald-500",
  amber: "text-amber-500",
  cyan: "text-cyan-500",
  rose: "text-rose-500",
  indigo: "text-indigo-500",
};

interface QuickActionsProps {
  onAction: (featureId: string) => void;
}

export function QuickActions({ onAction }: QuickActionsProps) {
  const { features } = useFeaturesStore();
  const { isExecuting } = useTaskStore();

  const handleAction = (featureId: string) => {
    if (isExecuting) return;
    onAction(featureId);
  };

  if (features.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap gap-2">
      {features.map((feature) => {
        const Icon = iconMap[feature.icon] || FileText;
        const colorClass = colorMap[feature.color || ""] || "text-[var(--text-primary)]";
        const isDisabled = isExecuting;

        return (
          <motion.button
            key={feature.id}
            onClick={() => handleAction(feature.id)}
            disabled={isDisabled}
            className={cn(
              "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium",
              "border border-[var(--border-default)] transition-all duration-200",
              "disabled:opacity-50 disabled:cursor-not-allowed",
              isDisabled
                ? "bg-[var(--bg-surface)] text-[var(--text-muted)]"
                : cn(
                    "bg-[var(--bg-surface)]",
                    "hover:bg-[var(--bg-muted)]",
                    colorClass
                  )
            )}
            whileHover={isDisabled ? {} : { scale: 1.02 }}
            whileTap={isDisabled ? {} : { scale: 0.98 }}
            title={isDisabled ? "请等待当前任务完成" : feature.description}
          >
            <Icon className="w-3.5 h-3.5" />
            {feature.name}
          </motion.button>
        );
      })}
    </div>
  );
}
```

**Step 2: 运行类型检查**

Run: `cd /home/cjz/academiagpt-v2/frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/components/workspace/QuickActions.tsx
git commit -m "feat: add dynamic quick actions component"
```

---

## Task 5: 创建 Agent 执行状态栏组件

**Files:**
- Create: `frontend/components/workspace/AgentStatusBar.tsx`

**Step 1: 创建通用状态栏组件**

```typescript
// frontend/components/workspace/AgentStatusBar.tsx

"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Check, Loader2, X, ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { useTaskStore } from "@/stores/task";

function StageNode({
  label,
  status,
}: {
  label: string;
  status: "completed" | "running" | "pending";
}) {
  return (
    <div className="flex flex-col items-center gap-1">
      <div
        className={cn(
          "w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium transition-all duration-300",
          status === "completed" && "bg-emerald-500 text-white",
          status === "running" &&
            "bg-[var(--accent-primary)] text-white shadow-lg shadow-[var(--accent-primary)]/30",
          status === "pending" &&
            "bg-[var(--bg-surface)] text-[var(--text-muted)] border border-[var(--border-default)]"
        )}
      >
        {status === "completed" && <Check className="w-4 h-4" />}
        {status === "running" && <Loader2 className="w-4 h-4 animate-spin" />}
        {status === "pending" && <span>○</span>}
      </div>
      <span
        className={cn(
          "text-[10px] whitespace-nowrap transition-colors",
          status === "completed" && "text-emerald-600",
          status === "running" && "text-[var(--accent-primary)] font-medium",
          status === "pending" && "text-[var(--text-muted)]"
        )}
      >
        {label}
      </span>
    </div>
  );
}

function StageConnector({ isCompleted }: { isCompleted: boolean }) {
  return (
    <div
      className={cn(
        "w-8 h-0.5 transition-colors duration-300",
        isCompleted ? "bg-emerald-500" : "bg-[var(--border-default)]"
      )}
    />
  );
}

export function AgentStatusBar() {
  const { currentTask, recentCompleted, cancelTask, clearRecentCompleted } =
    useTaskStore();
  const [isExpanded, setIsExpanded] = useState(true);

  // 完成状态提示
  if (recentCompleted) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
        className="flex items-center gap-2 px-4 py-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-600"
      >
        <Check className="w-5 h-5" />
        <span className="text-sm font-medium">任务完成！</span>
        <button
          onClick={clearRecentCompleted}
          className="ml-auto text-emerald-600/70 hover:text-emerald-600"
        >
          <X className="w-4 h-4" />
        </button>
      </motion.div>
    );
  }

  // 空闲状态
  if (!currentTask) {
    return null;
  }

  const { agentLabel, thinking, stages } = currentTask;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className="rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-default)] overflow-hidden"
    >
      {/* 头部 */}
      <div
        className="flex items-center justify-between px-4 py-2 cursor-pointer hover:bg-[var(--bg-surface)] transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin text-[var(--accent-primary)]" />
          <span className="text-sm font-medium text-[var(--text-primary)]">
            {agentLabel} 正在工作...
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              cancelTask();
            }}
            className="text-xs text-[var(--text-muted)] hover:text-red-500 transition-colors px-2 py-1 rounded hover:bg-red-500/10"
          >
            取消
          </button>
          {isExpanded ? (
            <ChevronUp className="w-4 h-4 text-[var(--text-muted)]" />
          ) : (
            <ChevronDown className="w-4 h-4 text-[var(--text-muted)]" />
          )}
        </div>
      </div>

      {/* 展开内容 */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-3 pt-1">
              {/* 阶段进度 - 动态从stages渲染 */}
              {stages.length > 0 && (
                <div className="flex items-center justify-center gap-0 mb-3">
                  {stages.map((stage, index) => (
                    <div key={stage.id} className="flex items-center">
                      <StageNode label={stage.label} status={stage.status} />
                      {index < stages.length - 1 && (
                        <StageConnector
                          isCompleted={stage.status === "completed"}
                        />
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* 思考气泡 */}
              {thinking && (
                <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-[var(--bg-surface)]">
                  <span className="text-[var(--accent-primary)]">💭</span>
                  <p className="text-xs text-[var(--text-secondary)] line-clamp-2">
                    {thinking}
                  </p>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
```

**Step 2: 运行类型检查**

Run: `cd /home/cjz/academiagpt-v2/frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/components/workspace/AgentStatusBar.tsx
git commit -m "feat: add generic agent status bar component"
```

---

## Task 6: 创建成果库组件

**Files:**
- Create: `frontend/components/workspace/ArtifactLibrary.tsx`

**Step 1: 创建通用成果库组件**

```typescript
// frontend/components/workspace/ArtifactLibrary.tsx

"use client";

import { motion } from "framer-motion";
import {
  FileText,
  BookOpen,
  BarChart3,
  Download,
  File,
  ChevronRight,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useWorkspaceStore, Artifact } from "@/stores/workspace";

// Icon映射
const artifactIconMap: Record<string, LucideIcon> = {
  outline: FileText,
  abstract: FileText,
  literature_review: BookOpen,
  chapter: FileText,
  figure: BarChart3,
  table: BarChart3,
  research_idea: FileText,
  methodology: FileText,
  framework_outline: FileText,
  results_analysis: BarChart3,
  conclusion: FileText,
  note: File,
};

// 颜色映射
const artifactColorMap: Record<string, string> = {
  outline: "text-purple-500 bg-purple-500/10",
  abstract: "text-blue-500 bg-blue-500/10",
  literature_review: "text-emerald-500 bg-emerald-500/10",
  chapter: "text-amber-500 bg-amber-500/10",
  figure: "text-rose-500 bg-rose-500/10",
  table: "text-cyan-500 bg-cyan-500/10",
};

interface ArtifactLibraryProps {
  workspaceId: string;
  onSelectArtifact: (artifact: Artifact) => void;
  onExport?: () => void;
}

export function ArtifactLibrary({
  workspaceId,
  onSelectArtifact,
  onExport,
}: ArtifactLibraryProps) {
  const { artifacts } = useWorkspaceStore();

  // 按类型分组并排序
  const groupedArtifacts = artifacts.reduce((acc, artifact) => {
    const type = artifact.type || "default";
    if (!acc[type]) acc[type] = [];
    acc[type].push(artifact);
    return acc;
  }, {} as Record<string, Artifact[]>);

  // 显示顺序（可扩展）
  const typeOrder = [
    "outline",
    "abstract",
    "literature_review",
    "methodology",
    "chapter",
    "figure",
    "table",
    "results_analysis",
    "conclusion",
    "note",
  ];

  return (
    <div className="flex flex-col h-full">
      {/* 头部 */}
      <div className="px-4 py-3 border-b border-[var(--border-default)]">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">
          成果库
        </h3>
        <p className="text-xs text-[var(--text-muted)] mt-0.5">
          {artifacts.length} 个成果
        </p>
      </div>

      {/* 成果列表 */}
      <div className="flex-1 overflow-y-auto p-2">
        {artifacts.length === 0 ? (
          <div className="text-center py-8 text-[var(--text-muted)]">
            <File className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-xs">暂无成果</p>
            <p className="text-xs">开始对话以生成内容</p>
          </div>
        ) : (
          <div className="space-y-1">
            {/* 按顺序显示 */}
            {typeOrder.map((type) => {
              const items = groupedArtifacts[type];
              if (!items || items.length === 0) return null;

              const Icon = artifactIconMap[type] || File;
              const colorClass =
                artifactColorMap[type] ||
                "text-[var(--text-muted)] bg-[var(--bg-surface)]";

              return items.map((artifact) => (
                <motion.button
                  key={artifact.id}
                  onClick={() => onSelectArtifact(artifact)}
                  className={cn(
                    "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg",
                    "text-left hover:bg-[var(--bg-surface)] transition-colors"
                  )}
                  whileHover={{ x: 2 }}
                >
                  <div className={cn("p-1.5 rounded-lg", colorClass)}>
                    <Icon className="w-4 h-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-[var(--text-primary)] truncate">
                      {artifact.title || type}
                    </p>
                    <p className="text-xs text-[var(--text-muted)]">{type}</p>
                  </div>
                  <ChevronRight className="w-4 h-4 text-[var(--text-muted)]" />
                </motion.button>
              ));
            })}

            {/* 其他未分类类型 */}
            {Object.entries(groupedArtifacts)
              .filter(([type]) => !typeOrder.includes(type))
              .map(([type, items]) =>
                items.map((artifact) => (
                  <motion.button
                    key={artifact.id}
                    onClick={() => onSelectArtifact(artifact)}
                    className={cn(
                      "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg",
                      "text-left hover:bg-[var(--bg-surface)] transition-colors"
                    )}
                    whileHover={{ x: 2 }}
                  >
                    <div className="p-1.5 rounded-lg text-[var(--text-muted)] bg-[var(--bg-surface)]">
                      <File className="w-4 h-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-[var(--text-primary)] truncate">
                        {artifact.title || type}
                      </p>
                      <p className="text-xs text-[var(--text-muted)]">{type}</p>
                    </div>
                    <ChevronRight className="w-4 h-4 text-[var(--text-muted)]" />
                  </motion.button>
                ))
              )}
          </div>
        )}
      </div>

      {/* 导出按钮 */}
      {onExport && artifacts.length > 0 && (
        <div className="p-3 border-t border-[var(--border-default)]">
          <button
            onClick={onExport}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-[var(--accent-primary)] text-white text-sm font-medium hover:bg-[var(--accent-primary)]/90 transition-colors"
          >
            <Download className="w-4 h-4" />
            导出PDF
          </button>
        </div>
      )}
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/components/workspace/ArtifactLibrary.tsx
git commit -m "feat: add generic artifact library component"
```

---

## Task 7: 创建组件导出索引

**Files:**
- Create: `frontend/components/workspace/index.ts`

**Step 1: 创建索引文件**

```typescript
// frontend/components/workspace/index.ts

export { QuickActions } from "./QuickActions";
export { AgentStatusBar } from "./AgentStatusBar";
export { ArtifactLibrary } from "./ArtifactLibrary";
```

**Step 2: Commit**

```bash
git add frontend/components/workspace/index.ts
git commit -m "feat: add workspace components index"
```

---

## Task 8: 更新 ChatPanel 集成组件

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`

**Step 1: 添加导入和状态**

```typescript
// 在导入区域添加
import { AgentStatusBar, QuickActions } from "@/components/workspace";
import { useTaskStore } from "@/stores/task";
import { useFeaturesStore } from "@/stores/features";

// 在组件内部添加
const { startTask, isExecuting } = useTaskStore();
const { getFeatureById } = useFeaturesStore();
```

**Step 2: 添加快捷指令处理函数**

```typescript
// 处理快捷指令点击
const handleQuickAction = (featureId: string) => {
  if (isExecuting) return;

  const feature = getFeatureById(featureId);
  if (!feature) return;

  startTask({
    featureId: feature.id,
    agent: feature.agent,
    agentLabel: feature.agentLabel,
    stages: feature.stages,
    initialThinking: `正在准备执行 ${feature.name}...`,
  });

  // TODO: 同时调用后端API执行任务
  // executeFeature(workspaceId, featureId, params);
};
```

**Step 3: 在输入框上方添加组件**

```typescript
// 在渲染区域添加（输入框上方）
<div className="space-y-3">
  <AgentStatusBar />
  {!isExecuting && <QuickActions onAction={handleQuickAction} />}
  {/* 原有的输入框 */}
</div>
```

**Step 4: 运行类型检查**

Run: `cd /home/cjz/academiagpt-v2/frontend && npx tsc --noEmit`
Expected: No errors

**Step 5: Commit**

```bash
git add "frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx"
git commit -m "feat: integrate dynamic quick actions and agent status bar"
```

---

## Task 9: 更新 workspace page 加载 features

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/page.tsx`

**Step 1: 添加 features 加载**

```typescript
// 在导入区域添加
import { useFeaturesStore } from "@/stores/features";
import { ArtifactLibrary } from "@/components/workspace";

// 在组件内部添加
const { fetchFeatures, clearFeatures } = useFeaturesStore();

// 修改 useEffect
useEffect(() => {
  if (workspaceId) {
    loadWorkspace(workspaceId);
    fetchFeatures(workspaceId);  // 加载features
  }

  return () => {
    clearWorkspace();
    clearFeatures();  // 清理
  };
}, [workspaceId, loadWorkspace, clearWorkspace, fetchFeatures, clearFeatures]);
```

**Step 2: 添加 ArtifactLibrary 到左侧**

将左侧面板替换为 ArtifactLibrary 组件。

**Step 3: Commit**

```bash
git add "frontend/app/(workbench)/workspaces/[id]/page.tsx"
git commit -m "feat: load workspace features and add artifact library"
```

---

## Task 10: 验证和测试

**Step 1: 运行类型检查**

Run: `cd /home/cjz/academiagpt-v2/frontend && npx tsc --noEmit`
Expected: No errors

**Step 2: 运行开发服务器**

Run: `cd /home/cjz/academiagpt-v2/frontend && npm run dev`
Expected: Server starts without errors

**Step 3: 手动测试**

1. 打开一个 workspace
2. 验证快捷指令根据 workspace type 动态显示
3. 点击一个快捷指令，验证 AgentStatusBar 出现
4. 验证状态栏显示动态获取的阶段
5. 验证成果库显示正确

---

## 后续工作（不在本计划范围）

1. **后端 API 实现** - `GET /api/workspaces/{id}/features`
2. **Feature 执行 API** - 调用 subagent 执行任务
3. **SSE 实时推送** - 实时更新 thinking 和 stage
4. **右侧动态面板** - FeaturePanel 组件

---

## 执行选择

**Plan complete and saved to `docs/plans/2026-03-11-thesis-workspace-implementation.md`.**

**Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
