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
  cancelThreadRun,
  createThreadRun,
  getThreadRun,
  waitThreadRun,
} from "@/lib/api/runs";

describe("runs api wrappers", () => {
  beforeEach(() => {
    mockPost.mockReset();
    mockGet.mockReset();
  });

  it("posts create and wait requests under thread-scoped runs routes", async () => {
    mockPost
      .mockResolvedValueOnce({ data: { run_id: "run-1" } })
      .mockResolvedValueOnce({
        data: { run_id: "run-2", thread_id: "thread-1", status: "success" },
      });

    await createThreadRun("thread id/1", { request_id: "request-1", message: "hello" });
    await waitThreadRun("thread id/1", { request_id: "request-2", message: "hello" });

    expect(mockPost).toHaveBeenNthCalledWith(
      1,
      "/threads/thread%20id%2F1/runs",
      { request_id: "request-1", message: "hello" }
    );
    expect(mockPost).toHaveBeenNthCalledWith(
      2,
      "/threads/thread%20id%2F1/runs/wait",
      { request_id: "request-2", message: "hello" }
    );
  });

  it("encodes run id for thread-bound read routes", async () => {
    mockGet.mockResolvedValueOnce({ data: { run_id: "run/1" } });

    await getThreadRun("thread-1", "run/1");

    expect(mockGet).toHaveBeenCalledWith("/threads/thread-1/runs/run%2F1");
  });

  it("builds a thread-bound cancel query string", async () => {
    mockPost.mockResolvedValue({ data: null });

    await cancelThreadRun("thread-1", "run-1", {
      action: "rollback",
      wait: true,
    });
    expect(mockPost).toHaveBeenCalledWith(
      "/threads/thread-1/runs/run-1/cancel?action=rollback&wait=true"
    );
  });
});
