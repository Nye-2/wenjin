"use client";

import { ClipboardCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { readString, reviewStatusLabel } from "./utils";
import type { ComputeReviewGateProjection } from "@/lib/api";

interface ReviewGatePanelProps {
  reviewGate: ComputeReviewGateProjection | null;
  runtimeProfile: {
    review_gate?: string | null;
  } | null;
}

export function ReviewGatePanel({ reviewGate, runtimeProfile }: ReviewGatePanelProps) {
  const reviewItems = reviewGate?.items ?? [];

  return (
    <section className="rounded-2xl border border-[var(--border-default)] bg-white/78 p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ClipboardCheck className="h-4 w-4 text-[var(--accent-primary)]" />
          <h4 className="text-sm font-semibold text-[var(--text-primary)]">
            Review Gate
          </h4>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium",
            reviewGate?.status === "clear"
              ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-700"
              : reviewGate?.status === "failed"
                ? "border-red-500/25 bg-red-500/10 text-red-700"
                : reviewGate?.required
                  ? "border-amber-500/25 bg-amber-500/10 text-amber-700"
                  : "border-[var(--border-default)] bg-[var(--bg-elevated)] text-[var(--text-secondary)]"
          )}
        >
          {reviewStatusLabel(reviewGate?.status)}
        </span>
      </div>
      {readString(reviewGate?.advisory_code) ? (
        <p className="mt-2 truncate text-[11px] text-[var(--text-muted)]">
          {readString(reviewGate?.advisory_code)}
        </p>
      ) : null}
      {readString(reviewGate?.policy ?? runtimeProfile?.review_gate) ? (
        <p className="mt-2 truncate text-[11px] text-[var(--text-muted)]">
          Policy: {readString(reviewGate?.policy ?? runtimeProfile?.review_gate)}
        </p>
      ) : null}
      <div className="mt-3 space-y-2">
        {reviewItems.length > 0 ? (
          reviewItems.map((item) => (
            <div
              key={item.id}
              className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2"
            >
              <div className="flex items-center justify-between gap-3">
                <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                  {item.label}
                </p>
                <span className="shrink-0 text-[11px] text-[var(--text-muted)]">
                  {item.required ? "required" : item.kind}
                </span>
              </div>
              {readString(item.kind) && item.required ? (
                <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                  {item.kind}
                </p>
              ) : null}
            </div>
          ))
        ) : (
          <p className="rounded-xl border border-dashed border-[var(--border-default)] px-3 py-4 text-center text-xs text-[var(--text-muted)]">
            当前没有等待处理的 review action。
          </p>
        )}
      </div>
    </section>
  );
}
