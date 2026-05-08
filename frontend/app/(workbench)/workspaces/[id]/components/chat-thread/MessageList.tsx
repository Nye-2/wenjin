"use client";

/**
 * MessageList — flat message flow (no run grouping).
 *
 * User messages render as right-aligned bubbles.
 * Agent messages render as left-aligned containers with block-level
 * children: text (simple bubble), status_line (inline), question_card
 * (card), result_card (card).
 */
import {
  isQuestionCard,
  isResultCard,
  isStatusLine,
  isText,
  type AgentBlock,
} from "@/lib/api/blocks";

import { QuestionCardBlock } from "./blocks/QuestionCardBlock";
import { ResultCardBlock } from "./blocks/ResultCardBlock";
import { StatusLineBlock } from "./blocks/StatusLineBlock";
import { TextBlock } from "./blocks/TextBlock";

export interface ChatMessage {
  id: string;
  role: "user" | "agent";
  run_id: string;
  text?: string;
  blocks?: AgentBlock[];
}

function renderBlock(
  b: AgentBlock,
  key: number,
  handlers: {
    onPillClick?: (intent: string, label: string) => void;
    onFeedback?: (intent: string, label: string) => void;
    onJumpToPhase?: (runId: string, phaseIndex: number) => void;
  },
): React.ReactNode {
  if (isText(b)) return <TextBlock key={key} block={b} />;
  if (isStatusLine(b)) {
    return (
      <StatusLineBlock
        key={key}
        block={b}
        onJumpToPhase={handlers.onJumpToPhase}
      />
    );
  }
  if (isQuestionCard(b)) {
    return (
      <QuestionCardBlock
        key={key}
        block={b}
        onPillClick={handlers.onPillClick}
      />
    );
  }
  if (isResultCard(b)) {
    return (
      <ResultCardBlock key={key} block={b} onFeedback={handlers.onFeedback} />
    );
  }
  return null;
}

interface MessageListProps {
  messages: ChatMessage[];
  onSubmit?: (text: string) => void;
  onJumpToPhase?: (runId: string, phaseIndex: number) => void;
}

export function MessageList({
  messages,
  onSubmit,
  onJumpToPhase,
}: MessageListProps) {
  const handlers = {
    onPillClick: onSubmit
      ? (intent: string) => {
          onSubmit(intent);
        }
      : undefined,
    onFeedback: onSubmit
      ? (intent: string) => {
          onSubmit(intent);
        }
      : undefined,
    onJumpToPhase,
  };

  return (
    <div className="flex flex-col gap-3">
      {messages.map((m) => (
        <div
          key={m.id}
          className={m.role === "user" ? "flex justify-end" : ""}
        >
          {m.role === "user" ? (
            <div
              className="rounded-2xl rounded-br-sm px-3.5 py-2 text-[14px] leading-relaxed"
              style={{
                background: "rgba(31, 66, 99, 0.10)",
                color: "var(--text-primary)",
                maxWidth: "78%",
              }}
            >
              {m.text}
            </div>
          ) : (
            <div className="flex max-w-[95%] flex-col gap-2.5">
              {(m.blocks ?? []).map((b, j) => renderBlock(b, j, handlers))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
