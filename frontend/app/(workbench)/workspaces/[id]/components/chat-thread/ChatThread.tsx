"use client";

/**
 * ChatThread · Plan 2 T13
 *
 * Top-level left-panel chat container. Composes the message list (or
 * empty state when no messages exist) above the input area. Threads
 * `onSubmit` and `onJumpToPhase` down so blocks (question_card pills,
 * result_card feedback, status_line jump-targets) can drive the
 * conversation forward.
 *
 * Pass `inputArea` to replace the default minimal InputArea with a
 * production composer (e.g. WorkspaceThreadComposer with model picker,
 * skill selector, attachments).
 */
import type { ReactNode } from "react";

import { ChatMessage, MessageList } from "./MessageList";
import { EmptyState } from "./EmptyState";
import { InputArea } from "./InputArea";

interface FeatureMeta {
  id: string;
  name: string;
  description: string;
}

interface ChatThreadProps {
  workspaceId: string;
  messages: ChatMessage[];
  currentRunId: string | null;
  feature: FeatureMeta | null;
  starterPrompts: string[];
  onSubmit?: (text: string) => void;
  onJumpToPhase?: (runId: string, phaseIndex: number) => void;
  inputArea?: ReactNode;
}

export function ChatThread({
  messages,
  currentRunId,
  feature,
  starterPrompts,
  onSubmit,
  onJumpToPhase,
  inputArea,
}: ChatThreadProps) {
  const submit = onSubmit ?? (() => {});

  return (
    <div
      className="flex h-full flex-col"
      style={{ background: "var(--bg-base)" }}
    >
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {messages.length === 0 ? (
          <EmptyState
            feature={feature}
            starterPrompts={starterPrompts}
            onPick={submit}
          />
        ) : (
          <MessageList
            messages={messages}
            currentRunId={currentRunId}
            onSubmit={submit}
            onJumpToPhase={onJumpToPhase}
          />
        )}
      </div>
      {inputArea ?? <InputArea onSubmit={submit} />}
    </div>
  );
}
