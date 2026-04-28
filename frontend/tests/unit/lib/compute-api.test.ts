import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGet = vi.fn();

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
  },
}));

import {
  getComputeProjection,
  getComputeSession,
  getWorkspaceComputeSessions,
} from "@/lib/api/compute";

describe("compute api wrappers", () => {
  beforeEach(() => {
    mockGet.mockReset();
  });

  it("reads workspace compute sessions with encoded workspace id and limit", async () => {
    mockGet.mockResolvedValueOnce({ data: { items: [], count: 0 } });

    await getWorkspaceComputeSessions("workspace / 1", 12);

    expect(mockGet).toHaveBeenCalledWith(
      "/workspaces/workspace%20%2F%201/compute/sessions",
      { params: { limit: 12 } }
    );
  });

  it("reads compute session and projection by encoded session id", async () => {
    mockGet
      .mockResolvedValueOnce({ data: { id: "compute/1" } })
      .mockResolvedValueOnce({ data: { compute_session: { id: "compute/1" } } });

    await getComputeSession("compute/1");
    await getComputeProjection("compute/1");

    expect(mockGet).toHaveBeenNthCalledWith(
      1,
      "/compute/sessions/compute%2F1"
    );
    expect(mockGet).toHaveBeenNthCalledWith(
      2,
      "/compute/sessions/compute%2F1/projection"
    );
  });
});
