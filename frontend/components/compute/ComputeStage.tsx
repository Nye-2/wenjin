"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
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

import { ComputeStageSkeleton } from "@/components/ui/skeleton";
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

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.06,
      delayChildren: 0.1,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 12 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.35,
      ease: [0.16, 1, 0.3, 1] as const,
    },
  },
};

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
      <div className="compute-bg flex h-full items-center justify-center p-6">
        <div className="max-w-sm text-center">
          <Cpu className="mx-auto h-8 w-8 text-compute-text-muted" />
          <h3 className="mt-3 text-sm font-semibold text-compute-text-primary">
            Agent 工作现场
          </h3>
          <p className="mt-2 text-xs leading-6 text-compute-text-secondary">
            启动任务后，这里会展示 Agent 的工作过程，不需要你手动操作。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="compute-bg flex h-full min-h-0 flex-col overflow-hidden">
      <ComputeHeader
        effectiveExecution={effectiveExecution}
        computeSession={computeSession}
        projection={projection}
        isLoadingProjection={isLoadingProjection}
      />

      {isLoadingProjection ? (
        <ComputeStageSkeleton />
      ) : (
        <motion.div
        className="min-h-0 flex-1 overflow-auto p-4"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        key={computeSession?.id ?? "empty"}
      >
        <motion.div variants={itemVariants}>
          <TaskRuntimePanel
            runtime={runtimeState}
            isRunning={isRunningStatus(effectiveExecution?.status)}
            status={
              isLoadingProjection
                ? "正在加载工作现场"
                : statusLabel(effectiveExecution?.status)
            }
            error={effectiveExecution?.last_error ?? null}
            title="Agent 运行时"
            emptyTitle="Agent 运行时"
            emptyDescription="当前执行还没有发布运行时块。"
            className="rounded-2xl"
          />
        </motion.div>

        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          <motion.div variants={itemVariants}>
            <SubagentPanel subagents={subagents} />
          </motion.div>
          <motion.div variants={itemVariants}>
            <TaskArtifactPanel tasks={tasks} artifactIds={artifactIds} />
          </motion.div>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-4">
          <motion.div variants={itemVariants}>
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
          </motion.div>
          <motion.div variants={itemVariants}>
            <SandboxFilePanel files={files} sandbox={sandbox} />
          </motion.div>
          <motion.div variants={itemVariants}>
            <LogPanel logs={logs} />
          </motion.div>
          <motion.div variants={itemVariants}>
            <ReviewGatePanel reviewGate={reviewGate} runtimeProfile={runtimeProfile} />
          </motion.div>
        </div>
      </motion.div>
      )}
    </div>
  );
}
