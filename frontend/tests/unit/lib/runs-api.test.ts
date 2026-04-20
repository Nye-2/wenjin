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
  cancelRun,
  cancelThreadRun,
  createThreadRun,
  getRun,
  getThreadRun,
  waitRun,
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

    await createThreadRun("thread id/1", { message: "hello" });
    await waitThreadRun("thread id/1", { message: "hello" });

    expect(mockPost).toHaveBeenNthCalledWith(
      1,
      "/threads/thread%20id%2F1/runs",
      { message: "hello" }
    );
    expect(mockPost).toHaveBeenNthCalledWith(
      2,
      "/threads/thread%20id%2F1/runs/wait",
      { message: "hello" }
    );
  });

  it("encodes run id for read routes", async () => {
    mockGet
      .mockResolvedValueOnce({ data: { run_id: "run/1" } })
      .mockResolvedValueOnce({ data: { run_id: "run/2" } });

    await getThreadRun("thread-1", "run/1");
    await getRun("run/2");

    expect(mockGet).toHaveBeenNthCalledWith(
      1,
      "/threads/thread-1/runs/run%2F1"
    );
    expect(mockGet).toHaveBeenNthCalledWith(2, "/runs/run%2F2");
  });

  it("builds cancel query string for scoped and stateless run cancellation", async () => {
    mockPost.mockResolvedValue({ data: null });

    await cancelThreadRun("thread-1", "run-1", {
      action: "rollback",
      wait: true,
    });
    await cancelRun("run-2", {
      action: "interrupt",
      wait: false,
    });

    expect(mockPost).toHaveBeenNthCalledWith(
      1,
      "/threads/thread-1/runs/run-1/cancel?action=rollback&wait=true"
    );
    expect(mockPost).toHaveBeenNthCalledWith(
      2,
      "/runs/run-2/cancel?action=interrupt&wait=false"
    );
  });

  it("posts stateless wait requests", async () => {
    mockPost.mockResolvedValueOnce({
      data: { run_id: "run-3", thread_id: "thread-3", status: "success" },
    });

    await waitRun({ message: "hello" });

    expect(mockPost).toHaveBeenCalledWith("/runs/wait", { message: "hello" });
  });
});
