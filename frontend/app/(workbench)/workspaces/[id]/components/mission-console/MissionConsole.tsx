"use client";

import {
  Archive,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  CircleDot,
  Clock3,
  FileText,
  History,
  LoaderCircle,
  Maximize2,
  MessageCircle,
  Minimize2,
  Paperclip,
  RefreshCw,
  Search,
  Users,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { MarkdownRenderer } from "@/components/ui/markdown-renderer";
import {
  commitMissionReviews,
  decideMissionReviews,
  getMissionView,
  listMissionArtifacts,
  listMissionEvidence,
  listMissionItems,
  updateMissionReviewMode,
} from "@/lib/api/missions";
import type {
  MissionArtifactView,
  MissionEvidenceView,
  MissionItem,
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
  onViewChange(view: MissionView): void;
  onChatAction(action: MissionChatAction): void;
}

export type MissionChatAction = "focus" | "attach";

const SURFACES = [
  { id: "progress", label: "进展", icon: CircleDot },
  { id: "review", label: "确认", icon: Check },
  { id: "evidence", label: "证据", icon: BookOpen },
  { id: "artifacts", label: "成果", icon: Archive },
  { id: "trace", label: "轨迹", icon: History },
] as const;

export function MissionConsole({
  view,
  compact = false,
  onClose,
  onViewChange,
  onChatAction,
}: MissionConsoleProps) {
  const panelMode = useMissionUiStore((state) => state.panelMode);
  const surface = useMissionUiStore((state) => state.surface);
  const setSurface = useMissionUiStore((state) => state.setSurface);
  const expandMission = useMissionUiStore((state) => state.expandMission);

  if (panelMode === "peek" && !compact) {
    return (
      <aside
        className="flex h-full min-w-0 flex-col border-l border-[var(--wjn-line)] bg-[var(--wjn-surface)]"
        aria-label="研究任务概览"
        data-testid="mission-console-peek"
      >
        <MissionHeader view={view} onClose={onClose} />
        <MissionStaleNotice view={view} onViewChange={onViewChange} />
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
      <MissionStaleNotice view={view} onViewChange={onViewChange} />
      <div
        className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-[var(--wjn-line)] px-3 py-2"
        role="tablist"
        aria-label="任务视图"
      >
        {SURFACES.map(({ id, label, icon: Icon }) => {
          const count =
            id === "review"
              ? view.reviewSummary.pending + view.reviewSummary.needsMoreEvidence
              : id === "evidence"
                ? view.evidenceCount
                : id === "artifacts"
                  ? view.artifactCount
                  : 0;
          return (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={surface === id}
              onClick={() => setSurface(id)}
              className={`flex h-8 shrink-0 items-center gap-1.5 rounded-[var(--wjn-radius)] px-2.5 text-xs font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--wjn-accent)] ${
                surface === id
                  ? "bg-[var(--wjn-accent-soft)] text-[var(--wjn-accent-strong)]"
                  : "text-[var(--wjn-text-secondary)] hover:bg-[var(--wjn-surface-subtle)] hover:text-[var(--wjn-text)]"
              }`}
            >
              <Icon size={14} />
              {label}
              {count > 0 ? (
                <span className="min-w-4 rounded-full bg-[var(--wjn-surface-muted)] px-1 text-center text-[10px]">
                  {count}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {surface === "progress" ? (
          <ProgressSurface view={view} onChatAction={onChatAction} />
        ) : null}
        {surface === "review" ? (
          <ReviewSurface view={view} onViewChange={onViewChange} />
        ) : null}
        {surface === "evidence" ? <EvidenceSurface view={view} /> : null}
        {surface === "artifacts" ? <ArtifactSurface view={view} /> : null}
        {surface === "trace" ? <TraceSurface view={view} /> : null}
      </div>
    </aside>
  );
}

function MissionStaleNotice({
  view,
  onViewChange,
}: {
  view: MissionView;
  onViewChange(view: MissionView): void;
}) {
  const [retrying, setRetrying] = useState(false);
  const [retryFailed, setRetryFailed] = useState(false);
  if (!view.isStale && !view.loadError) return null;

  const retry = async () => {
    setRetrying(true);
    setRetryFailed(false);
    try {
      onViewChange(await getMissionView(view.missionId));
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
      {view.activity.attempt || view.activity.retryAt ? (
        <p className="mt-1 text-[11px] text-[var(--wjn-text-muted)]">{activityMeta(view)}</p>
      ) : null}
    </section>
  );
}

function activityStateLabel(state: MissionView["activity"]["state"]): string {
  return {
    starting: "准备中",
    working: "推进中",
    collaborating: "协作中",
    retrying: "重试中",
    recovering: "调整中",
    waiting: "等待回应",
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
  if (activity.state === "collaborating") return `${view.subagents.length} 位成员参与`;
  return activityStateLabel(activity.state);
}

function MissionHeader({ view, onClose }: { view: MissionView; onClose(): void }) {
  const panelMode = useMissionUiStore((state) => state.panelMode);
  const expandMission = useMissionUiStore((state) => state.expandMission);
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
          <span>{formatMissionDuration(view.durationSeconds)}</span>
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
}: {
  view: MissionView;
  onChatAction(action: MissionChatAction): void;
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
        <AttentionRequestCard view={view} onChatAction={onChatAction} />
      ) : null}
      {!view.attentionRequest ? <MissionActivity view={view} /> : null}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-xs font-semibold text-[var(--wjn-text)]">当前推进</h3>
          <span className="text-[11px] text-[var(--wjn-text-muted)]">
            {view.stages.filter((stage) => stage.status === "passed").length}/{view.stages.length}
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
      {view.subagents.length ? (
        <section className="border-t border-[var(--wjn-line)] pt-5">
          <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold text-[var(--wjn-text)]">
            <Users size={14} /> 研究成员
          </h3>
          <div className="space-y-3">
            {view.subagents.map((member) => (
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
                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--wjn-text-muted)]">
                      {member.summary}
                    </p>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}
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

function AttentionRequestCard({
  view,
  onChatAction,
}: {
  view: MissionView;
  onChatAction(action: MissionChatAction): void;
}) {
  const request = view.attentionRequest;
  const setSurface = useMissionUiStore((state) => state.setSurface);
  if (!request) return null;

  const runAction = (actionType: (typeof request.actions)[number]["actionType"]) => {
    if (actionType === "open_review") {
      setSurface("review");
      return;
    }
    if (actionType === "upload_file") {
      onChatAction("attach");
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
            onClick={() => runAction(action.actionType)}
            className={`h-8 px-3 text-xs font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--wjn-accent)] ${action.primary ? "bg-[var(--wjn-accent)] text-white hover:bg-[var(--wjn-accent-strong)]" : "border border-[var(--wjn-line)] bg-[var(--wjn-surface)] text-[var(--wjn-text)] hover:bg-[var(--wjn-surface-subtle)]"}`}
          >
            {action.label}
          </button>
        ))}
      </div>
    </section>
  );
}

function ReviewSurface({
  view,
  onViewChange,
}: {
  view: MissionView;
  onViewChange(view: MissionView): void;
}) {
  const selected = useMissionUiStore((state) => state.selectedReviewItemIds);
  const toggleReviewItem = useMissionUiStore((state) => state.toggleReviewItem);
  const selectionRevisionRef = useRef<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = view.reviewItems.filter((item) => item.status === "pending");

  useEffect(() => {
    if (selectionRevisionRef.current !== view.reviewSelectionRevision) {
      selectionRevisionRef.current = view.reviewSelectionRevision;
      replaceReviewSelection(suggestedReviewSelection(view));
    }
  }, [view]);

  const selectedPending = pending.filter((item) => selected.has(item.id));
  const selectedHasProtected = selectedPending.some((item) => !item.batchAcceptable);

  const decide = async (decision: "accepted" | "rejected" | "needs_more_evidence") => {
    if (!selectedPending.length || (decision === "accepted" && selectedHasProtected)) return;
    setBusy(true);
    setError(null);
    try {
      const next = await decideMissionReviews({
        missionId: view.missionId,
        decisions: selectedPending.map((item) => ({ reviewItemId: item.id, decision })),
      });
      onViewChange(next);
      replaceReviewSelection([]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "确认失败");
    } finally {
      setBusy(false);
    }
  };

  const decideOne = async (
    reviewItemId: string,
    decision: "accepted" | "rejected" | "needs_more_evidence",
  ) => {
    setBusy(true);
    setError(null);
    try {
      const next = await decideMissionReviews({
        missionId: view.missionId,
        decisions: [{ reviewItemId, decision }],
      });
      onViewChange(next);
      replaceReviewSelection([]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "确认失败");
    } finally {
      setBusy(false);
    }
  };

  const saveAccepted = async () => {
    const accepted = view.reviewItems.filter((item) => item.status === "accepted");
    if (!accepted.length) return;
    setBusy(true);
    setError(null);
    try {
      onViewChange(
        await commitMissionReviews({
          missionId: view.missionId,
          reviewItemIds: accepted.map((item) => item.id),
        }),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败");
    } finally {
      setBusy(false);
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
        <ReviewModeSelect view={view} onViewChange={onViewChange} />
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
                    onChange={() => toggleReviewItem(item.id)}
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
          {view.reviewSummary.needsMoreEvidence} 项内容还需要补充证据，暂不会写入工作区。
        </div>
      ) : null}
      {view.reviewItems.some((item) => item.status !== "pending" && item.status !== "superseded") ? (
        <div className="mt-4 border-t border-[var(--wjn-line)] pt-3">
          <h4 className="mb-2 text-xs font-semibold text-[var(--wjn-text)]">已处理内容</h4>
          <div className="divide-y divide-[var(--wjn-line)]">
            {view.reviewItems.filter((item) => item.status !== "pending" && item.status !== "superseded").map((item) => (
              <div key={item.id} className="flex items-center justify-between gap-3 py-2.5 text-xs">
                <span className="min-w-0 truncate text-[var(--wjn-text-secondary)]">{item.title}</span>
                <span className={item.status === "committed" ? "text-[var(--wjn-success)]" : item.status === "needs_more_evidence" ? "text-[var(--wjn-review)]" : "text-[var(--wjn-text-muted)]"}>
                  {reviewItemStatusLabel(item.status, item.commitStatus)}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {error ? <p className="mt-3 text-xs text-[var(--wjn-error)]">{error}</p> : null}
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
          disabled={busy || view.reviewSummary.accepted === 0}
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

function ReviewModeSelect({ view, onViewChange }: { view: MissionView; onViewChange(view: MissionView): void }) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const labels: Record<MissionReviewMode, string> = {
    review_all: "每项确认",
    balanced_default: "平衡模式",
    auto_draft: "草稿自动保存",
  };
  const change = async (mode: MissionReviewMode) => {
    setOpen(false);
    setError(null);
    try {
      onViewChange(await updateMissionReviewMode(view.missionId, mode));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "确认方式更新失败");
    }
  };
  return (
    <div className="relative">
      <button
        type="button"
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
            <button key={mode} type="button" role="menuitem" onClick={() => void change(mode)} className="flex w-full items-center justify-between rounded px-2.5 py-2 text-left text-xs hover:bg-[var(--wjn-surface-subtle)]">
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

  useEffect(() => {
    setEvidenceItems(view.evidenceItems);
    setNextCursor(view.evidenceNextCursor ?? null);
  }, [view.evidenceItems, view.evidenceNextCursor, view.missionId]);

  const items = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return evidenceItems;
    return evidenceItems.filter((item) =>
      [item.title, item.summary, item.sourceLabel].some((value) => value?.toLowerCase().includes(needle)),
    );
  }, [evidenceItems, query]);

  const loadMore = async () => {
    if (nextCursor === null || loadingMore) return;
    setLoadingMore(true);
    setLoadError(null);
    try {
      const page = await listMissionEvidence({ missionId: view.missionId, cursor: nextCursor });
      setEvidenceItems((current) => appendUnique(current, page.items));
      setNextCursor(page.nextCursor);
    } catch (reason) {
      setLoadError(reason instanceof Error ? reason.message : "更多证据加载失败");
    } finally {
      setLoadingMore(false);
    }
  };

  return (
    <div className="px-5 py-5" data-testid="mission-evidence">
      <label className="flex h-9 items-center gap-2 rounded-[var(--wjn-radius)] border border-[var(--wjn-line)] px-3 focus-within:border-[var(--wjn-accent-line)]">
        <Search size={14} className="text-[var(--wjn-text-muted)]" />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="查找证据" className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-[var(--wjn-text-muted)]" />
      </label>
      {items.length ? (
        <div className="mt-3 divide-y divide-[var(--wjn-line)]">
          {items.map((item) => (
            <article key={item.id} className="py-4">
              <div className="flex items-start gap-3">
                <BookOpen size={15} className="mt-0.5 shrink-0 text-[var(--wjn-evidence)]" />
                <div className="min-w-0 flex-1">
                  <h4 className="text-sm font-medium leading-5 text-[var(--wjn-text)]">{item.title}</h4>
                  <div className="mt-1 text-[11px] text-[var(--wjn-text-muted)]">{item.sourceLabel ?? item.sourceType}</div>
                  {item.summary ? <p className="mt-2 text-xs leading-5 text-[var(--wjn-text-secondary)]">{item.summary}</p> : null}
                </div>
              </div>
            </article>
          ))}
        </div>
      ) : <QuietEmpty icon={BookOpen} title="还没有沉淀证据" detail="可核验的论文、网页、数据和上传材料会汇总在这里。" />}
      {loadError ? <p className="mt-3 text-xs text-[var(--wjn-error)]">{loadError}</p> : null}
      {nextCursor !== null && !query.trim() ? (
        <button type="button" disabled={loadingMore} onClick={() => void loadMore()} className="wjn-button-secondary mt-3 h-8 w-full text-xs disabled:opacity-45">
          {loadingMore ? "正在加载…" : `加载更多证据（已显示 ${evidenceItems.length}/${view.evidenceCount}）`}
        </button>
      ) : null}
    </div>
  );
}

function ArtifactSurface({ view }: { view: MissionView }) {
  const [artifactItems, setArtifactItems] = useState<MissionArtifactView[]>(view.artifactItems);
  const [nextCursor, setNextCursor] = useState<number | null>(view.artifactNextCursor ?? null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    setArtifactItems(view.artifactItems);
    setNextCursor(view.artifactNextCursor ?? null);
  }, [view.artifactItems, view.artifactNextCursor, view.missionId]);

  const loadMore = async () => {
    if (nextCursor === null || loadingMore) return;
    setLoadingMore(true);
    setLoadError(null);
    try {
      const page = await listMissionArtifacts({
        missionId: view.missionId,
        cursor: nextCursor,
      });
      setArtifactItems((current) => appendUnique(current, page.items));
      setNextCursor(page.nextCursor);
    } catch (reason) {
      setLoadError(reason instanceof Error ? reason.message : "更多成果加载失败");
    } finally {
      setLoadingMore(false);
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

function replaceReviewSelection(ids: string[]): void {
  useMissionUiStore.setState({ selectedReviewItemIds: new Set(ids) });
}

function TraceSurface({ view }: { view: MissionView }) {
  const [items, setItems] = useState<MissionItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [started, setStarted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = async (nextCursor?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listMissionItems({ missionId: view.missionId, cursor: nextCursor, limit: 30 });
      setItems((current) => (nextCursor ? [...current, ...page.items] : page.items));
      setCursor(page.nextCursor);
      setStarted(true);
    } catch {
      setError("任务轨迹暂时未能加载，请重试。");
    } finally {
      setLoading(false);
    }
  };
  if (!started) {
    return (
      <div className="px-5 py-5" data-testid="mission-trace-idle">
        <QuietEmpty icon={History} title="按需查看任务轨迹" detail="这里展示阶段、工具与成员的语义摘要，不显示原始日志和工具 JSON。" />
        {error ? <p role="alert" className="mt-3 text-center text-xs text-[var(--wjn-error)]">{error}</p> : null}
        <button type="button" disabled={loading} onClick={() => void load(null)} className="wjn-button-secondary mx-auto mt-4 flex h-8 items-center gap-2 px-3 text-xs disabled:opacity-45">{loading ? <LoaderCircle size={14} className="animate-spin" /> : null}{error ? "重新加载任务轨迹" : "加载任务轨迹"}</button>
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
      {cursor ? <button type="button" disabled={loading} onClick={() => void load(cursor)} className="wjn-button-secondary mt-4 flex h-8 w-full items-center justify-center gap-2 text-xs">{loading ? <LoaderCircle size={14} className="animate-spin" /> : null}{error ? "重试加载更早记录" : "加载更早记录"}</button> : null}
    </div>
  );
}

function semanticItemLabel(value: string): string {
  const labels: Record<string, string> = {
    stage: "研究阶段更新",
    subagent: "研究成员更新",
    evidence: "发现新证据",
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
