import {
  CheckCircle2,
  Database,
  PauseCircle,
  Users,
} from "lucide-react";

import type { ExecutionRecord } from "@/lib/api/types";
import { groupExecutionPhases } from "@/lib/execution-phases";
import {
  isTerminalRunStatus,
  runViewFromExecution,
  type RunViewTeam,
} from "@/lib/execution-run-view";

import { NodeInspector } from "./NodeInspector";
import { EmptyState, NodeStatusDot, StatusPill } from "./shared";
import { styles } from "./styles";
import { qualityGateLabel, qualityGateTone } from "./utils";

export function RunView({
  record,
  selectedNodeId,
  onSelectNode,
  onOpenReview,
  onOpenEvidence,
  onOpenIntervention,
}: {
  record: ExecutionRecord | null;
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string | null) => void;
  onOpenReview: () => void;
  onOpenEvidence: () => void;
  onOpenIntervention: () => void;
}) {
  if (!record) {
    return <EmptyState title="暂无当前运行" detail="当 Lead Agent 启动后，这里会显示节点进度、工具调用和产物。" />;
  }

  const view = runViewFromExecution(record);
  const phases = groupExecutionPhases(record);
  const allNodes = phases.flatMap((phase) => phase.nodes);
  const activeNodeId =
    selectedNodeId && allNodes.some((node) => node.id === selectedNodeId)
      ? selectedNodeId
      : allNodes.find((node) => record.node_states[node.id]?.status === "running")?.id ??
        allNodes[0]?.id ??
        null;
  const activeNode = allNodes.find((node) => node.id === activeNodeId) ?? null;
  const activeNodeState = activeNodeId ? record.node_states[activeNodeId] : null;
  const progress =
    typeof view.progress === "number"
      ? view.progress
      : view.nodeCount
        ? Math.round(((view.completedNodeCount ?? 0) / view.nodeCount) * 100)
        : 0;

  return (
    <div style={styles.runGrid}>
      <div style={styles.runMain}>
        <section style={{ ...styles.section, ...styles.runPrimarySection }}>
          <div style={styles.cockpitHeader}>
            <div style={{ minWidth: 0 }}>
              <div style={styles.sectionTitle}>{view.title}</div>
              <div style={styles.sectionSubtitle}>{view.summary}</div>
            </div>
            <div style={styles.cockpitActions}>
              <StatusPill status={view.status} />
              <button type="button" onClick={onOpenIntervention} disabled={isTerminalRunStatus(view.status)} style={styles.iconTextButton}>
                <PauseCircle size={14} />
                中断并补充
              </button>
            </div>
          </div>
          <div style={styles.progressOuter}>
            <div style={{ ...styles.progressInner, width: `${Math.max(4, Math.min(100, progress))}%` }} />
          </div>
          <div style={styles.progressMeta}>
            <span>{view.completedNodeCount ?? 0}/{view.nodeCount ?? 0} 节点完成</span>
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
                <div style={styles.sectionTitle}>节点时间线</div>
                <div style={styles.sectionSubtitle}>
                  可验证摘要、输入输出预览和工具调用。
                </div>
              </div>
            </div>
            {phases.length > 0 ? (
              <div style={styles.timeline}>
                {phases.map((phase) => (
                  <div key={phase.name} style={styles.phaseBlock}>
                    <div style={styles.phaseTitle}>{phase.name}</div>
                    <div style={styles.nodeGrid}>
                      {phase.nodes.map((node) => {
                        const state = record.node_states[node.id];
                        const status = state?.status ?? "pending";
                        return (
                          <button
                            key={node.id}
                            type="button"
                            onClick={() => onSelectNode(node.id)}
                            style={{
                              ...styles.nodeButton,
                              ...(node.id === activeNodeId
                                ? styles.nodeButtonActive
                                : null),
                            }}
                          >
                            <NodeStatusDot status={status} />
                            <span style={styles.nodeButtonText}>
                              {node.label ?? node.task ?? node.id}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState title="等待执行图谱" detail="图谱初始化后会自动显示节点。" compact />
            )}
          </div>
        </section>
      </div>

      <aside style={styles.inspector}>
        <NodeInspector node={activeNode} state={activeNodeState} />
      </aside>
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
            <span style={styles.sectionTitle}>执行团队</span>
          </div>
          <div style={styles.sectionSubtitle}>
            {team.members.length} 位成员 · {team.qualityGates.length} 个质量门
          </div>
        </div>
      </div>
      {team.members.length > 0 ? (
        <div style={styles.teamRows}>
          {team.members.map((member) => (
            <div key={member.id} style={styles.teamRow}>
              <div style={styles.teamMemberMain}>
                <NodeStatusDot status={member.status} />
                <div style={{ minWidth: 0 }}>
                  <div style={styles.teamMemberName}>{member.displayName}</div>
                  <div style={styles.teamMemberMeta}>
                    {member.templateId ?? member.id}
                  </div>
                </div>
              </div>
              <div style={styles.teamChipWrap}>
                {[...member.effectiveTools, ...member.effectiveSkills].slice(0, 5).map((item) => (
                  <span key={`${member.id}:${item}`} style={styles.teamChip}>
                    {item}
                  </span>
                ))}
              </div>
              <StatusPill status={member.status} />
            </div>
          ))}
        </div>
      ) : null}
      {team.qualityGates.length > 0 ? (
        <div style={styles.gateStrip}>
          {team.qualityGates.map((gate) => (
            <span key={gate.id} style={styles.gateItem}>
              <span style={styles.gateName}>{gate.id}</span>
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
