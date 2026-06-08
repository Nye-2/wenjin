import {
  CheckCircle2,
  Database,
  Users,
} from "lucide-react";

import type { ExecutionRecord } from "@/lib/api/types";
import {
  buildRunProgressItems,
  runViewFromExecution,
  type RunProgressItem,
  type RunViewTeam,
} from "@/lib/execution-run-view";

import { NodeInspector } from "./NodeInspector";
import { EmptyState, NodeStatusDot } from "./shared";
import { styles } from "./styles";
import { qualityGateLabel, qualityGateTone, statusTone } from "./utils";

export function RunView({
  record,
  selectedNodeId,
  onSelectNode,
  onOpenReview,
  onOpenEvidence,
}: {
  record: ExecutionRecord | null;
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string | null) => void;
  onOpenReview: () => void;
  onOpenEvidence: () => void;
}) {
  if (!record) {
    return <EmptyState title="还没有进行中的任务" detail="在左侧描述任务后，问津会自动组织团队，并在这里展示关键进展和可审阅结果。" />;
  }

  const view = runViewFromExecution(record);
  const progressItems = buildRunProgressItems(record);
  const progressGroups = groupProgressItems(progressItems);
  const activeNodeId =
    selectedNodeId && progressItems.some((node) => node.id === selectedNodeId)
      ? selectedNodeId
      : progressItems.find((node) => record.node_states[node.id]?.status === "running")?.id ??
        progressItems[0]?.id ??
        null;
  const activeNode =
    record.graph_structure?.nodes.find((node) => node.id === activeNodeId) ??
    (activeNodeId
      ? {
          id: activeNodeId,
          type: record.node_states[activeNodeId]?.node_type ?? "node",
          label: record.node_states[activeNodeId]?.label ?? undefined,
        }
      : null);
  const activeNodeState = activeNodeId ? record.node_states[activeNodeId] : null;
  const progress =
    typeof view.progress === "number"
      ? view.progress
      : view.nodeCount
        ? Math.round(((view.completedNodeCount ?? 0) / view.nodeCount) * 100)
        : 0;

  return (
    <div style={styles.runStack}>
      <section style={{ ...styles.section, ...styles.runPrimarySection }}>
        <div style={styles.cockpitHeader}>
          <div style={{ minWidth: 0 }}>
            <div style={styles.sectionTitle}>{view.title}</div>
            <div style={styles.sectionSubtitle}>{view.summary}</div>
          </div>
        </div>
        <div style={styles.progressOuter}>
          <div style={{ ...styles.progressInner, width: `${Math.max(4, Math.min(100, progress))}%` }} />
        </div>
        <div style={styles.progressMeta}>
          <span>{view.completedNodeCount ?? 0}/{view.nodeCount ?? 0} 步完成</span>
          <span>{view.durationLabel ?? "计时中"}</span>
        </div>
        <div style={styles.quickActions}>
          <button type="button" onClick={onOpenEvidence} style={styles.secondaryButton}>
            <Database size={14} />
            查看证据
          </button>
          <button type="button" onClick={onOpenReview} style={styles.secondaryButton}>
            <CheckCircle2 size={14} />
            进入审阅
          </button>
        </div>

        {view.team ? <TeamRoster team={view.team} /> : null}

        <div style={styles.timelinePanel}>
          <div style={styles.sectionHeaderCompact}>
            <div>
              <div style={styles.sectionTitle}>任务进展</div>
              <div style={styles.sectionSubtitle}>
                默认只展示用户需要理解的工作状态，技术输入输出已收进运行详情。
              </div>
            </div>
          </div>
          {progressGroups.length > 0 ? (
            <div style={styles.timeline}>
              {progressGroups.map((phase) => (
                <div key={phase.name} style={styles.phaseBlock}>
                  <div style={styles.phaseTitle}>{phase.name}</div>
                  <div style={styles.progressStepList}>
                    {phase.items.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => onSelectNode(item.id)}
                        style={{
                          ...styles.progressStepButton,
                          ...(item.id === activeNodeId
                            ? styles.progressStepButtonActive
                            : null),
                        }}
                      >
                        <NodeStatusDot status={item.status} />
                        <span style={styles.progressStepMain}>
                          <span style={styles.progressStepTitle}>{item.title}</span>
                          {item.detail ? (
                            <span style={styles.progressStepDetail}>{item.detail}</span>
                          ) : null}
                        </span>
                        <span style={styles.progressStepStatus}>
                          {workItemStatusLabel(item.status)}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="正在准备任务" detail="问津会在启动后展示关键进展。" compact />
          )}
        </div>

        <details style={styles.runDetails}>
          <summary style={styles.runDetailsSummary}>运行详情</summary>
          <NodeInspector node={activeNode} state={activeNodeState} />
        </details>
      </section>
    </div>
  );
}

function TeamRoster({ team }: { team: RunViewTeam }) {
  if (team.members.length === 0 && team.qualityGates.length === 0) {
    return null;
  }
  return (
    <section role="region" aria-label="执行团队" style={styles.teamPanel}>
      <div style={styles.sectionHeaderCompact}>
        <div style={{ minWidth: 0 }}>
          <div style={styles.teamTitleLine}>
            <Users size={15} />
            <span style={styles.sectionTitle}>研究团队</span>
          </div>
          <div style={styles.sectionSubtitle}>
            {team.members.length} 个团队成员 · {team.qualityGates.length} 个质量检查
          </div>
        </div>
      </div>
      {team.members.length > 0 ? (
        <div style={styles.teamRows}>
          {team.members.map((member) => (
            <div
              key={member.id}
              style={{
                ...styles.teamRow,
                borderLeft: `3px solid ${teamStatusStripe(member.status)}`,
              }}
            >
              <div style={styles.teamMemberMain}>
                <NodeStatusDot status={member.status} />
                <div style={{ minWidth: 0 }}>
                  <div style={styles.teamMemberName}>{member.displayName}</div>
                  <div style={styles.teamMemberMeta}>
                    {memberCapabilitySummary(member)}
                  </div>
                </div>
              </div>
              <TeamMemberStatusPill status={member.status} />
            </div>
          ))}
        </div>
      ) : null}
      {team.qualityGates.length > 0 ? (
        <div style={styles.gateStrip}>
          {team.qualityGates.map((gate) => (
            <span key={gate.id} style={styles.gateItem}>
              <span style={styles.gateName}>{qualityGateDisplayName(gate.id)}</span>
              <span
                style={{
                  ...styles.gateBadge,
                  ...qualityGateTone(gate.status),
                }}
              >
                {qualityGateLabel(gate.status)}
              </span>
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function teamStatusStripe(status: string) {
  if (status === "completed" || status === "passed" || status === "pass") {
    return "var(--wjn-evidence)";
  }
  if (status === "failed" || status === "fail" || status === "failed_partial") {
    return "var(--wjn-error)";
  }
  if (status === "review" || status === "warning") {
    return "var(--wjn-review)";
  }
  if (status === "running" || status === "launching") {
    return "var(--wjn-blue)";
  }
  return "var(--wjn-line-strong)";
}

function groupProgressItems(items: RunProgressItem[]): Array<{
  name: string;
  items: RunProgressItem[];
}> {
  const groups: Array<{ name: string; items: RunProgressItem[] }> = [];
  for (const item of items) {
    const last = groups[groups.length - 1];
    if (last?.name === item.phaseTitle) {
      last.items.push(item);
      continue;
    }
    groups.push({ name: item.phaseTitle, items: [item] });
  }
  return groups;
}

function memberCapabilitySummary(member: RunViewTeam["members"][number]): string {
  if (member.activityLabel) return member.activityLabel;
  const count = member.effectiveTools.length + member.effectiveSkills.length;
  if (count > 0) return "能力已就绪";
  if (member.status === "running" || member.status === "launching") return "正在处理";
  if (member.status === "completed") return "已完成";
  return "按任务需要待命";
}

function TeamMemberStatusPill({ status }: { status: string }) {
  return (
    <span style={{ ...styles.statusPill, ...statusTone(status) }}>
      {workItemStatusLabel(status)}
    </span>
  );
}

function workItemStatusLabel(status: string): string {
  if (status === "launching") return "准备中";
  if (status === "queued" || status === "pending") return "待处理";
  if (status === "running" || status === "cancelling") return "处理中";
  if (status === "completed") return "已完成";
  if (status === "failed_partial") return "部分完成";
  if (status === "failed") return "异常";
  if (status === "cancelled") return "已取消";
  return status || "未知";
}

function qualityGateDisplayName(id: string): string {
  const normalized = id.toLowerCase().replace(/[^a-z0-9]+/g, "_");
  if (normalized.includes("evidence") || normalized.includes("trace")) {
    return "证据可追溯";
  }
  if (normalized.includes("novelty") || normalized.includes("contribution")) {
    return "创新点检查";
  }
  if (normalized.includes("citation") || normalized.includes("reference")) {
    return "引文规范";
  }
  if (normalized.includes("quality") || normalized.includes("review")) {
    return "质量审阅";
  }
  return "质量检查";
}
