"use client";

import {
  Archive,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  CircleDot,
  Clock3,
  Download,
  FileText,
  History,
  LoaderCircle,
  Maximize2,
  MessageCircle,
  Minimize2,
  Paperclip,
  RefreshCw,
  RotateCcw,
  Search,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { MarkdownRenderer } from "@/components/ui/markdown-renderer";
import { StatusPill } from "@/components/ui/status-pill";
import { TypeChip, resolveMaterialType } from "@/components/ui/type-chip";
import {
  commitMissionReviews,
  decideMissionReviews,
  downloadMissionArtifact,
  getMissionReviewPreview,
  listMissionArtifacts,
  listMissionEvidence,
  listMissionItems,
  listMissionReviews,
  resolveMissionPermission,
  updateMissionReviewMode,
  type MissionMutationResult,
} from "@/lib/api/missions";
import type {
  MissionArtifactView,
  MissionEvidenceView,
  MissionItem,
  MissionReviewItemView,
  MissionReviewMode,
  MissionView,
} from "@/lib/api/mission-types";
import {
  defaultMissionSurface,
  formatMissionDuration,
  missionStatusTone,
  suggestedReviewSelection,
} from "@/lib/mission-view";
import { useMissionUiStore } from "@/stores/mission-ui-store";

import { AcademicVisualReviewPreview } from "./AcademicVisualReviewPreview";

interface MissionConsoleProps {
  view: MissionView;
  compact?: boolean;
  onClose(): void;
  onMissionTarget(missionId: string): Promise<boolean>;
  onChatAction(action: MissionChatAction): void;
}

export type MissionChatAction = "focus" | "attach" | "continue";

const EMPTY_REVIEW_SELECTION = new Set<string>();
const MAX_REVIEW_REPLAY_PAGES = 100;

function assertReviewRevision(actual: string, expected: string): void {
  if (actual !== expected) {
    throw new Error("待确认内容刚刚更新，正在同步最新状态");
  }
}

export function MissionConsole({
  view,
  compact = false,
  onClose,
  onMissionTarget,
  onChatAction,
}: MissionConsoleProps) {
  const panelMode = useMissionUiStore((state) => state.panelMode);
  const expandMission = useMissionUiStore((state) => state.expandMission);

  if (panelMode === "peek" && !compact) {
    return (
      <aside
        className="flex h-full min-w-0 flex-col border-l border-[var(--wjn-line)] bg-[var(--wjn-surface)]"
        aria-label="研究任务概览"
        data-testid="mission-console-peek"
      >
        <MissionHeader view={view} onClose={onClose} />
        <MissionStaleNotice view={view} onMissionTarget={onMissionTarget} />
        <button
          type="button"
          className="group flex flex-1 flex-col items-start gap-4 px-5 py-6 text-left hover:bg-[var(--wjn-surface-subtle)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--wjn-accent)]"
          onClick={() => expandMission(view.attentionRequest ? "progress" : defaultMissionSurface(view))}
        >
          <div className="flex w-full items-start gap-3">
            <StatusMark status={view.executionStatus} />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold text-[var(--wjn-text)]">
                {view.attentionRequest?.title ?? view.activity.title}
              </div>
              <p className="mt-1 line-clamp-3 text-sm leading-6 text-[var(--wjn-text-secondary)]">
                {view.attentionRequest?.summary ?? view.activity.summary ?? view.activeStage?.summary ?? "问津正在推进这项研究任务。"}
              </p>
            </div>
          </div>
          <div className="mt-auto flex w-full items-center justify-between border-t border-[var(--wjn-line)] pt-4 text-xs text-[var(--wjn-text-muted)]">
            <span>{view.attentionRequest ? "回复后将从当前进度继续" : activityMeta(view)}</span>
            <span className="flex items-center gap-1 text-[var(--wjn-accent-strong)]">
              展开任务 <ChevronRight size={14} />
            </span>
          </div>
        </button>
      </aside>
    );
  }

  return (
    <aside
      className="flex h-full min-w-0 flex-col bg-[var(--wjn-surface)]"
      aria-label="研究任务"
      data-testid="mission-console"
    >
      <MissionHeader view={view} onClose={onClose} />
      <MissionStaleNotice view={view} onMissionTarget={onMissionTarget} />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <ProgressSurface
          view={view}
          onChatAction={onChatAction}
          onMissionTarget={onMissionTarget}
        />
        <ReviewInlineSection view={view} onMissionTarget={onMissionTarget} />
        <MaterialsFold view={view} />
        <TraceFold view={view} />
      </div>
    </aside>
  );
}

/**
 * 待确认内容：有待处理项时自动展开的处理区，空了则收起为一行。
 * 确认是「事件」而非「页面」。
 */
function ReviewInlineSection({
  view,
  onMissionTarget,
}: {
  view: MissionView;
  onMissionTarget(missionId: string): Promise<boolean>;
}) {
  const pending = view.reviewSummary.pending + view.reviewSummary.needsMoreEvidence;
  const handled = view.reviewSummary.accepted + view.reviewSummary.committed;
  const [open, setOpen] = useState(pending > 0);
  useEffect(() => {
    if (pending > 0) setOpen(true);
  }, [pending]);
  if (pending === 0 && handled === 0) return null;
  return (
    <section
      id="mission-review-section"
      className="border-t border-[var(--wjn-line)] px-5 pb-3 pt-4"
      data-testid="mission-review-inline"
    >
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-center gap-2 text-left text-xs font-semibold text-[var(--wjn-text)]"
      >
        <Check size={14} className={pending > 0 ? "text-[var(--wjn-review)]" : "text-[var(--wjn-text-muted)]"} />
        确认与决定
        {pending > 0 ? (
          <span className="rounded-full bg-[var(--wjn-review-soft)] px-2 py-0.5 text-[10px] font-medium text-[var(--wjn-review)]">
            {pending} 项待你确认
          </span>
        ) : (
          <span className="text-[10px] font-normal text-[var(--wjn-text-muted)]">
            已处理 {handled} 项
          </span>
        )}
        <ChevronDown
          size={14}
          className={`ml-auto text-[var(--wjn-text-muted)] transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open ? (
        <ReviewSurface key={view.missionId} view={view} onMissionTarget={onMissionTarget} />
      ) : null}
    </section>
  );
}

/** 材料与成果：默认收起的排障视图，按需展开。 */
function MaterialsFold({ view }: { view: MissionView }) {
  const [open, setOpen] = useState(false);
  const total = view.evidenceCount + view.artifactCount;
  return (
    <section
      className="border-t border-[var(--wjn-line)] px-5 pb-4 pt-4"
      data-testid="mission-materials-fold"
    >
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-center gap-2 text-left text-xs font-semibold text-[var(--wjn-text)]"
      >
        <BookOpen size={14} className="text-[var(--wjn-text-muted)]" />
        材料与成果
        <span className="text-[10px] font-normal text-[var(--wjn-text-muted)]">
          来源 {view.evidenceCount} · 成果 {view.artifactCount}
        </span>
        <ChevronDown
          size={14}
          className={`ml-auto text-[var(--wjn-text-muted)] transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open ? (
        total > 0 ? (
          <div className="mt-2 space-y-6">
            <div>
              <div className="text-[11px] font-semibold text-[var(--wjn-text-muted)]">来源与结果</div>
              <EvidenceSurface key={`${view.missionId}-evidence`} view={view} />
            </div>
            <div>
              <div className="text-[11px] font-semibold text-[var(--wjn-text-muted)]">成果</div>
              <ArtifactSurface key={`${view.missionId}-artifacts`} view={view} />
            </div>
          </div>
        ) : (
          <p className="mt-3 text-xs text-[var(--wjn-text-muted)]">
            还没有沉淀材料；任务推进后，可查证的来源、数据、图表会汇总在这里。
          </p>
        )
      ) : null}
    </section>
  );
}

/** 轨迹：低频审计视图，默认收起。 */
function TraceFold({ view }: { view: MissionView }) {
  const [open, setOpen] = useState(false);
  return (
    <section
      className="border-t border-[var(--wjn-line)] px-5 pb-5 pt-4"
      data-testid="mission-trace-fold"
    >
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-center gap-2 text-left text-xs font-semibold text-[var(--wjn-text)]"
      >
        <History size={14} className="text-[var(--wjn-text-muted)]" />
        轨迹
        <span className="text-[10px] font-normal text-[var(--wjn-text-muted)]">运行过程审计</span>
        <ChevronDown
          size={14}
          className={`ml-auto text-[var(--wjn-text-muted)] transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open ? <TraceSurface key={view.missionId} view={view} /> : null}
    </section>
  );
}

function MissionStaleNotice({
  view,
  onMissionTarget,
}: {
  view: MissionView;
  onMissionTarget(missionId: string): Promise<boolean>;
}) {
  const [retrying, setRetrying] = useState(false);
  const [retryFailed, setRetryFailed] = useState(false);
  if (!view.isStale && !view.loadError) return null;

  const retry = async () => {
    setRetrying(true);
    setRetryFailed(false);
    try {
      setRetryFailed(!(await onMissionTarget(view.missionId)));
    } catch {
      setRetryFailed(true);
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div className="flex shrink-0 items-center gap-3 border-b border-[var(--wjn-line)] bg-[var(--wjn-review-soft)] px-4 py-2.5" data-testid="mission-stale-notice">
      <div className="min-w-0 flex-1">
        <div className="text-xs font-medium text-[var(--wjn-text)]">当前显示的是上次已加载的任务进度</div>
        <div className="mt-0.5 text-[11px] text-[var(--wjn-text-secondary)]">
          {retryFailed ? "刷新仍未完成，请稍后再试。" : "最新进度暂时未能同步。"}
        </div>
      </div>
      <button type="button" disabled={retrying} onClick={() => void retry()} className="flex h-7 shrink-0 items-center gap-1.5 px-2 text-xs font-medium text-[var(--wjn-accent-strong)] hover:bg-[var(--wjn-surface-subtle)] disabled:opacity-45">
        <RefreshCw size={13} className={retrying ? "animate-spin" : undefined} />
        重试
      </button>
    </div>
  );
}

function MissionActivity({ view }: { view: MissionView }) {
  const operationElapsed = useElapsedTime(view.currentOperation?.startedAt ?? null);
  return (
    <section className="border-l-2 border-[var(--wjn-accent-line)] pl-3" data-testid="mission-activity">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-[var(--wjn-text)]">{view.activity.title}</h3>
        <span className="bg-[var(--wjn-accent-soft)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--wjn-accent-strong)]">
          {activityStateLabel(view.activity.state)}
        </span>
      </div>
      {view.activity.summary ? (
        <p className="mt-1 text-xs leading-5 text-[var(--wjn-text-secondary)]">{view.activity.summary}</p>
      ) : null}
      {view.activity.attempt || view.activity.retryAt || view.activity.state === "collaborating" ? (
        <p className="mt-1 text-[11px] text-[var(--wjn-text-muted)]">{activityMeta(view)}</p>
      ) : null}
      {view.currentOperation ? (
        <div className="mt-3 border-t border-[var(--wjn-line)] pt-3" data-testid="mission-current-operation">
          <div className="flex items-center gap-2 text-xs font-medium text-[var(--wjn-text)]">
            <LoaderCircle size={13} className="animate-spin text-[var(--wjn-accent-strong)]" />
            <span>{view.currentOperation.label}</span>
          </div>
          <p className="mt-1 text-[11px] text-[var(--wjn-text-muted)]">
            {view.currentOperation.actor} · 已运行 {operationElapsed}
            {view.currentOperation.attempt > 1 ? ` · 第 ${view.currentOperation.attempt} 次尝试` : ""}
          </p>
        </div>
      ) : view.activity.lastProgressAt ? (
        <p className="mt-2 text-[11px] text-[var(--wjn-text-muted)]">
          最近进展 {formatRelativeTime(view.activity.lastProgressAt)}
        </p>
      ) : null}
    </section>
  );
}

function useElapsedTime(startedAt: string | null): string {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!startedAt) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [startedAt]);
  if (!startedAt) return "0 秒";
  const seconds = Math.max(0, Math.floor((now - Date.parse(startedAt)) / 1_000));
  if (seconds < 60) return `${seconds} 秒`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} 分 ${seconds % 60} 秒`;
}

/**
 * 以服务端 durationSeconds 为锚点、客户端每秒续走的平滑时长。
 * 服务端值只在 SSE refetch 时更新，直接渲染会出现"冻结后跳变"。
 */
function useLiveDuration(
  durationSeconds: number | null | undefined,
  executionStatus: MissionView["executionStatus"],
  missionId: string,
): string {
  const base = durationSeconds ?? 0;
  const isTerminal = executionStatus === "completed"
    || executionStatus === "failed"
    || executionStatus === "cancelled";
  const [liveSeconds, setLiveSeconds] = useState(base);

  useEffect(() => {
    setLiveSeconds(base);
    if (isTerminal) return;
    const anchoredAt = Date.now();
    const timer = window.setInterval(() => {
      const locallyElapsed = Math.max(0, Math.floor((Date.now() - anchoredAt) / 1_000));
      setLiveSeconds(base + locallyElapsed);
    }, 1_000);
    return () => window.clearInterval(timer);
  }, [base, isTerminal, missionId]);

  return formatMissionDuration(liveSeconds);
}

function formatRelativeTime(value: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - Date.parse(value)) / 1_000));
  if (!Number.isFinite(seconds) || seconds < 10) return "刚刚";
  if (seconds < 60) return `${seconds} 秒前`;
  return `${Math.floor(seconds / 60)} 分钟前`;
}

