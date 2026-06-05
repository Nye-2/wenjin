import { describe, expect, it } from "vitest";

import { choosePrismAssistRoute } from "@/components/latex/latex-editor/prismAssistRouting";

describe("choosePrismAssistRoute", () => {
  it("uses quick rewrite for local small selections", () => {
    expect(
      choosePrismAssistRoute({
        selectedTextLength: 320,
        comment: "更学术一点",
        scope: "selection",
      }),
    ).toBe("quick");
  });

  it("uses deep assist for large selections", () => {
    expect(
      choosePrismAssistRoute({
        selectedTextLength: 3000,
        comment: "整体优化",
        scope: "section",
      }),
    ).toBe("deep");
  });

  it("uses deep assist for manuscript-level intent", () => {
    expect(
      choosePrismAssistRoute({
        selectedTextLength: 500,
        comment: "检查贡献和审稿风险",
        scope: "selection",
      }),
    ).toBe("deep");
  });

  it("respects explicit route overrides", () => {
    expect(
      choosePrismAssistRoute({
        selectedTextLength: 4000,
        comment: "压缩一下",
        scope: "section",
        force: "quick",
      }),
    ).toBe("quick");
  });
});
