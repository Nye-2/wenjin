import { describe, expect, it } from "vitest";

import {
  buildWorkspaceResultPreviewsFromOutputs,
  buildWorkspaceResultPreviewsFromReviewPacket,
  buildWorkspaceResultPreviewsFromReviewItems,
} from "@/lib/workspace-result-preview";

describe("buildWorkspaceResultPreviewsFromOutputs", () => {
  it("projects staged figure outputs as image previews without technical figure metadata", () => {
    const previews = buildWorkspaceResultPreviewsFromOutputs([
      {
        id: "fig-1",
        kind: "figure",
        preview: "Result trend",
        default_checked: true,
        data: {
          title: "Accuracy trend",
          primary_path: "/workspace/outputs/figures/run-1/figure.png",
          caption: "Validation accuracy improved across the final three epochs.",
          strategy: "matplotlib_line_chart",
          figure_type: "line",
          provenance: "sandbox",
          stdout: "debug logs should not be shown",
        },
      },
    ]);

    expect(previews).toHaveLength(1);
    expect(previews[0]).toMatchObject({
      id: "fig-1",
      kind: "figure",
      previewMode: "image",
      previewPath: "/workspace/outputs/figures/run-1/figure.png",
      title: "Accuracy trend",
      subtitle: "Validation accuracy improved across the final three epochs.",
      badge: "图表",
    });
    expect(previews[0]?.metadataLines).toEqual([]);
    expect(previews[0]?.metadataLines.join(" ")).not.toContain("matplotlib");
    expect(previews[0]?.metadataLines.join(" ")).not.toContain("line");
    expect(previews[0]?.metadataLines.join(" ")).not.toContain("debug logs");
  });

  it("projects figure-like document outputs as figure image previews", () => {
    const previews = buildWorkspaceResultPreviewsFromOutputs([
      {
        id: "doc-figure-1",
        kind: "document",
        preview: "/workspace/outputs/figures/run-2/figure.png",
        default_checked: true,
        data: {
          doc_kind: "figure",
          name: "figure.png",
          mime_type: "image/png",
          preview_path: "/workspace/outputs/figures/run-2/preview.png",
          manifest: {
            caption: "Ablation comparison for accepted variants.",
          },
          provider: "matplotlib",
        },
      },
    ]);

    expect(previews).toHaveLength(1);
    expect(previews[0]).toMatchObject({
      kind: "figure",
      previewMode: "image",
      previewPath: "/workspace/outputs/figures/run-2/preview.png",
      title: "/workspace/outputs/figures/run-2/figure.png",
      subtitle: "Ablation comparison for accepted variants.",
    });
    expect(previews[0]?.metadataLines).toEqual([]);
  });

  it("projects sandbox figure review items as image previews without making them output-committable", () => {
    const previews = buildWorkspaceResultPreviewsFromReviewItems([
      {
        id: "review-figure-1",
        kind: "sandbox_artifact",
        status: "pending",
        title: "Accept sandbox artifact: figure",
        summary: "/workspace/outputs/figures/fed_curve/figure.png",
        target: {
          kind: "sandbox_artifact",
          path: "/workspace/outputs/figures/fed_curve/figure.png",
          artifact_kind: "figure",
          sandbox_artifact_id: "artifact-1",
        },
        preview: {
          mode: "artifact",
          path: "/workspace/outputs/figures/fed_curve/figure.png",
          mime_type: "image/png",
          content_hash: "sha256:figure",
        },
        reproducibility: {
          source_script: "/workspace/scripts/fed_curve.py",
          dataset_paths: ["/workspace/datasets/results.csv"],
          content_hash: "sha256:figure",
        },
      },
    ]);

    expect(previews).toHaveLength(1);
    expect(previews[0]).toMatchObject({
      id: "review:review-figure-1",
      kind: "figure",
      previewMode: "image",
      previewPath: "/workspace/outputs/figures/fed_curve/figure.png",
      title: "Accept sandbox artifact: figure",
      defaultChecked: false,
      canCommit: false,
    });
    expect(previews[0]?.metadataLines.join(" ")).toContain("image/png");
    expect(previews[0]?.metadataLines.join(" ")).toContain("fed_curve.py");
  });

  it("projects academic review packet items as read-only previews", () => {
    const previews = buildWorkspaceResultPreviewsFromReviewPacket({
      packet_id: "packet-1",
      completion_status: "partial",
      items: [
        {
          item_id: "writer-summary",
          kind: "document",
          title: "写作专家摘要",
          summary: "完成初稿结构，但仍有两个论断缺证据。",
          preview: { format: "markdown", excerpt: "## 摘要\n完成初稿结构。" },
          source: { expert_id: "manuscript_writer.v1" },
          claim_refs: ["claim-1"],
          evidence_refs: ["library_reference:source-1"],
          quality_surfaces: ["claim_evidence_alignment"],
          risk: { level: "medium", reasons: ["missing evidence"] },
          default_checked: false,
          can_commit: true,
        },
        {
          item_id: "claim-warning",
          kind: "warning",
          title: "弱证据或未支持论断",
          summary: "这一段结论缺少来源支撑。",
          preview: { format: "text", excerpt: "这一段结论缺少来源支撑。" },
          risk: { level: "high", reasons: ["unsupported"] },
          can_commit: false,
        },
      ],
    });

    expect(previews).toHaveLength(2);
    expect(previews[0]).toMatchObject({
      id: "packet:writer-summary",
      source: "review_packet",
      kind: "document",
      badge: "需确认",
      previewMode: "markdown",
      title: "写作专家摘要",
      canCommit: false,
    });
    expect(previews[0]?.metadataLines.join(" ")).toContain("状态 需确认");
    expect(previews[0]?.metadataLines.join(" ")).toContain("证据 1");
    expect(previews[1]).toMatchObject({
      kind: "warning",
      badge: "阻断",
      previewMode: "plain_text",
      canCommit: false,
    });
    expect(previews[1]?.metadataLines.join(" ")).toContain("状态 阻断");
  });
});
