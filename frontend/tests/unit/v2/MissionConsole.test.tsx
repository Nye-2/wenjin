import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ComponentProps } from "react";

import { MissionConsole as MissionConsoleView } from "@/app/(workbench)/workspaces/[id]/components/mission-console/MissionConsole";
import type { MissionView } from "@/lib/api/mission-types";
import type { MissionMutationResult } from "@/lib/api/missions";
import { useMissionUiStore } from "@/stores/mission-ui-store";

const { commitMissionReviewsMock, decideMissionReviewsMock, getMissionReviewPreviewMock, getMissionViewMock, listMissionEvidenceMock, listMissionArtifactsMock, listMissionItemsMock, resolveMissionPermissionMock } = vi.hoisted(() => ({
  commitMissionReviewsMock: vi.fn(),
  decideMissionReviewsMock: vi.fn(),
  getMissionReviewPreviewMock: vi.fn(),
  getMissionViewMock: vi.fn(),
  listMissionEvidenceMock: vi.fn(),
  listMissionArtifactsMock: vi.fn(),
  listMissionItemsMock: vi.fn(),
  resolveMissionPermissionMock: vi.fn(),
}));

vi.mock("@/lib/api/missions", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/missions")>("@/lib/api/missions");
  return {
    ...actual,
    commitMissionReviews: commitMissionReviewsMock,
    decideMissionReviews: decideMissionReviewsMock,
    getMissionReviewPreview: getMissionReviewPreviewMock,
    getMissionView: getMissionViewMock,
    listMissionEvidence: listMissionEvidenceMock,
    listMissionArtifacts: listMissionArtifactsMock,
    listMissionItems: listMissionItemsMock,
    resolveMissionPermission: resolveMissionPermissionMock,
  };
});

function MissionConsole(
  props: Omit<ComponentProps<typeof MissionConsoleView>, "onChatAction" | "onMissionTarget"> & {
    onChatAction?: ComponentProps<typeof MissionConsoleView>["onChatAction"];
    onMissionTarget?: ComponentProps<typeof MissionConsoleView>["onMissionTarget"];
  },
) {
  return (
    <MissionConsoleView
      {...props}
      onChatAction={props.onChatAction ?? (() => undefined)}
      onMissionTarget={props.onMissionTarget ?? (async () => true)}
    />
  );
}

