import {
  Activity,
  ArrowRight,
  ClipboardList,
  Database,
  History,
} from "lucide-react";

import type { ExecutionRecord } from "@/lib/api/types";
import type { RunViewMissionState } from "@/lib/execution-run-view";
import { runViewFromExecution } from "@/lib/execution-run-view";
import type { WorkspaceTypeConfig } from "@/lib/workspace-suggestions";

import { EmptyState, MetricCard, StatusPill } from "./shared";
import { styles } from "./styles";
import { isTerminalStatus } from "./utils";

interface OverviewViewProps {
  typeConfig?: WorkspaceTypeConfig;
  mission: RunViewMissionState | null;
  records: ExecutionRecord[];
  pendingReviewCount: number;
  evidenceCount: number;
  hasMissionActivity: boolean;
  onOpenRun: (runId: string) => void;
}

export function OverviewView({
  typeConfig,
  mission,
  records,
  pendingReviewCount,
  evidenceCount,
  hasMissionActivity,
  onOpenRun,
}: OverviewViewProps) {
  const runningCount = records.filter((record) => !isTerminalStatus(record.status)).length;
  const completedCount = records.filter((record) => isTerminalStatus(record.status)).length;
  const latestRun = records[0] ?? null;
  const recentRuns = records.slice(0, 4);
  const nextAction = mission?.nextActions[0] ?? mission?.openQuestions[0] ?? null;

  return (
    <div style={styles.viewStack}>
      <section style={styles.primarySection}>
        <div style={styles.sectionHeader}>
          <div>
            <div style={styles.sectionTitle}>{typeConfig?.title ?? "研究工作台"}</div>
            <div style={styles.sectionSubtitle}>
              {mission?.statusLine ??
                (hasMissionActivity
                  ? "右侧会跟随运行、证据和复核状态持续更新。"
                  : "任务启动后，这里会汇总当前进度、证据和复核动作。")}
            </div>
          </div>
          {latestRun ? (
            <button
              type="button"
              onClick={() => onOpenRun(latestRun.id)}
              style={styles.missionActionButton}
            >
              打开当前运行
              <ArrowRight size={14} />
            </button>
          ) : null}
        </div>

        {mission ? (
          <div style={styles.missionConsole}>
            <div style={styles.missionHeader}>
              <div style={styles.missionLabel}>当前任务</div>
              <div style={styles.missionTitleRow}>
                <div style={styles.missionTitle}>{mission.title}</div>
                {latestRun ? <StatusPill status={latestRun.status} /> : null}
              </div>
              <div style={styles.missionGoal}>{mission.goal}</div>
            </div>

            <div style={styles.missionStageRow}>
              {mission.stages.map((stage) => (
                <div
                  key={stage.id}
                  style={{
                    ...styles.missionStageChip,
                    ...(stage.status === "running"
                      ? styles.missionStageChipActive
                      : stage.status === "completed"
                        ? styles.missionStageChipDone
                        : stage.status === "review"
                          ? styles.missionStageChipReview
                          : stage.status === "blocked"
                            ? styles.missionStageChipBlocked
                            : null),
                  }}
                >
                  {stage.label}
                </div>
              ))}
            </div>

            <div style={styles.summaryStrip}>
              <MetricCard
                icon={Activity}
                label="阶段"
                value={mission.currentStageLabel}
                detail="当前推进位置"
              />
              <MetricCard
                icon={Database}
                label="证据"
                value={String(mission.evidenceSummary.used)}
                detail={`已发现 ${mission.evidenceSummary.found} · 风险 ${mission.evidenceSummary.risky}`}
              />
              <MetricCard
                icon={ClipboardList}
                label="复核"
                value={String(mission.reviewSummary.pending)}
                detail={`阻塞 ${mission.reviewSummary.blockers} · 待确认 ${mission.reviewSummary.needsConfirmation}`}
              />
            </div>

            {nextAction ? (
              <div style={styles.missionNextAction}>
                <span style={styles.missionLabel}>下一步</span>
                <span style={styles.missionNextActionText}>{nextAction}</span>
              </div>
            ) : null}
          </div>
        ) : hasMissionActivity ? (
          <div style={styles.missionIdleState}>
            <div style={styles.missionLabel}>当前任务</div>
            <div style={styles.sectionSubtitle}>
              右侧会随着运行、证据和复核状态更新；先打开最近一次任务即可继续查看。
            </div>
          </div>
        ) : (
          <EmptyState
            title="等待左侧发起研究任务"
            detail="还没有正在执行的研究任务。直接在左侧描述你想推进的论文、实验或材料。"
          />
        )}

        {latestRun && (records.length > 0 || evidenceCount > 0) ? (
          <div style={styles.missionActionRow}>
            {records.length > 0 ? (
              <button
                type="button"
                onClick={() => onOpenRun(latestRun.id)}
                style={styles.missionActionButton}
              >
                <History size={14} />
                查看最近运行
              </button>
            ) : null}
            {evidenceCount > 0 ? (
              <button
                type="button"
                onClick={() => onOpenRun(latestRun.id)}
                style={styles.missionActionButton}
              >
                <Database size={14} />
                查看证据摘要
              </button>
            ) : null}
          </div>
        ) : null}
      </section>

      {hasMissionActivity ? (
        <div style={styles.summaryStrip}>
          <MetricCard icon={Activity} label="正在处理" value={String(runningCount)} detail="进行中的任务" />
          <MetricCard icon={Database} label="证据" value={String(evidenceCount)} detail="已沉淀材料" />
          <MetricCard icon={ClipboardList} label="结果" value={String(pendingReviewCount)} detail="待复核或待保存" />
          <MetricCard icon={History} label="最近完成" value={String(completedCount)} detail="可回看任务" />
        </div>
      ) : null}

      {recentRuns.length > 0 ? (
        <section style={styles.section}>
          <div style={styles.sectionHeader}>
            <div>
              <div style={styles.sectionTitle}>最近运行</div>
              <div style={styles.sectionSubtitle}>最近任务会保留进展、证据和写入状态。</div>
            </div>
          </div>
          <div style={styles.runList}>
            {recentRuns.map((record) => {
              const view = runViewFromExecution(record);
              return (
                <button
                  key={record.id}
                  type="button"
                  onClick={() => onOpenRun(record.id)}
                  style={styles.runListItem}
                >
                  <span style={styles.runListMain}>
                    <span style={styles.runListTitle}>{view.title}</span>
                    <span style={styles.runListMeta}>{view.summary}</span>
                  </span>
                  <StatusPill status={view.status} />
                </button>
              );
            })}
          </div>
        </section>
      ) : null}
    </div>
  );
}
