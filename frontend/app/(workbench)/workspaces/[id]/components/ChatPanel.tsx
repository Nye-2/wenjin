"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import {
  uploadThreadFiles,
  type ChatAttachment,
  type ChatUploadKind,
  type ReasoningEffort,
} from "@/lib/api";
import { useModelSelection } from "@/hooks/useModelSelection";
import { useChatStore } from "@/stores/chat";
import { useDashboardStore } from "@/stores/dashboard";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeaturesStore } from "@/stores/features";
import { WorkspaceChatMessages } from "./WorkspaceChatMessages";
import {
  isReasoningEffort,
  WorkspaceChatComposer,
} from "./WorkspaceChatComposer";
import { WorkspaceChatHeader } from "./WorkspaceChatHeader";
import {
  buildWorkspaceChatEntryPrompt,
  resolveWorkspaceChatEntrySkill,
  type WorkspaceChatEntrySeed,
} from "@/lib/workspace-chat-entry";

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
  const {
    messages,
    isStreaming,
    isThreadLoading,
    currentSkill,
    activeSkill,
    isSkillSelectionPending,
    error: chatError,
    threadId,
    currentThreadSummary,
    ensureWorkspaceThread,
    abortStream,
    sendMessage,
    setCurrentSkill,
  } = useChatStore();
  const summary = useDashboardStore((state) => state.summary);
  const fetchDashboard = useDashboardStore((state) => state.fetchDashboard);
  const { workspace, artifacts } = useWorkspaceStore();
  const fetchPapers = useWorkspaceStore((state) => state.fetchPapers);
  const fetchArtifacts = useWorkspaceStore((state) => state.fetchArtifacts);
  const { getFeatureById } = useFeaturesStore();
  const skills = useFeaturesStore((state) => state.skills);
  const [inputValue, setInputValue] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [selectedReasoningEffort, setSelectedReasoningEffort] = useState<ReasoningEffort | null>(() => {
    if (typeof window === "undefined") {
      return null;
    }
    try {
      const persisted = window.localStorage.getItem(
        `workspace:${workspaceId}:model:chat:reasoning-effort`
      );
      return isReasoningEffort(persisted) ? persisted : null;
    } catch {
      return null;
    }
  });
  const [defaultUploadKind, setDefaultUploadKind] = useState<ChatUploadKind>("transient");
  const [pendingAttachments, setPendingAttachments] = useState<PendingChatAttachment[]>([]);
  const [statusExpanded, setStatusExpanded] = useState(false);
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
  const selectedModelDefinition =
    availableModels.find((candidate) => candidate.name === selectedModel) ?? null;
  const supportsReasoningEffort = selectedModelDefinition?.supports_reasoning_effort ?? false;
  const reasoningPersistenceKey = `workspace:${workspaceId}:model:chat:reasoning-effort`;
  const entrySeedFeature = entrySeed?.featureId
    ? getFeatureById(entrySeed.featureId)
    : undefined;
  const resolvedEntrySkillId = useMemo(
    () => entrySeedFeature?.defaultSkillId
      ?? resolveWorkspaceChatEntrySkill({
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
    return skills.find((skill) => skill.id === skillId)?.name || skillId;
  }, [activeSkill, currentSkill, skills]);
  const currentPhaseTitle =
    summary?.current_phase.title ||
    (entrySeed?.featureId
      ? getFeatureById(entrySeed.featureId)?.name
      : null) ||
    "继续当前主线";
  const currentPhaseDescription =
    summary?.current_phase.description ||
    (entrySeed?.featureId
      ? "已根据入口上下文预置本次工作目标。"
      : "从当前阶段开始，告诉问津你要推进什么。");
  const nextStepAction = summary?.next_step ?? null;

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

    // For onboarding, don't auto-send — let the user type their own first message.
    // The system prompt already has workspace-type-specific guidance.
    const isOnboarding = entrySeed.featureId === "__onboarding__";
    if (isOnboarding) {
      return;
    }

    // For real feature entries, auto-send the entry prompt.
    const prompt = buildWorkspaceChatEntryPrompt({
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
      setCurrentSkill(null);
    }
  }, [skills, activeSkill, setCurrentSkill]);

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
      let activeThreadId: string | undefined = threadId || undefined;
      let uploadedAttachments: ChatAttachment[] = [];

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
        model: selectedModel || undefined,
        reasoningEffort: supportsReasoningEffort ? selectedReasoningEffort ?? "minimal" : undefined,
        threadId: activeThreadId,
        attachments: uploadedAttachments,
        ...(isSkillSelectionPending ? { skill: currentSkill } : {}),
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
        <WorkspaceChatMessages
          messages={messages}
          isStreaming={isStreaming}
          isThreadLoading={isThreadLoading}
          workspaceName={workspace?.name}
        />
        <div ref={messagesEndRef} />
      </div>

      <WorkspaceChatComposer
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
