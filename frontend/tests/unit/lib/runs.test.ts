import { describe, expect, it, vi } from "vitest";
import { pauseRun, resumeRun, cancelWorkspaceRun, deleteRun } from "@/lib/api/runs";

describe("runs API wrappers", () => {
  it("POSTs to /pause", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );
    await pauseRun("ws1", "r1");
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/workspaces/ws1/runs/r1/pause",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("POSTs to /resume", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );
    await resumeRun("ws1", "r1");
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/workspaces/ws1/runs/r1/resume",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("POSTs to /cancel", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );
    await cancelWorkspaceRun("ws1", "r1");
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/workspaces/ws1/runs/r1/cancel",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("DELETEs runs", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );
    await deleteRun("ws1", "r1");
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/workspaces/ws1/runs/r1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("throws on non-2xx", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("err", { status: 500 }),
    );
    await expect(pauseRun("ws1", "r1")).rejects.toThrow(/500/);
  });
});
