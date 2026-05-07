import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { QuestionCardBlock } from "@/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/QuestionCardBlock";
import type { QuestionCardBlock as QuestionBlockType } from "@/lib/api/blocks";

const baseBlock: QuestionBlockType = {
  kind: "question_card",
  label: "需要你拍一下",
  question: "更想看哪条线？",
  pills: [
    { label: "单客户端", intent: "single" },
    { label: "多客户端", intent: "multi" },
  ],
};

describe("QuestionCardBlock", () => {
  it("renders the label and question text", () => {
    render(<QuestionCardBlock block={baseBlock} />);
    expect(screen.getByText("需要你拍一下")).toBeInTheDocument();
    expect(screen.getByText("更想看哪条线？")).toBeInTheDocument();
  });

  it("renders one button per pill", () => {
    render(<QuestionCardBlock block={baseBlock} />);
    expect(screen.getAllByRole("button")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "单客户端" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "多客户端" })).toBeInTheDocument();
  });

  it("invokes onPillClick with the pill's intent and label", () => {
    const onPill = vi.fn();
    render(<QuestionCardBlock block={baseBlock} onPillClick={onPill} />);
    fireEvent.click(screen.getByRole("button", { name: "单客户端" }));
    expect(onPill).toHaveBeenCalledWith("single", "单客户端");
  });

  it("shows the free-input hint", () => {
    render(<QuestionCardBlock block={baseBlock} />);
    expect(
      screen.getByText(/或者直接打字告诉我你的想法/),
    ).toBeInTheDocument();
  });

  it("renders without pills when empty", () => {
    render(<QuestionCardBlock block={{ ...baseBlock, pills: [] }} />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});
