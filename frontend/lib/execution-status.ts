/**
 * Canonical execution session lifecycle statuses.
 *
 * Keep in sync with backend ExecutionSessionStatus
 * (src/database/models/execution_session.py).
 */
export const ExecutionSessionStatus = {
  LAUNCHING: "launching",
  PENDING: "pending",
  RUNNING: "running",
  AWAITING_USER_INPUT: "awaiting_user_input",
  COMPLETED: "completed",
  FAILED: "failed",
  CANCELLED: "cancelled",
  ADVISORY: "advisory",
} as const;

export type ExecutionSessionStatusValue =
  (typeof ExecutionSessionStatus)[keyof typeof ExecutionSessionStatus];

/** Statuses that indicate an active execution (visible in status bar). */
export const ACTIVE_EXECUTION_STATUSES: ReadonlySet<ExecutionSessionStatusValue> =
  new Set([
    ExecutionSessionStatus.LAUNCHING,
    ExecutionSessionStatus.RUNNING,
    ExecutionSessionStatus.PENDING,
    ExecutionSessionStatus.AWAITING_USER_INPUT,
  ]);

/** Terminal statuses that trigger a full hydration refresh. */
export const TERMINAL_TASK_STATUSES: ReadonlySet<string> = new Set([
  "success",
  "failed",
  "cancelled",
]);
