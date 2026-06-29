import {
  Activity,
  ClipboardList,
  Database,
  FileCheck2,
  PlayCircle,
} from "lucide-react";

import type { ExecutionRecord, WorkspaceCapability } from "@/lib/api/types";
import { runViewFromExecution } from "@/lib/execution-run-view";
import type { WorkspaceTypeConfig } from "@/lib/workspace-suggestions";

import { EmptyState, GuidanceNote, MetricCard, StatusPill } from "./shared";
import { styles } from "./styles";
import { isTerminalStatus } from "./utils";

export function OverviewView({
  typeConfig,
  features,
  records,
  pendingReviewCount,
  evidenceCount,
  isSending,
  onLaunchFeature,
  onOpenRun,
}: {
  typeConfig?: WorkspaceTypeConfig;
  features: WorkspaceCapability[];
  records: ExecutionRecord[];
  pendingReviewCount: number;
  evidenceCount: number;
  isSending: boolean;
  onLaunchFeature: (feature: WorkspaceCapability) => void;
  onOpenRun: (runId: string) => void;
}) {
  const runningCount = records.filter((record) => !isTerminalStatus(record.status)).length;
  const completedCount = records.filter((record) => isTerminalStatus(record.status)).length;
  const hasActivity =
    records.length > 0 || pendingReviewCount > 0 || evidenceCount > 0;
  const hasSoftwareCopyrightPack = features.some(
    (feature) => feature.id === "software_copyright_application_pack",
  );
  const hasMathModelingPack = features.some(
    (feature) => feature.id === "math_modeling_paper_pack",
  );
  const overviewCopy = hasSoftwareCopyrightPack
    ? {
        subtitle:
          "先把软件名称、形态、语言和功能重点写成澄清 Spec；确认后再生成申报材料包。",
        metaHint: "先写 Spec，确认后执行",
        guidance:
          "轻量问题可直接在左侧问；要生成完整软著材料包时，从这里进入澄清 Spec。",
        note:
          "软著材料包会按 mock 后端代码、静态前端页面截图、说明书和材料清单组织。",
      }
    : hasMathModelingPack
      ? {
          subtitle:
            "先提交赛题题面和数据附件，问津会整理建模论文包 Spec；确认后再执行。",
          metaHint: "先写 Spec，确认后执行",
          guidance:
            "没有赛题时可先在左侧讨论思路；正式生成论文包前，请先进入澄清 Spec。",
          note:
            "数模执行默认使用 Python，并按高教社杯论文格式组织模型、图表和 LaTeX 初稿。",
        }
      : {
          subtitle:
            "选择一个方向后，问津会先确认主题、材料和目标；信息足够时再启动研究团队。",
          metaHint: "先确认信息，再进入团队任务",
          guidance:
            "如果你只是想问概念、改一句话或讨论选题，直接在左侧输入即可，不需要先点能力。",
          note:
            "能力入口适合长任务：文献、写作、实验和成稿。轻量问题直接聊天，会更快。",
        };
  return (
    <div style={styles.viewStack}>
      <section style={styles.primarySection}>
        <div style={styles.sectionHeader}>
          <div>
            <div style={styles.sectionTitle}>{typeConfig?.title ?? "能力启动台"}</div>
            <div style={styles.sectionSubtitle}>
              {overviewCopy.subtitle}
            </div>
          </div>
        </div>
        {features.length > 0 ? (
          <>
            <div style={styles.featureGrid}>
              {features.slice(0, 10).map((feature) => {
                const description =
                  feature.description || "启动该能力并展示关键进展和结果";
                const descriptionId = `capability-${feature.id.replace(/[^a-zA-Z0-9_-]/g, "-")}-description`;

                return (
                  <button
                    key={feature.id}
                    type="button"
                    disabled={isSending}
                    aria-label={feature.name}
                    aria-describedby={descriptionId}
                    onClick={() => onLaunchFeature(feature)}
                    style={styles.featureButton}
                  >
                    <PlayCircle size={16} />
                    <span style={{ minWidth: 0 }}>
                      <span style={styles.featureTitle}>{feature.name}</span>
                      <span
                        id={descriptionId}
                        style={styles.featureDescription}
                      >
                        {description}
                      </span>
                      <span style={styles.featureMetaHint}>
                        {overviewCopy.metaHint}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
            <div style={styles.featureGuidance}>
              {overviewCopy.guidance}
            </div>
            <GuidanceNote>
              {overviewCopy.note}
            </GuidanceNote>
          </>
        ) : (
          <EmptyState title="暂无可启动能力" detail="能力目录加载后会显示在这里。" />
        )}
      </section>

      {hasActivity ? (
        <div style={styles.summaryStrip}>
          <MetricCard icon={Activity} label="正在处理" value={String(runningCount)} detail="进行中的任务" />
          <MetricCard icon={Database} label="证据" value={String(evidenceCount)} detail="已沉淀材料" />
          <MetricCard icon={ClipboardList} label="结果" value={String(pendingReviewCount)} detail="已写入或待处理" />
          <MetricCard icon={FileCheck2} label="最近完成" value={String(completedCount)} detail="可回看任务" />
        </div>
      ) : null}

      {records.length > 0 ? (
        <section style={styles.section}>
          <div style={styles.sectionHeader}>
            <div>
              <div style={styles.sectionTitle}>最近运行</div>
              <div style={styles.sectionSubtitle}>最近任务会保留进展、证据和写入状态。</div>
            </div>
          </div>
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
                      {view.durationLabel ?? "计时中"} · {view.completedNodeCount ?? 0}/{view.nodeCount ?? 0} 步
                    </span>
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
