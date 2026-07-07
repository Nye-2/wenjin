"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useShallow } from "zustand/react/shallow";

import {
  acceptExecutionChangeSetUnits,
  rejectExecutionChangeSetUnits,
  undoExecutionChangeSetUnits,
} from "@/lib/api/change-sets";
import { cancelExecution, listExecutions } from "@/lib/api/executions";
import {
  changeSetViewFromResponse,
  responseResultPatch,
  type ExecutionChangeSetResponse,
} from "@/lib/change-set-view";
import type { WorkspaceTypeConfig } from "@/lib/workspace-suggestions";
import {
  findLatestIntakeSpec,
  type IntakeSpecV1,
} from "@/lib/intake-spec";
import { filterVisibleWorkspaceResultItems } from "@/lib/workspace-result-kind";
import { useChatStoreV2 } from "@/stores/chat-store";
import { useExecutionStore } from "@/stores/execution-store";
import { useRunUiStore } from "@/stores/run-ui-store";
import {
  useWorkbenchLayoutStore,
} from "@/stores/workbench-layout-store";
import { EvidenceView } from "./live-workflow/EvidenceView";
import { InterventionBar } from "./live-workflow/InterventionBar";
import { IntakeSpecPreview } from "./live-workflow/IntakeSpecPreview";
import { OverviewView } from "./live-workflow/OverviewView";
import type {
  ChangeSetReviewAction,
  ChangeSetReviewActionState,
} from "./review-changes/ChangeSetReviewPanel";
import { ReviewView } from "./live-workflow/ReviewView";
import { RunView } from "./live-workflow/RunView";
import { WorkbenchHeader } from "./live-workflow/WorkbenchHeader";
import { styles } from "./live-workflow/styles";
import type { EvidenceFilter } from "./live-workflow/types";
import {
  resolveAutoWorkbenchTab,
  useLiveWorkflowViewModel,
} from "./live-workflow/useLiveWorkflowViewModel";
import { useExecutionWriteback } from "./live-workflow/useExecutionWriteback";
import {
  isTerminalStatus,
} from "./live-workflow/utils";
import type { WorkbenchTab } from "@/stores/workbench-layout-store";

interface LiveWorkflowPanelProps {
  workspaceId: string;
  typeConfig?: WorkspaceTypeConfig;
  className?: string;
  "data-testid"?: string;
}

