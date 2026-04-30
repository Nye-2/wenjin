"use client";

import { Info } from "lucide-react";
import { readArray, readStringValue, readNumberValue } from "./shared";
import type { ThreadMessageBlock } from "@/lib/api";

export function ContextBriefBlock({ block }: { block: ThreadMessageBlock }) {
  const data = block.data ?? {};
  const willUse = readArray(data.will_use);
  const missing = readArray(data.missing);
  const outputDestinations = readArray(data.output_destinations);
  const policy =
    data.policy && typeof data.policy === "object"
      ? (data.policy as Record<string, unknown>)
      : null;

  return (
    <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)]/70 px-3 py-3">
      <div className="flex items-start gap-2">
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-sky-500/10 text-sky-600">
          <Info className="h-3.5 w-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-[var(--text-primary)]">
            {block.title || "本次任务上下文"}
          </p>

          {willUse.length > 0 ? (
            <div className="mt-2">
              <p className="text-xs font-medium text-[var(--text-secondary)]">
                我将使用：
              </p>
              <ul className="mt-1 space-y-1">
                {willUse.map((item, i) => {
                  const label = readStringValue(
                    (item as Record<string, unknown>)?.label
                  );
                  const count = readNumberValue(
                    (item as Record<string, unknown>)?.count
                  );
                  if (!label) return null;
                  return (
                    <li
                      key={i}
                      className="text-xs text-[var(--text-secondary)]"
                    >
                      - {label}
                      {count !== null ? ` ${count}` : ""}
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}

          {missing.length > 0 ? (
            <div className="mt-2">
              <p className="text-xs font-medium text-[var(--text-secondary)]">
                还缺：
              </p>
              <ul className="mt-1 space-y-1">
                {missing.map((item, i) => {
                  const label = readStringValue(
                    (item as Record<string, unknown>)?.label
                  );
                  const required = Boolean(
                    (item as Record<string, unknown>)?.required
                  );
                  if (!label) return null;
                  return (
                    <li
                      key={i}
                      className="text-xs text-[var(--text-secondary)]"
                    >
                      - {label}
                      {required ? "" : "（可选）"}
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}

          {outputDestinations.length > 0 ? (
            <div className="mt-2">
              <p className="text-xs font-medium text-[var(--text-secondary)]">
                输出：
              </p>
              <ul className="mt-1 space-y-1">
                {outputDestinations.map((item, i) => {
                  const label = readStringValue(
                    (item as Record<string, unknown>)?.label
                  );
                  if (!label) return null;
                  return (
                    <li
                      key={i}
                      className="text-xs text-[var(--text-secondary)]"
                    >
                      - {label}
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}

          {policy?.will_not_overwrite_prism ? (
            <p className="mt-2 text-[11px] text-emerald-600">
              不会自动覆盖主稿，写入前会经过确认。
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}


