"use client";

import { BookOpen } from "lucide-react";
import { BlockActionButtons, readStringValue, type BlockActionType } from "./shared";
import type { ThreadMessageBlock } from "@/lib/api";
import type { BlockActionItem } from "./shared";

export function PrismStatusBlock({
  block,
  onAction,
}: {
  block: ThreadMessageBlock;
  onAction?: (
    action: BlockActionType,
    featureId: string | null,
    routeParams?: Record<string, unknown> | null
  ) => void;
}) {
  const data = block.data ?? {};
  const projectId = readStringValue(data.project_id);
  const projectName = readStringValue(data.project_name);
  const mainFile = readStringValue(data.main_file);
  const pendingFileChanges =
    typeof data.pending_file_changes === "number"
      ? data.pending_file_changes
      : 0;
  const appliedFileChanges =
    typeof data.applied_file_changes === "number"
      ? data.applied_file_changes
      : 0;
  const compileStatus = readStringValue(data.compile_status);
  const prismUrl = readStringValue(data.url);

  const actions: BlockActionItem[] = [];

  if (pendingFileChanges > 0 && projectId) {
    actions.push({
      label: `查看待确认修改 (${pendingFileChanges})`,
      action: "preview_prism_changes",
      routeParams: {
        project_id: projectId,
        url: prismUrl,
      },
    });
  }

  if (projectId) {
    actions.push({
      label: "打开 WenjinPrism",
      action: "open_prism",
      routeParams: {
        project_id: projectId,
        url: prismUrl,
      },
    });
  }

  return (
    <div className="rounded-xl border border-compute-cyan/20 bg-compute-cyan/8 px-3 py-3">
      <div className="flex items-start gap-2">
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-compute-cyan/10 text-compute-cyan">
          <BookOpen className="h-3.5 w-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-[var(--text-primary)]">
            {block.title || "主稿状态"}
          </p>
          {projectName ? (
            <p className="mt-1 text-xs text-[var(--text-secondary)]">
              {projectName}
              {mainFile ? ` · ${mainFile}` : ""}
            </p>
          ) : null}
        </div>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2">
        <div className="rounded-lg bg-white/60 px-2.5 py-2 text-center">
          <p className="text-[11px] text-[var(--text-muted)]">待确认</p>
          <p className="mt-0.5 text-sm font-medium text-compute-gold">
            {pendingFileChanges}
          </p>
        </div>
        <div className="rounded-lg bg-white/60 px-2.5 py-2 text-center">
          <p className="text-[11px] text-[var(--text-muted)]">已写入</p>
          <p className="mt-0.5 text-sm font-medium text-emerald-600">
            {appliedFileChanges}
          </p>
        </div>
        <div className="rounded-lg bg-white/60 px-2.5 py-2 text-center">
          <p className="text-[11px] text-[var(--text-muted)]">编译状态</p>
          <p className="mt-0.5 text-sm font-medium text-[var(--text-primary)]">
            {compileStatus === "blocked_by_review"
              ? "待审核"
              : compileStatus === "compile_failed"
                ? "失败"
                : compileStatus === "ready"
                  ? "就绪"
                  : compileStatus || "—"}
          </p>
        </div>
      </div>

      <BlockActionButtons
        actions={actions}
        onAction={onAction as unknown as Parameters<typeof BlockActionButtons>[0]['onAction']}
      />
    </div>
  );
}
