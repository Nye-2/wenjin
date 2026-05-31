"use client";

import { useEffect, useMemo, useState } from "react";
import type {
  ReactNode,
} from "react";
import {
  Activity,
  BookOpen,
  CheckCircle2,
  ClipboardList,
  Database,
  Edit3,
  ExternalLink,
  FileText,
  FlaskConical,
  History,
  Maximize2,
  Minimize2,
  PauseCircle,
  PlayCircle,
  Search,
  ShieldCheck,
  Users,
  XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useShallow } from "zustand/react/shallow";

import type {
  ExecutionNodeState,
  ExecutionRecord,
  WorkspaceCapability,
  WorkspacePrismReviewItem,
} from "@/lib/api/types";
import { cancelExecution, listExecutions } from "@/lib/api/executions";
import {
  buildCommittedRoomLinks,
  commitExecutionOutputs,
  type CommittedRoomLink,
  type ExecutionCommitRequest,
} from "@/lib/execution-commit";
import { groupExecutionPhases } from "@/lib/execution-phases";
import {
  isTerminalRunStatus,
  runViewFromExecution,
  type RunViewTeam,
  type RunViewStatus,
} from "@/lib/execution-run-view";
import {
  getWorkspaceResultKindMeta,
  groupWorkspaceResultPreviews,
} from "@/lib/workspace-result-kind";
import type { WorkspaceTypeConfig } from "@/lib/workspace-suggestions";
import type { WorkspaceResultPreview } from "@/lib/workspace-result-preview";
import {
  buildOutputOverrides,
  coerceEditableValue,
  getEditableFields,
  stringifyEditableValue,
  type EditableResultKind,
} from "@/lib/workbench-result-editing";
import { useChatStoreV2 } from "@/stores/chat-store";
import { useExecutionStore } from "@/stores/execution-store";
import { useRunUiStore } from "@/stores/run-ui-store";
import {
  useWorkbenchLayoutStore,
  type WorkbenchDraftEdit,
  type WorkbenchTab,
} from "@/stores/workbench-layout-store";
import { CommitActionBar } from "./result-preview/CommitActionBar";
import { ResultPreviewDetail } from "./result-preview/ResultPreviewDetail";
import { WorkspaceActionLink } from "./WorkspaceActionLink";
import { styles } from "./live-workflow/styles";
import type { EvidenceFilter, EvidenceItem } from "./live-workflow/types";
import { useLiveWorkflowViewModel } from "./live-workflow/useLiveWorkflowViewModel";
import {
  applyDraftLabelsToCommitLinks,
  buildSandboxSummary,
  fieldLabel,
  formatDateTime,
  formatJsonPreview,
  generateUUID,
  isTerminalStatus,
  kindLabel,
  qualityGateLabel,
  qualityGateTone,
  readString,
  statusLabel,
  statusTone,
  toggleChecked,
  truncate,
} from "./live-workflow/utils";

interface LiveWorkflowPanelProps {
  workspaceId: string;
  typeConfig?: WorkspaceTypeConfig;
  features?: WorkspaceCapability[];
  className?: string;
  "data-testid"?: string;
}

const TABS: Array<{
  key: WorkbenchTab;
  label: string;
  icon: LucideIcon;
}> = [
  { key: "overview", label: "总览", icon: Activity },
  { key: "run", label: "运行", icon: History },
  { key: "evidence", label: "证据", icon: Database },
  { key: "review", label: "审阅", icon: CheckCircle2 },
];

