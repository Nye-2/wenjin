"use client";

import { useRef, useEffect, useMemo, useState, memo, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { SendHorizontal } from "lucide-react";
import {
  listModels,
  type Model,
  type ReasoningEffort,
  type WorkspaceCapability,
} from "@/lib/api";
import {
  buildContinueThreadBlockAction,
  type ContinueThreadBlockAction,
} from "@/lib/block-actions";
import {
  useChatStoreV2,
  type Message,
  type SendMessageOptions,
} from "@/stores/chat-store";
import { useExecutionStore } from "@/stores/execution-store";
import { useRunUiStore } from "@/stores/run-ui-store";
import { useWorkbenchLayoutStore } from "@/stores/workbench-layout-store";
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

function withMissionRunContext(
  options: SendMessageOptions | undefined,
  executionId: string | null | undefined,
): SendMessageOptions | undefined {
  const normalizedExecutionId =
    typeof executionId === "string" ? executionId.trim() : "";
  if (!normalizedExecutionId) {
    return options;
  }

  const nextOptions: SendMessageOptions = { ...(options ?? {}) };
  const metadata =
    nextOptions.metadata && typeof nextOptions.metadata === "object"
      ? { ...(nextOptions.metadata as Record<string, unknown>) }
      : {};
  const currentOrchestration =
    metadata.orchestration && typeof metadata.orchestration === "object"
      ? { ...(metadata.orchestration as Record<string, unknown>) }
      : {};

  if (
    typeof currentOrchestration.execution_id === "string" &&
    currentOrchestration.execution_id.trim()
  ) {
    return nextOptions;
  }

  metadata.orchestration = {
    ...currentOrchestration,
    execution_id: normalizedExecutionId,
    source: currentOrchestration.source ?? "mission_console",
  };
  nextOptions.metadata = metadata;
  return nextOptions;
}

function workspaceScopedMissionRunId(
  executionId: string | null | undefined,
  workspaceId: string,
): string | null {
  const normalizedExecutionId =
    typeof executionId === "string" ? executionId.trim() : "";
  if (!normalizedExecutionId) {
    return null;
  }
  const record = useExecutionStore.getState().executions.get(normalizedExecutionId);
  return record?.workspace_id === workspaceId ? normalizedExecutionId : null;
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
  const messages = useChatStoreV2((s) => s.getWorkspaceMessages(workspaceId));
  const isSending = useChatStoreV2((s) => s.isSending);
  const sendMessage = useChatStoreV2((s) => s.sendMessage);
  const setActiveWorkspace = useChatStoreV2((s) => s.setActiveWorkspace);
  const focusedRunId = useRunUiStore((s) => s.focusedRunId);
  const selectedRunId = useWorkbenchLayoutStore((s) => s.selectedRunId);
  const [inputValue, setInputValue] = useState("");
  const [attachments, setAttachments] = useState<Array<{ name: string; path: string }>>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [modelOptions, setModelOptions] = useState<Model[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [modelLoadState, setModelLoadState] = useState<
    "loading" | "ready" | "error"
  >("loading");
  const [reasoningEffort, setReasoningEffort] =
    useState<ReasoningEffort>("medium");
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
  const lastMessageId = messages[messages.length - 1]?.id ?? null;
  const intakeGuidance = typeConfig?.intakeGuidance;
  const suggestionTexts =
    intakeGuidance?.chips?.length ? intakeGuidance.chips : typeConfig?.suggestions ?? [];
  const selectedModelLabel =
    modelOptions.find((model) => model.name === selectedModel)?.display_name ??
    selectedModel;
  const selectedModelOption = modelOptions.find(
    (model) => model.name === selectedModel,
  );
  const selectedModelSupportsReasoning =
    selectedModelOption?.supports_reasoning_effort === true;
  const withSelectedModel = useCallback(
    (options?: SendMessageOptions): SendMessageOptions | undefined => {
      const model = selectedModel.trim();
      const nextOptions: SendMessageOptions = { ...(options ?? {}) };
      if (model) {
        nextOptions.model = model;
      }
      if (selectedModelSupportsReasoning) {
        nextOptions.reasoning_effort = reasoningEffort;
      }
      return Object.keys(nextOptions).length > 0 ? nextOptions : undefined;
    },
    [reasoningEffort, selectedModel, selectedModelSupportsReasoning],
  );
  const handleBlockIntent = useCallback(
    (
      intent: string,
      options?: SendMessageOptions,
    ) => {
      if (!intent.trim() || isSending) {
        return;
      }
      void sendMessage(workspaceId, intent.trim(), [], withSelectedModel(options));
    },
    [isSending, sendMessage, withSelectedModel, workspaceId],
  );

  useEffect(() => {
    let cancelled = false;
    setModelLoadState("loading");
    listModels("chat")
      .then(({ models }) => {
        if (cancelled) return;
        setModelOptions(models);
        setSelectedModel((current) => {
          if (current && models.some((model) => model.name === current)) {
            return current;
          }
          const defaultModel =
            models.find((model) => model.is_default) ?? models[0];
          return defaultModel?.name ?? "";
        });
        setModelLoadState("ready");
      })
      .catch(() => {
        if (cancelled) return;
        setModelOptions([]);
        setSelectedModel("");
        setModelLoadState("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
    let cancelled = false;
    setActiveWorkspace(workspaceId);
    const store = useChatStoreV2.getState();
    if (store.getWorkspaceMessages(workspaceId).length === 0) {
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
  }, [setActiveWorkspace, workspaceId]);

  useEffect(() => {
    if (
      !historyHydrated ||
      !entrySeed ||
      isSending ||
      messages.length > 0 ||
      modelLoadState === "loading"
    ) {
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
      withSelectedModel({
        skill: resolveWorkspaceThreadEntrySkill({ seed: entrySeed }),
        metadata: buildWorkspaceThreadEntryMetadata({ seed: entrySeed }),
      }),
    );
  }, [
    entryFeature,
    entrySeed,
    entrySeedSignature,
    historyHydrated,
    isSending,
    messages.length,
    modelLoadState,
    sendMessage,
    withSelectedModel,
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

    const missionRunId = workspaceScopedMissionRunId(
      focusedRunId || selectedRunId,
      workspaceId,
    );
    void sendMessage(
      workspaceId,
      trimmed,
      currentAttachments,
      withMissionRunContext(
        withSelectedModel(
          shouldForwardResumeSeed && entrySeed
            ? {
                skill: resolveWorkspaceThreadEntrySkill({ seed: entrySeed }),
                metadata: buildWorkspaceThreadEntryMetadata({ seed: entrySeed }),
              }
            : undefined,
        ),
        missionRunId,
      ),
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
            {intakeGuidance ? (
              <div
                style={{
                  width: "min(100%, 340px)",
                  marginTop: 18,
                  padding: 14,
                  border: "1px solid var(--wjn-line)",
                  borderRadius: "var(--wjn-radius-lg)",
                  background: "var(--wjn-surface)",
                  textAlign: "left",
                }}
              >
                <div
                  style={{
                    fontSize: 12,
                    fontWeight: 700,
                    color: "var(--wjn-text)",
                    marginBottom: 8,
                    fontFamily: "var(--wjn-font-sans)",
                  }}
                >
                  先准备这些信息
                </div>
                <ul
                  style={{
                    margin: 0,
                    padding: "0 0 0 18px",
                    color: "var(--wjn-text-secondary)",
                    fontSize: 12.5,
                    lineHeight: 1.7,
                    fontFamily: "var(--wjn-font-sans)",
                  }}
                >
                  {intakeGuidance.checklist.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : (
          messages.map((msg) => (
            <MessageRow
              key={msg.id}
              message={msg}
              workspaceId={workspaceId}
              onIntent={handleBlockIntent}
              intentDisabled={isSending}
              pending={
                isSending &&
                msg.role === "assistant" &&
                msg.id === lastMessageId &&
                msg.blocks.length === 0
              }
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
        suggestionTexts.length > 0 && (
          <div
            style={{
              padding: "0 12px 8px",
              display: "flex",
              flexWrap: "wrap",
              gap: 6,
            }}
          >
            {suggestionTexts.map((text) => (
              <button
                key={text}
                onClick={() =>
                  void sendMessage(
                    workspaceId,
                    text,
                    [],
                    withSelectedModel(),
                  )
                }
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
          background: "var(--wjn-bg-rail)",
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
          <label
            style={{
              display: "inline-flex",
              alignItems: "center",
              minWidth: 112,
              maxWidth: 168,
              height: 38,
              borderRadius: "var(--wjn-radius)",
              border: "1px solid var(--wjn-line)",
              background: "#fff",
              color: "var(--wjn-text-secondary)",
              position: "relative",
              overflow: "hidden",
            }}
            title={
              modelLoadState === "error"
                ? "模型目录加载失败"
                : selectedModelLabel
                  ? `当前模型：${selectedModelLabel}`
                  : modelLoadState === "loading"
                    ? "模型加载中"
                    : "暂无可用模型"
            }
          >
            <span
              style={{
                position: "absolute",
                width: 1,
                height: 1,
                padding: 0,
                margin: -1,
                overflow: "hidden",
                clip: "rect(0, 0, 0, 0)",
                whiteSpace: "nowrap",
                border: 0,
              }}
            >
              选择对话模型
            </span>
            <select
              aria-label="选择对话模型"
              data-testid="chat-model-selector"
              value={selectedModel}
              onChange={(event) => setSelectedModel(event.target.value)}
              disabled={isSending || modelOptions.length === 0}
              style={{
                width: "100%",
                height: "100%",
                border: "none",
                background: "transparent",
                color: "var(--wjn-text-secondary)",
                fontSize: 12,
                fontWeight: 650,
                padding: "0 28px 0 10px",
                outline: "none",
                cursor:
                  isSending || modelOptions.length === 0
                    ? "not-allowed"
                    : "pointer",
                opacity: isSending ? 0.58 : 1,
                fontFamily: "var(--wjn-font-sans)",
              }}
            >
              {modelOptions.length === 0 ? (
                <option value="">
                  {modelLoadState === "error"
                    ? "模型加载失败"
                    : modelLoadState === "loading"
                      ? "模型加载中"
                      : "暂无可用模型"}
                </option>
              ) : (
                modelOptions.map((model) => (
                  <option key={model.name} value={model.name}>
                    {model.display_name}
                  </option>
                ))
              )}
            </select>
          </label>
          {selectedModelSupportsReasoning ? (
            <label
              style={{
                display: "inline-flex",
                alignItems: "center",
                minWidth: 92,
                maxWidth: 116,
                height: 38,
                borderRadius: "var(--wjn-radius)",
                border: "1px solid var(--wjn-line)",
                background: "#fff",
                color: "var(--wjn-text-secondary)",
                position: "relative",
                overflow: "hidden",
              }}
              title="思考强度"
            >
              <span
                style={{
                  position: "absolute",
                  width: 1,
                  height: 1,
                  padding: 0,
                  margin: -1,
                  overflow: "hidden",
                  clip: "rect(0, 0, 0, 0)",
                  whiteSpace: "nowrap",
                  border: 0,
                }}
              >
                选择思考强度
              </span>
              <select
                aria-label="选择思考强度"
                data-testid="chat-reasoning-selector"
                value={reasoningEffort}
                onChange={(event) =>
                  setReasoningEffort(event.target.value as ReasoningEffort)
                }
                disabled={isSending}
                style={{
                  width: "100%",
                  height: "100%",
                  border: "none",
                  background: "transparent",
                  color: "var(--wjn-text-secondary)",
                  fontSize: 12,
                  fontWeight: 650,
                  padding: "0 24px 0 10px",
                  outline: "none",
                  cursor: isSending ? "not-allowed" : "pointer",
                  opacity: isSending ? 0.58 : 1,
                  fontFamily: "var(--wjn-font-sans)",
                }}
              >
                <option value="minimal">极简</option>
                <option value="low">低</option>
                <option value="medium">中</option>
                <option value="high">高</option>
                <option value="xhigh">超高</option>
              </select>
            </label>
          ) : null}
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
  pending,
}: {
  message: Message;
  workspaceId: string;
  onIntent?: (
    intent: string,
    options?: SendMessageOptions,
  ) => void;
  intentDisabled?: boolean;
  pending?: boolean;
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
        {pending ? (
          <PendingAssistantResponse />
        ) : (
          message.blocks.map((block, i) => (
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
          ))
        )}
      </div>
    </div>
  );
});

function PendingAssistantResponse() {
  return (
    <div
      data-testid="chat-pending-response"
      role="status"
      aria-live="polite"
      aria-busy="true"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        minHeight: 30,
        padding: "6px 10px",
        borderRadius: "var(--wjn-radius)",
        border: "1px solid var(--wjn-line)",
        background: "var(--wjn-surface-subtle)",
        color: "var(--wjn-text-secondary)",
        fontSize: 12.5,
        fontWeight: 600,
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 7,
          height: 7,
          borderRadius: "999px",
          background: "var(--wjn-accent)",
          animation: "wjn-pulse-soft 1.2s infinite",
        }}
      />
      模型正在思考
    </div>
  );
}
