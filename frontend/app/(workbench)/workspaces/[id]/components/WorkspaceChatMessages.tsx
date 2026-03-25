"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Bot, Sparkles, User } from "lucide-react";
import { StreamingText, ThinkingIndicator } from "@/components/glass";
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
