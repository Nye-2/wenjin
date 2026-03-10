"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, User, Bot, Sparkles } from "lucide-react";
import { useChatStore, Message } from "@/stores/chat";
import { useWorkspaceStore } from "@/stores/workspace";
import { SkillSelector } from "./SkillSelector";
import { StreamingText, ThinkingIndicator } from "@/components/glass";
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
            ? "bg-academic-primary text-white"
            : "bg-gradient-to-br from-academic-primary to-academic-secondary text-white"
        )}
      >
        {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
      </div>

      {/* Message content */}
      <div
        className={cn(
          "max-w-[80%] rounded-2xl px-4 py-3",
          isUser
            ? "bg-academic-primary text-white rounded-tr-md"
            : "bg-white/70 dark:bg-slate-800/70 backdrop-blur-sm text-slate-900 dark:text-slate-100 rounded-tl-md border border-white/20"
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
  const { workspace } = useWorkspaceStore();
  const [inputValue, setInputValue] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

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
    await sendMessage(content, currentSkill || undefined);
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
      <div className="px-6 py-4 border-b border-[var(--glass-border)] bg-[var(--glass-bg)] backdrop-blur-xl">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-academic-primary" />
              {workspace?.name || "Agent Chat"}
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              AI-powered academic assistant
            </p>
          </div>
          {currentSkill && (
            <span className="px-3 py-1 rounded-full text-xs font-medium bg-academic-primary/10 text-academic-primary">
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
                <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gradient-to-br from-academic-primary to-academic-secondary flex items-center justify-center">
                  <Sparkles className="w-8 h-8 text-white" />
                </div>
                <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-2">
                  Start Your Research Journey
                </h3>
                <p className="text-sm text-slate-500 dark:text-slate-400">
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
      <div className="p-4 border-t border-[var(--glass-border)] bg-[var(--glass-bg)] backdrop-blur-xl">
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
