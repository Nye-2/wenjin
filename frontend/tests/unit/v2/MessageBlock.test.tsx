import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MessageBlock } from "@/app/(workbench)/workspaces/[id]/components/MessageBlock";

describe("MessageBlock launch receipt", () => {
  it("shows the launch write mode snapshot when present", () => {
    render(
      <MessageBlock
        workspaceId="ws-1"
        block={
          {
            kind: "tool_result",
            tool: "launch_feature",
            status: "launched",
            execution_id: "exec-1",
            feature_id: "thesis_research_pack",
            capability_name: "论文研究包",
            write_mode: "strict_review",
          } as never
        }
      />,
    );

    expect(screen.getByTestId("run-receipt")).toBeInTheDocument();
    expect(screen.getByText("写入模式：")).toBeInTheDocument();
    expect(screen.getByText("严格审阅")).toBeInTheDocument();
    expect(screen.getByText(/所有工作区写入都先进入复核与保存/)).toBeInTheDocument();
  });
});
