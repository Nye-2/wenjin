import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGet = vi.fn();

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
  },
}));

import { listModels } from "@/lib/api/models";

describe("model api wrappers", () => {
  beforeEach(() => {
    mockGet.mockReset();
  });

  it("normalizes dataservice items into composer models", async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        items: [
          {
            name: "gpt-5.3-codex-spark",
            display_name: "GPT 5.3 Spark",
            provider: "openai",
            category: "llm",
            is_default: true,
          },
        ],
      },
    });

    await expect(listModels("chat")).resolves.toEqual({
      models: [
        {
          name: "gpt-5.3-codex-spark",
          display_name: "GPT 5.3 Spark",
          provider: "openai",
          category: "llm",
          is_default: true,
        },
      ],
    });
    expect(mockGet).toHaveBeenCalledWith("/models", {
      params: { purpose: "chat" },
    });
  });

  it("returns an empty model list for empty fallback responses", async () => {
    mockGet.mockResolvedValueOnce({ data: {} });

    await expect(listModels()).resolves.toEqual({ models: [] });
  });
});
