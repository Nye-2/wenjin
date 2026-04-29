"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  ClipboardCheck,
  Cpu,
  ExternalLink,
  FileText,
  FolderOpen,
  GitBranch,
  Layers3,
  Loader2,
  RotateCcw,
  Terminal,
} from "lucide-react";

import { LatexFileChangeDiffPreview } from "@/components/latex/LatexFileChangeDiffPreview";
import { TaskRuntimePanel } from "@/components/workspace/TaskRuntimePanel";
import {
  applyLatexFileChange,
  discardLatexFileChange,
  previewLatexFileChange,
  revertLatexFileChange,
} from "@/lib/api";
import type {
  ComputeFileProjection,
  ComputeLogProjection,
  ComputePrismProjection,
  ComputeProjection,
  ComputeReviewGateProjection,
  ComputeSession,
  ExecutionSession,
  LatexFileChangePreviewResponse,
} from "@/lib/api";
import type {
  TaskRuntimeBlock,
  TaskRuntimePhase,
  TaskRuntimeState,
} from "@/lib/task-runtime";
import { cn } from "@/lib/utils";
import { useComputeStore } from "@/stores/compute";

const EMPTY_COMPUTE_SESSIONS: ComputeSession[] = [];

interface ComputeStageProps {
  workspaceId: string;
  activeExecution: ExecutionSession | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function readString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function readNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function readFileChangeKey(value: Record<string, unknown>): string | null {
  return readString(value.logical_key);
}

function isRunningStatus(status?: string | null): boolean {
  return ["launching", "pending", "running", "awaiting_user_input"].includes(
    String(status || "")
  );
}

function statusLabel(status?: string | null): string {
  switch (status) {
    case "launching":
      return "启动中";
    case "pending":
      return "排队中";
    case "running":
      return "运行中";
    case "awaiting_user_input":
      return "等待补充";
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
    case "advisory":
      return "需处理";
    default:
      return status || "未知";
  }
}

function sandboxStatusLabel(status?: string | null): string {
  switch (status) {
    case "bound":
      return "已绑定";
    case "derived":
      return "已发现";
    case "required":
      return "需绑定";
    case "unbound":
      return "未绑定";
    default:
      return status || "未知";
  }
}

function reviewStatusLabel(status?: string | null): string {
  switch (status) {
    case "clear":
      return "无阻塞";
    case "awaiting_user":
      return "待确认";
    case "advisory":
      return "有建议";
    case "failed":
      return "失败";
    default:
      return status || "未知";
  }
}

function prismStatusLabel(status?: string | null): string {
  switch (status) {
    case "ready":
      return "已关联";
    case "pending_changes":
      return "待确认写入";
    case "compile_failed":
      return "编译失败";
    case "unbound":
      return "未关联";
    default:
      return status || "未知";
  }
}

function fileLabel(file: ComputeFileProjection): string {
  return (
    readString(file.artifact_id) ??
    readString(file.label) ??
    readString(file.path)?.split("/").filter(Boolean).at(-1) ??
    readString(file.url) ??
    "file"
  );
}

function fileMeta(file: ComputeFileProjection): string {
  const source = readString(file.source) ?? "compute";
  const kind = readString(file.kind) ?? "file";
  return `${kind} · ${source}`;
}

function logToneClass(level?: string | null): string {
  switch (level) {
    case "success":
      return "border-emerald-500/20 bg-emerald-500/8 text-emerald-700";
    case "warning":
      return "border-amber-500/20 bg-amber-500/8 text-amber-700";
    case "error":
      return "border-red-500/20 bg-red-500/8 text-red-700";
    default:
      return "border-[var(--border-default)] bg-[var(--bg-elevated)] text-[var(--text-secondary)]";
  }
}

function reviewTone(gate: ComputeReviewGateProjection | null): "default" | "success" | "warning" | "danger" {
  if (!gate) {
    return "default";
  }
  if (gate.status === "clear") {
    return "success";
  }
  if (gate.status === "failed") {
    return "danger";
  }
  return gate.required ? "warning" : "default";
}

function prismTone(prism: ComputePrismProjection | null): "default" | "success" | "warning" | "danger" {
  if (!prism || prism.status === "unbound") {
    return "default";
  }
  if (prism.status === "ready") {
    return "success";
  }
  if (prism.status === "compile_failed") {
    return "danger";
  }
  return "warning";
}

function normalizePhase(value: unknown): TaskRuntimePhase | null {
  if (!isRecord(value)) {
    return null;
  }
  const id = readString(value.id);
  const label = readString(value.label) ?? readString(value.title) ?? id;
  if (!id || !label) {
    return null;
  }
  const rawStatus = readString(value.status);
  const status: TaskRuntimePhase["status"] =
    rawStatus === "completed" ||
    rawStatus === "running" ||
    rawStatus === "failed" ||
    rawStatus === "pending"
      ? rawStatus
      : "pending";
  const progress = readNumber(value.progress);
  return {
    id,
    label,
    description: readString(value.description) ?? undefined,
    status,
    progress: progress === null ? undefined : Math.max(0, Math.min(100, progress)),
  };
}

function normalizeBlock(value: unknown): TaskRuntimeBlock | null {
  if (!isRecord(value)) {
    return null;
  }
  const id = readString(value.id);
  const title = readString(value.title);
  const kind = readString(value.kind);
  if (!id || !title) {
    return null;
  }

  const base = {
    id,
    phase_id: readString(value.phase_id) ?? undefined,
    title,
    description: readString(value.description) ?? undefined,
  };
  if (kind === "metrics" && Array.isArray(value.entries)) {
    return {
      ...base,
      kind,
      entries: value.entries
        .filter(isRecord)
        .map((entry) => ({
          label: readString(entry.label) ?? "Metric",
          value: String(entry.value ?? ""),
        })),
    };
  }
  if (kind === "activity" && Array.isArray(value.items)) {
    return {
      ...base,
      kind,
      items: value.items
        .filter(isRecord)
        .map((item) => ({
          title: readString(item.title) ?? "Activity",
          description: readString(item.description) ?? undefined,
          tone:
            item.tone === "success" ||
            item.tone === "warning" ||
            item.tone === "danger" ||
            item.tone === "info"
              ? item.tone
              : undefined,
          timestamp: readString(item.timestamp) ?? undefined,
        })),
    };
  }
  if (kind === "text") {
    return {
      ...base,
      kind,
      content: readString(value.content) ?? "",
    };
  }
  if (Array.isArray(value.items)) {
    return {
      ...base,
      kind: "list",
      items: value.items
        .filter(isRecord)
        .map((item) => ({
          title: readString(item.title) ?? "Item",
          description: readString(item.description) ?? undefined,
          meta: readString(item.meta) ?? undefined,
          badge: readString(item.badge),
        })),
    };
  }
  return null;
}

function buildRuntimeState(
  projection: ComputeProjection | null,
  execution: ExecutionSession | null
): TaskRuntimeState | null {
  const runtimeSnapshot = projection?.execution.runtime_snapshot ?? execution?.runtime_snapshot;
  const snapshot = isRecord(runtimeSnapshot) ? runtimeSnapshot : {};
  const projectedBlocks = projection?.runtime_blocks ?? [];
  const snapshotBlocks = Array.isArray(snapshot.blocks) ? snapshot.blocks : [];
  const blocks = (projectedBlocks.length > 0 ? projectedBlocks : snapshotBlocks)
    .map(normalizeBlock)
    .filter((block): block is TaskRuntimeBlock => block !== null);
  const phases = (Array.isArray(snapshot.phases) ? snapshot.phases : [])
    .map(normalizePhase)
    .filter((phase): phase is TaskRuntimePhase => phase !== null);
  const primaryTask = projection?.primary_task;
  const taskMessage = isRecord(primaryTask)
    ? readString(primaryTask.message) ?? readString(primaryTask.status)
    : null;

  if (phases.length === 0 && blocks.length === 0 && !projection && !execution) {
    return null;
  }

  const title =
    readString(snapshot.title) ??
    execution?.feature_id ??
    projection?.execution.feature_id ??
    "Compute";
  return {
    title,
    current_phase: readString(snapshot.current_phase) ?? undefined,
    phases,
    blocks:
      blocks.length > 0
        ? blocks
        : taskMessage
          ? [
              {
                id: "compute-task-message",
                kind: "text",
                title: "当前说明",
                content: taskMessage,
              },
            ]
          : [],
    updated_at: projection?.compute_session.updated_at ?? execution?.updated_at ?? undefined,
  };
}

function formatShortId(value?: string | null): string {
  return value ? value.slice(0, 8) : "N/A";
}

function SummaryItem({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "success" | "warning" | "danger";
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border px-3 py-3",
        tone === "success"
          ? "border-emerald-500/20 bg-emerald-500/8"
          : tone === "warning"
            ? "border-amber-500/20 bg-amber-500/8"
            : tone === "danger"
              ? "border-red-500/20 bg-red-500/8"
              : "border-[var(--border-default)] bg-white/78"
      )}
    >
      <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
        {label}
      </p>
      <p className="mt-1 truncate text-sm font-medium text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
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
  const subagents = projection?.subagents ?? [];
  const tasks = projection?.tasks ?? [];
  const sandbox = projection?.sandbox ?? null;
  const runtimeProfile = projection?.runtime_profile ?? null;
  const prism = projection?.prism ?? null;
  const files = projection?.files ?? sandbox?.files ?? [];
  const logs = projection?.logs ?? sandbox?.logs ?? [];
  const reviewGate = projection?.review_gate ?? null;
  const reviewItems = reviewGate?.items ?? [];
  const artifactIds = Array.isArray(projection?.artifacts?.ids)
    ? projection?.artifacts.ids.filter((item): item is string => typeof item === "string")
    : effectiveExecution?.artifact_ids ?? [];
  const nextActions = Array.isArray(reviewGate?.next_actions)
    ? reviewGate.next_actions
    : effectiveExecution?.next_actions ?? [];

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
      <div className="border-b border-[var(--border-default)] px-4 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Cpu className="h-4 w-4 text-[var(--accent-primary)]" />
              <h3 className="truncate text-base font-semibold text-[var(--text-primary)]">
                {effectiveExecution?.feature_id ?? "Compute Session"}
              </h3>
            </div>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">
              {computeSession
                ? `Compute ${formatShortId(computeSession.id)} · Execution ${formatShortId(computeSession.execution_session_id)}`
                : "等待 Compute session 绑定"}
            </p>
          </div>
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
              effectiveExecution?.status === "completed"
                ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-700"
                : effectiveExecution?.status === "failed"
                  ? "border-red-500/25 bg-red-500/10 text-red-700"
                  : "border-[var(--accent-primary)]/25 bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]"
            )}
          >
            {effectiveExecution?.status === "completed" ? (
              <CheckCircle2 className="h-3.5 w-3.5" />
            ) : effectiveExecution?.status === "failed" ? (
              <AlertCircle className="h-3.5 w-3.5" />
            ) : isLoadingProjection ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <GitBranch className="h-3.5 w-3.5" />
            )}
            {statusLabel(effectiveExecution?.status)}
          </span>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
          <SummaryItem
            label="Task"
            value={formatShortId(effectiveExecution?.primary_task_id)}
          />
          <SummaryItem label="Subagents" value={String(subagents.length)} />
          <SummaryItem
            label="Sandbox"
            value={sandboxStatusLabel(sandbox?.status)}
            tone={
              sandbox?.status === "bound"
                ? "success"
                : sandbox?.required
                  ? "warning"
                  : "default"
            }
          />
          <SummaryItem
            label="Prism"
            value={prismStatusLabel(prism?.status)}
            tone={prismTone(prism)}
          />
          <SummaryItem label="Files" value={String(files.length)} />
          <SummaryItem label="Logs" value={String(logs.length)} />
          <SummaryItem
            label="Review"
            value={
              reviewGate
                ? reviewStatusLabel(reviewGate.status)
                : nextActions.length > 0
                  ? `${nextActions.length} actions`
                  : "None"
            }
            tone={reviewTone(reviewGate)}
          />
        </div>
      </div>

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
          <section className="rounded-2xl border border-[var(--border-default)] bg-white/78 p-4">
            <div className="flex items-center gap-2">
              <Layers3 className="h-4 w-4 text-[var(--accent-primary)]" />
              <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                子代理
              </h4>
            </div>
            <div className="mt-3 space-y-2">
              {subagents.length > 0 ? (
                subagents.slice(0, 8).map((subagent) => (
                  <div
                    key={String(subagent.task_id)}
                    className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                        {String(subagent.subagent_type || "subagent")}
                      </p>
                      <span className="shrink-0 text-[11px] text-[var(--text-muted)]">
                        {String(subagent.status || "unknown")}
                      </span>
                    </div>
                    {readString(subagent.output_preview) ? (
                      <p className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--text-secondary)]">
                        {readString(subagent.output_preview)}
                      </p>
                    ) : null}
                  </div>
                ))
              ) : (
                <p className="rounded-xl border border-dashed border-[var(--border-default)] px-3 py-4 text-center text-xs text-[var(--text-muted)]">
                  当前执行未启动子代理。
                </p>
              )}
            </div>
          </section>

          <section className="rounded-2xl border border-[var(--border-default)] bg-white/78 p-4">
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-[var(--accent-primary)]" />
              <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                任务与产物
              </h4>
            </div>
            <div className="mt-3 space-y-2">
              {tasks.slice(0, 5).map((task) => (
                <div
                  key={String(task.task_id)}
                  className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                      {formatShortId(readString(task.task_id))}
                    </p>
                    <span className="shrink-0 text-[11px] text-[var(--text-muted)]">
                      {String(task.status || "unknown")}
                    </span>
                  </div>
                  {readString(task.message) ? (
                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--text-secondary)]">
                      {readString(task.message)}
                    </p>
                  ) : null}
                </div>
              ))}
              {tasks.length === 0 ? (
                <p className="rounded-xl border border-dashed border-[var(--border-default)] px-3 py-4 text-center text-xs text-[var(--text-muted)]">
                  当前 Compute projection 暂无任务记录。
                </p>
              ) : null}
              {artifactIds.length > 0 ? (
                <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2">
                  <p className="text-xs font-medium text-[var(--text-primary)]">
                    Artifact IDs
                  </p>
                  <p className="mt-1 line-clamp-3 text-[11px] leading-5 text-[var(--text-muted)]">
                    {artifactIds.join(", ")}
                  </p>
                </div>
              ) : null}
            </div>
          </section>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-4">
          <section className="rounded-2xl border border-[var(--border-default)] bg-white/78 p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <BookOpen className="h-4 w-4 text-[var(--accent-primary)]" />
                <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                  WenjinPrism
                </h4>
              </div>
              <span
                className={cn(
                  "shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium",
                  prism?.status === "ready"
                    ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-700"
                    : prism?.status === "compile_failed"
                      ? "border-red-500/25 bg-red-500/10 text-red-700"
                      : prism?.status === "pending_changes"
                        ? "border-amber-500/25 bg-amber-500/10 text-amber-700"
                        : "border-[var(--border-default)] bg-[var(--bg-elevated)] text-[var(--text-secondary)]"
                )}
              >
                {prismStatusLabel(prism?.status)}
              </span>
            </div>
            {readString(prism?.project_id) ? (
              <div className="mt-3 rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                      {formatShortId(readString(prism?.project_id))}
                    </p>
                    <p className="mt-0.5 truncate text-[11px] text-[var(--text-muted)]">
                      {readString(prism?.main_file) ?? "main.tex"}
                    </p>
                  </div>
                  {readString(prism?.url) ? (
                    <a
                      href={readString(prism?.url) ?? undefined}
                      target="_blank"
                      rel="noreferrer"
                      className="shrink-0 rounded-md border border-[var(--border-default)] p-1.5 text-[var(--text-secondary)] hover:border-[var(--accent-primary)] hover:text-[var(--accent-primary)]"
                      title="打开 WenjinPrism"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  ) : null}
                </div>
              </div>
            ) : (
              <p className="mt-3 rounded-xl border border-dashed border-[var(--border-default)] px-3 py-4 text-center text-xs text-[var(--text-muted)]">
                当前执行未关联 WenjinPrism 主稿工程。
              </p>
            )}

            {prism?.target_files?.length ? (
              <div className="mt-3 space-y-1.5">
                {prism.target_files.slice(0, 5).map((path) => (
                  <p
                    key={path}
                    className="truncate rounded-lg bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[11px] text-[var(--text-secondary)]"
                  >
                    {path}
                  </p>
                ))}
              </div>
            ) : null}

            {prism?.compile?.status ? (
              <p className="mt-3 truncate text-[11px] text-[var(--text-muted)]">
                Compile: {prism.compile.status}
                {typeof prism.compile.page_count === "number"
                  ? ` · ${prism.compile.page_count} pages`
                  : ""}
              </p>
            ) : null}

            {prism?.file_changes?.length ? (
              <div className="mt-3 rounded-xl border border-amber-500/20 bg-amber-500/8 px-3 py-2">
                <p className="text-xs font-medium text-amber-800">
                  Prism 待确认写入 {prism.file_changes.length}
                </p>
                <p className="mt-1 line-clamp-2 text-[11px] leading-5 text-amber-800/80">
                  {prism.file_changes
                    .map((item) => readString(item.path) ?? readString(item.logical_key))
                    .filter(Boolean)
                    .slice(0, 3)
                    .join(", ")}
                </p>
                <div className="mt-2 space-y-2">
                  {prism.file_changes.slice(0, 3).map((change) => {
                    const logicalKey = readFileChangeKey(change);
                    const isResolving =
                      logicalKey !== null && resolvingPrismFileChangeKey === logicalKey;
                    const isPreviewing =
                      logicalKey !== null && previewingPrismFileChangeKey === logicalKey;
                    const preview = logicalKey
                      ? prismFileChangePreviewByKey[logicalKey] ?? null
                      : null;
                    return (
                      <div
                        key={logicalKey ?? readString(change.path) ?? "file-change"}
                        className="rounded-lg bg-white/60 px-2.5 py-2"
                      >
                        <p className="truncate text-[11px] font-medium text-amber-900">
                          {readString(change.path) ??
                            readString(change.logical_key) ??
                            "未命名写入"}
                        </p>
                        <p className="mt-1 truncate text-[10px] text-amber-900/65">
                          {readString(change.reason) ?? "feature_proposal"}
                        </p>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <button
                            type="button"
                            disabled={!logicalKey || isResolving || isPreviewing}
                            onClick={() => {
                              void handlePreviewPrismFileChange(change);
                            }}
                            className="rounded-md border border-amber-500/25 bg-white/70 px-2 py-1 text-[11px] font-medium text-amber-900 hover:border-amber-500/50 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {isPreviewing
                              ? "预览中..."
                              : preview
                                ? "刷新 diff"
                                : "预览 diff"}
                          </button>
                          <button
                            type="button"
                            disabled={!logicalKey || isResolving}
                            onClick={() => {
                              void handlePrismFileChange(change, "discard");
                            }}
                            className="rounded-md border border-amber-500/25 bg-white/70 px-2 py-1 text-[11px] font-medium text-amber-900 hover:border-amber-500/50 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            忽略本次
                          </button>
                          <button
                            type="button"
                            disabled={!logicalKey || isResolving}
                            onClick={() => {
                              void handlePrismFileChange(change, "apply");
                            }}
                            className="rounded-md border border-amber-500/25 bg-amber-500/10 px-2 py-1 text-[11px] font-medium text-amber-900 hover:border-amber-500/50 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            应用到 Prism
                          </button>
                        </div>
                        {preview ? (
                          <LatexFileChangeDiffPreview
                            preview={preview}
                            maxOps={4}
                            className="mt-2"
                          />
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : null}

            {prism?.applied_file_changes?.length ? (
              <div className="mt-3 rounded-xl border border-emerald-500/20 bg-emerald-500/8 px-3 py-2">
                <p className="text-xs font-medium text-emerald-800">
                  已写入 Prism {prism.applied_file_changes.length}
                </p>
                <div className="mt-2 space-y-2">
                  {prism.applied_file_changes.slice(0, 3).map((change) => {
                    const logicalKey = readFileChangeKey(change);
                    const revertSignature = readString(change.revert_signature);
                    const isReverting =
                      logicalKey !== null && revertingPrismFileChangeKey === logicalKey;
                    return (
                      <div
                        key={logicalKey ?? readString(change.path) ?? "applied-file-change"}
                        className="rounded-lg bg-white/60 px-2.5 py-2"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="truncate text-[11px] font-medium text-emerald-900">
                              {readString(change.path) ??
                                readString(change.logical_key) ??
                                "未命名写入"}
                            </p>
                            <p className="mt-1 truncate text-[10px] text-emerald-900/65">
                              {readString(change.applied_hash) ?? "applied"}
                            </p>
                          </div>
                          <button
                            type="button"
                            disabled={!logicalKey || !revertSignature || isReverting}
                            onClick={() => {
                              void handleRevertPrismFileChange(change);
                            }}
                            className="inline-flex shrink-0 items-center gap-1 rounded-md border border-emerald-500/25 bg-white/70 px-2 py-1 text-[11px] font-medium text-emerald-900 hover:border-emerald-500/50 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            <RotateCcw className="h-3 w-3" />
                            {isReverting ? "撤回中..." : "撤回"}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : null}
          </section>

          <section className="rounded-2xl border border-[var(--border-default)] bg-white/78 p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <FolderOpen className="h-4 w-4 text-[var(--accent-primary)]" />
                <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                  Sandbox 文件
                </h4>
              </div>
              <span className="shrink-0 text-[11px] text-[var(--text-muted)]">
                {sandboxStatusLabel(sandbox?.status)}
              </span>
            </div>
            {readString(sandbox?.session_id) ? (
              <p className="mt-2 truncate text-[11px] text-[var(--text-muted)]">
                {readString(sandbox?.session_id)}
              </p>
            ) : null}
            {sandbox?.required && !readString(sandbox?.session_id) ? (
              <p className="mt-2 rounded-lg border border-amber-500/20 bg-amber-500/10 px-2.5 py-2 text-[11px] text-amber-800">
                当前 feature runtime profile 要求 sandbox；等待执行环境绑定或产出文件。
              </p>
            ) : null}
            <div className="mt-3 space-y-2">
              {files.length > 0 ? (
                files.slice(0, 8).map((file) => {
                  const label = fileLabel(file);
                  const url = readString(file.url);
                  const path = readString(file.path);
                  return (
                    <div
                      key={file.id}
                      className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                            {label}
                          </p>
                          <p className="mt-0.5 truncate text-[11px] text-[var(--text-muted)]">
                            {fileMeta(file)}
                          </p>
                        </div>
                        {url ? (
                          <a
                            href={url}
                            target="_blank"
                            rel="noreferrer"
                            className="shrink-0 rounded-md border border-[var(--border-default)] p-1.5 text-[var(--text-secondary)] hover:border-[var(--accent-primary)] hover:text-[var(--accent-primary)]"
                            title="打开文件"
                          >
                            <ExternalLink className="h-3.5 w-3.5" />
                          </a>
                        ) : null}
                      </div>
                      {path && path !== label ? (
                        <p className="mt-1 line-clamp-2 break-all text-[11px] leading-5 text-[var(--text-secondary)]">
                          {path}
                        </p>
                      ) : null}
                    </div>
                  );
                })
              ) : (
                <p className="rounded-xl border border-dashed border-[var(--border-default)] px-3 py-4 text-center text-xs text-[var(--text-muted)]">
                  当前执行没有发布 sandbox 文件。
                </p>
              )}
            </div>
          </section>

          <section className="rounded-2xl border border-[var(--border-default)] bg-white/78 p-4">
            <div className="flex items-center gap-2">
              <Terminal className="h-4 w-4 text-[var(--accent-primary)]" />
              <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                执行日志
              </h4>
            </div>
            <div className="mt-3 space-y-2">
              {logs.length > 0 ? (
                logs.slice(0, 8).map((log: ComputeLogProjection) => (
                  <div
                    key={log.id}
                    className={cn(
                      "rounded-xl border px-3 py-2",
                      logToneClass(log.level)
                    )}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                        {log.title}
                      </p>
                      <span className="shrink-0 text-[11px]">
                        {log.level}
                      </span>
                    </div>
                    <p className="mt-1 line-clamp-4 whitespace-pre-wrap text-xs leading-5">
                      {log.message}
                    </p>
                    {readString(log.timestamp) ? (
                      <p className="mt-1 truncate text-[11px] text-[var(--text-muted)]">
                        {readString(log.timestamp)}
                      </p>
                    ) : null}
                  </div>
                ))
              ) : (
                <p className="rounded-xl border border-dashed border-[var(--border-default)] px-3 py-4 text-center text-xs text-[var(--text-muted)]">
                  当前执行还没有结构化日志。
                </p>
              )}
            </div>
          </section>

          <section className="rounded-2xl border border-[var(--border-default)] bg-white/78 p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <ClipboardCheck className="h-4 w-4 text-[var(--accent-primary)]" />
                <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                  Review Gate
                </h4>
              </div>
              <span
                className={cn(
                  "shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium",
                  reviewGate?.status === "clear"
                    ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-700"
                    : reviewGate?.status === "failed"
                      ? "border-red-500/25 bg-red-500/10 text-red-700"
                      : reviewGate?.required
                        ? "border-amber-500/25 bg-amber-500/10 text-amber-700"
                        : "border-[var(--border-default)] bg-[var(--bg-elevated)] text-[var(--text-secondary)]"
                )}
              >
                {reviewStatusLabel(reviewGate?.status)}
              </span>
            </div>
            {readString(reviewGate?.advisory_code) ? (
              <p className="mt-2 truncate text-[11px] text-[var(--text-muted)]">
                {readString(reviewGate?.advisory_code)}
              </p>
            ) : null}
            {readString(reviewGate?.policy ?? runtimeProfile?.review_gate) ? (
              <p className="mt-2 truncate text-[11px] text-[var(--text-muted)]">
                Policy: {readString(reviewGate?.policy ?? runtimeProfile?.review_gate)}
              </p>
            ) : null}
            <div className="mt-3 space-y-2">
              {reviewItems.length > 0 ? (
                reviewItems.map((item) => (
                  <div
                    key={item.id}
                    className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                        {item.label}
                      </p>
                      <span className="shrink-0 text-[11px] text-[var(--text-muted)]">
                        {item.required ? "required" : item.kind}
                      </span>
                    </div>
                    {readString(item.kind) && item.required ? (
                      <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                        {item.kind}
                      </p>
                    ) : null}
                  </div>
                ))
              ) : (
                <p className="rounded-xl border border-dashed border-[var(--border-default)] px-3 py-4 text-center text-xs text-[var(--text-muted)]">
                  当前没有等待处理的 review action。
                </p>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
