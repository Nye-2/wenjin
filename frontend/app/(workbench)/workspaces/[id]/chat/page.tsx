"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import {
  useParams,
  usePathname,
  useRouter,
  useSearchParams,
} from "next/navigation";

import {
  uploadThreadFiles,
  type ThreadAttachment,
  type ThreadUploadKind,
  type ReasoningEffort,
} from "@/lib/api";
import { useModelSelection } from "@/hooks/useModelSelection";
import { useThreadStore } from "@/stores/thread";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeaturesStore } from "@/stores/features";
import { ChatThread } from "../components/chat-thread/ChatThread";
import { LiveWorkflowPanel } from "../components/live-workflow/LiveWorkflowPanel";
import { WorkspaceThreadHeader } from "../components/WorkspaceThreadHeader";
import {
  isReasoningEffort,
  WorkspaceThreadComposer,
} from "../components/WorkspaceThreadComposer";
import { ArtifactDetailDialog } from "@/components/workspace/ArtifactDetailDialog";
import {
  buildWorkspaceThreadEntryPrompt,
  parseWorkspaceThreadEntrySeed,
  resolveWorkspaceThreadEntrySkill,
  type WorkspaceThreadEntrySeed,
} from "@/lib/workspace-thread-entry";
import { toChatMessages } from "@/stores/thread-store-support";

interface PendingThreadAttachment {
  id: string;
  file: File;
  kind: ThreadUploadKind;
}

function deriveStarterPrompts(
  feature: ReturnType<typeof useFeaturesStore.getState>["features"][number] | null,
  skill: ReturnType<typeof useFeaturesStore.getState>["skills"][number] | null,
): string[] {
  const src = (skill?.guidancePrompt ?? feature?.followUpPrompt ?? "") as string;
  return src
    .split(/\n+/)
    .map((line) => line.trim())
    .filter((line) => line.startsWith("- ") || line.startsWith("• "))
    .slice(0, 3)
    .map((line) => line.replace(/^[-•]\s+/, ""));
}

