/**
 * Performance test: ensure rendering many messages does not block the main thread.
 *
 * Messages are append-only, so React.memo on MessageRow / MessageBlock should
 * prevent re-rendering old messages when new ones arrive. This test verifies
 * that a large batch of messages renders within an acceptable time budget.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import { ChatPanel } from "@/app/(workbench)/workspaces/[id]/v2/components/ChatPanel";
import { useChatStoreV2 } from "@/stores/chat-store";

describe("Render performance", () => {
  beforeEach(() => {
    useChatStoreV2.getState().reset();
  });

  it("renders 50 messages without timeout", () => {
    const { handleEvent } = useChatStoreV2.getState();

    // Generate 50 user + 50 assistant messages (100 total)
    for (let i = 0; i < 50; i++) {
      handleEvent({
        type: "chat.user.message",
        data: {
          id: `u${i}`,
          content: `Message ${i}`,
          timestamp: "2026-01-01",
        },
      });
      handleEvent({
        type: "chat.assistant.start",
        data: { message_id: `a${i}`, timestamp: "2026-01-01" },
      });
      handleEvent({
        type: "chat.assistant.block",
        block: {
          kind: "text",
          content: `Reply ${i} with some content that makes it realistic enough to test rendering performance. This is a longer message to simulate real chat.`,
        },
      });
      handleEvent({ type: "chat.assistant.completion" });
    }

    const start = performance.now();
    render(<ChatPanel workspaceId="ws-1" data-testid="chat-panel" />);
    const duration = performance.now() - start;

    // Should render within 500ms even with 100 blocks (50 user + 50 assistant)
    expect(duration).toBeLessThan(500);
    expect(useChatStoreV2.getState().messages.length).toBe(100);
  });
});
