"use client";

import {
  forwardRef,
  memo,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Circle,
  SendHorizontal,
} from "lucide-react";
import {
  getWorkspaceSettings,
  listModels,
  type Model,
  updateWorkspaceSettings,
} from "@/lib/api";
import type { ThreadAttachment } from "@/lib/api/types";
import {
  chooseReasoningEffort,
  REASONING_EFFORT_OPTIONS,
  type ReasoningEffort,
} from "@/lib/reasoning-effort";
import {
  buildContinueThreadBlockAction,
  type ContinueThreadBlockAction,
} from "@/lib/block-actions";
import {
  useChatStoreV2,
  type Message,
  type SendMessageOptions,
} from "@/stores/chat-store";
import { useMissionUiStore } from "@/stores/mission-ui-store";
import { MessageBlock } from "./MessageBlock";
import {
  FileAttachButton,
  type FileAttachButtonHandle,
} from "./FileAttachButton";
import type {
  WorkspaceTypeConfig,
  WorkspaceWelcomeChip,
  WorkspaceWelcomeConfig,
} from "@/lib/workspace-type-config";

interface ChatPanelProps {
  workspaceId: string;
  workspaceName?: string;
  typeConfig?: WorkspaceTypeConfig;
  className?: string;
  onMissionCreated?: (missionId: string) => void;
  "data-testid"?: string;
}

export interface ChatPanelHandle {
  focusComposer(): void;
  openAttachment(): void;
}

function cleanModelLabel(label: string): string {
  return label
    .replace(/\s*\(Default\)\s*/gi, "")
    .replace(/^GPT\s+/i, "GPT-")
    .trim();
}

function compactModelLabel(label: string): string {
  const cleaned = cleanModelLabel(label);
  return cleaned.replace(/^GPT-?/i, "").replace(/-Codex-Spark$/i, " Codex");
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
  missionId: string | null | undefined,
): SendMessageOptions | undefined {
  const normalizedMissionId =
    typeof missionId === "string" ? missionId.trim() : "";
  if (!normalizedMissionId) {
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
    typeof currentOrchestration.mission_id === "string" &&
    currentOrchestration.mission_id.trim()
  ) {
    return nextOptions;
  }

  metadata.orchestration = {
    ...currentOrchestration,
    mission_id: normalizedMissionId,
    source: currentOrchestration.source ?? "mission_console",
  };
  nextOptions.metadata = metadata;
  return nextOptions;
}

