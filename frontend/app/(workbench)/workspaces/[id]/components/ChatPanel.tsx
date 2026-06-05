"use client";

import { useRef, useEffect, useMemo, useState, memo, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { SendHorizontal } from "lucide-react";
import type { WorkspaceCapability } from "@/lib/api";
import {
  buildContinueThreadBlockAction,
  type ContinueThreadBlockAction,
} from "@/lib/block-actions";
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

function buildBlockIntentForwardingOptions(
  metadata: Record<string, unknown> | undefined,
  blockAction: ContinueThreadBlockAction | undefined,
):
  | {
      metadata: {
        orchestration?: Record<string, unknown>;
        block_action?: ContinueThreadBlockAction;
      };
    }
  | undefined {
  const payload: {
    orchestration?: Record<string, unknown>;
    block_action?: {
      action: "continue_thread";
      intent: string;
      source_block_kind: "question_card" | "result_card";
    };
  } = {};
  if (metadata && typeof metadata === "object") {
    const orchestration = metadata.orchestration;
    if (orchestration && typeof orchestration === "object") {
      payload.orchestration = { ...(orchestration as Record<string, unknown>) };
    }
  }
  if (blockAction) {
    payload.block_action = blockAction;
  }
  if (!payload.orchestration && !payload.block_action) {
    return undefined;
  }
  return {
    metadata: payload,
  };
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
  const [historyHydration, setHistoryHydration] = useState<{
    workspaceId: string;
    hydrated: boolean;
  }>(() => ({
    workspaceId,
    hydrated: false,
  }));
  const historyHydrated =
    historyHydration.workspaceId === workspaceId && historyHydration.hydrated;
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isComposingRef = useRef(false);
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
  const inputPlaceholder = useMemo(() => {
    if (isSending) {
      return "等待回复中...";
    }
    const lastAssistantMessage = [...messages]
      .reverse()
      .find((message) => message.role === "assistant");
    if (lastAssistantMessage?.blocks.some((block) => block.kind === "question_card")) {
      return "直接说想法...";
    }
    if (lastAssistantMessage?.blocks.some((block) => block.kind === "result_card")) {
      return "或对结果反馈、推翻、迭代";
    }
    return "输入消息... Shift+Enter 换行";
  }, [isSending, messages]);

  const showThinking = isSending && messages.length > 0 && messages[messages.length - 1].role === "user";
  const handleBlockIntent = useCallback(
    (
      intent: string,
      options?: {
        metadata: {
          orchestration?: Record<string, unknown>;
          block_action?: ContinueThreadBlockAction;
        };
      },
    ) => {
      if (!intent.trim() || isSending) {
        return;
      }
      void sendMessage(workspaceId, intent.trim(), [], options);
    },
    [isSending, sendMessage, workspaceId],
  );

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
    if (store.messages.length === 0) {
      void store.loadHistory(workspaceId).then((tid) => {
        if (cancelled) return;
        if (tid) setThreadId(tid);
        setHistoryHydration({ workspaceId, hydrated: true });
      });
      return () => {
        cancelled = true;
      };
    }
    void Promise.resolve().then(() => {
      if (!cancelled) {
        setHistoryHydration({ workspaceId, hydrated: true });
      }
    });
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
    const nativeEvent = e.nativeEvent as KeyboardEvent;
    if (
      isComposingRef.current ||
      nativeEvent.isComposing ||
      nativeEvent.keyCode === 229
    ) {
      return;
    }
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
        background: "var(--wjn-surface)",
        display: "flex",
        flexDirection: "column",
        fontFamily: "var(--wjn-font-sans)",
      }}
    >
      {/* Message list / idle state */}
      <div
        ref={scrollRef}
        style={{ flex: 1, overflowY: "auto", padding: "18px 14px" }}
      >
        {messages.length === 0 && workspaceName && typeConfig ? (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
              padding: "0 22px",
              animation: "wjn-panel-in 400ms var(--wjn-ease-standard)",
            }}
          >
            <div
              className="wjn-hairline-panel"
              style={{
                width: 46,
                height: 46,
                borderRadius: 12,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 24,
                marginBottom: 14,
              }}
            >
              {typeConfig.icon}
            </div>
            <div
              style={{
                fontSize: 18,
                fontWeight: 700,
                color: "var(--wjn-text)",
                marginBottom: 6,
                fontFamily: "var(--wjn-font-sans)",
              }}
            >
              {workspaceName}
            </div>
            <div
              style={{
                fontSize: 13,
                color: "var(--wjn-text-muted)",
                fontFamily: "var(--wjn-font-sans)",
                textAlign: "center",
                lineHeight: 1.6,
              }}
            >
              {typeConfig.chatSubtitle}
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <MessageRow
              key={msg.id}
              message={msg}
              workspaceId={workspaceId}
              onIntent={handleBlockIntent}
              intentDisabled={isSending}
            />
          ))
        )}
        {showThinking && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "4px 4px",
              color: "var(--wjn-text-muted)",
              fontSize: 13,
              fontFamily: "var(--wjn-font-sans)",
            }}
          >
            <span style={{ color: "var(--wjn-accent)", animation: "wjn-pulse-soft 1.5s infinite" }}>●</span>
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
                  borderRadius: "var(--wjn-radius)",
                  border: "1px solid var(--wjn-line)",
                  background: "#fff",
                  color: "var(--wjn-text-secondary)",
                  fontSize: 12.5,
                  fontWeight: 600,
                  cursor: isSending ? "not-allowed" : "pointer",
                  fontFamily: "var(--wjn-font-sans)",
                  transition: "background 150ms, border-color 150ms",
                  opacity: isSending ? 0.5 : 1,
                }}
                onMouseEnter={(e) => {
                  if (!isSending) {
                    e.currentTarget.style.background =
                      "var(--wjn-accent-soft)";
                    e.currentTarget.style.borderColor =
                      "var(--wjn-accent-line)";
                  }
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "#fff";
                  e.currentTarget.style.borderColor = "var(--wjn-line)";
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
          borderTop: "1px solid var(--wjn-line)",
          padding: "12px",
          background: "linear-gradient(180deg, rgba(255,255,255,0.8), rgba(249,250,252,0.96))",
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
                  borderRadius: "var(--wjn-radius)",
                  background: "var(--wjn-accent-soft)",
                  color: "var(--wjn-accent-strong)",
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
                    color: "var(--wjn-text-muted)",
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
            placeholder={inputPlaceholder}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onCompositionStart={() => {
              isComposingRef.current = true;
            }}
            onCompositionEnd={() => {
              isComposingRef.current = false;
            }}
            onKeyDown={handleKeyDown}
            rows={1}
            style={{
              flex: 1,
              padding: "8px 12px",
              borderRadius: "var(--wjn-radius)",
              border: "1px solid var(--wjn-line)",
              background: "#fff",
              fontSize: 13.5,
              outline: "none",
              fontFamily: "var(--wjn-font-sans)",
              color: "var(--wjn-text)",
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
              width: 38,
              height: 38,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              borderRadius: "var(--wjn-radius)",
              border: "none",
              background:
                isSending || !inputValue.trim()
                  ? "var(--wjn-line-strong)"
                  : "var(--wjn-accent)",
              color: "#FFFFFF",
              fontSize: 13,
              cursor:
                isSending || !inputValue.trim() ? "not-allowed" : "pointer",
              opacity: isSending ? 0.6 : 1,
            }}
            aria-label="发送"
          >
            {isSending ? "..." : <SendHorizontal size={16} aria-hidden="true" />}
          </button>
        </div>
      </div>
    </div>
  );
}

