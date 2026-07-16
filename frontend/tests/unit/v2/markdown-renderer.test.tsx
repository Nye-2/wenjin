import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  MarkdownRenderer,
  normalizeLatexDelimiters,
} from "@/components/ui/markdown-renderer";

describe("MarkdownRenderer", () => {
  it("renders dollar and LaTeX bracket delimiters through KaTeX", () => {
    const { container } = render(
      <MarkdownRenderer
        content={String.raw`Inline \(x_i^2\) and block:

\[
\sum_i x_i = 10
\]`}
      />,
    );

    expect(container.querySelectorAll(".katex")).toHaveLength(2);
    expect(container.querySelector(".katex-display")).not.toBeNull();
    expect(container.textContent).toContain("x");
    expect(container.textContent).toContain("10");
  });

  it("does not normalize delimiters inside inline or fenced code", () => {
    const content = [
      String.raw`Use \(x\), keep \\(literal\\) and:`,
      "",
      "`\\(inline\\)`",
      "",
      "```tex",
      String.raw`\[block\]`,
      "```",
    ].join("\n");

    const normalized = normalizeLatexDelimiters(content);

    expect(normalized).toContain("$x$");
    expect(normalized).toContain("`\\(inline\\)`");
    expect(normalized).toContain(String.raw`\[block\]`);
  });

  it("keeps ordinary markdown behavior", () => {
    render(<MarkdownRenderer content="**结论**：约束满足。" />);

    expect(screen.getByText("结论").tagName).toBe("STRONG");
  });
});
