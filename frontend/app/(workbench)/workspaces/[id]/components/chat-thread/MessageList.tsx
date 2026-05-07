"use client";

/**
 * MessageList · Plan 2 T12
 *
 * Groups thread messages by run_id and renders each run inside a
 * RunContainer. User messages get a bubble on the right (brand-navy
 * tinted); agent messages get a multi-block container on the left.
 *
 * Each run's title is derived in this order:
 *   1. The run's result_card title (if the run completed)
 *   2. The first user message text (truncated)
 *   3. Fallback string "运行"
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
import { RunContainer } from "./RunContainer";

export interface ChatMessage {
  id: string;
  role: "user" | "agent";
  run_id: string;
  text?: string;
  blocks?: AgentBlock[];
}

function groupByRun(
  messages: ChatMessage[],
): { run_id: string; messages: ChatMessage[] }[] {
  const out: { run_id: string; messages: ChatMessage[] }[] = [];
  for (const m of messages) {
    const last = out[out.length - 1];
    if (last && last.run_id === m.run_id) {
      last.messages.push(m);
    } else {
      out.push({ run_id: m.run_id, messages: [m] });
    }
  }
  return out;
}

function deriveRunTitle(messages: ChatMessage[]): string {
  for (const m of messages) {
    for (const b of m.blocks ?? []) {
      if (isResultCard(b)) {
        return b.title.replace(/^📑\s*/, "");
      }
    }
  }
  const firstUser = messages.find((m) => m.role === "user");
  if (firstUser?.text) {
    return firstUser.text.length > 24
      ? `${firstUser.text.slice(0, 24)}…`
      : firstUser.text;
  }
  return "运行";
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
  currentRunId: string | null;
  onSubmit?: (text: string) => void;
  onJumpToPhase?: (runId: string, phaseIndex: number) => void;
}

export function MessageList({
  messages,
  currentRunId,
  onSubmit,
  onJumpToPhase,
}: MessageListProps) {
  const groups = groupByRun(messages);

  // Pill-click + feedback both submit a new user-side intent string.
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
    <div className="flex flex-col gap-4">
      {groups.map((g, i) => {
        const isCurrent = g.run_id === currentRunId;
        const title = deriveRunTitle(g.messages);

        return (
          <RunContainer
            key={g.run_id}
            index={i + 1}
            title={title}
            isCurrent={isCurrent}
          >
            {g.messages.map((m) => (
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
                  <div
                    className="flex max-w-[95%] flex-col gap-2.5 rounded-2xl rounded-bl-sm px-3.5 py-2.5"
                    style={{
                      background: "var(--bg-elevated)",
                      border: "1px solid var(--border-subtle)",
                    }}
                  >
                    {(m.blocks ?? []).map((b, j) =>
                      renderBlock(b, j, handlers),
                    )}
                  </div>
                )}
              </div>
            ))}
          </RunContainer>
        );
      })}
    </div>
  );
}
