"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useShallow } from "zustand/react/shallow";

import type {
  WorkspaceCapability,
} from "@/lib/api/types";
import { cancelExecution, listExecutions } from "@/lib/api/executions";
import {
  buildCommittedRoomLinks,
  COMMIT_STATE_SYNC_ERROR,
  commitExecutionOutputs,
  commitStateFromCommitResponse,
  commitStateRoomTargets,
  type ExecutionCommitRequest,
  type ExecutionCommitState,
  isExecutionCommitted,
  isExecutionDiscarded,
  isExecutionReverted,
  readCommitStateFromResult,
  undoExecutionCommit,
} from "@/lib/execution-commit";
import type { WorkspaceResultPreview } from "@/lib/workspace-result-preview";
import type { WorkspaceTypeConfig } from "@/lib/workspace-suggestions";
import {
  buildOutputOverrides,
} from "@/lib/workbench-result-editing";
import {
  findLatestIntakeSpec,
  isSuperWorkflowCapability,
  type IntakeSpecV1,
} from "@/lib/intake-spec";
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
import { RunView } from "./live-workflow/RunView";
import { WorkbenchHeader } from "./live-workflow/WorkbenchHeader";
import { styles } from "./live-workflow/styles";
import type { EvidenceFilter } from "./live-workflow/types";
import { useLiveWorkflowViewModel } from "./live-workflow/useLiveWorkflowViewModel";
import {
  applyDraftLabelsToCommitLinks,
  generateUUID,
  isTerminalStatus,
  toggleChecked,
} from "./live-workflow/utils";

