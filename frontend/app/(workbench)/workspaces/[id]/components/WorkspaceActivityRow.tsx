"use client";

import { motion } from "framer-motion";
import type { Artifact, WorkspaceActivityItem } from "@/stores/workspace";
import { cn } from "@/lib/utils";
import {
  getActivityMeta,
  getStatusMeta,
  resolveMetadataLine,
  resolveSummary,
} from "./WorkspaceActivityPresenters";

function formatTime(dateString: string) {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "刚刚";
  if (diffMins < 60) return `${diffMins} 分钟前`;
  if (diffHours < 24) return `${diffHours} 小时前`;
  if (diffDays < 7) return `${diffDays} 天前`;
  return date.toLocaleDateString();
}

interface ActivityItemRowProps {
  item: WorkspaceActivityItem;
  artifact: Artifact | null;
  title: string;
  resolveSkillLabel: (skillId: string | null | undefined) => string | null;
  onSelectArtifact: (artifact: Artifact) => void;
  onOpenDetails: (item: WorkspaceActivityItem) => void;
  actions?: Array<{
    key: string;
    label: string;
    icon: React.ElementType;
    onClick: () => void;
    tone?: "default" | "primary" | "danger";
  }>;
}

export function ActivityItemRow({
  item,
  artifact,
  title,
  resolveSkillLabel,
  onSelectArtifact,
  onOpenDetails,
  actions = [],
}: ActivityItemRowProps) {
  const meta = getActivityMeta(item, artifact);
  const statusMeta = getStatusMeta(item.status);
  const Icon = meta.icon;
  const clickableArtifact = item.kind === "artifact" && artifact !== null;
  const metadataLine = resolveMetadataLine(item, title, resolveSkillLabel);

  const content = (
    <>
      <div className="relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)]">
        <div className={cn("rounded-lg p-2", meta.className)}>
          <Icon className="h-4 w-4" />
        </div>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-muted)]">
                {meta.label}
              </span>
              {statusMeta && (
                <span
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium",
                    statusMeta.className
                  )}
                >
                  <statusMeta.icon
                    className={cn(
                      "h-3 w-3",
                      (item.status === "running" || item.status === "pending") &&
                        "animate-spin"
                    )}
                  />
                  {statusMeta.label}
                </span>
              )}
            </div>
            <p className="mt-2 truncate text-sm font-medium text-[var(--text-primary)]">
              {title}
            </p>
            <p className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--text-secondary)]">
              {resolveSummary(item)}
            </p>
            <p className="mt-1 text-[11px] text-[var(--text-muted)]">
              {metadataLine}
            </p>
            {actions.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {actions.map((action) => {
                  const ActionIcon = action.icon;
                  return (
                    <button
                      key={action.key}
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        action.onClick();
                      }}
                      className={cn(
                        "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors",
                        action.tone === "primary"
                          ? "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] hover:bg-[var(--accent-primary)]/15"
                          : action.tone === "danger"
                            ? "bg-red-500/10 text-red-600 hover:bg-red-500/15"
                            : "bg-[var(--bg-elevated)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                      )}
                    >
                      <ActionIcon className="h-3 w-3" />
                      {action.label}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
          <span className="shrink-0 text-[11px] text-[var(--text-muted)]">
            {formatTime(item.occurred_at)}
          </span>
        </div>
      </div>
    </>
  );

  if (clickableArtifact && artifact) {
    return (
      <motion.button
        type="button"
        initial={{ opacity: 0, x: -12 }}
        animate={{ opacity: 1, x: 0 }}
        onClick={() => onSelectArtifact(artifact)}
        className="group relative flex w-full items-start gap-3 rounded-2xl border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-3 text-left transition-all hover:border-[var(--accent-primary)]/30 hover:bg-[var(--bg-surface)]/80"
      >
        {content}
      </motion.button>
    );
  }

  return (
    <motion.button
      type="button"
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      onClick={() => onOpenDetails(item)}
      className="relative flex w-full items-start gap-3 rounded-2xl border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-3 text-left transition-all hover:border-[var(--accent-primary)]/20"
    >
      {content}
    </motion.button>
  );
}