export function LiveWorkflowPanel({
  workspaceId,
  typeConfig,
  features = [],
  className,
  "data-testid": testId,
}: LiveWorkflowPanelProps) {
  const executionRecords = useExecutionStore(
    useShallow((state) => Array.from(state.executions.values())),
  );
  const upsertExecution = useExecutionStore((state) => state.upsertExecution);
  const focusedRunId = useRunUiStore((state) => state.focusedRunId);
  const activeRunId = useRunUiStore((state) => state.activeRunId);
  const activeWorkbenchTab = useWorkbenchLayoutStore(
    (state) => state.activeWorkbenchTab,
  );
  const selectedRunId = useWorkbenchLayoutStore((state) => state.selectedRunId);
  const selectedNodeId = useWorkbenchLayoutStore((state) => state.selectedNodeId);
  const draftEdits = useWorkbenchLayoutStore((state) => state.draftEdits);
  const isFullscreen = useWorkbenchLayoutStore(
    (state) => state.isWorkbenchFullscreen,
  );
  const setActiveWorkbenchTab = useWorkbenchLayoutStore(
    (state) => state.setActiveWorkbenchTab,
  );
  const setAutoWorkbenchTab = useWorkbenchLayoutStore(
    (state) => state.setAutoWorkbenchTab,
  );
  const selectRun = useWorkbenchLayoutStore((state) => state.selectRun);
  const selectNode = useWorkbenchLayoutStore((state) => state.selectNode);
  const setWorkbenchFullscreen = useWorkbenchLayoutStore(
    (state) => state.setWorkbenchFullscreen,
  );
  const setDraftEdit = useWorkbenchLayoutStore((state) => state.setDraftEdit);
  const patchDraftData = useWorkbenchLayoutStore((state) => state.patchDraftData);
  const clearDraftEdits = useWorkbenchLayoutStore((state) => state.clearDraftEdits);
  const sendMessage = useChatStoreV2((state) => state.sendMessage);
  const isSending = useChatStoreV2((state) => state.isSending);
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [selectedPreviewId, setSelectedPreviewId] = useState<string | null>(null);
  const [evidenceFilter, setEvidenceFilter] = useState<EvidenceFilter>("all");
  const [evidenceQuery, setEvidenceQuery] = useState("");
  const [commitState, setCommitState] = useState<{
    executionId: string | null;
    idempotencyKey: string;
    committed: boolean;
    committing: boolean;
    links: CommittedRoomLink[];
    error: string | null;
  }>(() => ({
    executionId: null,
    idempotencyKey: generateUUID(),
    committed: false,
    committing: false,
    links: [],
    error: null,
  }));
  const [interventionOpen, setInterventionOpen] = useState(false);
  const [interventionText, setInterventionText] = useState("");
  const [interventionState, setInterventionState] = useState<{
    executionId: string | null;
    instruction: string;
    requestedAt: number | null;
    status: string | null;
    sent: boolean;
  }>({
    executionId: null,
    instruction: "",
    requestedAt: null,
    status: null,
    sent: false,
  });
  const {
    records,
    selectedRecord,
    baseOutputs,
    previews,
    reviewItems,
    evidenceItems,
    outputSignature,
    selectedPreview,
    selectedDraft,
    runningRecord,
    pendingReviewCount,
    sandboxCount,
  } = useLiveWorkflowViewModel({
    records: executionRecords,
    workspaceId,
    selectedRunId,
    focusedRunId,
    activeRunId,
    selectedPreviewId,
    draftEdits,
  });

  useEffect(() => {
    if (records.length > 0) {
      return;
    }
    let cancelled = false;
    void listExecutions({ workspace_id: workspaceId, limit: 20 })
      .then(({ items }) => {
        if (cancelled) {
          return;
        }
        [...items].reverse().forEach((item) => upsertExecution(item));
      })
      .catch(() => {
        // Live SSE can still populate the panel; keep history hydration best-effort.
      });
    return () => {
      cancelled = true;
    };
  }, [records.length, upsertExecution, workspaceId]);

  useEffect(() => {
    if (activeRunId) {
      selectRun(activeRunId);
      setActiveWorkbenchTab("run");
    }
  }, [activeRunId, selectRun, setActiveWorkbenchTab]);

  useEffect(() => {
    if (selectedRecord) {
      if (selectedRunId !== selectedRecord.id) {
        selectRun(selectedRecord.id);
      }
      return;
    }
    if (records[0]) {
      selectRun(records[0].id);
    }
  }, [records, selectedRecord, selectedRunId, selectRun]);

  useEffect(() => {
    if (!selectedRecord) {
      setAutoWorkbenchTab("overview");
      return;
    }
    if (!isTerminalStatus(selectedRecord.status)) {
      setAutoWorkbenchTab("run");
      return;
    }
    if (previews.length > 0 || reviewItems.length > 0) {
      setAutoWorkbenchTab("review");
      return;
    }
    if (evidenceItems.length > 0) {
      setAutoWorkbenchTab("evidence");
      return;
    }
    setAutoWorkbenchTab("overview");
  }, [evidenceItems.length, previews.length, reviewItems.length, selectedRecord, setAutoWorkbenchTab]);

  useEffect(() => {
    setCheckedIds(
      new Set(
        baseOutputs
          .filter((output) => output.default_checked !== false)
          .map((output) => output.id),
      ),
    );
  }, [baseOutputs, outputSignature]);

  useEffect(() => {
    if (previews.length === 0) {
      setSelectedPreviewId(null);
      return;
    }
    setSelectedPreviewId((current) =>
      current && previews.some((preview) => preview.id === current)
        ? current
        : previews[0].id,
    );
  }, [previews]);

  useEffect(() => {
    setCommitState({
      executionId: selectedRecord?.id ?? null,
      idempotencyKey: generateUUID(),
      committed: false,
      committing: false,
      links: [],
      error: null,
    });
  }, [selectedRecord?.id]);

  useEffect(() => {
    if (
      !interventionState.executionId ||
      interventionState.sent ||
      isSending
    ) {
      return;
    }
    const record = records.find(
      (item) => item.id === interventionState.executionId,
    );
    if (!record || !isTerminalStatus(record.status)) {
      return;
    }
    const instruction = interventionState.instruction.trim();
    if (!instruction) {
      return;
    }
    setInterventionState((current) => ({
      ...current,
      status: "已中断，正在用补充指令重启任务",
      sent: true,
    }));
    void sendMessage(
      workspaceId,
      [
        "请基于上一轮被中断的执行继续处理。",
        `被中断的执行 ID：${interventionState.executionId}`,
        "补充指令：",
        instruction,
        "请复用上一轮已经完成且仍可靠的证据和产物，避免无必要重复。",
      ].join("\n"),
      [],
      {
        metadata: {
          intervention: true,
          interrupted_execution_id: interventionState.executionId,
          orchestration: {
            intervention: true,
            interrupted_execution_id: interventionState.executionId,
          },
        },
      },
    ).finally(() => {
      setInterventionText("");
      setInterventionOpen(false);
      setInterventionState({
        executionId: null,
        instruction: "",
        requestedAt: null,
        status: "补充指令已提交，等待新任务启动",
        sent: false,
      });
    });
  }, [interventionState, isSending, records, sendMessage, workspaceId]);

  useEffect(() => {
    if (!interventionState.executionId || interventionState.sent) {
      return;
    }
    const timer = window.setTimeout(() => {
      setInterventionState((current) => {
        if (!current.executionId || current.sent) {
          return current;
        }
        return {
          ...current,
          status: "已请求中断，等待当前安全点结束",
        };
      });
    }, 15000);
    return () => window.clearTimeout(timer);
  }, [interventionState.executionId, interventionState.sent]);

  async function handleLaunchFeature(feature: WorkspaceCapability) {
    if (isSending) {
      return;
    }
    const description = feature.description?.trim();
    const prompt = [
      `请启动「${feature.name}」能力。`,
      description ? `能力目标：${description}` : null,
      "如果当前对话缺少具体研究主题、材料或目标，请先向用户确认，不要用空泛主题启动检索、写作或实验。",
      "请先判断是否需要实验或检索；若需要，请由右侧 Lead Agent/subagent 自主推进，并在右侧工作台展示关键证据、运行状态和可审阅结果。",
    ]
      .filter(Boolean)
      .join("\n");
    await sendMessage(workspaceId, prompt, [], {
      metadata: {
        workbench_launch: {
          capability_id: feature.id,
          capability_name: feature.name,
        },
      },
    });
  }

  async function handleCommit(mode: "all" | "selected" | "discard") {
    if (!selectedRecord || commitState.committing || commitState.committed) {
      return;
    }
    const outputIds = previews.map((preview) => preview.id);
    const acceptedIds =
      mode === "all"
        ? outputIds
        : mode === "selected"
          ? Array.from(checkedIds)
          : [];
    const body: ExecutionCommitRequest =
      mode === "all"
        ? { accept_all: true }
        : { accepted_ids: acceptedIds };
    const overrides = buildOutputOverrides(acceptedIds, draftEdits);
    if (overrides) {
      body.output_overrides = overrides;
    }

    setCommitState((current) => ({
      ...current,
      committing: true,
      error: null,
      links: [],
    }));
    try {
      const response = await commitExecutionOutputs({
        executionId: selectedRecord.id,
        idempotencyKey: commitState.idempotencyKey,
        body,
      });
      const commitLinkPreviews = applyDraftLabelsToCommitLinks(previews, draftEdits);
      const links = buildCommittedRoomLinks({
        workspaceId,
        previews: commitLinkPreviews,
        roomTargets: response.room_targets,
      });
      clearDraftEdits(acceptedIds);
      setCommitState((current) => ({
        ...current,
        committed: true,
        committing: false,
        links,
      }));
    } catch (error) {
      setCommitState((current) => ({
        ...current,
        committed: false,
        committing: false,
        links: [],
        error: error instanceof Error ? error.message : "保存失败",
      }));
    }
  }

  async function handleInterventionSubmit() {
    const record = runningRecord;
    const instruction = interventionText.trim();
    if (!record || !instruction) {
      return;
    }
    setInterventionState({
      executionId: record.id,
      instruction,
      requestedAt: Date.now(),
      status: "正在中断当前任务",
      sent: false,
    });
    try {
      await cancelExecution(record.id, "interrupt");
    } catch (error) {
      setInterventionState({
        executionId: null,
        instruction,
        requestedAt: null,
        status: error instanceof Error ? error.message : "中断请求失败",
        sent: false,
      });
    }
  }

  return (
    <div
      className={className}
      data-testid={testId}
      style={{
        position: "relative",
        height: "100%",
        minHeight: 0,
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        background:
          "linear-gradient(180deg, rgba(255,255,255,0.54), rgba(246,248,251,0.98))",
        fontFamily: "var(--wjn-font-sans)",
        color: "var(--wjn-text)",
      }}
    >
      <WorkbenchHeader
        activeTab={activeWorkbenchTab}
        status={selectedRecord ? runViewFromExecution(selectedRecord).status : null}
        pendingReviewCount={pendingReviewCount}
        evidenceCount={evidenceItems.length}
        sandboxCount={sandboxCount}
        isFullscreen={isFullscreen}
        canInterrupt={Boolean(runningRecord)}
        interventionOpen={interventionOpen}
        interventionStatus={interventionState.status}
        onTabChange={setActiveWorkbenchTab}
        onToggleFullscreen={() => setWorkbenchFullscreen(!isFullscreen)}
        onToggleIntervention={() => setInterventionOpen((current) => !current)}
      />

      {interventionOpen ? (
        <InterventionBar
          value={interventionText}
          disabled={!runningRecord || Boolean(interventionState.executionId)}
          status={interventionState.status}
          onChange={setInterventionText}
          onSubmit={handleInterventionSubmit}
        />
      ) : null}

      <div style={styles.body}>
        {activeWorkbenchTab === "overview" ? (
          <OverviewView
            typeConfig={typeConfig}
            features={features}
            records={records}
            pendingReviewCount={pendingReviewCount}
            evidenceCount={evidenceItems.length}
            sandboxCount={sandboxCount}
            isSending={isSending}
            onLaunchFeature={(feature) => void handleLaunchFeature(feature)}
            onOpenRun={(runId) => {
              selectRun(runId);
              setActiveWorkbenchTab("run");
            }}
          />
        ) : null}
        {activeWorkbenchTab === "run" ? (
          <RunView
            record={selectedRecord}
            selectedNodeId={selectedNodeId}
            onSelectNode={selectNode}
            onOpenReview={() => setActiveWorkbenchTab("review")}
            onOpenEvidence={() => setActiveWorkbenchTab("evidence")}
            onOpenIntervention={() => setInterventionOpen(true)}
          />
        ) : null}
        {activeWorkbenchTab === "evidence" ? (
          <EvidenceView
            items={evidenceItems}
            filter={evidenceFilter}
            query={evidenceQuery}
            selectedId={selectedPreviewId}
            checkedIds={checkedIds}
            draftEdits={draftEdits}
            disabled={commitState.committed}
            onFilterChange={setEvidenceFilter}
            onQueryChange={setEvidenceQuery}
            onSelect={(id) => setSelectedPreviewId(id)}
            onToggleChecked={(id) => toggleChecked(setCheckedIds, id)}
            onPatchDraft={patchDraftData}
            onSetDraft={setDraftEdit}
          />
        ) : null}
        {activeWorkbenchTab === "review" ? (
          <ReviewView
            workspaceId={workspaceId}
            record={selectedRecord}
            previews={previews}
            selectedPreview={selectedPreview}
            selectedDraft={selectedDraft}
            draftEdits={draftEdits}
            checkedIds={checkedIds}
            committed={commitState.committed}
            committing={commitState.committing}
            commitLinks={commitState.links}
            commitError={commitState.error}
            reviewItems={reviewItems}
            isFullscreen={isFullscreen}
            onSelectPreview={setSelectedPreviewId}
            onEnterDetailMode={() => setWorkbenchFullscreen(true)}
            onToggleChecked={(id) => toggleChecked(setCheckedIds, id)}
            onPatchDraft={patchDraftData}
            onSetDraft={setDraftEdit}
            onAcceptAll={() => void handleCommit("all")}
            onAcceptSelected={() => void handleCommit("selected")}
            onDiscard={() => void handleCommit("discard")}
          />
        ) : null}
      </div>
    </div>
  );
}