export const ChatPanel = forwardRef<ChatPanelHandle, ChatPanelProps>(
  function ChatPanel(
    {
      workspaceId,
      workspaceName,
      typeConfig,
      className,
      onMissionCreated,
      "data-testid": testId,
    },
    ref,
  ) {
  const messages = useChatStoreV2((s) => s.getWorkspaceMessages(workspaceId));
  const isSending = useChatStoreV2((s) => s.isSending);
  const sendMessage = useChatStoreV2((s) => s.sendMessage);
  const setActiveWorkspace = useChatStoreV2((s) => s.setActiveWorkspace);
  const focusedMissionId = useMissionUiStore((state) => state.focusedMissionId);
  const [inputValue, setInputValue] = useState("");
  const [attachments, setAttachments] = useState<ThreadAttachment[]>([]);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const [attachmentUploading, setAttachmentUploading] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [modelOptions, setModelOptions] = useState<Model[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [modelLoadState, setModelLoadState] = useState<
    "loading" | "ready" | "error"
  >("loading");
  const [reasoningEffort, setReasoningEffort] =
    useState<ReasoningEffort>("xhigh");
  const [modelPreferenceError, setModelPreferenceError] = useState<string | null>(null);
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
  const fileAttachRef = useRef<FileAttachButtonHandle>(null);
  const modelMenuRef = useRef<HTMLDivElement>(null);
  const isComposingRef = useRef(false);
  const pendingAttachmentOpenRef = useRef(false);
  const preferenceWriteSeqRef = useRef(0);
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [modelSubmenuOpen, setModelSubmenuOpen] = useState(false);
  const welcome = typeConfig?.welcome ?? null;
  const showWorkspaceWelcome =
    historyHydrated &&
    messages.length === 0 &&
    welcome !== null &&
    focusedMissionId === null;
  const inputPlaceholder = useMemo(() => {
    if (attachmentUploading) {
      return "附件上传中...";
    }
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
    if (showWorkspaceWelcome && welcome) {
      return welcome.inputPlaceholder;
    }
    return "输入消息... Shift+Enter 换行";
  }, [attachmentUploading, isSending, messages, showWorkspaceWelcome, welcome]);

  const showThinking = isSending && messages.length > 0 && messages[messages.length - 1].role === "user";
  const sendDisabled =
    isSending || attachmentUploading || !inputValue.trim();
  const lastMessageId = messages[messages.length - 1]?.id ?? null;
  const selectedModelLabel =
    modelOptions.find((model) => model.name === selectedModel)?.display_name ??
    selectedModel;
  const selectedModelDisplayLabel = cleanModelLabel(selectedModelLabel);
  const selectedModelCompactLabel = compactModelLabel(selectedModelLabel);
  const selectedModelOption = modelOptions.find(
    (model) => model.name === selectedModel,
  );
  const availableReasoningEfforts =
    selectedModelOption?.capability_profile.reasoning_efforts ?? [];
  const selectedModelSupportsReasoning = availableReasoningEfforts.length > 0;
  const selectedReasoningLabel =
    REASONING_EFFORT_OPTIONS.find((option) => option.value === reasoningEffort)?.label ??
    "超高";
  const persistModelPreference = useCallback(
    async (settings: {
      default_model?: string;
      reasoning_effort?: ReasoningEffort;
    }) => {
      const writeSeq = preferenceWriteSeqRef.current + 1;
      preferenceWriteSeqRef.current = writeSeq;
      setModelPreferenceError(null);
      try {
        await updateWorkspaceSettings(workspaceId, settings);
      } catch {
        if (preferenceWriteSeqRef.current === writeSeq) {
          setModelPreferenceError("模型偏好未能保存，当前选择仍用于本次对话");
        }
      }
    },
    [workspaceId],
  );
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
      void sendMessage(workspaceId, intent.trim(), [], withMissionRunContext(withSelectedModel(options), focusedMissionId)).then((result) => {
        if (result?.missionId) onMissionCreated?.(result.missionId);
      });
    },
    [focusedMissionId, isSending, onMissionCreated, sendMessage, withSelectedModel, workspaceId],
  );
  const handleWelcomeChoice = useCallback(
    (chip: WorkspaceWelcomeChip) => {
      if (isSending) {
        return;
      }
      setInputValue(chip.prompt);
      if (chip.action === "attach") {
        if (threadId) {
          fileAttachRef.current?.open();
        } else {
          pendingAttachmentOpenRef.current = true;
        }
      }
      window.requestAnimationFrame(() => {
        textareaRef.current?.focus();
        textareaRef.current?.setSelectionRange(
          chip.prompt.length,
          chip.prompt.length,
        );
      });
    },
    [isSending, threadId],
  );

  useImperativeHandle(
    ref,
    () => ({
      focusComposer: () => {
        textareaRef.current?.focus();
      },
      openAttachment: () => {
        if (threadId) {
          fileAttachRef.current?.open();
        } else {
          pendingAttachmentOpenRef.current = true;
        }
      },
    }),
    [threadId],
  );

  useEffect(() => {
    if (!threadId || !pendingAttachmentOpenRef.current) return;
    pendingAttachmentOpenRef.current = false;
    const frame = window.requestAnimationFrame(() => {
      fileAttachRef.current?.open();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [threadId]);

  useEffect(() => {
    let cancelled = false;
    setModelLoadState("loading");
    setModelPreferenceError(null);
    void Promise.allSettled([
      listModels("chat"),
      getWorkspaceSettings(workspaceId),
    ]).then(([catalogResult, settingsResult]) => {
      if (cancelled) return;
      if (catalogResult.status === "rejected") {
        if (cancelled) return;
        setModelOptions([]);
        setSelectedModel("");
        setModelLoadState("error");
        return;
      }
      const models = catalogResult.value.models;
      const settings =
        settingsResult.status === "fulfilled" ? settingsResult.value : null;
      const selected =
        models.find((model) => model.name === settings?.default_model) ??
        models.find((model) => model.is_default) ??
        models[0];
      setModelOptions(models);
      setSelectedModel(selected?.name ?? "");
      setReasoningEffort(
        chooseReasoningEffort(
          selected?.capability_profile.reasoning_efforts ?? [],
          settings?.reasoning_effort,
        ),
      );
      setModelLoadState("ready");
    });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  useEffect(() => {
    if (!modelMenuOpen) {
      return;
    }
    const closeOnPointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (
        target instanceof Node &&
        modelMenuRef.current?.contains(target)
      ) {
        return;
      }
      setModelMenuOpen(false);
      setModelSubmenuOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") {
        return;
      }
      setModelMenuOpen(false);
      setModelSubmenuOpen(false);
    };
    window.addEventListener("pointerdown", closeOnPointerDown);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("pointerdown", closeOnPointerDown);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [modelMenuOpen]);

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
    setThreadId(store.getThreadId(workspaceId));
    setAttachments([]);
    setAttachmentError(null);
    setAttachmentUploading(false);
    void store.loadHistory(workspaceId).then((tid) => {
      if (cancelled) return;
      setThreadId(tid);
      setHistoryHydration({ workspaceId, hydrated: true });
    });
    return () => {
      cancelled = true;
    };
  }, [setActiveWorkspace, workspaceId]);

  function handleSubmit() {
    const trimmed = inputValue.trim();
    if (!trimmed || isSending || attachmentUploading) return;
    setInputValue("");
    const currentAttachments = [...attachments];
    setAttachments([]);

    void sendMessage(
      workspaceId,
      trimmed,
      currentAttachments,
      withMissionRunContext(
        withSelectedModel(),
        focusedMissionId,
      ),
    ).then((result) => {
      if (result?.missionId) onMissionCreated?.(result.missionId);
    });
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
        {showWorkspaceWelcome && welcome ? (
          <WorkspaceWelcome
            icon={typeConfig?.icon ?? "问"}
            workspaceName={workspaceName}
            welcome={welcome}
            disabled={isSending}
            onChoose={handleWelcomeChoice}
          />
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
                  aria-label={`移除附件 ${a.name}`}
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
        {attachmentError ? (
          <div
            role="status"
            style={{
              marginBottom: 6,
              color: "var(--wjn-error)",
              fontSize: 12,
            }}
          >
            {attachmentError}
          </div>
        ) : null}
        <div
          style={{
            display: "flex",
            gap: 8,
            alignItems: "center",
          }}
        >
          <FileAttachButton
            ref={fileAttachRef}
            threadId={threadId}
            workspaceId={workspaceId}
            onAttached={(files) => {
              setAttachmentError(null);
              setAttachments((prev) => [...prev, ...files]);
            }}
            onError={setAttachmentError}
            onUploadingChange={setAttachmentUploading}
            disabled={isSending}
          />
          <textarea
            ref={textareaRef}
            data-testid="chat-composer-input"
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
          <div
            ref={modelMenuRef}
            style={{ position: "relative", flexShrink: 0 }}
          >
            <button
              type="button"
              aria-label="选择模型和推理强度"
              aria-haspopup="menu"
              aria-expanded={modelMenuOpen}
              data-testid="chat-model-selector"
              disabled={isSending || modelOptions.length === 0}
              onClick={() => {
                setModelMenuOpen((open) => !open);
                setModelSubmenuOpen(false);
              }}
              title={
                modelPreferenceError
                  ? modelPreferenceError
                  : modelLoadState === "error"
                  ? "模型目录加载失败"
                  : selectedModelDisplayLabel
                    ? `当前模型：${selectedModelDisplayLabel}`
                    : modelLoadState === "loading"
                      ? "模型加载中"
                      : "暂无可用模型"
              }
              style={{
                height: 38,
                minWidth: selectedModelSupportsReasoning ? 116 : 86,
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 7,
                borderRadius: "var(--wjn-radius)",
                border: "1px solid var(--wjn-line)",
                background: "#fff",
                color: "var(--wjn-text-secondary)",
                fontSize: 12.5,
                fontWeight: 650,
                padding: "0 9px",
                cursor:
                  isSending || modelOptions.length === 0
                    ? "not-allowed"
                    : "pointer",
                opacity: isSending ? 0.58 : 1,
                fontFamily: "var(--wjn-font-sans)",
                whiteSpace: "nowrap",
              }}
            >
              <Circle size={12} strokeWidth={2} aria-hidden="true" />
              <span>{selectedModelCompactLabel || "模型"}</span>
              {selectedModelSupportsReasoning ? (
                <span style={{ color: "var(--wjn-text-muted)" }}>
                  {selectedReasoningLabel}
                </span>
              ) : null}
              <ChevronDown size={13} aria-hidden="true" />
            </button>
            {modelMenuOpen ? (
              <div
                role="menu"
                data-testid="chat-model-menu"
                style={{
                  position: "absolute",
                  right: 0,
                  bottom: 44,
                  width: 210,
                  padding: 6,
                  borderRadius: "var(--wjn-radius-lg)",
                  border: "1px solid var(--wjn-line)",
                  background: "var(--wjn-surface)",
                  boxShadow: "var(--wjn-shadow-lg)",
                  zIndex: 30,
                  color: "var(--wjn-text)",
                  fontFamily: "var(--wjn-font-sans)",
                }}
              >
                {selectedModelSupportsReasoning ? (
                  <>
                    <div
                      style={{
                        padding: "4px 8px 3px",
                        fontSize: 12,
                        color: "var(--wjn-text-muted)",
                        fontWeight: 650,
                      }}
                    >
                      推理
                    </div>
                    {REASONING_EFFORT_OPTIONS.filter((option) =>
                      availableReasoningEfforts.includes(option.value),
                    ).map((option) => {
                      const active = reasoningEffort === option.value;
                      return (
                        <button
                          key={option.value}
                          type="button"
                          role="menuitemradio"
                          aria-checked={active}
                          data-testid={`chat-reasoning-option-${option.value}`}
                          onClick={() => {
                            setReasoningEffort(option.value);
                            void persistModelPreference({
                              reasoning_effort: option.value,
                            });
                          }}
                          style={{
                            width: "100%",
                            minHeight: 28,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: 10,
                            border: "none",
                            borderRadius: "var(--wjn-radius)",
                            background: active
                              ? "var(--wjn-surface-subtle)"
                              : "transparent",
                            color: "var(--wjn-text)",
                            fontSize: 13,
                            fontWeight: 600,
                            padding: "0 8px",
                            cursor: "pointer",
                            fontFamily: "var(--wjn-font-sans)",
                          }}
                        >
                          <span>{option.label}</span>
                          {active ? <Check size={14} aria-hidden="true" /> : null}
                        </button>
                      );
                    })}
                  </>
                ) : null}
                <div
                  style={{
                    height: 1,
                    margin: selectedModelSupportsReasoning ? "6px -6px" : "0 -6px 6px",
                    background: "var(--wjn-line)",
                  }}
                />
                <button
                  type="button"
                  role="menuitem"
                  data-testid="chat-model-submenu-trigger"
                  aria-haspopup="menu"
                  aria-expanded={modelSubmenuOpen}
                  onClick={() => setModelSubmenuOpen((open) => !open)}
                  style={{
                    width: "100%",
                    minHeight: 30,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 10,
                    border: "none",
                    borderRadius: "var(--wjn-radius)",
                    background: modelSubmenuOpen
                      ? "var(--wjn-surface-subtle)"
                      : "transparent",
                    color: "var(--wjn-text)",
                    fontSize: 13,
                    fontWeight: 650,
                    padding: "0 8px",
                    cursor: "pointer",
                    fontFamily: "var(--wjn-font-sans)",
                  }}
                >
                  <span>{selectedModelDisplayLabel || "模型"}</span>
                  <ChevronRight size={14} aria-hidden="true" />
                </button>
                {modelSubmenuOpen ? (
                  <div
                    role="menu"
                    aria-label="模型"
                    style={{
                      position: "absolute",
                      left: "calc(100% + 4px)",
                      bottom: 0,
                      width: 212,
                      padding: 6,
                      borderRadius: "var(--wjn-radius-lg)",
                      border: "1px solid var(--wjn-line)",
                      background: "var(--wjn-surface)",
                      boxShadow: "var(--wjn-shadow-lg)",
                    }}
                  >
                    <div
                      style={{
                        padding: "4px 8px 3px",
                        fontSize: 12,
                        color: "var(--wjn-text-muted)",
                        fontWeight: 650,
                      }}
                    >
                      模型
                    </div>
                    {modelOptions.map((model) => {
                      const active = model.name === selectedModel;
                      return (
                        <button
                          key={model.name}
                          type="button"
                          role="menuitemradio"
                          aria-checked={active}
                          data-testid={`chat-model-option-${model.name}`}
                          onClick={() => {
                            const nextReasoningEffort = chooseReasoningEffort(
                              model.capability_profile.reasoning_efforts,
                              reasoningEffort,
                            );
                            setSelectedModel(model.name);
                            setReasoningEffort(nextReasoningEffort);
                            setModelMenuOpen(false);
                            setModelSubmenuOpen(false);
                            void persistModelPreference({
                              default_model: model.name,
                              reasoning_effort: nextReasoningEffort,
                            });
                          }}
                          style={{
                            width: "100%",
                            minHeight: 30,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: 10,
                            border: "none",
                            borderRadius: "var(--wjn-radius)",
                            background: active
                              ? "var(--wjn-surface-subtle)"
                              : "transparent",
                            color: "var(--wjn-text)",
                            fontSize: 13,
                            fontWeight: 600,
                            padding: "0 8px",
                            cursor: "pointer",
                            fontFamily: "var(--wjn-font-sans)",
                          }}
                        >
                          <span>{cleanModelLabel(model.display_name)}</span>
                          {active ? <Check size={14} aria-hidden="true" /> : null}
                        </button>
                      );
                    })}
                  </div>
                ) : null}
                {modelPreferenceError ? (
                  <div
                    role="status"
                    data-testid="chat-model-preference-error"
                    style={{
                      margin: "6px 8px 2px",
                      color: "var(--wjn-error)",
                      fontSize: 11.5,
                      lineHeight: 1.35,
                    }}
                  >
                    {modelPreferenceError}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
          <button
            onClick={handleSubmit}
            disabled={sendDisabled}
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
                sendDisabled
                  ? "var(--wjn-line-strong)"
                  : "var(--wjn-accent)",
              color: "#FFFFFF",
              fontSize: 13,
              cursor:
                sendDisabled ? "not-allowed" : "pointer",
              opacity: isSending || attachmentUploading ? 0.6 : 1,
            }}
            aria-label="发送"
          >
            {isSending || attachmentUploading ? "..." : <SendHorizontal size={16} aria-hidden="true" />}
          </button>
        </div>
      </div>
    </div>
  );
  },
);

function WorkspaceWelcome({
  icon,
  workspaceName,
  welcome,
  disabled,
  onChoose,
}: {
  icon: string;
  workspaceName?: string;
  welcome: WorkspaceWelcomeConfig;
  disabled: boolean;
  onChoose: (chip: WorkspaceWelcomeChip) => void;
}) {
  return (
    <div
      data-testid="workspace-welcome"
      style={{
        minHeight: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px 18px",
        animation: "wjn-panel-in 360ms var(--wjn-ease-standard)",
      }}
    >
      <section
        aria-label={welcome.eyebrow}
        style={{
          width: "min(100%, 480px)",
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-start",
          gap: 14,
        }}
      >
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <span
            aria-hidden="true"
            style={{
              width: 34,
              height: 34,
              borderRadius: "var(--wjn-radius)",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              background: "var(--wjn-text)",
              color: "#fff",
              fontSize: 14,
              fontWeight: 800,
              fontFamily: "var(--wjn-font-sans)",
            }}
          >
            {icon}
          </span>
          <div style={{ minWidth: 0 }}>
            <div
              style={{
                color: "var(--wjn-text-muted)",
                fontSize: 12,
                fontWeight: 700,
                fontFamily: "var(--wjn-font-sans)",
              }}
            >
              {welcome.eyebrow}
            </div>
            {workspaceName ? (
              <div
                style={{
                  color: "var(--wjn-text)",
                  fontSize: 13,
                  fontWeight: 750,
                  fontFamily: "var(--wjn-font-sans)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                  maxWidth: 340,
                }}
              >
                {workspaceName}
              </div>
            ) : null}
          </div>
        </div>

        <div>
          <h2
            style={{
              margin: 0,
              color: "var(--wjn-text)",
              fontSize: 21,
              fontWeight: 760,
              lineHeight: 1.28,
              fontFamily: "var(--wjn-font-sans)",
            }}
          >
            {welcome.title}
          </h2>
          <p
            style={{
              margin: "8px 0 0",
              color: "var(--wjn-text-secondary)",
              fontSize: 13.5,
              lineHeight: 1.75,
              fontFamily: "var(--wjn-font-sans)",
            }}
          >
            {welcome.body}
          </p>
        </div>

        <div
          style={{
            width: "100%",
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
          }}
        >
          {welcome.chips.map((chip) => (
            <button
              key={chip.label}
              type="button"
              data-testid="workspace-welcome-chip"
              disabled={disabled}
              onClick={() => onChoose(chip)}
              style={{
                minHeight: 34,
                padding: "0 12px",
                borderRadius: "var(--wjn-radius)",
                border: "1px solid var(--wjn-line)",
                background: "var(--wjn-surface)",
                color: "var(--wjn-text)",
                fontSize: 13,
                fontWeight: 680,
                fontFamily: "var(--wjn-font-sans)",
                cursor: disabled ? "not-allowed" : "pointer",
                opacity: disabled ? 0.55 : 1,
                transition: "background 150ms, border-color 150ms, color 150ms",
              }}
              onMouseEnter={(event) => {
                if (disabled) {
                  return;
                }
                event.currentTarget.style.background = "var(--wjn-accent-soft)";
                event.currentTarget.style.borderColor = "var(--wjn-accent-line)";
                event.currentTarget.style.color = "var(--wjn-accent-strong)";
              }}
              onMouseLeave={(event) => {
                event.currentTarget.style.background = "var(--wjn-surface)";
                event.currentTarget.style.borderColor = "var(--wjn-line)";
                event.currentTarget.style.color = "var(--wjn-text)";
              }}
            >
              {chip.label}
            </button>
          ))}
        </div>
      </section>
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
