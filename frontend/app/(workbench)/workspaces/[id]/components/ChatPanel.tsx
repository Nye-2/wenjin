"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  createThread,
  uploadThreadFiles,
  type ChatAttachment,
  type ChatUploadKind,
  type ReasoningEffort,
} from "@/lib/api";
import { useModelSelection } from "@/hooks/useModelSelection";
import { useChatStore, Message } from "@/stores/chat";
import { useDashboardStore } from "@/stores/dashboard";
import { useWorkspaceStore } from "@/stores/workspace";
import { useTaskStore } from "@/stores/task";
import { useFeaturesStore } from "@/stores/features";
import {
  WorkspaceChatMessages,
  resolveBlockFeatureId,
} from "./WorkspaceChatMessages";
import {
  isReasoningEffort,
  WorkspaceChatComposer,
} from "./WorkspaceChatComposer";
import { WorkspaceChatHeader } from "./WorkspaceChatHeader";
import { getWorkspaceFeatureRoute } from "@/lib/workspace-feature-routes";
import {
  createWorkspaceFeatureTask,
  trackWorkspaceFeatureTask,
} from "@/lib/workspace-feature-execution";
import {
  readWorkspaceFeatureOrchestrationParams,
  resolveWorkspaceFeatureActionContext,
  type WorkspaceFeatureActionContext,
} from "@/lib/workspace-feature-action-context";
import {
  formatWorkspaceChatSkillLabel,
  getWorkspaceChatSkills
} from "@/lib/workspace-chat-skills";

interface ChatPanelProps {
  workspaceId: string;
}

interface PendingChatAttachment {
  id: string;
  file: File;
  kind: ChatUploadKind;
}

