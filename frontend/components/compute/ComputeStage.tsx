"use client";

import { useEffect, useMemo, useState } from "react";
import { Cpu } from "lucide-react";

import { TaskRuntimePanel } from "@/components/workspace/TaskRuntimePanel";
import {
  applyLatexFileChange,
  discardLatexFileChange,
  previewLatexFileChange,
  revertLatexFileChange,
} from "@/lib/api";
import type {
  ComputeSession,
  ExecutionSession,
  LatexFileChangePreviewResponse,
} from "@/lib/api";
import { useComputeStore } from "@/stores/compute";

import { ComputeHeader } from "./ComputeHeader";
import { SubagentPanel } from "./SubagentPanel";
import { TaskArtifactPanel } from "./TaskArtifactPanel";
import { PrismPanel } from "./PrismPanel";
import { SandboxFilePanel } from "./SandboxFilePanel";
import { LogPanel } from "./LogPanel";
import { ReviewGatePanel } from "./ReviewGatePanel";
import {
  buildRuntimeState,
  isRunningStatus,
  readFileChangeKey,
  readString,
  statusLabel,
} from "./utils";

const EMPTY_COMPUTE_SESSIONS: ComputeSession[] = [];

interface ComputeStageProps {
  workspaceId: string;
  activeExecution: ExecutionSession | null;
}

