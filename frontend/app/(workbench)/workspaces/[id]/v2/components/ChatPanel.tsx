"use client";

import { useRef, useEffect, useState, memo } from "react";
import { useChatStoreV2, type Message } from "@/stores/chat-store";
import { MessageBlock } from "./MessageBlock";
import type { WorkspaceTypeConfig } from "@/lib/workspace-suggestions";

interface ChatPanelProps {
  workspaceId: string;
  workspaceName?: string;
  typeConfig?: WorkspaceTypeConfig;
  className?: string;
  "data-testid"?: string;
}

export function ChatPanel({
  workspaceId,
  workspaceName,
  typeConfig,
  className,
  "data-testid": testId,
}: ChatPanelProps) {
  const messages = useChatStoreV2((s) => s.messages);
  const isSending = useChatStoreV2((s) => s.isSending);
  const sendMessage = useChatStoreV2((s) => s.sendMessage);
  const [inputValue, setInputValue] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  function handleSubmit() {
    const trimmed = inputValue.trim();
    if (!trimmed || isSending) return;
    setInputValue("");
    void sendMessage(workspaceId, trimmed);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
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
        <div
          style={{
            display: "flex",
            gap: 8,
            alignItems: "center",
          }}
        >
          <input
            placeholder="输入消息..."
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isSending}
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