const MessageRow = memo(function MessageRow({
  message,
  workspaceId,
  onIntent,
  intentDisabled,
}: {
  message: Message;
  workspaceId: string;
  onIntent?: (
    intent: string,
    options?: {
      metadata: {
        orchestration?: Record<string, unknown>;
        block_action?: ContinueThreadBlockAction;
      };
    },
  ) => void;
  intentDisabled?: boolean;
}) {
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
          borderRadius: isUser ? "var(--wjn-radius-lg)" : 0,
          background: isUser ? "var(--wjn-surface-subtle)" : "transparent",
          fontSize: 13.5,
          lineHeight: 1.55,
          color: "var(--wjn-text)",
          border: isUser ? "1px solid var(--wjn-line)" : "none",
        }}
      >
        {message.blocks.map((block, i) => (
          <MessageBlock
            key={i}
            block={block}
            workspaceId={workspaceId}
            onIntent={
              onIntent
                ? (intent, sourceBlockKind) =>
                    onIntent(
                      intent,
                      buildBlockIntentForwardingOptions(
                        message.metadata,
                        buildContinueThreadBlockAction(intent, sourceBlockKind),
                      ),
                    )
                : undefined
            }
            intentDisabled={intentDisabled}
          />
        ))}
      </div>
    </div>
  );
});
