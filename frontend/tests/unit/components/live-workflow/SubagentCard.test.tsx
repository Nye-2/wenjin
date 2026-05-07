import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { SubagentCard } from "@/app/(workbench)/workspaces/[id]/components/live-workflow/SubagentCard";
import type { SubagentSnap } from "@/stores/workflow-store-support";

const base: SubagentSnap = {
  task_id: "t1abcdef",
  status: "running",
  subagent_type: "reader",
  output_preview: "正在读 §3 方法 · LoRA 适配器分发",
  token_usage: { total: 1200 },
};

describe("SubagentCard", () => {
  it("renders subagent_type label and live preview", () => {
    render(<SubagentCard subagent={base} />);
    expect(screen.getByText(/reader/i)).toBeInTheDocument();
    expect(
      screen.getByText(/正在读 §3 方法 · LoRA 适配器分发/),
    ).toBeInTheDocument();
  });

  it("formats tokens (>1000 → x.xk) and duration in seconds", () => {
    render(
      <SubagentCard
        subagent={{ ...base, duration_ms: 14_321, token_usage: { total: 8400 } }}
      />,
    );
    expect(screen.getByText(/8\.4k tokens/i)).toBeInTheDocument();
    expect(screen.getByText(/14s/i)).toBeInTheDocument();
  });

  it("running status shows the running pill", () => {
    render(<SubagentCard subagent={{ ...base, status: "running" }} />);
    expect(screen.getByText(/运行中/)).toBeInTheDocument();
  });

  it("completed status shows the completed pill", () => {
    render(<SubagentCard subagent={{ ...base, status: "completed" }} />);
    expect(screen.getByText(/完成/)).toBeInTheDocument();
  });

  it("waiting status shows pointer back to chat", () => {
    render(<SubagentCard subagent={{ ...base, status: "waiting" }} />);
    expect(screen.getByText(/需要你回答/)).toBeInTheDocument();
    expect(screen.getByText(/在 chat 里问了你/)).toBeInTheDocument();
  });

  it("failed status shows error text", () => {
    render(
      <SubagentCard
        subagent={{ ...base, status: "failed", error: "PDF 解析超时" }}
      />,
    );
    expect(screen.getByText(/失败/)).toBeInTheDocument();
    expect(screen.getByText(/PDF 解析超时/)).toBeInTheDocument();
  });

  it("renders without preview when none is provided", () => {
    render(
      <SubagentCard
        subagent={{ ...base, output_preview: null, token_usage: null }}
      />,
    );
    expect(screen.queryByText(/正在读/)).not.toBeInTheDocument();
  });

  it("exposes a stable testid keyed on task_id for grid identification", () => {
    render(<SubagentCard subagent={base} />);
    expect(screen.getByTestId("subagent-card-t1abcdef")).toBeInTheDocument();
  });
});
