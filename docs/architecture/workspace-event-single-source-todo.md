# Workspace Event Single Source TODO

## Objective

Make the workspace event line stable and monotonic:

- `workspace activity` reads from durable domain records, not process memory.
- SSE becomes an incremental projection of the same canonical payloads.
- frontend stores reject stale snapshots and preserve monotonic state.

## Serial Work Plan

- [x] Extract canonical activity payload builders into `backend/src/services/workspace_activity_contracts.py`.
- [x] Add durable `SubagentTaskRecord` storage and Alembic migration.
- [x] Switch workspace activity aggregation to read subagent history from the database.
- [x] Publish canonical `task.updated` activity on `mark_task_started()`.
- [x] Publish canonical running activity snapshots from `ProgressTracker.update()`.
- [x] Add frontend monotonic upsert guards for `WorkspaceActivityItem` and `ThreadSummary`.

## Review Gates

- [x] Review event payload shape parity between `/workspaces/{id}/activity` and SSE payloads.
- [x] Review subagent lifecycle to ensure `running/completed/failed/cancelled/timed_out` status fidelity is preserved.
- [x] Review frontend incremental write path to ensure stale events cannot overwrite newer state.
- [ ] Continue decomposing oversized frontend API surface after the event line remains stable across more end-to-end verification.
