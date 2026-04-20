import { beforeEach, describe, expect, it, vi } from "vitest";

const mockPost = vi.fn();
const mockGet = vi.fn();

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    post: (...args: unknown[]) => mockPost(...args),
    get: (...args: unknown[]) => mockGet(...args),
  },
}));

import {
  getThreadHistory,
  getThreadState,
  searchThreads,
} from "@/lib/api/threads";

describe("threads api wrappers", () => {
  beforeEach(() => {
    mockPost.mockReset();
    mockGet.mockReset();
  });

  it("uses default pagination/search payload for thread search", async () => {
    mockPost.mockResolvedValueOnce({ data: [] });

    await searchThreads();

    expect(mockPost).toHaveBeenCalledWith("/threads/search", {
      metadata: {},
      status: undefined,
      limit: 100,
      offset: 0,
    });
  });

  it("forwards custom filters for thread search", async () => {
    mockPost.mockResolvedValueOnce({ data: [] });

    await searchThreads({
      metadata: { workspace_id: "ws-1" },
      status: "busy",
      limit: 25,
      offset: 10,
    });

    expect(mockPost).toHaveBeenCalledWith("/threads/search", {
      metadata: { workspace_id: "ws-1" },
      status: "busy",
      limit: 25,
      offset: 10,
    });
  });

  it("encodes thread id for state and history endpoints", async () => {
    mockGet.mockResolvedValueOnce({ data: { values: {}, tasks: [], next: [], metadata: {}, checkpoint: {} } });
    mockPost.mockResolvedValueOnce({ data: [] });

    await getThreadState("thread id/1");
    await getThreadHistory("thread id/1", { before: "ckpt-1", limit: 5 });

    expect(mockGet).toHaveBeenCalledWith("/threads/thread%20id%2F1/state");
    expect(mockPost).toHaveBeenCalledWith("/threads/thread%20id%2F1/history", {
      limit: 5,
      before: "ckpt-1",
    });
  });

  it("applies default history limit when omitted", async () => {
    mockPost.mockResolvedValueOnce({ data: [] });

    await getThreadHistory("thread-1");

    expect(mockPost).toHaveBeenCalledWith("/threads/thread-1/history", {
      limit: 10,
      before: undefined,
    });
  });
});
