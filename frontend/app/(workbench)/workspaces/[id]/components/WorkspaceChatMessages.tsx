"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  Clock3,
  FileText,
  Sparkles,
  User,
} from "lucide-react";
import { StreamingText, ThinkingIndicator } from "@/components/glass";
import { type PaperExtractionSubmission } from "@/lib/api";
import { resolvePublicAssetUrl } from "@/lib/public-assets";
import {
  type WorkspaceFeatureActionContext,
} from "@/lib/workspace-feature-action-context";
import { cn } from "@/lib/utils";
import type { Message } from "@/stores/chat";

type NextStepActionType =
  | "trigger_feature"
  | "open_feature"
  | "continue_chat"
  | "rerun_from_artifact";

export interface WorkspaceChatMessageActionHandlers {
  onFeatureAction: (featureId: string) => void;
  onOpenFeature: (route: string | null, featureId: string | null) => void;
  onContinueAsk: (prompt: string | null) => void;
  onRerunFeature: (
    featureId: string | null,
    params: Record<string, unknown> | null,
    unavailableReason: string | null
  ) => void;
}

interface WorkspaceChatMessageBubbleProps
  extends WorkspaceChatMessageActionHandlers {
  message: Message;
  isLast: boolean;
  isStreaming: boolean;
  actionContext: WorkspaceFeatureActionContext;
}

interface WorkspaceChatMessagesProps extends WorkspaceChatMessageActionHandlers {
  messages: Message[];
  isStreaming: boolean;
  workspaceName: string | null | undefined;
  resolveActionContext: (message: Message) => WorkspaceFeatureActionContext;
}

type AttachmentRecord = Record<string, unknown>;

export function resolveBlockFeatureId(message: Message): string | null {
  for (const block of message.blocks) {
    if (!block.data || typeof block.data !== "object") {
      continue;
    }
    const featureId = (block.data as Record<string, unknown>).feature_id;
    if (typeof featureId === "string") {
      return featureId;
    }
  }
  return null;
}

function readMessageAttachments(message: Message): AttachmentRecord[] {
  const attachments = message.metadata?.attachments;
  if (!Array.isArray(attachments)) {
    return [];
  }
  return attachments.filter(
    (item): item is AttachmentRecord =>
      Boolean(item) && typeof item === "object"
  );
}

function readAttachmentMetadata(attachment: AttachmentRecord): AttachmentRecord {
  const metadata = attachment.metadata;
  if (!metadata || typeof metadata !== "object") {
    return {};
  }
  return metadata as AttachmentRecord;
}

