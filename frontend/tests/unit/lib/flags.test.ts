import { describe, expect, it } from "vitest";
import { isFlagEnabled } from "@/lib/flags";

describe("Feature flags", () => {
  it("default_to_v2 is enabled", () => {
    expect(isFlagEnabled("default_to_v2")).toBe(true);
  });

  it("unknown flags default to false", () => {
    expect(isFlagEnabled("nonexistent")).toBe(false);
  });
});
