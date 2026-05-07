"use client";

/**
 * QuestionCardBlock · Plan 2 T10
 *
 * The agent's brainstorming-style question card. Distinct from regular
 * chat text bubbles: an inset card with a "需要你拍一下" header label,
 * the focused question, and 0-3 pill suggestions. Brand-brass accent
 * signals "agent needs your input" — same gold tone as the right
 * panel's "waiting" subagent state.
 */
import type { QuestionCardBlock as QuestionCardBlockType } from "@/lib/api/blocks";

interface QuestionCardBlockProps {
  block: QuestionCardBlockType;
  onPillClick?: (intent: string, label: string) => void;
}

export function QuestionCardBlock({
  block,
  onPillClick,
}: QuestionCardBlockProps) {
  return (
    <div
      className="rounded-xl px-4 py-3"
      style={{
        background: "rgba(166, 124, 57, 0.06)", // brass-tinted paper
        border: "1px solid rgba(166, 124, 57, 0.25)",
      }}
    >
      <div
        className="text-[10.5px] uppercase tracking-wider"
        style={{ color: "var(--brand-brass)" }}
      >
        {block.label}
      </div>
      <div
        className="mt-1.5 text-[14px] leading-relaxed"
        style={{ color: "var(--text-primary)" }}
      >
        {block.question}
      </div>

      {block.pills.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {block.pills.map((p) => (
            <button
              key={p.intent}
              type="button"
              onClick={() => onPillClick?.(p.intent, p.label)}
              className="rounded px-2.5 py-1 text-[12.5px] transition-colors"
              style={{
                background: "var(--bg-elevated)",
                border: "1px solid var(--border-default)",
                color: "var(--text-primary)",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "var(--input-bg-hover)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "var(--bg-elevated)";
              }}
            >
              {p.label}
            </button>
          ))}
        </div>
      )}

      <div
        className="mt-2.5 text-[11px]"
        style={{ color: "var(--text-muted)" }}
      >
        或者直接打字告诉我你的想法。
      </div>
    </div>
  );
}
