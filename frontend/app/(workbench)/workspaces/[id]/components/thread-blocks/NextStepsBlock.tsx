"use client";

import { BlockActionButtons, isBlockActionType, readStringValue } from "./shared";
import type { ThreadMessageBlock } from "@/lib/api";
import type { BlockActionItem, BlockActionType } from "./shared";

export function NextStepsBlock({
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
  const items = Array.isArray(data.items) ? data.items : [];

  const actions: BlockActionItem[] = items
    .map((raw, index) => {
      const item =
        raw && typeof raw === "object" && !Array.isArray(raw)
          ? (raw as Record<string, unknown>)
          : {};
      const label = readStringValue(item.label) || `建议 ${index + 1}`;
      const rawAction = readStringValue(item.action) || "";
      const featureId = readStringValue(item.feature_id);
      const projectId = readStringValue(item.project_id);
      const url = readStringValue(item.url);
      const params =
        item.params && typeof item.params === "object" && !Array.isArray(item.params)
          ? (item.params as Record<string, unknown>)
          : {};
      const routeParams =
        item.route_params && typeof item.route_params === "object" && !Array.isArray(item.route_params)
          ? (item.route_params as Record<string, unknown>)
          : {};
      const disabledReason = readStringValue(item.disabled_reason);

      const action: BlockActionType = isBlockActionType(rawAction)
        ? rawAction
        : "continue_thread";

      return {
        label,
        action,
        featureId,
        routeParams: {
          ...routeParams,
          ...params,
          ...(projectId ? { project_id: projectId } : {}),
          ...(url ? { url } : {}),
        },
        disabled: Boolean(disabledReason),
        title: disabledReason ?? undefined,
      };
    })
    .filter((a) => Boolean(a.label));

  return (
    <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)]/70 px-3 py-3">
      <p className="text-sm font-medium text-[var(--text-primary)]">
        {block.title || "建议下一步"}
      </p>
      <BlockActionButtons
        actions={actions}
        onAction={onAction as unknown as Parameters<typeof BlockActionButtons>[0]['onAction']}
      />
    </div>
  );
}
