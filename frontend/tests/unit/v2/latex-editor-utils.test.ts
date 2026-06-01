import { describe, expect, it } from "vitest";

import type { ExecutionRecord } from "@/lib/api/types";
import {
  buildFeedbackAnchor,
  parsePdfAnchor,
  resolveFeedbackRange,
  resolveSnippetRange,
} from "@/components/latex/latex-editor/feedbackAnchors";
import {
  isImageFile,
  isTextFile,
  languageForPath,
} from "@/components/latex/latex-editor/fileKinds";
import {
  diffOpLabel,
  isWhitespaceOnlyDiffOp,
  rewriteProfileLabel,
  riskLevelLabel,
} from "@/components/latex/latex-editor/rewriteDisplay";
import {
  jobStatusFromExecution,
  prismExecutionNodeLabel,
  prismJobStatusLabel,
} from "@/components/latex/latex-editor/prismOptimizationJobs";

function makeExecution(status: ExecutionRecord["status"], reviewItems: unknown[] = []): ExecutionRecord {
  return {
    id: `exec-${status}`,
    user_id: "user-1",
    workspace_id: "ws-1",
    execution_type: "capability",
    feature_id: "prism_selection_optimize",
    status,
    params: {},
    node_states: {},
    artifact_ids: [],
    next_actions: [],
    child_execution_ids: [],
    progress: status === "completed" ? 100 : 20,
    created_at: "2026-05-31T00:00:00Z",
    updated_at: "2026-05-31T00:00:00Z",
    started_at: "2026-05-31T00:00:00Z",
    completed_at: status === "completed" ? "2026-05-31T00:01:00Z" : null,
    result: null,
    review_items: reviewItems as ExecutionRecord["review_items"],
  };
}

describe("latex editor pure helpers", () => {
  it("classifies editor languages and preview file kinds", () => {
    expect(languageForPath("main.tex")).toBe("latex");
    expect(languageForPath("refs.bib")).toBe("bibtex");
    expect(languageForPath("metadata.json")).toBe("json");
    expect(languageForPath("notes.md")).toBe("markdown");
    expect(languageForPath("figure.png")).toBe("plaintext");

    expect(isTextFile("sections/intro.tex")).toBe(true);
    expect(isTextFile("assets/figure.png")).toBe(false);
    expect(isImageFile("assets/figure.svg")).toBe(true);
    expect(isImageFile("main.tex")).toBe(false);
  });

  it("builds feedback anchors with nearest non-comment heading and line hints", () => {
    const content = [
      "\\section{Background}",
      "A first paragraph.",
      "% \\section{Ignored}",
      "\\subsection{Method}",
      "The selected contribution sentence is here.",
    ].join("\n");

    const start = content.indexOf("selected contribution");
    const anchor = buildFeedbackAnchor(content, start, start + "selected contribution".length);

    expect(anchor.heading_title).toBe("Method");
    expect(anchor.heading_level).toBe("subsection");
    expect(anchor.line_hint).toBe(5);
    expect(anchor.selected_text).toBe("selected contribution");
  });

  it("resolves feedback and snippet ranges after nearby content shifts", () => {
    const original = "Intro\nTarget claim about method.\nConclusion";
    const start = original.indexOf("Target claim");
    const item = {
      start,
      end: start + "Target claim about method.".length,
      selected_text: "Target claim about method.",
      anchor: buildFeedbackAnchor(original, start, start + "Target claim about method.".length),
    };
    const shifted = "Preface\nIntro\nTarget claim about method.\nConclusion";

    expect(resolveFeedbackRange(item, shifted)).toMatchObject({
      start: shifted.indexOf("Target claim"),
      end: shifted.indexOf("Target claim") + "Target claim about method.".length,
    });
    expect(resolveSnippetRange(shifted, "Target   claim about method.", 0)).toMatchObject({
      start: shifted.indexOf("Target claim"),
    });
  });

  it("sanitizes PDF anchors and rewrite display labels", () => {
    expect(
      parsePdfAnchor({
        page: "3",
        text: "selected pdf text",
        rects: [{ x: "1", y: 2, width: 3, height: 4 }, { x: "bad" }],
      }),
    ).toEqual({
      page: 3,
      text: "selected pdf text",
      rects: [{ x: 1, y: 2, width: 3, height: 4 }],
    });

    expect(parsePdfAnchor({ page: 0, rects: [] })).toBeNull();
    expect(rewriteProfileLabel("conservative")).toBe("保守");
    expect(riskLevelLabel("high")).toBe("高风险");
    expect(diffOpLabel("replace")).toBe("替换");
    expect(isWhitespaceOnlyDiffOp({ old_text: "a b", new_text: "ab" })).toBe(true);
  });

  it("maps Prism optimization execution status to compact UI labels", () => {
    expect(jobStatusFromExecution(makeExecution("running"))).toBe("running");
    expect(jobStatusFromExecution(makeExecution("completed"))).toBe("completed");
    expect(jobStatusFromExecution(makeExecution("failed_partial", [{}]))).toBe("completed");
    expect(jobStatusFromExecution(makeExecution("failed_partial"))).toBe("failed");
    expect(prismJobStatusLabel("advisory")).toBe("需要稍后重试");
    expect(prismExecutionNodeLabel("completed")).toBe("完成");
  });
});
