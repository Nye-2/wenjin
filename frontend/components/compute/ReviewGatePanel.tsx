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
    <section className="compute-card p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ClipboardCheck className="h-4 w-4 text-compute-cyan" />
          <h4 className="text-sm font-semibold text-compute-text-primary">
            审核关卡
          </h4>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium",
            reviewGate?.status === "clear"
              ? "border-compute-green/25 bg-compute-green/10 text-compute-green"
              : reviewGate?.status === "failed"
                ? "border-compute-red/25 bg-compute-red/10 text-compute-red"
                : reviewGate?.required
                  ? "border-compute-gold/25 bg-compute-gold/10 text-compute-gold"
                  : "border-compute-border bg-compute-elevated text-compute-text-secondary"
          )}
        >
          {reviewStatusLabel(reviewGate?.status)}
        </span>
      </div>
      {readString(reviewGate?.advisory_code) ? (
        <p className="mt-2 truncate text-[11px] text-compute-text-muted">
          {readString(reviewGate?.advisory_code)}
        </p>
      ) : null}
      {readString(reviewGate?.policy ?? runtimeProfile?.review_gate) ? (
        <p className="mt-2 truncate text-[11px] text-compute-text-muted">
          策略: {readString(reviewGate?.policy ?? runtimeProfile?.review_gate)}
        </p>
      ) : null}
      <div className="mt-3 space-y-2">
        {reviewItems.length > 0 ? (
          reviewItems.map((item) => (
            <div
              key={item.id}
              className="rounded-xl border border-compute-border bg-compute-surface px-3 py-2"
            >
              <div className="flex items-center justify-between gap-3">
                <p className="truncate text-sm font-medium text-compute-text-primary">
                  {item.label}
                </p>
                <span className="shrink-0 text-[11px] text-compute-text-muted">
                  {item.required ? "必需" : item.kind}
                </span>
              </div>
              {readString(item.kind) && item.required ? (
                <p className="mt-1 text-[11px] text-compute-text-muted">
                  {item.kind}
                </p>
              ) : null}
            </div>
          ))
        ) : (
          <p className="rounded-xl border border-dashed border-compute-border px-3 py-4 text-center text-xs text-compute-text-muted">
            当前没有等待处理的审核动作。
          </p>
        )}
      </div>
    </section>
  );
}