interface LiveWorkflowPanelProps {
  workspaceId: string;
  typeConfig?: WorkspaceTypeConfig;
  features?: WorkspaceCapability[];
  className?: string;
  "data-testid"?: string;
}

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
  const messages = useChatStoreV2((state) => state.messages);
  const sendMessage = useChatStoreV2((state) => state.sendMessage);
  const isSending = useChatStoreV2((state) => state.isSending);
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [selectedPreviewId, setSelectedPreviewId] = useState<string | null>(null);
  const [evidenceFilter, setEvidenceFilter] = useState<EvidenceFilter>("all");
  const [evidenceQuery, setEvidenceQuery] = useState("");
  const [commitState, setCommitState] = useState<{
    executionId: string | null;
    idempotencyKey: string;
    committing: boolean;
    reverting: boolean;
    responseCommitState: ExecutionCommitState | null;
    linkPreviews: WorkspaceResultPreview[] | null;
    error: string | null;
  }>(() => ({
    executionId: null,
    idempotencyKey: generateUUID(),
    committing: false,
    reverting: false,
    responseCommitState: null,
    linkPreviews: null,
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
  } = useLiveWorkflowViewModel({
    records: executionRecords,
    workspaceId,
    selectedRunId,
    focusedRunId,
    activeRunId,
    selectedPreviewId,
    draftEdits,
  });
  const selectedRecordIdRef = useRef<string | null>(null);
  selectedRecordIdRef.current = selectedRecord?.id ?? null;
  const durableCommitState = readCommitStateFromResult(selectedRecord?.result);
  const localCommitState =
    commitState.executionId === selectedRecord?.id
      ? commitState.responseCommitState
      : null;
  const effectiveCommitState = durableCommitState ?? localCommitState;
  const commitFinal = Boolean(effectiveCommitState);
  const commitCommitted = isExecutionCommitted(effectiveCommitState);
  const commitDiscarded = isExecutionDiscarded(effectiveCommitState);
  const commitReverted = isExecutionReverted(effectiveCommitState);
  const autoCommitAttemptedRef = useRef<Set<string>>(new Set());
  const commitLinkPreviews =
    commitState.executionId === selectedRecord?.id && commitState.linkPreviews
      ? commitState.linkPreviews
      : previews;
  const commitLinks = useMemo(
    () =>
      buildCommittedRoomLinks({
        workspaceId,
        previews: commitLinkPreviews,
        roomTargets: commitStateRoomTargets(effectiveCommitState),
      }),
    [commitLinkPreviews, effectiveCommitState, workspaceId],
  );
  const latestMessageSpec = useMemo(
    () => findLatestIntakeSpec(messages, workspaceId),
    [messages, workspaceId],
  );
  const intakeSpec = latestMessageSpec;
  const visibleWorkbenchTab =
    activeWorkbenchTab === "review" ? "run" : activeWorkbenchTab;

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
    if (activeWorkbenchTab === "spec" && intakeSpec) {
      return;
    }
    if (!selectedRecord) {
      setAutoWorkbenchTab("overview");
      return;
    }
    if (!isTerminalStatus(selectedRecord.status)) {
      setAutoWorkbenchTab("run");
      return;
    }
    if (
      activeWorkbenchTab === "evidence" &&
      evidenceItems.length > 0
    ) {
      return;
    }
    if (isTerminalStatus(selectedRecord.status)) {
      setAutoWorkbenchTab("run");
      return;
    }
    if (evidenceItems.length > 0) {
      setAutoWorkbenchTab("evidence");
      return;
    }
    setAutoWorkbenchTab("overview");
  }, [
    activeWorkbenchTab,
    evidenceItems.length,
    intakeSpec,
    previews.length,
    reviewItems.length,
    selectedRecord,
    setAutoWorkbenchTab,
  ]);

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
      committing: false,
      reverting: false,
      responseCommitState: null,
      linkPreviews: null,
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
        "请复用上一轮已经完成且仍可靠的证据和结果，避免无必要重复。",
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
    if (isSuperWorkflowCapability(feature.id)) {
      const prompt =
        feature.id === "software_copyright_application_pack"
          ? [
              "先帮我梳理软著申报材料包的执行 Spec。",
              "请通过对话确认：我要做一个什么软件、软件名称、Web 还是 App、后端语言偏好，以及是否有必须强调的功能点。",
              "Spec 写好后生成一张澄清卡片，等我同意后再开始执行。",
            ].join("\n")
          : [
              "先帮我梳理数学建模论文生成的执行 Spec。",
              "请通过对话确认题目、数据、竞赛格式和需要强调的建模方向。编程统一使用 Python，不要询问语言。",
              "Spec 写好后生成一张澄清卡片，等我同意后再开始执行。",
            ].join("\n");
      setActiveWorkbenchTab("spec");
      await sendMessage(workspaceId, prompt, [], {
        metadata: {
          workbench_launch: {
            capability_id: feature.id,
            capability_name: feature.name,
            mode: "intake",
          },
        },
      });
      return;
    }
    const prompt = [
      `我想使用「${feature.name}」能力。`,
      "请先确认启动所需的具体研究主题、材料或目标；信息足够时再组织研究团队。",
    ]
      .filter(Boolean)
      .join("\n");
    await sendMessage(workspaceId, prompt, [], {
      metadata: {
        orchestration: {
          feature_id: feature.id,
        },
        workbench_launch: {
          capability_id: feature.id,
          capability_name: feature.name,
        },
      },
    });
  }

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

  async function handleCommit(
    mode: "all" | "selected" | "discard",
    options?: { automatic?: boolean },
  ) {
    if (!selectedRecord || commitState.committing || commitState.reverting || commitFinal) {
      return;
    }
    const requestExecutionId = selectedRecord.id;
    const requestIdempotencyKey = commitState.idempotencyKey;
    const committablePreviews = previews.filter((preview) => preview.canCommit);
    const outputIds = committablePreviews.map((preview) => preview.id);
    const outputIdSet = new Set(outputIds);
    const canAcceptAll = selectedRecord.status === "completed" && outputIds.length > 0;
    if (mode !== "discard" && outputIds.length === 0) {
      return;
    }
    const useAcceptAll = mode === "all" && canAcceptAll;
    const acceptedIds =
      useAcceptAll
        ? outputIds
        : mode === "selected"
          ? Array.from(checkedIds).filter((id) => outputIdSet.has(id))
          : [];
    const body: ExecutionCommitRequest =
      useAcceptAll
        ? { accept_all: true }
        : { accepted_ids: acceptedIds };
    const overrides = options?.automatic
      ? null
      : buildOutputOverrides(acceptedIds, draftEdits);
    if (overrides) {
      body.output_overrides = overrides;
    }

    setCommitState((current) => ({
      ...current,
      executionId: requestExecutionId,
      committing: true,
      reverting: false,
      error: null,
      linkPreviews: null,
    }));
    try {
      const response = await commitExecutionOutputs({
        executionId: requestExecutionId,
        idempotencyKey: requestIdempotencyKey,
        body,
      });
      const commitLinkPreviews = applyDraftLabelsToCommitLinks(committablePreviews, draftEdits);
      const nextCommitState = commitStateFromCommitResponse(response);
      if (!nextCommitState) {
        setCommitState((current) =>
          shouldApplyCommitResponseToLocalState(
            current.executionId,
            requestExecutionId,
          )
            ? {
                ...current,
                committing: false,
                reverting: false,
                responseCommitState: null,
                linkPreviews: null,
                error: COMMIT_STATE_SYNC_ERROR,
              }
            : current,
        );
        return;
      }
      clearDraftEdits(acceptedIds);
      const recordToPatch =
        useExecutionStore.getState().executions.get(requestExecutionId);
      if (recordToPatch) {
        upsertExecution({
          ...recordToPatch,
          result: {
            ...(recordToPatch.result ?? {}),
            commit_state: nextCommitState,
          },
        });
      }
      setCommitState((current) =>
        shouldApplyCommitResponseToLocalState(
          current.executionId,
          requestExecutionId,
        )
          ? {
              ...current,
              executionId: requestExecutionId,
              committing: false,
              reverting: false,
              responseCommitState: nextCommitState,
              linkPreviews: commitLinkPreviews,
            }
          : current,
      );
    } catch (error) {
      setCommitState((current) =>
        shouldApplyCommitResponseToLocalState(
          current.executionId,
          requestExecutionId,
        )
          ? {
              ...current,
              committing: false,
              reverting: false,
              responseCommitState: null,
              linkPreviews: null,
              error: error instanceof Error ? error.message : "保存失败",
            }
          : current,
      );
    }
  }

  useEffect(() => {
    if (
      !selectedRecord ||
      selectedRecord.status !== "completed" ||
      effectiveCommitState ||
      commitState.committing ||
      commitState.reverting
    ) {
      return;
    }
    if (!previews.some((preview) => preview.canCommit)) {
      return;
    }
    const attempted = autoCommitAttemptedRef.current;
    if (attempted.has(selectedRecord.id)) {
      return;
    }
    attempted.add(selectedRecord.id);
    void handleCommit("all", { automatic: true });
  }, [
    commitState.committing,
    commitState.reverting,
    effectiveCommitState,
    previews,
    selectedRecord,
  ]);

  async function handleUndoCommit() {
    if (
      !selectedRecord ||
      commitState.committing ||
      commitState.reverting ||
      !effectiveCommitState ||
      effectiveCommitState.status !== "committed"
    ) {
      return;
    }
    const requestExecutionId = selectedRecord.id;
    setCommitState((current) => ({
      ...current,
      executionId: requestExecutionId,
      reverting: true,
      error: null,
    }));
    try {
      const response = await undoExecutionCommit({ executionId: requestExecutionId });
      const nextCommitState = commitStateFromCommitResponse(response);
      if (!nextCommitState) {
        setCommitState((current) =>
          shouldApplyCommitResponseToLocalState(
            current.executionId,
            requestExecutionId,
          )
            ? {
                ...current,
                reverting: false,
                responseCommitState: null,
                error: COMMIT_STATE_SYNC_ERROR,
              }
            : current,
        );
        return;
      }
      const recordToPatch =
        useExecutionStore.getState().executions.get(requestExecutionId);
      if (recordToPatch) {
        upsertExecution({
          ...recordToPatch,
          result: {
            ...(recordToPatch.result ?? {}),
            commit_state: nextCommitState,
          },
        });
      }
      setCommitState((current) =>
        shouldApplyCommitResponseToLocalState(
          current.executionId,
          requestExecutionId,
        )
          ? {
              ...current,
              reverting: false,
              responseCommitState: nextCommitState,
              linkPreviews: previews,
            }
          : current,
      );
    } catch (error) {
      setCommitState((current) =>
        shouldApplyCommitResponseToLocalState(
          current.executionId,
          requestExecutionId,
        )
          ? {
              ...current,
              reverting: false,
              error: error instanceof Error ? error.message : "撤回保存失败",
            }
          : current,
      );
    }
  }

  function shouldApplyCommitResponseToLocalState(
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
        activeTab={visibleWorkbenchTab}
        evidenceCount={evidenceItems.length}
        showProgressTab={Boolean(runningRecord) || activeWorkbenchTab === "run"}
        showSpecTab={Boolean(intakeSpec) || activeWorkbenchTab === "spec"}
        hasRunHistory={records.length > 0}
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
        {visibleWorkbenchTab === "overview" ? (
          <OverviewView
            typeConfig={typeConfig}
            features={features}
            records={records}
            pendingReviewCount={pendingReviewCount}
            evidenceCount={evidenceItems.length}
            isSending={isSending}
            onLaunchFeature={(feature) => void handleLaunchFeature(feature)}
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
            writeback={
              selectedRecord && isTerminalStatus(selectedRecord.status)
                ? {
                    committed: commitCommitted,
                    discarded: commitDiscarded,
                    reverted: commitReverted,
                    committing: commitState.committing,
                    reverting: commitState.reverting,
                    error: commitState.error,
                    links: commitLinks,
                    onUndo: () => void handleUndoCommit(),
                    onRetry: () => void handleCommit("all"),
                  }
                : undefined
            }
            onSelectNode={selectNode}
            onOpenEvidence={() => setActiveWorkbenchTab("evidence")}
          />
        ) : null}
        {visibleWorkbenchTab === "evidence" ? (
          <EvidenceView
            items={evidenceItems}
            filter={evidenceFilter}
            query={evidenceQuery}
            selectedId={selectedPreviewId}
            checkedIds={checkedIds}
            draftEdits={draftEdits}
            disabled={commitFinal || selectedRecord?.status === "completed"}
            onFilterChange={setEvidenceFilter}
            onQueryChange={setEvidenceQuery}
            onSelect={(id) => setSelectedPreviewId(id)}
            onToggleChecked={(id) => toggleChecked(setCheckedIds, id)}
            onPatchDraft={patchDraftData}
            onSetDraft={setDraftEdit}
          />
        ) : null}
      </div>
    </div>
  );
}
