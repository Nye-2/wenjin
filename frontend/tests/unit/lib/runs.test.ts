import { describe, expect, it, vi } from "vitest";

import { deleteRunLifecycle } from "@/lib/api/runs";

describe("runs lifecycle wrappers", () => {
  it("DELETEs /api/runs/{id}", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    await deleteRunLifecycle("r1");
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/runs/r1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("encodes ids that contain special characters", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    await deleteRunLifecycle("run/with/slashes");
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/runs/run%2Fwith%2Fslashes",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("throws on non-2xx response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("internal", { status: 500 }),
    );
    await expect(deleteRunLifecycle("r1")).rejects.toThrow(/500/);
  });
});
