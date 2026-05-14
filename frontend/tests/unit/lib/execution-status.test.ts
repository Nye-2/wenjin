import { describe, expect, it } from "vitest";

import {
  ACTIVE_EXECUTION_STATUSES,
  TERMINAL_TASK_STATUSES,
} from "@/lib/execution-status";

describe("execution status helpers", () => {
  it("treats record lifecycle active states as active", () => {
    expect(ACTIVE_EXECUTION_STATUSES.has("pending")).toBe(true);
    expect(ACTIVE_EXECUTION_STATUSES.has("running")).toBe(true);
    expect(ACTIVE_EXECUTION_STATUSES.has("cancelling")).toBe(true);
    expect(ACTIVE_EXECUTION_STATUSES.has("awaiting_user_input")).toBe(true);
  });

  it("keeps task terminal statuses separate from execution active statuses", () => {
    expect(TERMINAL_TASK_STATUSES.has("success")).toBe(true);
    expect(TERMINAL_TASK_STATUSES.has("failed")).toBe(true);
    expect(TERMINAL_TASK_STATUSES.has("cancelled")).toBe(true);
    expect(TERMINAL_TASK_STATUSES.has("running")).toBe(false);
  });
});
