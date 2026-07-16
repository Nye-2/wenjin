import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ComponentProps } from "react";

import { MissionConsole as MissionConsoleView } from "@/app/(workbench)/workspaces/[id]/components/mission-console/MissionConsole";
import type { MissionView } from "@/lib/api/mission-types";
import { useMissionUiStore } from "@/stores/mission-ui-store";

const { decideMissionReviewsMock, getMissionReviewPreviewMock, getMissionViewMock, listMissionEvidenceMock, listMissionArtifactsMock, listMissionItemsMock } = vi.hoisted(() => ({
  decideMissionReviewsMock: vi.fn(),
  getMissionReviewPreviewMock: vi.fn(),
  getMissionViewMock: vi.fn(),
  listMissionEvidenceMock: vi.fn(),
  listMissionArtifactsMock: vi.fn(),
  listMissionItemsMock: vi.fn(),
}));

vi.mock("@/lib/api/missions", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/missions")>("@/lib/api/missions");
  return {
    ...actual,
    decideMissionReviews: decideMissionReviewsMock,
    getMissionReviewPreview: getMissionReviewPreviewMock,
    getMissionView: getMissionViewMock,
    listMissionEvidence: listMissionEvidenceMock,
    listMissionArtifacts: listMissionArtifactsMock,
    listMissionItems: listMissionItemsMock,
  };
});

function MissionConsole(
  props: Omit<ComponentProps<typeof MissionConsoleView>, "onChatAction"> & {
    onChatAction?: ComponentProps<typeof MissionConsoleView>["onChatAction"];
  },
) {
  return (
    <MissionConsoleView
      {...props}
      onChatAction={props.onChatAction ?? (() => undefined)}
    />
  );
}

function makeView(): MissionView {
  return {
    missionId: "mission-1", workspaceId: "ws-1", title: "联邦微调研究空白", executionStatus: "running", statusLabel: "正在研究", activity: { state: "working", title: "问津正在推进当前研究" }, attentionRequest: null, createdAt: "2026-07-11T00:00:00Z", updatedAt: "2026-07-11T00:01:00Z",
    activeStage: { id: "literature", title: "查找与核验证据", status: "active", summary: "正在交叉核验关键文献" },
    stages: [{ id: "scope", title: "收敛问题", status: "passed" }, { id: "literature", title: "查找与核验证据", status: "active" }],
    requiredStageIds: ["scope", "literature"],
    teamSummary: "按方法、评测和隐私三个侧面并行推进",
    subagents: [{ id: "s-1", name: "严谨派阿澈", role: "方法与实验审校", status: "working", summary: "核对 Non-IID 设定" }],
    evidenceItems: [], artifactItems: [], evidenceCount: 0, artifactCount: 0,
    reviewItems: [{ id: "r-1", title: "可写创新点", targetKind: "claim", riskLevel: "high", status: "pending", suggestedSelected: false, batchAcceptable: false, requiresExplicitReview: true, previewAvailable: false, reasonLabel: "涉及核心论断，需要逐项确认", preview: { claim: "异构性与自适应秩聚合存在可验证关联" } }],
    reviewSummary: { pending: 1, needsMoreEvidence: 0, accepted: 0, committed: 0 }, reviewMode: "balanced_default", reviewPolicy: { protectedOutputsRequireConfirmation: true, draftOutputsMayBeAutomatic: true }, reviewSelectionRevision: "review-selection-revision-1",
    commitSummary: { pending: 0, applying: 0, committed: 0, failed: 0 }, qualityHighlights: [], lastItemSeq: 4, stateVersion: 2,
  };
}