export function ComputeStage({ workspaceId, activeExecution }: ComputeStageProps) {
  const [resolvingPrismFileChangeKey, setResolvingPrismFileChangeKey] = useState<
    string | null
  >(null);
  const [previewingPrismFileChangeKey, setPreviewingPrismFileChangeKey] = useState<
    string | null
  >(null);
  const [revertingPrismFileChangeKey, setRevertingPrismFileChangeKey] = useState<
    string | null
  >(null);
  const [
    prismFileChangePreviewByKey,
    setPrismFileChangePreviewByKey,
  ] = useState<Record<string, LatexFileChangePreviewResponse>>({});

  const computeSessions = useComputeStore(
    (state) => state.byWorkspace[workspaceId] ?? EMPTY_COMPUTE_SESSIONS
  );
  const activeComputeSessionId = useComputeStore(
    (state) => state.activeComputeSessionIdByWorkspace[workspaceId] ?? null
  );
  const projections = useComputeStore((state) => state.projectionBySessionId);
  const isProjectionLoadingBySessionId = useComputeStore(
    (state) => state.isProjectionLoadingBySessionId
  );
  const hydrateWorkspace = useComputeStore((state) => state.hydrateWorkspace);
  const fetchProjection = useComputeStore((state) => state.fetchProjection);
  const setActiveComputeSession = useComputeStore(
    (state) => state.setActiveComputeSession
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
  }, [activeComputeSessionId, activeExecution, computeSessions]);

  const projection = computeSession ? projections[computeSession.id] ?? null : null;
  const runtimeState = useMemo(
    () => buildRuntimeState(projection, activeExecution),
    [activeExecution, projection]
  );
  const effectiveExecution = projection?.execution ?? activeExecution;
  const isLoadingProjection =
    Boolean(computeSession) &&
    Boolean(isProjectionLoadingBySessionId[computeSession?.id ?? ""]);

  const sandbox = projection?.sandbox ?? null;
  const prism = projection?.prism ?? null;
  const runtimeProfile = projection?.runtime_profile ?? null;
  const files = projection?.files ?? sandbox?.files ?? [];
  const logs = projection?.logs ?? sandbox?.logs ?? [];
  const reviewGate = projection?.review_gate ?? null;
  const subagents = projection?.subagents ?? [];
  const tasks = projection?.tasks ?? [];
  const artifactIds = Array.isArray(projection?.artifacts?.ids)
    ? projection?.artifacts.ids.filter((item): item is string => typeof item === "string")
    : effectiveExecution?.artifact_ids ?? [];

  const handlePrismFileChange = async (
    change: Record<string, unknown>,
    action: "discard" | "apply"
  ) => {
    const projectId = readString(prism?.project_id);
    const logicalKey = readFileChangeKey(change);
    if (!projectId || !logicalKey || !computeSession) {
      return;
    }
    setResolvingPrismFileChangeKey(logicalKey);
    try {
      if (action === "apply") {
        const preview =
          prismFileChangePreviewByKey[logicalKey] ??
          (await previewLatexFileChange(projectId, {
            logical_key: logicalKey,
          }));
        await applyLatexFileChange(projectId, {
          logical_key: logicalKey,
          change_signature: preview.change_signature,
        });
      } else {
        await discardLatexFileChange(projectId, {
          logical_key: logicalKey,
        });
      }
      await fetchProjection(computeSession.id);
      setPrismFileChangePreviewByKey((prev) => {
        const next = { ...prev };
        delete next[logicalKey];
        return next;
      });
    } finally {
      setResolvingPrismFileChangeKey(null);
    }
  };

  const handlePreviewPrismFileChange = async (change: Record<string, unknown>) => {
    const projectId = readString(prism?.project_id);
    const logicalKey = readFileChangeKey(change);
    if (!projectId || !logicalKey) {
      return;
    }
    setPreviewingPrismFileChangeKey(logicalKey);
    try {
      const preview = await previewLatexFileChange(projectId, {
        logical_key: logicalKey,
      });
      setPrismFileChangePreviewByKey((prev) => ({
        ...prev,
        [logicalKey]: preview,
      }));
    } finally {
      setPreviewingPrismFileChangeKey(null);
    }
  };

  const handleRevertPrismFileChange = async (change: Record<string, unknown>) => {
    const projectId = readString(prism?.project_id);
    const logicalKey = readFileChangeKey(change);
    const revertSignature = readString(change.revert_signature);
    if (!projectId || !logicalKey || !revertSignature || !computeSession) {
      return;
    }
    setRevertingPrismFileChangeKey(logicalKey);
    try {
      await revertLatexFileChange(projectId, {
        logical_key: logicalKey,
        revert_signature: revertSignature,
      });
      await fetchProjection(computeSession.id);
      setPrismFileChangePreviewByKey((prev) => {
        const next = { ...prev };
        delete next[logicalKey];
        return next;
      });
    } finally {
      setRevertingPrismFileChangeKey(null);
    }
  };

  useEffect(() => {
    if (!workspaceId) {
      return;
    }
    if (computeSessions.length === 0 && activeExecution) {
      void hydrateWorkspace(workspaceId);
    }
  }, [activeExecution, computeSessions.length, hydrateWorkspace, workspaceId]);

  useEffect(() => {
    if (!computeSession) {
      return;
    }
    if (activeComputeSessionId !== computeSession.id) {
      setActiveComputeSession(workspaceId, computeSession.id);
      return;
    }
    if (!projection) {
      void fetchProjection(computeSession.id);
    }
  }, [
    activeComputeSessionId,
    computeSession,
    fetchProjection,
    projection,
    setActiveComputeSession,
    workspaceId,
  ]);

  if (!activeExecution && !computeSession) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <div className="max-w-sm text-center">
          <Cpu className="mx-auto h-8 w-8 text-[var(--text-muted)]" />
          <h3 className="mt-3 text-sm font-semibold text-[var(--text-primary)]">
            Compute 工作面
          </h3>
          <p className="mt-2 text-xs leading-6 text-[var(--text-secondary)]">
            启动 feature 后，这里会展开运行时、sandbox、日志和 review gate。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-[rgba(251,248,242,0.72)]">
      <ComputeHeader
        effectiveExecution={effectiveExecution}
        computeSession={computeSession}
        projection={projection}
        isLoadingProjection={isLoadingProjection}
      />

      <div className="min-h-0 flex-1 overflow-auto p-4">
        <TaskRuntimePanel
          runtime={runtimeState}
          isRunning={isRunningStatus(effectiveExecution?.status)}
          status={
            isLoadingProjection
              ? "正在加载 Compute projection"
              : statusLabel(effectiveExecution?.status)
          }
          error={effectiveExecution?.last_error ?? null}
          title="Compute Runtime"
          emptyTitle="Compute Runtime"
          emptyDescription="当前执行还没有发布运行时块。"
          className="rounded-2xl"
        />

        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          <SubagentPanel subagents={subagents} />
          <TaskArtifactPanel tasks={tasks} artifactIds={artifactIds} />
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-4">
          <PrismPanel
            prism={prism}
            resolvingKey={resolvingPrismFileChangeKey}
            previewingKey={previewingPrismFileChangeKey}
            revertingKey={revertingPrismFileChangeKey}
            previewByKey={prismFileChangePreviewByKey}
            onPreview={handlePreviewPrismFileChange}
            onApply={(change) => void handlePrismFileChange(change, "apply")}
            onDiscard={(change) => void handlePrismFileChange(change, "discard")}
            onRevert={handleRevertPrismFileChange}
          />
          <SandboxFilePanel files={files} sandbox={sandbox} />
          <LogPanel logs={logs} />
          <ReviewGatePanel reviewGate={reviewGate} runtimeProfile={runtimeProfile} />
        </div>
      </div>
    </div>
  );
}