function WorkbenchHeader({
  activeTab,
  status,
  pendingReviewCount,
  evidenceCount,
  sandboxCount,
  isFullscreen,
  canInterrupt,
  interventionOpen,
  interventionStatus,
  onTabChange,
  onToggleFullscreen,
  onToggleIntervention,
}: {
  activeTab: WorkbenchTab;
  status: RunViewStatus | null;
  pendingReviewCount: number;
  evidenceCount: number;
  sandboxCount: number;
  isFullscreen: boolean;
  canInterrupt: boolean;
  interventionOpen: boolean;
  interventionStatus: string | null;
  onTabChange: (tab: WorkbenchTab) => void;
  onToggleFullscreen: () => void;
  onToggleIntervention: () => void;
}) {
  return (
    <div style={styles.header}>
      <div style={{ minWidth: 0 }}>
        <div style={styles.eyebrow}>Agent Workbench</div>
        <div style={styles.headerTitle}>证据化运行工作台</div>
      </div>
      <div style={styles.headerMiddle}>
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const count =
            tab.key === "evidence"
              ? evidenceCount
              : tab.key === "review"
                ? pendingReviewCount
                : tab.key === "run" && sandboxCount > 0
                  ? sandboxCount
                  : 0;
          return (
            <button
              key={tab.key}
              type="button"
              aria-label={tab.label}
              title={tab.label}
              onClick={() => onTabChange(tab.key)}
              style={{
                ...styles.tabButton,
                ...(activeTab === tab.key ? styles.tabButtonActive : null),
                ...(activeTab === tab.key ? styles.tabButtonExpanded : styles.tabButtonIconOnly),
              }}
            >
              <Icon size={14} />
              {activeTab === tab.key ? <span>{tab.label}</span> : null}
              {count > 0 ? <span style={styles.tabBadge}>{Math.min(count, 99)}</span> : null}
            </button>
          );
        })}
      </div>
      <div style={styles.headerActions}>
        {status ? <StatusPill status={status} /> : null}
        <button
          type="button"
          aria-label={interventionOpen ? "收起介入" : "中断并补充"}
          title={interventionOpen ? "收起介入" : "中断并补充"}
          onClick={onToggleIntervention}
          disabled={!canInterrupt}
          style={{
            ...styles.iconTextButton,
            ...(!canInterrupt && !interventionOpen ? styles.iconButtonCompact : null),
            opacity: canInterrupt ? 1 : 0.45,
          }}
        >
          <PauseCircle size={14} />
          {canInterrupt || interventionOpen ? (
            <span>{interventionOpen ? "收起介入" : "中断并补充"}</span>
          ) : null}
        </button>
        <button
          type="button"
          title={isFullscreen ? "退出全屏" : "右侧全屏"}
          aria-label={isFullscreen ? "退出全屏" : "右侧全屏"}
          onClick={onToggleFullscreen}
          style={styles.iconButton}
        >
          {isFullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
        </button>
        {interventionStatus ? (
          <span style={styles.miniStatus}>{interventionStatus}</span>
        ) : null}
      </div>
    </div>
  );
}

