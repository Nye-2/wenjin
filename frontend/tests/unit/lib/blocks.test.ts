import { describe, expect, it } from "vitest";
import {
  AgentBlock, AgentMessage, isQuestionCard, isResultCard,
  isStatusLine, isText,
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
        { kind: "status_line", label: "phase 1 done", run_id: "r1", tone: "info" },
      ],
    };
    expect(m.blocks).toHaveLength(2);
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
});
