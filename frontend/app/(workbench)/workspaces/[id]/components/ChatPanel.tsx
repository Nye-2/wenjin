"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, ChevronDown, ChevronUp, FileText, GitBranch, Layers3 } from "lucide-react";
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
import { type CurrentTask, useTaskStore } from "@/stores/task";
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
  buildWorkspaceChatEntryPrompt,
  type WorkspaceChatEntrySeed,
} from "@/lib/workspace-chat-entry";

import { TaskRuntimePanel } from "@/components/workspace/TaskRuntimePanel";

function formatRuntimeTimestamp(value?: string): string {
  if (!value) {
    return "N/A";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function buildTaskRuntimeState(task: CurrentTask | null) {
  if (!task) {
    return null;
  }

  return {
    title: task.agentLabel,
    current_phase: task.stages[task.currentStageIndex]?.id,
    phases: task.stages.map((stage, index) => ({
      id: stage.id,
      label: stage.label,
      description:
        stage.status === "running"
          ? "当前阶段正在推进中"
          : stage.status === "completed"
            ? "该阶段已完成"
            : "等待进入该阶段",
      status: stage.status,
      progress:
        stage.status === "completed"
          ? 100
          : stage.status === "running"
            ? Math.max(
                12,
                Math.round(((index + 1) / Math.max(task.stages.length, 1)) * 100)
              )
            : 0,
    })),
    blocks: [
      {
        id: "task-metrics",
        kind: "metrics" as const,
        title: "任务信息",
        entries: [
          { label: "Task", value: task.id.slice(0, 8) },
          { label: "Agent", value: task.agentLabel },
          { label: "Started", value: formatRuntimeTimestamp(task.startedAt) },
          {
            label: "Updated",
            value: formatRuntimeTimestamp(task.completedAt || task.startedAt),
          },
        ],
      },
      {
        id: "task-thinking",
        kind: "text" as const,
        title: "当前说明",
        content:
          task.thinking?.trim() || "任务已启动，等待更多运行时信息。",
      },
    ],
    updated_at: task.completedAt || task.startedAt,
  };
}

interface ChatPanelProps {
  workspaceId: string;
  entrySeed?: WorkspaceChatEntrySeed | null;
}

interface PendingChatAttachment {
  id: string;
  file: File;
  kind: ChatUploadKind;
}

export function ChatPanel({ workspaceId, entrySeed = null }: ChatPanelProps) {
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
  const summary = useDashboardStore((state) => state.summary);
  const fetchDashboard = useDashboardStore((state) => state.fetchDashboard);
  const { workspace, artifacts } = useWorkspaceStore();
  const fetchPapers = useWorkspaceStore((state) => state.fetchPapers);
  const fetchArtifacts = useWorkspaceStore((state) => state.fetchArtifacts);
  const {
    startTask,
    isExecuting,
    currentTask,
    recentCompleted,
  } = useTaskStore();
  const { getFeatureById, getSkillById } = useFeaturesStore();
  const skills = useFeaturesStore((state) => state.skills);
  const [inputValue, setInputValue] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [deletingThreadId, setDeletingThreadId] = useState<string | null>(null);
  const [selectedReasoningEffort, setSelectedReasoningEffort] = useState<ReasoningEffort | null>(null);
  const [defaultUploadKind, setDefaultUploadKind] = useState<ChatUploadKind>("transient");
  const [pendingAttachments, setPendingAttachments] = useState<PendingChatAttachment[]>([]);
  const [statusExpanded, setStatusExpanded] = useState(false);
  const [pendingEntrySeed, setPendingEntrySeed] = useState<WorkspaceChatEntrySeed | null>(
    entrySeed
  );
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
  const appliedEntrySeedKeyRef = useRef<string | null>(null);
  const currentSkillLabel = currentSkill ? (getSkillById(currentSkill)?.name ?? currentSkill) : null;
  const resolveSkillLabel = (skillId: string | null | undefined): string | null =>
    skillId ? (getSkillById(skillId)?.name ?? skillId) : null;
  const selectedModelDefinition =
    availableModels.find((candidate) => candidate.name === selectedModel) ?? null;
  const currentThreadSummary =
    threadId ? threads.find((candidate) => candidate.id === threadId) ?? null : null;
  const supportsReasoningEffort = selectedModelDefinition?.supports_reasoning_effort ?? false;
  const reasoningPersistenceKey = `workspace:${workspaceId}:model:chat:reasoning-effort`;
  const entrySeedFeature = entrySeed?.featureId
    ? getFeatureById(entrySeed.featureId)
    : undefined;
  const recommendedFeatureIds = useMemo(
    () => summary?.recommended_actions.map((action) => action.feature_id) ?? [],
    [summary?.recommended_actions]
  );
  const recommendedActions = useMemo(() => {
    if (summary?.recommended_actions && summary.recommended_actions.length > 0) {
      return summary.recommended_actions
        .map((action) => ({
          featureId: action.feature_id,
          title: action.title,
          description: action.reason || action.description || "",
        }))
        .filter((action) => Boolean(action.featureId))
        .slice(0, 2);
    }

    return (summary?.recommended_actions ?? [])
      .map((featureId) => {
        const feature = getFeatureById(featureId.feature_id);
        if (!feature) {
          return null;
        }
        return {
          featureId: featureId.feature_id,
          title: feature.name,
          description: feature.description,
        };
      })
      .filter((item): item is { featureId: string; title: string; description: string } => item !== null)
      .slice(0, 2);
  }, [getFeatureById, summary?.recommended_actions]);
  const contextStats = useMemo(
    () => [
      { label: "产物", value: artifacts.length, icon: FileText },
      { label: "分支", value: threads.length, icon: GitBranch },
      { label: "消息", value: messages.length, icon: Layers3 },
    ],
    [artifacts.length, threads.length, messages.length]
  );
  const currentPhaseTitle =
    summary?.current_phase.title ||
    (pendingEntrySeed?.featureId
      ? getFeatureById(pendingEntrySeed.featureId)?.name
      : null) ||
    "继续当前主线";
  const currentPhaseDescription =
    summary?.current_phase.description ||
    (pendingEntrySeed?.featureId
      ? "已根据入口上下文预置本次工作目标。"
      : "从当前阶段开始，告诉问津你要推进什么。");
  const nextStepAction = summary?.next_step ?? null;

  useEffect(() => {
    const nextSeedKey = entrySeed
      ? JSON.stringify({
          featureId: entrySeed.featureId,
          skillId: entrySeed.skillId,
          params: entrySeed.params,
        })
      : null;

    if (!nextSeedKey) {
      appliedEntrySeedKeyRef.current = null;
      setPendingEntrySeed(null);
      return;
    }

    if (appliedEntrySeedKeyRef.current === nextSeedKey) {
      return;
    }
    if (!entrySeed) {
      return;
    }

    const prompt = buildWorkspaceChatEntryPrompt({
      seed: entrySeed,
      feature: entrySeedFeature ?? null,
    });
    setActionError(null);
    setPendingEntrySeed(entrySeed);
    appliedEntrySeedKeyRef.current = nextSeedKey;

    // Auto-send entry prompt so LLM generates the guidance message.
    // Only include orchestration metadata for real features, not onboarding.
    const isOnboarding = entrySeed.featureId === "__onboarding__";
    sendMessage(prompt, {
      workspaceId,
      skill: entrySeed.skillId ?? currentSkill,
      model: selectedModel || undefined,
      metadata: isOnboarding
        ? undefined
        : {
            orchestration: {
              feature_id: entrySeed.featureId,
              params: entrySeed.params,
            },
          },
    });
    setPendingEntrySeed(null);
  }, [entrySeed, entrySeedFeature]);

  useEffect(() => {
    if (!currentSkill || skills.length === 0) {
      return;
    }
    const isSupported = skills.some((skill) => skill.id === currentSkill);
    if (!isSupported) {
      setCurrentSkill(null);
    }
  }, [skills, currentSkill, setCurrentSkill]);

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
      setActionError(error instanceof Error ? error.message : "执行模块失败");
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
        const refreshJobs: Promise<void>[] = [fetchDashboard(workspaceId)];
        if (uploadedAttachments.some((attachment) => attachment.paper_id)) {
          refreshJobs.push(fetchPapers(workspaceId));
        }
        if (uploadedAttachments.some((attachment) => attachment.artifact_id)) {
          refreshJobs.push(fetchArtifacts(workspaceId));
        }
        await Promise.allSettled(refreshJobs);
      }

      setInputValue("");
      setPendingAttachments([]);
      sendMessage(content, {
        workspaceId,
        skill: currentSkill,
        model: selectedModel || undefined,
        reasoningEffort: supportsReasoningEffort ? selectedReasoningEffort ?? "minimal" : undefined,
        threadId: activeThreadId,
        attachments: uploadedAttachments,
        metadata: pendingEntrySeed
          ? {
              orchestration: {
                feature_id: pendingEntrySeed.featureId,
                params: pendingEntrySeed.params,
              },
            }
          : undefined,
      });
      setPendingEntrySeed(null);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "附件上传失败");
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
    setPendingEntrySeed(null);
    setInputValue("");
    startNewThread();
  };

  const handleDeleteThread = async (selectedThreadId: string) => {
    setActionError(null);
    setDeletingThreadId(selectedThreadId);
    try {
      await deleteThread(selectedThreadId, workspaceId);
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "删除对话分支失败"
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
    const feature = featureId ? getFeatureById(featureId) : undefined;

    return resolveWorkspaceFeatureActionContext({
      workspaceId,
      featureId,
      feature: feature ?? null,
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
  const visibleRuntimeTask = currentTask ?? recentCompleted ?? null;
  const runtimeState = useMemo(
    () => buildTaskRuntimeState(visibleRuntimeTask),
    [visibleRuntimeTask]
  );
  const runtimeStatus = visibleRuntimeTask?.status ?? null;
  const runtimeError =
    visibleRuntimeTask?.status === "failed"
      ? visibleRuntimeTask.thinking.replace(/^错误:\s*/, "").trim()
      : null;

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

      <div className="border-b border-[var(--border-default)] bg-[rgba(251,248,242,0.94)] px-4 py-2">
        <div className="flex items-center gap-3">
          {/* Stage indicator */}
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-[var(--brand-brass)]" />
            <span className="text-sm font-medium text-[var(--text-primary)]">
              {currentPhaseTitle}
            </span>
          </div>

          {/* Skill badge */}
          {currentSkillLabel ? (
            <span className="rounded-full border border-[var(--accent-primary)]/18 bg-[var(--accent-primary)]/8 px-2 py-0.5 text-[10px] font-medium text-[var(--accent-primary)]">
              {currentSkillLabel}
            </span>
          ) : null}

          {/* Stats */}
          <span className="text-xs text-[var(--text-muted)]">
            产出 {artifacts.length}
          </span>

          {/* Right side: recommendation + toggle */}
          <div className="ml-auto flex items-center gap-2">
            {nextStepAction?.feature_id ? (
              <button
                type="button"
                onClick={() => {
                  const route = getWorkspaceFeatureRoute(workspaceId, nextStepAction.feature_id);
                  if (route) router.push(route);
                }}
                className="text-xs font-medium text-[var(--brand-navy)] hover:underline"
              >
                推荐：{nextStepAction.title} →
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => setStatusExpanded((prev) => !prev)}
              className="rounded-lg p-1 text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-surface)]"
            >
              {statusExpanded ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </button>
          </div>
        </div>

        {/* Expanded detail */}
        {statusExpanded ? (
          <div className="mt-3 grid gap-3 xl:grid-cols-2">
            {/* Phase detail */}
            <div className="rounded-2xl border border-[var(--border-default)] bg-white/76 p-4">
              <p className="text-sm font-medium text-[var(--text-primary)]">
                {currentPhaseTitle}
              </p>
              <p className="mt-2 text-xs leading-6 text-[var(--text-secondary)]">
                {summary?.headline || currentPhaseDescription}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {contextStats.map((item) => (
                  <div
                    key={item.label}
                    className="flex items-center gap-1.5 rounded-full border border-[var(--border-default)] bg-white/78 px-2.5 py-1 text-[10px] text-[var(--text-muted)]"
                  >
                    <item.icon className="h-3 w-3" />
                    {item.label}: {item.value}
                  </div>
                ))}
              </div>
            </div>

            {/* Recommendations */}
            <div className="rounded-2xl border border-[var(--border-default)] bg-white/76 p-4">
              <p className="text-sm font-medium text-[var(--text-primary)]">推荐动作</p>
              {nextStepAction ? (
                <div className="mt-2">
                  <p className="text-xs leading-6 text-[var(--text-secondary)]">
                    {nextStepAction.reason || nextStepAction.description || "从当前主线继续推进。"}
                  </p>
                </div>
              ) : null}
              {recommendedActions.length > 0 ? (
                <div className="mt-2 space-y-1.5">
                  {recommendedActions.map((action) => (
                    <button
                      key={`${action.featureId}-${action.title}`}
                      type="button"
                      onClick={() => void handleQuickAction(action.featureId)}
                      className="flex w-full items-center justify-between gap-2 rounded-xl border border-[var(--border-default)] bg-white/60 px-3 py-2 text-left text-xs transition-colors hover:bg-[var(--bg-surface)]"
                    >
                      <span className="text-[var(--text-primary)]">{action.title}</span>
                      <ArrowRight className="h-3 w-3 shrink-0 text-[var(--text-muted)]" />
                    </button>
                  ))}
                </div>
              ) : !nextStepAction ? (
                <p className="mt-2 text-xs text-[var(--text-secondary)]">
                  直接描述你要推进的步骤。
                </p>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>

      {runtimeState ? (
        <div className="border-b border-[var(--border-default)] bg-[rgba(251,248,242,0.72)] px-6 py-4">
          <TaskRuntimePanel
            runtime={runtimeState}
            isRunning={visibleRuntimeTask?.status === "running"}
            status={runtimeStatus}
            error={runtimeError}
            title="当前运行时"
          />
        </div>
      ) : null}

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