function makeView(missionId = "mission-1"): MissionView {
  return {
    missionId, workspaceId: "ws-1", title: missionId === "mission-1" ? "联邦微调研究空白" : missionId, executionStatus: "running", statusLabel: "正在研究", activity: { state: "working", title: "问津正在推进当前研究" }, attentionRequest: null, createdAt: "2026-07-11T00:00:00Z", updatedAt: "2026-07-11T00:01:00Z",
    activeStage: { id: "literature", title: "查找与核验证据", status: "active", summary: "正在交叉核验关键文献" },
    stages: [{ id: "scope", title: "收敛问题", status: "passed" }, { id: "literature", title: "查找与核验证据", status: "active" }],
    requiredStageIds: ["scope", "literature"],
    teamSummary: "按方法、评测和隐私三个侧面并行推进",
    subagents: [{ id: "s-1", name: "严谨派阿澈", role: "方法与实验审校", status: "working", summary: "核对 Non-IID 设定" }],
    evidenceItems: [], artifactItems: [], evidenceCount: 0, artifactCount: 0,
    reviewItems: [{ id: "r-1", title: "可写创新点", targetKind: "claim", riskLevel: "high", status: "pending", suggestedSelected: false, batchAcceptable: false, requiresExplicitReview: true, previewAvailable: false, commitEligible: false, reasonLabel: "涉及核心论断，需要逐项确认", preview: { claim: "异构性与自适应秩聚合存在可验证关联" } }],
    reviewSummary: { pending: 1, needsMoreEvidence: 0, accepted: 0, committed: 0 }, reviewMode: "balanced_default", reviewPolicy: { protectedOutputsRequireConfirmation: true, draftOutputsMayBeAutomatic: true }, reviewSelectionRevision: "review-selection-revision-1",
    commitSummary: { pending: 0, applying: 0, committed: 0, failed: 0 }, qualityHighlights: [], lastItemSeq: 4, stateVersion: 2,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

describe("MissionConsole", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useMissionUiStore.getState().clearWorkspaceFocus();
    useMissionUiStore.getState().focusMission("mission-1", "progress");
    commitMissionReviewsMock.mockResolvedValue({ targetMissionId: "mission-1", issueCodes: [] });
    decideMissionReviewsMock.mockResolvedValue({ targetMissionId: "mission-1", issueCodes: [] });
    resolveMissionPermissionMock.mockResolvedValue(undefined);
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
    render(<MissionConsole view={makeView()} onClose={() => undefined} />);
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

    render(<MissionConsole view={view} onClose={() => undefined} />);

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

    render(<MissionConsole view={view} onClose={() => undefined} />);

    expect(screen.getByTestId("mission-console-peek")).toHaveTextContent("连接暂时波动，问津正在重试");
    expect(screen.getByTestId("mission-console-peek")).toHaveTextContent("正在进行第 2 次尝试");
  });

  it("shows stale MissionView state without exposing the raw load error and retries", async () => {
    const view = makeView();
    view.isStale = true;
    view.loadError = "provider raw error: upstream unavailable";
    const onMissionTarget = vi.fn().mockResolvedValue(true);

    render(<MissionConsole view={view} onClose={() => undefined} onMissionTarget={onMissionTarget} />);

    expect(screen.getByTestId("mission-stale-notice")).toHaveTextContent("上次已加载的任务进度");
    expect(screen.queryByText(/provider raw error/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await waitFor(() => expect(onMissionTarget).toHaveBeenCalledWith("mission-1"));
    expect(getMissionViewMock).not.toHaveBeenCalled();
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
        onMissionTarget={async () => true}
        onChatAction={onChatAction}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "上传赛题" }));

    expect(onChatAction).toHaveBeenCalledWith("attach");
  });

  it("prevents protected review items from batch acceptance", () => {
    render(<MissionConsole view={makeView()} onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: /确认/ }));
    fireEvent.click(screen.getByLabelText("选择 可写创新点"));
    expect(screen.getByRole("button", { name: "确认选中" })).toBeDisabled();
    expect(screen.getByText("需逐项确认")).toBeInTheDocument();
  });

  it("keeps local review choices when the review tab remounts", () => {
    const view = makeView();
    view.reviewItems[0] = {
      ...view.reviewItems[0],
      batchAcceptable: true,
      requiresExplicitReview: false,
    };
    render(<MissionConsole view={view} onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: /确认/ }));
    const checkbox = screen.getByLabelText("选择 可写创新点");
    fireEvent.click(checkbox);
    expect(checkbox).toBeChecked();

    fireEvent.click(screen.getByRole("tab", { name: "进展" }));
    fireEvent.click(screen.getByRole("tab", { name: /确认/ }));

    expect(screen.getByLabelText("选择 可写创新点")).toBeChecked();
  });

  it("holds a synchronous submission lock while a review decision is in flight", async () => {
    let resolveDecision: ((value: MissionMutationResult) => void) | undefined;
    decideMissionReviewsMock.mockReturnValueOnce(new Promise((resolve) => {
      resolveDecision = resolve;
    }));
    render(<MissionConsole view={makeView()} onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: /确认/ }));
    const confirm = screen.getByRole("button", { name: "确认此项" });

    fireEvent.click(confirm);
    fireEvent.click(confirm);

    expect(decideMissionReviewsMock).toHaveBeenCalledTimes(1);
    expect(confirm).toBeDisabled();
    expect(screen.getByRole("button", { name: "不采纳" })).toBeDisabled();

    await act(async () => resolveDecision?.({ targetMissionId: "mission-1", issueCodes: [] }));
    await waitFor(() => expect(confirm).toBeEnabled());
  });

  it("does not issue a duplicate commit while save is in flight", async () => {
    let resolveCommit: ((value: MissionMutationResult) => void) | undefined;
    commitMissionReviewsMock.mockReturnValueOnce(new Promise((resolve) => {
      resolveCommit = resolve;
    }));
    const view = makeView();
    view.reviewItems[0] = {
      ...view.reviewItems[0],
      status: "accepted",
      commitEligible: true,
    };
    view.reviewSummary = { pending: 0, needsMoreEvidence: 0, accepted: 1, committed: 0 };
    render(<MissionConsole view={view} onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: /确认/ }));
    const save = screen.getByRole("button", { name: "保存已确认内容" });

    fireEvent.click(save);
    fireEvent.click(save);

    expect(commitMissionReviewsMock).toHaveBeenCalledTimes(1);
    expect(save).toBeDisabled();

    await act(async () => resolveCommit?.({ targetMissionId: "mission-1", issueCodes: [] }));
    await waitFor(() => expect(save).toBeEnabled());
  });

  it("shows the canonical preview and supports rejecting one item", async () => {
    render(<MissionConsole view={makeView()} onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: /确认/ }));
    fireEvent.click(screen.getByText("查看内容预览"));
    expect(screen.getByText(/异构性与自适应秩聚合存在可验证关联/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "不采纳" }));
    await waitFor(() => expect(decideMissionReviewsMock).toHaveBeenCalledWith({
      missionId: "mission-1",
      decisions: [{ reviewItemId: "r-1", decision: "rejected" }],
    }));
  });

  it("keeps an accepted command distinct from a delayed projection refresh", async () => {
    const onMissionTarget = vi.fn().mockResolvedValue(false);
    decideMissionReviewsMock.mockResolvedValueOnce({
      targetMissionId: "mission-continuation",
      issueCodes: [],
    });
    render(
      <MissionConsole
        view={makeView()}
        onClose={() => undefined}
        onMissionTarget={onMissionTarget}
      />,
    );
    fireEvent.click(screen.getByRole("tab", { name: /确认/ }));
    fireEvent.click(screen.getByRole("button", { name: "不采纳" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "操作已受理，最新任务状态正在同步",
    );
    expect(onMissionTarget).toHaveBeenCalledWith("mission-continuation");
    expect(screen.queryByText("确认失败")).not.toBeInTheDocument();
  });

  it("renders document preview bodies as markdown instead of raw transport JSON", () => {
    const view = makeView();
    view.reviewItems[0].preview = {
      body: "# 问题理解\n\n这是可复核的任务正文。",
      format: "markdown",
      title: "建模问题简报",
    };

    render(<MissionConsole view={view} onClose={() => undefined} />);
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

    const { rerender, unmount } = render(<MissionConsole view={view} onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: /确认/ }));

    await waitFor(() => expect(screen.getByRole("img", { name: "三组柱状图比较不同方法准确率" })).toHaveAttribute("src", "blob:visual-review"));
    expect(getMissionReviewPreviewMock).toHaveBeenCalledWith({ missionId: "mission-1", reviewItemId: "r-1" });
    expect(screen.getByText(/Matplotlib/)).toBeInTheDocument();
    expect(screen.getByText(/来源：results.csv/)).toBeInTheDocument();
    expect(screen.getByText(/复现：已验证/)).toBeInTheDocument();
    expect(screen.queryByText(/mission-previews\/private/)).not.toBeInTheDocument();

    const refreshedView = {
      ...view,
      stateVersion: view.stateVersion + 1,
      reviewItems: view.reviewItems.map((item) => ({
        ...item,
        visual: item.visual ? { ...item.visual } : null,
      })),
    };
    rerender(<MissionConsole view={refreshedView} onClose={() => undefined} />);
    expect(getMissionReviewPreviewMock).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "放大视觉预览" }));
    expect(screen.getByRole("button", { name: "缩小视觉预览" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "在新窗口查看" }));
    expect(open).toHaveBeenCalledWith("blob:visual-review", "_blank", "noopener,noreferrer");

    unmount();
    expect(createObjectUrl).toHaveBeenCalled();
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:visual-review");
  });

  it("offers the committed visual insertion through the canonical Prism route", () => {
    const view = makeView();
    view.reviewItems[0] = {
      ...view.reviewItems[0],
      targetKind: "workspace_asset",
      status: "committed",
      commitStatus: "committed",
      committedTargetRef: "asset-1",
      visual: {
        artifactKind: "figure",
        mimeType: "image/png",
        figureType: "graphical_abstract",
        strategy: "llm_image",
        evidenceLevel: "explanatory",
        caption: "Federated tuning workflow",
        altText: "Federated tuning workflow",
        rendererId: "gpt-image-2",
        sourceLabels: [],
        reproducibilityStatus: null,
      },
    };
    view.reviewSummary = { pending: 0, needsMoreEvidence: 0, accepted: 0, committed: 1 };

    render(<MissionConsole view={view} onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: /确认/ }));

    expect(screen.getByRole("link", { name: "插入写作台" })).toHaveAttribute(
      "href",
      "/workspaces/ws-1/prism?visual_mission_id=mission-1&visual_review_item_id=r-1",
    );
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

    render(<MissionConsole view={view} onClose={() => undefined} />);
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
    render(<MissionConsole view={view} onClose={() => undefined} />);

    fireEvent.click(screen.getByRole("tab", { name: /来源与结果/ }));
    fireEvent.click(screen.getByRole("button", { name: /加载更多/ }));
    await waitFor(() => expect(screen.getByText("后续核验证据")).toBeInTheDocument());
    expect(listMissionEvidenceMock).toHaveBeenCalledWith({ missionId: "mission-1", cursor: 12 });

    fireEvent.click(screen.getByRole("tab", { name: /成果/ }));
    fireEvent.click(screen.getByRole("button", { name: /加载更多成果/ }));
    await waitFor(() => expect(screen.getByText("完整研究稿")).toBeInTheDocument());
    expect(listMissionArtifactsMock).toHaveBeenCalledWith({ missionId: "mission-1", cursor: 14 });
  });

  it("drops a late evidence page after Mission identity changes", async () => {
    const latePage = deferred<{
      items: Array<{ id: string; title: string; sourceType: "paper"; verified: boolean }>;
      nextCursor: null;
      total: number;
    }>();
    listMissionEvidenceMock.mockReturnValueOnce(latePage.promise);
    const first = makeView("mission-1");
    first.evidenceItems = [{ id: "ev-a", title: "任务 A 首批证据", sourceType: "paper", verified: true }];
    first.evidenceCount = 2;
    first.evidenceNextCursor = 12;
    const { rerender } = render(<MissionConsole view={first} onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: /来源与结果/ }));
    fireEvent.click(screen.getByRole("button", { name: /加载更多/ }));

    const second = makeView("mission-2");
    second.evidenceItems = [{ id: "ev-b", title: "任务 B 证据", sourceType: "paper", verified: true }];
    second.evidenceCount = 1;
    useMissionUiStore.getState().focusMission("mission-2", "evidence");
    rerender(<MissionConsole view={second} onClose={() => undefined} />);

    await act(async () => {
      latePage.resolve({
        items: [{ id: "ev-a-late", title: "任务 A 晚到证据", sourceType: "paper", verified: true }],
        nextCursor: null,
        total: 2,
      });
      await latePage.promise;
    });
    expect(screen.getByText("任务 B 证据")).toBeInTheDocument();
    expect(screen.queryByText("任务 A 晚到证据")).not.toBeInTheDocument();
  });

  it("drops a late artifact page after Mission identity changes", async () => {
    const latePage = deferred<{
      items: Array<{ id: string; title: string; kind: string; previewAvailable: boolean; committed: boolean }>;
      nextCursor: null;
      total: number;
    }>();
    listMissionArtifactsMock.mockReturnValueOnce(latePage.promise);
    const first = makeView("mission-1");
    first.artifactItems = [{ id: "artifact-a", title: "任务 A 初稿", kind: "document", previewAvailable: true, committed: false }];
    first.artifactCount = 2;
    first.artifactNextCursor = 14;
    const { rerender } = render(<MissionConsole view={first} onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: /成果/ }));
    fireEvent.click(screen.getByRole("button", { name: /加载更多成果/ }));

    const second = makeView("mission-2");
    second.artifactItems = [{ id: "artifact-b", title: "任务 B 成果", kind: "document", previewAvailable: true, committed: false }];
    second.artifactCount = 1;
    useMissionUiStore.getState().focusMission("mission-2", "artifacts");
    rerender(<MissionConsole view={second} onClose={() => undefined} />);

    await act(async () => {
      latePage.resolve({
        items: [{ id: "artifact-a-late", title: "任务 A 晚到成果", kind: "document", previewAvailable: true, committed: false }],
        nextCursor: null,
        total: 2,
      });
      await latePage.promise;
    });
    expect(screen.getByText("任务 B 成果")).toBeInTheDocument();
    expect(screen.queryByText("任务 A 晚到成果")).not.toBeInTheDocument();
  });

  it("loads semantic trace only after the user asks", async () => {
    render(<MissionConsole view={makeView()} onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: "轨迹" }));
    expect(screen.getByTestId("mission-trace-idle")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "加载任务轨迹" }));
    await waitFor(() => expect(screen.getByText("找到一篇可核验论文")).toBeInTheDocument());
    expect(screen.queryByText(/tool_json|stdout|api_key/i)).not.toBeInTheDocument();
  });

  it("drops a late trace page and starts the next Mission trace cleanly", async () => {
    const latePage = deferred<{
      items: Array<{ id: string; missionId: string; seq: number; itemType: string; phase: string; summary: string; createdAt: string }>;
      nextCursor: null;
    }>();
    listMissionItemsMock.mockReturnValueOnce(latePage.promise);
    const { rerender } = render(<MissionConsole view={makeView("mission-1")} onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: "轨迹" }));
    fireEvent.click(screen.getByRole("button", { name: "加载任务轨迹" }));

    useMissionUiStore.getState().focusMission("mission-2", "trace");
    rerender(<MissionConsole view={makeView("mission-2")} onClose={() => undefined} />);
    await act(async () => {
      latePage.resolve({
        items: [{ id: "trace-a", missionId: "mission-1", seq: 1, itemType: "stage", phase: "completed", summary: "任务 A 晚到轨迹", createdAt: "2026-07-11T00:00:00Z" }],
        nextCursor: null,
      });
      await latePage.promise;
    });

    expect(screen.queryByText("任务 A 晚到轨迹")).not.toBeInTheDocument();
    expect(screen.getByTestId("mission-trace-idle")).toBeInTheDocument();
    listMissionItemsMock.mockResolvedValueOnce({
      items: [{ id: "trace-b", missionId: "mission-2", seq: 1, itemType: "stage", phase: "completed", summary: "任务 B 轨迹", createdAt: "2026-07-11T00:01:00Z" }],
      nextCursor: null,
    });
    fireEvent.click(screen.getByRole("button", { name: "加载任务轨迹" }));
    expect(await screen.findByText("任务 B 轨迹")).toBeInTheDocument();
    expect(listMissionItemsMock).toHaveBeenLastCalledWith({
      missionId: "mission-2",
      cursor: null,
      limit: 30,
    });
  });

  it("catches an initial trace failure and retries it", async () => {
    listMissionItemsMock
      .mockRejectedValueOnce(new Error("provider raw trace error"))
      .mockResolvedValueOnce({ items: [{ id: "i-2", missionId: "mission-1", seq: 2, itemType: "stage", phase: "completed", summary: "完成研究问题收敛", createdAt: "2026-07-11T00:02:00Z" }], nextCursor: null });
    render(<MissionConsole view={makeView()} onClose={() => undefined} />);
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
      impact: "收到材料前，相关查证与后续写作会暂停。",
      requiredInputs: [{ id: "pdf", label: "题目 PDF", inputType: "file", required: true }],
      actions: [
        { id: "reply", label: "回到对话回复", actionType: "reply_in_chat", primary: true },
        { id: "upload", label: "添加材料", actionType: "upload_file", primary: false },
      ],
    };
    useMissionUiStore.getState().closePanel();
    useMissionUiStore.getState().peekMission(view.missionId);

    render(<MissionConsole view={view} onClose={() => undefined} />);

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
      impact: "收到材料前，相关查证与后续写作会暂停。",
      requiredInputs: [{ id: "pdf", label: "题目 PDF", inputType: "file", required: true }],
      actions: [{ id: "reply", label: "回到对话回复", actionType: "reply_in_chat", primary: true }],
    };
    const onChatAction = vi.fn();

    render(
      <MissionConsole
        view={view}
        onClose={() => undefined}
        onMissionTarget={async () => true}
        onChatAction={onChatAction}
      />,
    );
    expect(screen.getByTestId("mission-attention-request")).toHaveTextContent("题目 PDF");
    expect(screen.getByTestId("mission-attention-request")).toHaveTextContent("相关查证与后续写作会暂停");
    fireEvent.click(screen.getByRole("button", { name: "回到对话回复" }));

    expect(onChatAction).toHaveBeenCalledWith("focus");
  });

  it("resolves a permission request through explicit server-owned decisions", async () => {
    const view = makeView();
    view.executionStatus = "waiting";
    view.attentionRequest = {
      requestId: "permission-1",
      reason: "permission",
      title: "需要确认外部访问",
      summary: "需要访问 Python 包索引安装依赖。",
      impact: "确认后，问津会从当前步骤继续。",
      requiredInputs: [{ id: "decision", label: "确认是否允许", inputType: "confirmation", required: true }],
      actions: [
        { id: "allow-once", label: "仅本次允许", actionType: "permission_allow_once", primary: true },
        { id: "allow-mission", label: "本任务内允许", actionType: "permission_allow_mission", primary: false },
        { id: "reject", label: "不允许", actionType: "permission_reject", primary: false },
      ],
    };
    const onMissionTarget = vi.fn(async () => true);

    render(
      <MissionConsole
        view={view}
        onClose={() => undefined}
        onMissionTarget={onMissionTarget}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "仅本次允许" }));

    await waitFor(() => {
      expect(resolveMissionPermissionMock).toHaveBeenCalledWith({
        missionId: "mission-1",
        requestId: "permission-1",
        decision: "allow_once",
      });
    });
    expect(onMissionTarget).toHaveBeenCalledWith("mission-1");
  });
});
