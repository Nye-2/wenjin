"use client";

import { Sparkles } from "lucide-react";
import { BlockActionButtons, type BlockActionType } from "./shared";
import type { ThreadMessageBlock } from "@/lib/api";
import type { BlockActionItem } from "./shared";

export function TaskProposalBlock({
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
  const featureId =
    typeof data.feature_id === "string" ? data.feature_id : null;
  const featureName =
    typeof data.feature_name === "string"
      ? data.feature_name
      : typeof data.feature_id === "string"
        ? data.feature_id
        : null;
  const reason =
    typeof data.reason === "string" ? data.reason : null;
  const confidence =
    typeof data.confidence === "number" && Number.isFinite(data.confidence)
      ? Math.round(data.confidence * 100)
      : null;
  const params =
    data.params && typeof data.params === "object"
      ? (data.params as Record<string, unknown>)
      : {};
  const skillId =
    typeof data.skill_id === "string" ? data.skill_id : null;

  const routeParams: Record<string, unknown> = {
    ...params,
    ...(skillId ? { skill: skillId } : {}),
  };

  const actions: BlockActionItem[] = [];
  if (featureId) {
    actions.push({
      label: featureName ? `启动${featureName}` : "启动任务",
      action: "trigger_feature",
      featureId,
      routeParams,
    });
    actions.push({
      label: "继续补充要求",
      action: "continue_thread",
      featureId,
    });
  }

  return (
    <div className="rounded-xl border border-[rgba(46,111,109,0.22)] bg-[linear-gradient(135deg,rgba(46,111,109,0.10),rgba(244,216,170,0.12))] px-3 py-3">
      <div className="flex items-start gap-2">
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white/70 text-[var(--brand-teal)]">
          <Sparkles className="h-3.5 w-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-[var(--text-primary)]">
            {block.title || "建议启动任务"}
          </p>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            {featureName ? `将进入「${featureName}」执行链路。` : ""}
            {reason ? ` 识别依据：${reason}。` : null}
          </p>
          {confidence !== null ? (
            <span className="mt-2 inline-flex rounded-full bg-white/70 px-2 py-0.5 text-[11px] font-medium text-[var(--brand-teal)]">
              意图置信度 {confidence}%
            </span>
          ) : null}
        </div>
      </div>
      <BlockActionButtons actions={actions} onAction={onAction} />
    </div>
  );
}
