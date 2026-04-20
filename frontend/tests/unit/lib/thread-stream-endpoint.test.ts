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

  it("routes to stateless runs stream when thread_id is missing", () => {
    const url = resolveThreadStreamUrl({
      message: "hello",
    });
    expect(url).toContain("/runs/stream");
    expect(url).not.toContain("/threads/");
  });

  it("trims and encodes thread_id safely", () => {
    const url = resolveThreadStreamUrl({
      message: "hello",
      thread_id: "  thread id/2  ",
    });
    expect(url).toContain("/threads/thread%20id%2F2/runs/stream");
  });
});
