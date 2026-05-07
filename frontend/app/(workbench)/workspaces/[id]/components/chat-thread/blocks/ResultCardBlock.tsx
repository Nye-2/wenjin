"use client";

/**
 * ResultCardBlock · Plan 2 T11
 *
 * The closing card of every run: TL;DR → findings → recommend → links → feedback.
 * Uses the brand-teal accent (paper/ink ✓ semantic) to signal completion,
 * distinct from question_card's brand-brass "needs your input".
 *
 * Findings are numbered with circled numerals (①②③) so users can refer
 * to them in chat ("深入第 ① 点").
 */
import type {
  FeedbackPill,
  ResultCardBlock as ResultCardBlockType,
} from "@/lib/api/blocks";

const NUM_BADGE = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨"] as const;

interface PillStyle {
  background: string;
  border: string;
  color: string;
}

const PILL: Record<FeedbackPill["kind"], PillStyle> = {
  primary: {
    background: "var(--brand-teal)",
    border: "var(--brand-teal)",
    color: "#FFFFFF",
  },
  normal: {
    background: "var(--bg-elevated)",
    border: "var(--border-default)",
    color: "var(--text-primary)",
  },
  warn: {
    background: "rgba(198, 138, 26, 0.08)",
    border: "rgba(198, 138, 26, 0.4)",
    color: "var(--semantic-warning)",
  },
};

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k tokens`;
  return `${n} tokens`;
}

function formatDuration(ms: number): string {
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return rem ? `${m}m ${rem}s` : `${m}m`;
}

interface ResultCardBlockProps {
  block: ResultCardBlockType;
  onFeedback?: (intent: string, label: string) => void;
}

export function ResultCardBlock({ block, onFeedback }: ResultCardBlockProps) {
  return (
    <div
      className="rounded-xl px-4 py-4"
      style={{
        background:
          "linear-gradient(180deg, rgba(46, 111, 109, 0.05), rgba(46, 111, 109, 0.02))",
        border: "1px solid rgba(46, 111, 109, 0.25)",
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between pb-2.5"
        style={{ borderBottom: "1px dashed rgba(46, 111, 109, 0.2)" }}
      >
        <div>
          <div
            className="text-[14.5px] font-semibold"
            style={{ color: "var(--text-primary)" }}
          >
            {block.title}
          </div>
          <div
            className="mt-0.5 text-[11px]"
            style={{ color: "var(--text-muted)" }}
          >
            {block.stats.subagents} subagents · {formatDuration(block.stats.duration_ms)} ·{" "}
            {formatTokens(block.stats.tokens)}
          </div>
        </div>
        <span
          className="rounded px-2 py-0.5 text-[11px] font-medium"
          style={{
            background: "rgba(13, 146, 101, 0.12)",
            color: "var(--semantic-success)",
          }}
        >
          已完成
        </span>
      </div>

      {/* TL;DR */}
      <div
        className="mt-3 rounded-md px-3 py-2.5 text-[13px] leading-relaxed"
        style={{
          background: "rgba(255, 255, 255, 0.55)",
          color: "var(--text-primary)",
        }}
      >
        <span className="font-semibold" style={{ color: "var(--brand-teal)" }}>
          TL;DR：
        </span>
        {block.tldr}
      </div>

      {/* Findings */}
      {block.findings.length > 0 && (
        <div className="mt-4">
          <div
            className="mb-1.5 text-[10.5px] uppercase tracking-wider"
            style={{ color: "var(--text-muted)" }}
          >
            关键发现
          </div>
          <div className="flex flex-col gap-1">
            {block.findings.map((f, i) => (
              <div
                key={f.id}
                className="flex gap-2 text-[13px] leading-relaxed"
                style={{ color: "var(--text-primary)" }}
              >
                <span
                  className="font-semibold"
                  style={{ color: "var(--brand-teal)" }}
                >
                  {NUM_BADGE[i] ?? `(${i + 1})`}
                </span>
                <span>{f.text}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recommend */}
      {block.recommend && (
        <div
          className="mt-4 rounded-r-md py-2 pl-3 pr-2.5"
          style={{
            borderLeft: "2px solid var(--brand-navy)",
            background: "rgba(31, 66, 99, 0.05)",
          }}
        >
          <div
            className="text-[10.5px] uppercase tracking-wider"
            style={{ color: "var(--brand-navy)" }}
          >
            {block.recommend.label}
          </div>
          <div
            className="mt-0.5 text-[13px] leading-relaxed"
            style={{ color: "var(--text-primary)" }}
          >
            {block.recommend.body}
          </div>
        </div>
      )}

      {/* Links */}
      {block.links.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {block.links.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-[12px] transition-colors hover:opacity-80"
              style={{
                background: "var(--bg-elevated)",
                border: "1px solid var(--border-default)",
                color: "var(--text-primary)",
              }}
            >
              <span style={{ color: "var(--text-muted)" }}>{l.icon}</span>
              {l.label}
            </a>
          ))}
        </div>
      )}

      {/* Feedback */}
      <div
        className="mt-4 pt-3"
        style={{ borderTop: "1px dashed rgba(46, 111, 109, 0.2)" }}
      >
        <div
          className="text-[13px]"
          style={{ color: "var(--text-secondary)" }}
        >
          {block.feedback.question}
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {block.feedback.pills.map((p) => {
            const style = PILL[p.kind];
            return (
              <button
                key={p.intent}
                type="button"
                data-pill-kind={p.kind}
                onClick={() => onFeedback?.(p.intent, p.label)}
                className="rounded px-3 py-1 text-[12.5px] font-medium transition-opacity hover:opacity-80"
                style={style}
              >
                {p.label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
