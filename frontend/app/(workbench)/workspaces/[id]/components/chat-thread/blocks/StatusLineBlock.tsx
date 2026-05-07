"use client";

/**
 * StatusLineBlock · Plan 2 T9
 *
 * A lightweight phase-transition row in the chat thread. Distinct from
 * regular agent messages — appears as an inset, indented line with an
 * arrow indicator. Click jumps the right panel to the corresponding
 * phase (when phase_index is set).
 */
import type {
  StatusLineBlock as StatusLineBlockType,
  StatusTone,
} from "@/lib/api/blocks";

interface ToneStyle {
  borderColor: string;
  textColor: string;
  arrowColor: string;
}

const TONE: Record<StatusTone, ToneStyle> = {
  info: {
    borderColor: "var(--brand-teal)",
    textColor: "var(--text-secondary)",
    arrowColor: "var(--brand-teal)",
  },
  warn: {
    borderColor: "var(--semantic-warning)",
    textColor: "var(--semantic-warning)",
    arrowColor: "var(--semantic-warning)",
  },
  error: {
    borderColor: "var(--semantic-error)",
    textColor: "var(--semantic-error)",
    arrowColor: "var(--semantic-error)",
  },
};

interface StatusLineBlockProps {
  block: StatusLineBlockType;
  onJumpToPhase?: (runId: string, phaseIndex: number) => void;
}

export function StatusLineBlock({
  block,
  onJumpToPhase,
}: StatusLineBlockProps) {
  const tone = TONE[block.tone] ?? TONE.info;
  const clickable = block.phase_index != null && onJumpToPhase != null;

  return (
    <button
      type="button"
      data-tone={block.tone}
      onClick={() => {
        if (clickable && block.phase_index != null) {
          onJumpToPhase(block.run_id, block.phase_index);
        }
      }}
      disabled={!clickable}
      className={`my-1.5 ml-2 flex items-center gap-2 border-l-2 py-0.5 pl-2.5 pr-2 text-[12px] leading-snug ${
        clickable ? "cursor-pointer hover:opacity-80" : "cursor-default"
      }`}
      style={{
        borderLeftColor: tone.borderColor,
        color: tone.textColor,
      }}
    >
      <span style={{ color: tone.arrowColor }}>→</span>
      <span>{block.label}</span>
    </button>
  );
}
