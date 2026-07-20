"use client";

import { AlertTriangle, Sparkles, XCircle } from "lucide-react";

import type { StatusTone } from "@/lib/api/blocks";

interface StatusLineBlockProps {
  label: string;
  tone?: StatusTone;
  phaseIndex?: number | null;
}

const TONE_STYLES: Record<
  StatusTone,
  { accent: string; background: string; Icon: typeof Sparkles }
> = {
  info: {
    accent: "var(--wjn-blue)",
    background: "var(--wjn-accent-soft)",
    Icon: Sparkles,
  },
  warn: {
    accent: "var(--wjn-review)",
    background: "var(--wjn-review-soft)",
    Icon: AlertTriangle,
  },
  error: {
    accent: "var(--wjn-error)",
    background: "var(--wjn-error-soft)",
    Icon: XCircle,
  },
};

export function StatusLineBlock({
  label,
  tone = "info",
  phaseIndex,
}: StatusLineBlockProps) {
  const toneStyle = TONE_STYLES[tone];
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 8px",
        borderLeft: `2px solid ${toneStyle.accent}`,
        background: toneStyle.background,
        borderRadius: "0 var(--wjn-radius) var(--wjn-radius) 0",
        margin: "4px 0 4px 4px",
        fontSize: 12,
        color: "var(--wjn-text-secondary)",
      }}
    >
      <toneStyle.Icon size={13} strokeWidth={2} style={{ color: toneStyle.accent, flexShrink: 0 }} aria-hidden="true" />
      <span>
        {phaseIndex != null ? `阶段 ${phaseIndex} · ` : ""}
        {label}
      </span>
    </div>
  );
}