function readStringValue(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function readStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function readNumberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function resolveAttachmentUrl(value: unknown): string | null {
  const raw = readStringValue(value);
  return raw ? resolvePublicAssetUrl(raw) : null;
}

function formatFileSize(size: unknown): string | null {
  if (typeof size !== "number" || !Number.isFinite(size) || size <= 0) {
    return null;
  }
  if (size < 1024 * 1024) {
    return `${Math.max(1, Math.round(size / 1024))} KB`;
  }
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function truncateText(value: string, maxChars: number = 180): string {
  if (value.length <= maxChars) {
    return value;
  }
  return `${value.slice(0, maxChars - 1).trimEnd()}…`;
}

function formatAttachmentStorage(attachment: AttachmentRecord): string {
  const paperId = readStringValue(attachment.paper_id);
  const artifactId = readStringValue(attachment.artifact_id);

  switch (attachment.kind) {
    case "literature":
      return paperId ? "已归档到文献中心" : "文献附件";
    case "workspace_context":
      return artifactId ? "已归档到工作区上下文" : "工作区上下文附件";
    default:
      return "仅用于当前对话";
  }
}

function formatAttachmentKind(kind: unknown): string {
  switch (kind) {
    case "literature":
      return "核心文献";
    case "workspace_context":
      return "工作区上下文";
    default:
      return "临时附件";
  }
}

function readAttachmentExtraction(
  attachment: AttachmentRecord
): PaperExtractionSubmission | null {
  const extraction = readAttachmentMetadata(attachment).extraction;
  if (!extraction || typeof extraction !== "object") {
    return null;
  }

  const payload = extraction as Record<string, unknown>;
  const status = readStringValue(payload.status);
  if (!status) {
    return null;
  }

  return {
    task_id: readStringValue(payload.task_id),
    status,
    paper_id: readStringValue(payload.paper_id),
    workspace_id: readStringValue(payload.workspace_id),
    tier: readNumberValue(payload.tier),
    message: readStringValue(payload.message),
    reused_existing_task: Boolean(payload.reused_existing_task),
  };
}

function formatExtractionLabel(status: string): string {
  switch (status) {
    case "scheduled":
      return "抽取已排队";
    case "existing":
      return "复用抽取任务";
    case "failed":
      return "抽取排队失败";
    default:
      return status;
  }
}

function renderMessageAttachments(message: Message, isUser: boolean) {
  const attachments = readMessageAttachments(message);
  if (attachments.length === 0) {
    return null;
  }

  return (
    <div className="mb-3 space-y-2">
      {attachments.map((attachment, index) => {
        const name =
          readStringValue(attachment.name) ?? `附件 ${index + 1}`;
        const metadata = readAttachmentMetadata(attachment);
        const storedUrl = resolveAttachmentUrl(metadata.stored_url);
        const threadUrl = resolveAttachmentUrl(metadata.thread_url ?? attachment.url);
        const primaryUrl = storedUrl ?? threadUrl;
        const documentTitle = readStringValue(metadata.document_title);
        const authors = readStringArray(metadata.document_authors);
        const pageCount = readNumberValue(metadata.page_count);
        const textPreview = readStringValue(metadata.text_preview);
        const sizeLabel = formatFileSize(attachment.size_bytes);
        const paperId = readStringValue(attachment.paper_id);
        const artifactId = readStringValue(attachment.artifact_id);
        const extraction = readAttachmentExtraction(attachment);
        const storageLabel = formatAttachmentStorage(attachment);

        const extractionTone =
          extraction?.status === "failed"
            ? isUser
              ? "bg-red-500/15 text-white"
              : "bg-red-500/10 text-red-600"
            : extraction?.status === "existing"
              ? isUser
                ? "bg-sky-500/20 text-white"
                : "bg-sky-500/10 text-sky-600"
              : isUser
                ? "bg-amber-500/20 text-white"
                : "bg-amber-500/10 text-amber-600";

        return (
          <div
            key={`${name}-${index}`}
            className={cn(
              "rounded-xl border px-3 py-3",
              isUser
                ? "border-white/20 bg-white/10"
                : "border-[var(--border-default)] bg-[var(--bg-surface)]/70"
            )}
          >
            <div className="flex items-start gap-2">
              <FileText className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="min-w-0 flex-1 truncate text-xs font-medium">
                    {name}
                  </p>
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-[10px] font-medium",
                      isUser
                        ? "bg-white/15 text-white"
                        : "bg-[var(--bg-muted)] text-[var(--text-muted)]"
                    )}
                  >
                    {formatAttachmentKind(attachment.kind)}
                  </span>
                </div>

                <p
                  className={cn(
                    "mt-1 text-[11px]",
                    isUser ? "text-white/80" : "text-[var(--text-muted)]"
                  )}
                >
                  {storageLabel}
                  {sizeLabel ? ` · ${sizeLabel}` : ""}
                  {pageCount ? ` · ${pageCount} 页` : ""}
                </p>

                {documentTitle && documentTitle !== name ? (
                  <p
                    className={cn(
                      "mt-2 text-xs font-medium",
                      isUser ? "text-white" : "text-[var(--text-primary)]"
                    )}
                  >
                    {documentTitle}
                  </p>
                ) : null}

                {authors.length > 0 ? (
                  <p
                    className={cn(
                      "mt-1 text-[11px]",
                      isUser ? "text-white/80" : "text-[var(--text-secondary)]"
                    )}
                  >
                    作者：{authors.slice(0, 4).join("、")}
                    {authors.length > 4 ? ` 等 ${authors.length} 人` : ""}
                  </p>
                ) : null}

                {extraction ? (
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <span
                      className={cn(
                        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium",
                        extractionTone
                      )}
                    >
                      {extraction.status === "failed" ? (
                        <AlertCircle className="h-3 w-3" />
                      ) : extraction.status === "existing" ? (
                        <CheckCircle2 className="h-3 w-3" />
                      ) : (
                        <Clock3 className="h-3 w-3" />
                      )}
                      {formatExtractionLabel(extraction.status)}
                    </span>
                    {extraction.task_id ? (
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-[10px]",
                          isUser
                            ? "bg-white/10 text-white/90"
                            : "bg-[var(--bg-muted)] text-[var(--text-muted)]"
                        )}
                      >
                        Task {extraction.task_id.slice(0, 8)}
                      </span>
                    ) : null}
                  </div>
                ) : null}

                {extraction?.message ? (
                  <p
                    className={cn(
                      "mt-2 text-[11px]",
                      extraction.status === "failed"
                        ? isUser
                          ? "text-white/90"
                          : "text-red-600/90"
                        : isUser
                          ? "text-white/80"
                          : "text-[var(--text-secondary)]"
                    )}
                  >
                    {truncateText(extraction.message, 120)}
                  </p>
                ) : null}

                {textPreview ? (
                  <p
                    className={cn(
                      "mt-2 text-[11px] leading-5",
                      isUser ? "text-white/90" : "text-[var(--text-secondary)]"
                    )}
                  >
                    {truncateText(textPreview)}
                  </p>
                ) : null}

                {paperId || artifactId ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {paperId ? (
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-[10px]",
                          isUser
                            ? "bg-white/10 text-white/90"
                            : "bg-[var(--bg-muted)] text-[var(--text-muted)]"
                        )}
                      >
                        Paper {paperId.slice(0, 8)}
                      </span>
                    ) : null}
                    {artifactId ? (
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-[10px]",
                          isUser
                            ? "bg-white/10 text-white/90"
                            : "bg-[var(--bg-muted)] text-[var(--text-muted)]"
                        )}
                      >
                        Artifact {artifactId.slice(0, 8)}
                      </span>
                    ) : null}
                  </div>
                ) : null}

                {primaryUrl ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    <a
                      href={primaryUrl}
                      target="_blank"
                      rel="noreferrer"
                      className={cn(
                        "rounded-full px-2.5 py-1 text-[11px] font-medium",
                        isUser
                          ? "bg-white/15 text-white"
                          : "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]"
                      )}
                    >
                      查看详情
                    </a>
                    {storedUrl && threadUrl && storedUrl !== threadUrl ? (
                      <a
                        href={threadUrl}
                        target="_blank"
                        rel="noreferrer"
                        className={cn(
                          "rounded-full border px-2.5 py-1 text-[11px] font-medium",
                          isUser
                            ? "border-white/20 bg-transparent text-white"
                            : "border-[var(--border-default)] bg-[var(--bg-surface)] text-[var(--text-primary)]"
                        )}
                      >
                        线程副本
                      </a>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function renderCardActions(
  actionContext: WorkspaceFeatureActionContext,
  handlers: WorkspaceChatMessageActionHandlers
) {
  if (!actionContext.featureId) {
    return null;
  }

  return (
    <div className="mt-3 flex flex-wrap gap-2">
      <button
        type="button"
        onClick={() =>
          handlers.onOpenFeature(actionContext.route, actionContext.featureId)
        }
        className="rounded-full bg-[var(--accent-primary)]/10 px-2.5 py-1 text-[11px] font-medium text-[var(--accent-primary)]"
      >
        直接跳转
      </button>
      <button
        type="button"
        onClick={() => handlers.onContinueAsk(actionContext.followUpPrompt)}
        className="rounded-full border border-[var(--border-default)] bg-[var(--bg-muted)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-primary)]"
      >
        继续追问
      </button>
      <button
        type="button"
        onClick={() =>
          handlers.onRerunFeature(
            actionContext.featureId,
            actionContext.rerunParams,
            actionContext.rerunUnavailableReason
          )
        }
        title={actionContext.rerunUnavailableReason || undefined}
        className={cn(
          "rounded-full border border-[var(--border-default)] bg-[var(--bg-muted)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-primary)]",
          !actionContext.rerunParams && "opacity-60"
        )}
      >
        基于 artifact 二次执行
      </button>
    </div>
  );
}

function renderStructuredBlocks(
  message: Message,
  actionContext: WorkspaceFeatureActionContext,
  handlers: WorkspaceChatMessageActionHandlers
) {
  if (!message.blocks || message.blocks.length === 0) {
    return null;
  }

  return (
    <div className="mt-3 space-y-2">
      {message.blocks.map((block, index) => {
        const data = block.data ?? {};
        if (block.type === "task") {
          const featureId = typeof data.feature_id === "string" ? data.feature_id : null;
          return (
            <div
              key={`${block.type}-${index}`}
              className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)]/70 px-3 py-3"
            >
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-[var(--text-primary)]">
                    {block.title || "任务已启动"}
                  </p>
                  <p className="mt-1 text-xs text-[var(--text-secondary)]">
                    {typeof data.message === "string" ? data.message : "任务已进入执行队列。"}
                  </p>
                </div>
                <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-600">
                  {typeof data.status === "string" ? data.status : "pending"}
                </span>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {typeof data.task_id === "string" && (
                  <span className="rounded-full bg-[var(--bg-muted)] px-2 py-1 text-[11px] text-[var(--text-muted)]">
                    Task {data.task_id.slice(0, 8)}
                  </span>
                )}
              </div>
              {featureId ? renderCardActions(actionContext, handlers) : null}
            </div>
          );
        }

        if (block.type === "warning") {
          const featureId = typeof data.feature_id === "string" ? data.feature_id : null;
          return (
            <div
              key={`${block.type}-${index}`}
              className="rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-3"
            >
              <p className="text-sm font-medium text-red-600 dark:text-red-400">
                {block.title || "暂时无法执行"}
              </p>
              <p className="mt-1 text-xs leading-5 text-red-600/90 dark:text-red-300">
                {typeof data.detail === "string" ? data.detail : message.content}
              </p>
              {featureId ? renderCardActions(actionContext, handlers) : null}
            </div>
          );
        }

        if (block.type === "result") {
          const featureId = typeof data.feature_id === "string" ? data.feature_id : null;
          return (
            <div
              key={`${block.type}-${index}`}
              className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)]/70 px-3 py-3"
            >
              <p className="text-sm font-medium text-[var(--text-primary)]">
                {block.title || "结果摘要"}
              </p>
              <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                {typeof data.summary === "string" ? data.summary : message.content}
              </p>
              {featureId ? renderCardActions(actionContext, handlers) : null}
            </div>
          );
        }

        if (block.type === "artifacts") {
          const items = Array.isArray(data.items) ? data.items : [];
          return (
            <div
              key={`${block.type}-${index}`}
              className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)]/70 px-3 py-3"
            >
              <p className="text-sm font-medium text-[var(--text-primary)]">
                {block.title || "输出文件"}
              </p>
              <div className="mt-3 space-y-2">
                {items.map((item, itemIndex) => {
                  const name =
                    typeof item?.name === "string"
                      ? item.name
                      : typeof item?.path === "string"
                        ? item.path
                        : `文件 ${itemIndex + 1}`;
                  const path = typeof item?.path === "string" ? item.path : null;
                  const url = typeof item?.url === "string" ? item.url : null;
                  const downloadUrl =
                    typeof item?.download_url === "string" ? item.download_url : url;
                  return (
                    <div
                      key={`${name}-${itemIndex}`}
                      className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-muted)]/60 px-3 py-2"
                    >
                      <p className="text-xs font-medium text-[var(--text-primary)]">
                        {name}
                      </p>
                      {path ? (
                        <p className="mt-1 break-all text-[11px] text-[var(--text-muted)]">
                          {path}
                        </p>
                      ) : null}
                      {url ? (
                        <div className="mt-3 flex flex-wrap gap-2">
                          <a
                            href={url}
                            target="_blank"
                            rel="noreferrer"
                            className="rounded-full bg-[var(--accent-primary)]/10 px-2.5 py-1 text-[11px] font-medium text-[var(--accent-primary)]"
                          >
                            打开文件
                          </a>
                          <a
                            href={downloadUrl || url}
                            target="_blank"
                            rel="noreferrer"
                            className="rounded-full border border-[var(--border-default)] bg-[var(--bg-surface)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-primary)]"
                          >
                            下载
                          </a>
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        }

        if (block.type === "next_steps") {
          const items = Array.isArray(data.items) ? data.items : [];
          return (
            <div
              key={`${block.type}-${index}`}
              className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)]/70 px-3 py-3"
            >
              <p className="text-sm font-medium text-[var(--text-primary)]">
                {block.title || "建议下一步"}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {items.map((item, itemIndex) => {
                  const label =
                    typeof item?.label === "string"
                      ? item.label
                      : `建议 ${itemIndex + 1}`;
                  const featureId =
                    typeof item?.feature_id === "string" ? item.feature_id : null;
                  const actionType =
                    typeof item?.action === "string"
                      ? (item.action as NextStepActionType)
                      : "trigger_feature";
                  const prompt =
                    typeof item?.prompt === "string"
                      ? item.prompt
                      : actionContext.followUpPrompt;
                  const disabled = !featureId;
                  const tooltip =
                    actionType === "rerun_from_artifact"
                      ? actionContext.rerunUnavailableReason || undefined
                      : undefined;
                  return (
                    <button
                      type="button"
                      key={`${label}-${itemIndex}`}
                      onClick={() => {
                        if (!featureId) {
                          return;
                        }
                        if (actionType === "open_feature") {
                          handlers.onOpenFeature(null, featureId);
                          return;
                        }
                        if (actionType === "continue_chat") {
                          handlers.onContinueAsk(prompt);
                          return;
                        }
                        if (actionType === "rerun_from_artifact") {
                          handlers.onRerunFeature(
                            featureId,
                            actionContext.rerunParams,
                            actionContext.rerunUnavailableReason
                          );
                          return;
                        }
                        handlers.onFeatureAction(featureId);
                      }}
                      disabled={disabled}
                      title={tooltip}
                      className="rounded-full border border-[var(--border-default)] bg-[var(--bg-muted)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-primary)] disabled:cursor-default disabled:opacity-80"
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        }

        return (
          <div
            key={`${block.type}-${index}`}
            className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)]/70 px-3 py-3"
          >
            <p className="text-sm font-medium text-[var(--text-primary)]">
              {block.title || block.type}
            </p>
          </div>
        );
      })}
    </div>
  );
}

function WorkspaceChatMessageBubble({
  message,
  isLast,
  isStreaming,
  actionContext,
  onFeatureAction,
  onOpenFeature,
  onContinueAsk,
  onRerunFeature,
}: WorkspaceChatMessageBubbleProps) {
  const isUser = message.role === "user";
  const showStreaming = isLast && !isUser && isStreaming && !message.content;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={cn("flex gap-3", isUser ? "flex-row-reverse" : "flex-row")}
    >
      <div
        className={cn(
          "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center",
          isUser
            ? "bg-[var(--accent-primary)] text-white"
            : "bg-gradient-to-br from-[var(--accent-primary)] to-[var(--accent-secondary)] text-white"
        )}
      >
        {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
      </div>

      <div
        className={cn(
          "max-w-[80%] rounded-2xl px-4 py-3",
          isUser
            ? "bg-[var(--accent-primary)] text-white rounded-tr-md"
            : "bg-[var(--bg-elevated)] backdrop-blur-sm text-[var(--text-primary)] rounded-tl-md border border-[var(--border-default)]"
        )}
      >
        {showStreaming ? (
          <ThinkingIndicator />
        ) : isLast && !isUser && isStreaming ? (
          <StreamingText text={message.content} isStreaming={true} />
        ) : (
          <>
            {renderMessageAttachments(message, isUser)}
            {message.content ? (
              <p className="text-sm whitespace-pre-wrap">{message.content}</p>
            ) : null}
            {renderStructuredBlocks(message, actionContext, {
              onFeatureAction,
              onOpenFeature,
              onContinueAsk,
              onRerunFeature,
            })}
          </>
        )}
      </div>
    </motion.div>
  );
}

export function WorkspaceChatMessages({
  messages,
  isStreaming,
  workspaceName,
  resolveActionContext,
  onFeatureAction,
  onOpenFeature,
  onContinueAsk,
  onRerunFeature,
}: WorkspaceChatMessagesProps) {
  return (
    <AnimatePresence mode="popLayout">
      {messages.length === 0 ? (
        <div className="h-full flex items-center justify-center">
          <div className="text-center max-w-md">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gradient-to-br from-[var(--accent-primary)] to-[var(--accent-secondary)] flex items-center justify-center">
              <Sparkles className="w-8 h-8 text-white" />
            </div>
            <h3 className="text-lg font-semibold text-[var(--text-primary)] mb-2">
              从 chat 启动你的任务主线
            </h3>
            <p className="text-sm text-[var(--text-secondary)]">
              先描述你现在要推进的步骤，或直接点击下方推荐动作。
              我会结合当前 workspace
              {workspaceName ? `「${workspaceName}」` : ""} 进度来安排下一步。
            </p>
          </div>
        </div>
      ) : (
        messages.map((message, index) => (
          <WorkspaceChatMessageBubble
            key={message.id}
            message={message}
            isLast={index === messages.length - 1}
            isStreaming={isStreaming}
            actionContext={resolveActionContext(message)}
            onFeatureAction={onFeatureAction}
            onOpenFeature={onOpenFeature}
            onContinueAsk={onContinueAsk}
            onRerunFeature={onRerunFeature}
          />
        ))
      )}
    </AnimatePresence>
  );
}
