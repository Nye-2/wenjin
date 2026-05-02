"use client";

import { useMemo } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  ArrowLeft,
  BriefcaseBusiness,
  ChevronLeft,
  ChevronRight,
  Clock3,
  LayoutDashboard,
  Loader2,
  MessageSquare,
} from "lucide-react";
import {
  adaptExecutionToPanelSession,
  groupExecutionSessions,
} from "@/lib/execution-presenters";
import type { ExecutionSession } from "@/lib/api";
import { useExecutionStore } from "@/stores/execution";
import { useFeaturesStore } from "@/stores/features";
import { useWorkspaceStore } from "@/stores/workspace";
import { useI18n } from "@/components/i18n-provider";
import { ACTIVE_EXECUTION_STATUSES } from "@/lib/execution-status";
import { cn } from "@/lib/utils";

interface AppShellSidebarProps {
  workspaceId: string;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}
const EMPTY_EXECUTION_SESSIONS: ExecutionSession[] = [];
const EMPTY_EXECUTION_IDS: string[] = [];

function sessionStatusTone(status: string) {
  if (status === "running" || status === "pending") {
    return "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]";
  }
  if (status === "success") {
    return "bg-emerald-500/10 text-emerald-700";
  }
  if (status === "failed") {
    return "bg-red-500/10 text-red-700";
  }
  if (status === "cancelled") {
    return "bg-slate-500/10 text-slate-700";
  }
  return "bg-[var(--bg-surface)] text-[var(--text-muted)]";
}

