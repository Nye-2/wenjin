import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MissionCard } from "@/app/(workbench)/workspaces/[id]/components/MissionCardBlock";
import type { MissionCardBlock } from "@/lib/api/blocks";
import { useMissionUiStore } from "@/stores/mission-ui-store";

const { commitMissionReviewsMock, decideMissionReviewsMock, getMissionViewMock } = vi.hoisted(() => ({
  commitMissionReviewsMock: vi.fn(),
  decideMissionReviewsMock: vi.fn(),
  getMissionViewMock: vi.fn(),
}));

vi.mock("@/lib/api/missions", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/missions")>("@/lib/api/missions");
  return {
    ...actual,
    commitMissionReviews: commitMissionReviewsMock,
    decideMissionReviews: decideMissionReviewsMock,
    getMissionView: getMissionViewMock,
  };
});

function missionViewWithReview(status: string) {
  return {
    reviewItems: [
      { id: "r-1", status },
    ],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  getMissionViewMock.mockResolvedValue(missionViewWithReview("pending"));
  decideMissionReviewsMock.mockResolvedValue({ targetMissionId: "m-1", issueCodes: [], appliedReviewItemIds: ["r-1"] });
  commitMissionReviewsMock.mockResolvedValue({ targetMissionId: "m-1", issueCodes: [], appliedReviewItemIds: ["r-1"] });
});

describe("MissionCard", () => {
  it("renders a stage-passed milestone with the verified material count", () => {
    const block: MissionCardBlock = {
      kind: "mission_card",
      card: "stage_passed",
      mission_id: "m-1",
      stage_title: "文献调研",
      evidence_count: 6,
    };
    render(<MissionCard block={block} />);
    expect(screen.getByTestId("mission-card-stage-passed")).toHaveTextContent("「文献调研」已通过验收");
    expect(screen.getByText("已查证 6 份材料。")).toBeInTheDocument();
  });

  it("renders a material request that raises the composer and attachment picker", () => {
    const onMaterialAction = vi.fn();
    render(
      <MissionCard
        block={{ kind: "mission_card", card: "material_request", mission_id: "m-1", title: "需要你补充研究材料", summary: "缺少数据附件" }}
        onMaterialAction={onMaterialAction}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "去补充材料" }));
    expect(onMaterialAction).toHaveBeenCalledTimes(1);
  });

  it("decides and commits a review batch in place", async () => {
    render(
      <MissionCard
        block={{
          kind: "mission_card",
          card: "review_request",
          mission_id: "m-1",
          review_item_ids: ["r-1"],
          count: 1,
          summary: "第一问成果已就绪",
        }}
      />,
    );
    await waitFor(() => expect(getMissionViewMock).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "确认并保存" }));
    await waitFor(() => expect(screen.getByText("已确认并保存")).toBeInTheDocument());
    expect(decideMissionReviewsMock).toHaveBeenCalledWith({
      missionId: "m-1",
      decisions: [{ reviewItemId: "r-1", decision: "accepted" }],
    });
    expect(commitMissionReviewsMock).toHaveBeenCalledWith({ missionId: "m-1", reviewItemIds: ["r-1"] });
  });

  it("does not offer actions for an already handled review batch", async () => {
    getMissionViewMock.mockResolvedValueOnce(missionViewWithReview("committed"));
    render(
      <MissionCard
        block={{
          kind: "mission_card",
          card: "review_request",
          mission_id: "m-1",
          review_item_ids: ["r-1"],
          count: 1,
        }}
      />,
    );
    await waitFor(() => expect(screen.getByText("已确认并保存")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "确认并保存" })).not.toBeInTheDocument();
  });

  it("renders terminal states", () => {
    render(<MissionCard block={{ kind: "mission_card", card: "terminal", mission_id: "m-1", status: "completed", title: "共享单车" }} />);
    expect(screen.getByText("研究已完成：共享单车")).toBeInTheDocument();
  });

  it("offers a reason action for a failed terminal card", () => {
    render(<MissionCard block={{ kind: "mission_card", card: "terminal", mission_id: "m-1", status: "failed", title: "测试页摘要" }} />);
    expect(screen.getByText("任务未能完成：测试页摘要")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "查看原因" }));
    expect(useMissionUiStore.getState().panelMode).toBe("expanded");
  });
});
