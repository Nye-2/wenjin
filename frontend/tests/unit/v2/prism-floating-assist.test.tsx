import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PrismFloatingAssist } from "@/components/latex/latex-editor/PrismFloatingAssist";

function renderAssist(
  overrides: Partial<React.ComponentProps<typeof PrismFloatingAssist>> = {},
) {
  const props: React.ComponentProps<typeof PrismFloatingAssist> = {
    isPanelOpen: false,
    selectedCharacterCount: 0,
    pendingRewriteCount: 0,
    runningJobCount: 0,
    hasError: false,
    onOpen: vi.fn(),
    onAnnotate: vi.fn(),
    onQuickRewrite: vi.fn(),
    onDeepAssist: vi.fn(),
    ...overrides,
  };
  render(<PrismFloatingAssist {...props} />);
  return props;
}

describe("PrismFloatingAssist", () => {
  it("renders a restrained AI rewrite entry by default", () => {
    const props = renderAssist();

    fireEvent.click(screen.getByRole("button", { name: "改稿助手" }));

    expect(screen.getByRole("button", { name: "改稿助手" })).toBeInTheDocument();
    expect(props.onOpen).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "批注" })).not.toBeInTheDocument();
  });

  it("shows selection actions when text is selected", () => {
    const props = renderAssist({ selectedCharacterCount: 42 });

    expect(screen.getByRole("button", { name: "改稿助手，已选 42 字" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "批注" }));
    fireEvent.click(screen.getByRole("button", { name: "改这段" }));
    fireEvent.click(screen.getByRole("button", { name: "修改全文" }));

    expect(props.onAnnotate).toHaveBeenCalled();
    expect(props.onQuickRewrite).toHaveBeenCalled();
    expect(props.onDeepAssist).toHaveBeenCalled();
  });

  it("hides the floating entry while the assist panel is open", () => {
    renderAssist({ isPanelOpen: true });

    expect(screen.queryByRole("button", { name: "改稿助手" })).not.toBeInTheDocument();
  });

  it("surfaces pending rewrite and async job states on the main pill", () => {
    const { rerender } = render(
      <PrismFloatingAssist
        selectedCharacterCount={0}
        isPanelOpen={false}
        pendingRewriteCount={1}
        runningJobCount={0}
        hasError={false}
        onOpen={vi.fn()}
        onAnnotate={vi.fn()}
        onQuickRewrite={vi.fn()}
        onDeepAssist={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "改稿助手，待应用修改" })).toBeInTheDocument();

    rerender(
      <PrismFloatingAssist
        selectedCharacterCount={0}
        isPanelOpen={false}
        pendingRewriteCount={0}
        runningJobCount={1}
        hasError={false}
        onOpen={vi.fn()}
        onAnnotate={vi.fn()}
        onQuickRewrite={vi.fn()}
        onDeepAssist={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "改稿助手，团队处理中" })).toBeInTheDocument();
  });
});