export function ChatPanel({ workspaceId }: ChatPanelProps) {
  const router = useRouter();
  const {
    messages,
    isStreaming,
    isThreadsLoading,
    currentSkill,
    error: chatError,
    threadId,
    threads,
    deleteThread,
    loadThread,
    sendMessage,
    startNewThread,
    setCurrentSkill,
  } = useChatStore();
  const recommendedFeatureIds = useDashboardStore(
    (state) => state.summary?.recommended_actions.map((action) => action.feature_id) ?? []
  );
  const { workspace, artifacts } = useWorkspaceStore();
  const {
    startTask,
    isExecuting,
  } = useTaskStore();
  const { getFeatureById } = useFeaturesStore();
  const [inputValue, setInputValue] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [deletingThreadId, setDeletingThreadId] = useState<string | null>(null);
  const [selectedReasoningEffort, setSelectedReasoningEffort] = useState<ReasoningEffort | null>(null);
  const [defaultUploadKind, setDefaultUploadKind] = useState<ChatUploadKind>("transient");
  const [pendingAttachments, setPendingAttachments] = useState<PendingChatAttachment[]>([]);
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
  const attachmentInputRef = useRef<HTMLInputElement>(null);
  const availableChatSkills = getWorkspaceChatSkills(workspace?.type);
  const currentSkillLabel = formatWorkspaceChatSkillLabel(workspace?.type, currentSkill);
  const resolveSkillLabel = (skillId: string | null | undefined): string | null =>
    formatWorkspaceChatSkillLabel(workspace?.type, skillId);
  const selectedModelDefinition =
    availableModels.find((candidate) => candidate.name === selectedModel) ?? null;
  const currentThreadSummary =
    threadId ? threads.find((candidate) => candidate.id === threadId) ?? null : null;
  const supportsReasoningEffort = selectedModelDefinition?.supports_reasoning_effort ?? false;
  const reasoningPersistenceKey = `workspace:${workspaceId}:model:chat:reasoning-effort`;

  useEffect(() => {
    if (!workspace?.type || !currentSkill) {
      return;
    }
    const isSupported = availableChatSkills.some((skill) => skill.id === currentSkill);
    if (!isSupported) {
      setCurrentSkill(null);
    }
  }, [availableChatSkills, currentSkill, setCurrentSkill, workspace?.type]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    if (!supportsReasoningEffort) {
      if (selectedReasoningEffort !== null) {
        setSelectedReasoningEffort(null);
      }
      return;
    }
    try {
      const persisted = window.localStorage.getItem(reasoningPersistenceKey);
      if (isReasoningEffort(persisted)) {
        setSelectedReasoningEffort(persisted);
        return;
      }
    } catch {
      // Ignore localStorage failures.
    }
    setSelectedReasoningEffort((current) => current ?? "minimal");
  }, [reasoningPersistenceKey, selectedReasoningEffort, supportsReasoningEffort]);

  useEffect(() => {
    if (typeof window === "undefined" || !supportsReasoningEffort || !selectedReasoningEffort) {
      return;
    }
    try {
      window.localStorage.setItem(reasoningPersistenceKey, selectedReasoningEffort);
    } catch {
      // Ignore localStorage failures.
    }
  }, [reasoningPersistenceKey, selectedReasoningEffort, supportsReasoningEffort]);

  const openFeature = (route: string | null, featureId: string | null) => {
    const targetRoute =
      route || (featureId ? getWorkspaceFeatureRoute(workspaceId, featureId) : null);
    if (targetRoute) {
      router.push(targetRoute);
    }
  };

  // 处理快捷指令点击
  const handleQuickAction = async (
    featureId: string,
    overrideParams?: Record<string, unknown>
  ) => {
    if (isExecuting) return;

    const feature = getFeatureById(featureId);
    if (!feature) return;

    setActionError(null);

    try {
      // 根据 feature 类型构造默认参数，保证快捷动作命中正确后端 action。
      const params: Record<string, unknown> = {
        ...(overrideParams ?? {}),
      };
      if (
        feature.id === "deep_research" &&
        params.query === undefined &&
        params.topic === undefined
      ) {
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
      if (feature.id === "thesis_writing" && params.action === undefined) {
        // Chat 快捷动作默认走 Step 1：大纲生成，避免落入无参写作动作。
        const paperTitle =
          workspace?.name?.trim() ||
          workspace?.description?.trim() ||
          "未命名论文";
        params.action = "generate_outline";
        params.paper_title = paperTitle;
        params.target_words = 20000;
      }
      if (selectedModel && params.model_id === undefined) {
        params.model_id = selectedModel;
      }

      const created = await createWorkspaceFeatureTask({
        workspaceId,
        featureId: feature.id,
        params,
        threadId: threadId || undefined,
        warningFallback: "该功能暂时无法执行",
        missingTaskFallback: "任务创建失败，请稍后重试",
      });
      trackWorkspaceFeatureTask({
        feature,
        startTask,
        taskId: created.taskId,
        initialThinking: created.message,
      });
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to execute feature");
    }
  };

  const handleContinueAsk = (prompt: string | null) => {
    const nextPrompt = prompt?.trim();
    if (!nextPrompt) {
      return;
    }
    setActionError(null);
    setInputValue(nextPrompt);
    requestAnimationFrame(() => {
      inputRef.current?.focus();
      const end = nextPrompt.length;
      inputRef.current?.setSelectionRange(end, end);
    });
  };

  const handleRerunFromArtifact = (
    featureId: string | null,
    params: Record<string, unknown> | null,
    unavailableReason: string | null
  ) => {
    if (!featureId) {
      return;
    }
    if (!params) {
      setActionError(unavailableReason || "当前没有可复用的 artifact。");
      return;
    }
    void handleQuickAction(featureId, params);
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
    if (isStreaming) {
      return;
    }

    const content = inputValue.trim();
    if (!content) {
      setActionError(
        pendingAttachments.length > 0
          ? "发送附件时请补充一句说明。"
          : "请输入消息内容。"
      );
      return;
    }

    setActionError(null);

    try {
      let activeThreadId = threadId || undefined;
      let uploadedAttachments: ChatAttachment[] = [];

      if (pendingAttachments.length > 0) {
        if (!activeThreadId) {
          const createdThread = await createThread({
            workspace_id: workspaceId,
            model: selectedModel || undefined,
            skill: currentSkill,
          });
          activeThreadId = createdThread.id;
        }

        const grouped = pendingAttachments.reduce(
          (map, attachment) => {
            const existing = map.get(attachment.kind) ?? [];
            existing.push(attachment.file);
            map.set(attachment.kind, existing);
            return map;
          },
          new Map<ChatUploadKind, File[]>()
        );

        const uploadResults = await Promise.all(
          Array.from(grouped.entries()).map(([kind, files]) =>
            uploadThreadFiles({
              threadId: activeThreadId as string,
              kind,
              workspaceId,
              files,
            })
          )
        );
        uploadedAttachments = uploadResults.flatMap((result) => result.files);
      }

      setInputValue("");
      setPendingAttachments([]);
      await sendMessage(content, {
        workspaceId,
        skill: currentSkill,
        model: selectedModel || undefined,
        reasoningEffort: supportsReasoningEffort ? selectedReasoningEffort ?? "minimal" : undefined,
        threadId: activeThreadId,
        attachments: uploadedAttachments,
      });
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to upload attachments");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleSelectThread = async (selectedThreadId: string) => {
    setIsHistoryOpen(false);
    setPendingAttachments([]);
    await loadThread(selectedThreadId);
  };

  const handleStartNewThread = () => {
    setIsHistoryOpen(false);
    setActionError(null);
    setPendingAttachments([]);
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

  const resolveMessageActionContext = (
    message: Message
  ): WorkspaceFeatureActionContext => {
    const orchestration =
      message.metadata?.orchestration &&
      typeof message.metadata.orchestration === "object"
        ? (message.metadata.orchestration as Record<string, unknown>)
        : null;
    const featureId =
      typeof orchestration?.feature_id === "string"
        ? orchestration.feature_id
        : resolveBlockFeatureId(message);

    return resolveWorkspaceFeatureActionContext({
      workspaceId,
      featureId,
      workspace,
      artifacts,
      orchestrationParams: readWorkspaceFeatureOrchestrationParams(
        orchestration?.params
      ),
    });
  };

  const handleOpenFilePicker = () => {
    attachmentInputRef.current?.click();
  };

  const handleSelectFiles = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    if (files.length === 0) {
      return;
    }

    const createdAt = Date.now();
    setPendingAttachments((current) => [
      ...current,
      ...files.map((file, index) => ({
        id: `attachment-${createdAt}-${index}`,
        file,
        kind: defaultUploadKind,
      })),
    ]);
    event.target.value = "";
  };

  const handleRemoveAttachment = (attachmentId: string) => {
    setPendingAttachments((current) =>
      current.filter((attachment) => attachment.id !== attachmentId)
    );
  };

  const handleUpdateAttachmentKind = (
    attachmentId: string,
    kind: ChatUploadKind
  ) => {
    setPendingAttachments((current) =>
      current.map((attachment) =>
        attachment.id === attachmentId
          ? { ...attachment, kind }
          : attachment
      )
    );
  };

  const composerError = actionError ?? chatError;

  return (
    <div className="flex-1 h-full flex flex-col">
      <input
        ref={attachmentInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={handleSelectFiles}
      />
      <WorkspaceChatHeader
        workspaceName={workspace?.name}
        workspaceType={workspace?.type}
        currentSkillLabel={currentSkillLabel}
        currentThreadSummary={currentThreadSummary}
        messages={messages}
        isHistoryOpen={isHistoryOpen}
        isThreadsLoading={isThreadsLoading}
        threadId={threadId}
        threads={threads}
        deletingThreadId={deletingThreadId}
        isStreaming={isStreaming}
        resolveSkillLabel={resolveSkillLabel}
        onToggleHistory={() => setIsHistoryOpen((open) => !open)}
        onStartNewThread={handleStartNewThread}
        onSelectThread={(selectedThreadId) => void handleSelectThread(selectedThreadId)}
        onDeleteThread={(selectedThreadId) => void handleDeleteThread(selectedThreadId)}
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        <WorkspaceChatMessages
          messages={messages}
          isStreaming={isStreaming}
          workspaceName={workspace?.name}
          resolveActionContext={resolveMessageActionContext}
          onFeatureAction={(nextFeatureId) => void handleQuickAction(nextFeatureId)}
          onOpenFeature={openFeature}
          onContinueAsk={handleContinueAsk}
          onRerunFeature={handleRerunFromArtifact}
        />
        <div ref={messagesEndRef} />
      </div>

      <WorkspaceChatComposer
        actionError={composerError}
        isExecuting={isExecuting}
        recommendedFeatureIds={recommendedFeatureIds}
        onQuickAction={(featureId) => void handleQuickAction(featureId)}
        workspaceType={workspace?.type}
        currentSkill={currentSkill}
        onSelectSkill={setCurrentSkill}
        availableModels={availableModels}
        selectedModel={selectedModel}
        onSelectModel={setSelectedModel}
        isStreaming={isStreaming}
        supportsReasoningEffort={supportsReasoningEffort}
        selectedReasoningEffort={selectedReasoningEffort}
        onSelectReasoningEffort={setSelectedReasoningEffort}
        defaultUploadKind={defaultUploadKind}
        onSelectDefaultUploadKind={setDefaultUploadKind}
        pendingAttachments={pendingAttachments.map((attachment) => ({
          id: attachment.id,
          name: attachment.file.name,
          size: attachment.file.size,
          kind: attachment.kind,
        }))}
        onOpenFilePicker={handleOpenFilePicker}
        onRemoveAttachment={handleRemoveAttachment}
        onUpdateAttachmentKind={handleUpdateAttachmentKind}
        inputValue={inputValue}
        onInputChange={setInputValue}
        inputRef={inputRef}
        onKeyDown={handleKeyDown}
        onSubmit={handleSubmit}
      />
    </div>
  );
}
