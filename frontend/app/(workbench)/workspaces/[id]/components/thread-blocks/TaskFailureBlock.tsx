"use client";

import { AlertCircle, ShieldCheck } from "lucide-react";
import {
  BlockActionButtons,
  isBlockActionType,
  readArray,
  readStringValue,
  type BlockActionType,
} from "./shared";
import type { ThreadMessageBlock } from "@/lib/api";
import type { BlockActionItem } from "./shared";

export function TaskFailureBlock({
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
  const failedPhase =
    typeof data.failed_phase === "string" ? data.failed_phase : null;
  const errorSummary =
    typeof data.error_summary === "string"
      ? data.error_summary
      : typeof data.detail === "string"
        ? data.detail
        : null;
  const completed = readArray(data.completed);
  const prismAffected = Boolean(data.prism_affected);
  const recoveryActions = readArray(data.recovery_actions);
  const executionSessionId = readStringValue(
    data.execution_session_id
  );

  const actions: BlockActionItem[] = [];

  recoveryActions.forEach((raw) => {
    const item =
      raw && typeof raw === "object" && !Array.isArray(raw)
        ? (raw as Record<string, unknown>)
        : {};
    const label = readStringValue(item.label);
    const action = readStringValue(item.action);
    if (!label || !action) return;

    if (!isBlockActionType(action)) return;

    actions.push({
      label,
      action,
      featureId,
      routeParams: {
        execution_session_id: executionSessionId,
        recovery_action: action,
      },
    });
  });

  if (actions.length === 0 && featureId) {
    actions.push({
      label: "重试",
      action: "rerun_feature",
      featureId,
      routeParams: {
        execution_session_id: executionSessionId,
      },
    });
    actions.push({
      label: "继续补充",
      action: "continue_thread",
      featureId,
    });
  }

  return (
    <div className="rounded-xl border border-red-500/20 bg-red-500/8 px-3 py-3">
      <div className="flex items-start gap-2">
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-red-500/10 text-red-600">
          <AlertCircle className="h-3.5 w-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-red-700">
            {block.title || "任务失败"}
          </p>
          {failedPhase ? (
            <p className="mt-1 text-xs text-red-600/80">
              失败阶段：{failedPhase}
            </p>
          ) : null}
          {errorSummary ? (
            <p className="mt-1 text-xs leading-5 text-red-600/90">
              {errorSummary}
            </p>
          ) : null}
        </div>
      </div>

      {completed.length > 0 ? (
        <div className="mt-3 rounded-lg bg-white/60 px-2.5 py-2">
          <p className="text-xs font-medium text-[var(--text-primary)]">
            已完成内容
          </p>
          <ul className="mt-1 space-y-1">
            {completed.map((item, i) =>
              typeof item === "string" ? (
                <li
                  key={i}
                  className="text-xs text-[var(--text-secondary)]"
                >
                  - {item}
                </li>
              ) : null
            )}
          </ul>
        </div>
      ) : null}

      <div className="mt-2 flex items-center gap-2">
        {prismAffected ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2 py-0.5 text-[10px] text-red-600">
            <AlertCircle className="h-3 w-3" />
            主稿可能受影响
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-600">
            <ShieldCheck className="h-3 w-3" />
            主稿未受影响
          </span>
        )}
      </div>

      <BlockActionButtons
        actions={actions}
        onAction={onAction as unknown as Parameters<typeof BlockActionButtons>[0]['onAction']}
      />
    </div>
  );
}
