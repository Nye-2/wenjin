"use client";

import { Sparkles } from "lucide-react";
import type { ThreadSummary } from "@/lib/api";
import { ConversationExportTrigger } from "@/components/workspace/ConversationExportTrigger";
import type { Message } from "@/stores/thread";

interface WorkspaceThreadHeaderProps {
  workspaceName: string | null | undefined;
  currentThreadSummary: ThreadSummary | null;
  messages: Message[];
}

export function WorkspaceThreadHeader({
  workspaceName,
  currentThreadSummary,
  messages,
}: WorkspaceThreadHeaderProps) {
  return (
    <div className="border-b border-[var(--border-default)] bg-[rgba(251,248,242,0.92)] px-6 py-4 backdrop-blur-xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold text-[var(--text-primary)]">
            <Sparkles className="h-5 w-5 text-[var(--brand-brass)]" />
            {workspaceName || "问津工作主线"}
          </h2>
          <p className="text-xs text-[var(--text-muted)]">
            通过对话确定需求，并在右侧工作面板中查看执行过程
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ConversationExportTrigger
            thread={currentThreadSummary}
            messages={messages}
          />
        </div>
      </div>
    </div>
  );
}
