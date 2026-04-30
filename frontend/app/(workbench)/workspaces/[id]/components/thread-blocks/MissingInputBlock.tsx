"use client";

import { AlertCircle } from "lucide-react";
import { BlockActionButtons, readArray, readStringValue, type BlockActionType } from "./shared";
import type { ThreadMessageBlock } from "@/lib/api";
import type { BlockActionItem } from "./shared";

export function MissingInputBlock({
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
  const message =
    typeof data.message === "string"
      ? data.message
      : typeof data.detail === "string"
        ? data.detail
        : null;
  const missingFields = readArray(data.missing_fields);

  const actions: BlockActionItem[] = [];
  if (featureId) {
    actions.push({
      label: "直接回复补充信息",
      action: "continue_thread",
      featureId,
    });
  }

  return (
    <div className="rounded-xl border border-sky-500/20 bg-sky-500/8 px-3 py-3">
      <div className="flex items-start gap-2">
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-sky-500/10 text-sky-600">
          <AlertCircle className="h-3.5 w-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-sky-700">
            {block.title || "还缺少必要信息"}
          </p>
          {message ? (
            <p className="mt-1 text-xs leading-5 text-sky-600/90">
              {message}
            </p>
          ) : null}
          {missingFields.length > 0 ? (
            <div className="mt-2 space-y-1">
              {missingFields.map((field, i) => {
                const label = readStringValue(
                  (field as Record<string, unknown>)?.label
                );
                const fieldName = readStringValue(
                  (field as Record<string, unknown>)?.field
                );
                const examples = readArray(
                  (field as Record<string, unknown>)?.examples
                );
                return (
                  <div key={i} className="text-xs text-sky-700">
                    <span className="font-medium">
                      {label || fieldName || `字段 ${i + 1}`}
                    </span>
                    {examples.length > 0 ? (
                      <span className="text-sky-600/80">
                        {" "}
                        （例如：
                        {examples
                          .filter((e): e is string => typeof e === "string")
                          .join("、")}
                        ）
                      </span>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ) : null}
          <p className="mt-2 text-[11px] text-sky-600/80">
            直接回复补充信息即可继续，不需要进入工作现场。
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
