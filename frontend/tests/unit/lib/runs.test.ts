import { describe, expect, it, vi } from "vitest";

import { deleteThreadRun } from "@/lib/api/runs";

describe("runs lifecycle wrappers", () => {
  it("DELETEs a thread-bound run", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    await deleteThreadRun("thread-1", "r1");
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/threads/thread-1/runs/r1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("encodes ids that contain special characters", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    await deleteThreadRun("thread/1", "run/with/slashes");
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/threads/thread%2F1/runs/run%2Fwith%2Fslashes",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("throws on non-2xx response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("internal", { status: 500 }),
    );
    await expect(deleteThreadRun("thread-1", "r1")).rejects.toThrow(/500/);
  });
});
