"use client";

import { useRef, useEffect, useMemo, useState, memo } from "react";
import { useSearchParams } from "next/navigation";
import type { WorkspaceCapability } from "@/lib/api";
import { useChatStoreV2, type Message } from "@/stores/chat-store";
import { MessageBlock } from "./MessageBlock";
import { FileAttachButton } from "./FileAttachButton";
import type { WorkspaceTypeConfig } from "@/lib/workspace-suggestions";
import {
  buildWorkspaceThreadEntryMetadata,
  buildWorkspaceThreadEntryPrompt,
  parseWorkspaceThreadEntrySeed,
  resolveWorkspaceThreadEntrySkill,
} from "@/lib/workspace-thread-entry";

interface ChatPanelProps {
  workspaceId: string;
  workspaceName?: string;
  typeConfig?: WorkspaceTypeConfig;
  features?: WorkspaceCapability[];
  className?: string;
  "data-testid"?: string;
}

export function ChatPanel({
  workspaceId,
  workspaceName,
  typeConfig,
  features,
  className,
  "data-testid": testId,
}: ChatPanelProps) {
  const searchParams = useSearchParams();
  const messages = useChatStoreV2((s) => s.messages);
  const isSending = useChatStoreV2((s) => s.isSending);
  const sendMessage = useChatStoreV2((s) => s.sendMessage);
  const [inputValue, setInputValue] = useState("");
  const [attachments, setAttachments] = useState<Array<{ name: string; path: string }>>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [historyHydrated, setHistoryHydrated] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const autoLaunchedSeedRef = useRef<string | null>(null);
  const entrySeed = useMemo(
    () => parseWorkspaceThreadEntrySeed(searchParams),
    [searchParams],
  );
  const entrySeedSignature = useMemo(() => {
    if (!entrySeed) {
      return null;
    }
    return JSON.stringify({
      workspaceId,
      featureId: entrySeed.featureId,
      skillId: entrySeed.skillId,
      params: entrySeed.params,
    });
  }, [entrySeed, workspaceId]);
  const entryFeature = useMemo(() => {
    if (!entrySeed) {
      return null;
    }
    return features?.find((candidate) => candidate.id === entrySeed.featureId) ?? null;
  }, [entrySeed, features]);

  const showThinking = isSending && messages.length > 0 && messages[messages.length - 1].role === "user";

  // Auto-scroll to bottom on new messages or thinking state change
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, showThinking]);

  // Auto-resize textarea based on content
  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 120) + "px";
    }
  }, [inputValue]);

  // Load message history on mount
  useEffect(() => {
    const store = useChatStoreV2.getState();
    let cancelled = false;
    setHistoryHydrated(false);
    if (store.messages.length === 0) {
      void store.loadHistory(workspaceId).then((tid) => {
        if (cancelled) return;
        if (tid) setThreadId(tid);
        setHistoryHydrated(true);
      });
      return () => {
        cancelled = true;
      };
    }
    setHistoryHydrated(true);
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  useEffect(() => {
    if (!historyHydrated || !entrySeed || isSending || messages.length > 0) {
      return;
    }

    const entryMode =
      typeof entrySeed.params.entry === "string"
        ? entrySeed.params.entry.trim().toLowerCase()
        : "";
    if (entryMode === "resume") {
      return;
    }

    if (!entrySeedSignature || autoLaunchedSeedRef.current === entrySeedSignature) {
      return;
    }

    autoLaunchedSeedRef.current = entrySeedSignature;
    void sendMessage(
      workspaceId,
      buildWorkspaceThreadEntryPrompt({
        seed: entrySeed,
        feature: entryFeature,
      }),
      [],
      {
        skill: resolveWorkspaceThreadEntrySkill({ seed: entrySeed }),
        metadata: buildWorkspaceThreadEntryMetadata({ seed: entrySeed }),
      },
    );
  }, [
    entryFeature,
    entrySeed,
    entrySeedSignature,
    historyHydrated,
    isSending,
    messages.length,
    sendMessage,
    workspaceId,
  ]);

  function handleSubmit() {
    const trimmed = inputValue.trim();
    if (!trimmed || isSending) return;
    setInputValue("");
    const currentAttachments = [...attachments];
    setAttachments([]);

    const entryMode =
      typeof entrySeed?.params.entry === "string"
        ? entrySeed.params.entry.trim().toLowerCase()
        : "";
    const shouldForwardResumeSeed =
      entryMode === "resume" &&
      !!entrySeed &&
      !!entrySeedSignature &&
      autoLaunchedSeedRef.current !== entrySeedSignature;

    if (shouldForwardResumeSeed && entrySeedSignature) {
      autoLaunchedSeedRef.current = entrySeedSignature;
    }

    void sendMessage(
      workspaceId,
      trimmed,
      currentAttachments,
      shouldForwardResumeSeed && entrySeed
        ? {
            skill: resolveWorkspaceThreadEntrySkill({ seed: entrySeed }),
            metadata: buildWorkspaceThreadEntryMetadata({ seed: entrySeed }),
          }
        : undefined,
    );
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div
      data-testid={testId}
      className={className}
      style={{
        background: "var(--v2-surface-white)",
        display: "flex",
        flexDirection: "column",
        fontFamily: "var(--v2-font-sans)",
      }}
    >
      {/* Message list / idle state */}
      <div
        ref={scrollRef}
        style={{ flex: 1, overflowY: "auto", padding: "16px 12px" }}
      >
        {messages.length === 0 && workspaceName && typeConfig ? (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
              padding: "0 20px",
              animation: "v2-glass-in 400ms var(--v2-ease-standard)",
            }}
          >
            <div style={{ fontSize: 36, marginBottom: 12 }}>{typeConfig.icon}</div>
            <div
              style={{
                fontSize: 18,
                fontWeight: 600,
                color: "var(--v2-text-primary)",
                marginBottom: 6,
                fontFamily: "var(--v2-font-sans)",
              }}
            >
              {workspaceName}
            </div>
            <div
              style={{
                fontSize: 13,
                color: "var(--v2-text-tertiary)",
                fontFamily: "var(--v2-font-sans)",
              }}
            >
              {typeConfig.chatSubtitle}
            </div>
          </div>
        ) : (
          messages.map((msg) => <MessageRow key={msg.id} message={msg} />)
        )}
        {showThinking && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "4px 4px",
              color: "var(--v2-text-tertiary)",
              fontSize: 13,
              fontFamily: "var(--v2-font-sans)",
            }}
          >
            <span style={{ animation: "v2-pulse-soft 1.5s infinite" }}>●</span>
            思考中...
          </div>
        )}
      </div>

      {/* Suggestion pills — shown only before first message */}
      {messages.length === 0 &&
        typeConfig &&
        typeConfig.suggestions.length > 0 && (
          <div
            style={{
              padding: "0 12px 8px",
              display: "flex",
              flexWrap: "wrap",
              gap: 6,
            }}
          >
            {typeConfig.suggestions.map((text) => (
              <button
                key={text}
                onClick={() => void sendMessage(workspaceId, text)}
                disabled={isSending}
                style={{
                  padding: "6px 14px",
                  borderRadius: "var(--v2-radius-pill)",
                  border: "1px solid var(--v2-border-default)",
                  background: "var(--v2-accent-purple-100)",
                  color: "var(--v2-accent-purple-700)",
                  fontSize: 12.5,
                  fontWeight: 500,
                  cursor: isSending ? "not-allowed" : "pointer",
                  fontFamily: "var(--v2-font-sans)",
                  transition: "background 150ms, border-color 150ms",
                  opacity: isSending ? 0.5 : 1,
                }}
                onMouseEnter={(e) => {
                  if (!isSending) {
                    e.currentTarget.style.background =
                      "var(--v2-accent-purple-300)";
                    e.currentTarget.style.borderColor =
                      "var(--v2-accent-purple-300)";
                  }
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "var(--v2-accent-purple-100)";
                  e.currentTarget.style.borderColor = "var(--v2-border-default)";
                }}
              >
                {text}
              </button>
            ))}
          </div>
        )}

      {/* Input area */}
      <div
        style={{
          borderTop: "1px solid var(--v2-border-soft)",
          padding: "12px",
        }}
      >
        {/* Attachment chips */}
        {attachments.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 6 }}>
            {attachments.map((a, i) => (
              <span
                key={i}
                style={{
                  fontSize: 11,
                  padding: "2px 8px",
                  borderRadius: "var(--v2-radius-pill)",
                  background: "var(--v2-accent-purple-100)",
                  color: "var(--v2-accent-purple-700)",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                }}
              >
                {a.name}
                <button
                  type="button"
                  onClick={() => setAttachments((prev) => prev.filter((_, j) => j !== i))}
                  style={{
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    color: "var(--v2-text-tertiary)",
                    fontSize: 13,
                    padding: 0,
                    lineHeight: 1,
                  }}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}
        <div
          style={{
            display: "flex",
            gap: 8,
            alignItems: "center",
          }}
        >
          <FileAttachButton
            threadId={threadId}
            workspaceId={workspaceId}
            onAttached={(files) => setAttachments((prev) => [...prev, ...files])}
            disabled={isSending}
          />
          <textarea
            ref={textareaRef}
            placeholder={isSending ? "等待回复中..." : "输入消息... Shift+Enter 换行"}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            style={{
              flex: 1,
              padding: "8px 12px",
              borderRadius: "var(--v2-radius-md)",
              border: "1px solid var(--v2-border-default)",
              background: "var(--v2-surface-soft)",
              fontSize: 13.5,
              outline: "none",
              fontFamily: "var(--v2-font-sans)",
              color: "var(--v2-text-primary)",
              opacity: isSending ? 0.6 : 1,
              resize: "none",
              minHeight: 38,
              maxHeight: 120,
              lineHeight: "1.4",
            }}
          />
          <button
            onClick={handleSubmit}
            disabled={isSending || !inputValue.trim()}
            data-testid="chat-send"
            style={{
              padding: "8px 16px",
              borderRadius: "var(--v2-radius-md)",
              border: "none",
              background:
                isSending || !inputValue.trim()
                  ? "var(--v2-border-default)"
                  : "var(--v2-accent-purple-700)",
              color: "#FFFFFF",
              fontSize: 13,
              fontWeight: 500,
              cursor:
                isSending || !inputValue.trim() ? "not-allowed" : "pointer",
              fontFamily: "var(--v2-font-sans)",
              opacity: isSending ? 0.6 : 1,
            }}
          >
            {isSending ? "..." : "发送"}
          </button>
        </div>
      </div>
    </div>
  );
}

const MessageRow = memo(function MessageRow({ message }: { message: Message }) {
  const isUser = message.role === "user";
  return (
    <div
      style={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        marginBottom: 12,
      }}
    >
      <div
        style={{
          maxWidth: "85%",
          padding: isUser ? "10px 14px" : "0 4px",
          borderRadius: isUser ? 14 : 0,
          background: isUser ? "var(--v2-surface-card)" : "transparent",
          fontSize: 13.5,
          lineHeight: 1.55,
          color: "var(--v2-text-primary)",
        }}
      >
        {message.blocks.map((block, i) => (
          <MessageBlock key={i} block={block} />
        ))}
      </div>
    </div>
  );
});
