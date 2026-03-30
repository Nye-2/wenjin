"use client";

import { AnimatePresence, motion } from "framer-motion";
import { History, Plus, Sparkles, Trash2 } from "lucide-react";
import type { ThreadSummary, Workspace } from "@/lib/api";
import { ConversationExportTrigger } from "@/components/workspace/ConversationExportTrigger";
import { cn } from "@/lib/utils";
import type { Message } from "@/stores/chat";

interface WorkspaceChatHeaderProps {
  workspaceName: string | null | undefined;
  workspaceType?: Workspace["type"] | null;
  currentSkillLabel: string | null;
  currentThreadSummary: ThreadSummary | null;
  messages: Message[];
  isHistoryOpen: boolean;
  isThreadsLoading: boolean;
  threadId: string | null;
  threads: ThreadSummary[];
  deletingThreadId: string | null;
  isStreaming: boolean;
  resolveSkillLabel: (skillId: string | null | undefined) => string | null;
  onToggleHistory: () => void;
  onStartNewThread: () => void;
  onSelectThread: (threadId: string) => void;
  onDeleteThread: (threadId: string) => void;
}

export function WorkspaceChatHeader({
  workspaceName,
  workspaceType,
  currentSkillLabel,
  currentThreadSummary,
  messages,
  isHistoryOpen,
  isThreadsLoading,
  threadId,
  threads,
  deletingThreadId,
  isStreaming,
  resolveSkillLabel,
  onToggleHistory,
  onStartNewThread,
  onSelectThread,
  onDeleteThread,
}: WorkspaceChatHeaderProps) {
  return (
    <div className="border-b border-[var(--border-default)] bg-[rgba(251,248,242,0.92)] px-6 py-4 backdrop-blur-xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold text-[var(--text-primary)]">
            <Sparkles className="h-5 w-5 text-[var(--brand-brass)]" />
            {workspaceName || "问津工作主线"}
          </h2>
          <p className="text-xs text-[var(--text-muted)]">
            持续推进当前工作路径的主线会话
          </p>
        </div>
        <div className="flex items-center gap-2">
          {currentSkillLabel && (
            <span className="px-3 py-1 rounded-full text-xs font-medium bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
              {currentSkillLabel}
            </span>
          )}
          <ConversationExportTrigger
            thread={currentThreadSummary}
            messages={messages}
            workspaceType={workspaceType}
          />
          <button
            type="button"
            onClick={onStartNewThread}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--bg-muted)]"
          >
            <Plus className="h-3.5 w-3.5" />
            新建分支
          </button>
          <button
            type="button"
            onClick={onToggleHistory}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--bg-muted)]"
          >
            <History className="h-3.5 w-3.5" />
            主线与分支
          </button>
        </div>
      </div>
      <AnimatePresence>
        {isHistoryOpen && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            className="mt-3 rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-2"
          >
            {isThreadsLoading ? (
              <p className="px-2 py-3 text-xs text-[var(--text-muted)]">
                正在加载主线 / 分支记录...
              </p>
            ) : threads.length === 0 ? (
              <p className="px-2 py-3 text-xs text-[var(--text-muted)]">
                当前工作区还没有可恢复的对话分支。
              </p>
            ) : (
              <div className="space-y-1">
                {threads.map((thread) => {
                  const isActive = thread.id === threadId;
                  const threadSkillLabel = resolveSkillLabel(thread.skill);
                  const label =
                    thread.title?.trim() ||
                    thread.last_message_preview ||
                    `${threadSkillLabel || "未命名会话"}`;
                  const secondaryText =
                    thread.title?.trim() && thread.last_message_preview
                      ? thread.last_message_preview
                      : null;
                  const metadataText =
                    `${threadSkillLabel || "未设置能力"} · ${
                      thread.message_count ?? 0
                    } 条消息`;
                  return (
                    <div
                      key={thread.id}
                      className={cn(
                        "flex items-start gap-2 rounded-lg px-2 py-1.5 transition-colors",
                        isActive
                          ? "bg-[var(--accent-primary)]/10"
                          : "hover:bg-[var(--bg-muted)]"
                      )}
                    >
                      <button
                        type="button"
                        onClick={() => onSelectThread(thread.id)}
                        className="min-w-0 flex-1 text-left"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p
                              className={cn(
                                "truncate text-sm font-medium",
                                isActive
                                  ? "text-[var(--accent-primary)]"
                                  : "text-[var(--text-primary)]"
                              )}
                            >
                              {label}
                            </p>
                            {secondaryText && (
                              <p className="mt-0.5 line-clamp-2 text-[11px] text-[var(--text-muted)]">
                                {secondaryText}
                              </p>
                            )}
                            <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                              {metadataText}
                            </p>
                          </div>
                          <span className="shrink-0 text-[11px] text-[var(--text-muted)]">
                            {new Date(thread.updated_at).toLocaleDateString()}
                          </span>
                        </div>
                      </button>
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          onDeleteThread(thread.id);
                        }}
                        disabled={deletingThreadId === thread.id || isStreaming}
                        className="mt-1 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[var(--text-muted)] transition-colors hover:bg-red-500/10 hover:text-red-500 disabled:cursor-not-allowed disabled:opacity-50"
                        aria-label="删除会话"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
