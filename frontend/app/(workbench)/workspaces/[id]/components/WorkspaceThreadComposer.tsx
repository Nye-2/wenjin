"use client";

import type {
  FormEvent,
  KeyboardEvent,
  RefObject,
} from "react";
import { motion } from "framer-motion";
import { Paperclip, Send, X } from "lucide-react";
import type { ThreadUploadKind, Model, ReasoningEffort } from "@/lib/api";
import { AgentStatusBar } from "@/components/workspace";
import { useI18n } from "@/components/i18n-provider";
import { cn } from "@/lib/utils";

export const WORKSPACE_THREAD_REASONING_EFFORT_OPTIONS: Array<{
  value: ReasoningEffort;
  label: string;
  description: string;
}> = [
  { value: "minimal", label: "极简", description: "默认快速响应" },
  { value: "low", label: "轻量", description: "轻量推理" },
  { value: "medium", label: "均衡", description: "平衡质量与延迟" },
  { value: "high", label: "深入", description: "更强推理，响应更慢" },
];

export function isReasoningEffort(value: string | null): value is ReasoningEffort {
  return WORKSPACE_THREAD_REASONING_EFFORT_OPTIONS.some(
    (option) => option.value === value
  );
}

export const WORKSPACE_THREAD_UPLOAD_KIND_OPTIONS: Array<{
  value: ThreadUploadKind;
  label: string;
  description: string;
}> = [
  {
    value: "literature",
    label: "核心文献",
    description: "进入文献中心并保留文件",
  },
  {
    value: "workspace_context",
    label: "工作区上下文",
    description: "存入工作区并沉淀基础材料",
  },
  {
    value: "transient",
    label: "临时附件",
    description: "仅用于当前主线 / 分支",
  },
];

interface PendingAttachment {
  id: string;
  name: string;
  size: number;
  kind: ThreadUploadKind;
}

interface WorkspaceThreadComposerProps {
  workspaceId: string;
  actionError: string | null;
  availableModels: Model[];
  selectedModel: string | null;
  onSelectModel: (modelId: string | null) => void;
  isStreaming: boolean;
  supportsReasoningEffort: boolean;
  selectedReasoningEffort: ReasoningEffort | null;
  onSelectReasoningEffort: (value: ReasoningEffort) => void;
  defaultUploadKind: ThreadUploadKind;
  onSelectDefaultUploadKind: (value: ThreadUploadKind) => void;
  pendingAttachments: PendingAttachment[];
  onOpenFilePicker: () => void;
  onRemoveAttachment: (attachmentId: string) => void;
  onUpdateAttachmentKind: (attachmentId: string, kind: ThreadUploadKind) => void;
  inputValue: string;
  onInputChange: (value: string) => void;
  inputRef: RefObject<HTMLTextAreaElement | null>;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onSubmit: (event: FormEvent) => void;
  onAbortStream: () => void;
}

