"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, User, Bot, Sparkles, History, Plus, Trash2 } from "lucide-react";
import { executeWorkspaceFeature } from "@/lib/api";
import { useModelSelection } from "@/hooks/useModelSelection";
import { useChatStore, Message } from "@/stores/chat";
import { useWorkspaceStore } from "@/stores/workspace";
import { useTaskStore } from "@/stores/task";
import { useFeaturesStore } from "@/stores/features";
import { SkillSelector } from "./SkillSelector";
import { StreamingText, ThinkingIndicator } from "@/components/glass";
import { AgentStatusBar, QuickActions } from "@/components/workspace";
import { cn } from "@/lib/utils";

interface MessageBubbleProps {
  message: Message;
  isLast: boolean;
}

function MessageBubble({ message, isLast }: MessageBubbleProps) {
  const { isStreaming } = useChatStore();
  const isUser = message.role === "user";
  const showStreaming = isLast && !isUser && isStreaming && !message.content;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={cn(
        "flex gap-3",
        isUser ? "flex-row-reverse" : "flex-row"
      )}
    >
      {/* Avatar */}
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

      {/* Message content */}
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
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        )}
      </div>
    </motion.div>
  );
}

interface ChatPanelProps {
  workspaceId: string;
}

export function ChatPanel({ workspaceId }: ChatPanelProps) {
  const {
    messages,
    isStreaming,
    isThreadsLoading,
    currentSkill,
    threadId,
    threads,
    deleteThread,
    loadThread,
    sendMessage,
    startNewThread,
    setCurrentSkill,
  } = useChatStore();
  const { workspace } = useWorkspaceStore();
  const {
    startTask,
    isExecuting,
  } = useTaskStore();
  const { getFeatureById } = useFeaturesStore();
  const [inputValue, setInputValue] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [deletingThreadId, setDeletingThreadId] = useState<string | null>(null);
  const {
    models: availableModels,
    selectedModel,
    setSelectedModel,
  } = useModelSelection({
    purpose: "chat",
    persistenceKey: `workspace:${workspaceId}:model:chat`,
  });
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // 处理快捷指令点击
  const handleQuickAction = async (featureId: string) => {
    if (isExecuting) return;

    const feature = getFeatureById(featureId);
    if (!feature) return;

    setActionError(null);

    try {
      // 根据 feature 类型构造默认参数，保证快捷动作命中正确后端 action。
      const params: Record<string, unknown> = {};
      if (feature.id === "deep_research") {
        // 暂时使用 workspace 描述或名称作为研究主题，后续可由专用页面接管
        const topic =
          workspace?.description?.trim() ||
          workspace?.name?.trim() ||
          "";
        if (topic) {
          params.query = topic;
          params.topic = topic;
        }
      }
      if (feature.id === "thesis_writing") {
        // Chat 快捷动作默认走 Step 1：大纲生成，避免落入无参写作动作。
        const paperTitle =
          workspace?.name?.trim() ||
          workspace?.description?.trim() ||
          "未命名论文";
        params.action = "generate_outline";
        params.paper_title = paperTitle;
        params.target_words = 20000;
      }
      if (selectedModel) {
        params.model_id = selectedModel;
      }

      const execution = await executeWorkspaceFeature(
        workspaceId,
        featureId,
        params
      );

      // 文献不足等 warning 场景：后端不会创建 task，前端不应进入轮询
      if (execution.status === "warning" && !execution.task_id) {
        const detail = execution.detail as
          | { current?: number; recommended?: number }
          | undefined;
        if (execution.warning === "literature_insufficient" && detail) {
          setActionError(
            `文献数量不足（当前 ${detail.current ?? 0} / 推荐 ${detail.recommended ?? 0}），请先在「文献管理」中补充文献。`
          );
        } else {
          setActionError(execution.message || "该功能暂时无法执行");
        }
        return;
      }

      if (!execution.task_id) {
        setActionError("任务创建失败，请稍后重试");
        return;
      }

      startTask({
        taskId: execution.task_id,
        featureId: feature.id,
        agent: feature.agent,
        agentLabel: feature.agentLabel,
        stages: feature.stages,
        initialThinking: execution.message,
      });
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to execute feature");
    }
  };

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 200)}px`;
    }
  }, [inputValue]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || isStreaming) return;

    const content = inputValue.trim();
    setInputValue("");
    await sendMessage(content, {
      workspaceId,
      skill: currentSkill,
      model: selectedModel || undefined,
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleSelectThread = async (selectedThreadId: string) => {
    setIsHistoryOpen(false);
    await loadThread(selectedThreadId);
  };

  const handleStartNewThread = () => {
    setIsHistoryOpen(false);
    setActionError(null);
    startNewThread();
  };

  const handleDeleteThread = async (selectedThreadId: string) => {
    setActionError(null);
    setDeletingThreadId(selectedThreadId);
    try {
      await deleteThread(selectedThreadId, workspaceId);
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "Failed to delete chat thread"
      );
    } finally {
      setDeletingThreadId(null);
    }
  };

  return (
    <div className="flex-1 h-full flex flex-col">
      {/* Header */}
      <div className="px-6 py-4 border-b border-[var(--border-default)] bg-[var(--bg-elevated)] backdrop-blur-xl">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)] flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-[var(--accent-primary)]" />
              {workspace?.name || "Agent Chat"}
            </h2>
            <p className="text-xs text-[var(--text-muted)]">
              AI-powered academic assistant
            </p>
          </div>
          <div className="flex items-center gap-2">
            {currentSkill && (
              <span className="px-3 py-1 rounded-full text-xs font-medium bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
                {currentSkill.replace("-", " ")}
              </span>
            )}
            <button
              type="button"
              onClick={handleStartNewThread}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--bg-muted)]"
            >
              <Plus className="h-3.5 w-3.5" />
              新会话
            </button>
            <button
              type="button"
              onClick={() => setIsHistoryOpen((open) => !open)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--bg-muted)]"
            >
              <History className="h-3.5 w-3.5" />
              历史会话
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
                  正在加载历史会话...
                </p>
              ) : threads.length === 0 ? (
                <p className="px-2 py-3 text-xs text-[var(--text-muted)]">
                  当前工作区还没有历史会话。
                </p>
              ) : (
                <div className="space-y-1">
                  {threads.map((thread) => {
                    const isActive = thread.id === threadId;
                    const label =
                      thread.title?.trim() ||
                      thread.last_message_preview ||
                      `${thread.skill ? thread.skill.replace("-", " ") : "未命名会话"}`;
                    const secondaryText =
                      thread.title?.trim() && thread.last_message_preview
                        ? thread.last_message_preview
                        : null;
                    const metadataText =
                      `${thread.skill ? thread.skill.replace("-", " ") : "未设置能力"} · ${
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
                          onClick={() => void handleSelectThread(thread.id)}
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
                            void handleDeleteThread(thread.id);
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

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        <AnimatePresence mode="popLayout">
          {messages.length === 0 ? (
            <div className="h-full flex items-center justify-center">
              <div className="text-center max-w-md">
                <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gradient-to-br from-[var(--accent-primary)] to-[var(--accent-secondary)] flex items-center justify-center">
                  <Sparkles className="w-8 h-8 text-white" />
                </div>
                <h3 className="text-lg font-semibold text-[var(--text-primary)] mb-2">
                  Start Your Research Journey
                </h3>
                <p className="text-sm text-[var(--text-secondary)]">
                  Select a skill below and ask me anything about your research.
                  I can help with literature reviews, paper writing, experiment
                  design, and more.
                </p>
              </div>
            </div>
          ) : (
            messages.map((message, index) => (
              <MessageBubble
                key={message.id}
                message={message}
                isLast={index === messages.length - 1}
              />
            ))
          )}
        </AnimatePresence>
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 border-t border-[var(--border-default)] bg-[var(--bg-elevated)] backdrop-blur-xl">
        {/* Agent Status Bar */}
        <div className="mb-3">
          <AgentStatusBar />
        </div>

        {actionError && (
          <div className="mb-3 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-600 dark:text-red-400">
            {actionError}
          </div>
        )}

        {/* Quick Actions */}
        {!isExecuting && (
          <div className="mb-3 overflow-x-auto pb-2">
            <QuickActions onAction={handleQuickAction} />
          </div>
        )}

        {/* Skill Selector */}
        <div className="mb-3 overflow-x-auto pb-2">
          <SkillSelector
            selectedSkill={currentSkill}
            onSelect={setCurrentSkill}
          />
        </div>

        <div className="mb-3 flex items-center gap-3">
          <label
            htmlFor="chat-model-select"
            className="text-xs font-medium text-[var(--text-muted)]"
          >
            Chat Model
          </label>
          <select
            id="chat-model-select"
            value={selectedModel ?? ""}
            onChange={(event) => setSelectedModel(event.target.value || null)}
            disabled={availableModels.length === 0 || isStreaming}
            className="min-w-[220px] rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent-primary)] focus:outline-none"
          >
            {availableModels.length === 0 ? (
              <option value="">No models available</option>
            ) : (
              availableModels.map((model) => (
                <option key={model.name} value={model.name}>
                  {model.display_name}
                </option>
              ))
            )}
          </select>
        </div>

        {/* Input Form */}
        <form onSubmit={handleSubmit} className="flex gap-3">
          <div className="flex-1 relative">
            <textarea
              ref={inputRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about your research..."
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
            type="submit"
            disabled={!inputValue.trim() || isStreaming}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className={cn(
              "px-4 py-3 rounded-xl flex items-center justify-center",
              "bg-gradient-to-r from-[var(--accent-primary)] to-[#1D4ED8] text-white",
              "hover:shadow-lg transition-shadow",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
          >
            <Send className="w-5 h-5" />
          </motion.button>
        </form>
      </div>
    </div>
  );
}
