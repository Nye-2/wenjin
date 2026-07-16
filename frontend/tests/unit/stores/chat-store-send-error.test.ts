import { beforeEach, describe, expect, it, vi } from "vitest";

const { authorizedFetchMock, readErrorMessageMock } = vi.hoisted(() => ({
  authorizedFetchMock: vi.fn(),
  readErrorMessageMock: vi.fn(),
}));

vi.mock("@/lib/api/client", () => ({
  authorizedFetch: authorizedFetchMock,
  readErrorMessage: readErrorMessageMock,
}));

import { useChatStoreV2 } from "@/stores/chat-store";

describe("chat send failures", () => {
  beforeEach(() => {
    authorizedFetchMock.mockReset();
    readErrorMessageMock.mockReset();
    useChatStoreV2.getState().reset();
  });

  it("shows an explicit failure block instead of silently keeping a fake send", async () => {
    authorizedFetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not authenticated" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );
    readErrorMessageMock.mockResolvedValue("登录已失效，请重新登录");

    const result = await useChatStoreV2
      .getState()
      .sendMessage("workspace-1", "启动第三阶段");

    expect(result).toEqual({
      status: "failed",
      error: "登录已失效，请重新登录",
    });
    expect(useChatStoreV2.getState().getWorkspaceMessages("workspace-1"))
      .toMatchObject([
        { role: "user" },
        {
          role: "assistant",
          blocks: [
            {
              kind: "status_line",
              label: "登录已失效，请重新登录",
              tone: "error",
            },
          ],
        },
      ]);
    expect(useChatStoreV2.getState().isSending).toBe(false);
  });

  it("forwards the complete canonical attachment contract", async () => {
    authorizedFetchMock
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "thread-1", messages: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response('event: content\ndata: {"content":"已读取"}\n\n', {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
      );
    const attachment = {
      name: "problem.pdf",
      path: "/mnt/user-data/uploads/problem.pdf",
      kind: "transient" as const,
      url: "/api/threads/thread-1/artifacts/mnt/user-data/uploads/problem.pdf",
      content_type: "application/pdf",
      size_bytes: 2048,
      reference_id: null,
      artifact_id: null,
      metadata: {
        preprocess: { status: "disabled", provider: "unknown" },
      },
    };

    await useChatStoreV2
      .getState()
      .sendMessage("workspace-1", "请读取赛题", [attachment]);

    const streamInit = authorizedFetchMock.mock.calls[1][1] as RequestInit;
    const payload = JSON.parse(String(streamInit.body));
    expect(payload.attachments).toEqual([attachment]);
    expect(
      useChatStoreV2.getState().getWorkspaceMessages("workspace-1")[0]
        .metadata?.attachments,
    ).toEqual([attachment]);
  });

  it("resolves the thread id even when workspace messages are already cached", async () => {
    const store = useChatStoreV2.getState();
    store.setActiveWorkspace("workspace-1");
    store.handleEvent({
      type: "chat.user.message",
      data: { id: "cached-message", content: "已有消息" },
    });
    authorizedFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ id: "thread-cached", messages: [] }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await expect(store.loadHistory("workspace-1")).resolves.toBe(
      "thread-cached",
    );
    expect(useChatStoreV2.getState().getThreadId("workspace-1")).toBe(
      "thread-cached",
    );
    await expect(
      useChatStoreV2.getState().loadHistory("workspace-1"),
    ).resolves.toBe("thread-cached");
    expect(authorizedFetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not treat steer status blocks as newly launched missions", async () => {
    authorizedFetchMock
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "thread-1", messages: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          'event: block\ndata: {"block":{"kind":"status_line","label":"研究要求已更新","run_id":"mission-1","tone":"info","action":"steer_mission"}}\n\n',
          {
            status: 200,
            headers: { "Content-Type": "text/event-stream" },
          },
        ),
      );

    await expect(
      useChatStoreV2
        .getState()
        .sendMessage("workspace-1", "把样本量改成 100"),
    ).resolves.toBeUndefined();
  });

  it("returns a mission only for an explicit start status block", async () => {
    authorizedFetchMock
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "thread-1", messages: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          'event: block\ndata: {"block":{"kind":"status_line","label":"研究任务已开始","run_id":"mission-1","tone":"info","action":"start_mission"}}\n\n',
          {
            status: 200,
            headers: { "Content-Type": "text/event-stream" },
          },
        ),
      );

    await expect(
      useChatStoreV2.getState().sendMessage("workspace-1", "开始研究"),
    ).resolves.toEqual({ missionId: "mission-1", status: "launched" });
  });

  it("aborts and isolates an old workspace stream after navigation", async () => {
    const streamState: {
      controller?: ReadableStreamDefaultController<Uint8Array>;
    } = {};
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        streamState.controller = controller;
      },
    });
    authorizedFetchMock
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "thread-1", messages: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(stream, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
      );

    const pending = useChatStoreV2
      .getState()
      .sendMessage("workspace-1", "长任务");
    await vi.waitFor(() => {
      expect(authorizedFetchMock).toHaveBeenCalledTimes(2);
    });
    const streamInit = authorizedFetchMock.mock.calls[1][1] as RequestInit;

    useChatStoreV2.getState().setActiveWorkspace("workspace-2");
    expect(streamInit.signal?.aborted).toBe(true);
    const encoder = new TextEncoder();
    expect(streamState.controller).toBeDefined();
    streamState.controller!.enqueue(
      encoder.encode('event: content\ndata: {"content":"旧工作区内容"}\n\n'),
    );
    streamState.controller!.close();
    await pending;

    expect(
      useChatStoreV2.getState().getWorkspaceMessages("workspace-2"),
    ).toEqual([]);
    expect(
      JSON.stringify(
        useChatStoreV2.getState().getWorkspaceMessages("workspace-1"),
      ),
    ).not.toContain("旧工作区内容");
    expect(useChatStoreV2.getState().isSending).toBe(false);
  });
});
