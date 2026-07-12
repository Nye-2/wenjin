import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MissionConsole } from "@/app/(workbench)/workspaces/[id]/components/mission-console/MissionConsole";
import type { MissionView } from "@/lib/api/mission-types";
import { useMissionUiStore } from "@/stores/mission-ui-store";

const { decideMissionReviewsMock, listMissionEvidenceMock, listMissionArtifactsMock } = vi.hoisted(() => ({
  decideMissionReviewsMock: vi.fn(),
  listMissionEvidenceMock: vi.fn(),
  listMissionArtifactsMock: vi.fn(),
}));

vi.mock("@/lib/api/missions", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/missions")>("@/lib/api/missions");
  return {
    ...actual,
    decideMissionReviews: decideMissionReviewsMock,
    listMissionEvidence: listMissionEvidenceMock,
    listMissionArtifacts: listMissionArtifactsMock,
    listMissionItems: vi.fn().mockResolvedValue({ items: [{ id: "i-1", missionId: "mission-1", seq: 1, itemType: "evidence", phase: "completed", summary: "找到一篇可核验论文", createdAt: "2026-07-11T00:00:00Z" }], nextCursor: null }),
  };
});

function makeView(): MissionView {
  return {
    missionId: "mission-1", workspaceId: "ws-1", title: "联邦微调研究空白", executionStatus: "running", statusLabel: "正在研究", attentionRequest: null, createdAt: "2026-07-11T00:00:00Z", updatedAt: "2026-07-11T00:01:00Z",
    activeStage: { id: "literature", title: "查找与核验证据", status: "active", summary: "正在交叉核验关键文献" },
    stages: [{ id: "scope", title: "收敛问题", status: "passed" }, { id: "literature", title: "查找与核验证据", status: "active" }],
    requiredStageIds: ["scope", "literature"],
    teamSummary: "按方法、评测和隐私三个侧面并行推进",
    subagents: [{ id: "s-1", name: "严谨派阿澈", role: "方法与实验审校", status: "working", summary: "核对 Non-IID 设定" }],
    evidenceItems: [], artifactItems: [], evidenceCount: 0, artifactCount: 0,
    reviewItems: [{ id: "r-1", title: "可写创新点", targetKind: "claim", riskLevel: "high", status: "pending", suggestedSelected: false, batchAcceptable: false, requiresExplicitReview: true, reasonLabel: "涉及核心论断，需要逐项确认", preview: { claim: "异构性与自适应秩聚合存在可验证关联" } } as MissionView["reviewItems"][number] & { requiresExplicitReview: boolean }],
    reviewSummary: { pending: 1, needsMoreEvidence: 0, accepted: 0, committed: 0 }, reviewMode: "balanced_default", reviewPolicy: { protectedOutputsRequireConfirmation: true, draftOutputsMayBeAutomatic: true }, reviewSelectionRevision: 1,
    commitSummary: { pending: 0, applying: 0, committed: 0, failed: 0 }, qualityHighlights: [], lastItemSeq: 4, stateVersion: 2,
  };
}

