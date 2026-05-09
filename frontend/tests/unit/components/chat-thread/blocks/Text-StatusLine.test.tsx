import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { TextBlock } from "@/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/TextBlock";
import { StatusLineBlock } from "@/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/StatusLineBlock";

describe("TextBlock", () => {
  it("renders content", () => {
    render(<TextBlock block={{ kind: "text", content: "好，先扫文献" }} />);
    expect(screen.getByText("好，先扫文献")).toBeInTheDocument();
  });

  it("preserves whitespace and newlines via markdown paragraph rendering", () => {
    render(
      <TextBlock
        block={{ kind: "text", content: "line one\n\nline three" }}
      />,
    );
    // MarkdownRenderer parses double newlines into separate <p> tags
    expect(screen.getByText(/line one/)).toBeInTheDocument();
    expect(screen.getByText(/line three/)).toBeInTheDocument();
  });
});

describe("StatusLineBlock", () => {
  it("renders the label with arrow indicator", () => {
    render(
      <StatusLineBlock
        block={{
          kind: "status_line",
          label: "phase 1 完成",
          run_id: "r1",
          tone: "info",
        }}
      />,
    );
    expect(screen.getByText(/phase 1 完成/)).toBeInTheDocument();
  });

  it("calls onJumpToPhase when clicked with phase_index set", () => {
    const onJump = vi.fn();
    render(
      <StatusLineBlock
        block={{
          kind: "status_line",
          label: "phase 2 启动",
          run_id: "r1",
          phase_index: 2,
          tone: "info",
        }}
        onJumpToPhase={onJump}
      />,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(onJump).toHaveBeenCalledWith("r1", 2);
  });

  it("does not call onJumpToPhase when phase_index is missing", () => {
    const onJump = vi.fn();
    render(
      <StatusLineBlock
        block={{
          kind: "status_line",
          label: "汇总中",
          run_id: "r1",
          tone: "info",
        }}
        onJumpToPhase={onJump}
      />,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(onJump).not.toHaveBeenCalled();
  });

  it("warn tone applies an amber-ish color", () => {
    render(
      <StatusLineBlock
        block={{
          kind: "status_line",
          label: "1 篇文献无法解析",
          run_id: "r1",
          tone: "warn",
        }}
      />,
    );
    const btn = screen.getByRole("button");
    expect(btn.getAttribute("data-tone")).toBe("warn");
  });

  it("error tone applies a red-ish color", () => {
    render(
      <StatusLineBlock
        block={{
          kind: "status_line",
          label: "phase 失败",
          run_id: "r1",
          tone: "error",
        }}
      />,
    );
    const btn = screen.getByRole("button");
    expect(btn.getAttribute("data-tone")).toBe("error");
  });
});