export function LiveWorkflowPanel({
  workspaceId,
  typeConfig,
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
  const messages = useChatStoreV2((state) => state.messages);
  const sendMessage = useChatStoreV2((state) => state.sendMessage);
  const isSending = useChatStoreV2((state) => state.isSending);
  const [selectedPreviewId, setSelectedPreviewId] = useState<string | null>(null);
  const [evidenceFilter, setEvidenceFilter] = useState<EvidenceFilter>("all");
  const [evidenceQuery, setEvidenceQuery] = useState("");
  const [changeSetActionState, setChangeSetActionState] =
    useState<ChangeSetReviewActionState>(() => ({
      executionId: null,
      action: null,
      unitIds: [],
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
    selectedRunView,
    mission,
    previews,
    reviewItems,
    evidenceItems,
    runningRecord,
    changeSet,
    pendingReviewCount,
    hasMissionActivity,
  } = useLiveWorkflowViewModel({
    records: executionRecords,
    workspaceId,
    selectedRunId,
    focusedRunId,
    activeRunId,
    selectedPreviewId,
  });
  const selectedRecordIdRef = useRef<string | null>(null);
  selectedRecordIdRef.current = selectedRecord?.id ?? null;
  const reviewablePreviews = useMemo(
    () => filterVisibleWorkspaceResultItems(previews),
    [previews],
  );
  const writeback = useExecutionWriteback({
    workspaceId,
    selectedRecord,
    previews,
    reviewablePreviews,
    changeSet,
  });
  const latestMessageSpec = useMemo(
    () => findLatestIntakeSpec(messages, workspaceId),
    [messages, workspaceId],
  );
  const intakeSpec = latestMessageSpec;
  const visibleWorkbenchTab = activeWorkbenchTab;
  const lastAutoWorkbenchTabRef = useRef<WorkbenchTab>("overview");
  const hasManualWorkbenchTabChoiceRef = useRef(false);
  const hasProgressContext = Boolean(
    activeRunId || focusedRunId || selectedRunId || runningRecord,
  );

  function applyAutoWorkbenchTab(tab: WorkbenchTab) {
    lastAutoWorkbenchTabRef.current = tab;
    hasManualWorkbenchTabChoiceRef.current = false;
    setAutoWorkbenchTab(tab);
  }

  function handleWorkbenchTabChange(tab: WorkbenchTab) {
    hasManualWorkbenchTabChoiceRef.current = true;
    setActiveWorkbenchTab(tab);
  }

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
      applyAutoWorkbenchTab("run");
    }
  }, [activeRunId, selectRun]);

  useEffect(() => {
    if (!selectedRecord || !(activeRunId || focusedRunId || selectedRunId)) {
      return;
    }
    if (selectedRunId !== selectedRecord.id) {
      selectRun(selectedRecord.id);
    }
  }, [activeRunId, focusedRunId, selectedRecord, selectedRunId, selectRun]);

  useEffect(() => {
    if (activeWorkbenchTab === "spec" && intakeSpec) {
      return;
    }
    const autoTab = resolveAutoWorkbenchTab({
      selectedRecord,
      previews: reviewablePreviews,
      reviewItems,
      evidenceItems,
      pendingReviewCount,
    });
    if (activeWorkbenchTab === "run" && !hasProgressContext && records.length > 0) {
      applyAutoWorkbenchTab(autoTab);
      return;
    }
    if (activeWorkbenchTab === autoTab) {
      lastAutoWorkbenchTabRef.current = autoTab;
      return;
    }
    if (
      activeWorkbenchTab !== lastAutoWorkbenchTabRef.current &&
      (hasManualWorkbenchTabChoiceRef.current || activeWorkbenchTab !== "overview")
    ) {
      return;
    }
    applyAutoWorkbenchTab(autoTab);
  }, [
    activeWorkbenchTab,
    evidenceItems,
    intakeSpec,
    reviewablePreviews,
    reviewItems,
    pendingReviewCount,
    selectedRecord,
    hasProgressContext,
    records.length,
  ]);

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
    setChangeSetActionState({
      executionId: selectedRecord?.id ?? null,
      action: null,
      unitIds: [],
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
      status: "已中断，正在把补充说明发回对话继续处理",
      sent: true,
    }));
    void sendMessage(
      workspaceId,
      [
        "请基于当前任务继续处理。",
        `上一轮执行 ID：${interventionState.executionId}`,
        "补充说明：",
        instruction,
        "请复用上一轮已经完成且仍可靠的证据和结果，避免无必要重复。",
      ].join("\n"),
      [],
      {
        metadata: {
          intervention: true,
          execution_id: interventionState.executionId,
          interrupted_execution_id: interventionState.executionId,
          orchestration: {
            intervention: true,
            execution_id: interventionState.executionId,
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
        status: "补充说明已提交，等待对话继续编排",
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

  async function handleApproveIntakeSpec(spec: IntakeSpecV1) {
    if (isSending || spec.status !== "ready" || spec.missing_fields.length > 0) {
      return;
    }
    await sendMessage(
      workspaceId,
      [
        `同意并开始执行这份 Spec：${spec.title}`,
        "请按澄清文档中的范围和参数启动团队执行。",
      ].join("\n"),
      [],
      {
        metadata: {
          orchestration: {
            feature_id: spec.capability_id,
            params: spec.params,
          },
          intake_spec_launch: {
            spec_id: spec.spec_id,
            revision: spec.revision,
          },
        },
      },
    );
  }

  async function handleChangeSetAction(
    action: ChangeSetReviewAction,
    unitIds: string[],
  ) {
    if (!selectedRecord || changeSetActionState.action !== null) {
      return;
    }
    const requestUnitIds = Array.from(
      new Set(unitIds.map((unitId) => unitId.trim()).filter(Boolean)),
    );
    if (requestUnitIds.length === 0) {
      return;
    }
    const requestExecutionId = selectedRecord.id;
    setChangeSetActionState({
      executionId: requestExecutionId,
      action,
      unitIds: requestUnitIds,
      error: null,
    });
    try {
      const response =
        action === "accept"
          ? await acceptExecutionChangeSetUnits({
              executionId: requestExecutionId,
              unitIds: requestUnitIds,
            })
          : action === "reject"
            ? await rejectExecutionChangeSetUnits({
                executionId: requestExecutionId,
                unitIds: requestUnitIds,
              })
            : await undoExecutionChangeSetUnits({
                executionId: requestExecutionId,
                unitIds: requestUnitIds,
              });
      if (!changeSetViewFromResponse(response)) {
        throw new Error("审阅状态同步失败，请刷新后重试");
      }
      patchChangeSetResponse(requestExecutionId, response);
      setChangeSetActionState((current) =>
        shouldApplyChangeSetActionResponse(
          current.executionId,
          requestExecutionId,
        )
          ? {
              executionId: requestExecutionId,
              action: null,
              unitIds: [],
              error: null,
            }
          : current,
      );
    } catch (error) {
      setChangeSetActionState((current) =>
        shouldApplyChangeSetActionResponse(
          current.executionId,
          requestExecutionId,
        )
          ? {
              executionId: requestExecutionId,
              action: null,
              unitIds: requestUnitIds,
              error: error instanceof Error ? error.message : "审阅变更失败",
            }
          : current,
      );
    }
  }

  function patchChangeSetResponse(
    executionId: string,
    response: ExecutionChangeSetResponse,
  ) {
    const recordToPatch = useExecutionStore.getState().executions.get(executionId);
    if (!recordToPatch) {
      return;
    }
    upsertExecution({
      ...recordToPatch,
      result: {
        ...(recordToPatch.result ?? {}),
        ...responseResultPatch(response),
      },
    });
  }

  function shouldApplyChangeSetActionResponse(
    currentExecutionId: string | null,
    requestExecutionId: string,
  ): boolean {
    return (
      currentExecutionId === requestExecutionId ||
      selectedRecordIdRef.current === requestExecutionId
    );
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
      status: "正在请求安全中断",
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
        background: "var(--wjn-bg-base)",
        fontFamily: "var(--wjn-font-sans)",
        color: "var(--wjn-text)",
      }}
    >
      <WorkbenchHeader
        activeTab={visibleWorkbenchTab}
        title={mission?.title ?? "研究任务"}
        eyebrow={typeConfig?.title ?? null}
        evidenceCount={evidenceItems.length}
        reviewCount={pendingReviewCount}
        showProgressTab={hasProgressContext}
        showReviewTab={
          pendingReviewCount > 0 ||
          activeWorkbenchTab === "review"
        }
        showSpecTab={Boolean(intakeSpec) || activeWorkbenchTab === "spec"}
        hasRunHistory={records.length > 0}
        isFullscreen={isFullscreen}
        canInterrupt={Boolean(runningRecord)}
        interventionOpen={interventionOpen}
        interventionStatus={interventionState.status}
        onTabChange={handleWorkbenchTabChange}
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
        {visibleWorkbenchTab === "overview" ? (
          <OverviewView
            typeConfig={typeConfig}
            selectedRecord={selectedRecord}
            selectedRunView={selectedRunView}
            mission={mission}
            records={records}
            pendingReviewCount={pendingReviewCount}
            evidenceCount={evidenceItems.length}
            hasMissionActivity={hasMissionActivity}
            onOpenRun={(runId) => {
              selectRun(runId);
              setActiveWorkbenchTab("run");
            }}
          />
        ) : null}
        {visibleWorkbenchTab === "spec" ? (
          <IntakeSpecPreview
            spec={intakeSpec}
            isSending={isSending}
            onApprove={(spec) => void handleApproveIntakeSpec(spec)}
          />
        ) : null}
        {visibleWorkbenchTab === "run" ? (
          <RunView
            record={selectedRecord}
            selectedNodeId={selectedNodeId}
            writeback={writeback}
            onSelectNode={selectNode}
            onOpenEvidence={() => setActiveWorkbenchTab("evidence")}
          />
        ) : null}
        {visibleWorkbenchTab === "review" ? (
          <ReviewView
            previews={reviewablePreviews}
            reviewItems={reviewItems}
            pendingReviewCount={pendingReviewCount}
            changeSet={changeSet}
            changeSetActionState={
              changeSetActionState.executionId === selectedRecord?.id
                ? changeSetActionState
                : undefined
            }
            selectedPreviewId={selectedPreviewId}
            writeback={writeback}
            onAcceptChangeUnits={(unitIds) =>
              void handleChangeSetAction("accept", unitIds)
            }
            onRejectChangeUnits={(unitIds) =>
              void handleChangeSetAction("reject", unitIds)
            }
            onUndoChangeUnits={(unitIds) =>
              void handleChangeSetAction("undo", unitIds)
            }
            onSelectPreview={setSelectedPreviewId}
          />
        ) : null}
        {visibleWorkbenchTab === "evidence" ? (
          <EvidenceView
            items={evidenceItems}
            mission={mission}
            filter={evidenceFilter}
            query={evidenceQuery}
            selectedId={selectedPreviewId}
            onFilterChange={setEvidenceFilter}
            onQueryChange={setEvidenceQuery}
            onSelect={(id) => setSelectedPreviewId(id)}
          />
        ) : null}
      </div>
    </div>
  );
}
