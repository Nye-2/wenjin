"use client";

import { useState } from "react";
import { Download, FileJson, FileText } from "lucide-react";

import type { ThreadSummary } from "@/lib/api";
import { exportConversationAsJson, exportConversationAsMarkdown } from "@/lib/thread-export";
import type { Message } from "@/stores/chat-store-v2";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface ConversationExportTriggerProps {
  thread: ThreadSummary | null;
  messages: Message[];
}

export function ConversationExportTrigger({
  thread,
  messages,
}: ConversationExportTriggerProps) {
  const [open, setOpen] = useState(false);

  if (!thread || messages.length === 0) {
    return null;
  }

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5"
      >
        <Download className="h-3.5 w-3.5" />
        导出
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>导出当前会话</DialogTitle>
            <DialogDescription>
              导出当前 workspace 会话，便于留档、复盘或交付评审。
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <button
              type="button"
              onClick={() => {
                exportConversationAsMarkdown(thread, messages);
                setOpen(false);
              }}
              className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-4 text-left transition-colors hover:bg-[var(--bg-muted)]"
            >
              <div className="flex items-center gap-2 text-sm font-medium text-[var(--text-primary)]">
                <FileText className="h-4 w-4" />
                Markdown
              </div>
              <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
                适合发给导师、评审或直接放入项目文档。
              </p>
            </button>
            <button
              type="button"
              onClick={() => {
                exportConversationAsJson(thread, messages);
                setOpen(false);
              }}
              className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-4 text-left transition-colors hover:bg-[var(--bg-muted)]"
            >
              <div className="flex items-center gap-2 text-sm font-medium text-[var(--text-primary)]">
                <FileJson className="h-4 w-4" />
                JSON
              </div>
              <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
                保留完整结构化消息，适合二次处理或导入别的系统。
              </p>
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
