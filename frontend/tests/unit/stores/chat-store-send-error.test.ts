import { beforeEach, describe, expect, it, vi } from "vitest";

const { authorizedFetchMock, readErrorMessageMock } = vi.hoisted(() => ({
  authorizedFetchMock: vi.fn(),
  readErrorMessageMock: vi.fn(),
}));

vi.mock("@/lib/api/client", () => ({
  API_BASE_URL: "/api",
  authorizedFetch: authorizedFetchMock,
  readErrorMessage: readErrorMessageMock,
}));

import { useChatStoreV2 } from "@/stores/chat-store";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

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
        new Response('event: content\ndata: {"type":"content","content":"已读取"}\n\nevent: done\ndata: {"type":"done"}\n\n', {
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

  it("force-refreshes cached history from the canonical thread projection", async () => {
    authorizedFetchMock
      .mockResolvedValueOnce(
        new Response(JSON.stringify({
          id: "thread-1",
          messages: [{
            id: "message-old",
            role: "assistant",
            blocks: [{ kind: "text", content: "旧内容" }],
            created_at: "2026-07-23T00:00:00Z",
          }],
        }), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({
          id: "thread-1",
          messages: [{
            id: "message-new",
            role: "assistant",
            blocks: [{ kind: "text", content: "服务端最终内容" }],
            created_at: "2026-07-23T00:01:00Z",
          }],
        }), { status: 200 }),
      );

    const store = useChatStoreV2.getState();
    await store.loadHistory("workspace-1");
    store.handleEvent({
      type: "chat.user.message",
      data: { id: "local-only", content: "本地临时内容" },
    });

    await store.refreshHistory("workspace-1");

    expect(
      useChatStoreV2.getState().getWorkspaceMessages("workspace-1"),
    ).toMatchObject([
      {
        id: "message-new",
        blocks: [{ kind: "text", content: "服务端最终内容" }],
      },
    ]);
  });

  it("deduplicates concurrent canonical history refreshes", async () => {
    const delayedHistory = deferred<Response>();
    authorizedFetchMock.mockReturnValueOnce(delayedHistory.promise);

    const store = useChatStoreV2.getState();
    store.setActiveWorkspace("workspace-1");
    const first = store.refreshHistory("workspace-1");
    const second = store.refreshHistory("workspace-1");

    expect(authorizedFetchMock).toHaveBeenCalledTimes(1);
    delayedHistory.resolve(
      new Response(
        JSON.stringify({ id: "thread-1", messages: [] }),
        { status: 200 },
      ),
    );

    await expect(Promise.all([first, second])).resolves.toEqual([
      "thread-1",
      "thread-1",
    ]);
  });

  it("does not let an older history response overwrite a newly started turn", async () => {
    const delayedHistory = deferred<Response>();
    const liveStream = new ReadableStream<Uint8Array>({ start() {} });
    authorizedFetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ id: "thread-1", messages: [] }),
          { status: 200 },
        ),
      )
      .mockReturnValueOnce(delayedHistory.promise)
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ id: "thread-1", messages: [] }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(liveStream, {
          status: 200,
          headers: {
            "Content-Type": "text/event-stream",
            "Content-Location": "/api/threads/thread-1/runs/run-live/stream",
          },
        }),
      );

    const store = useChatStoreV2.getState();
    await store.loadHistory("workspace-1");
    const refresh = store.refreshHistory("workspace-1");
    const sending = store.sendMessage("workspace-1", "新的问题");
    await vi.waitFor(() => {
      expect(authorizedFetchMock).toHaveBeenCalledTimes(4);
    });

    delayedHistory.resolve(
      new Response(JSON.stringify({
        id: "thread-1",
        messages: [{
          id: "stale-message",
          role: "assistant",
          blocks: [{ kind: "text", content: "过期快照" }],
          created_at: "2026-07-23T00:00:00Z",
        }],
      }), { status: 200 }),
    );
    await refresh;

    expect(JSON.stringify(
      useChatStoreV2.getState().getWorkspaceMessages("workspace-1"),
    )).toContain("新的问题");
    expect(JSON.stringify(
      useChatStoreV2.getState().getWorkspaceMessages("workspace-1"),
    )).not.toContain("过期快照");

    useChatStoreV2.getState().reset();
    await expect(sending).resolves.toEqual({ status: "cancelled" });
  });

  it("rejoins an active run and finishes with canonical persisted history", async () => {
    authorizedFetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ id: "thread-1", messages: [] }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify([{
          run_id: "run-1",
          thread_id: "thread-1",
          status: "running",
          created_at: "2026-07-23T00:00:00Z",
        }]), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response([
          'event: content\ndata: {"type":"content","content":"恢复内容"}',
          'event: block\ndata: {"type":"block","message_id":"assistant-1","block":{"kind":"status_line","label":"研究任务已开始","run_id":"mission-1","tone":"info","action":"start_mission"}}',
          'event: done\ndata: {"type":"done"}',
          "",
        ].join("\n\n"), {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({
          id: "thread-1",
          messages: [{
            id: "assistant-persisted",
            role: "assistant",
            blocks: [{ kind: "text", content: "服务端已保存的最终回答" }],
            created_at: "2026-07-23T00:01:00Z",
          }],
        }), { status: 200 }),
      );

    const store = useChatStoreV2.getState();
    await store.loadHistory("workspace-1");

    await expect(
      store.recoverActiveRun("workspace-1", "thread-1"),
    ).resolves.toEqual({ status: "launched", missionId: "mission-1" });
    expect(
      useChatStoreV2.getState().getWorkspaceMessages("workspace-1"),
    ).toMatchObject([{
      id: "assistant-persisted",
      blocks: [{ kind: "text", content: "服务端已保存的最终回答" }],
    }]);
    expect(authorizedFetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/workspaces/workspace-1/thread",
      "/api/threads/thread-1/runs",
      "/api/threads/thread-1/runs/run-1/stream",
      "/api/workspaces/workspace-1/thread",
    ]);
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
          'event: block\ndata: {"type":"block","message_id":"assistant-1","block":{"kind":"status_line","label":"研究要求已更新","run_id":"mission-1","tone":"info","action":"steer_mission"}}\n\nevent: done\ndata: {"type":"done"}\n\n',
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
    ).resolves.toEqual({ status: "completed" });
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
          'event: block\ndata: {"type":"block","message_id":"assistant-1","block":{"kind":"status_line","label":"研究任务已开始","run_id":"mission-1","tone":"info","action":"start_mission"}}\n\nevent: done\ndata: {"type":"done"}\n\n',
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
    await expect(pending).resolves.toEqual({ status: "cancelled" });

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

  it("stops an active run through the server cancel endpoint", async () => {
    const stream = new ReadableStream<Uint8Array>({ start() {} });
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
          headers: {
            "Content-Type": "text/event-stream",
            "Content-Location": "/api/threads/thread-1/runs/run-1/stream",
          },
        }),
      )
      .mockResolvedValueOnce(new Response("", { status: 202 }));

    const pending = useChatStoreV2
      .getState()
      .sendMessage("workspace-1", "请生成回答");
    await vi.waitFor(() => {
      expect(useChatStoreV2.getState().activeStream).not.toBeNull();
    });

    await useChatStoreV2.getState().stopSending();

    await expect(pending).resolves.toEqual({ status: "cancelled" });
    expect(authorizedFetchMock.mock.calls[2]?.[0]).toBe(
      "/api/threads/thread-1/runs/run-1/cancel?action=interrupt",
    );
    expect(authorizedFetchMock.mock.calls[2]?.[1]).toMatchObject({
      method: "POST",
    });
  });
});