function ChatPageInner() {
  const params = useParams<{ id: string }>();
  const workspaceId = params?.id ?? "";
  const router = useRouter();
  const pathname = usePathname() ?? "";
  const searchParams = useSearchParams();
  const searchParamString = searchParams?.toString() ?? "";
  const skillFromUrl = searchParams?.get("skill") ?? null;
  const isOnboarding = searchParams?.get("onboarding") === "true";
  const artifactIdFromUrl = searchParams?.get("artifact") ?? null;

  const workspace = useWorkspaceStore((state) => state.workspace);
  const artifacts = useWorkspaceStore((state) => state.artifacts);
  const fetchReferences = useWorkspaceStore((state) => state.fetchReferences);
  const fetchArtifacts = useWorkspaceStore((state) => state.fetchArtifacts);

  const messages = useThreadStore((state) => state.messages);
  const isStreaming = useThreadStore((state) => state.isStreaming);
  const currentSkill = useThreadStore((state) => state.currentSkill);
  const activeSkill = useThreadStore((state) => state.activeSkill);
  const isSkillSelectionPending = useThreadStore(
    (state) => state.isSkillSelectionPending,
  );
  const chatError = useThreadStore((state) => state.error);
  const threadId = useThreadStore((state) => state.threadId);
  const currentThreadSummary = useThreadStore(
    (state) => state.currentThreadSummary,
  );
  const isWorkspaceThreadLoading = useThreadStore(
    (state) => state.isWorkspaceThreadLoading,
  );
  const ensureWorkspaceThread = useThreadStore(
    (state) => state.ensureWorkspaceThread,
  );
  const sendMessage = useThreadStore((state) => state.sendMessage);
  const abortStream = useThreadStore((state) => state.abortStream);
  const setCurrentSkill = useThreadStore((state) => state.setCurrentSkill);

  const features = useFeaturesStore((state) => state.features);
  const skills = useFeaturesStore((state) => state.skills);
  const getFeatureById = useFeaturesStore((state) => state.getFeatureById);

  const entrySeedRaw: WorkspaceThreadEntrySeed | null = useMemo(
    () => (searchParams ? parseWorkspaceThreadEntrySeed(searchParams) : null),
    [searchParams],
  );
  const entrySeed: WorkspaceThreadEntrySeed | null = useMemo(() => {
    if (entrySeedRaw) return entrySeedRaw;
    if (isOnboarding && workspace) {
      return {
        featureId: "__onboarding__",
        skillId: null,
        params: { __onboarding_type: workspace.type },
      };
    }
    return null;
  }, [entrySeedRaw, isOnboarding, workspace]);

  const selectedArtifact = useMemo(
    () => artifacts.find((a) => a.id === artifactIdFromUrl) ?? null,
    [artifacts, artifactIdFromUrl],
  );
  const isArtifactDialogOpen = Boolean(artifactIdFromUrl && selectedArtifact);

  const handleArtifactDialogClose = (open: boolean) => {
    if (!open && artifactIdFromUrl) {
      const nextParams = new URLSearchParams(searchParamString);
      nextParams.delete("artifact");
      const nextQuery = nextParams.toString();
      const nextUrl = nextQuery ? `${pathname}?${nextQuery}` : pathname;
      router.replace(nextUrl, { scroll: false });
    }
  };

  const initializedSelectionRef = useRef<string | null>(null);
  const cleanedQueryKeyRef = useRef<string | null>(null);
  const appliedEntrySeedKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!workspaceId || isWorkspaceThreadLoading) return;
    const selectionKey = `${workspaceId}:__single_thread__`;
    if (initializedSelectionRef.current === selectionKey) return;

    if (skillFromUrl && skillFromUrl !== activeSkill) {
      setCurrentSkill(skillFromUrl, workspaceId);
    }

    let cancelled = false;
    const initialize = async () => {
      initializedSelectionRef.current = selectionKey;
      await ensureWorkspaceThread(workspaceId, { skill: skillFromUrl });
      if (cancelled) return;
    };
    void initialize();
    return () => {
      cancelled = true;
    };
  }, [
    activeSkill,
    ensureWorkspaceThread,
    isWorkspaceThreadLoading,
    setCurrentSkill,
    skillFromUrl,
    workspaceId,
  ]);

  useEffect(() => {
    if (!workspaceId || isWorkspaceThreadLoading) return;
    const selectionKey = `${workspaceId}:__single_thread__`;
    if (initializedSelectionRef.current !== selectionKey) return;
    if (!searchParamString.includes("thread=")) return;

    const cleanKey = `${workspaceId}:${searchParamString}`;
    if (cleanedQueryKeyRef.current === cleanKey) return;

    const nextParams = new URLSearchParams(searchParamString);
    if (!nextParams.has("thread")) return;
    nextParams.delete("thread");
    const nextQuery = nextParams.toString();
    const currentUrl = searchParamString
      ? `${pathname}?${searchParamString}`
      : pathname;
    const nextUrl = nextQuery ? `${pathname}?${nextQuery}` : pathname;
    if (nextUrl === currentUrl) return;

    cleanedQueryKeyRef.current = cleanKey;
    router.replace(nextUrl, { scroll: false });
  }, [
    isWorkspaceThreadLoading,
    pathname,
    router,
    searchParamString,
    workspaceId,
  ]);

  const entrySeedFeature = entrySeed?.featureId
    ? getFeatureById(entrySeed.featureId)
    : undefined;
  const resolvedEntrySkillId = useMemo(
    () =>
      entrySeedFeature?.defaultSkillId ??
      resolveWorkspaceThreadEntrySkill({ seed: entrySeed, skills }),
    [entrySeed, entrySeedFeature?.defaultSkillId, skills],
  );

  const [inputValue, setInputValue] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [selectedReasoningEffort, setSelectedReasoningEffort] =
    useState<ReasoningEffort | null>(() => {
      if (typeof window === "undefined") return null;
      try {
        const persisted = window.localStorage.getItem(
          `workspace:${workspaceId}:model:thread:reasoning-effort`,
        );
        return isReasoningEffort(persisted) ? persisted : null;
      } catch {
        return null;
      }
    });
  const [defaultUploadKind, setDefaultUploadKind] =
    useState<ThreadUploadKind>("transient");
  const [pendingAttachments, setPendingAttachments] = useState<
    PendingThreadAttachment[]
  >([]);
  const {
    models: availableModels,
    selectedModel,
    setSelectedModel,
  } = useModelSelection({
    purpose: "chat",
    persistenceKey: `workspace:${workspaceId}:model:thread`,
  });
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const attachmentInputRef = useRef<HTMLInputElement>(null);
  const selectedModelDefinition =
    availableModels.find((c) => c.name === selectedModel) ?? null;
  const supportsReasoningEffort =
    selectedModelDefinition?.supports_reasoning_effort ?? false;
  const reasoningPersistenceKey = `workspace:${workspaceId}:model:thread:reasoning-effort`;

  // entrySeed auto-send (ported from ThreadPanel)
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
    if (appliedEntrySeedKeyRef.current === nextSeedKey) return;
    if (!entrySeed) return;

    if (
      entrySeed.featureId !== "__onboarding__" &&
      entrySeed.skillId == null &&
      skills.length === 0
    ) {
      return;
    }

    appliedEntrySeedKeyRef.current = nextSeedKey;

    const isOnboardingEntry = entrySeed.featureId === "__onboarding__";
    const entryAction =
      typeof entrySeed.params?.entry === "string"
        ? entrySeed.params.entry.trim().toLowerCase()
        : "";
    const isPassiveEntry = entryAction === "open" || entryAction === "view";
    if (isOnboardingEntry || isPassiveEntry) return;

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
    if (!activeSkill || skills.length === 0) return;
    const isSupported = skills.some((s) => s.id === activeSkill);
    if (!isSupported) setCurrentSkill(null, workspaceId);
  }, [skills, activeSkill, setCurrentSkill, workspaceId]);

  useEffect(() => {
    if (
      typeof window === "undefined" ||
      !supportsReasoningEffort ||
      !selectedReasoningEffort
    ) {
      return;
    }
    try {
      window.localStorage.setItem(
        reasoningPersistenceKey,
        selectedReasoningEffort,
      );
    } catch {
      // Ignore localStorage failures.
    }
  }, [
    reasoningPersistenceKey,
    selectedReasoningEffort,
    supportsReasoningEffort,
  ]);

  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
      inputRef.current.style.height = `${Math.min(
        inputRef.current.scrollHeight,
        200,
      )}px`;
    }
  }, [inputValue]);

  const submitText = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || isStreaming) return;
    sendMessage(trimmed, {
      workspaceId,
      model: selectedModel || undefined,
      reasoningEffort: supportsReasoningEffort
        ? selectedReasoningEffort ?? "minimal"
        : undefined,
      threadId: threadId ?? undefined,
      ...(isSkillSelectionPending ? { skill: currentSkill } : {}),
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isStreaming) return;

    let content = inputValue.trim();
    if (!content) {
      if (pendingAttachments.length > 0) {
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
        currentThreadWorkspaceId === workspaceId
          ? threadId || undefined
          : undefined;
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
          new Map<ThreadUploadKind, File[]>(),
        );

        const uploadResults = await Promise.all(
          Array.from(grouped.entries()).map(([kind, files]) =>
            uploadThreadFiles({
              threadId: activeThreadId as string,
              kind,
              workspaceId,
              files,
            }),
          ),
        );
        uploadedAttachments = uploadResults.flatMap((result) => result.files);
        const refreshJobs: Promise<void>[] = [];
        if (uploadedAttachments.some((a) => a.reference_id)) {
          refreshJobs.push(fetchReferences(workspaceId));
        }
        if (uploadedAttachments.some((a) => a.artifact_id)) {
          refreshJobs.push(fetchArtifacts(workspaceId));
        }
        await Promise.allSettled(refreshJobs);
      }

      setInputValue("");
      setPendingAttachments([]);
      sendMessage(content, {
        workspaceId,
        model: selectedModel || undefined,
        reasoningEffort: supportsReasoningEffort
          ? selectedReasoningEffort ?? "minimal"
          : undefined,
        threadId: activeThreadId,
        attachments: uploadedAttachments,
        ...(isSkillSelectionPending ? { skill: currentSkill } : {}),
      });
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "附件上传失败",
      );
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSubmit(e);
    }
  };

  const handleOpenFilePicker = () => attachmentInputRef.current?.click();

  const handleSelectFiles = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    if (files.length === 0) return;
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
      current.filter((a) => a.id !== attachmentId),
    );
  };

  const handleUpdateAttachmentKind = (
    attachmentId: string,
    kind: ThreadUploadKind,
  ) => {
    setPendingAttachments((current) =>
      current.map((a) => (a.id === attachmentId ? { ...a, kind } : a)),
    );
  };

  const composerError = actionError ?? chatError;
  const chatMessages = useMemo(() => toChatMessages(messages), [messages]);
  const feature = entrySeed?.featureId
    ? features.find((f) => f.id === entrySeed.featureId) ?? null
    : null;
  const skill = entrySeed?.skillId
    ? skills.find((s) => s.id === entrySeed.skillId) ?? null
    : null;
  const featureMeta = feature
    ? { id: feature.id, name: feature.name, description: feature.description }
    : null;
  const starterPrompts = useMemo(
    () => deriveStarterPrompts(feature, skill),
    [feature, skill],
  );

  return (
    <div className="flex h-full flex-col overflow-hidden p-4 sm:p-6 atmosphere-mesh">
      <input
        ref={attachmentInputRef}
        type="file"
        multiple
        accept=".pdf,image/*"
        className="hidden"
        onChange={handleSelectFiles}
      />

      <div className="grid h-full min-h-0 grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(430px,520px)]">
        <div className="chat-container flex min-h-0 flex-col overflow-hidden rounded-[1.75rem]">
          <WorkspaceThreadHeader
            workspaceName={workspace?.name}
            currentThreadSummary={currentThreadSummary}
            messages={messages}
          />
          <div className="flex-1 min-h-0">
            <ChatThread
              workspaceId={workspaceId}
              messages={chatMessages}
              feature={featureMeta}
              starterPrompts={starterPrompts}
              onSubmit={submitText}
              inputArea={
                <WorkspaceThreadComposer
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
                  pendingAttachments={pendingAttachments.map((a) => ({
                    id: a.id,
                    name: a.file.name,
                    size: a.file.size,
                    kind: a.kind,
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
              }
            />
          </div>
        </div>
        <div className="min-h-0 overflow-hidden rounded-[1.75rem]">
          <LiveWorkflowPanel workspaceId={workspaceId} />
        </div>
      </div>

      <ArtifactDetailDialog
        artifact={selectedArtifact}
        open={isArtifactDialogOpen}
        onOpenChange={handleArtifactDialogClose}
      />
    </div>
  );
}

export default function ChatPage() {
  return (
    <Suspense>
      <ChatPageInner />
    </Suspense>
  );
}
