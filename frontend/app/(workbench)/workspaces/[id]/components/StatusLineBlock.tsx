"use client";

import type { StatusTone } from "@/lib/api/blocks";

interface StatusLineBlockProps {
  label: string;
  tone?: StatusTone;
  phaseIndex?: number | null;
}

const TONE_STYLES: Record<StatusTone, { accent: string; background: string; icon: string }> = {
  info: {
    accent: "var(--wjn-blue)",
    background: "var(--wjn-accent-soft)",
    icon: "→",
  },
  warn: {
    accent: "var(--wjn-review)",
    background: "var(--wjn-review-soft)",
    icon: "!",
  },
  error: {
    accent: "var(--wjn-error)",
    background: "var(--wjn-error-soft)",
    icon: "×",
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
      <span style={{ color: toneStyle.accent }}>{toneStyle.icon}</span>
      <span>
        {phaseIndex != null ? `Phase ${phaseIndex} · ` : ""}
        {label}
      </span>
    </div>
  );
}
