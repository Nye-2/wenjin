import {
  Activity,
  ClipboardList,
  Database,
  FlaskConical,
  PlayCircle,
} from "lucide-react";

import type { ExecutionRecord, WorkspaceCapability } from "@/lib/api/types";
import { runViewFromExecution } from "@/lib/execution-run-view";
import type { WorkspaceTypeConfig } from "@/lib/workspace-suggestions";

import { EmptyState, MetricCard, StatusPill } from "./shared";
import { styles } from "./styles";
import { isTerminalStatus } from "./utils";

export function OverviewView({
  typeConfig,
  features,
  records,
  pendingReviewCount,
  evidenceCount,
  sandboxCount,
  isSending,
  onLaunchFeature,
  onOpenRun,
}: {
  typeConfig?: WorkspaceTypeConfig;
  features: WorkspaceCapability[];
  records: ExecutionRecord[];
  pendingReviewCount: number;
  evidenceCount: number;
  sandboxCount: number;
  isSending: boolean;
  onLaunchFeature: (feature: WorkspaceCapability) => void;
  onOpenRun: (runId: string) => void;
}) {
  const runningCount = records.filter((record) => !isTerminalStatus(record.status)).length;
  return (
    <div style={styles.viewStack}>
      <div style={styles.summaryGrid}>
        <MetricCard icon={Activity} label="运行中" value={String(runningCount)} detail="Lead Agent / subagent" />
        <MetricCard icon={Database} label="证据项" value={String(evidenceCount)} detail="候选结果与节点输出" />
        <MetricCard icon={ClipboardList} label="待审阅" value={String(pendingReviewCount)} detail="默认勾选，可编辑后提交" />
        <MetricCard icon={FlaskConical} label="Sandbox" value={String(sandboxCount)} detail="仅 Agent 内部可用" />
      </div>

      <section style={styles.section}>
        <div style={styles.sectionHeader}>
          <div>
            <div style={styles.sectionTitle}>{typeConfig?.title ?? "能力启动台"}</div>
            <div style={styles.sectionSubtitle}>
              从这里发起任务仍走 chat-agent 到 lead-agent 管线，实验由右侧 subagent 执行。
            </div>
          </div>
        </div>
        {features.length > 0 ? (
          <div style={styles.featureGrid}>
            {features.slice(0, 10).map((feature) => (
              <button
                key={feature.id}
                type="button"
                disabled={isSending}
                onClick={() => onLaunchFeature(feature)}
                style={styles.featureButton}
              >
                <PlayCircle size={16} />
                <span style={{ minWidth: 0 }}>
                  <span style={styles.featureTitle}>{feature.name}</span>
                  <span style={styles.featureDescription}>
                    {feature.description || "启动该能力并在右侧展示运行证据"}
                  </span>
                </span>
              </button>
            ))}
          </div>
        ) : (
          <EmptyState title="暂无可启动能力" detail="能力目录加载后会显示在这里。" />
        )}
      </section>

      <section style={styles.section}>
        <div style={styles.sectionHeader}>
          <div>
            <div style={styles.sectionTitle}>最近运行</div>
            <div style={styles.sectionSubtitle}>长任务进展和历史 trace 都在这里承接。</div>
          </div>
        </div>
        {records.length > 0 ? (
          <div style={styles.runList}>
            {records.slice(0, 6).map((record) => {
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
                    <span style={styles.runListMeta}>
                      {view.durationLabel ?? "计时中"} · {view.completedNodeCount ?? 0}/{view.nodeCount ?? 0} 节点
                    </span>
                  </span>
                  <StatusPill status={view.status} />
                </button>
              );
            })}
          </div>
        ) : (
          <EmptyState title="还没有运行记录" detail="从左侧对话或上方能力启动台发起任务后，会显示实时进度。" />
        )}
      </section>
    </div>
  );
}
