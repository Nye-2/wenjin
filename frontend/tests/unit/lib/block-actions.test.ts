import { describe, expect, it } from "vitest";

import { resolveExecutionNextActionPresentation } from "@/lib/block-actions";

describe("block action routing", () => {
  it("routes Prism actions only through the workspace-owned Prism surface", () => {
    const presentation = resolveExecutionNextActionPresentation({
      workspaceId: "ws-1",
      actionRecord: {
        action: "preview_prism_changes",
        label: "预览待复核修改",
        url: "/latex/legacy-project",
      },
    });

    expect(presentation?.href).toBe(
      "/workspaces/ws-1/prism?focus=file_changes",
    );
  });

  it("does not fall back to legacy Prism URLs without workspace context", () => {
    const presentation = resolveExecutionNextActionPresentation({
      actionRecord: {
        action: "open_prism",
        label: "在 WenjinPrism 中继续编辑",
        url: "/latex/legacy-project",
      },
    });

    expect(presentation?.href).toBeNull();
  });

  it("carries focused Prism review item routing when present", () => {
    const presentation = resolveExecutionNextActionPresentation({
      workspaceId: "ws-1",
      actionRecord: {
        action: "preview_prism_changes",
        label: "预览待复核修改",
        review_item_id: "review-1",
        logical_key: "section:introduction",
      },
    });

    expect(presentation?.href).toBe(
      "/workspaces/ws-1/prism?focus=file_changes&review_item_id=review-1&logical_key=section%3Aintroduction",
    );
  });
});
