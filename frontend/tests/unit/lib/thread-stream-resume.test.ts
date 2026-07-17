import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockAuthorizedFetch = vi.fn();

vi.mock("@/lib/api/client", () => ({
  API_BASE_URL: "/api",
  authorizedFetch: (...args: unknown[]) => mockAuthorizedFetch(...args),
  readErrorMessage: vi.fn(async () => "stream error"),
  subscribeJsonEventStream: vi.fn(),
}));

import { streamThread } from "@/lib/api/streams";

function buildSseResponse(
  text: string,
  headers?: Record<string, string>
): Response {
  return new Response(text, {
    status: 200,
    headers: headers ?? {},
  });
}

function readHeaderValue(headers: HeadersInit | undefined, key: string): string | null {
  if (!headers) {
    return null;
  }
  if (headers instanceof Headers) {
    return headers.get(key);
  }
  if (Array.isArray(headers)) {
    const found = headers.find(([headerKey]) => headerKey.toLowerCase() === key.toLowerCase());
    return found ? String(found[1]) : null;
  }
  const record = headers as Record<string, unknown>;
  for (const [headerKey, value] of Object.entries(record)) {
    if (headerKey.toLowerCase() === key.toLowerCase()) {
      return value == null ? null : String(value);
    }
  }
  return null;
}

