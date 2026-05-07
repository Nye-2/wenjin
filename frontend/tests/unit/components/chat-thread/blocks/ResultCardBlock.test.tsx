import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ResultCardBlock } from "@/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/ResultCardBlock";
import type { ResultCardBlock as ResultBlockType } from "@/lib/api/blocks";

const baseBlock: ResultBlockType = {
  kind: "result_card",
  run_id: "r1",
  title: "📑 论文分析 · 完成",
  tldr: "3 个角度可切，最有价值是通信效率 ↔ 隐私强度",
  findings: [
    { id: "1", text: "异构客户端缺口" },
    { id: "2", text: "联邦预训练 vs 联邦微调供需错位" },
    { id: "3", text: "trade-off 量化空白" },
  ],
  recommend: { label: "推荐切入", body: "通信效率 × 隐私强度 × 异构客户端" },
  links: [{ icon: "📄", label: "详细报告", href: "#" }],
  feedback: {
    question: "这个结论你怎么看？",
    pills: [
      { kind: "primary", label: "进入选题", intent: "next" },
      { kind: "normal", label: "深入第 ① 点", intent: "deep-1" },
      { kind: "warn", label: "换方向", intent: "redirect" },
    ],
    allow_free_input: true,
  },
  stats: { duration_ms: 102_000, subagents: 13, tokens: 8400 },
};

describe("ResultCardBlock", () => {
  it("renders title, TL;DR, and stats", () => {
    render(<ResultCardBlock block={baseBlock} />);
    expect(screen.getByText(/论文分析 · 完成/)).toBeInTheDocument();
    expect(screen.getByText(/3 个角度可切/)).toBeInTheDocument();
    expect(screen.getByText(/13 subagents/)).toBeInTheDocument();
    expect(screen.getByText(/8\.4k tokens|8400 tokens/)).toBeInTheDocument();
  });

  it("renders findings with circled-numeral labels (① ② ③)", () => {
    render(<ResultCardBlock block={baseBlock} />);
    // ① also appears inside the "深入第 ① 点" pill, so >=1 occurrence is enough.
    expect(screen.getAllByText(/①/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/②/)).toBeInTheDocument();
    expect(screen.getByText(/③/)).toBeInTheDocument();
    expect(screen.getByText(/异构客户端缺口/)).toBeInTheDocument();
  });

  it("renders recommend block when present", () => {
    render(<ResultCardBlock block={baseBlock} />);
    expect(screen.getByText(/推荐切入/)).toBeInTheDocument();
    expect(screen.getByText(/通信效率 × 隐私强度/)).toBeInTheDocument();
  });

  it("renders link pills", () => {
    render(<ResultCardBlock block={baseBlock} />);
    expect(screen.getByText(/详细报告/)).toBeInTheDocument();
  });

  it("renders feedback question and pills", () => {
    render(<ResultCardBlock block={baseBlock} />);
    expect(screen.getByText(/这个结论你怎么看？/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "进入选题" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "深入第 ① 点" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "换方向" })).toBeInTheDocument();
  });

  it("primary feedback pill has data-pill-kind=primary", () => {
    render(<ResultCardBlock block={baseBlock} />);
    const primary = screen.getByRole("button", { name: "进入选题" });
    expect(primary.getAttribute("data-pill-kind")).toBe("primary");
  });

  it("warn feedback pill has data-pill-kind=warn", () => {
    render(<ResultCardBlock block={baseBlock} />);
    const warn = screen.getByRole("button", { name: "换方向" });
    expect(warn.getAttribute("data-pill-kind")).toBe("warn");
  });

  it("invokes onFeedback with intent + label", () => {
    const onFeedback = vi.fn();
    render(<ResultCardBlock block={baseBlock} onFeedback={onFeedback} />);
    fireEvent.click(screen.getByRole("button", { name: "深入第 ① 点" }));
    expect(onFeedback).toHaveBeenCalledWith("deep-1", "深入第 ① 点");
  });

  it("omits recommend block when null", () => {
    render(
      <ResultCardBlock block={{ ...baseBlock, recommend: null }} />,
    );
    expect(screen.queryByText(/推荐切入/)).not.toBeInTheDocument();
  });
});
