"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import {
  uploadThreadFiles,
  type ThreadAttachment,
  type ThreadUploadKind,
  type ExecutionSession,
  type ReasoningEffort,
} from "@/lib/api";
import { useModelSelection } from "@/hooks/useModelSelection";
import { useThreadStore } from "@/stores/thread";
import { useDashboardStore } from "@/stores/dashboard";
import { useExecutionStore } from "@/stores/execution";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeaturesStore } from "@/stores/features";
import { WorkspaceThreadMessages } from "./WorkspaceThreadMessages";
import {
  isReasoningEffort,
  WorkspaceThreadComposer,
} from "./WorkspaceThreadComposer";
import { WorkspaceThreadHeader } from "./WorkspaceThreadHeader";
import {
  buildWorkspaceThreadEntryPrompt,
  resolveWorkspaceThreadEntrySkill,
  type WorkspaceThreadEntrySeed,
} from "@/lib/workspace-thread-entry";

interface ThreadPanelProps {
  workspaceId: string;
  entrySeed?: WorkspaceThreadEntrySeed | null;
}

interface PendingThreadAttachment {
  id: string;
  file: File;
  kind: ThreadUploadKind;
}

function resolveContinuationMetadata(
  messages: Array<{
    role: "user" | "assistant";
    metadata: Record<string, unknown> | null;
  }>
): Record<string, unknown> | null {
  const latestAssistant = [...messages]
    .reverse()
    .find((message) => message.role === "assistant");
  if (!latestAssistant || !latestAssistant.metadata) {
    return null;
  }

  const orchestration = latestAssistant.metadata.orchestration;
  if (!orchestration || typeof orchestration !== "object") {
    return null;
  }
  const payload = orchestration as Record<string, unknown>;
  const executionSessionId =
    typeof payload.execution_session_id === "string"
      ? payload.execution_session_id.trim()
      : "";
  const featureId =
    typeof payload.feature_id === "string"
      ? payload.feature_id.trim()
      : "";
  const status =
    typeof payload.status === "string" ? payload.status.trim() : "";
  if (!featureId) {
    return null;
  }

  if (
    ["awaiting_user_input", "missing_params"].includes(status) &&
    executionSessionId
  ) {
    return {
      orchestration: {
        intent: "resume",
        feature_id: featureId,
        execution_session_id: executionSessionId,
        status: "awaiting_user_input",
        params:
          payload.params && typeof payload.params === "object"
            ? (payload.params as Record<string, unknown>)
            : {},
      },
    };
  }

  if (["confirmation_required", "awaiting_user_confirmation"].includes(status)) {
    return {
      orchestration: {
        intent: "launch",
        feature_id: featureId,
        status: "confirmation_required",
        params:
          payload.params && typeof payload.params === "object"
            ? (payload.params as Record<string, unknown>)
            : {},
      },
    };
  }

  return null;
}

const EMPTY_EXECUTION_SESSIONS: ExecutionSession[] = [];
const EMPTY_EXECUTION_IDS: string[] = [];