describe("MissionConsole", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useMissionUiStore.getState().clearWorkspaceFocus();
    useMissionUiStore.getState().focusMission("mission-1", "progress");
    decideMissionReviewsMock.mockResolvedValue(makeView());
    listMissionEvidenceMock.mockResolvedValue({
      items: [{ id: "ev-2", title: "后续核验证据", sourceType: "paper", verified: true }],
      nextCursor: null,
    });
    listMissionArtifactsMock.mockResolvedValue({
      items: [{ id: "artifact-2", title: "完整研究稿", kind: "document", previewAvailable: true, committed: false }],
      nextCursor: null,
    });
  });

  it("shows dynamic members and server-projected progress", () => {
    render(<MissionConsole view={makeView()} onClose={() => undefined} onViewChange={() => undefined} />);
    expect(screen.getByText("严谨派阿澈")).toBeInTheDocument();
    expect(screen.getByText("查找与核验证据")).toBeInTheDocument();
    expect(screen.queryByText(/provider|schema|high risk|blocked/i)).not.toBeInTheDocument();
  });

  it("prevents protected review items from batch acceptance", () => {
    render(<MissionConsole view={makeView()} onClose={() => undefined} onViewChange={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: /确认/ }));
    fireEvent.click(screen.getByLabelText("选择 可写创新点"));
    expect(screen.getByRole("button", { name: "确认选中" })).toBeDisabled();
    expect(screen.getByText("需逐项确认")).toBeInTheDocument();
  });

  it("shows the canonical preview and supports rejecting one item", async () => {
    render(<MissionConsole view={makeView()} onClose={() => undefined} onViewChange={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: /确认/ }));
    fireEvent.click(screen.getByText("查看内容预览"));
    expect(screen.getByText(/异构性与自适应秩聚合存在可验证关联/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "不采纳" }));
    await waitFor(() => expect(decideMissionReviewsMock).toHaveBeenCalledWith({
      missionId: "mission-1",
      reviewSelectionRevision: 1,
      decisions: [{ reviewItemId: "r-1", decision: "rejected" }],
    }));
  });

  it("loads additional evidence and artifacts from their projection cursors", async () => {
    const view = makeView();
    view.evidenceItems = [{ id: "ev-1", title: "首批证据", sourceType: "paper", verified: true }];
    view.evidenceCount = 2;
    view.evidenceNextCursor = 12;
    view.artifactItems = [{ id: "artifact-1", title: "研究提纲", kind: "document", previewAvailable: true, committed: false }];
    view.artifactCount = 2;
    view.artifactNextCursor = 14;
    render(<MissionConsole view={view} onClose={() => undefined} onViewChange={() => undefined} />);

    fireEvent.click(screen.getByRole("tab", { name: /证据/ }));
    fireEvent.click(screen.getByRole("button", { name: /加载更多证据/ }));
    await waitFor(() => expect(screen.getByText("后续核验证据")).toBeInTheDocument());
    expect(listMissionEvidenceMock).toHaveBeenCalledWith({ missionId: "mission-1", cursor: 12 });

    fireEvent.click(screen.getByRole("tab", { name: /成果/ }));
    fireEvent.click(screen.getByRole("button", { name: /加载更多成果/ }));
    await waitFor(() => expect(screen.getByText("完整研究稿")).toBeInTheDocument());
    expect(listMissionArtifactsMock).toHaveBeenCalledWith(expect.objectContaining({ missionId: "mission-1", cursor: 14 }));
  });

  it("loads semantic trace only after the user asks", async () => {
    render(<MissionConsole view={makeView()} onClose={() => undefined} onViewChange={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: "轨迹" }));
    expect(screen.getByTestId("mission-trace-idle")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "加载任务轨迹" }));
    await waitFor(() => expect(screen.getByText("找到一篇可核验论文")).toBeInTheDocument());
    expect(screen.queryByText(/tool_json|stdout|api_key/i)).not.toBeInTheDocument();
  });

  it("shows the canonical attention request in peek instead of generic progress", () => {
    const view = makeView();
    view.executionStatus = "waiting";
    view.statusLabel = "等待你的回应";
    view.attentionRequest = {
      requestId: "request-materials-1",
      reason: "external_data",
      title: "需要你补充研究材料",
      summary: "请上传题目 PDF 和已有数据表。",
      impact: "收到材料前，相关证据核验与后续写作会暂停。",
      requiredInputs: [{ id: "pdf", label: "题目 PDF", inputType: "file", required: true }],
      actions: [
        { id: "reply", label: "回到对话回复", actionType: "reply_in_chat", primary: true },
        { id: "upload", label: "添加材料", actionType: "upload_file", primary: false },
      ],
    };
    useMissionUiStore.getState().closePanel();
    useMissionUiStore.getState().peekMission(view.missionId);

    render(<MissionConsole view={view} onClose={() => undefined} onViewChange={() => undefined} />);

    expect(screen.getByTestId("mission-console-peek")).toHaveTextContent("需要你补充研究材料");
    expect(screen.getByTestId("mission-console-peek")).toHaveTextContent("请上传题目 PDF 和已有数据表。");
    expect(screen.getByTestId("mission-console-peek")).not.toHaveTextContent("问津正在推进这项研究任务");
  });

  it("renders required inputs and focuses chat for a waiting mission", () => {
    const view = makeView();
    view.executionStatus = "waiting";
    view.statusLabel = "等待你的回应";
    view.attentionRequest = {
      requestId: "request-materials-1",
      reason: "external_data",
      title: "需要你补充研究材料",
      summary: "请上传题目 PDF 和已有数据表。",
      impact: "收到材料前，相关证据核验与后续写作会暂停。",
      requiredInputs: [{ id: "pdf", label: "题目 PDF", inputType: "file", required: true }],
      actions: [{ id: "reply", label: "回到对话回复", actionType: "reply_in_chat", primary: true }],
    };
    const composer = document.createElement("textarea");
    composer.dataset.testid = "chat-composer-input";
    document.body.appendChild(composer);

    render(<MissionConsole view={view} onClose={() => undefined} onViewChange={() => undefined} />);
    expect(screen.getByTestId("mission-attention-request")).toHaveTextContent("题目 PDF");
    expect(screen.getByTestId("mission-attention-request")).toHaveTextContent("相关证据核验与后续写作会暂停");
    fireEvent.click(screen.getByRole("button", { name: "回到对话回复" }));

    expect(composer).toHaveFocus();
    composer.remove();
  });
});
