import { describe, expect, it, vi } from "vitest";

import {
  deleteRunLifecycle,
  pauseRunLifecycle,
  resumeRunLifecycle,
} from "@/lib/api/runs";

describe("runs lifecycle wrappers (Plan 2 T2)", () => {
  it("POSTs to /api/runs/{id}/pause", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    await pauseRunLifecycle("r1");
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/runs/r1/pause",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("POSTs to /api/runs/{id}/resume", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    await resumeRunLifecycle("r1");
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/runs/r1/resume",
      expect.objectContaining({ method: "POST" }),
    );
  });

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
    await pauseRunLifecycle("run/with/slashes");
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/runs/run%2Fwith%2Fslashes/pause",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("throws on non-2xx response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("internal", { status: 500 }),
    );
    await expect(pauseRunLifecycle("r1")).rejects.toThrow(/500/);
  });
});
