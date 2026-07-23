import { beforeEach, describe, expect, it, vi } from "vitest";

const { authorizedFetchMock } = vi.hoisted(() => ({
  authorizedFetchMock: vi.fn(),
}));

vi.mock("@/lib/api/client", () => ({
  authorizedFetch: authorizedFetchMock,
  readErrorMessage: vi.fn(async (_response: Response, fallback: string) => fallback),
}));

import {
  commitMissionReviews,
  decideMissionReviews,
  getWorkspaceMissionSummary,
  getMissionView,
  listMissionArtifacts,
  listMissionEvidence,
  listMissionReviews,
  resolveMissionPermission,
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
      last_progress_at: "2026-07-14T00:01:00Z",
      heartbeat_at: "2026-07-14T00:01:00Z",
    },
    current_operation: null,
    input_summary: { total: 2, ready: 2, failed: 0, names: ["题目.pdf", "附件.xlsx"] },
    failure: null,
    attention_request: null,
    review_summary: { pending: 0, accepted: 0, needs_more_evidence: 0, committed: 0 },
    commit_summary: { pending: 0, applying: 0, committed: 0, failed: 0 },
    review_items: [{
      review_item_id: "review-1",
      mission_id: "mission-1",
      target_kind: "claim",
      title: "核心论断",
      risk_level: "high",
      status: "pending",
      requires_explicit_review: true,
      batch_acceptable: true,
      suggested_selected: false,
      commit_status: null,
      commit_eligible: false,
      commit_block_reason: "review_item_not_accepted",
    }],
    review_page: {
      total: 1,
      returned: 1,
      next_cursor: null,
      revision: "review-revision-42",
    },
    required_stage_ids: [],
    stage_summaries: [],
    team_summary: null,
    subagents: [],
    evidence_items: [],
    evidence_page: { total: 1, returned: 0, next_cursor: 12 },
    artifact_items: [],
    artifact_page: { total: 1, returned: 0, next_cursor: 14, revision: "artifact-revision-42" },
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

  it("resolves Mission permission decisions through the dedicated endpoint", async () => {
    authorizedFetchMock.mockResolvedValueOnce(jsonResponse({ resumed: true }));

    await resolveMissionPermission({
      missionId: "mission-1",
      requestId: "permission/1",
      decision: "allow_for_mission",
    });

    expect(authorizedFetchMock).toHaveBeenCalledWith(
      "/api/missions/mission-1/permissions/permission%2F1/resolve",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ decision: "allow_for_mission", input_json: {} }),
      }),
    );
  });

  it("projects activity and uses the dedicated review selection revision", async () => {
    const wire = missionViewWire();
    wire.mission.artifact_count = 6;
    wire.mission.evidence_count = 9;
    wire.evidence_page.total = 1;
    wire.artifact_page.total = 1;
    authorizedFetchMock.mockResolvedValueOnce(jsonResponse(wire));

    const view = await getMissionView("mission-1");

    expect(view.activity).toEqual({
      state: "retrying",
      title: "连接暂时波动，问津正在重试",
      summary: "任务进度已经保留，无需重新开始。",
      attempt: 2,
      retryAt: "2026-07-14T00:02:00Z",
      lastProgressAt: "2026-07-14T00:01:00Z",
      heartbeatAt: "2026-07-14T00:01:00Z",
    });
    expect(view.inputSummary.ready).toBe(2);
    expect(view.reviewSelectionRevision).toBe("4e623f1e58e841dd80c8f16a39497f95");
    expect(view.reviewSelectionRevision).not.toBe(String(view.stateVersion));
    expect(view.artifactRevision).toBe("artifact-revision-42");
    expect(view.reviewRevision).toBe("review-revision-42");
    expect(view.artifactCount).toBe(1);
    expect(view.evidenceCount).toBe(1);
    expect(view.reviewItems[0]).toMatchObject({
      requiresExplicitReview: true,
      batchAcceptable: true,
      suggestedSelected: false,
      commitEligible: false,
      commitBlockReason: "review_item_not_accepted",
    });
  });

  it("projects confirmed worker milestones from the Mission ledger", async () => {
    const wire = {
      ...missionViewWire(),
      team_summary: "1 位研究成员正在推进，已有 1 条可查看进展。",
      subagents: [{
        subagent_id: "worker-1",
        display_name: "优化建模员",
        role_label: "负责求解模型",
        status: "working",
        summary: "已确认功率平衡约束",
        updated_at: "2026-07-14T00:01:30Z",
        milestones: [{
          kind: "formula",
          summary: "已确认逐时功率平衡方程",
          created_at: "2026-07-14T00:01:20Z",
        }],
      }],
    };
    authorizedFetchMock.mockResolvedValueOnce(jsonResponse(wire));

    const view = await getMissionView("mission-1");

    expect(view.teamSummary).toBe("1 位研究成员正在推进，已有 1 条可查看进展。");
    expect(view.subagents[0]).toMatchObject({
      id: "worker-1",
      status: "working",
      milestones: [{ kind: "formula", summary: "已确认逐时功率平衡方程" }],
    });
  });

  it("omits the removed bulk field from review decision requests", async () => {
    authorizedFetchMock
      .mockResolvedValueOnce(jsonResponse({
        outcomes: [
          { review_item_id: "review-1", applied: true },
          { review_item_id: "review-2", applied: true },
        ],
      }));

    await decideMissionReviews({
      missionId: "mission-1",
      decisions: [
        { reviewItemId: "review-1", decision: "accepted" },
        { reviewItemId: "review-2", decision: "needs_more_evidence" },
      ],
    });

    const request = authorizedFetchMock.mock.calls[0][1] as RequestInit;
    const payload = JSON.parse(String(request.body)) as Record<string, unknown>;
    expect(payload).not.toHaveProperty("bulk");
    expect(payload.decisions).toEqual([
      { review_item_id: "review-1", action: "accept" },
      { review_item_id: "review-2", action: "needs_more_evidence" },
    ]);
    expect(payload.decision_id).toMatch(/^review-[0-9a-f]{40}$/);
  });

  it("derives stable idempotency keys for repeated review and commit intents", async () => {
    authorizedFetchMock
      .mockResolvedValueOnce(jsonResponse({ outcomes: [] }))
      .mockResolvedValueOnce(jsonResponse({ outcomes: [] }))
      .mockResolvedValueOnce(jsonResponse({ outcomes: [] }))
      .mockResolvedValueOnce(jsonResponse({ outcomes: [] }));

    const decisions = [{ reviewItemId: "review-1", decision: "accepted" as const }];
    await decideMissionReviews({ missionId: "mission-1", decisions });
    await decideMissionReviews({ missionId: "mission-1", decisions });
    await commitMissionReviews({
      missionId: "mission-1",
      reviewItemIds: ["review-2", "review-1"],
    });
    await commitMissionReviews({
      missionId: "mission-1",
      reviewItemIds: ["review-1", "review-2"],
    });

    const payloads = authorizedFetchMock.mock.calls.map((call) =>
      JSON.parse(String((call[1] as RequestInit).body)) as Record<string, unknown>
    );
    expect(payloads[0].decision_id).toBe(payloads[1].decision_id);
    expect(payloads[2].request_id).toBe(payloads[3].request_id);
    expect(payloads[2].request_id).toMatch(/^commit-[0-9a-f]{40}$/);
    expect(payloads[2].review_item_ids).toEqual(["review-1", "review-2"]);
  });

  it("follows the continuation Mission returned by terminal review feedback", async () => {
    authorizedFetchMock.mockResolvedValueOnce(jsonResponse({
      outcomes: [{ review_item_id: "review-1", applied: true }],
      continuation_mission_id: "mission-child-1",
    }));

    const result = await decideMissionReviews({
      missionId: "mission-1",
      decisions: [{ reviewItemId: "review-1", decision: "needs_more_evidence" }],
    });

    expect(result.targetMissionId).toBe("mission-child-1");
    expect(authorizedFetchMock).toHaveBeenCalledTimes(1);
  });

  it("surfaces a continuation failure without losing the parent Mission view", async () => {
    authorizedFetchMock.mockResolvedValueOnce(jsonResponse({
      outcomes: [{ review_item_id: "review-1", applied: true }],
      continuation_error_code: "continuation_policy_changed",
    }));

    const result = await decideMissionReviews({
      missionId: "mission-1",
      decisions: [{ reviewItemId: "review-1", decision: "needs_more_evidence" }],
    });

    expect(result.targetMissionId).toBe("mission-1");
    expect(result.issueCodes).toContain("continuation_policy_changed");
    expect(authorizedFetchMock).toHaveBeenCalledTimes(1);
  });

  it("loads evidence and artifacts only from typed projection endpoints", async () => {
    authorizedFetchMock
      .mockResolvedValueOnce(jsonResponse({
        items: [{ item_id: "ev-13", seq: 13, title: "核验证据", source_type: "paper", source_label: "期刊", summary: "已复核", citation: "cite-1", verified: true }],
        page: { total: 2, returned: 1, next_cursor: null },
      }))
      .mockResolvedValueOnce(jsonResponse({
        items: [{ item_id: "artifact-15", seq: 15, title: "研究稿", kind: "document", summary: "完整稿", preview_available: true, preview_expires_at: "2026-07-14T01:00:00Z", committed: true }],
        page: { total: 2, returned: 1, next_cursor: 15, next_tiebreaker: "review-15", revision: "artifact-revision-43" },
      }));

    await expect(listMissionEvidence({ missionId: "mission-1", cursor: 12 })).resolves.toMatchObject({
      items: [{ id: "ev-13", title: "核验证据", verified: true }],
      nextCursor: null,
      total: 2,
    });
    await expect(listMissionArtifacts({ missionId: "mission-1", cursor: 14, tiebreaker: "review-14" })).resolves.toMatchObject({
      items: [{ id: "artifact-15", title: "研究稿", previewExpiresAt: "2026-07-14T01:00:00Z", committed: true }],
      nextCursor: 15,
      nextTiebreaker: "review-15",
      total: 2,
      revision: "artifact-revision-43",
    });
    expect(authorizedFetchMock).toHaveBeenNthCalledWith(1, "/api/missions/mission-1/evidence?cursor=12&limit=50");
    expect(authorizedFetchMock).toHaveBeenNthCalledWith(2, "/api/missions/mission-1/artifacts?cursor=14&limit=50&tiebreaker=review-14");
    expect(authorizedFetchMock.mock.calls.flat().join(" ")).not.toContain("/items");
  });

  it("loads paged review projections with commit eligibility", async () => {
    authorizedFetchMock.mockResolvedValueOnce(jsonResponse({
      items: [{
        review_item_id: "review-51",
        mission_id: "mission-1",
        target_kind: "document",
        title: "第 51 项成果",
        risk_level: "medium",
        status: "accepted",
        preview_json: { body: "draft" },
        preview_url: null,
        preview_expires_at: "2026-07-14T01:00:00Z",
        requires_explicit_review: false,
        batch_acceptable: true,
        suggested_selected: false,
        commit_status: null,
        commit_eligible: true,
      }],
      page: { total: 51, returned: 1, next_cursor: null },
    }));

    await expect(listMissionReviews({ missionId: "mission-1", cursor: "page-2" })).resolves.toMatchObject({
      items: [{ id: "review-51", commitEligible: true, previewExpiresAt: "2026-07-14T01:00:00Z" }],
      nextCursor: null,
      total: 51,
    });
    expect(authorizedFetchMock).toHaveBeenCalledWith(
      "/api/missions/mission-1/review-items?cursor=page-2&limit=50",
    );
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
      event_cursor: "summary-cursor",
    }));

    const summary = await getWorkspaceMissionSummary("workspace-1");

    expect(summary.total).toBe(132);
    expect(summary.statusCounts.running).toBe(12);
    expect(summary.pendingReviewCount).toBe(7);
    expect(summary.active?.missionId).toBe("mission-1");
    expect(summary.eventCursor).toBe("summary-cursor");
    expect(authorizedFetchMock).toHaveBeenCalledWith(
      "/api/workspaces/workspace-1/missions/summary",
    );
  });

  it("deduplicates concurrent workspace summary reads without caching them", async () => {
    const run = missionViewWire().mission;
    authorizedFetchMock.mockImplementation(async () =>
      jsonResponse({
        total: 1,
        status_counts: { running: 1 },
        pending_review_count: 0,
        evidence_count: 1,
        artifact_count: 1,
        latest: run,
        active: run,
        event_cursor: "summary-cursor",
      }),
    );

    const [first, second] = await Promise.all([
      getWorkspaceMissionSummary("workspace-1"),
      getWorkspaceMissionSummary("workspace-1"),
    ]);

    expect(first).toEqual(second);
    expect(authorizedFetchMock).toHaveBeenCalledTimes(1);

    await getWorkspaceMissionSummary("workspace-1");
    expect(authorizedFetchMock).toHaveBeenCalledTimes(2);
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
