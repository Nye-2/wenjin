import type { ExecutionStatus } from "@/lib/api/types";

export const ACTIVE_EXECUTION_STATUSES: ReadonlySet<ExecutionStatus> = new Set([
  "pending",
  "running",
  "cancelling",
  "awaiting_user_input",
]);

export const TERMINAL_EXECUTION_STATUSES: ReadonlySet<ExecutionStatus> = new Set([
  "completed",
  "failed_partial",
  "failed",
  "cancelled",
]);

export const TERMINAL_TASK_STATUSES: ReadonlySet<string> = new Set([
  "success",
  "failed",
  "cancelled",
]);