function activityStateLabel(state: MissionView["activity"]["state"]): string {
  return {
    starting: "准备中",
    working: "推进中",
    collaborating: "协作中",
    retrying: "重试中",
    recovering: "调整中",
    waiting: "待你回应",
    reviewing: "等待确认",
    completed: "已完成",
    unavailable: "稍后再试",
    stopped: "已停止",
  }[state];
}

function activityMeta(view: MissionView): string {
  const { activity } = view;
  if (activity.retryAt) {
    const retryAt = new Date(activity.retryAt);
    if (Number.isFinite(retryAt.getTime())) {
      return `${activity.attempt ? `第 ${activity.attempt} 次尝试，` : ""}${retryAt.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })} 继续`;
    }
  }
  if (activity.attempt) return `正在进行第 ${activity.attempt} 次尝试`;
  if (activity.state === "collaborating") {
    return view.subagents.length
      ? `${view.subagents.length} 位成员参与`
      : "研究成员正在启动";
  }
  return activityStateLabel(activity.state);
}

function MissionHeader({ view, onClose }: { view: MissionView; onClose(): void }) {
  const panelMode = useMissionUiStore((state) => state.panelMode);
  const expandMission = useMissionUiStore((state) => state.expandMission);
  const liveDuration = useLiveDuration(
    view.durationSeconds,
    view.executionStatus,
    view.missionId,
  );
  return (
    <header className="flex min-h-14 shrink-0 items-center gap-3 border-b border-[var(--wjn-line)] px-4">
      <StatusMark status={view.executionStatus} />
      <div className="min-w-0 flex-1">
        <h2 className="truncate text-sm font-semibold text-[var(--wjn-text)]">
          {view.title}
        </h2>
        <div className="mt-0.5 flex items-center gap-2 text-[11px] text-[var(--wjn-text-muted)]">
          <span>{view.activity.title}</span>
          <span aria-hidden="true">·</span>
          <span>{liveDuration}</span>
        </div>
      </div>
      {panelMode === "peek" ? (
        <IconButton label="展开任务" onClick={() => expandMission()}>
          <Maximize2 size={15} />
        </IconButton>
      ) : null}
      <IconButton label="关闭任务面板" onClick={onClose}>
        {panelMode === "expanded" ? <Minimize2 size={15} /> : <X size={15} />}
      </IconButton>
    </header>
  );
}

