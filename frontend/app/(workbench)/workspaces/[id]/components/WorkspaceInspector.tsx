"use client";

import { useMemo, useState } from "react";
import { Activity, BookOpen, BriefcaseBusiness, FileText } from "lucide-react";
import type { ExecutionSession } from "@/lib/api";
import {
  type ExecutionCurrentTask,
  buildExecutionCurrentTask,
} from "@/lib/execution-presenters";
import { useWorkspaceStore, type Artifact } from "@/stores/workspace";
import { useExecutionStore } from "@/stores/execution";
import { useFeaturesStore } from "@/stores/features";
import { ArtifactLibrary } from "@/components/workspace/ArtifactLibrary";
import { ComputeStage } from "@/components/compute";
import { ArtifactDetailDialog } from "@/components/workspace/ArtifactDetailDialog";
import { TaskRuntimePanel } from "@/components/workspace/TaskRuntimePanel";
import { KnowledgePanel } from "./KnowledgePanel";
import { LiteraturePanel } from "./LiteraturePanel";
import { cn } from "@/lib/utils";

type InspectorTab = "work" | "outputs" | "sources" | "activity";
const EMPTY_EXECUTION_SESSIONS: ExecutionSession[] = [];
const EMPTY_EXECUTION_IDS: string[] = [];

interface WorkspaceInspectorProps {
  workspaceId: string;
}

const inspectorTabs: Array<{
  id: InspectorTab;
  label: string;
  icon: typeof FileText;
  description: string;
}> = [
  {
    id: "outputs",
    label: "成果",
    icon: FileText,
    description: "查看已经沉淀下来的草稿、结构化结果与交付物。",
  },
  {
    id: "sources",
    label: "文献",
    icon: BookOpen,
    description: "把上传的 PDF、文献信息与抽取状态留在当前主线旁边。",
  },
  {
    id: "activity",
    label: "活动",
    icon: Activity,
    description: "按时间线回看模块执行、对话推进与子代理活动。",
  },
];