describe("chat stream resume", () => {
  beforeEach(() => {
    mockAuthorizedFetch.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("reconnects with Last-Event-ID from Content-Location", async () => {
    const firstResponse = buildSseResponse(
      [
        'id: evt-1',
        'data: {"type":"thread_id","thread_id":"thread-1"}',
        "",
        'id: evt-2',
        'data: {"type":"content","content":"hello "}',
        "",
      ].join("\n"),
      { "Content-Location": "/api/threads/thread-1/runs/run-1" }
    );
    const secondResponse = buildSseResponse(
      [
        'id: evt-3',
        'data: {"type":"content","content":"world"}',
        "",
        'id: evt-4',
        'data: {"type":"done"}',
        "",
      ].join("\n")
    );

    mockAuthorizedFetch
      .mockResolvedValueOnce(firstResponse)
      .mockResolvedValueOnce(secondResponse);

    vi.spyOn(globalThis, "setTimeout").mockImplementation(
      ((fn: (...args: unknown[]) => void) => {
        fn();
        return 0 as unknown as ReturnType<typeof setTimeout>;
      }) as typeof setTimeout
    );

    const chunks: string[] = [];
    const threadIds: string[] = [];

    const outcome = await streamThread(
      {
        request_id: "request-reconnect",
        message: "hello",
        thread_id: "thread-1",
      },
      {
        onContent: (content) => chunks.push(content),
        onThreadId: (threadId) => threadIds.push(threadId),
      },
    ).completion;
    if (outcome.status !== "completed") {
      throw new Error(`unexpected stream outcome: ${outcome.status}`);
    }

    expect(chunks).toEqual(["hello ", "world"]);
    expect(threadIds).toEqual(["thread-1"]);

    expect(mockAuthorizedFetch).toHaveBeenCalledTimes(2);
    expect(mockAuthorizedFetch.mock.calls[0]?.[0]).toBe(
      "/api/threads/thread-1/runs/stream"
    );
    const firstRequest = mockAuthorizedFetch.mock.calls[0]?.[1] as
      | RequestInit
      | undefined;
    const firstBody =
      typeof firstRequest?.body === "string"
        ? JSON.parse(firstRequest.body)
        : null;
    expect(firstBody?.on_disconnect).toBe("continue");
    expect(firstBody?.multitask_strategy).toBe("interrupt");
    expect(mockAuthorizedFetch.mock.calls[1]?.[0]).toBe(
      "/api/threads/thread-1/runs/run-1/stream"
    );

    const secondRequest = mockAuthorizedFetch.mock.calls[1]?.[1] as
      | RequestInit
      | undefined;
    expect(secondRequest?.method).toBe("GET");
    expect(readHeaderValue(secondRequest?.headers, "Last-Event-ID")).toBe("evt-2");
  });

  it("falls back to metadata run_id when Content-Location is missing", async () => {
    const firstResponse = buildSseResponse(
      [
        "event: metadata",
        'id: evt-1',
        'data: {"run_id":"run-meta","thread_id":"thread-1"}',
        "",
        'id: evt-2',
        'data: {"type":"content","content":"hello "}',
        "",
      ].join("\n")
    );
    const secondResponse = buildSseResponse(
      ['id: evt-3', 'data: {"type":"done"}', ""].join("\n")
    );

    mockAuthorizedFetch
      .mockResolvedValueOnce(firstResponse)
      .mockResolvedValueOnce(secondResponse);

    vi.spyOn(globalThis, "setTimeout").mockImplementation(
      ((fn: (...args: unknown[]) => void) => {
        fn();
        return 0 as unknown as ReturnType<typeof setTimeout>;
      }) as typeof setTimeout
    );

    const outcome = await streamThread(
      {
        request_id: "request-metadata",
        message: "hello",
        thread_id: "thread-1",
      },
      { onContent: () => {} },
    ).completion;
    expect(outcome.status).toBe("completed");

    expect(mockAuthorizedFetch.mock.calls[1]?.[0]).toBe(
      "/api/threads/thread-1/runs/run-meta/stream"
    );
    const secondRequest = mockAuthorizedFetch.mock.calls[1]?.[1] as
      | RequestInit
      | undefined;
    expect(secondRequest?.method).toBe("GET");
    expect(readHeaderValue(secondRequest?.headers, "Last-Event-ID")).toBe("evt-2");
  });

  it("best-effort cancels active run on manual abort", async () => {
    const encoder = new TextEncoder();
    const liveResponse = new Response(
      new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(encoder.encode([
            "event: metadata",
            'data: {"run_id":"run-live","thread_id":"thread-1"}',
            "",
            'data: {"type":"content","content":"hello"}',
            "",
          ].join("\n")));
        },
      }),
      { status: 200 },
    );
    mockAuthorizedFetch
      .mockResolvedValueOnce(liveResponse)
      .mockResolvedValueOnce(new Response("", { status: 202 }));

    const handle = streamThread(
      {
        request_id: "request-cancel",
        message: "hello",
        thread_id: "thread-1",
      },
      { onContent: () => {} },
    );

    await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
    await handle.stop();
    await expect(handle.completion).resolves.toEqual({ status: "cancelled" });

    expect(mockAuthorizedFetch.mock.calls[1]?.[0]).toBe(
      "/api/threads/thread-1/runs/run-live/cancel?action=interrupt"
    );
    const cancelRequest = mockAuthorizedFetch.mock.calls[1]?.[1] as
      | RequestInit
      | undefined;
    expect(cancelRequest?.method).toBe("POST");
  });

  it("treats SSE end event as terminal and does not reconnect", async () => {
    const response = buildSseResponse(
      [
        "event: metadata",
        'data: {"run_id":"run-end","thread_id":"thread-1"}',
        "",
        "event: content",
        'data: {"type":"content","content":"done"}',
        "",
        "event: end",
        "data: null",
        "",
      ].join("\n"),
      { "Content-Location": "/api/threads/thread-1/runs/run-end/stream" }
    );

    mockAuthorizedFetch.mockResolvedValueOnce(response);

    const chunks: string[] = [];
    const errors: string[] = [];
    let doneCount = 0;

    const outcome = await streamThread(
      {
        request_id: "request-end",
        message: "hello",
        thread_id: "thread-1",
      },
      { onContent: (content) => chunks.push(content) },
    ).completion;
    if (outcome.status === "failed") errors.push(outcome.error);
    if (outcome.status === "completed") doneCount += 1;

    expect(chunks).toEqual(["done"]);
    expect(errors).toEqual([]);
    expect(doneCount).toBe(1);
    expect(mockAuthorizedFetch).toHaveBeenCalledTimes(1);
  });
});
