"use client";

import { useRef, useEffect, memo } from "react";
import { useChatStoreV2, type Message } from "@/stores/chat-store-v2";
import { MessageBlock } from "./MessageBlock";

interface ChatPanelProps {
  workspaceId: string;
  className?: string;
  "data-testid"?: string;
}

export function ChatPanel({
  workspaceId,
  className,
  "data-testid": testId,
}: ChatPanelProps) {
  const messages = useChatStoreV2((s) => s.messages);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

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
      {/* Message list */}
      <div
        ref={scrollRef}
        style={{ flex: 1, overflowY: "auto", padding: "16px 12px" }}
      >
        {messages.map((msg) => (
          <MessageRow key={msg.id} message={msg} />
        ))}
      </div>

      {/* Input area (placeholder — will be built separately) */}
      <div
        style={{
          borderTop: "1px solid var(--v2-border-soft)",
          padding: "12px",
        }}
      >
        <input
          placeholder="输入消息..."
          disabled
          style={{
            width: "100%",
            padding: "8px 12px",
            borderRadius: "var(--v2-radius-md)",
            border: "1px solid var(--v2-border-default)",
            background: "var(--v2-surface-soft)",
            fontSize: 13.5,
            outline: "none",
            fontFamily: "var(--v2-font-sans)",
          }}
        />
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