function SessionGroup({
  title,
  sessions,
  activeSessionId,
  onOpenSession,
}: {
  title: string;
  sessions: Array<{
    executionId: string;
    taskId: string;
    title: string;
    status: string;
    updatedAt: string;
    message: string | null;
  }>;
  activeSessionId: string | null;
  onOpenSession: (executionId: string) => void;
}) {
  if (sessions.length === 0) {
    return null;
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between px-2.5">
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">
          {title}
        </p>
        <span className="rounded-full bg-white/80 px-1.5 py-0.5 text-[10px] text-[var(--text-muted)]">
          {sessions.length}
        </span>
      </div>
      {sessions.map((session) => {
        const isActive = activeSessionId === session.executionId;
        const isWorking = ACTIVE_EXECUTION_STATUSES.has(session.status as never);
        return (
          <button
            key={session.executionId}
            type="button"
            onClick={() => onOpenSession(session.executionId)}
            className={cn(
              "flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition-colors hover:bg-[var(--bg-surface)]",
              isActive && "bg-[rgba(166,124,57,0.06)]"
            )}
          >
            <div
              className={cn(
                "flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
                sessionStatusTone(session.status)
              )}
            >
              {isWorking ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <BriefcaseBusiness className="h-3.5 w-3.5" />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <p
                className={cn(
                  "truncate text-sm",
                  isActive
                    ? "font-medium text-[var(--text-primary)]"
                    : "text-[var(--text-secondary)]"
                )}
              >
                {session.title}
              </p>
              <p className="truncate text-[11px] text-[var(--text-muted)]">
                {session.message ||
                  `最近更新 ${new Date(session.updatedAt).toLocaleTimeString("zh-CN", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}`}
              </p>
            </div>
            {isActive ? (
              <span className="ml-auto rounded-full bg-[rgba(166,124,57,0.1)] px-1.5 py-0.5 text-[9px] font-medium text-[var(--brand-brass)]">
                当前
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

export function AppShellSidebar({
  workspaceId,
  collapsed = false,
  onToggleCollapse,
}: AppShellSidebarProps) {
  const router = useRouter();
  const pathname = usePathname() ?? "";
  const { t } = useI18n();

  const workspace = useWorkspaceStore((state) => state.workspace);
  const workspaces = useWorkspaceStore((state) => state.workspaces);
  const executionSessions = useExecutionStore(
    (state) => state.byWorkspace[workspaceId] ?? EMPTY_EXECUTION_SESSIONS
  );
  const activeExecutionId = useExecutionStore(
    (state) => state.activeExecutionIdByWorkspace[workspaceId] ?? null
  );
  const dismissedExecutionIds = useExecutionStore(
    (state) =>
      state.dismissedExecutionIdsByWorkspace[workspaceId] ?? EMPTY_EXECUTION_IDS
  );
  const setActiveExecution = useExecutionStore((state) => state.setActiveExecution);
  const getFeatureById = useFeaturesStore((state) => state.getFeatureById);
  const visibleExecutions = useMemo(
    () =>
      executionSessions.filter(
        (execution) => !dismissedExecutionIds.includes(execution.id)
      ),
    [dismissedExecutionIds, executionSessions]
  );
  const displaySessions = useMemo(
    () =>
      visibleExecutions.map((execution) =>
        adaptExecutionToPanelSession(
          execution,
          getFeatureById(execution.feature_id)
        )
      ),
    [getFeatureById, visibleExecutions]
  );
  const resolvedActiveSessionId =
    activeExecutionId &&
    displaySessions.some((session) => session.executionId === activeExecutionId)
      ? activeExecutionId
      : displaySessions[0]?.executionId ?? null;
  const groupedSessions = groupExecutionSessions(displaySessions);
  const primarySession =
    resolvedActiveSessionId
      ? displaySessions.find((session) => session.executionId === resolvedActiveSessionId) ?? displaySessions[0]
      : displaySessions[0];

  const isOnChat = pathname.startsWith(`/workspaces/${workspaceId}/chat`);
  const isOnDashboard = pathname === `/workspaces/${workspaceId}`;

  const workspaceSnapshot =
    workspace ?? workspaces.find((c) => c.id === workspaceId) ?? null;
  const workspaceName = workspaceSnapshot?.name ?? "Workspace";
  const workspaceTypeLabel = workspaceSnapshot?.type
    ? t(`workspace.types.${workspaceSnapshot.type}`)
    : "";
  const disciplineLabel = workspaceSnapshot?.discipline
    ? workspaceSnapshot.discipline.replace(/_/g, " ")
    : null;

  const goToDashboard = () => router.push(`/workspaces/${workspaceId}`);
  const goToChat = () => router.push(`/workspaces/${workspaceId}/chat`);
  const handleOpenSession = (executionId: string) => {
    setActiveExecution(workspaceId, executionId);
    router.push(`/workspaces/${workspaceId}/chat`);
  };

  if (collapsed) {
    return (
      <aside className="flex w-14 shrink-0 flex-col items-center gap-2 border-r border-[var(--border-default)] bg-[rgba(251,248,242,0.92)] py-3">
        <button
          onClick={onToggleCollapse}
          className="rounded-xl p-2 text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-surface)]"
          title="Expand sidebar"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
        <button
          onClick={goToDashboard}
          className={cn(
            "rounded-xl p-2 transition-colors",
            isOnDashboard
              ? "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]"
              : "text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]"
          )}
          title="工作总览"
        >
          <LayoutDashboard className="h-4 w-4" />
        </button>
        <button
          onClick={goToChat}
          className={cn(
            "rounded-xl p-2 transition-colors",
            isOnChat
              ? "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]"
              : "text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]"
          )}
          title="对话"
        >
          <MessageSquare className="h-4 w-4" />
        </button>
        <button
          onClick={() => router.push("/workspaces")}
          className="mt-auto rounded-xl p-2 text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-surface)]"
          title="全部 workspace"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
      </aside>
    );
  }

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-[var(--border-default)] bg-[rgba(251,248,242,0.94)]">
      {/* Workspace info — compact */}
      <div className="border-b border-[var(--border-default)] px-4 py-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-[var(--text-primary)]">
              {workspaceName}
            </h2>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {workspaceTypeLabel && (
                <span className="rounded-full border border-[var(--border-default)] bg-white/78 px-2.5 py-0.5 text-[11px] font-medium text-[var(--text-primary)]">
                  {workspaceTypeLabel}
                </span>
              )}
              {disciplineLabel && (
                <span className="rounded-full border border-[var(--border-default)] bg-[var(--bg-surface)] px-2.5 py-0.5 text-[11px] text-[var(--text-secondary)]">
                  {disciplineLabel}
                </span>
              )}
            </div>
          </div>
          <button
            onClick={onToggleCollapse}
            className="rounded-xl p-1.5 text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-surface)]"
            title="Collapse sidebar"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Work sessions */}
      <div className="border-b border-[var(--border-default)] px-4 py-3">
        <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
          工作面
        </p>
        {displaySessions.length > 0 ? (
          <div className="mt-2.5 space-y-3">
            <SessionGroup
              title="进行中"
              sessions={groupedSessions.active}
              activeSessionId={resolvedActiveSessionId}
              onOpenSession={handleOpenSession}
            />
            <SessionGroup
              title="最近完成"
              sessions={groupedSessions.recent}
              activeSessionId={resolvedActiveSessionId}
              onOpenSession={handleOpenSession}
            />
            <SessionGroup
              title="更早记录"
              sessions={groupedSessions.completed}
              activeSessionId={resolvedActiveSessionId}
              onOpenSession={handleOpenSession}
            />
          </div>
        ) : (
          <div className="mt-3 rounded-2xl border border-dashed border-[var(--border-default)] bg-white/70 px-3 py-3">
            <p className="text-xs text-[var(--text-secondary)]">
              当前还没有进行中的工作面。先在对话里描述任务，问津会创建并打开对应工作面。
            </p>
          </div>
        )}
      </div>

      {/* Navigation */}
      <div className="border-b border-[var(--border-default)] px-4 py-3">
        <div className="flex gap-2">
          <button
            onClick={goToChat}
            className={cn(
              "flex flex-1 items-center justify-center gap-1.5 rounded-xl border px-3 py-2 text-sm font-medium transition-colors",
              isOnChat
                ? "border-[var(--accent-primary)]/30 bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]"
                : "border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]"
            )}
          >
            <MessageSquare className="h-3.5 w-3.5" />
            对话
          </button>
          <button
            onClick={goToDashboard}
            className={cn(
              "flex flex-1 items-center justify-center gap-1.5 rounded-xl border px-3 py-2 text-sm font-medium transition-colors",
              isOnDashboard
                ? "border-[var(--accent-primary)]/30 bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]"
                : "border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]"
            )}
          >
            <LayoutDashboard className="h-3.5 w-3.5" />
            总览
          </button>
        </div>
      </div>

      <div className="border-b border-[var(--border-default)] px-4 py-3">
        <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
          主线状态
        </p>
        <div className="mt-2.5 flex items-start gap-2.5 rounded-xl bg-white/72 px-3 py-3">
          <Clock3 className="mt-0.5 h-4 w-4 shrink-0 text-[var(--brand-brass)]" />
          <div>
            <p className="text-sm font-medium text-[var(--text-primary)]">
              {primarySession?.title || "等待新的工作"}
            </p>
            <p className="mt-1 text-[11px] leading-5 text-[var(--text-muted)]">
              {primarySession?.description ||
                "当前没有进行中的工作。进入对话后，问津会先确认需求，再安排下一步。"}
            </p>
          </div>
        </div>
      </div>

      <div className="flex-1" />

      {/* Back link */}
      <div className="border-t border-[var(--border-default)] px-4 py-2.5">
        <button
          onClick={() => router.push("/workspaces")}
          className="flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-sm text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-surface)]"
        >
          <ArrowLeft className="h-4 w-4 shrink-0" />
          全部 workspace
        </button>
      </div>
    </aside>
  );
}
