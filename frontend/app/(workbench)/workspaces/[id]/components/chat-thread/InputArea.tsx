"use client";

/**
 * InputArea · Plan 2 T13
 *
 * Thin shell around the chat composer. The real attachment-aware
 * WorkspaceThreadComposer is mounted in Plan 3 once the existing
 * composer is reconciled with the new thread store. For now this is
 * a minimal text input + cancel-current-run button.
 */
import { useState } from "react";

import { cancelRun } from "@/lib/api/runs";
import { useWorkflowStore } from "@/stores/workflow-store";

interface InputAreaProps {
  onSubmit: (text: string) => void;
}

export function InputArea({ onSubmit }: InputAreaProps) {
  const [draft, setDraft] = useState("");
  const currentRunId = useWorkflowStore((s) => s.currentRunId);
  const pausedRunIds = useWorkflowStore((s) => s.pausedRunIds);
  const isPaused = currentRunId ? pausedRunIds.has(currentRunId) : false;

  const placeholder = currentRunId
    ? "或者直接说想法..."
    : "输入开始对话...";

  return (
    <div
      className="px-4 py-3"
      style={{ borderTop: "1px solid var(--border-subtle)" }}
    >
      {currentRunId && !isPaused && (
        <button
          type="button"
          onClick={() => {
            void cancelRun(currentRunId).catch(() => {
              // best-effort
            });
          }}
          className="mb-2 rounded px-2.5 py-1 text-[11.5px] transition-opacity hover:opacity-80"
          style={{
            background: "rgba(196, 43, 43, 0.06)",
            border: "1px solid rgba(196, 43, 43, 0.3)",
            color: "var(--semantic-error)",
          }}
        >
          中断当前任务
        </button>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          const text = draft.trim();
          if (text) {
            onSubmit(text);
            setDraft("");
          }
        }}
      >
        <input
          name="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="w-full rounded-md px-3.5 py-2.5 text-[13.5px] outline-none transition-colors"
          style={{
            background: "var(--input-bg)",
            border: "1px solid var(--border-subtle)",
            color: "var(--text-primary)",
          }}
          placeholder={placeholder}
          autoComplete="off"
        />
      </form>
    </div>
  );
}
