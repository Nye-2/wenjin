"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { WorkspaceProjectStatusStrip } from "./WorkspaceProjectStatusStrip";
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
import { useComputeStore } from "@/stores/compute";
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
import { ACTIVE_EXECUTION_STATUSES } from "@/lib/execution-status";

interface ThreadPanelProps {
  workspaceId: string;
  entrySeed?: WorkspaceThreadEntrySeed | null;
}

interface PendingThreadAttachment {
  id: string;
  file: File;
  kind: ThreadUploadKind;
}

function hasUserInputAction(execution: ExecutionSession): boolean {
  return execution.next_actions.some((action) => {
    const kind = typeof action.kind === "string" ? action.kind.trim() : "";
    const actionName =
      typeof action.action === "string" ? action.action.trim() : "";
    return kind === "user_input_required" || actionName === "user_input_required";
  });
}

function buildFeatureResumeMetadata(
  execution: ExecutionSession | null
): Record<string, unknown> | null {
  if (!execution) {
    return null;
  }
  const status = execution.status.trim();
  if (status !== "awaiting_user_input" && !hasUserInputAction(execution)) {
    return null;
  }

  const featureId = execution.feature_id.trim();
  const executionSessionId = execution.id.trim();
  if (!featureId || !executionSessionId) {
    return null;
  }

  return {
    orchestration: {
      intent: "resume",
      feature_id: featureId,
      execution_session_id: executionSessionId,
      status: "awaiting_user_input",
      params: execution.params,
    },
  };
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
  const fetchReferences = useWorkspaceStore((state) => state.fetchReferences);
  const fetchArtifacts = useWorkspaceStore((state) => state.fetchArtifacts);
  const getFeatureById = useFeaturesStore((state) => state.getFeatureById);
  const getSkillById = useFeaturesStore((state) => state.getSkillById);
  const skills = useFeaturesStore((state) => state.skills);
  const computeSessions = useComputeStore(
    (state) => state.byWorkspace[workspaceId] ?? EMPTY_EXECUTION_SESSIONS
  );
  const projections = useComputeStore((state) => state.projectionBySessionId);
  const activeComputeSessionId = useComputeStore(
    (state) => state.activeComputeSessionIdByWorkspace[workspaceId] ?? null
  );
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
          ACTIVE_EXECUTION_STATUSES.has(execution.status as never)
      ) ??
      executionSessions.find(
        (execution) => !dismissedExecutionIds.includes(execution.id)
      ) ??
      executionSessions[0] ??
      null,
    [activeExecutionId, dismissedExecutionIds, executionSessions]
  );
  const computeSession = useMemo(() => {
    if (activeExecution) {
      const matched = computeSessions.find(
        (session) => session.execution_session_id === activeExecution.id
      );
      if (matched) {
        return matched;
      }
    }
    return (
      computeSessions.find((session) => session.id === activeComputeSessionId) ??
      computeSessions[0] ??
      null
    );
  }, [activeExecution, activeComputeSessionId, computeSessions]);
  const projection = computeSession ? projections[computeSession.id] ?? null : null;
  const prism = projection?.prism ?? null;
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
    const isResumeEntry = entryAction === "resume";
    const executionSessionId =
      typeof entrySeed.params?.execution_session_id === "string"
        ? entrySeed.params.execution_session_id.trim()
        : null;
    const orchestrationParams = Object.fromEntries(
      Object.entries(entrySeed.params ?? {}).filter(
        ([key]) => key !== "entry" && key !== "execution_session_id"
      )
    );
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
          intent: isResumeEntry ? "resume" : "launch",
          feature_id: entrySeed.featureId,
          ...(isResumeEntry && executionSessionId
            ? { execution_session_id: executionSessionId }
            : {}),
          params: orchestrationParams,
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

    let content = inputValue.trim();
    if (!content) {
      if (pendingAttachments.length > 0) {
        // Allow attachment-only send with a default message
        content = "请阅读这些附件，并结合上下文继续分析。";
      } else {
        setActionError("请输入消息内容。");
        return;
      }
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
        if (uploadedAttachments.some((attachment) => attachment.reference_id)) {
          refreshJobs.push(fetchReferences(workspaceId));
        }
        if (uploadedAttachments.some((attachment) => attachment.artifact_id)) {
          refreshJobs.push(fetchArtifacts(workspaceId));
        }
        await Promise.allSettled(refreshJobs);
      }

      setInputValue("");
      setPendingAttachments([]);
      const continuationMetadata = buildFeatureResumeMetadata(activeExecution);
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
        accept=".pdf,image/*"
        className="hidden"
        onChange={handleSelectFiles}
      />
      <WorkspaceThreadHeader
        workspaceName={workspace?.name}
        currentThreadSummary={currentThreadSummary}
        messages={messages}
      />

      <WorkspaceProjectStatusStrip
        currentPhaseTitle={currentPhaseTitle}
        currentPhaseDescription={currentPhaseDescription}
        headline={summary?.headline ?? null}
        activeSkillLabel={activeSkillLabel}
        artifactsCount={artifacts.length}
        activeExecution={activeExecution}
        nextStepAction={nextStepAction}
        prismPendingChanges={Array.isArray(prism?.file_changes) ? prism.file_changes.length : 0}
        prismAppliedChanges={Array.isArray(prism?.applied_file_changes) ? prism.applied_file_changes.length : 0}
      />

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
