import { beforeEach, describe, expect, it, vi } from "vitest";

const mockPost = vi.fn();

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    post: (...args: unknown[]) => mockPost(...args),
    get: vi.fn(),
  },
}));

import {
  ensureWorkspaceThread,
  uploadThreadFiles,
} from "@/lib/api/threads";

describe("chat api wrappers", () => {
  beforeEach(() => {
    mockPost.mockReset();
  });

  it("posts ensure workspace thread requests", async () => {
    mockPost.mockResolvedValueOnce({ data: { id: "thread-1" } });

    await ensureWorkspaceThread("ws 1", {
      model: "qwen-plus",
    });

    expect(mockPost).toHaveBeenCalledWith("/workspaces/ws%201/thread", {
      model: "qwen-plus",
    });
  });

  it("uploads thread files through multipart endpoint", async () => {
    const file = new File(["hello"], "hello.txt", { type: "text/plain" });
    mockPost.mockResolvedValueOnce({
      data: { success: true, files: [], message: "ok" },
    });

    await uploadThreadFiles({
      threadId: "thread id/1",
      kind: "transient",
      workspaceId: "ws-1",
      files: [file],
    });

    const [url, body, config] = mockPost.mock.calls[0] as [
      string,
      FormData,
      { headers: Record<string, string> },
    ];

    expect(url).toBe("/threads/thread%20id%2F1/uploads");
    expect(config.headers["Content-Type"]).toBe("multipart/form-data");
    expect(body.get("kind")).toBe("transient");
    expect(body.get("workspace_id")).toBe("ws-1");
    expect(body.getAll("files")).toHaveLength(1);
  });
});