describe("MissionConsole", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useMissionUiStore.getState().clearWorkspaceFocus();
    useMissionUiStore.getState().focusMission("mission-1", "progress");
    decideMissionReviewsMock.mockResolvedValue(makeView());
    getMissionViewMock.mockResolvedValue(makeView());
    getMissionReviewPreviewMock.mockResolvedValue({
      blob: new Blob(["visual"], { type: "image/png" }),
      mimeType: "image/png",
    });
    listMissionEvidenceMock.mockResolvedValue({
      items: [{ id: "ev-2", title: "后续核验证据", sourceType: "paper", verified: true }],
      nextCursor: null,
      total: 2,
    });
    listMissionArtifactsMock.mockResolvedValue({
      items: [{ id: "artifact-2", title: "完整研究稿", kind: "document", previewAvailable: true, committed: false }],
      nextCursor: null,
      total: 2,
    });
    listMissionItemsMock.mockResolvedValue({ items: [{ id: "i-1", missionId: "mission-1", seq: 1, itemType: "evidence", phase: "completed", summary: "找到一篇可核验论文", createdAt: "2026-07-11T00:00:00Z" }], nextCursor: null });
  });

  it("shows dynamic members and server-projected progress", () => {
    render(<MissionConsole view={makeView()} onClose={() => undefined} onViewChange={() => undefined} />);
    expect(screen.getByText("严谨派阿澈")).toBeInTheDocument();
    expect(screen.getByText("查找与核验证据")).toBeInTheDocument();
    expect(screen.queryByText(/provider|schema|high risk|blocked/i)).not.toBeInTheDocument();
  });

  it.each([
    ["retrying", "连接暂时波动，问津正在重试", "重试中"],
    ["recovering", "当前步骤未完成，问津正在调整方案", "调整中"],
    ["collaborating", "研究成员正在协作", "协作中"],
    ["unavailable", "模型服务暂时不可用", "稍后再试"],
  ] as const)("shows the %s activity projection in progress", (state, title, label) => {
    const view = makeView();
    view.activity = { state, title, summary: "任务进度已经保留。", attempt: state === "retrying" ? 2 : null };

    render(<MissionConsole view={view} onClose={() => undefined} onViewChange={() => undefined} />);

    expect(screen.getByTestId("mission-activity")).toHaveTextContent(title);
    expect(screen.getByTestId("mission-activity")).toHaveTextContent(label);
    expect(screen.queryByText(/provider|raw error/i)).not.toBeInTheDocument();
  });

  it("uses the retry activity in compact peek", () => {
    const view = makeView();
    view.activity = {
      state: "retrying",
      title: "连接暂时波动，问津正在重试",
      summary: "任务进度已经保留，无需重新开始。",
      attempt: 2,
    };
    useMissionUiStore.getState().closePanel();
    useMissionUiStore.getState().peekMission(view.missionId);

    render(<MissionConsole view={view} onClose={() => undefined} onViewChange={() => undefined} />);

    expect(screen.getByTestId("mission-console-peek")).toHaveTextContent("连接暂时波动，问津正在重试");
    expect(screen.getByTestId("mission-console-peek")).toHaveTextContent("正在进行第 2 次尝试");
  });

  it("shows stale MissionView state without exposing the raw load error and retries", async () => {
    const view = makeView();
    view.isStale = true;
    view.loadError = "provider raw error: upstream unavailable";
    const onViewChange = vi.fn();

    render(<MissionConsole view={view} onClose={() => undefined} onViewChange={onViewChange} />);

    expect(screen.getByTestId("mission-stale-notice")).toHaveTextContent("上次已加载的任务进度");
    expect(screen.queryByText(/provider raw error/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await waitFor(() => expect(getMissionViewMock).toHaveBeenCalledWith("mission-1"));
    expect(onViewChange).toHaveBeenCalled();
  });

  it("delegates waiting-task chat actions without querying the document", () => {
    const view = makeView();
    view.executionStatus = "waiting";
    view.attentionRequest = {
      requestId: "request-1",
      reason: "external_data",
      title: "还需要赛题文件",
      summary: "上传 PDF 后会从当前进度继续。",
      impact: "未上传前不会开始求解。",
      requiredInputs: [
        {
          id: "problem-file",
          label: "赛题 PDF",
          inputType: "file",
          required: true,
        },
      ],
      actions: [
        {
          id: "upload",
          label: "上传赛题",
          actionType: "upload_file",
          primary: true,
        },
      ],
    };
    const onChatAction = vi.fn();

    render(
      <MissionConsole
        view={view}
        onClose={() => undefined}
        onViewChange={() => undefined}
        onChatAction={onChatAction}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "上传赛题" }));

    expect(onChatAction).toHaveBeenCalledWith("attach");
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
      decisions: [{ reviewItemId: "r-1", decision: "rejected" }],
    }));
  });

  it("renders document preview bodies as markdown instead of raw transport JSON", () => {
    const view = makeView();
    view.reviewItems[0].preview = {
      body: "# 问题理解\n\n这是可复核的任务正文。",
      format: "markdown",
      title: "建模问题简报",
    };

    render(<MissionConsole view={view} onClose={() => undefined} onViewChange={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: /确认/ }));
    fireEvent.click(screen.getByText("查看内容预览"));

    expect(screen.getByRole("heading", { name: "问题理解" })).toBeInTheDocument();
    expect(screen.getByText("这是可复核的任务正文。")).toBeInTheDocument();
    expect(screen.queryByText(/\"format\": \"markdown\"/)).not.toBeInTheDocument();
  });

  it("loads authenticated academic visual candidates and keeps preview refs private", async () => {
    const createObjectUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:visual-review");
    const revokeObjectUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    const view = makeView();
    view.reviewItems[0] = {
      ...view.reviewItems[0],
      title: "Non-IID 客户端性能对比",
      previewAvailable: true,
      previewUrl: "/api/missions/mission-1/review-items/r-1/preview",
      preview: {
        artifact_kind: "chart",
        mime_type: "image/png",
        figure_type: "grouped_bar",
        strategy: "matplotlib",
        evidence_level: "evidence",
        caption: "不同异构程度下的客户端准确率。",
        alt_text: "三组柱状图比较不同方法准确率",
        renderer_id: "matplotlib-3.10",
        source_refs: ["results.csv"],
        reproducibility_status: "verified",
      },
      visual: {
        artifactKind: "chart",
        mimeType: "image/png",
        figureType: "grouped_bar",
        strategy: "matplotlib",
        evidenceLevel: "evidence",
        caption: "不同异构程度下的客户端准确率。",
        altText: "三组柱状图比较不同方法准确率",
        rendererId: "matplotlib-3.10",
        sourceLabels: ["results.csv"],
        reproducibilityStatus: "verified",
      },
    };

    const { unmount } = render(<MissionConsole view={view} onClose={() => undefined} onViewChange={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: /确认/ }));

    await waitFor(() => expect(screen.getByRole("img", { name: "三组柱状图比较不同方法准确率" })).toHaveAttribute("src", "blob:visual-review"));
    expect(getMissionReviewPreviewMock).toHaveBeenCalledWith({ missionId: "mission-1", reviewItemId: "r-1" });
    expect(screen.getByText(/Matplotlib/)).toBeInTheDocument();
    expect(screen.getByText(/来源：results.csv/)).toBeInTheDocument();
    expect(screen.getByText(/复现：已验证/)).toBeInTheDocument();
    expect(screen.queryByText(/mission-previews\/private/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "放大视觉预览" }));
    expect(screen.getByRole("button", { name: "缩小视觉预览" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "在新窗口查看" }));
    expect(open).toHaveBeenCalledWith("blob:visual-review", "_blank", "noopener,noreferrer");

    unmount();
    expect(createObjectUrl).toHaveBeenCalled();
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:visual-review");
  });

  it("offers a safe open action for PDF visual candidates", async () => {
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:visual-pdf");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    getMissionReviewPreviewMock.mockResolvedValueOnce({
      blob: new Blob(["pdf"], { type: "application/pdf" }),
      mimeType: "application/pdf",
    });
    const view = makeView();
    view.reviewItems[0] = {
      ...view.reviewItems[0],
      previewAvailable: true,
      previewUrl: "/api/missions/mission-1/review-items/r-1/preview",
      visual: {
        artifactKind: "figure",
        mimeType: "application/pdf",
        figureType: "mechanism_schematic",
        strategy: "graphviz",
        evidenceLevel: "explanatory",
        caption: null,
        altText: null,
        rendererId: "tectonic",
        sourceLabels: [],
        reproducibilityStatus: "complete",
      },
    };

    render(<MissionConsole view={view} onClose={() => undefined} onViewChange={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: /确认/ }));
    const viewPdf = await screen.findByRole("button", { name: "查看 PDF 预览" });
    fireEvent.click(viewPdf);
    expect(open).toHaveBeenCalledWith("blob:visual-pdf", "_blank", "noopener,noreferrer");
    expect(screen.queryByText(/mission-previews\/private/)).not.toBeInTheDocument();
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
    expect(listMissionArtifactsMock).toHaveBeenCalledWith({ missionId: "mission-1", cursor: 14 });
  });

  it("loads semantic trace only after the user asks", async () => {
    render(<MissionConsole view={makeView()} onClose={() => undefined} onViewChange={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: "轨迹" }));
    expect(screen.getByTestId("mission-trace-idle")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "加载任务轨迹" }));
    await waitFor(() => expect(screen.getByText("找到一篇可核验论文")).toBeInTheDocument());
    expect(screen.queryByText(/tool_json|stdout|api_key/i)).not.toBeInTheDocument();
  });

  it("catches an initial trace failure and retries it", async () => {
    listMissionItemsMock
      .mockRejectedValueOnce(new Error("provider raw trace error"))
      .mockResolvedValueOnce({ items: [{ id: "i-2", missionId: "mission-1", seq: 2, itemType: "stage", phase: "completed", summary: "完成研究问题收敛", createdAt: "2026-07-11T00:02:00Z" }], nextCursor: null });
    render(<MissionConsole view={makeView()} onClose={() => undefined} onViewChange={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: "轨迹" }));

    fireEvent.click(screen.getByRole("button", { name: "加载任务轨迹" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("任务轨迹暂时未能加载，请重试");
    expect(screen.queryByText(/provider raw trace error/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "重新加载任务轨迹" }));
    expect(await screen.findByText("完成研究问题收敛")).toBeInTheDocument();
    expect(listMissionItemsMock).toHaveBeenCalledTimes(2);
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

  it("renders required inputs and delegates chat focus for a waiting mission", () => {
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
    const onChatAction = vi.fn();

    render(
      <MissionConsole
        view={view}
        onClose={() => undefined}
        onViewChange={() => undefined}
        onChatAction={onChatAction}
      />,
    );
    expect(screen.getByTestId("mission-attention-request")).toHaveTextContent("题目 PDF");
    expect(screen.getByTestId("mission-attention-request")).toHaveTextContent("相关证据核验与后续写作会暂停");
    fireEvent.click(screen.getByRole("button", { name: "回到对话回复" }));

    expect(onChatAction).toHaveBeenCalledWith("focus");
  });
});
