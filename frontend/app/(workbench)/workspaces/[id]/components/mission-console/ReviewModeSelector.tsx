"use client";

import { Bot, CheckSquare, ShieldCheck } from "lucide-react";
import type { MissionReviewMode } from "@/lib/api/mission-types";

export const REVIEW_MODE_LABELS: Record<MissionReviewMode, string> = {
  auto_draft: "草稿自动保存",
  balanced_default: "平衡模式",
  review_all: "每项确认",
};
export const REVIEW_MODE_DESCRIPTIONS: Record<MissionReviewMode, string> = {
  auto_draft: "低风险草稿可自动保存；引用、论断、来源和长期记忆仍需确认。",
  balanced_default: "普通内容按建议处理，影响论文依据与可信度的内容逐项确认。",
  review_all: "所有任务结果都先进入确认区，由你决定是否保存。",
};
export function normalizeReviewMode(value: unknown): MissionReviewMode {
  return value === "review_all" || value === "balanced_default" || value === "auto_draft" ? value : "balanced_default";
}
export function reviewModeLabel(value: unknown): string { return REVIEW_MODE_LABELS[normalizeReviewMode(value)]; }
export function reviewModeDescription(value: unknown): string { return REVIEW_MODE_DESCRIPTIONS[normalizeReviewMode(value)]; }
export function ReviewModeSelector({ value, onChange, disabled = false }: { value: MissionReviewMode; onChange(value: MissionReviewMode): void; disabled?: boolean }) {
  const options = [
    { value: "auto_draft" as const, Icon: Bot },
    { value: "balanced_default" as const, Icon: ShieldCheck },
    { value: "review_all" as const, Icon: CheckSquare },
  ];
  return <div className="grid gap-2" role="radiogroup" aria-label="确认方式">{options.map(({ value: option, Icon }) => <button key={option} type="button" role="radio" aria-checked={value === option} data-testid={`review-mode-${option}`} disabled={disabled} onClick={() => onChange(option)} className={`grid gap-1 rounded-[var(--wjn-radius)] border p-3 text-left disabled:opacity-60 ${value === option ? "border-[var(--wjn-accent-line)] bg-[var(--wjn-accent-soft)]" : "border-[var(--wjn-line)] bg-[var(--wjn-surface)]"}`}><span className="flex items-center gap-2 text-sm font-semibold text-[var(--wjn-text)]"><Icon size={15} />{REVIEW_MODE_LABELS[option]}</span><span className="text-xs leading-5 text-[var(--wjn-text-secondary)]">{REVIEW_MODE_DESCRIPTIONS[option]}</span></button>)}</div>;
}