function InterventionBar({
  value,
  disabled,
  status,
  onChange,
  onSubmit,
}: {
  value: string;
  disabled: boolean;
  status: string | null;
  onChange: (value: string) => void;
  onSubmit: () => void;
}) {
  return (
    <div style={styles.interventionBar}>
      <textarea
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        placeholder="补充新的约束、方向或纠错信息。提交后会先中断当前 run，再用这条指令启动新 run。"
        rows={2}
        style={styles.interventionInput}
      />
      <button
        type="button"
        disabled={disabled || !value.trim()}
        onClick={onSubmit}
        style={{
          ...styles.primaryButton,
          opacity: disabled || !value.trim() ? 0.55 : 1,
        }}
      >
        提交介入
      </button>
      {status ? <span style={styles.interventionStatus}>{status}</span> : null}
    </div>
  );
}

function OverviewView({
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

function RunView({
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

function EvidenceView({
  items,
  filter,
  query,
  selectedId,
  checkedIds,
  draftEdits,
  disabled,
  onFilterChange,
  onQueryChange,
  onSelect,
  onToggleChecked,
  onPatchDraft,
  onSetDraft,
}: {
  items: EvidenceItem[];
  filter: EvidenceFilter;
  query: string;
  selectedId: string | null;
  checkedIds: Set<string>;
  draftEdits: Record<string, WorkbenchDraftEdit>;
  disabled: boolean;
  onFilterChange: (filter: EvidenceFilter) => void;
  onQueryChange: (query: string) => void;
  onSelect: (id: string) => void;
  onToggleChecked: (id: string) => void;
  onPatchDraft: (outputId: string, field: string, value: unknown) => void;
  onSetDraft: (outputId: string, edit: WorkbenchDraftEdit | null) => void;
}) {
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter((item) => {
      if (filter === "outputs" && item.source !== "output") return false;
      if (filter === "nodes" && item.source !== "node") return false;
      if (filter === "sandbox" && !item.summary.toLowerCase().includes("sandbox") && item.kind !== "sandbox") return false;
      if (!q) return true;
      return `${item.title} ${item.kind} ${item.summary}`.toLowerCase().includes(q);
    });
  }, [filter, items, query]);
  const selected =
    filtered.find((item) => item.id === selectedId) ??
    filtered[0] ??
    null;

  return (
    <div style={styles.evidenceGrid}>
      <section style={styles.section}>
        <div style={styles.toolbar}>
          <div style={styles.searchBox}>
            <Search size={15} />
            <input
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
              placeholder="搜索标题、作者、节点或摘要"
              style={styles.searchInput}
            />
          </div>
          <div style={styles.segmented}>
            {[
              ["all", "全部"],
              ["outputs", "候选结果"],
              ["nodes", "节点输出"],
              ["sandbox", "Sandbox"],
            ].map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => onFilterChange(key as EvidenceFilter)}
                style={{
                  ...styles.segmentButton,
                  ...(filter === key ? styles.segmentButtonActive : null),
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        {filtered.length > 0 ? (
          <div style={styles.evidenceTableWrap}>
            <table style={styles.evidenceTable}>
              <thead>
                <tr>
                  <th style={styles.th}>包含</th>
                  <th style={styles.th}>类型</th>
                  <th style={styles.th}>标题 / 节点</th>
                  <th style={styles.th}>摘要</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => {
                  const isSelected = selected?.id === item.id;
                  return (
                    <tr
                      key={item.id}
                      onClick={() => onSelect(item.id)}
                      style={{
                        ...styles.tr,
                        ...(isSelected ? styles.trSelected : null),
                      }}
                    >
                      <td style={styles.td}>
                        {item.source === "output" ? (
                          <input
                            type="checkbox"
                            checked={checkedIds.has(item.preview.id)}
                            disabled={disabled}
                            onChange={(event) => {
                              event.stopPropagation();
                              onToggleChecked(item.preview.id);
                            }}
                            onClick={(event) => event.stopPropagation()}
                            style={styles.checkbox}
                          />
                        ) : (
                          <span style={styles.readOnlyMark}>只读</span>
                        )}
                      </td>
                      <td style={styles.td}>
                        <ResultKindBadge kind={item.kind} />
                      </td>
                      <td style={styles.tdStrong}>{item.title}</td>
                      <td style={styles.tdMuted}>{truncate(item.summary, 140)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="没有匹配证据" detail="调整搜索或过滤条件后再查看。" compact />
        )}
      </section>

      <aside style={styles.editorAside}>
        {selected?.source === "output" ? (
          <ResultEditor
            preview={selected.preview}
            draft={draftEdits[selected.preview.id]}
            disabled={disabled}
            onPatchDraft={onPatchDraft}
            onSetDraft={onSetDraft}
          />
        ) : selected?.source === "node" ? (
          <NodeInspector
            node={{ id: selected.nodeId, type: selected.kind, label: selected.title }}
            state={selected.nodeState}
          />
        ) : (
          <EmptyState title="选择证据项" detail="可在这里编辑候选结果字段，或查看节点输出摘要。" compact />
        )}
      </aside>
    </div>
  );
}

function ReviewView({
  workspaceId,
  record,
  previews,
  selectedPreview,
  selectedDraft,
  draftEdits,
  checkedIds,
  committed,
  committing,
  commitLinks,
  commitError,
  reviewItems,
  isFullscreen,
  onSelectPreview,
  onEnterDetailMode,
  onToggleChecked,
  onPatchDraft,
  onSetDraft,
  onAcceptAll,
  onAcceptSelected,
  onDiscard,
}: {
  workspaceId: string;
  record: ExecutionRecord | null;
  previews: WorkspaceResultPreview[];
  selectedPreview: WorkspaceResultPreview | null;
  selectedDraft?: WorkbenchDraftEdit;
  draftEdits: Record<string, WorkbenchDraftEdit>;
  checkedIds: Set<string>;
  committed: boolean;
  committing: boolean;
  commitLinks: CommittedRoomLink[];
  commitError: string | null;
  reviewItems: WorkspacePrismReviewItem[];
  isFullscreen: boolean;
  onSelectPreview: (id: string) => void;
  onEnterDetailMode: () => void;
  onToggleChecked: (id: string) => void;
  onPatchDraft: (outputId: string, field: string, value: unknown) => void;
  onSetDraft: (outputId: string, edit: WorkbenchDraftEdit | null) => void;
  onAcceptAll: () => void;
  onAcceptSelected: () => void;
  onDiscard: () => void;
}) {
  const previewGroups = useMemo(
    () => groupWorkspaceResultPreviews(previews),
    [previews],
  );
  const [activeKind, setActiveKind] = useState<string>("all");
  const effectiveKind =
    activeKind === "all" || previewGroups.some((group) => group.kind === activeKind)
      ? activeKind
      : "all";
  const visibleGroups = useMemo(() => {
    return effectiveKind === "all"
      ? previewGroups
      : previewGroups.filter((group) => group.kind === effectiveKind);
  }, [effectiveKind, previewGroups]);

  function activateFilter(kind: string) {
    setActiveKind(kind);
    if (kind === "all") {
      return;
    }
    const firstItem = previewGroups.find((group) => group.kind === kind)?.items[0];
    if (firstItem && firstItem.id !== selectedPreview?.id) {
      onSelectPreview(firstItem.id);
    }
  }

  function activatePreview(previewId: string) {
    onSelectPreview(previewId);
    if (!isFullscreen) {
      onEnterDetailMode();
    }
  }

  if (!record) {
    return <EmptyState title="暂无可审阅结果" detail="完成运行后，候选文档、文献、记忆、决策和任务会进入这里。" />;
  }

  return (
    <div
      style={{
        ...styles.reviewGrid,
        ...(!isFullscreen ? styles.reviewGridSingle : null),
      }}
    >
      <section
        role="region"
        aria-label="候选结果列表"
        style={styles.reviewInbox}
      >
        <div style={styles.sectionHeader}>
          <div>
            <div style={styles.sectionTitle}>候选结果</div>
            <div style={styles.sectionSubtitle}>按类型筛选，点选后在右侧查看详情。</div>
          </div>
          <span style={styles.countBadge}>{previews.length} 项</span>
        </div>
        <div style={styles.reviewFilterBar} aria-label="候选结果筛选">
          <button
            type="button"
            aria-label="筛选全部结果"
            title="全部"
            onClick={() => activateFilter("all")}
            style={{
              ...styles.reviewFilterButton,
              ...(effectiveKind === "all" ? styles.reviewFilterButtonActive : null),
            }}
          >
            全部
            <span style={styles.filterCount}>{previews.length}</span>
          </button>
          {previewGroups.map((group) => (
            <button
              key={group.kind}
              type="button"
              aria-label={`筛选${group.meta.groupLabel}`}
              title={group.meta.groupLabel}
              onClick={() => activateFilter(group.kind)}
              style={{
                ...styles.reviewFilterButton,
                ...(effectiveKind === group.kind
                  ? {
                      ...styles.reviewFilterButtonActive,
                      color: group.meta.accent,
                      borderColor: group.meta.border,
                      background: group.meta.tint,
                    }
                  : null),
              }}
            >
              {group.meta.shortLabel}
              <span style={styles.filterCount}>{group.items.length}</span>
            </button>
          ))}
        </div>
        {previews.length > 0 ? (
          <div style={styles.previewList}>
            {visibleGroups.map((group) => (
              <section key={group.kind} style={styles.previewGroupCompact}>
                <div style={styles.previewGroupHeader}>
                  <span
                    style={{
                      ...styles.previewGroupTitle,
                      color: group.meta.accent,
                    }}
                  >
                    {group.meta.groupLabel}
                  </span>
                  <span
                    style={{
                      ...styles.previewGroupCount,
                      background: group.meta.tint,
                      borderColor: group.meta.border,
                      color: group.meta.accent,
                    }}
                  >
                    {group.items.length}
                  </span>
                </div>
                <div style={styles.previewGroupList}>
                  {group.items.map((preview) => {
                    const selected = selectedPreview?.id === preview.id;
                    return (
                      <div
                        key={preview.id}
                        onClick={() => activatePreview(preview.id)}
                        style={{
                          ...styles.previewListItem,
                          ...(selected ? styles.previewListItemActive : null),
                          ...(selected
                            ? {
                                borderColor: group.meta.border,
                                background: group.meta.tint,
                              }
                            : null),
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={checkedIds.has(preview.id)}
                          disabled={committed}
                          onClick={(event) => event.stopPropagation()}
                          onChange={() => onToggleChecked(preview.id)}
                          style={styles.checkbox}
                        />
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            activatePreview(preview.id);
                          }}
                          style={styles.previewListButton}
                        >
                          <span style={styles.previewTitle}>{preview.title}</span>
                          <span style={styles.previewMeta}>
                            <ResultKindBadge kind={preview.kind} />
                            {preview.subtitle ? (
                              <span style={styles.previewSubtitleInline}>
                                {preview.subtitle}
                              </span>
                            ) : null}
                          </span>
                        </button>
                        {draftEdits[preview.id] ? (
                          <Edit3 size={13} color="var(--v2-accent-purple-700)" />
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        ) : (
          <EmptyState title="没有 staged outputs" detail="如果是 Prism 文件级修改，请从下方入口进入 Prism 精修。" compact />
        )}

        <div style={styles.commitBox}>
          <CommitActionBar
            committed={committed}
            committing={committing}
            onAcceptAll={onAcceptAll}
            onAcceptSelected={onAcceptSelected}
            onDiscard={onDiscard}
            acceptAllLabel="全部接受"
            acceptSelectedLabel="保存已勾选"
            discardLabel="暂不保存"
            committedLabel="已写入工作区"
          />
          {commitError ? <div style={styles.commitError}>{commitError}</div> : null}
          {commitLinks.length > 0 ? (
            <div style={styles.linkWrap}>
              {commitLinks.map((link) => (
                <WorkspaceActionLink key={link.key} href={link.href} style={styles.roomLink}>
                  <ExternalLink size={12} />
                  {link.label}
                </WorkspaceActionLink>
              ))}
            </div>
          ) : null}
        </div>

        {reviewItems.length > 0 ? (
          <div style={styles.prismBox}>
            <div style={styles.sectionTitleSmall}>Prism 文件级修改</div>
            <div style={styles.sectionSubtitle}>精细 diff、patch 和保护区仍在 Prism 页面完成。</div>
            <div style={styles.linkWrap}>
              <WorkspaceActionLink href={`/workspaces/${workspaceId}/prism`} style={styles.roomLink}>
                <FileText size={12} />
                打开 Prism 审阅
              </WorkspaceActionLink>
            </div>
          </div>
        ) : null}
      </section>

      {isFullscreen ? (
        <section
          role="region"
          aria-label="候选结果详情"
          style={styles.reviewDetail}
        >
          {selectedPreview ? (
            <>
              <ResultPreviewDetail preview={selectedPreview} />
              <ResultEditor
                preview={selectedPreview}
                draft={selectedDraft}
                disabled={committed}
                onPatchDraft={onPatchDraft}
                onSetDraft={onSetDraft}
              />
            </>
          ) : (
            <EmptyState title="选择一个候选结果" detail="右侧会显示预览和可编辑字段。" compact />
          )}
        </section>
      ) : null}
    </div>
  );
}

function ResultEditor({
  preview,
  draft,
  disabled,
  onPatchDraft,
  onSetDraft,
}: {
  preview: WorkspaceResultPreview;
  draft?: WorkbenchDraftEdit;
  disabled: boolean;
  onPatchDraft: (outputId: string, field: string, value: unknown) => void;
  onSetDraft: (outputId: string, edit: WorkbenchDraftEdit | null) => void;
}) {
  const fields = getEditableFields(preview.kind);
  const kind = preview.kind as EditableResultKind;
  if (fields.length === 0) {
    return (
      <div style={styles.editorPanel}>
        <div style={styles.sectionTitleSmall}>只读预览</div>
        <div style={styles.sectionSubtitle}>该类型暂不支持字段编辑。</div>
      </div>
    );
  }
  const data = {
    ...(preview.data ?? {}),
    ...(draft?.data ?? {}),
  };

  return (
    <div style={styles.editorPanel} data-testid="workbench-result-editor">
      <div style={styles.sectionHeaderCompact}>
        <div>
          <div style={styles.sectionTitleSmall}>暂存编辑</div>
          <div style={styles.sectionSubtitle}>编辑只暂存在右侧，点击接受后才写入 DataService rooms。</div>
        </div>
        {draft ? (
          <button
            type="button"
            disabled={disabled}
            onClick={() => onSetDraft(preview.id, null)}
            style={styles.ghostButton}
          >
            清除编辑
          </button>
        ) : null}
      </div>
      <label style={styles.fieldLabel}>
        卡片摘要
        <input
          value={draft?.preview ?? preview.previewText ?? preview.title}
          disabled={disabled}
          onChange={(event) =>
            onSetDraft(preview.id, {
              ...(draft ?? {}),
              preview: event.target.value,
            })
          }
          style={styles.textInput}
        />
      </label>
      {fields.map((field) => {
        const value = stringifyEditableValue(data[field]);
        const longField = ["content", "abstract", "value", "description"].includes(field);
        return (
          <label key={field} style={styles.fieldLabel}>
            {fieldLabel(preview.kind, field)}
            {longField ? (
              <textarea
                value={value}
                disabled={disabled}
                rows={field === "content" ? 10 : 5}
                onChange={(event) =>
                  onPatchDraft(
                    preview.id,
                    field,
                    coerceEditableValue(kind, field, event.target.value),
                  )
                }
                style={styles.textArea}
              />
            ) : (
              <input
                value={value}
                disabled={disabled}
                onChange={(event) =>
                  onPatchDraft(
                    preview.id,
                    field,
                    coerceEditableValue(kind, field, event.target.value),
                  )
                }
                style={styles.textInput}
              />
            )}
          </label>
        );
      })}
    </div>
  );
}

function NodeInspector({
  node,
  state,
}: {
  node: { id: string; type?: string; label?: string; task?: string } | null;
  state: ExecutionNodeState | null;
}) {
  if (!node && !state) {
    return <EmptyState title="选择节点" detail="节点详情会显示输入、输出、工具调用和 sandbox 摘要。" compact />;
  }
  const output = state?.output ?? null;
  const sandboxSummary = buildSandboxSummary(state);
  return (
    <div style={styles.nodeInspector}>
      <div style={styles.sectionTitle}>{node?.label ?? node?.task ?? node?.id ?? "节点详情"}</div>
      <div style={styles.nodeMetaLine}>
        <NodeStatusDot status={state?.status ?? "pending"} />
        <span>{statusLabel(state?.status ?? "pending")}</span>
        {state?.started_at ? <span>{formatDateTime(state.started_at)}</span> : null}
      </div>

      {state?.thinking ? (
        <InspectorBlock title="进展摘要" icon={Activity}>
          {truncate(state.thinking, 360)}
        </InspectorBlock>
      ) : null}
      {state?.input ? (
        <InspectorBlock title="输入预览" icon={ClipboardList}>
          <pre style={styles.pre}>{formatJsonPreview(state.input)}</pre>
        </InspectorBlock>
      ) : null}
      {output ? (
        <InspectorBlock title="输出预览" icon={Database}>
          <pre style={styles.pre}>{formatJsonPreview(output)}</pre>
        </InspectorBlock>
      ) : null}
      {state?.tool_calls && state.tool_calls.length > 0 ? (
        <InspectorBlock title="工具调用" icon={ShieldCheck}>
          <div style={styles.toolList}>
            {state.tool_calls.slice(0, 6).map((call, index) => (
              <div key={index} style={styles.toolItem}>
                <span style={styles.toolName}>{readString(call.name) ?? `tool-${index + 1}`}</span>
                <span style={styles.toolMeta}>
                  {[
                    readString(call.status),
                    call.exit_code !== undefined ? `exit ${String(call.exit_code)}` : null,
                    readString(call.docker_image),
                  ].filter(Boolean).join(" · ")}
                </span>
              </div>
            ))}
          </div>
        </InspectorBlock>
      ) : null}
      {sandboxSummary ? (
        <InspectorBlock title="Sandbox 摘要" icon={FlaskConical}>
          <div style={styles.sandboxSummary}>
            {sandboxSummary.map((line) => (
              <div key={line}>{line}</div>
            ))}
          </div>
        </InspectorBlock>
      ) : null}
    </div>
  );
}

function InspectorBlock({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: LucideIcon;
  children: ReactNode;
}) {
  return (
    <div style={styles.inspectorBlock}>
      <div style={styles.inspectorBlockTitle}>
        <Icon size={13} />
        {title}
      </div>
      <div>{children}</div>
    </div>
  );
}

function ResultKindBadge({ kind }: { kind: string }) {
  const meta = getWorkspaceResultKindMeta(kind);
  return (
    <span
      style={{
        ...styles.kindBadge,
        color: meta.accent,
        background: meta.tint,
        borderColor: meta.border,
      }}
    >
      {kindLabel(kind)}
    </span>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div style={styles.metricCard}>
      <Icon size={17} color="var(--v2-accent-purple-700)" />
      <div>
        <div style={styles.metricValue}>{value}</div>
        <div style={styles.metricLabel}>{label}</div>
        <div style={styles.metricDetail}>{detail}</div>
      </div>
    </div>
  );
}

function EmptyState({
  title,
  detail,
  compact = false,
}: {
  title: string;
  detail: string;
  compact?: boolean;
}) {
  return (
    <div style={{ ...styles.emptyState, padding: compact ? 16 : 28 }}>
      <BookOpen size={compact ? 18 : 24} color="var(--v2-text-tertiary)" />
      <div style={styles.emptyTitle}>{title}</div>
      <div style={styles.emptyDetail}>{detail}</div>
    </div>
  );
}

function StatusPill({ status }: { status: RunViewStatus | string }) {
  const tone = statusTone(status);
  return <span style={{ ...styles.statusPill, ...tone }}>{statusLabel(status)}</span>;
}

function NodeStatusDot({ status }: { status: string }) {
  const tone = statusTone(status);
  const Icon =
    status === "completed" ? CheckCircle2 : status === "failed" ? XCircle : Activity;
  return (
    <span style={{ ...styles.nodeDot, color: tone.color }}>
      <Icon size={12} />
    </span>
  );
}
