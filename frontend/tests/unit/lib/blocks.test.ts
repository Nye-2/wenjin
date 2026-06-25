import { describe, expect, it } from "vitest";
import {
  AgentBlock, AgentMessage, isQuestionCard, isResultCard,
  isStatusLine, isText, normalizeChatBlock,
} from "@/lib/api/blocks";

describe("AgentBlock type guards", () => {
  it("narrows by kind", () => {
    const b: AgentBlock = { kind: "text", content: "hi" };
    expect(isText(b)).toBe(true);
    expect(isStatusLine(b)).toBe(false);
  });

  it("AgentMessage type accepts mixed blocks", () => {
    const m: AgentMessage = {
      blocks: [
        { kind: "text", content: "hi" },
        { kind: "thinking", text: "checking" },
        { kind: "status_line", label: "phase 1 done", run_id: "r1", tone: "info" },
        {
          kind: "tool_invocation",
          tool: "launch_feature",
          input: { feature_id: "outline" },
          tool_call_id: "call-1",
        },
        {
          kind: "tool_result",
          tool: "launch_feature",
          status: "launched",
          output: { execution_id: "exec-1", feature_id: "outline" },
          execution_id: "exec-1",
          feature_id: "outline",
          tool_call_id: "call-1",
        },
      ],
    };
    expect(m.blocks).toHaveLength(5);
  });

  it("question_card pills are typed", () => {
    const q: AgentBlock = {
      kind: "question_card",
      label: "需要你拍一下",
      question: "?",
      pills: [{ label: "A", intent: "go" }],
    };
    expect(isQuestionCard(q)).toBe(true);
    if (isQuestionCard(q)) {
      expect(q.pills[0].label).toBe("A");
    }
  });

  it("result_card requires feedback + stats", () => {
    const r: AgentBlock = {
      kind: "result_card",
      run_id: "r1",
      title: "done",
      tldr: "x",
      findings: [{ id: "1", text: "a" }],
      links: [],
      feedback: { question: "?", pills: [], allow_free_input: true },
      stats: { duration_ms: 1000, subagents: 3, tokens: 100 },
    };
    expect(isResultCard(r)).toBe(true);
  });

  it("normalizes legacy reasoning blocks to canonical thinking", () => {
    expect(
      normalizeChatBlock({
        type: "reasoning",
        title: "思考过程",
        data: { text: "step 1" },
      }),
    ).toEqual({ kind: "thinking", text: "step 1" });
  });

  it("normalizes legacy tool invocation blocks to top-level fields", () => {
    expect(
      normalizeChatBlock({
        kind: "tool_invocation",
        data: {
          tool: "launch_feature",
          args: { feature_id: "outline" },
          tool_call_id: "call-1",
        },
      }),
    ).toEqual({
      kind: "tool_invocation",
      tool: "launch_feature",
      input: { feature_id: "outline" },
      tool_call_id: "call-1",
    });
  });

  it("normalizes legacy tool result blocks to top-level fields", () => {
    expect(
      normalizeChatBlock({
        kind: "tool_result",
        data: {
          tool: "launch_feature",
          status: "launched",
          execution_id: "exec-1",
          feature_id: "outline",
          tool_call_id: "call-1",
        },
      }),
    ).toEqual({
      kind: "tool_result",
      tool: "launch_feature",
      status: "launched",
      output: {
        tool: "launch_feature",
        status: "launched",
        execution_id: "exec-1",
        feature_id: "outline",
        tool_call_id: "call-1",
      },
      execution_id: "exec-1",
      feature_id: "outline",
      tool_call_id: "call-1",
    });
  });

  it("leaves canonical tool blocks unchanged", () => {
    const block: AgentBlock = {
      kind: "tool_result",
      tool: "launch_feature",
      status: "launched",
      output: {},
      execution_id: "exec-1",
    };
    expect(normalizeChatBlock(block)).toEqual(block);
  });

  it("normalizes legacy warning blocks to visible status lines", () => {
    expect(
      normalizeChatBlock({
        type: "warning",
        title: "能力未启动",
        data: { detail: "缺少真实工具结果" },
      }),
    ).toEqual({
      kind: "status_line",
      label: "能力未启动：缺少真实工具结果",
      run_id: "warning-status",
      tone: "warn",
    });
  });

  it("normalizes malformed text-like blocks to visible text", () => {
    expect(
      normalizeChatBlock({
        kind: "text",
        text: "visible fallback",
      }),
    ).toEqual({ kind: "text", content: "visible fallback" });
  });

  it("normalizes malformed text blocks with non-string content to safe visible text", () => {
    expect(
      normalizeChatBlock({
        kind: "text",
        content: {
          detail: "structured fallback",
          output_ref: "/mnt/user-data/runtime/internal.json",
        },
      }),
    ).toEqual({
      kind: "text",
      content: "structured fallback",
    });
  });

  it("falls back unknown blocks to visible text instead of invalid kinds", () => {
    expect(
      normalizeChatBlock({
        type: "custom_panel",
        title: "Legacy panel",
        data: { detail: "useful detail" },
      }),
    ).toEqual({ kind: "text", content: "Legacy panel：useful detail" });
  });

  it("does not expose raw unknown block payloads by default", () => {
    const block = normalizeChatBlock({
      type: "custom_panel",
      data: {
        output_ref: "/mnt/user-data/runtime/internal.json",
        secret: "runtime payload",
      },
    });

    expect(block).toEqual({ kind: "text", content: "Unsupported message block" });
    if (block.kind !== "text") {
      throw new Error("expected text fallback");
    }
    expect(block.content).not.toContain("/mnt/user-data/runtime/internal.json");
    expect(block.content).not.toContain("runtime payload");
  });

  it("normalizes incomplete result cards with renderer-safe defaults", () => {
    expect(
      normalizeChatBlock({
        kind: "result_card",
        run_id: "run-1",
        title: "Finished",
        tldr: "Summary",
        findings: [],
        stats: { duration_ms: 100, subagents: 1, tokens: 10 },
      }),
    ).toEqual({
      kind: "result_card",
      run_id: "run-1",
      title: "Finished",
      tldr: "Summary",
      findings: [],
      links: [],
      review_items: [],
      feedback: { question: "", pills: [], allow_free_input: true },
      stats: { duration_ms: 100, subagents: 1, tokens: 10 },
    });
  });
});
