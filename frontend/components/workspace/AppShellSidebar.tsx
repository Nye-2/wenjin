"use client";

import { usePathname, useRouter } from "next/navigation";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  LayoutDashboard,
  MessageSquare,
} from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useI18n } from "@/components/i18n-provider";
import { cn } from "@/lib/utils";
import { workspaceStages } from "@/lib/workspace-feature-stages";

interface AppShellSidebarProps {
  workspaceId: string;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

function inferSuggestedStageIndex({
  pathname,
  artifactsCount,
}: {
  pathname: string;
  artifactsCount: number;
}) {
  if (pathname.includes("/chat")) return 3;
  if (artifactsCount > 0) return 2;
  return 0;
}

export function AppShellSidebar({
  workspaceId,
  collapsed = false,
  onToggleCollapse,
}: AppShellSidebarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { t } = useI18n();

  const workspace = useWorkspaceStore((state) => state.workspace);
  const artifacts = useWorkspaceStore((state) => state.artifacts);
  const workspaces = useWorkspaceStore((state) => state.workspaces);

  const isOnChat = pathname.includes("/chat/");
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

  const suggestedStageIndex = inferSuggestedStageIndex({
    pathname,
    artifactsCount: artifacts.length,
  });

  const goToDashboard = () => router.push(`/workspaces/${workspaceId}`);
  const goToChat = () => router.push(`/workspaces/${workspaceId}/chat`);
  const handleStageClick = (stageIndex: number) => {
    if (isOnDashboard) {
      const el = document.getElementById(`stage-${workspaceStages[stageIndex].id}`);
      el?.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      router.push(`/workspaces/${workspaceId}#stage-${workspaceStages[stageIndex].id}`);
    }
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

      {/* Stage stepper — compact, clickable */}
      <div className="border-b border-[var(--border-default)] px-4 py-3">
        <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
          工作阶段
        </p>
        <div className="mt-2.5 space-y-1">
          {workspaceStages.map((stage, index) => {
            const isCurrent = index === suggestedStageIndex;
            const isPast = index < suggestedStageIndex;
            return (
              <button
                key={stage.id}
                type="button"
                onClick={() => handleStageClick(index)}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-xl px-2.5 py-1.5 text-left transition-colors hover:bg-[var(--bg-surface)]",
                  isCurrent && "bg-[rgba(166,124,57,0.06)]"
                )}
              >
                <div
                  className={cn(
                    "h-2.5 w-2.5 shrink-0 rounded-full border",
                    isCurrent
                      ? "border-[var(--brand-brass)] bg-[var(--brand-brass)]"
                      : isPast
                        ? "border-[var(--brand-teal)] bg-[var(--brand-teal)]"
                        : "border-[var(--border-default)] bg-white"
                  )}
                />
                <span
                  className={cn(
                    "text-sm",
                    isCurrent
                      ? "font-medium text-[var(--text-primary)]"
                      : isPast
                        ? "text-[var(--text-secondary)]"
                        : "text-[var(--text-muted)]"
                  )}
                >
                  {stage.title}
                </span>
                {isCurrent && (
                  <span className="ml-auto rounded-full bg-[rgba(166,124,57,0.1)] px-1.5 py-0.5 text-[9px] font-medium text-[var(--brand-brass)]">
                    当前
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Work entries — compact */}
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
