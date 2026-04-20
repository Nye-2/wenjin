"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock3,
  FileText,
  Sparkles,
  User,
} from "lucide-react";
import { StreamingText, ThinkingIndicator } from "@/components/glass";
import { MarkdownRenderer } from "@/components/ui/markdown-renderer";
import { type PaperExtractionSubmission } from "@/lib/api";
import { parseThreadTokenUsage } from "@/lib/thread-token-usage";
import {
  readWorkspaceFeatureOrchestrationParams,
  resolveWorkspaceFeatureActionContext,
} from "@/lib/workspace-feature-action-context";
import { getWorkspaceFeatureThreadRoute } from "@/lib/workspace-feature-routes";
import { openAuthorizedAsset, resolvePublicAssetUrl } from "@/lib/public-assets";
import { cn } from "@/lib/utils";
import { useFeaturesStore } from "@/stores/features";
import type { Message } from "@/stores/thread";
import { useWorkspaceStore } from "@/stores/workspace";

interface WorkspaceThreadMessageBubbleProps
{
  message: Message;
  isLast: boolean;
  isStreaming: boolean;
  workspaceId: string;
}

interface WorkspaceThreadMessagesProps {
  workspaceId: string;
  messages: Message[];
  isStreaming: boolean;
  isThreadLoading?: boolean;
  workspaceName: string | null | undefined;
}

type AttachmentRecord = Record<string, unknown>;
type RouteParamScalar = string | number | boolean;
type RouteParamMap = Record<
  string,
  RouteParamScalar | Array<RouteParamScalar>
>;

function extractReasoningBlockText(message: Message): string | null {
  for (const block of message.blocks) {
    if (block.type !== "reasoning") {
      continue;
    }
    const text =
      block.data && typeof block.data === "object" && typeof block.data.text === "string"
        ? block.data.text.trim()
        : "";
    if (text) {
      return text;
    }
  }
  return null;
}

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

type CardActionType =
  | "trigger_feature"
  | "continue_thread"
  | "open_feature"
  | "rerun_from_artifact";

interface CardActionItem {
  label: string;
  action: CardActionType;
  featureId: string | null;
  routeParams?: RouteParamMap;
  disabled?: boolean;
  title?: string;
}

interface RerunAvailability {
  canRerun: boolean;
  reason: string | null;
}

function readMessageOrchestration(
  message: Message
): Record<string, unknown> | null {
  const orchestration = message.metadata?.orchestration;
  if (!orchestration || typeof orchestration !== "object") {
    return null;
  }
  return orchestration as Record<string, unknown>;
}

function resolveMessageFeatureId(message: Message): string | null {
  const blockFeatureId = resolveBlockFeatureId(message);
  if (blockFeatureId) {
    return blockFeatureId;
  }
  const orchestration = readMessageOrchestration(message);
  const featureId = orchestration?.feature_id;
  return typeof featureId === "string" && featureId.trim() ? featureId : null;
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

function sanitizeRouteParamMap(value: unknown): RouteParamMap {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }

  const routeParams: RouteParamMap = {};
  for (const [key, raw] of Object.entries(value as Record<string, unknown>)) {
    if (!key.trim()) {
      continue;
    }

    if (typeof raw === "string") {
      const normalized = raw.trim();
      if (normalized) {
        routeParams[key] = normalized;
      }
      continue;
    }
    if (typeof raw === "number" && Number.isFinite(raw)) {
      routeParams[key] = raw;
      continue;
    }
    if (typeof raw === "boolean") {
      routeParams[key] = raw;
      continue;
    }
    if (Array.isArray(raw)) {
      const normalized = raw
        .map((item) => {
          if (typeof item === "string") {
            const trimmed = item.trim();
            return trimmed || null;
          }
          if (typeof item === "number" && Number.isFinite(item)) {
            return item;
          }
          if (typeof item === "boolean") {
            return item;
          }
          return null;
        })
        .filter(
          (item): item is RouteParamScalar =>
            typeof item === "string" ||
            typeof item === "number" ||
            typeof item === "boolean"
        );
      if (normalized.length > 0) {
        routeParams[key] = normalized;
      }
    }
  }

  return routeParams;
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
    progress: readNumberValue(payload.progress),
    current_step: readStringValue(payload.current_step),
    error: readStringValue(payload.error),
    reused_existing_task: Boolean(payload.reused_existing_task),
  };
}

