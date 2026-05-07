"use client";

/**
 * TextBlock · Plan 2 T9
 *
 * Renders a paragraph of agent text inside a chat message bubble.
 * Lives in the paper/ink aesthetic of the chat thread (--text-primary
 * on --bg-elevated bubbles supplied by the parent message wrapper).
 */
import type { TextBlock as TextBlockType } from "@/lib/api/blocks";

export function TextBlock({ block }: { block: TextBlockType }) {
  return (
    <div
      className="whitespace-pre-wrap text-[14px] leading-relaxed"
      style={{ color: "var(--text-primary)" }}
    >
      {block.content}
    </div>
  );
}