export function ThreadPanel({ workspaceId, entrySeed = null }: ThreadPanelProps) {
  const messages = useThreadStore((state) => state.messages);
  const isStreaming = useThreadStore((state) => state.isStreaming);
  const isThreadLoading = useThreadStore((state) => state.isThreadLoading);
  const currentSkill = useThreadStore((state) => state.currentSkill);
  const activeSkill = useThreadStore((state) => state.activeSkill);
  const isSkillSelectionPending = useThreadStore(
    (state) => state.isSkillSelectionPending
  );
  const chatError = useThreadStore((state) => state.error);
  const threadId = useThreadStore((state) => state.threadId);
  const currentThreadSummary = useThreadStore(
    (state) => state.currentThreadSummary
  );
  const threadStatuses = useThreadStore((state) => state.threadStatuses);
  const ensureWorkspaceThread = useThreadStore(
    (state) => state.ensureWorkspaceThread
  );
  const abortStream = useThreadStore((state) => state.abortStream);
  const sendMessage = useThreadStore((state) => state.sendMessage);
  const setCurrentSkill = useThreadStore((state) => state.setCurrentSkill);
  const summary = useDashboardStore((state) => state.summary);
  const fetchDashboard = useDashboardStore((state) => state.fetchDashboard);
  const executionSessions = useExecutionStore(
    (state) => state.byWorkspace[workspaceId] ?? EMPTY_EXECUTION_SESSIONS
  );
  const activeExecutionId = useExecutionStore(
    (state) => state.activeExecutionIdByWorkspace[workspaceId] ?? null
  );
  const dismissedExecutionIds = useExecutionStore(
    (state) =>
      state.dismissedExecutionIdsByWorkspace[workspaceId] ?? EMPTY_EXECUTION_IDS
  );
  const workspace = useWorkspaceStore((state) => state.workspace);
  const artifacts = useWorkspaceStore((state) => state.artifacts);
  const fetchPapers = useWorkspaceStore((state) => state.fetchPapers);
  const fetchArtifacts = useWorkspaceStore((state) => state.fetchArtifacts);
  const getFeatureById = useFeaturesStore((state) => state.getFeatureById);
  const getSkillById = useFeaturesStore((state) => state.getSkillById);
  const skills = useFeaturesStore((state) => state.skills);
  const [inputValue, setInputValue] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [selectedReasoningEffort, setSelectedReasoningEffort] = useState<ReasoningEffort | null>(() => {
    if (typeof window === "undefined") {
      return null;
    }
    try {
      const persisted = window.localStorage.getItem(
        `workspace:${workspaceId}:model:thread:reasoning-effort`
      );
      return isReasoningEffort(persisted) ? persisted : null;
    } catch {
      return null;
    }
  });
  const [defaultUploadKind, setDefaultUploadKind] = useState<ThreadUploadKind>("transient");
  const [pendingAttachments, setPendingAttachments] = useState<PendingThreadAttachment[]>([]);
  const [statusExpanded, setStatusExpanded] = useState(false);
  const {
    models: availableModels,
    selectedModel,
    setSelectedModel,
  } = useModelSelection({
    purpose: "chat",
    persistenceKey: `workspace:${workspaceId}:model:thread`,
  });
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const attachmentInputRef = useRef<HTMLInputElement>(null);
  const appliedEntrySeedKeyRef = useRef<string | null>(null);
  const selectedModelDefinition =
    availableModels.find((candidate) => candidate.name === selectedModel) ?? null;
  const supportsReasoningEffort = selectedModelDefinition?.supports_reasoning_effort ?? false;
  const reasoningPersistenceKey = `workspace:${workspaceId}:model:thread:reasoning-effort`;
  const entrySeedFeature = entrySeed?.featureId
    ? getFeatureById(entrySeed.featureId)
    : undefined;
  const resolvedEntrySkillId = useMemo(
    () => entrySeedFeature?.defaultSkillId
      ?? resolveWorkspaceThreadEntrySkill({
        seed: entrySeed,
        skills,
      }),
    [entrySeed, entrySeedFeature?.defaultSkillId, skills]
  );
  const activeSkillLabel = useMemo(() => {
    const skillId = activeSkill || currentSkill;
    if (!skillId) {
      return null;
    }
    const currentThreadStatus = threadId ? threadStatuses[threadId] ?? null : null;
    return (
      (currentThreadStatus?.current_skill === skillId
        ? currentThreadStatus.current_skill_name
        : null) ||
      (currentThreadSummary?.skill === skillId
        ? currentThreadSummary.skill_name
        : null) ||
      getSkillById(skillId)?.name ||
      skillId
    );
  }, [
    activeSkill,
    currentSkill,
    currentThreadSummary?.skill,
    currentThreadSummary?.skill_name,
    getSkillById,
    threadId,
    threadStatuses,
  ]);
  const activeExecution = useMemo<ExecutionSession | null>(
    () =>
      executionSessions.find((execution) => execution.id === activeExecutionId) ??
      executionSessions.find(
        (execution) =>
          !dismissedExecutionIds.includes(execution.id) &&
          (execution.status === "running" ||
            execution.status === "pending" ||
            execution.status === "awaiting_user_input")
      ) ??
      executionSessions.find(
        (execution) => !dismissedExecutionIds.includes(execution.id)
      ) ??
      executionSessions[0] ??
      null,
    [activeExecutionId, dismissedExecutionIds, executionSessions]
  );
  const executionRuntime = activeExecution?.runtime_snapshot;
  const executionPhaseTitle =
    executionRuntime &&
    typeof executionRuntime === "object" &&
    typeof executionRuntime.title === "string"
      ? executionRuntime.title
      : activeExecution?.feature_id
        ? getFeatureById(activeExecution.feature_id)?.name ?? activeExecution.feature_id
        : null;
  const executionCurrentPhase =
    executionRuntime &&
    typeof executionRuntime === "object" &&
    Array.isArray(executionRuntime.phases)
      ? executionRuntime.phases.find(
          (phase) =>
            phase &&
            typeof phase === "object" &&
            phase.id === executionRuntime.current_phase
        )
      : null;
  const executionNextAction =
    Array.isArray(activeExecution?.next_actions) && activeExecution?.next_actions.length > 0
      ? activeExecution.next_actions[0]
      : null;
  const currentPhaseTitle =
    executionPhaseTitle ||
    summary?.current_phase.title ||
    (entrySeed?.featureId
      ? getFeatureById(entrySeed.featureId)?.name
      : null) ||
    "继续当前主线";
  const currentPhaseDescription =
    (executionCurrentPhase &&
    typeof executionCurrentPhase === "object" &&
    typeof executionCurrentPhase.description === "string"
      ? executionCurrentPhase.description
      : null) ||
    summary?.current_phase.description ||
    (entrySeed?.featureId
      ? "已根据入口上下文预置本次工作目标。"
      : "从当前阶段开始，告诉问津你要推进什么。");
  const nextStepAction =
    executionNextAction && typeof executionNextAction === "object"
      ? {
          title:
            typeof executionNextAction.label === "string"
              ? executionNextAction.label
              : "继续当前执行",
          description: null,
          reason:
            typeof activeExecution?.result_summary === "string"
              ? activeExecution.result_summary
              : null,
        }
      : summary?.next_step ?? null;

  useEffect(() => {
    if (!workspaceId) {
      return;
    }
    void fetchDashboard(workspaceId);
  }, [fetchDashboard, workspaceId]);

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
      return;
    }

    if (appliedEntrySeedKeyRef.current === nextSeedKey) {
      return;
    }
    if (!entrySeed) {
      return;
    }

    if (
      entrySeed.featureId !== "__onboarding__" &&
      entrySeed.skillId == null &&
      skills.length === 0
    ) {
      return;
    }

    appliedEntrySeedKeyRef.current = nextSeedKey;

    // For onboarding or passive open actions, don't auto-send.
    // The system prompt already has workspace-type-specific guidance, and
    // passive card actions should not accidentally relaunch executions.
    const isOnboarding = entrySeed.featureId === "__onboarding__";
    const entryAction =
      typeof entrySeed.params?.entry === "string"
        ? entrySeed.params.entry.trim().toLowerCase()
        : "";
    const isPassiveEntry = entryAction === "open" || entryAction === "view";
    if (isOnboarding || isPassiveEntry) {
      return;
    }

    // For real feature entries, auto-send the entry prompt.
    const prompt = buildWorkspaceThreadEntryPrompt({
      seed: entrySeed,
      feature: entrySeedFeature ?? null,
    });
    sendMessage(prompt, {
      workspaceId,
      ...(resolvedEntrySkillId !== null
        ? { skill: resolvedEntrySkillId }
        : isSkillSelectionPending
          ? { skill: currentSkill }
          : {}),
      model: selectedModel || undefined,
      metadata: {
        orchestration: {
          intent: "launch",
          feature_id: entrySeed.featureId,
          params: entrySeed.params,
        },
      },
    });
  }, [
    currentSkill,
    entrySeed,
    entrySeedFeature,
    isSkillSelectionPending,
    resolvedEntrySkillId,
    selectedModel,
    sendMessage,
    skills.length,
    workspaceId,
  ]);

  useEffect(() => {
    if (!activeSkill || skills.length === 0) {
      return;
    }
    const isSupported = skills.some((skill) => skill.id === activeSkill);
    if (!isSupported) {
      setCurrentSkill(null, workspaceId);
    }
  }, [skills, activeSkill, setCurrentSkill, workspaceId]);

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
      const currentThreadWorkspaceId =
        currentThreadSummary?.workspace_id ?? null;
      let activeThreadId: string | undefined =
        currentThreadWorkspaceId === workspaceId ? threadId || undefined : undefined;
      let uploadedAttachments: ThreadAttachment[] = [];

      if (pendingAttachments.length > 0) {
        if (!activeThreadId) {
          const ensuredThreadId = await ensureWorkspaceThread(workspaceId, {
            model: selectedModel || undefined,
            skill: activeSkill,
          });
          if (!ensuredThreadId) {
            throw new Error("无法初始化当前工作区对话主线");
          }
          activeThreadId = ensuredThreadId;
        }

        const grouped = pendingAttachments.reduce(
          (map, attachment) => {
            const existing = map.get(attachment.kind) ?? [];
            existing.push(attachment.file);
            map.set(attachment.kind, existing);
            return map;
          },
          new Map<ThreadUploadKind, File[]>()
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
      const continuationMetadata = resolveContinuationMetadata(messages);
      sendMessage(content, {
        workspaceId,
        model: selectedModel || undefined,
        reasoningEffort: supportsReasoningEffort ? selectedReasoningEffort ?? "minimal" : undefined,
        threadId: activeThreadId,
        attachments: uploadedAttachments,
        ...(isSkillSelectionPending ? { skill: currentSkill } : {}),
        ...(continuationMetadata ? { metadata: continuationMetadata } : {}),
      });
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
    kind: ThreadUploadKind
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
      <WorkspaceThreadHeader
        workspaceName={workspace?.name}
        currentThreadSummary={currentThreadSummary}
        messages={messages}
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

          {activeSkillLabel ? (
            <span className="rounded-full border border-[var(--accent-primary)]/18 bg-[var(--accent-primary)]/8 px-2 py-0.5 text-[10px] font-medium text-[var(--accent-primary)]">
              {activeSkillLabel}
            </span>
          ) : null}

          {/* Stats */}
          <span className="text-xs text-[var(--text-muted)]">
            产出 {artifacts.length}
          </span>

          {/* Right side: recommendation + toggle */}
          <div className="ml-auto flex items-center gap-2">
            {nextStepAction ? (
              <span className="max-w-[320px] truncate text-xs text-[var(--text-secondary)]">
                建议：{nextStepAction.title}
              </span>
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
          <div className="mt-3 rounded-2xl border border-[var(--border-default)] bg-white/76 p-4">
            <p className="text-sm font-medium text-[var(--text-primary)]">
              {currentPhaseTitle}
            </p>
            <p className="mt-2 text-xs leading-6 text-[var(--text-secondary)]">
              {summary?.headline || currentPhaseDescription}
            </p>
            <div className="mt-3 border-t border-[var(--border-default)] pt-3">
              <p className="text-xs font-medium text-[var(--text-primary)]">下一步建议</p>
              <p className="mt-1 text-xs leading-6 text-[var(--text-secondary)]">
                {nextStepAction?.reason ||
                  nextStepAction?.description ||
                  "直接描述你要推进的步骤，问津会通过对话确认后再决定是否开始执行。"}
              </p>
            </div>
          </div>
        ) : null}
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        <WorkspaceThreadMessages
          workspaceId={workspaceId}
          messages={messages}
          isStreaming={isStreaming}
          isThreadLoading={isThreadLoading}
          workspaceName={workspace?.name}
        />
        <div ref={messagesEndRef} />
      </div>

      <WorkspaceThreadComposer
        workspaceId={workspaceId}
        actionError={composerError}
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
        onAbortStream={abortStream}
      />
    </div>
  );
}
