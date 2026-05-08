"use client";

/**
 * MessageList — flat message flow (no run grouping).
 *
 * User messages render as right-aligned bubbles.
 * Agent messages render as left-aligned: text blocks get a subtle
 * bubble wrapper, card blocks (result_card, question_card) render
 * with their own card style, status_line is inline.
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

/**
 * Group consecutive text blocks into a single bubble, while card blocks
 * and status_line blocks render standalone.
 */
function renderAgentBlocks(
  blocks: AgentBlock[],
  handlers: {
    onPillClick?: (intent: string, label: string) => void;
    onFeedback?: (intent: string, label: string) => void;
    onJumpToPhase?: (runId: string, phaseIndex: number) => void;
  },
): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  let textBuf: React.ReactNode[] = [];
  let keyIdx = 0;

  const flushText = () => {
    if (textBuf.length === 0) return;
    out.push(
      <div
        key={`bubble-${keyIdx}`}
        className="rounded-2xl rounded-bl-sm px-3.5 py-2.5"
        style={{
          background: "var(--bg-elevated)",
          border: "1px solid var(--border-subtle)",
        }}
      >
        {textBuf}
      </div>,
    );
    textBuf = [];
  };

  for (const b of blocks) {
    if (isText(b)) {
      textBuf.push(renderBlock(b, keyIdx++, handlers));
    } else {
      flushText();
      out.push(renderBlock(b, keyIdx++, handlers));
    }
  }
  flushText();
  return out;
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
              {renderAgentBlocks(m.blocks ?? [], handlers)}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
