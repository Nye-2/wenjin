import { afterEach, describe, expect, it, vi } from "vitest";

const { authorizedFetchMock } = vi.hoisted(() => ({
  authorizedFetchMock: vi.fn(),
}));

vi.mock("@/lib/api/client", () => ({
  authorizedFetch: authorizedFetchMock,
  readErrorMessage: vi.fn(),
}));

import { subscribeMissionEvents } from "@/lib/api/missions";

describe("Mission SSE recovery", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    authorizedFetchMock.mockReset();
  });

  it("reconnects after transport failure and consumes the typed cursor event", async () => {
    vi.useFakeTimers();
    vi.spyOn(Math, "random").mockReturnValue(0);
    const frame = {
      type: "mission.updated",
      missionId: "mission-2",
      stateVersion: 3,
      lastItemSeq: 2,
      cursor: "cursor-2",
    };
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(frame)}\n\n`));
      },
    });
    authorizedFetchMock
      .mockRejectedValueOnce(new Error("disconnected"))
      .mockResolvedValueOnce(new Response(stream, { status: 200 }));
    const onEvent = vi.fn();
    const onReconnect = vi.fn();
    const unsubscribe = subscribeMissionEvents({
      workspaceId: "workspace-1",
      onEvent,
      onReconnect,
    });

    await vi.waitFor(() => expect(onReconnect).toHaveBeenCalledOnce());
    await vi.advanceTimersByTimeAsync(500);
    await vi.waitFor(() => expect(onEvent).toHaveBeenCalledWith(frame));
    expect(authorizedFetchMock).toHaveBeenCalledTimes(2);
    unsubscribe();
  });
});
