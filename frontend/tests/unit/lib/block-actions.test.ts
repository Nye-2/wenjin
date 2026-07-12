import { describe, expect, it } from "vitest";

import { buildContinueThreadBlockAction } from "@/lib/block-actions";

describe("buildContinueThreadBlockAction", () => {
  it("keeps chat-native follow-up context without feature routing", () => {
    expect(buildContinueThreadBlockAction("继续完善实验设计", "result_card")).toEqual({
      action: "continue_thread",
      intent: "继续完善实验设计",
      source_block_kind: "result_card",
    });
  });
});