function ProgressSurface({
  view,
  onChatAction,
  onMissionTarget,
}: {
  view: MissionView;
  onChatAction(action: MissionChatAction): void;
  onMissionTarget(missionId: string): Promise<boolean>;
}) {
  return (
    <div className="space-y-7 px-5 py-5" data-testid="mission-progress">
      {view.objective ? (
        <section className="border-b border-[var(--wjn-line)] pb-4">
          <h3 className="text-[11px] font-semibold text-[var(--wjn-text-muted)]">
            任务目标
          </h3>
          <p className="mt-1 line-clamp-4 text-sm leading-6 text-[var(--wjn-text-secondary)]">
            {view.objective}
          </p>
        </section>
      ) : null}
      {view.attentionRequest ? (
        <AttentionRequestCard
          view={view}
          onChatAction={onChatAction}
          onMissionTarget={onMissionTarget}
        />
      ) : null}
      {!view.attentionRequest ? <MissionActivity view={view} /> : null}
      {view.failure ? (
        <section className="border border-[var(--wjn-line-strong)] bg-[var(--wjn-review-soft)] p-4" data-testid="mission-failure-card">
          <h3 className="text-sm font-semibold text-[var(--wjn-text)]">任务停在了一个安全边界</h3>
          <p className="mt-2 text-xs leading-5 text-[var(--wjn-text-secondary)]">{view.failure.userSummary}</p>
          <p className="mt-2 text-xs leading-5 text-[var(--wjn-text-secondary)]">{view.failure.preservedProgress}</p>
          <p className="mt-2 text-[11px] leading-5 text-[var(--wjn-text-muted)]">{view.failure.recommendedAction}</p>
          <button type="button" className="wjn-button-primary mt-3 flex h-8 items-center gap-2 px-3 text-xs" onClick={() => onChatAction("continue")}>
            <RotateCcw size={13} /> 从已保存进度继续
          </button>
        </section>
      ) : null}
      <section className="grid grid-cols-3 gap-2" aria-label="任务实时概览">
        <MissionMetric label="材料就绪" value={`${view.inputSummary.ready}/${view.inputSummary.total}`} />
        <MissionMetric label="来源与结果" value={String(view.evidenceCount)} />
        <MissionMetric label="成果" value={String(view.artifactCount)} />
      </section>
      {view.inputSummary.names.length ? (
        <p className="-mt-5 line-clamp-2 text-[11px] leading-5 text-[var(--wjn-text-muted)]" data-testid="mission-input-inventory">
          已读取材料：{view.inputSummary.names.join("、")}
        </p>
      ) : null}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-xs font-semibold text-[var(--wjn-text)]">阶段进度</h3>
          <span className="text-[11px] text-[var(--wjn-text-muted)]">
            已通过 {view.stages.filter((stage) => stage.status === "passed").length}/{view.stages.length}
          </span>
        </div>
        <div className="space-y-0">
          {view.stages.map((stage, index) => (
            <div key={stage.id} className="flex gap-3" data-testid={`mission-stage-${stage.id}`}>
              <div className="flex w-4 shrink-0 flex-col items-center">
                <span
                  className={`mt-1.5 h-2 w-2 rounded-full ${
                    stage.status === "passed"
                      ? "bg-[var(--wjn-success)]"
                      : stage.status === "active" || stage.status === "revising"
                        ? "bg-[var(--wjn-accent)]"
                        : "bg-[var(--wjn-surface-muted)]"
                  }`}
                />
                {index < view.stages.length - 1 ? (
                  <span className="min-h-8 w-px flex-1 bg-[var(--wjn-line)]" />
                ) : null}
              </div>
              <div className="min-w-0 pb-4">
                <div className="text-sm font-medium text-[var(--wjn-text)]">{stage.title}</div>
                {stage.summary ? (
                  <p className="mt-1 text-xs leading-5 text-[var(--wjn-text-secondary)]">
                    {stage.summary}
                  </p>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </section>
      {view.subagents.length || (view.activeSubagentCount ?? 0) > 0 ? (
        <section className="border-t border-[var(--wjn-line)] pt-5">
          <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold text-[var(--wjn-text)]">
            <Users size={14} /> 研究成员
          </h3>
          {view.teamSummary ? (
            <p className="mb-3 text-xs leading-5 text-[var(--wjn-text-secondary)]" data-testid="mission-team-summary">
              {view.teamSummary}
            </p>
          ) : null}
          <div className="space-y-3">
            {!view.subagents.length && (view.activeSubagentCount ?? 0) > 0 ? (
              <div className="flex items-center gap-2 text-xs text-[var(--wjn-text-muted)]" role="status">
                <LoaderCircle size={14} className="animate-spin" />
                研究成员正在启动…
              </div>
            ) : null}
            {view.subagents.map((member) => {
              const visibleMilestones = member.milestones
                .filter((milestone) => milestone.summary !== member.summary)
                .slice(-3);
              return (
              <div key={member.id} className="flex items-start gap-3" data-testid="mission-member">
                <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--wjn-surface-subtle)] text-xs font-semibold text-[var(--wjn-accent-strong)]">
                  {member.name.slice(0, 1)}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium text-[var(--wjn-text)]">
                      {member.name}
                    </span>
                    <span className="shrink-0 text-[11px] text-[var(--wjn-text-muted)]">
                      {subagentStatusLabel(member.status)}
                    </span>
                  </div>
                  <div className="text-xs text-[var(--wjn-text-secondary)]">{member.role}</div>
                  {member.summary ? (
                    <p className="mt-1 text-xs leading-5 text-[var(--wjn-text-muted)]" data-testid="mission-member-summary">
                      {member.summary}
                    </p>
                  ) : null}
                  {visibleMilestones.length ? (
                    <ol className="mt-2 space-y-1.5" data-testid="mission-member-milestones">
                      {visibleMilestones.map((milestone) => (
                        <li
                          key={`${milestone.kind}:${milestone.createdAt}:${milestone.summary}`}
                          className="flex items-start gap-2 text-xs leading-5 text-[var(--wjn-text-muted)]"
                        >
                          <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--wjn-accent)]" />
                          <span>
                            <span className="mr-1 text-[var(--wjn-text-secondary)]">
                              {subagentMilestoneLabel(milestone.kind)}
                            </span>
                            {milestone.summary}
                          </span>
                        </li>
                      ))}
                    </ol>
                  ) : null}
                </div>
              </div>
              );
            })}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function MissionMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-[var(--wjn-surface-subtle)] px-3 py-2.5">
      <div className="text-base font-semibold text-[var(--wjn-text)]">{value}</div>
      <div className="mt-0.5 text-[10px] text-[var(--wjn-text-muted)]">{label}</div>
    </div>
  );
}

function subagentStatusLabel(status: MissionView["subagents"][number]["status"]): string {
  return {
    queued: "等待中",
    working: "推进中",
    done: "已完成",
    needs_input: "待补充",
    failed: "未完成",
    cancelled: "已停止",
  }[status];
}

function subagentMilestoneLabel(
  kind: MissionView["subagents"][number]["milestones"][number]["kind"],
): string {
  return {
    finding: "发现",
    formula: "公式",
    file: "文件",
    figure: "图表",
    checkpoint: "进展",
  }[kind];
}

function AttentionRequestCard({
  view,
  onChatAction,
  onMissionTarget,
}: {
  view: MissionView;
  onChatAction(action: MissionChatAction): void;
  onMissionTarget(missionId: string): Promise<boolean>;
}) {
  const request = view.attentionRequest;
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!request) return null;

  const runAction = async (actionType: (typeof request.actions)[number]["actionType"]) => {
    if (actionType === "open_review") {
      document.getElementById("mission-review-section")?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    if (actionType === "upload_file") {
      onChatAction("attach");
      return;
    }
    const permissionDecision =
      actionType === "permission_allow_once"
        ? "allow_once"
        : actionType === "permission_allow_mission"
          ? "allow_for_mission"
          : actionType === "permission_reject"
            ? "reject"
            : undefined;
    if (permissionDecision) {
      setSubmitting(true);
      setError(null);
      try {
        await resolveMissionPermission({
          missionId: view.missionId,
          requestId: request.requestId,
          decision: permissionDecision,
        });
        if (!(await onMissionTarget(view.missionId))) {
          setError("权限决定已记录，最新任务状态暂时未能同步。请稍后重试。");
        }
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "权限确认失败");
      } finally {
        setSubmitting(false);
      }
      return;
    }
    onChatAction("focus");
  };

  return (
    <section
      className="border border-[var(--wjn-review)] bg-[var(--wjn-review-soft)] px-4 py-4"
      aria-labelledby={`attention-${request.requestId}`}
      data-testid="mission-attention-request"
    >
      <div className="flex items-start gap-3">
        <MessageCircle className="mt-0.5 shrink-0 text-[var(--wjn-review)]" size={17} />
        <div className="min-w-0 flex-1">
          <h3 id={`attention-${request.requestId}`} className="text-sm font-semibold text-[var(--wjn-text)]">
            {request.title}
          </h3>
          <p className="mt-1 text-sm leading-6 text-[var(--wjn-text-secondary)]">{request.summary}</p>
        </div>
      </div>
      {request.requiredInputs.length ? (
        <div className="mt-4 border-t border-[var(--wjn-line)] pt-3">
          <div className="text-[11px] font-medium text-[var(--wjn-text-muted)]">需要补充</div>
          <ul className="mt-2 space-y-2">
            {request.requiredInputs.map((input) => (
              <li key={input.id} className="flex items-start gap-2 text-sm text-[var(--wjn-text)]">
                {input.inputType === "file" ? <Paperclip className="mt-0.5 shrink-0 text-[var(--wjn-text-muted)]" size={14} /> : <CircleDot className="mt-0.5 shrink-0 text-[var(--wjn-text-muted)]" size={14} />}
                <span>{input.label}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <p className="mt-3 text-xs leading-5 text-[var(--wjn-text-muted)]">{request.impact}</p>
      <div className="mt-4 flex flex-wrap gap-2">
        {request.actions.map((action) => (
          <button
            key={action.id}
            type="button"
            onClick={() => void runAction(action.actionType)}
            disabled={submitting}
            className={`h-8 px-3 text-xs font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--wjn-accent)] ${action.primary ? "bg-[var(--wjn-accent)] text-white hover:bg-[var(--wjn-accent-strong)]" : "border border-[var(--wjn-line)] bg-[var(--wjn-surface)] text-[var(--wjn-text)] hover:bg-[var(--wjn-surface-subtle)]"}`}
          >
            {submitting && action.primary ? <LoaderCircle size={13} className="mr-1 inline animate-spin" /> : null}
            {action.label}
          </button>
        ))}
      </div>
      {error ? <p role="alert" className="mt-3 text-xs text-[var(--wjn-danger)]">{error}</p> : null}
    </section>
  );
}

function ReviewSurface({
  view,
  onMissionTarget,
}: {
  view: MissionView;
  onMissionTarget(missionId: string): Promise<boolean>;
}) {
  const storedSelection = useMissionUiStore((state) => state.selectedReviewItemIds);
  const selectionMissionId = useMissionUiStore((state) => state.selectionMissionId);
  const selectionRevision = useMissionUiStore((state) => state.selectionRevision);
  const ensureReviewSelection = useMissionUiStore((state) => state.ensureReviewSelection);
  const toggleReviewItem = useMissionUiStore((state) => state.toggleReviewItem);
  const busy = useMissionUiStore((state) => state.submittingReviewMissionIds.has(view.missionId));
  const beginReviewSubmission = useMissionUiStore((state) => state.beginReviewSubmission);
  const endReviewSubmission = useMissionUiStore((state) => state.endReviewSubmission);
  const [error, setError] = useState<string | null>(null);
  const [projectionPending, setProjectionPending] = useState(false);
  const [reviewItems, setReviewItems] = useState(view.reviewItems);
  const [nextReviewCursor, setNextReviewCursor] = useState(view.reviewNextCursor ?? null);
  const [loadingMore, setLoadingMore] = useState(false);
  const reviewRequestEpochRef = useRef(0);
  const reviewRequestInFlightRef = useRef(false);
  const projectedReviewItemsRef = useRef(view.reviewItems);
  const projectedReviewRevisionRef = useRef(view.reviewRevision);
  const reviewFirstPageIdsRef = useRef(
    new Set(view.reviewItems.map((item) => item.id)),
  );
  const loadedReviewPageCountRef = useRef(0);
  const reviewFullyLoadedRef = useRef(
    (view.reviewNextCursor ?? null) === null,
  );
  const pending = reviewItems.filter((item) => item.status === "pending");
  const suggestedSelection = useMemo(
    () => suggestedReviewSelection({ ...view, reviewItems }),
    [reviewItems, view],
  );
  const selected =
    selectionMissionId === view.missionId &&
    selectionRevision === view.reviewSelectionRevision
      ? storedSelection
      : EMPTY_REVIEW_SELECTION;

  useEffect(() => {
    ensureReviewSelection(
      view.missionId,
      view.reviewSelectionRevision,
      suggestedSelection,
    );
  }, [
    ensureReviewSelection,
    suggestedSelection,
    view.missionId,
    view.reviewSelectionRevision,
  ]);

  useEffect(() => {
    setProjectionPending(false);
  }, [view.missionId, view.stateVersion]);

  const replayReviewTail = useCallback(async ({
    expectedRevision,
    initialCursor,
    minimumPageCount,
    throughEnd,
  }: {
    expectedRevision: string;
    initialCursor: string;
    minimumPageCount: number;
    throughEnd: boolean;
  }) => {
    if (reviewRequestInFlightRef.current) return;
    const requestEpoch = ++reviewRequestEpochRef.current;
    reviewRequestInFlightRef.current = true;
    setLoadingMore(true);
    setError(null);
    let cursor: string | null = initialCursor;
    let loadedPageCount = 0;
    let tailItems: MissionReviewItemView[] = [];
    const seenCursors = new Set<string>();
    try {
      while (
        cursor &&
        loadedPageCount < MAX_REVIEW_REPLAY_PAGES &&
        (loadedPageCount < minimumPageCount || throughEnd)
      ) {
        if (seenCursors.has(cursor)) {
          throw new Error("待确认内容分页游标重复，已停止同步");
        }
        seenCursors.add(cursor);
        const page = await listMissionReviews({
          missionId: view.missionId,
          cursor,
        });
        if (requestEpoch !== reviewRequestEpochRef.current) return;
        assertReviewRevision(page.revision, expectedRevision);
        tailItems = appendUnique(tailItems, page.items);
        cursor = page.nextCursor;
        loadedPageCount += 1;
      }
      if (requestEpoch !== reviewRequestEpochRef.current) return;
      setReviewItems(
        reconcileProjectedPage(projectedReviewItemsRef.current, tailItems),
      );
      setNextReviewCursor(cursor);
      loadedReviewPageCountRef.current = loadedPageCount;
      reviewFullyLoadedRef.current = cursor === null;
      if (cursor && loadedPageCount >= MAX_REVIEW_REPLAY_PAGES) {
        setError("待确认内容较多，已暂停自动同步，可继续手动加载。");
      }
    } catch (reason) {
      if (requestEpoch !== reviewRequestEpochRef.current) return;
      setReviewItems(projectedReviewItemsRef.current);
      setNextReviewCursor(
        projectedReviewItemsRef.current.length
          ? view.reviewNextCursor ?? null
          : null,
      );
      loadedReviewPageCountRef.current = 0;
      reviewFullyLoadedRef.current =
        (view.reviewNextCursor ?? null) === null;
      setError(
        reason instanceof Error ? reason.message : "待确认内容同步失败",
      );
    } finally {
      if (requestEpoch === reviewRequestEpochRef.current) {
        reviewRequestInFlightRef.current = false;
        setLoadingMore(false);
      }
    }
  }, [view.missionId, view.reviewNextCursor]);

  useEffect(() => {
    projectedReviewItemsRef.current = view.reviewItems;
    const previousFirstPageIds = reviewFirstPageIdsRef.current;
    reviewFirstPageIdsRef.current = new Set(
      view.reviewItems.map((item) => item.id),
    );
    if (projectedReviewRevisionRef.current === view.reviewRevision) {
      setReviewItems((current) =>
        reconcileProjectedFirstPage(
          view.reviewItems,
          current,
          previousFirstPageIds,
        ),
      );
      if (loadedReviewPageCountRef.current === 0) {
        setNextReviewCursor(view.reviewNextCursor ?? null);
        reviewFullyLoadedRef.current =
          (view.reviewNextCursor ?? null) === null;
      }
      return;
    }

    const previouslyLoadedPageCount = loadedReviewPageCountRef.current;
    const previousTailWasComplete = reviewFullyLoadedRef.current;
    projectedReviewRevisionRef.current = view.reviewRevision;
    ++reviewRequestEpochRef.current;
    reviewRequestInFlightRef.current = false;
    loadedReviewPageCountRef.current = 0;
    reviewFullyLoadedRef.current =
      (view.reviewNextCursor ?? null) === null;
    setReviewItems(view.reviewItems);
    setNextReviewCursor(view.reviewNextCursor ?? null);
    if (
      previouslyLoadedPageCount > 0 &&
      view.reviewNextCursor
    ) {
      void replayReviewTail({
        expectedRevision: view.reviewRevision,
        initialCursor: view.reviewNextCursor,
        minimumPageCount: previouslyLoadedPageCount,
        throughEnd: previousTailWasComplete,
      });
    }
  }, [
    replayReviewTail,
    view.reviewItems,
    view.reviewNextCursor,
    view.reviewRevision,
  ]);

  useEffect(() => {
    const requestEpoch = reviewRequestEpochRef;
    const requestInFlight = reviewRequestInFlightRef;
    return () => {
      ++requestEpoch.current;
      requestInFlight.current = false;
    };
  }, []);

  useEffect(() => {
    if (loadedReviewPageCountRef.current === 0) {
      setNextReviewCursor(view.reviewNextCursor ?? null);
    }
  }, [view.reviewNextCursor]);

  useEffect(() => {
    const expirations = reviewItems
      .flatMap((item) => item.previewExpiresAt ? [Date.parse(item.previewExpiresAt)] : [])
      .filter((value) => Number.isFinite(value) && value > Date.now());
    if (!expirations.length) return;
    const delay = Math.min(Math.max(Math.min(...expirations) - Date.now() + 100, 100), 2_147_000_000);
    const timer = window.setTimeout(() => {
      void onMissionTarget(view.missionId);
    }, delay);
    return () => window.clearTimeout(timer);
  }, [
    onMissionTarget,
    reviewItems,
    view.missionId,
  ]);

  const loadMoreReviews = async () => {
    if (
      !nextReviewCursor ||
      loadingMore ||
      reviewRequestInFlightRef.current
    ) {
      return;
    }
    const requestEpoch = ++reviewRequestEpochRef.current;
    reviewRequestInFlightRef.current = true;
    setLoadingMore(true);
    setError(null);
    try {
      const page = await listMissionReviews({
        missionId: view.missionId,
        cursor: nextReviewCursor,
      });
      if (requestEpoch !== reviewRequestEpochRef.current) return;
      assertReviewRevision(page.revision, view.reviewRevision);
      setReviewItems((current) => reconcileProjectedPage(current, page.items));
      setNextReviewCursor(page.nextCursor);
      loadedReviewPageCountRef.current += 1;
      reviewFullyLoadedRef.current = page.nextCursor === null;
    } catch (reason) {
      if (requestEpoch !== reviewRequestEpochRef.current) return;
      setError(reason instanceof Error ? reason.message : "更多待确认内容加载失败");
    } finally {
      if (requestEpoch === reviewRequestEpochRef.current) {
        reviewRequestInFlightRef.current = false;
        setLoadingMore(false);
      }
    }
  };

  const synchronizeReceipt = async (result: MissionMutationResult) => {
    if (result.issueCodes.length) {
      setError(reviewMutationIssue(result.issueCodes));
    }
    let synchronized = false;
    try {
      synchronized = await onMissionTarget(result.targetMissionId);
    } catch {
      synchronized = false;
    }
    setProjectionPending(!synchronized);
  };

  const selectedPending = pending.filter((item) => selected.has(item.id));
  const selectedHasProtected = selectedPending.some((item) => !item.batchAcceptable);

  const decide = async (decision: "accepted" | "rejected" | "needs_more_evidence") => {
    if (!selectedPending.length || (decision === "accepted" && selectedHasProtected)) return;
    if (!beginReviewSubmission(view.missionId)) return;
    setError(null);
    try {
      const result = await decideMissionReviews({
        missionId: view.missionId,
        decisions: selectedPending.map((item) => ({ reviewItemId: item.id, decision })),
      });
      const decidedIds = new Set(result.appliedReviewItemIds ?? []);
      setReviewItems((current) => current.map((item) => (
        decidedIds.has(item.id) ? { ...item, status: decision } : item
      )));
      await synchronizeReceipt(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "确认失败");
    } finally {
      endReviewSubmission(view.missionId);
    }
  };

  const decideOne = async (
    reviewItemId: string,
    decision: "accepted" | "rejected" | "needs_more_evidence",
  ) => {
    if (!beginReviewSubmission(view.missionId)) return;
    setError(null);
    try {
      const result = await decideMissionReviews({
        missionId: view.missionId,
        decisions: [{ reviewItemId, decision }],
      });
      if (result.appliedReviewItemIds?.includes(reviewItemId)) {
        setReviewItems((current) => current.map((item) => (
          item.id === reviewItemId ? { ...item, status: decision } : item
        )));
      }
      await synchronizeReceipt(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "确认失败");
    } finally {
      endReviewSubmission(view.missionId);
    }
  };

  const saveAccepted = async () => {
    const accepted = reviewItems.filter(
      (item) => item.status === "accepted" && item.commitEligible,
    );
    if (!accepted.length) return;
    if (!beginReviewSubmission(view.missionId)) return;
    setError(null);
    try {
      const result = await commitMissionReviews({
        missionId: view.missionId,
        reviewItemIds: accepted.map((item) => item.id),
      });
      const committedIds = new Set(result.committedReviewItemIds ?? []);
      setReviewItems((current) => current.map((item) => (
        committedIds.has(item.id)
          ? {
              ...item,
              status: "committed",
              commitStatus: "committed",
              commitEligible: false,
            }
          : item
      )));
      await synchronizeReceipt(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败");
    } finally {
      endReviewSubmission(view.missionId);
    }
  };

  return (
    <div className="px-5 py-5" data-testid="mission-review">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--wjn-line)] pb-4">
        <div>
          <h3 className="text-sm font-semibold text-[var(--wjn-text)]">确认与保存</h3>
          <p className="mt-1 text-xs leading-5 text-[var(--wjn-text-secondary)]">
            {view.reviewSummary.pending
              ? `${view.reviewSummary.pending} 项内容等待你的确认。`
              : "当前没有待确认内容。"}
          </p>
        </div>
        <ReviewModeSelect view={view} onMissionTarget={onMissionTarget} />
      </div>

      {pending.length ? (
        <div className="divide-y divide-[var(--wjn-line)]">
          {pending.map((item) => {
            const protectedItem = item.requiresExplicitReview;
            return (
              <div key={item.id} className="flex gap-3 py-4">
                <label className="mt-1 flex h-5 w-5 shrink-0 cursor-pointer items-start">
                  <input
                    type="checkbox"
                    checked={selected.has(item.id)}
                    disabled={busy}
                    onChange={() => toggleReviewItem(
                      view.missionId,
                      view.reviewSelectionRevision,
                      item.id,
                    )}
                    aria-label={`选择 ${item.title}`}
                    className="h-4 w-4 accent-[var(--wjn-accent)]"
                  />
                </label>
                <div className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-[var(--wjn-text)]">{item.title}</span>
                    <span className="rounded-full bg-[var(--wjn-review-soft)] px-2 py-0.5 text-[10px] text-[var(--wjn-review)]">
                      {protectedItem ? "需逐项确认" : "建议确认"}
                    </span>
                  </span>
                  {item.summary ? (
                    <span className="mt-1 block text-xs leading-5 text-[var(--wjn-text-secondary)]">
                      {item.summary}
                    </span>
                  ) : null}
                  {item.reasonLabel ? (
                    <span className="mt-1 block text-[11px] text-[var(--wjn-text-muted)]">
                      {item.reasonLabel}
                    </span>
                  ) : null}
                  <ReviewPreview missionId={view.missionId} item={item} />
                  {!item.batchAcceptable ? (
                    <div className="mt-2 flex gap-2">
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => {
                          void decideOne(item.id, "accepted");
                        }}
                        className="wjn-button-secondary h-7 px-2.5 text-[11px]"
                      >
                        确认此项
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => {
                          void decideOne(item.id, "needs_more_evidence");
                        }}
                        className="h-7 px-2.5 text-[11px] text-[var(--wjn-text-secondary)] hover:text-[var(--wjn-text)]"
                      >
                        需要补证
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => {
                          void decideOne(item.id, "rejected");
                        }}
                        className="h-7 px-2.5 text-[11px] text-[var(--wjn-error)] hover:bg-[var(--wjn-error-soft)]"
                      >
                        不采纳
                      </button>
                    </div>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <QuietEmpty icon={Check} title="已处理完" detail="需要确认的内容会出现在这里。" />
      )}

      {view.reviewSummary.needsMoreEvidence > 0 ? (
        <div className="mt-3 rounded-[var(--wjn-radius)] bg-[var(--wjn-review-soft)] px-3 py-2 text-xs leading-5 text-[var(--wjn-review)]">
          {view.reviewSummary.needsMoreEvidence} 项内容还需要补充材料，暂不会写入工作区。
        </div>
      ) : null}
      {reviewItems.some((item) => item.status !== "pending" && item.status !== "superseded") ? (
        <div className="mt-4 border-t border-[var(--wjn-line)] pt-3">
          <h4 className="mb-2 text-xs font-semibold text-[var(--wjn-text)]">已处理内容</h4>
          <div className="divide-y divide-[var(--wjn-line)]">
            {reviewItems.filter((item) => item.status !== "pending" && item.status !== "superseded").map((item) => (
              <div key={item.id} className="flex items-center gap-3 py-2.5 text-xs">
                <span className="min-w-0 flex-1 truncate text-[var(--wjn-text-secondary)]">{item.title}</span>
                {item.status === "committed" && item.targetKind === "workspace_asset" && item.visual && item.committedTargetRef ? (
                  <Link
                    href={`/workspaces/${encodeURIComponent(view.workspaceId)}/prism?visual_mission_id=${encodeURIComponent(view.missionId)}&visual_review_item_id=${encodeURIComponent(item.id)}`}
                    className="shrink-0 font-medium text-[var(--wjn-accent-strong)] hover:underline"
                  >
                    插入写作台
                  </Link>
                ) : null}
                <span className={`shrink-0 ${item.status === "committed" ? "text-[var(--wjn-success)]" : item.status === "needs_more_evidence" ? "text-[var(--wjn-review)]" : "text-[var(--wjn-text-muted)]"}`}>
                  {reviewItemStatusLabel(item.status, item.commitStatus)}
                </span>
                {item.commitErrorCode ? (
                  <span className="sr-only">保存错误：{item.commitErrorCode}</span>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {nextReviewCursor ? (
        <button type="button" disabled={loadingMore || busy} onClick={() => void loadMoreReviews()} className="wjn-button-secondary mt-3 h-8 w-full text-xs disabled:opacity-45">
          {loadingMore ? "正在加载…" : `加载更多待确认内容（已显示 ${reviewItems.length} 项）`}
        </button>
      ) : null}
      {error ? <p className="mt-3 text-xs text-[var(--wjn-error)]">{error}</p> : null}
      {projectionPending ? (
        <p className="mt-3 text-xs text-[var(--wjn-text-secondary)]" role="status">
          操作已受理，最新任务状态正在同步。
        </p>
      ) : null}
      <div className="sticky bottom-0 mt-4 flex flex-wrap gap-2 border-t border-[var(--wjn-line)] bg-[var(--wjn-surface)] py-3">
        <button
          type="button"
          disabled={busy || !selectedPending.length || selectedHasProtected}
          onClick={() => void decide("accepted")}
          className="wjn-button-primary h-8 px-3 text-xs disabled:cursor-not-allowed disabled:opacity-45"
        >
          确认选中
        </button>
        <button
          type="button"
          disabled={busy || !selectedPending.length}
          onClick={() => void decide("needs_more_evidence")}
          className="wjn-button-secondary h-8 px-3 text-xs disabled:opacity-45"
        >
          需要补证
        </button>
        <button
          type="button"
          disabled={busy || !selectedPending.length}
          onClick={() => void decide("rejected")}
          className="h-8 px-3 text-xs text-[var(--wjn-error)] hover:bg-[var(--wjn-error-soft)] disabled:opacity-45"
        >
          不采纳选中
        </button>
        <button
          type="button"
          disabled={busy || !reviewItems.some((item) => item.status === "accepted" && item.commitEligible)}
          onClick={() => void saveAccepted()}
          className="wjn-button-secondary ml-auto h-8 px-3 text-xs disabled:opacity-45"
        >
          {view.commitSummary.applying ? "保存中…" : "保存已确认内容"}
        </button>
      </div>
    </div>
  );
}

function ReviewPreview({ missionId, item }: { missionId: string; item: MissionView["reviewItems"][number] }) {
  if (item.visual) {
    return <AcademicVisualReviewPreview missionId={missionId} item={item} />;
  }
  const hasInlinePreview = Boolean(item.preview && Object.keys(item.preview).length);
  const markdownPreview = reviewMarkdownPreview(item.preview);
  if (!hasInlinePreview) return null;

  return (
    <details className="mt-2 rounded-[var(--wjn-radius)] border border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] px-3 py-2">
      <summary className="cursor-pointer text-[11px] font-medium text-[var(--wjn-accent-strong)]">
        查看内容预览
      </summary>
      {markdownPreview ? (
        <MarkdownRenderer
          content={markdownPreview}
          className="prose-chat mt-2 max-h-72 overflow-auto text-xs leading-5 text-[var(--wjn-text-secondary)]"
        />
      ) : hasInlinePreview ? (
        <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words text-[11px] leading-5 text-[var(--wjn-text-secondary)]">
          {JSON.stringify(item.preview, null, 2)}
        </pre>
      ) : null}
    </details>
  );
}

function reviewMarkdownPreview(preview: MissionView["reviewItems"][number]["preview"]): string | null {
  if (!preview) return null;
  for (const field of ["body", "content", "markdown"] as const) {
    const value = preview[field];
    if (typeof value === "string" && value.trim()) return value;
  }
  return null;
}

function ReviewModeSelect({
  view,
  onMissionTarget,
}: {
  view: MissionView;
  onMissionTarget(missionId: string): Promise<boolean>;
}) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projectionPending, setProjectionPending] = useState(false);
  const busy = useMissionUiStore((state) => state.submittingReviewMissionIds.has(view.missionId));
  const beginReviewSubmission = useMissionUiStore((state) => state.beginReviewSubmission);
  const endReviewSubmission = useMissionUiStore((state) => state.endReviewSubmission);
  const labels: Record<MissionReviewMode, string> = {
    review_all: "每项确认",
    balanced_default: "平衡模式",
    auto_draft: "草稿自动保存",
  };

  useEffect(() => {
    setProjectionPending(false);
  }, [view.missionId, view.stateVersion]);

  const change = async (mode: MissionReviewMode) => {
    if (!beginReviewSubmission(view.missionId)) return;
    setOpen(false);
    setError(null);
    setProjectionPending(false);
    try {
      const result = await updateMissionReviewMode(view.missionId, mode);
      let synchronized = false;
      try {
        synchronized = await onMissionTarget(result.targetMissionId);
      } catch {
        synchronized = false;
      }
      setProjectionPending(!synchronized);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "确认方式更新失败");
    } finally {
      endReviewSubmission(view.missionId);
    }
  };
  return (
    <div className="relative">
      <button
        type="button"
        disabled={busy}
        onClick={() => setOpen((value) => !value)}
        className="flex h-8 items-center gap-1 rounded-[var(--wjn-radius)] border border-[var(--wjn-line)] px-2.5 text-xs text-[var(--wjn-text-secondary)] hover:bg-[var(--wjn-surface-subtle)]"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        {labels[view.reviewMode]} <ChevronDown size={13} />
      </button>
      {open ? (
        <div className="absolute right-0 top-9 z-30 min-w-40 rounded-[var(--wjn-radius)] border border-[var(--wjn-line)] bg-[var(--wjn-surface)] p-1 shadow-[var(--wjn-shadow-md)]" role="menu">
          {(Object.keys(labels) as MissionReviewMode[]).map((mode) => (
            <button key={mode} type="button" role="menuitem" disabled={busy} onClick={() => void change(mode)} className="flex w-full items-center justify-between rounded px-2.5 py-2 text-left text-xs hover:bg-[var(--wjn-surface-subtle)] disabled:opacity-45">
              {labels[mode]} {view.reviewMode === mode ? <Check size={13} /> : null}
            </button>
          ))}
        </div>
      ) : null}
      {error ? (
        <span className="absolute right-0 top-9 z-30 w-48 rounded-[var(--wjn-radius)] bg-[var(--wjn-error-soft)] px-2.5 py-2 text-[11px] leading-4 text-[var(--wjn-error)]">
          {error}
        </span>
      ) : null}
      {projectionPending ? (
        <span className="absolute right-0 top-9 z-30 w-48 rounded-[var(--wjn-radius)] bg-[var(--wjn-surface-subtle)] px-2.5 py-2 text-[11px] leading-4 text-[var(--wjn-text-secondary)]" role="status">
          设置已受理，最新状态正在同步。
        </span>
      ) : null}
    </div>
  );
}

function EvidenceSurface({ view }: { view: MissionView }) {
  const query = useMissionUiStore((state) => state.evidenceQuery);
  const setQuery = useMissionUiStore((state) => state.setEvidenceQuery);
  const [evidenceItems, setEvidenceItems] = useState<MissionEvidenceView[]>(view.evidenceItems);
  const [nextCursor, setNextCursor] = useState<number | null>(view.evidenceNextCursor ?? null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const requestEpochRef = useRef(0);
  const requestInFlightRef = useRef(false);
  const evidenceMissionRef = useRef(view.missionId);
  const evidencePagesLoadedRef = useRef(false);
  const evidenceVisibleCountRef = useRef(view.evidenceItems.length);
  const evidenceFullyLoadedRef = useRef((view.evidenceNextCursor ?? null) === null);
  const evidenceTailReplayCursorRef = useRef<number | null>(null);
  const evidenceFirstPageIdsRef = useRef(new Set(view.evidenceItems.map((item) => item.id)));

  useEffect(() => {
    const requestEpoch = requestEpochRef;
    const requestInFlight = requestInFlightRef;
    return () => {
      ++requestEpoch.current;
      requestInFlight.current = false;
    };
  }, []);

  const loadEvidencePage = useCallback(async (cursor: number) => {
    if (requestInFlightRef.current) return;
    const missionId = evidenceMissionRef.current;
    const requestEpoch = ++requestEpochRef.current;
    requestInFlightRef.current = true;
    evidenceFullyLoadedRef.current = false;
    setLoadingMore(true);
    setLoadError(null);
    try {
      const page = await listMissionEvidence({ missionId, cursor });
      if (requestEpoch !== requestEpochRef.current) return;
      evidencePagesLoadedRef.current = true;
      evidenceTailReplayCursorRef.current = cursor;
      setEvidenceItems((current) => {
        const next = appendUnique(current, page.items);
        evidenceVisibleCountRef.current = next.length;
        return next;
      });
      setNextCursor(page.nextCursor);
      evidenceFullyLoadedRef.current = page.nextCursor === null;
    } catch (reason) {
      if (requestEpoch !== requestEpochRef.current) return;
      setNextCursor(cursor);
      setLoadError(reason instanceof Error ? reason.message : "更多内容加载失败");
    } finally {
      if (requestEpoch === requestEpochRef.current) {
        requestInFlightRef.current = false;
        setLoadingMore(false);
      }
    }
  }, []);

  useEffect(() => {
    if (evidenceMissionRef.current !== view.missionId) return;
    const previouslyVisibleCount = evidenceVisibleCountRef.current;
    const previousFirstPageIds = evidenceFirstPageIdsRef.current;
    evidenceFirstPageIdsRef.current = new Set(view.evidenceItems.map((item) => item.id));
    setEvidenceItems((current) => {
      const next = reconcileProjectedFirstPage(
        view.evidenceItems,
        current,
        previousFirstPageIds,
      );
      evidenceVisibleCountRef.current = next.length;
      return next;
    });
    if (!evidencePagesLoadedRef.current) {
      setNextCursor(view.evidenceNextCursor ?? null);
      evidenceFullyLoadedRef.current = (view.evidenceNextCursor ?? null) === null;
    } else if (
      evidenceFullyLoadedRef.current
      && view.evidenceCount > previouslyVisibleCount
      && evidenceTailReplayCursorRef.current !== null
    ) {
      const replayCursor = evidenceTailReplayCursorRef.current;
      evidenceFullyLoadedRef.current = false;
      void loadEvidencePage(replayCursor);
    }
  }, [loadEvidencePage, view.evidenceCount, view.evidenceItems, view.evidenceNextCursor, view.missionId]);

  const items = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return evidenceItems;
    return evidenceItems.filter((item) =>
      [item.title, item.summary, item.sourceLabel].some((value) => value?.toLowerCase().includes(needle)),
    );
  }, [evidenceItems, query]);

  const loadMore = async () => {
    if (nextCursor === null || requestInFlightRef.current) return;
    await loadEvidencePage(nextCursor);
  };

  return (
    <div className="px-5 py-5" data-testid="mission-evidence">
      <label className="flex h-9 items-center gap-2 rounded-[var(--wjn-radius)] border border-[var(--wjn-line)] px-3 focus-within:border-[var(--wjn-accent-line)]">
        <Search size={14} className="text-[var(--wjn-text-muted)]" />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="查找来源" className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-[var(--wjn-text-muted)]" />
      </label>
      {items.length ? (
        <div className="mt-3 divide-y divide-[var(--wjn-line)]">
          {items.map((item) => (
            <article key={item.id} className="py-4">
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <TypeChip type={resolveMaterialType(item.sourceType)} />
                    <h4 className="min-w-0 truncate text-sm font-medium leading-5 text-[var(--wjn-text)]">{item.title}</h4>
                    {item.verified ? <StatusPill label="已查证" tone="verified" dot={false} className="ml-auto shrink-0" /> : null}
                  </div>
                  <div className="mt-1 text-[11px] text-[var(--wjn-text-muted)]">{item.sourceLabel ?? resolveMaterialType(item.sourceType)}</div>
                  {item.summary ? <p className="mt-2 text-xs leading-5 text-[var(--wjn-text-secondary)]">{item.summary}</p> : null}
                  {safeExternalUrl(item.citation) ? (
                    <a href={safeExternalUrl(item.citation)!} target="_blank" rel="noreferrer" className="mt-2 inline-flex text-xs font-medium text-[var(--wjn-accent-strong)] hover:underline">
                      查看来源
                    </a>
                  ) : item.citation ? (
                    <p className="mt-2 break-words text-[11px] text-[var(--wjn-text-muted)]">{item.citation}</p>
                  ) : null}
                </div>
              </div>
            </article>
          ))}
        </div>
      ) : <QuietEmpty icon={BookOpen} title="还没有沉淀来源材料" detail="可查证的论文、网页、数据和上传材料会汇总在这里。" />}
      {loadError ? <p className="mt-3 text-xs text-[var(--wjn-error)]">{loadError}</p> : null}
      {nextCursor !== null && !query.trim() ? (
        <button type="button" disabled={loadingMore} onClick={() => void loadMore()} className="wjn-button-secondary mt-3 h-8 w-full text-xs disabled:opacity-45">
          {loadingMore ? "正在加载…" : `加载更多（已显示 ${evidenceItems.length}/${view.evidenceCount}）`}
        </button>
      ) : null}
    </div>
  );
}

interface LoadedArtifactPage {
  items: MissionArtifactView[];
  nextCursor: number | null;
  nextTiebreaker: string | null;
}

function assertArtifactRevision(actual: string, expected: string): void {
  if (actual !== expected) {
    throw new Error("成果列表刚刚更新，正在同步最新内容");
  }
}

function ArtifactSurface({ view }: { view: MissionView }) {
  const [tailPages, setTailPages] = useState<LoadedArtifactPage[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const requestEpochRef = useRef(0);
  const requestInFlightRef = useRef(false);
  const projectedArtifactRevisionRef = useRef(view.artifactRevision);
  const tailItems = useMemo(
    () => tailPages.flatMap((page) => page.items),
    [tailPages],
  );
  const artifactItems = useMemo(
    () => reconcileProjectedPage(view.artifactItems, tailItems),
    [tailItems, view.artifactItems],
  );
  const [previewClock, setPreviewClock] = useState(0);
  const lastTailPage = tailPages.at(-1);
  const nextCursor = lastTailPage
    ? lastTailPage.nextCursor
    : (view.artifactNextCursor ?? null);
  const nextTiebreaker = lastTailPage
    ? lastTailPage.nextTiebreaker
    : (view.artifactNextTiebreaker ?? null);

  useEffect(() => {
    const expirations = artifactItems
      .flatMap((item) => item.previewExpiresAt
        ? [Date.parse(item.previewExpiresAt)]
        : [])
      .filter((value) => Number.isFinite(value) && value > previewClock);
    if (!expirations.length) return;
    const delay = Math.min(
      Math.max(Math.min(...expirations) - Date.now() + 100, 100),
      2_147_000_000,
    );
    const timer = window.setTimeout(() => setPreviewClock(Date.now()), delay);
    return () => window.clearTimeout(timer);
  }, [artifactItems, previewClock]);

  useEffect(() => {
    const requestEpoch = requestEpochRef;
    const requestInFlight = requestInFlightRef;
    return () => {
      ++requestEpoch.current;
      requestInFlight.current = false;
    };
  }, []);

  const loadMore = async () => {
    if (nextCursor === null || requestInFlightRef.current) return;
    const requestEpoch = ++requestEpochRef.current;
    requestInFlightRef.current = true;
    setLoadingMore(true);
    setLoadError(null);
    try {
      const page = await listMissionArtifacts({
        missionId: view.missionId,
        cursor: nextCursor,
        ...(nextTiebreaker ? { tiebreaker: nextTiebreaker } : {}),
      });
      if (requestEpoch !== requestEpochRef.current) return;
      assertArtifactRevision(page.revision, view.artifactRevision);
      setTailPages((current) => [
        ...current,
        {
          items: page.items,
          nextCursor: page.nextCursor,
          nextTiebreaker: page.nextTiebreaker ?? null,
        },
      ]);
    } catch (reason) {
      if (requestEpoch !== requestEpochRef.current) return;
      setLoadError(reason instanceof Error ? reason.message : "更多成果加载失败");
    } finally {
      if (requestEpoch === requestEpochRef.current) {
        requestInFlightRef.current = false;
        setLoadingMore(false);
      }
    }
  };

  useEffect(() => {
    if (projectedArtifactRevisionRef.current === view.artifactRevision) return;
    projectedArtifactRevisionRef.current = view.artifactRevision;

    // A page requested against an older projection must not land after this refresh.
    if (requestInFlightRef.current) {
      ++requestEpochRef.current;
      requestInFlightRef.current = false;
      setLoadingMore(false);
    }
    if (!tailPages.length) return;

    const previousTailWasComplete = tailPages.at(-1)?.nextCursor === null;
    const projectedTailCount = Math.max(0, view.artifactCount - view.artifactItems.length);
    const pageCount = previousTailWasComplete
      ? Math.max(tailPages.length, Math.ceil(projectedTailCount / 50))
      : tailPages.length;
    const requestEpoch = ++requestEpochRef.current;
    requestInFlightRef.current = true;

    const replayTail = async () => {
      setLoadingMore(true);
      setLoadError(null);
      try {
        const replayed: LoadedArtifactPage[] = [];
        let cursor = view.artifactNextCursor ?? null;
        let tiebreaker = view.artifactNextTiebreaker ?? null;
        for (let index = 0; index < pageCount && cursor !== null; index += 1) {
          const page = await listMissionArtifacts({
            missionId: view.missionId,
            cursor,
            ...(tiebreaker ? { tiebreaker } : {}),
          });
          if (requestEpoch !== requestEpochRef.current) return;
          assertArtifactRevision(page.revision, view.artifactRevision);
          replayed.push({
            items: page.items,
            nextCursor: page.nextCursor,
            nextTiebreaker: page.nextTiebreaker ?? null,
          });
          cursor = page.nextCursor;
          tiebreaker = page.nextTiebreaker ?? null;
        }
        if (requestEpoch !== requestEpochRef.current) return;
        setTailPages(replayed);
      } catch (reason) {
        if (requestEpoch !== requestEpochRef.current) return;
        setLoadError(reason instanceof Error ? reason.message : "成果刷新失败");
      } finally {
        if (requestEpoch === requestEpochRef.current) {
          requestInFlightRef.current = false;
          setLoadingMore(false);
        }
      }
    };

    void replayTail();
  }, [
    view.artifactCount,
    view.artifactItems,
    view.artifactNextCursor,
    view.artifactNextTiebreaker,
    view.artifactRevision,
    view.missionId,
    tailPages,
  ]);

  const openPreview = async (item: MissionArtifactView) => {
    setLoadError(null);
    try {
      const preview = await getMissionReviewPreview({
        missionId: view.missionId,
        reviewItemId: item.id,
      });
      const objectUrl = URL.createObjectURL(preview.blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.target = "_blank";
      anchor.rel = "noreferrer";
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
    } catch (reason) {
      setLoadError(reason instanceof Error ? reason.message : "成果预览加载失败");
    }
  };

  return (
    <div className="px-5 py-5" data-testid="mission-artifacts">
      {artifactItems.length ? (
        <div className="divide-y divide-[var(--wjn-line)]">
          {artifactItems.map((item) => (
            <div key={item.id} className="flex gap-3 py-4">
              <FileText size={16} className="mt-0.5 text-[var(--wjn-accent)]" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium">{item.title}</span>
                  <span className="text-[10px] text-[var(--wjn-text-muted)]">{item.committed ? "已保存" : "待确认"}</span>
                </div>
                {item.summary ? <p className="mt-1 text-xs leading-5 text-[var(--wjn-text-secondary)]">{item.summary}</p> : null}
                {item.previewAvailable && (
                  !item.previewExpiresAt
                  || !Number.isFinite(Date.parse(item.previewExpiresAt))
                  || Date.parse(item.previewExpiresAt) > previewClock
                ) ? (
                  <button type="button" onClick={() => void openPreview(item)} className="mt-2 mr-3 inline-flex text-xs font-medium text-[var(--wjn-accent-strong)] hover:underline">
                    查看预览
                  </button>
                ) : null}
                {item.downloadUrl ? (
                  <button
                    type="button"
                    onClick={() => void downloadMissionArtifact(item.downloadUrl!, item.title)}
                    className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-[var(--wjn-accent-strong)] hover:underline"
                  >
                    <Download size={13} aria-hidden="true" />
                    下载文件
                  </button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      ) : <QuietEmpty icon={Archive} title="还没有成果" detail="文稿、图表和实验产物会在生成后出现在这里。" />}
      {loadError ? <p className="mt-3 text-xs text-[var(--wjn-error)]">{loadError}</p> : null}
      {nextCursor !== null ? (
        <button type="button" disabled={loadingMore} onClick={() => void loadMore()} className="wjn-button-secondary mt-3 h-8 w-full text-xs disabled:opacity-45">
          {loadingMore ? "正在加载…" : `加载更多成果（已显示 ${artifactItems.length}/${view.artifactCount}）`}
        </button>
      ) : null}
    </div>
  );
}

function appendUnique<T extends { id: string }>(current: T[], incoming: T[]): T[] {
  const known = new Set(current.map((item) => item.id));
  return [...current, ...incoming.filter((item) => !known.has(item.id))];
}

function reconcileProjectedPage<T extends { id: string }>(
  authoritative: T[],
  current: T[],
): T[] {
  const authoritativeIds = new Set(authoritative.map((item) => item.id));
  return [
    ...authoritative,
    ...current.filter((item) => !authoritativeIds.has(item.id)),
  ];
}

function reconcileProjectedFirstPage<T extends { id: string }>(
  authoritative: T[],
  current: T[],
  previousFirstPageIds: ReadonlySet<string>,
): T[] {
  const authoritativeIds = new Set(authoritative.map((item) => item.id));
  return [
    ...authoritative,
    ...current.filter((item) => (
      !previousFirstPageIds.has(item.id) && !authoritativeIds.has(item.id)
    )),
  ];
}

function safeExternalUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : null;
  } catch {
    return null;
  }
}

function mergeTraceItems(current: MissionItem[], incoming: MissionItem[]): MissionItem[] {
  const byId = new Map(current.map((item) => [item.id, item]));
  for (const item of incoming) byId.set(item.id, item);
  return [...byId.values()].sort((left, right) => left.seq - right.seq);
}

function TraceSurface({ view }: { view: MissionView }) {
  const [items, setItems] = useState<MissionItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [started, setStarted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [failedLatestSeq, setFailedLatestSeq] = useState<number | null>(null);
  const requestEpochRef = useRef(0);
  const requestInFlightRef = useRef(false);
  const observedLastItemSeqRef = useRef(view.lastItemSeq);

  useEffect(() => {
    const requestEpoch = requestEpochRef;
    const requestInFlight = requestInFlightRef;
    return () => {
      ++requestEpoch.current;
      requestInFlight.current = false;
    };
  }, []);

  const load = useCallback(async (
    nextCursor?: string | null,
    options: { refreshLatest?: boolean; observedSeq?: number } = {},
  ) => {
    if (requestInFlightRef.current) return;
    const missionId = view.missionId;
    const requestEpoch = ++requestEpochRef.current;
    requestInFlightRef.current = true;
    setLoading(true);
    setError(null);
    try {
      const page = await listMissionItems({ missionId, beforeSeq: nextCursor, limit: 30 });
      if (requestEpoch !== requestEpochRef.current) return;
      setItems((current) => (
        nextCursor || options.refreshLatest
          ? mergeTraceItems(current, page.items)
          : page.items
      ));
      if (!options.refreshLatest) setCursor(page.nextCursor);
      if (options.observedSeq !== undefined) {
        observedLastItemSeqRef.current = Math.max(
          observedLastItemSeqRef.current,
          options.observedSeq,
        );
      }
      if (options.refreshLatest) setFailedLatestSeq(null);
      setStarted(true);
    } catch {
      if (requestEpoch !== requestEpochRef.current) return;
      setError("任务轨迹暂时未能加载，请重试。");
      if (options.refreshLatest && options.observedSeq !== undefined) {
        setFailedLatestSeq(options.observedSeq);
      }
    } finally {
      if (requestEpoch === requestEpochRef.current) {
        requestInFlightRef.current = false;
        setLoading(false);
      }
    }
  }, [view.missionId]);

  useEffect(() => {
    if (!started || loading || requestInFlightRef.current) return;
    const previousSeq = observedLastItemSeqRef.current;
    if (view.lastItemSeq <= previousSeq) return;
    if (failedLatestSeq === view.lastItemSeq) return;
    void load(null, { refreshLatest: true, observedSeq: view.lastItemSeq });
  }, [failedLatestSeq, load, loading, started, view.lastItemSeq]);
  if (!started) {
    return (
      <div className="px-5 py-5" data-testid="mission-trace-idle">
        <QuietEmpty icon={History} title="按需查看任务轨迹" detail="这里展示阶段、工具与成员的语义摘要，不显示原始日志和工具 JSON。" />
        {error ? <p role="alert" className="mt-3 text-center text-xs text-[var(--wjn-error)]">{error}</p> : null}
        <button type="button" disabled={loading} onClick={() => void load(null, { observedSeq: view.lastItemSeq })} className="wjn-button-secondary mx-auto mt-4 flex h-8 items-center gap-2 px-3 text-xs disabled:opacity-45">{loading ? <LoaderCircle size={14} className="animate-spin" /> : null}{error ? "重新加载任务轨迹" : "加载任务轨迹"}</button>
      </div>
    );
  }
  return (
    <div className="px-5 py-5" data-testid="mission-trace">
      <div className="divide-y divide-[var(--wjn-line)]">
        {items.map((item) => (
          <div key={item.id} className="flex gap-3 py-3">
            <Clock3 size={14} className="mt-0.5 shrink-0 text-[var(--wjn-text-muted)]" />
            <div className="min-w-0">
              <div className="text-xs font-medium text-[var(--wjn-text)]">{item.summary ?? semanticItemLabel(item.itemType)}</div>
              <div className="mt-1 text-[10px] text-[var(--wjn-text-muted)]">{new Date(item.createdAt).toLocaleString("zh-CN")}</div>
            </div>
          </div>
        ))}
      </div>
      {error ? <p role="alert" className="mt-3 text-xs text-[var(--wjn-error)]">{error}</p> : null}
      {failedLatestSeq !== null ? (
        <button
          type="button"
          disabled={loading}
          onClick={() => void load(null, {
            refreshLatest: true,
            observedSeq: Math.max(failedLatestSeq, view.lastItemSeq),
          })}
          className="wjn-button-secondary mt-4 flex h-8 w-full items-center justify-center gap-2 text-xs disabled:opacity-45"
        >
          {loading ? <LoaderCircle size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          重试加载最新进展
        </button>
      ) : null}
      {cursor ? <button type="button" disabled={loading} onClick={() => void load(cursor)} className="wjn-button-secondary mt-4 flex h-8 w-full items-center justify-center gap-2 text-xs disabled:opacity-45">{loading ? <LoaderCircle size={14} className="animate-spin" /> : null}{error && failedLatestSeq === null ? "重试加载更早记录" : "加载更早记录"}</button> : null}
    </div>
  );
}

function semanticItemLabel(value: string): string {
  const labels: Record<string, string> = {
    stage: "研究阶段更新",
    subagent: "研究成员更新",
    evidence: "发现新材料",
    artifact: "生成新成果",
    review: "内容进入确认",
    commit: "内容保存状态更新",
  };
  return labels[value] ?? "任务进展更新";
}

function reviewItemStatusLabel(
  status: MissionView["reviewItems"][number]["status"],
  commitStatus?: MissionView["reviewItems"][number]["commitStatus"],
): string {
  if (status === "committed" || commitStatus === "committed") return "已保存";
  if (commitStatus === "applying") return "保存中";
  if (commitStatus === "failed") return "保存未完成";
  if (status === "accepted") return "已确认，待保存";
  if (status === "needs_more_evidence") return "需补证";
  if (status === "rejected") return "暂不保存";
  return "已更新";
}

function reviewMutationIssue(codes: string[]): string {
  const labels: Record<string, string> = {
    commit_in_progress: "部分内容仍在保存中",
    explicit_review_required: "部分内容需要逐项确认",
    review_item_not_accepted: "部分内容尚未确认",
    review_preview_expired: "部分预览已过期，请重新生成",
    review_preview_integrity_failed: "部分预览已变化，请重新生成",
    stale_target_precondition: "目标文档已有更新，请重新生成变更",
    target_path_conflict: "目标文件已存在，请调整后重试",
    review_source_stage_unavailable: "暂时无法定位需要补充的研究阶段，请在对话中说明要修改的部分",
    continuation_policy_changed: "研究方法已更新，请在对话中重新发起这项补充任务",
    continuation_parent_not_terminal: "当前任务仍在推进，反馈会在下一步处理",
  };
  return [...new Set(codes)].map((code) => labels[code] ?? "部分内容未能完成").join("；");
}

function StatusMark({ status }: { status: MissionView["executionStatus"] }) {
  const tone = missionStatusTone(status);
  return (
    <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${tone === "active" ? "bg-[var(--wjn-accent-soft)] text-[var(--wjn-accent)]" : tone === "success" ? "bg-[var(--wjn-success-soft)] text-[var(--wjn-success)]" : tone === "warning" ? "bg-[var(--wjn-review-soft)] text-[var(--wjn-review)]" : "bg-[var(--wjn-surface-subtle)] text-[var(--wjn-text-muted)]"}`}>
      {tone === "active" ? <LoaderCircle size={14} className="animate-spin motion-reduce:animate-none" /> : tone === "success" ? <Check size={14} /> : <CircleDot size={14} />}
    </span>
  );
}

function IconButton({ label, onClick, children }: { label: string; onClick(): void; children: ReactNode }) {
  return <button type="button" aria-label={label} title={label} onClick={onClick} className="flex h-8 w-8 items-center justify-center rounded-[var(--wjn-radius)] text-[var(--wjn-text-secondary)] hover:bg-[var(--wjn-surface-subtle)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--wjn-accent)]">{children}</button>;
}

function QuietEmpty({ icon: Icon, title, detail }: { icon: typeof History; title: string; detail: string }) {
  return <div className="mx-auto flex max-w-72 flex-col items-center py-12 text-center"><Icon size={22} className="text-[var(--wjn-text-muted)]" /><h3 className="mt-3 text-sm font-medium text-[var(--wjn-text)]">{title}</h3><p className="mt-1 text-xs leading-5 text-[var(--wjn-text-secondary)]">{detail}</p></div>;
}
