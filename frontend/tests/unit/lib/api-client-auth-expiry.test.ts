import { beforeEach, describe, expect, it, vi } from "vitest";

import { authorizedFetch } from "@/lib/api/client";
import { useAuthStore } from "@/stores/auth";

describe("authorizedFetch session expiry", () => {
  beforeEach(() => {
    localStorage.clear();
    useAuthStore.setState({
      user: {
        id: "user-1",
        email: "student@example.com",
        name: "Student",
        role: "user",
      },
      accessToken: "expired-access-token",
      refreshToken: null,
      isAuthenticated: true,
      isLoading: false,
      error: null,
    });
  });

  it("clears the stale session after a final 401", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(JSON.stringify({ detail: "Not authenticated" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await authorizedFetch("/api/workspaces/workspace-1");

    expect(response.status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(useAuthStore.getState()).toMatchObject({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
    });
  });
});
