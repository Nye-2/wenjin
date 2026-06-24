"use client";

import type { ExecutionNodeState } from "@/lib/api/types";
import {
  recoverableOutputRefCount,
  readRuntimeObject,
  runtimeStatusLabel,
  safeRuntimeText,
  safeStructuredFallback,
} from "@/lib/runtime-payload-safety";

export interface NodeInlineDetailProps {
  state: ExecutionNodeState;
}

export function NodeInlineDetail({ state }: NodeInlineDetailProps) {
  const lines = buildSafeNodeDetailLines(state);

  return (
    <div
      style={{
        marginTop: 6,
        borderRadius: "var(--wjn-radius-md)",
        background: "var(--wjn-bg-base)",
        border: "1px solid var(--wjn-line)",
        overflow: "hidden",
        fontFamily: "var(--wjn-font-sans)",
        fontSize: 12,
        color: "var(--wjn-text)",
      }}
    >
      <div
        style={{
          padding: "8px 12px",
          display: "grid",
          gap: 4,
          background: "rgba(255, 255, 255, 0.3)",
        }}
      >
        {lines.length > 0 ? (
          lines.map((line) => (
            <div
              key={line}
              style={{
                fontSize: 11.5,
                lineHeight: 1.5,
                color: "var(--wjn-text-secondary)",
              }}
            >
              {line}
            </div>
          ))
        ) : (
          <span
            style={{
              fontFamily: "var(--wjn-font-sans)",
              fontSize: 11,
              color: "var(--wjn-text-muted)",
            }}
          >
            No data available
          </span>
        )}
      </div>

    </div>
  );
}

function buildSafeNodeDetailLines(state: ExecutionNodeState): string[] {
  const input = readRuntimeObject(state.input);
  const output = readRuntimeObject(state.output);
  const outputRefCount = recoverableOutputRefCount(
    output?.output_refs,
    output?.output_ref,
    ...(state.tool_calls ?? []).flatMap((call) => [call.output_refs, call.output_ref]),
  );
  const outputSummary = [
    safeRuntimeText(output?.summary) ??
      safeRuntimeText(output?.result_summary) ??
      safeRuntimeText(output?.narrative) ??
      safeRuntimeText(output?.message),
    safeRuntimeText(output?.operation) ? `操作：${safeRuntimeText(output?.operation)}` : null,
    outputRefCount > 0
      ? `输出：${outputRefCount} 个可恢复引用`
      : output
        ? "输出：已生成运行结果"
        : null,
  ].filter((line): line is string => Boolean(line)).join(" · ");

  return [
    `状态：${runtimeStatusLabel(state.status)}`,
    input ? `输入：${safeStructuredFallback(input, "已接收运行输入")}` : null,
    outputSummary || null,
    safeRuntimeText(state.thinking, 260)
      ? `进展：${safeRuntimeText(state.thinking, 260)}`
      : null,
  ].filter((line): line is string => Boolean(line));
}
