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
            name: "gpt-5.6-sol",
            display_name: "GPT-5.6 Sol",
            provider: "openai",
            category: "llm",
            max_tokens: 128000,
            generation_api: "chat_completions",
            capability_profile_version: "2026-07-11",
            strict_tool_calls: true,
            streaming: true,
            reasoning_efforts: ["low", "medium", "high", "xhigh"],
            vision: false,
            native_web_search: false,
            is_default: true,
          },
        ],
      },
    });

    await expect(listModels("chat")).resolves.toEqual({
      models: [
        {
          name: "gpt-5.6-sol",
          display_name: "GPT-5.6 Sol",
          provider: "openai",
          category: "llm",
          max_tokens: 128000,
          generation_api: "chat_completions",
          capability_profile_version: "2026-07-11",
          capability_profile: {
            strict_tool_calls: true,
            streaming: true,
            reasoning_efforts: ["low", "medium", "high", "xhigh"],
            vision: false,
            native_web_search: false,
          },
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
