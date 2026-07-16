import { describe, expect, it } from "vitest";

import { resolveThreadStreamUrl } from "@/lib/api/streams";

describe("chat stream endpoint routing", () => {
  it("routes to thread runs stream when thread_id is provided", () => {
    const url = resolveThreadStreamUrl({
      message: "hello",
      thread_id: "thread-1",
    });
    expect(url).toContain("/threads/thread-1/runs/stream");
  });

  it("requires a thread-bound chat transport", () => {
    expect(() => resolveThreadStreamUrl({ message: "hello" })).toThrow(
      "thread_id is required",
    );
  });

  it("trims and encodes thread_id safely", () => {
    const url = resolveThreadStreamUrl({
      message: "hello",
      thread_id: "  thread id/2  ",
    });
    expect(url).toContain("/threads/thread%20id%2F2/runs/stream");
  });
});
