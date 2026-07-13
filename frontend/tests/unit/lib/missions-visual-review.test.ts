import { beforeEach, describe, expect, it, vi } from "vitest";

const { authorizedFetchMock } = vi.hoisted(() => ({
  authorizedFetchMock: vi.fn(),
}));

vi.mock("@/lib/api/client", () => ({
  authorizedFetch: authorizedFetchMock,
  readErrorMessage: vi.fn().mockResolvedValue("视觉预览加载失败"),
}));

import { getMissionReviewPreview, projectMissionVisualReviewMetadata } from "@/lib/api/missions";

describe("mission academic visual reviews", () => {
  beforeEach(() => {
    authorizedFetchMock.mockReset();
  });

  it("projects bounded visual metadata from preview_json", () => {
    expect(projectMissionVisualReviewMetadata({
      artifact_kind: "figure",
      mime_type: "image/webp",
      figure_type: "graphical_abstract",
      strategy: "hybrid",
      evidence_level: "explanatory",
      caption: "联邦参数高效微调机制图",
      alt_text: "服务器聚合三个客户端的 LoRA 更新",
      renderer_id: "gpt-image-2+overlay-v1",
      reproducibility: { status: "not_applicable" },
      source_refs: ["paper:1", "paper:1"],
      dataset_refs: ["dataset:2"],
      provider_model: "gpt-image-2",
    })).toEqual({
      artifactKind: "figure",
      mimeType: "image/webp",
      figureType: "graphical_abstract",
      strategy: "hybrid",
      evidenceLevel: "explanatory",
      caption: "联邦参数高效微调机制图",
      altText: "服务器聚合三个客户端的 LoRA 更新",
      rendererId: "gpt-image-2+overlay-v1",
      reproducibilityStatus: "not_applicable",
      sourceLabels: ["paper:1", "dataset:2", "gpt-image-2"],
    });
  });

  it("does not classify ordinary document previews as visual candidates", () => {
    expect(projectMissionVisualReviewMetadata({
      artifact_kind: "document",
      mime_type: "text/markdown",
      body: "# Draft",
    })).toBeNull();
    expect(projectMissionVisualReviewMetadata({
      artifact_kind: "table",
      mime_type: "text/markdown",
      body: "| 指标 | 数值 |",
    })).toBeNull();
  });

  it("loads preview bytes through the canonical authenticated endpoint", async () => {
    const blob = new Blob(["png"], { type: "image/png" });
    authorizedFetchMock.mockResolvedValueOnce(new Response(blob, {
      status: 200,
      headers: { "Content-Type": "image/png; charset=binary" },
    }));

    await expect(getMissionReviewPreview({ missionId: "mission/1", reviewItemId: "review 2" })).resolves.toEqual({
      blob: expect.any(Blob),
      mimeType: "image/png",
    });
    expect(authorizedFetchMock).toHaveBeenCalledWith(
      "/api/missions/mission%2F1/review-items/review%202/preview",
      { headers: { Accept: "image/png, image/webp, image/svg+xml, application/pdf" } },
    );
  });
});
