import { describe, expect, it } from "vitest";

import {
  DOCUMENT_REWRITE_CONTEXT_REQUIREMENTS,
  LOCAL_REWRITE_CONTEXT_REQUIREMENTS,
} from "@/components/latex/latex-editor/prismRewriteContext";

describe("Prism rewrite context contracts", () => {
  it("keeps local rewrite context lightweight", () => {
    expect(LOCAL_REWRITE_CONTEXT_REQUIREMENTS).toEqual({
      include_manuscript_context: true,
      include_workspace_history: false,
      include_related_documents: false,
      include_sandbox_artifacts: false,
      include_pending_review_summary: false,
    });
  });

  it("keeps whole-document rewrite context workspace-aware", () => {
    expect(DOCUMENT_REWRITE_CONTEXT_REQUIREMENTS).toEqual({
      include_manuscript_context: true,
      include_workspace_history: true,
      include_related_documents: true,
      include_sandbox_artifacts: true,
      include_pending_review_summary: true,
    });
  });
});