function formatRuntimeTimestamp(value?: string): string {
  if (!value) {
    return "N/A";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function buildTaskRuntimeState(task: ExecutionCurrentTask | null) {
  if (!task) {
    return null;
  }

  return {
    title: task.agentLabel,
    current_phase: task.stages[task.currentStageIndex]?.id,
    phases: task.stages.map((stage, index) => ({
      id: stage.id,
      label: stage.label,
      description:
        stage.status === "running"
          ? "当前阶段正在推进中"
          : stage.status === "completed"
            ? "该阶段已完成"
            : "等待进入该阶段",
      status: stage.status,
      progress:
        stage.status === "completed"
          ? 100
          : stage.status === "running"
            ? Math.max(
                12,
                Math.round(((index + 1) / Math.max(task.stages.length, 1)) * 100)
              )
            : 0,
    })),
    blocks: [
      {
        id: "task-metrics",
        kind: "metrics" as const,
        title: "任务信息",
        entries: [
          { label: "Task", value: task.id.slice(0, 8) },
          { label: "Agent", value: task.agentLabel },
          { label: "Started", value: formatRuntimeTimestamp(task.startedAt) },
          {
            label: "Updated",
            value: formatRuntimeTimestamp(task.completedAt || task.startedAt),
          },
        ],
      },
      {
        id: "task-thinking",
        kind: "text" as const,
        title: "当前说明",
        content: task.thinking?.trim() || "任务已启动，等待更多运行时信息。",
      },
    ],
    updated_at: task.completedAt || task.startedAt,
  };
}

export function WorkspaceInspector({ workspaceId }: WorkspaceInspectorProps) {
  const artifacts = useWorkspaceStore((state) => state.artifacts);
  const papers = useWorkspaceStore((state) => state.papers);
  const activities = useWorkspaceStore((state) => state.activities);
  const executionSessions = useExecutionStore(
    (state) => state.byWorkspace[workspaceId] ?? EMPTY_EXECUTION_SESSIONS
  );
  const dismissedExecutionIds = useExecutionStore(
    (state) =>
      state.dismissedExecutionIdsByWorkspace[workspaceId] ?? EMPTY_EXECUTION_IDS
  );
  const activeExecutionId = useExecutionStore(
    (state) => state.activeExecutionIdByWorkspace[workspaceId] ?? null
  );
  const getFeatureById = useFeaturesStore((state) => state.getFeatureById);
  const visibleExecutions = useMemo(
    () =>
      executionSessions.filter(
        (execution) => !dismissedExecutionIds.includes(execution.id)
      ),
    [dismissedExecutionIds, executionSessions]
  );
  const activeExecution =
    visibleExecutions.find(
      (execution) => execution.id === activeExecutionId
    ) ??
    visibleExecutions.find(
      (execution) =>
        execution.status === "running" ||
        execution.status === "pending" ||
        execution.status === "awaiting_user_input"
    ) ?? null;
  const latestCompletedExecution =
    [...visibleExecutions]
      .filter((execution) => execution.status === "completed")
      .sort((left, right) =>
        String(right.updated_at || right.created_at || "").localeCompare(
          String(left.updated_at || left.created_at || "")
        )
      )[0] ?? null;
  const hasActiveWork = visibleExecutions.length > 0;
  const [preferredTab, setPreferredTab] = useState<InspectorTab>("outputs");
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);
  const visibleRuntimeTask =
    (activeExecution
      ? buildExecutionCurrentTask(
          activeExecution,
          getFeatureById(activeExecution.feature_id)
        )
      : latestCompletedExecution
        ? buildExecutionCurrentTask(
            latestCompletedExecution,
            getFeatureById(latestCompletedExecution.feature_id)
          )
        : null);
  const runtimeState = useMemo(
    () => buildTaskRuntimeState(visibleRuntimeTask),
    [visibleRuntimeTask]
  );
  const runtimeStatus = visibleRuntimeTask?.status ?? null;
  const runtimeError =
    visibleRuntimeTask?.status === "failed"
      ? visibleRuntimeTask.thinking.replace(/^错误:\s*/, "").trim()
      : null;
  const activeTab: InspectorTab = hasActiveWork
    ? preferredTab === "outputs"
      ? "work"
      : preferredTab
    : preferredTab === "work"
      ? "outputs"
      : preferredTab;

  const counts = useMemo(
    () => ({
      work: visibleExecutions.length,
      outputs: artifacts.length,
      sources: papers.length,
      activity: activities.length,
    }),
    [
      activities.length,
      artifacts.length,
      visibleExecutions.length,
      papers.length,
    ]
  );
  const visibleTabs = useMemo(() => {
    const tabs = [...inspectorTabs];
    if (hasActiveWork) {
      tabs.unshift({
        id: "work",
        label: "工作面",
        icon: BriefcaseBusiness,
        description: "展示当前 feature 的工作流、状态、中间结果与最终产出。",
      });
    }
    return tabs;
  }, [hasActiveWork]);
  const activeTabMeta =
    visibleTabs.find((tab) => tab.id === activeTab) ?? visibleTabs[0];

  return (
    <>
      <aside className="inspector-panel flex h-full min-h-[420px] flex-col overflow-hidden rounded-[1.75rem]">
        <div className="border-b border-[var(--border-default)] px-4 py-4">
          <p className="section-accent text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
            Inspector
          </p>
          <h2 className="mt-2 text-lg font-semibold text-[var(--text-primary)]">
            证据与成果
          </h2>
          <p className="mt-1 text-xs leading-6 text-[var(--text-secondary)]">
            在当前主线旁边查看文献、活动与已沉淀产物。
          </p>
          <div className="mt-4 flex gap-2">
            {visibleTabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setPreferredTab(tab.id)}
                className={cn(
                  "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                  activeTab === tab.id
                    ? "border-[var(--accent-primary)]/25 bg-[var(--accent-primary)]/12 text-[var(--accent-primary)] shadow-sm"
                    : "border-[var(--border-default)] bg-white/78 text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]"
                )}
              >
                <tab.icon className="h-3.5 w-3.5" />
                <span>{tab.label}</span>
                <span className="rounded-full bg-white/80 px-1.5 py-0.5 text-[10px] text-[var(--text-muted)]">
                  {counts[tab.id]}
                </span>
              </button>
            ))}
          </div>
          {activeTabMeta ? (
            <p className="mt-3 text-xs leading-6 text-[var(--text-muted)]">
              {activeTabMeta.description}
            </p>
          ) : null}
        </div>

        <div className="min-h-0 flex flex-1 flex-col overflow-hidden">
          {runtimeState ? (
            <div className="border-b border-[var(--border-default)] bg-[rgba(251,248,242,0.72)] px-3 py-3">
              <TaskRuntimePanel
                runtime={runtimeState}
                isRunning={visibleRuntimeTask?.status === "running"}
                status={runtimeStatus}
                error={runtimeError}
                title="当前运行时"
                className="rounded-2xl p-4"
              />
            </div>
          ) : null}

          <div className="min-h-0 flex-1 overflow-hidden">
            {activeTab === "work" ? (
              <ComputeStage
                workspaceId={workspaceId}
                activeExecution={activeExecution ?? latestCompletedExecution}
              />
            ) : null}
            {activeTab === "outputs" ? (
              <ArtifactLibrary onSelectArtifact={setSelectedArtifact} embedded />
            ) : null}
            {activeTab === "sources" ? (
              <LiteraturePanel workspaceId={workspaceId} embedded />
            ) : null}
            {activeTab === "activity" ? (
              <div className="h-full p-3">
                <KnowledgePanel workspaceId={workspaceId} embedded />
              </div>
            ) : null}
          </div>
        </div>
      </aside>

      <ArtifactDetailDialog
        artifact={selectedArtifact}
        open={selectedArtifact !== null}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedArtifact(null);
          }
        }}
      />
    </>
  );
}
