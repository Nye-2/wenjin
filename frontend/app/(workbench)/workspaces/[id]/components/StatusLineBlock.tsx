"use client";

import type { StatusTone } from "@/lib/api/blocks";

interface StatusLineBlockProps {
  label: string;
  tone?: StatusTone;
  phaseIndex?: number | null;
}

const TONE_STYLES: Record<StatusTone, { accent: string; background: string; icon: string }> = {
  info: {
    accent: "var(--v2-accent-blue-700)",
    background: "var(--v2-accent-blue-100)",
    icon: "→",
  },
  warn: {
    accent: "var(--v2-warning-700, #B45309)",
    background: "var(--v2-warning-100, #FEF3C7)",
    icon: "!",
  },
  error: {
    accent: "var(--v2-error-700, #B91C1C)",
    background: "var(--v2-error-100, #FEE2E2)",
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
        borderRadius: "0 var(--v2-radius-sm) var(--v2-radius-sm) 0",
        margin: "4px 0 4px 4px",
        fontSize: 12,
        color: "var(--v2-text-secondary)",
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
