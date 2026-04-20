import { describe, expect, it } from "vitest";

import type { ThreadSummary, WorkspaceActivityItem } from "@/lib/api/types";
import {
  shouldReplaceThreadSummary,
  shouldReplaceWorkspaceActivity,
  upsertThreadSummaryList,
  upsertWorkspaceActivityList,
} from "@/lib/workspace-event-ordering";

function activity(overrides: Partial<WorkspaceActivityItem> = {}): WorkspaceActivityItem {
  return {
    id: overrides.id ?? "a1",
    kind: overrides.kind ?? "feature_task",
    occurred_at: overrides.occurred_at ?? "2026-04-13T10:00:00Z",
    title: overrides.title ?? "activity",
    status: overrides.status ?? "pending",
    metadata: overrides.metadata,
  };
}

function thread(overrides: Partial<ThreadSummary> = {}): ThreadSummary {
  return {
    id: overrides.id ?? "t1",
    model: overrides.model ?? "gpt",
    created_at: overrides.created_at ?? "2026-04-13T09:00:00Z",
    updated_at: overrides.updated_at ?? "2026-04-13T10:00:00Z",
    message_count: overrides.message_count ?? 1,
    ...overrides,
  };
}

describe("workspace-event-ordering", () => {
  it("prefers newer activity timestamps", () => {
    const existing = activity({ occurred_at: "2026-04-13T10:00:00Z" });
    const older = activity({ occurred_at: "2026-04-13T09:59:00Z" });
    const newer = activity({ occurred_at: "2026-04-13T10:01:00Z" });

    expect(shouldReplaceWorkspaceActivity(existing, older)).toBe(false);
    expect(shouldReplaceWorkspaceActivity(existing, newer)).toBe(true);
  });

  it("uses status/progress rank when timestamps tie", () => {
    const existing = activity({
      status: "running",
      metadata: { progress: 30 },
    });
    const completed = activity({
      status: "completed",
      metadata: { progress: 30 },
    });
    const progressed = activity({
      status: "running",
      metadata: { progress: 60 },
    });

    expect(shouldReplaceWorkspaceActivity(existing, completed)).toBe(true);
    expect(shouldReplaceWorkspaceActivity(existing, progressed)).toBe(true);
  });

  it("upserts and keeps latest activities within limit", () => {
    const items = [
      activity({ id: "a1", occurred_at: "2026-04-13T09:00:00Z" }),
      activity({ id: "a2", occurred_at: "2026-04-13T08:00:00Z" }),
    ];
    const incoming = activity({ id: "a3", occurred_at: "2026-04-13T10:00:00Z" });

    const result = upsertWorkspaceActivityList(items, incoming, 2);
    expect(result).toHaveLength(2);
    expect(result[0].id).toBe("a3");
    expect(result[1].id).toBe("a1");
  });

  it("rejects older thread summaries and prefers larger message count on ties", () => {
    const existing = thread({
      updated_at: "2026-04-13T10:00:00Z",
      message_count: 5,
    });
    const older = thread({
      updated_at: "2026-04-13T09:59:59Z",
      message_count: 99,
    });
    const sameTimeMoreMessages = thread({
      updated_at: "2026-04-13T10:00:00Z",
      message_count: 6,
    });

    expect(shouldReplaceThreadSummary(existing, older)).toBe(false);
    expect(shouldReplaceThreadSummary(existing, sameTimeMoreMessages)).toBe(true);
  });

  it("upserts threads by id and sorts latest first", () => {
    const threads = [
      thread({ id: "t1", updated_at: "2026-04-13T10:00:00Z" }),
      thread({ id: "t2", updated_at: "2026-04-13T09:00:00Z" }),
    ];
    const incoming = thread({ id: "t2", updated_at: "2026-04-13T11:00:00Z" });

    const result = upsertThreadSummaryList(threads, incoming);
    expect(result[0].id).toBe("t2");
    expect(result[1].id).toBe("t1");
  });
});
