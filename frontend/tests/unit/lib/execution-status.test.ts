import { describe, expect, it } from "vitest";

import {
  ACTIVE_EXECUTION_STATUSES,
  ExecutionSessionStatus,
  TERMINAL_TASK_STATUSES,
} from "@/lib/execution-status";

describe("execution status helpers", () => {
  it("treats launching sessions as active", () => {
    expect(ACTIVE_EXECUTION_STATUSES.has(ExecutionSessionStatus.LAUNCHING)).toBe(
      true
    );
  });

  it("keeps task terminal statuses separate from execution active statuses", () => {
    expect(TERMINAL_TASK_STATUSES.has("success")).toBe(true);
    expect(TERMINAL_TASK_STATUSES.has("failed")).toBe(true);
    expect(TERMINAL_TASK_STATUSES.has("cancelled")).toBe(true);
    expect(TERMINAL_TASK_STATUSES.has("launching")).toBe(false);
  });
});
