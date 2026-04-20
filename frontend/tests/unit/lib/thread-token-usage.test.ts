import { describe, expect, it } from "vitest";

import { parseThreadTokenUsage } from "@/lib/thread-token-usage";

describe("thread-token-usage", () => {
  it("parses usage payload from message metadata", () => {
    const usage = parseThreadTokenUsage({
      usage: {
        input_tokens: 12,
        output_tokens: 4,
        total_tokens: 16,
        model_name: "tool-primary",
        source: "thread_agent",
      },
    });

    expect(usage).toEqual({
      input_tokens: 12,
      output_tokens: 4,
      total_tokens: 16,
      model_name: "tool-primary",
      source: "thread_agent",
      credits_charged: null,
      free_tokens_applied: null,
      billable_tokens: null,
    });
  });

  it("falls back to billing token_usage payload", () => {
    const usage = parseThreadTokenUsage({
      billing: {
        token_usage: {
          prompt_tokens: 10,
          completion_tokens: 3,
        },
        model_name: "gen-fallback",
        credits_charged: 2,
        free_tokens_applied: 1000,
        billable_tokens: 1200,
      },
    });

    expect(usage).toEqual({
      input_tokens: 10,
      output_tokens: 3,
      total_tokens: 13,
      model_name: "gen-fallback",
      source: null,
      credits_charged: 2,
      free_tokens_applied: 1000,
      billable_tokens: 1200,
    });
  });

  it("returns null when no usage or billing token metadata exists", () => {
    expect(parseThreadTokenUsage({})).toBeNull();
    expect(parseThreadTokenUsage(null)).toBeNull();
  });
});