function formatExtractionLabel(status: string): string {
  switch (status) {
    case "scheduled":
      return "抽取已排队";
    case "existing":
      return "复用抽取任务";
    case "pending":
      return "等待抽取";
    case "running":
      return "正在抽取";
    case "success":
      return "抽取完成";
    case "failed":
      return "抽取失败";
    case "cancelled":
      return "抽取已取消";
    default:
      return status;
  }
}

function renderTokenUsageTags(metadata: Record<string, unknown> | null, isUser: boolean) {
  const usage = parseThreadTokenUsage(metadata);
  if (!usage || isUser) {
    return null;
  }

  const chips: string[] = [];
  if (usage.total_tokens > 0) {
    chips.push(`${usage.total_tokens.toLocaleString()} tokens`);
  }
  if (usage.input_tokens > 0 || usage.output_tokens > 0) {
    chips.push(
      `输入 ${usage.input_tokens.toLocaleString()} / 输出 ${usage.output_tokens.toLocaleString()}`
    );
  }
  if (usage.credits_charged && usage.credits_charged > 0) {
    chips.push(`扣费 ${usage.credits_charged.toLocaleString()} 积分`);
  }
  if (usage.model_name) {
    chips.push(usage.model_name);
  }
  if (chips.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5 pt-1">
      {chips.map((chip, index) => (
        <span
          key={`${chip}-${index}`}
          className="rounded-full border border-[var(--border-default)] bg-[var(--bg-surface)]/70 px-2 py-0.5 text-[10px] text-[var(--text-muted)]"
        >
          {chip}
        </span>
      ))}
    </div>
  );
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
          extraction?.status === "failed" || extraction?.status === "cancelled"
            ? isUser
              ? "bg-red-500/15 text-white"
              : "bg-red-500/10 text-red-600"
            : extraction?.status === "existing" || extraction?.status === "success"
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
                      ) : extraction.status === "cancelled" ? (
                        <AlertCircle className="h-3 w-3" />
                      ) : extraction.status === "existing" ||
                        extraction.status === "success" ? (
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
                        任务 {extraction.task_id.slice(0, 8)}
                      </span>
                    ) : null}
                  </div>
                ) : null}

                {typeof extraction?.progress === "number" &&
                extraction.status === "running" ? (
                  <p
                    className={cn(
                      "mt-2 text-[11px]",
                      isUser ? "text-white/85" : "text-[var(--text-secondary)]"
                    )}
                  >
                    进度 {Math.max(0, Math.min(100, extraction.progress))}%
                    {extraction.current_step ? ` · ${extraction.current_step}` : ""}
                  </p>
                ) : null}

                {extraction?.message ? (
                  <p
                    className={cn(
                      "mt-2 text-[11px]",
                      extraction.status === "failed" || extraction.status === "cancelled"
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
                        文献 {paperId.slice(0, 8)}
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
                        成果 {artifactId.slice(0, 8)}
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

function renderCardActions(options: {
  actions: CardActionItem[];
  onAction?: (
    action: CardActionType,
    featureId: string | null,
    routeParams?: RouteParamMap | null
  ) => void;
}) {
  if (options.actions.length === 0 || !options.onAction) {
    return null;
  }

  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {options.actions.map((item, index) => (
        <button
          key={`${item.action}-${item.featureId || "none"}-${index}`}
          type="button"
          disabled={Boolean(item.disabled)}
          title={item.title}
          onClick={() =>
            options.onAction?.(item.action, item.featureId, item.routeParams ?? null)
          }
          className={cn(
            "rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors",
            item.disabled
              ? "cursor-not-allowed border-[var(--border-default)] bg-[var(--bg-surface)] text-[var(--text-muted)] opacity-70"
              : "border-[var(--border-default)] bg-[var(--bg-surface)] text-[var(--text-primary)] hover:bg-[var(--bg-muted)]"
          )}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

function ReasoningPanel({
  text,
  isStreaming,
}: {
  text: string;
  isStreaming: boolean;
}) {
  const [isExpanded, setIsExpanded] = useState(isStreaming);

  return (
    <div
      className={cn(
        "overflow-hidden rounded-2xl border",
        isStreaming
          ? "border-amber-500/35 bg-[linear-gradient(180deg,rgba(245,158,11,0.12),rgba(245,158,11,0.05))] shadow-[0_10px_30px_rgba(245,158,11,0.08)]"
          : "border-[var(--border-default)] bg-[linear-gradient(180deg,rgba(244,216,170,0.16),rgba(255,255,255,0.72))]"
      )}
    >
      <button
        type="button"
        onClick={() => setIsExpanded((current) => !current)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <div className="flex min-w-0 items-center gap-3">
          <div
            className={cn(
              "flex h-8 w-8 shrink-0 items-center justify-center rounded-xl",
              isStreaming
                ? "bg-amber-500/20 text-amber-700"
                : "bg-[var(--bg-surface)] text-[var(--brand-brass)]"
            )}
          >
            <Sparkles className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium text-[var(--text-primary)]">
              思考过程
            </p>
            <p className="text-[11px] text-[var(--text-muted)]">
              {isStreaming ? "实时推理通道" : "已完成，可展开查看"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isStreaming ? (
            <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-700">
              处理中
            </span>
          ) : null}
          {isExpanded ? (
            <ChevronUp className="h-4 w-4 text-[var(--text-muted)]" />
          ) : (
            <ChevronDown className="h-4 w-4 text-[var(--text-muted)]" />
          )}
        </div>
      </button>

      <AnimatePresence initial={false}>
        {isExpanded ? (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="overflow-hidden border-t border-black/5"
          >
            <div className="px-4 py-3">
              {isStreaming ? (
                <StreamingText
                  text={text}
                  isStreaming={true}
                  className="text-xs leading-6 text-[var(--text-secondary)]"
                  cursorClassName="bg-amber-500"
                />
              ) : (
                <MarkdownRenderer
                  content={text}
                  className="text-xs leading-6 text-[var(--text-secondary)]"
                />
              )}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

function renderStructuredBlocks(
  message: Message,
  options?: {
    isStreaming?: boolean;
    onCardAction?: (
      action: CardActionType,
      featureId: string | null,
      routeParams?: RouteParamMap | null
    ) => void;
    resolveRerunAvailability?: (featureId: string | null) => RerunAvailability;
  }
) {
  if (!message.blocks || message.blocks.length === 0) {
    return null;
  }

  return (
    <div className="mt-3 space-y-2">
      {message.blocks.map((block, index) => {
        const data = block.data ?? {};
        if (block.type === "reasoning") {
          const text = typeof data.text === "string" ? data.text : "";
          if (!text.trim()) {
            return null;
          }
          return <ReasoningPanel key={`${block.type}-${index}`} text={text} isStreaming={Boolean(options?.isStreaming)} />;
        }

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
                    任务 {data.task_id.slice(0, 8)}
                  </span>
                )}
                <span className="rounded-full bg-[var(--accent-primary)]/10 px-2 py-1 text-[11px] font-medium text-[var(--accent-primary)]">
                  右侧工作面板会持续更新执行过程
                </span>
              </div>
              {featureId
                ? renderCardActions({
                    onAction: options?.onCardAction,
                    actions: [
                      {
                        label: "打开对应模块",
                        action: "open_feature",
                        featureId,
                      },
                      {
                        label: "继续在线程里推进",
                        action: "continue_thread",
                        featureId,
                      },
                    ],
                  })
                : null}
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
              {featureId
                ? renderCardActions({
                    onAction: options?.onCardAction,
                    actions: [
                      {
                        label: "打开对应模块",
                        action: "open_feature",
                        featureId,
                      },
                      {
                        label: "回到线程继续",
                        action: "continue_thread",
                        featureId,
                      },
                    ],
                  })
                : null}
            </div>
          );
        }

        if (block.type === "result") {
          const featureId = typeof data.feature_id === "string" ? data.feature_id : null;
          const rerunAvailability =
            options?.resolveRerunAvailability?.(featureId) ?? {
              canRerun: false,
              reason: "当前卡片没有可复用的 artifact 执行上下文。",
            };
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
              {featureId
                ? renderCardActions({
                    onAction: options?.onCardAction,
                    actions: [
                      {
                        label: "查看模块详情",
                        action: "open_feature",
                        featureId,
                      },
                      {
                        label: "继续线程追问",
                        action: "continue_thread",
                        featureId,
                      },
                      {
                        label: "基于上下文再执行",
                        action: "rerun_from_artifact",
                        featureId,
                        disabled: !rerunAvailability.canRerun,
                        title: rerunAvailability.reason ?? undefined,
                      },
                    ],
                  })
                : null}
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
                          <button
                            type="button"
                            onClick={() => void openAuthorizedAsset(url)}
                            className="rounded-full bg-[var(--accent-primary)]/10 px-2.5 py-1 text-[11px] font-medium text-[var(--accent-primary)]"
                          >
                            打开文件
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              void openAuthorizedAsset(downloadUrl || url)
                            }
                            className="rounded-full border border-[var(--border-default)] bg-[var(--bg-surface)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-primary)]"
                          >
                            下载
                          </button>
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
          const actions: CardActionItem[] = items.map((item, itemIndex) => {
            const label =
              typeof item?.label === "string"
                ? item.label
                : `建议 ${itemIndex + 1}`;
            const action = (() => {
              const rawAction = typeof item?.action === "string" ? item.action : "";
              if (
                rawAction === "trigger_feature" ||
                rawAction === "continue_thread" ||
                rawAction === "open_feature" ||
                rawAction === "rerun_from_artifact"
              ) {
                return rawAction;
              }
              return "continue_thread";
            })();
            const featureId =
              typeof item?.feature_id === "string" && item.feature_id.trim()
                ? item.feature_id
                : resolveMessageFeatureId(message);
            const isRerun = action === "rerun_from_artifact";
            const rerunAvailability =
              options?.resolveRerunAvailability?.(featureId) ?? {
                canRerun: false,
                reason: "当前卡片没有可复用的 artifact 执行上下文。",
              };
            const routeParams = sanitizeRouteParamMap(
              item?.params && typeof item.params === "object"
                ? item.params
                : item?.route_params && typeof item.route_params === "object"
                  ? item.route_params
                  : null
            );
            return {
              label,
              action,
              featureId,
              routeParams,
              disabled: isRerun && !rerunAvailability.canRerun,
              title:
                isRerun && !rerunAvailability.canRerun
                  ? rerunAvailability.reason ?? undefined
                  : undefined,
            };
          });
          return (
            <div
              key={`${block.type}-${index}`}
              className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)]/70 px-3 py-3"
            >
              <p className="text-sm font-medium text-[var(--text-primary)]">
                {block.title || "建议下一步"}
              </p>
              {renderCardActions({
                actions,
                onAction: options?.onCardAction,
              })}
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

function WorkspaceThreadMessageBubble({
  message,
  isLast,
  isStreaming,
  workspaceId,
}: WorkspaceThreadMessageBubbleProps) {
  const router = useRouter();
  const workspace = useWorkspaceStore((state) => state.workspace);
  const artifacts = useWorkspaceStore((state) => state.artifacts);
  const getFeatureById = useFeaturesStore((state) => state.getFeatureById);
  const isUser = message.role === "user";
  const reasoningText = extractReasoningBlockText(message);
  const hasReasoning = Boolean(reasoningText);
  const messageFeatureId = useMemo(
    () => resolveMessageFeatureId(message),
    [message]
  );
  const messageOrchestrationParams = useMemo(() => {
    const orchestration = readMessageOrchestration(message);
    return readWorkspaceFeatureOrchestrationParams(orchestration?.params);
  }, [message]);
  const actionContext = useMemo(() => {
    if (!messageFeatureId) {
      return null;
    }
    return resolveWorkspaceFeatureActionContext({
      workspaceId,
      featureId: messageFeatureId,
      feature: getFeatureById(messageFeatureId) ?? null,
      workspace,
      artifacts,
      orchestrationParams: messageOrchestrationParams,
    });
  }, [
    artifacts,
    getFeatureById,
    messageFeatureId,
    messageOrchestrationParams,
    workspace,
    workspaceId,
  ]);
  const resolveTargetActionContext = (targetFeatureId: string) => {
    if (targetFeatureId === messageFeatureId && actionContext) {
      return actionContext;
    }
    return resolveWorkspaceFeatureActionContext({
      workspaceId,
      featureId: targetFeatureId,
      feature: getFeatureById(targetFeatureId) ?? null,
      workspace,
      artifacts,
      orchestrationParams: messageOrchestrationParams,
    });
  };
  const resolveRerunAvailability = (
    targetFeatureId: string | null
  ): RerunAvailability => {
    if (!targetFeatureId) {
      return {
        canRerun: false,
        reason: "当前卡片没有可复用的 artifact 执行上下文。",
      };
    }
    const targetContext = resolveTargetActionContext(targetFeatureId);
    const canRerun = Boolean(
      targetContext.route &&
        targetContext.rerunParams &&
        Object.keys(targetContext.rerunParams).length > 0
    );
    return {
      canRerun,
      reason: canRerun
        ? null
        : targetContext.rerunUnavailableReason ??
          "当前卡片没有可复用的 artifact 执行上下文。",
    };
  };

  const handleCardAction = (
    action: CardActionType,
    featureId: string | null,
    routeParams?: RouteParamMap | null
  ) => {
    const baseThreadRoute = `/workspaces/${workspaceId}/chat`;
    if (action === "continue_thread") {
      router.push(baseThreadRoute);
      return;
    }

    const resolvedFeatureId = featureId || messageFeatureId;
    const resolveFeatureRoute = (
      targetFeatureId: string,
      options?: {
        useRerunParams?: boolean;
        includeContextParams?: boolean;
        routeParams?: RouteParamMap | null;
      }
    ): string | null => {
      const targetContext = resolveTargetActionContext(targetFeatureId);
      const targetFeature = getFeatureById(targetFeatureId);
      const contextParams =
        options?.includeContextParams === false
          ? {}
          : options?.useRerunParams
            ? sanitizeRouteParamMap(targetContext.rerunParams)
            : targetContext.routeParams ?? {};
      return getWorkspaceFeatureThreadRoute(workspaceId, targetFeatureId, {
        ...contextParams,
        ...(options?.routeParams ?? {}),
        ...(targetFeature?.defaultSkillId
          ? { skill: targetFeature.defaultSkillId }
          : {}),
      });
    };

    if (action === "rerun_from_artifact") {
      if (resolvedFeatureId) {
        const rerunAvailability = resolveRerunAvailability(resolvedFeatureId);
        if (rerunAvailability.canRerun) {
          const rerunRoute =
            resolveFeatureRoute(resolvedFeatureId, {
              useRerunParams: true,
              routeParams,
            }) ??
            resolveFeatureRoute(resolvedFeatureId, {
              routeParams,
            });
          if (rerunRoute) {
            router.push(rerunRoute);
            return;
          }
        }
        const fallbackRerunRoute =
          resolveFeatureRoute(resolvedFeatureId, {
            routeParams,
          }) ??
          resolveFeatureRoute(resolvedFeatureId, {
            includeContextParams: false,
            routeParams,
          });
        if (fallbackRerunRoute) {
          router.push(fallbackRerunRoute);
          return;
        }
      }
      router.push(baseThreadRoute);
      return;
    }

    if (action === "open_feature") {
      if (!resolvedFeatureId) {
        router.push(baseThreadRoute);
        return;
      }
      const passiveFeatureRoute =
        resolveFeatureRoute(resolvedFeatureId, {
          routeParams,
        }) ??
        resolveFeatureRoute(resolvedFeatureId, {
          includeContextParams: false,
          routeParams,
        });
      if (passiveFeatureRoute) {
        const [pathname, queryString = ""] = passiveFeatureRoute.split("?");
        const query = new URLSearchParams(queryString);
        query.set("entry", "open");
        router.push(`${pathname}?${query.toString()}`);
        return;
      }
      const query = new URLSearchParams();
      query.set("feature", resolvedFeatureId);
      query.set("entry", "open");
      router.push(`${baseThreadRoute}?${query.toString()}`);
      return;
    }

    if (!resolvedFeatureId) {
      router.push(baseThreadRoute);
      return;
    }

    const featureRoute =
      resolveFeatureRoute(resolvedFeatureId, {
        routeParams,
      }) ??
      resolveFeatureRoute(resolvedFeatureId, {
        includeContextParams: false,
        routeParams,
      });
    router.push(featureRoute ?? baseThreadRoute);
  };

  const showStreaming =
    isLast &&
    !isUser &&
    isStreaming &&
    !message.content &&
    (!message.blocks || message.blocks.length === 0);
  const showStreamingContent = isLast && !isUser && isStreaming && Boolean(message.content);

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
        ) : (
          <div className="space-y-3">
            {renderMessageAttachments(message, isUser)}
            {renderStructuredBlocks(message, {
              isStreaming: isLast && !isUser && isStreaming,
              onCardAction: handleCardAction,
              resolveRerunAvailability,
            })}
            {message.content ? (
              isUser ? (
                <p className="text-sm whitespace-pre-wrap">{message.content}</p>
              ) : showStreamingContent ? (
                <div className="rounded-2xl border border-sky-500/20 bg-[linear-gradient(180deg,rgba(14,165,233,0.08),rgba(255,255,255,0.65))] px-4 py-3">
                  {hasReasoning ? (
                    <div className="mb-2 flex items-center gap-2 text-[11px] font-medium text-sky-700">
                      <div className="h-2 w-2 rounded-full bg-sky-500" />
                      回答通道
                    </div>
                  ) : null}
                  <StreamingText
                    text={message.content}
                    isStreaming={true}
                    className="text-sm"
                    cursorClassName="bg-sky-500"
                  />
                </div>
              ) : (
                <div
                  className={cn(
                    hasReasoning
                      ? "rounded-2xl border border-sky-500/15 bg-[linear-gradient(180deg,rgba(14,165,233,0.06),rgba(255,255,255,0.7))] px-4 py-3"
                      : ""
                  )}
                >
                  {hasReasoning ? (
                    <div className="mb-2 flex items-center gap-2 text-[11px] font-medium text-sky-700">
                      <div className="h-2 w-2 rounded-full bg-sky-500" />
                      最终回答
                    </div>
                  ) : null}
                  <MarkdownRenderer content={message.content} className="text-sm" />
                </div>
              )
            ) : null}
            {!message.content && isLast && !isUser && isStreaming ? (
              <div
                className={cn(
                  "rounded-2xl border px-4 py-3",
                  hasReasoning
                    ? "border-sky-500/20 bg-[linear-gradient(180deg,rgba(14,165,233,0.08),rgba(255,255,255,0.65))]"
                    : "border-[var(--border-default)] bg-[var(--bg-surface)]/60"
                )}
              >
                {hasReasoning ? (
                  <div className="mb-2 flex items-center gap-2 text-[11px] font-medium text-sky-700">
                    <div className="h-2 w-2 rounded-full bg-sky-500" />
                    回答通道
                  </div>
                ) : null}
                <ThinkingIndicator />
              </div>
            ) : null}
            {renderTokenUsageTags(message.metadata, isUser)}
          </div>
        )}
      </div>
    </motion.div>
  );
}

export function WorkspaceThreadMessages({
  workspaceId,
  messages,
  isStreaming,
  isThreadLoading = false,
  workspaceName,
}: WorkspaceThreadMessagesProps) {
  return (
    <AnimatePresence mode="popLayout">
      {isThreadLoading ? (
        <div className="h-full flex items-center justify-center">
          <div className="text-center max-w-md">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-[var(--bg-surface)] flex items-center justify-center border border-[var(--border-default)]">
              <Bot className="w-7 h-7 text-[var(--text-muted)]" />
            </div>
            <h3 className="text-lg font-semibold text-[var(--text-primary)] mb-2">
              正在恢复对话
            </h3>
            <p className="text-sm text-[var(--text-secondary)]">
              正在加载当前 thread 的完整上下文。
            </p>
          </div>
        </div>
      ) : messages.length === 0 ? (
        <div className="h-full flex items-center justify-center">
          <div className="text-center max-w-md">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gradient-to-br from-[var(--accent-primary)] to-[var(--accent-secondary)] flex items-center justify-center">
              <Sparkles className="w-8 h-8 text-white" />
            </div>
            <h3 className="text-lg font-semibold text-[var(--text-primary)] mb-2">
              从当前阶段开始
            </h3>
            <p className="text-sm text-[var(--text-secondary)]">
              先描述你要推进的步骤。问津会结合当前 workspace
              {workspaceName ? `「${workspaceName}」` : ""} 的上下文，安排下一步。
            </p>
          </div>
        </div>
      ) : (
        messages.map((message, index) => (
          <WorkspaceThreadMessageBubble
            key={message.id}
            message={message}
            isLast={index === messages.length - 1}
            isStreaming={isStreaming}
            workspaceId={workspaceId}
          />
        ))
      )}
    </AnimatePresence>
  );
}