export function WorkspaceThreadComposer({
  workspaceId,
  actionError,
  availableModels,
  selectedModel,
  onSelectModel,
  isStreaming,
  supportsReasoningEffort,
  selectedReasoningEffort,
  onSelectReasoningEffort,
  defaultUploadKind,
  onSelectDefaultUploadKind,
  pendingAttachments,
  onOpenFilePicker,
  onRemoveAttachment,
  onUpdateAttachmentKind,
  inputValue,
  onInputChange,
  inputRef,
  onKeyDown,
  onSubmit,
  onAbortStream,
}: WorkspaceThreadComposerProps) {
  const { t } = useI18n();

  return (
    <div className="p-4 border-t border-[var(--border-default)] bg-[var(--bg-elevated)] backdrop-blur-xl">
      <div className="mb-3">
        <AgentStatusBar workspaceId={workspaceId} />
      </div>

      {actionError && (
        <div className="mb-3 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-600 dark:text-red-400">
          {actionError}
        </div>
      )}

      <div className="mb-3 rounded-2xl border border-[var(--border-default)] bg-[var(--bg-surface)]/72 px-3 py-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
          对话工作流
        </p>
        <p className="mt-2 text-xs leading-6 text-[var(--text-secondary)]">
          直接描述你要推进的工作。问津会先确认需求，再决定是否启用内部模块或子代理。
        </p>
      </div>

      <div className="mb-3 flex items-center gap-3">
        <label
          htmlFor="thread-model-select"
          className="text-xs font-medium text-[var(--text-muted)]"
        >
          工作主线模型
        </label>
        <select
          id="thread-model-select"
          value={selectedModel ?? ""}
          onChange={(event) => onSelectModel(event.target.value || null)}
          disabled={availableModels.length === 0 || isStreaming}
          className="min-w-[220px] rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent-primary)] focus:outline-none"
        >
          {availableModels.length === 0 ? (
            <option value="">当前无可用模型</option>
          ) : (
            availableModels.map((model) => (
              <option key={model.name} value={model.name}>
                {model.display_name}
              </option>
            ))
          )}
        </select>
        {supportsReasoningEffort && (
          <>
            <label
              htmlFor="thread-reasoning-select"
              className="text-xs font-medium text-[var(--text-muted)]"
            >
              Reasoning
            </label>
            <select
              id="thread-reasoning-select"
              value={selectedReasoningEffort ?? "minimal"}
              onChange={(event) =>
                onSelectReasoningEffort(
                  isReasoningEffort(event.target.value)
                    ? event.target.value
                    : "minimal"
                )
              }
              disabled={isStreaming}
              className="min-w-[180px] rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent-primary)] focus:outline-none"
            >
              {WORKSPACE_THREAD_REASONING_EFFORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label} · {option.description}
                </option>
              ))}
            </select>
          </>
        )}
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-3">
        <label
          htmlFor="thread-upload-kind-select"
          className="text-xs font-medium text-[var(--text-muted)]"
        >
          上传归类
        </label>
        <select
          id="thread-upload-kind-select"
          value={defaultUploadKind}
          onChange={(event) =>
            onSelectDefaultUploadKind(event.target.value as ThreadUploadKind)
          }
          disabled={isStreaming}
          className="min-w-[220px] rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent-primary)] focus:outline-none"
        >
          {WORKSPACE_THREAD_UPLOAD_KIND_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label} · {option.description}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={onOpenFilePicker}
          disabled={isStreaming}
          className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)] transition-colors hover:border-[var(--border-focus)] disabled:opacity-60"
        >
          <Paperclip className="h-4 w-4" />
          添加附件
        </button>
      </div>

      {pendingAttachments.length > 0 ? (
        <div className="mb-3 flex flex-col gap-2">
          {pendingAttachments.map((attachment) => (
            <div
              key={attachment.id}
              className="flex flex-wrap items-center gap-3 rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)]/70 px-3 py-2"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                  {attachment.name}
                </p>
                <p className="text-[11px] text-[var(--text-muted)]">
                  {attachment.size < 1024 * 1024
                    ? `${Math.max(1, Math.round(attachment.size / 1024))} KB`
                    : `${(attachment.size / 1024 / 1024).toFixed(1)} MB`}
                </p>
              </div>
              <select
                value={attachment.kind}
                onChange={(event) =>
                  onUpdateAttachmentKind(
                    attachment.id,
                    event.target.value as ThreadUploadKind
                  )
                }
                disabled={isStreaming}
                className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-xs text-[var(--text-primary)] focus:border-[var(--accent-primary)] focus:outline-none"
              >
                {WORKSPACE_THREAD_UPLOAD_KIND_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => onRemoveAttachment(attachment.id)}
                disabled={isStreaming}
                className="rounded-full border border-[var(--border-default)] p-1 text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)] disabled:opacity-60"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      ) : null}

      <form onSubmit={onSubmit} className="flex gap-3">
        <div className="flex-1 relative">
          <textarea
            ref={inputRef}
            value={inputValue}
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder={t("chat.placeholder")}
            disabled={isStreaming}
            rows={1}
            className={cn(
              "w-full px-4 py-3 rounded-xl resize-none",
              "bg-[var(--bg-muted)]/70 backdrop-blur-sm",
              "border border-[var(--border-default)] focus:border-[var(--border-focus)]",
              "text-[var(--text-primary)] placeholder:text-[var(--text-muted)]",
              "focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/20",
              "transition-all duration-200"
            )}
          />
        </div>
        <motion.button
          type={isStreaming ? "button" : "submit"}
          onClick={isStreaming ? onAbortStream : undefined}
          disabled={!isStreaming && !inputValue.trim()}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          className={cn(
            "px-4 py-3 rounded-xl flex items-center justify-center",
            isStreaming
              ? "bg-red-500 text-white"
              : "bg-gradient-to-r from-[var(--accent-primary)] to-[#1D4ED8] text-white",
            "hover:shadow-lg transition-shadow",
            "disabled:opacity-50 disabled:cursor-not-allowed"
          )}
          aria-label={isStreaming ? t("chat.stop") : t("chat.send")}
          title={isStreaming ? t("chat.stop") : t("chat.send")}
        >
          {isStreaming ? <X className="w-5 h-5" /> : <Send className="w-5 h-5" />}
        </motion.button>
      </form>
    </div>
  );
}
