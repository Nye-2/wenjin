import { beforeEach, describe, expect, it, vi } from "vitest";

const { authorizedFetchMock } = vi.hoisted(() => ({
  authorizedFetchMock: vi.fn(),
}));

vi.mock("@/lib/api/client", () => ({
  authorizedFetch: authorizedFetchMock,
  readErrorMessage: vi.fn(async (_response: Response, fallback: string) => fallback),
}));

import {
  getWorkspaceMissionSummary,
  getMissionView,
  listMissionArtifacts,
  listMissionEvidence,
  subscribeMissionEvents,
} from "@/lib/api/missions";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function missionViewWire() {
  return {
    mission: {
      mission_id: "mission-1",
      workspace_id: "workspace-1",
      title: "研究任务",
      status: "running",
      review_mode: "balanced_default",
      active_stage_id: null,
      pending_review_count: 0,
      evidence_count: 1,
      artifact_count: 1,
      active_subagent_count: 0,
      state_version: 42,
      last_item_seq: 7,
      created_at: "2026-07-14T00:00:00Z",
      updated_at: "2026-07-14T00:01:00Z",
    },
    activity: {
      state: "retrying",
      title: "连接暂时波动，问津正在重试",
      summary: "任务进度已经保留，无需重新开始。",
      attempt: 2,
      retry_at: "2026-07-14T00:02:00Z",
    },
    attention_request: null,
    review_summary: { pending: 0, accepted: 0, needs_more_evidence: 0, committed: 0 },
    commit_summary: { pending: 0, applying: 0, committed: 0, failed: 0 },
    review_items: [],
    commits: [],
    required_stage_ids: [],
    stage_summaries: [],
    team_summary: null,
    subagents: [],
    evidence_items: [],
    evidence_page: { total: 1, returned: 0, next_cursor: 12 },
    artifact_items: [],
    artifact_page: { total: 1, returned: 0, next_cursor: 14 },
    review_policy: {
      mode: "balanced_default",
      protected_outputs_require_confirmation: true,
      draft_outputs_may_be_automatic: true,
    },
    review_selection_revision: "4e623f1e58e841dd80c8f16a39497f95",
    quality_highlights: [],
    refresh_token: "mission-1:42:7",
  };
}

describe("Mission projection API", () => {
  beforeEach(() => {
    authorizedFetchMock.mockReset();
  });

  it("projects activity and uses the dedicated review selection revision", async () => {
    const wire = missionViewWire();
    wire.mission.artifact_count = 6;
    authorizedFetchMock.mockResolvedValueOnce(jsonResponse(wire));

    const view = await getMissionView("mission-1");

    expect(view.activity).toEqual({
      state: "retrying",
      title: "连接暂时波动，问津正在重试",
      summary: "任务进度已经保留，无需重新开始。",
      attempt: 2,
      retryAt: "2026-07-14T00:02:00Z",
    });
    expect(view.reviewSelectionRevision).toBe("4e623f1e58e841dd80c8f16a39497f95");
    expect(view.reviewSelectionRevision).not.toBe(String(view.stateVersion));
    expect(view.artifactCount).toBe(1);
  });

  it("loads evidence and artifacts only from typed projection endpoints", async () => {
    authorizedFetchMock
      .mockResolvedValueOnce(jsonResponse({
        items: [{ item_id: "ev-13", seq: 13, title: "核验证据", source_type: "paper", source_label: "期刊", summary: "已复核", citation: "cite-1", verified: true }],
        page: { total: 2, returned: 1, next_cursor: null },
      }))
      .mockResolvedValueOnce(jsonResponse({
        items: [{ item_id: "artifact-15", seq: 15, title: "研究稿", kind: "document", summary: "完整稿", preview_available: true, committed: true }],
        page: { total: 2, returned: 1, next_cursor: null },
      }));

    await expect(listMissionEvidence({ missionId: "mission-1", cursor: 12 })).resolves.toMatchObject({
      items: [{ id: "ev-13", title: "核验证据", verified: true }],
      nextCursor: null,
      total: 2,
    });
    await expect(listMissionArtifacts({ missionId: "mission-1", cursor: 14 })).resolves.toMatchObject({
      items: [{ id: "artifact-15", title: "研究稿", committed: true }],
      nextCursor: null,
      total: 2,
    });
    expect(authorizedFetchMock).toHaveBeenNthCalledWith(1, "/api/missions/mission-1/evidence?cursor=12&limit=50");
    expect(authorizedFetchMock).toHaveBeenNthCalledWith(2, "/api/missions/mission-1/artifacts?cursor=14&limit=50");
    expect(authorizedFetchMock.mock.calls.flat().join(" ")).not.toContain("/items");
  });

  it("loads workspace-wide counts from the aggregate projection", async () => {
    const run = missionViewWire().mission;
    authorizedFetchMock.mockResolvedValueOnce(jsonResponse({
      total: 132,
      status_counts: { completed: 120, running: 12 },
      pending_review_count: 7,
      evidence_count: 420,
      artifact_count: 88,
      latest: run,
      active: run,
    }));

    const summary = await getWorkspaceMissionSummary("workspace-1");

    expect(summary.total).toBe(132);
    expect(summary.statusCounts.running).toBe(12);
    expect(summary.pendingReviewCount).toBe(7);
    expect(summary.active?.missionId).toBe("mission-1");
    expect(authorizedFetchMock).toHaveBeenCalledWith(
      "/api/workspaces/workspace-1/missions/summary",
    );
  });

  it("stops the Mission SSE after a 401 response", async () => {
    authorizedFetchMock.mockResolvedValue(new Response(null, { status: 401 }));
    const onError = vi.fn();

    const unsubscribe = subscribeMissionEvents({
      workspaceId: "workspace-1",
      onEvent: vi.fn(),
      onReconnect: vi.fn(),
      onError,
    });
    await vi.waitFor(() => expect(onError).toHaveBeenCalledWith("登录状态已失效，请重新登录后刷新任务。"));
    expect(authorizedFetchMock).toHaveBeenCalledTimes(1);
    unsubscribe();
  });
});
