"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, User, Bot, Sparkles } from "lucide-react";
import {
  executeWorkspaceFeature,
  getTaskStatus,
} from "@/lib/api";
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
    currentSkill,
    sendMessage,
    setCurrentSkill,
  } = useChatStore();
  const { workspace, fetchArtifacts, fetchPapers, loadWorkspace } = useWorkspaceStore();
  const {
    startTask,
    syncTaskProgress,
    updateTaskThinking,
    completeTask,
    cancelTask,
    failTask,
    currentTask,
    isExecuting,
  } = useTaskStore();
  const { getFeatureById } = useFeaturesStore();
  const [inputValue, setInputValue] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // 处理快捷指令点击
  const handleQuickAction = async (featureId: string) => {
    if (isExecuting) return;

    const feature = getFeatureById(featureId);
    if (!feature) return;

    setActionError(null);

    try {
      const execution = await executeWorkspaceFeature(workspaceId, featureId);
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

  useEffect(() => {
    if (!currentTask) {
      return;
    }

    let cancelled = false;

    const pollTaskStatus = async () => {
      try {
        const status = await getTaskStatus(currentTask.id);
        if (cancelled) return;

        const currentPhase =
          typeof status.metadata?.current_phase === "string"
            ? status.metadata.current_phase
            : undefined;
        syncTaskProgress(status.progress, status.message || currentPhase);

        if (status.status === "success") {
          const refreshTargets = Array.isArray(status.result?.refresh_targets)
            ? status.result.refresh_targets.filter(
                (target): target is string => typeof target === "string"
              )
            : [];

          const refreshJobs: Promise<unknown>[] = [];
          if (refreshTargets.includes("artifacts")) {
            refreshJobs.push(fetchArtifacts(workspaceId));
          }
          if (refreshTargets.includes("papers")) {
            refreshJobs.push(fetchPapers(workspaceId));
          }
          if (refreshTargets.includes("workspace")) {
            refreshJobs.push(loadWorkspace(workspaceId));
          }

          if (refreshJobs.length > 0) {
            await Promise.all(refreshJobs);
          }
          completeTask();
        } else if (status.status === "failed") {
          failTask(status.error || status.message || "Task failed");
        } else if (status.status === "cancelled") {
          cancelTask();
        }
      } catch (error) {
        if (!cancelled) {
          updateTaskThinking(
            error instanceof Error ? error.message : "Task status polling failed"
          );
        }
      }
    };

    void pollTaskStatus();
    const intervalId = window.setInterval(() => {
      void pollTaskStatus();
    }, 2000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [
    cancelTask,
    completeTask,
    currentTask?.id,
    failTask,
    fetchArtifacts,
    fetchPapers,
    loadWorkspace,
    syncTaskProgress,
    updateTaskThinking,
    workspaceId,
  ]);

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
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
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
          {currentSkill && (
            <span className="px-3 py-1 rounded-full text-xs font-medium bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
              {currentSkill.replace("-", " ")}
            </span>
          )}
        </div>
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
