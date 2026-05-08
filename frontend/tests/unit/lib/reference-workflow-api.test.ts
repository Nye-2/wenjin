import { beforeEach, describe, expect, it, vi } from "vitest";

const mockPost = vi.fn();
const mockGet = vi.fn();

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    post: (...args: unknown[]) => mockPost(...args),
    get: (...args: unknown[]) => mockGet(...args),
  },
}));

import {
  buildReferenceEvidencePack,
  getReferenceBibtex,
  syncReferenceBibtexToPrism,
  validateReferenceBibtex,
} from "@/lib/api/workspace";

describe("reference writing workflow api wrappers", () => {
  beforeEach(() => {
    mockPost.mockReset();
    mockGet.mockReset();
  });

  it("builds evidence packs through the workspace reference endpoint", async () => {
    mockPost.mockResolvedValueOnce({
      data: { policy: "outline_first_no_vector_rag" },
    });

    await buildReferenceEvidencePack("workspace/1", {
      query: "grounded",
      reference_ids: ["ref-1"],
      max_units: 4,
    });

    expect(mockPost).toHaveBeenCalledWith(
      "/workspaces/workspace/1/references/evidence-pack",
      {
        query: "grounded",
        reference_ids: ["ref-1"],
        max_units: 4,
      }
    );
  });

  it("syncs refs.bib to Prism with the requested scope", async () => {
    mockPost.mockResolvedValueOnce({
      data: { synced_file: "refs.bib", latex_project_id: "latex-1" },
    });

    await syncReferenceBibtexToPrism("ws-1", "used_only");

    expect(mockPost).toHaveBeenCalledWith(
      "/workspaces/ws-1/references/bibtex/sync-prism",
      { scope: "used_only" }
    );
  });

  it("validates citation keys when latex content is provided", async () => {
    mockPost.mockResolvedValueOnce({
      data: { valid: true, missing_keys: [], unverified_keys: [] },
    });

    await validateReferenceBibtex("ws-1", String.raw`\cite{lovelace2026}`);

    expect(mockPost).toHaveBeenCalledWith(
      "/workspaces/ws-1/references/bibtex/validate",
      { latex_content: String.raw`\cite{lovelace2026}` }
    );
  });

  it("falls back to key integrity validation when no latex content is provided", async () => {
    mockPost.mockResolvedValueOnce({
      data: { ok: true, duplicate_citation_keys: [] },
    });

    await validateReferenceBibtex("ws-1");

    expect(mockPost).toHaveBeenCalledWith(
      "/workspaces/ws-1/references/bibtex/validate",
      undefined
    );
  });

  it("reads generated BibTeX with the selected scope", async () => {
    mockGet.mockResolvedValueOnce({
      data: { content: "@article{lovelace2026}", reference_count: 1 },
    });

    await getReferenceBibtex("ws-1", "used_only");

    expect(mockGet).toHaveBeenCalledWith(
      "/workspaces/ws-1/references/bibtex",
      { params: { scope: "used_only" } }
    );
  });
});
