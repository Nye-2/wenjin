import {
  ArrowLeft,
  CheckCircle2,
  Database,
  Eye,
  ExternalLink,
  RotateCcw,
  Users,
} from "lucide-react";
import { useState } from "react";

import type { ExecutionRecord } from "@/lib/api/types";
import type { CommittedRoomLink } from "@/lib/execution-commit";
import {
  buildRunProgressItems,
  runViewFromExecution,
  type RunProgressItem,
  type RunViewTeam,
  type RunViewTeamMember,
  type RunViewTeamMemberPreviewItem,
} from "@/lib/execution-run-view";
import { useRunUiStore } from "@/stores/run-ui-store";

import { NodeInspector } from "./NodeInspector";
import { EmptyState, GuidanceNote, NodeStatusDot } from "./shared";
import { styles } from "./styles";
import { qualityGateLabel, qualityGateTone, statusTone } from "./utils";

export interface RunWritebackStatus {
  committed: boolean;
  discarded: boolean;
  reverted: boolean;
  committing: boolean;
  reverting: boolean;
  error: string | null;
  links: CommittedRoomLink[];
  canSave: boolean;
  saveCount: number;
  onSave: () => void;
  onUndo: () => void;
}

export function RunView({
  record,
  selectedNodeId,
  writeback,
  onSelectNode,
  onOpenEvidence,
}: {
  record: ExecutionRecord | null;
  selectedNodeId: string | null;
  writeback?: RunWritebackStatus;
  onSelectNode: (nodeId: string | null) => void;
  onOpenEvidence: () => void;
}) {
  if (!record) {
    return <EmptyState title="还没有进行中的任务" detail="在左侧描述任务后，问津会自动组织团队，并在这里展示关键进展和写入状态。" />;
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
  const progressScale = Math.max(4, Math.min(100, progress)) / 100;

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
          <div style={{ ...styles.progressInner, transform: `scaleX(${progressScale})` }} />
        </div>
        <div style={styles.progressMeta}>
          <span>{view.completedNodeCount ?? 0}/{view.nodeCount ?? 0} 步完成</span>
          <span>{view.durationLabel ?? "计时中"}</span>
        </div>
        {view.failureMessage ? (
          <GuidanceNote tone="warning">
            {view.failureMessage} 可以在左侧补充材料，或要求问津改用联网搜索继续。
          </GuidanceNote>
        ) : null}
        <div style={styles.quickActions}>
          <button type="button" onClick={onOpenEvidence} style={styles.secondaryButton}>
            <Database size={14} />
            查看证据
          </button>
        </div>
        {writeback ? <WritebackStatus writeback={writeback} /> : null}
        <GuidanceNote>
          这里展示的是用户需要理解的关键进展；更细的输入、工具调用和技术日志收在“运行详情”里。
        </GuidanceNote>

        {view.qualityHighlights.length > 0 ? (
          <QualityHighlights highlights={view.qualityHighlights} />
        ) : null}

        {view.team ? <TeamRoster team={view.team} /> : null}

        <div style={styles.timelinePanel}>
          <div style={styles.sectionHeaderCompact}>
            <div>
              <div style={styles.sectionTitle}>任务进展</div>
              <div style={styles.sectionSubtitle}>
                专家会按阶段更新关键摘录，完成后的文档和资料会进入审核保存流程。
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

export function WritebackStatus({
  writeback,
}: {
  writeback: RunWritebackStatus;
}) {
  const label = writeback.reverting
    ? "正在撤回本次保存..."
    : writeback.reverted
      ? "已撤回本次保存"
      : writeback.discarded
        ? "已暂不保存"
        : writeback.committed
          ? "已写入工作区"
          : writeback.committing
            ? "正在写入工作区..."
            : writeback.error
              ? "保存状态异常"
              : "待复核保存";
  const saveButtonLabel = writeback.committing
    ? "保存中..."
    : writeback.error
      ? `重试保存（${writeback.saveCount} 项）`
      : `保存到工作区（${writeback.saveCount} 项）`;

  return (
    <div
      style={{
        ...styles.writebackBox,
        ...(writeback.committed
          ? styles.writebackBoxCommitted
          : writeback.error
            ? styles.writebackBoxError
            : null),
      }}
    >
      <div
        style={styles.writebackMain}
        role="status"
        aria-label="保存状态"
        aria-live="polite"
        aria-atomic="true"
      >
        <CheckCircle2 size={14} />
        <span>{label}</span>
      </div>
      <div style={styles.writebackActions}>
        {writeback.canSave && !writeback.committed && !writeback.discarded ? (
          <button
            type="button"
            onClick={writeback.onSave}
            disabled={writeback.committing || writeback.reverting}
            style={styles.inlineGhostButton}
            aria-label={saveButtonLabel}
          >
            {saveButtonLabel}
          </button>
        ) : null}
        {writeback.committed && !writeback.reverted ? (
          <button
            type="button"
            onClick={writeback.onUndo}
            disabled={writeback.reverting}
            style={styles.inlineGhostButton}
            aria-label="撤回本次保存"
          >
            <RotateCcw size={13} />
            撤回本次保存
          </button>
        ) : null}
      </div>
      {writeback.error ? (
        <div style={styles.writebackError}>{writeback.error}</div>
      ) : null}
      {writeback.links.length > 0 ? (
        <div style={styles.writebackLinks}>
          {writeback.links.slice(0, 4).map((link) => (
            <a key={link.key} href={link.href} style={styles.writebackLink}>
              <ExternalLink size={12} />
              {link.label}
            </a>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function QualityHighlights({
  highlights,
}: {
  highlights: ReturnType<typeof runViewFromExecution>["qualityHighlights"];
}) {
  return (
    <div style={styles.gateStrip} aria-label="质量摘要">
      {highlights.map((item) => (
        <span key={`${item.label}:${item.detail}`} style={styles.gateItem}>
          <span style={styles.gateName}>{item.label}</span>
          <span
            style={{
              ...styles.gateBadge,
              ...qualityGateTone(item.status),
            }}
          >
            {item.detail}
          </span>
        </span>
      ))}
    </div>
  );
}

function TeamRoster({ team }: { team: RunViewTeam }) {
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null);
  const [selectedPreviewId, setSelectedPreviewId] = useState<string | null>(null);
  const focusedPreviewItemId = useRunUiStore((state) => state.focusedPreviewItemId);
  const focusPreviewItem = useRunUiStore((state) => state.focusPreviewItem);
  const focusedPreviewExists = focusedPreviewItemId
    ? team.members.some((member) =>
        member.previewItems.some((item) => item.id === focusedPreviewItemId),
      )
    : false;
  const activePreviewId = focusedPreviewExists
    ? focusedPreviewItemId
    : selectedPreviewId;
  const selectedMember = selectedMemberId
    && !activePreviewId
    ? team.members.find((member) => member.id === selectedMemberId) ?? null
    : null;
  const selectedPreview =
    activePreviewId
      ? team.members
        .flatMap((member) => member.previewItems)
        .find((item) => item.id === activePreviewId) ?? null
      : null;

  if (team.members.length === 0 && team.qualityGates.length === 0) {
    return null;
  }
  if (selectedPreview) {
    return (
      <TeamPreviewFullscreen
        preview={selectedPreview}
        onBack={() => {
          setSelectedPreviewId(null);
          if (focusedPreviewItemId === selectedPreview.id) {
            focusPreviewItem(null);
          }
        }}
      />
    );
  }
  if (selectedMember) {
    return (
      <ExpertDetail
        member={selectedMember}
        onBack={() => setSelectedMemberId(null)}
        onOpenPreview={setSelectedPreviewId}
      />
    );
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
                borderColor: teamStatusColor(member.status),
              }}
            >
              <div style={styles.teamMemberMain}>
                <span
                  aria-hidden="true"
                  style={{
                    ...styles.teamStatusDot,
                    background: teamStatusColor(member.status),
                  }}
                />
                <span style={expertAvatarStyle(member)}>{member.expertProfile?.avatarLabel ?? member.displayName.slice(0, 1)}</span>
                <div style={{ minWidth: 0 }}>
                  <div style={styles.teamMemberName}>{member.displayName}</div>
                  <div style={styles.teamMemberMeta}>
                    {memberCapabilitySummary(member)}
                  </div>
                  {member.latestSnapshot?.body ? (
                    <div style={expertSnapshotBodyStyle}>{member.latestSnapshot.body}</div>
                  ) : null}
                  {member.latestSnapshot?.chips.length ? (
                    <div style={expertChipRowStyle}>
                      {member.latestSnapshot.chips.slice(0, 3).map((chip) => (
                        <span key={`${member.id}:${chip.label}:${chip.value ?? ""}`} style={expertChipStyle}>
                          {chip.label}{chip.value ? ` ${chip.value}` : ""}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
              <div style={expertCardActionsStyle}>
                {member.previewItems.length > 0 ? (
                  <button
                    type="button"
                    style={expertIconButtonStyle}
                    onClick={() => setSelectedPreviewId(member.previewItems[member.previewItems.length - 1]?.id ?? null)}
                    aria-label="打开预览"
                    title="打开预览"
                  >
                    <Eye size={13} />
                    {member.previewItems.length}
                  </button>
                ) : null}
                <button
                  type="button"
                  style={expertTextButtonStyle}
                  onClick={() => setSelectedMemberId(member.id)}
                >
                  详情
                </button>
                <TeamMemberStatusPill status={member.status} />
              </div>
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

function ExpertDetail({
  member,
  onBack,
  onOpenPreview,
}: {
  member: RunViewTeamMember;
  onBack: () => void;
  onOpenPreview: (previewId: string) => void;
}) {
  return (
    <section role="region" aria-label={`${member.displayName}详情`} style={styles.teamPanel}>
      <div style={expertDetailHeaderStyle}>
        <button type="button" style={expertBackButtonStyle} onClick={onBack}>
          <ArrowLeft size={14} />
          返回团队
        </button>
        <TeamMemberStatusPill status={member.status} />
      </div>
      <div style={expertDetailTitleRowStyle}>
        <span style={expertAvatarStyle(member)}>{member.expertProfile?.avatarLabel ?? member.displayName.slice(0, 1)}</span>
        <div style={{ minWidth: 0 }}>
          <div style={styles.teamMemberName}>{member.displayName}</div>
          <div style={styles.sectionSubtitle}>
            {member.expertProfile?.roleTitle ?? member.templateId ?? "团队成员"}
          </div>
        </div>
      </div>
      {member.snapshots.length > 0 ? (
        <div style={expertDetailBlockStyle}>
          <div style={expertDetailLabelStyle}>思考摘录</div>
          {member.snapshots.slice(-5).reverse().map((snapshot) => (
            <div key={snapshot.id} style={expertTimelineItemStyle}>
              <div style={expertTimelineHeaderStyle}>
                <span>{snapshot.stageLabel}</span>
                <span>{snapshotStatusLabel(snapshot.status)}</span>
              </div>
              <div style={expertTimelineHeadlineStyle}>{snapshot.headline}</div>
              <div style={expertSnapshotBodyStyle}>{snapshot.body}</div>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState title="正在接手任务" detail="这个专家还没有发布可见摘录。" compact />
      )}
      {member.previewItems.length > 0 ? (
        <div style={expertDetailBlockStyle}>
          <div style={expertDetailLabelStyle}>预览</div>
          {member.previewItems.slice().reverse().map((preview) => (
            <button
              key={preview.id}
              type="button"
              style={previewCardButtonStyle}
              onClick={() => onOpenPreview(preview.id)}
            >
              <span style={previewCardTitleStyle}>{preview.title}</span>
              <span style={expertSnapshotBodyStyle}>{preview.summary}</span>
            </button>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function TeamPreviewFullscreen({
  preview,
  onBack,
}: {
  preview: RunViewTeamMemberPreviewItem;
  onBack: () => void;
}) {
  return (
    <section role="region" aria-label="结果预览" style={{ ...styles.teamPanel, minHeight: 360 }}>
      <div style={expertDetailHeaderStyle}>
        <button type="button" style={expertBackButtonStyle} onClick={onBack}>
          <ArrowLeft size={14} />
          返回
        </button>
        <span style={expertChipStyle}>{previewStatusLabel(preview.status)}</span>
      </div>
      <div style={previewFullscreenTitleStyle}>{preview.title}</div>
      {preview.subtitle ? <div style={styles.sectionSubtitle}>{preview.subtitle}</div> : null}
      <div style={previewFullscreenBodyStyle}>{preview.summary}</div>
      {preview.sourceRefs.length > 0 ? (
        <div style={expertChipRowStyle}>
          {preview.sourceRefs.slice(0, 6).map((ref) => (
            <span key={`${preview.id}:${ref.label}:${ref.refId ?? ref.path ?? ""}`} style={expertChipStyle}>
              {ref.label}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function expertAvatarStyle(member: RunViewTeamMember) {
  return {
    width: 32,
    height: 32,
    borderRadius: 10,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    flex: "0 0 auto",
    fontSize: 13,
    fontWeight: 700,
    color: "var(--wjn-blue)",
    background:
      member.status === "completed"
        ? "rgba(23, 122, 98, 0.1)"
        : "rgba(37, 99, 235, 0.1)",
    border: "1px solid rgba(37, 99, 235, 0.16)",
  } as const;
}

const expertSnapshotBodyStyle = {
  marginTop: 4,
  color: "var(--wjn-text-muted)",
  fontSize: 12,
  lineHeight: 1.55,
  overflow: "hidden",
  display: "-webkit-box",
  WebkitLineClamp: 2,
  WebkitBoxOrient: "vertical",
} as const;

const expertChipRowStyle = {
  display: "flex",
  flexWrap: "wrap",
  gap: 6,
  marginTop: 8,
} as const;

const expertChipStyle = {
  display: "inline-flex",
  alignItems: "center",
  minHeight: 22,
  borderRadius: 999,
  padding: "0 8px",
  border: "1px solid var(--wjn-line)",
  background: "var(--wjn-surface)",
  color: "var(--wjn-text-muted)",
  fontSize: 11,
  fontWeight: 650,
} as const;

const expertCardActionsStyle = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  flex: "0 0 auto",
} as const;

const expertIconButtonStyle = {
  display: "inline-flex",
  alignItems: "center",
  gap: 4,
  minHeight: 26,
  border: "1px solid var(--wjn-line)",
  borderRadius: 8,
  padding: "0 8px",
  background: "var(--wjn-surface)",
  color: "var(--wjn-text)",
  fontSize: 12,
  cursor: "pointer",
} as const;

const expertTextButtonStyle = {
  ...expertIconButtonStyle,
  fontWeight: 650,
} as const;

const expertDetailHeaderStyle = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: 12,
} as const;

const expertBackButtonStyle = {
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  border: "none",
  background: "transparent",
  color: "var(--wjn-text-muted)",
  fontSize: 12,
  fontWeight: 700,
  cursor: "pointer",
  padding: 0,
} as const;

const expertDetailTitleRowStyle = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  marginTop: 14,
} as const;

const expertDetailBlockStyle = {
  marginTop: 16,
  display: "grid",
  gap: 10,
} as const;

const expertDetailLabelStyle = {
  fontSize: 11,
  fontWeight: 800,
  letterSpacing: 0,
  color: "var(--wjn-text-muted)",
} as const;

const expertTimelineItemStyle = {
  border: "1px solid var(--wjn-line)",
  borderRadius: 10,
  padding: 12,
  background: "var(--wjn-surface-subtle)",
} as const;

const expertTimelineHeaderStyle = {
  display: "flex",
  justifyContent: "space-between",
  gap: 10,
  color: "var(--wjn-text-muted)",
  fontSize: 11,
  fontWeight: 700,
} as const;

const expertTimelineHeadlineStyle = {
  marginTop: 6,
  color: "var(--wjn-text)",
  fontSize: 13,
  fontWeight: 760,
  lineHeight: 1.35,
} as const;

const previewCardButtonStyle = {
  width: "100%",
  display: "grid",
  gap: 4,
  textAlign: "left",
  border: "1px solid var(--wjn-line)",
  borderRadius: 10,
  padding: 12,
  background: "var(--wjn-surface)",
  cursor: "pointer",
} as const;

const previewCardTitleStyle = {
  color: "var(--wjn-text)",
  fontSize: 13,
  fontWeight: 760,
} as const;

const previewFullscreenTitleStyle = {
  marginTop: 18,
  color: "var(--wjn-text)",
  fontSize: 18,
  fontWeight: 820,
  lineHeight: 1.25,
} as const;

const previewFullscreenBodyStyle = {
  marginTop: 16,
  border: "1px solid var(--wjn-line)",
  borderRadius: 12,
  padding: 14,
  background: "var(--wjn-surface)",
  color: "var(--wjn-text)",
  fontSize: 13,
  lineHeight: 1.65,
  whiteSpace: "pre-wrap",
} as const;

function teamStatusColor(status: string) {
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
  if (member.latestSnapshot?.headline) return member.latestSnapshot.headline;
  if (member.activityLabel) return member.activityLabel;
  const count = member.effectiveTools.length + member.effectiveSkills.length;
  if (count > 0) return "能力已就绪";
  if (member.status === "running" || member.status === "launching") return "正在处理";
  if (member.status === "completed") return "已完成";
  return "按任务需要待命";
}

function previewStatusLabel(status: RunViewTeamMemberPreviewItem["status"]): string {
  if (status === "ready") return "可预览";
  if (status === "saved") return "已保存";
  return "草稿";
}

function snapshotStatusLabel(status: string): string {
  if (status === "completed") return "完成";
  if (status === "failed") return "异常";
  if (status === "blocked") return "等待";
  if (status === "queued") return "待命";
  return "进行中";
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
    return "质量风险";
  }
  return "质量检查";
}
