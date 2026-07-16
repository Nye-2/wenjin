import { afterEach, describe, expect, it, vi } from "vitest";

describe("api client URL normalization", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("defaults to the same-origin API path", async () => {
    vi.unstubAllEnvs();
    vi.resetModules();

    const { API_BASE_URL, normalizeAuthorizedFetchInput } = await import(
      "@/lib/api/client"
    );

    expect(API_BASE_URL).toBe("/api");
    expect(normalizeAuthorizedFetchInput("/api/workspaces/ws-1/thread")).toBe(
      "/api/workspaces/ws-1/thread",
    );
  });

  it("routes same-origin /api paths through the configured gateway base", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8001");
    vi.resetModules();

    const { API_BASE_URL, normalizeAuthorizedFetchInput } = await import(
      "@/lib/api/client"
    );

    expect(API_BASE_URL).toBe("http://localhost:8001/api");
    expect(normalizeAuthorizedFetchInput("/api/workspaces/ws-1/thread")).toBe(
      "http://localhost:8001/api/workspaces/ws-1/thread",
    );
    expect(
      normalizeAuthorizedFetchInput("/api/missions/mission-1?include=items"),
    ).toBe("http://localhost:8001/api/missions/mission-1?include=items");
  });

  it("keeps non-api and absolute fetch targets unchanged", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8001");
    vi.resetModules();

    const { normalizeAuthorizedFetchInput } = await import("@/lib/api/client");

    expect(normalizeAuthorizedFetchInput("/assets/logo.png")).toBe(
      "/assets/logo.png",
    );
    expect(normalizeAuthorizedFetchInput("https://example.com/api")).toBe(
      "https://example.com/api",
    );
  });

  it("treats authentication failures as terminal event-stream responses", async () => {
    const { isTerminalEventStreamStatus } = await import("@/lib/api/client");

    expect(isTerminalEventStreamStatus(401)).toBe(true);
    expect(isTerminalEventStreamStatus(403)).toBe(true);
    expect(isTerminalEventStreamStatus(500)).toBe(false);
    expect(isTerminalEventStreamStatus(undefined)).toBe(false);
  });
});
