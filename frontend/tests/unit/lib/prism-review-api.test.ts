import { beforeEach, describe, expect, it, vi } from "vitest";

const mockPost = vi.fn();

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    post: (...args: unknown[]) => mockPost(...args),
  },
  authorizedFetch: vi.fn(),
  readErrorMessage: vi.fn(),
}));

import {
  applyLatexFileChange,
  discardLatexFileChange,
  previewLatexFileChange,
  protectLatexSection,
  revertLatexFileChange,
} from "@/lib/api/latex";

describe("prism review file-change api wrappers", () => {
  beforeEach(() => {
    mockPost.mockReset();
  });

  it("previews pending file changes by logical key", async () => {
    mockPost.mockResolvedValueOnce({
      data: { change_signature: "signature" },
    });

    await previewLatexFileChange("latex-1", {
      logical_key: "section:introduction",
    });

    expect(mockPost).toHaveBeenCalledWith(
      "/prism/latex-adapter/projects/latex-1/file-changes/preview",
      { logical_key: "section:introduction" }
    );
  });

  it("applies previewed file changes with the signed preview", async () => {
    mockPost.mockResolvedValueOnce({
      data: { applied: true },
    });

    await applyLatexFileChange("latex-1", {
      logical_key: "section:introduction",
      change_signature: "a".repeat(64),
    });

    expect(mockPost).toHaveBeenCalledWith(
      "/prism/latex-adapter/projects/latex-1/file-changes/apply",
      {
        logical_key: "section:introduction",
        change_signature: "a".repeat(64),
      }
    );
  });

  it("discards pending file changes without touching file content", async () => {
    mockPost.mockResolvedValueOnce({
      data: { discarded: true },
    });

    await discardLatexFileChange("latex-1", {
      logical_key: "section:introduction",
    });

    expect(mockPost).toHaveBeenCalledWith(
      "/prism/latex-adapter/projects/latex-1/file-changes/discard",
      { logical_key: "section:introduction" }
    );
  });

  it("reverts applied file changes with the stored undo signature", async () => {
    mockPost.mockResolvedValueOnce({
      data: { reverted: true },
    });

    await revertLatexFileChange("latex-1", {
      logical_key: "section:introduction",
      revert_signature: "b".repeat(64),
    });

    expect(mockPost).toHaveBeenCalledWith(
      "/prism/latex-adapter/projects/latex-1/file-changes/revert",
      {
        logical_key: "section:introduction",
        revert_signature: "b".repeat(64),
      }
    );
  });

  it("protects a workspace-owned Prism file through the canonical endpoint", async () => {
    mockPost.mockResolvedValueOnce({
      data: { protected: true },
    });

    await protectLatexSection("latex-1", {
      path: "sections/introduction.tex",
      scope: "file",
      reason: "user_manual_protect",
    });

    expect(mockPost).toHaveBeenCalledWith(
      "/prism/latex-adapter/projects/latex-1/protected-sections",
      {
        path: "sections/introduction.tex",
        scope: "file",
        reason: "user_manual_protect",
      }
    );
  });
});
