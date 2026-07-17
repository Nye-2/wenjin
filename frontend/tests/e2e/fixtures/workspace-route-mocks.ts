import type { BrowserContext, Page, Route } from "@playwright/test";

const AUTH_STORAGE_VALUE = JSON.stringify({
  state: {
    user: null,
    accessToken: null,
    refreshToken: null,
    isAuthenticated: true,
    isLoading: false,
    error: null,
  },
  version: 0,
});

type WorkspaceMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  blocks: Array<Record<string, unknown>>;
  created_at?: string;
  metadata?: Record<string, unknown>;
};

type MockOptions = {
  workspaceId?: string;
  workspaceName?: string;
  workspaceType?: string;
  models?: Array<Record<string, unknown>>;
  libraryItems?: Array<Record<string, unknown>>;
  missions?: Array<Record<string, unknown>>;
  missionViews?: Record<string, Record<string, unknown>>;
  missionItems?: Record<string, Array<Record<string, unknown>>>;
  missionReviewPreviews?: Record<string, { bodyBase64: string; mimeType: string }>;
  missionEventBodies?: string[];
  prismReview?: {
    projectId?: string;
    logicalKey?: string;
    path?: string;
    reason?: string;
  };
  thread?: {
    id: string;
    messages: WorkspaceMessage[];
  };
  runStreamBody?: string;
  runStreamBodies?: string[];
  onRunStream?: (payload: Record<string, unknown>) => void;
};

function json(body: unknown) {
  return {
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  };
}


export function buildEventStreamBody(
  frames: Array<{ event: string; data: unknown }>,
): string {
  const lines: string[] = [];
  for (const frame of frames) {
    lines.push(`event: ${frame.event}`);
    lines.push(`data: ${JSON.stringify(frame.data)}`);
    lines.push("");
  }
  lines.push("event: end");
  lines.push("data: null");
  lines.push("");
  return lines.join("\n");
}

export async function installWorkspaceRouteMocks(
  page: Page,
  _context: BrowserContext,
  options: MockOptions = {},
): Promise<void> {
  const workspaceId = options.workspaceId ?? "ws-1";
  const workspaceName = options.workspaceName ?? "Mock Workspace";
  const workspaceType = options.workspaceType ?? "sci";
  const models = options.models ?? [
    {
      name: "gpt-5.6-sol",
      display_name: "GPT-5.6 Sol (Default)",
      category: "chat",
      provider: "openai-compatible",
      max_tokens: 128000,
      generation_api: "chat_completions",
      capability_profile_version: "2026-07-11",
      strict_tool_calls: true,
      streaming: true,
      reasoning_efforts: ["low", "medium", "high", "xhigh"],
      vision: true,
      native_web_search: false,
      is_default: true,
    },
  ];
  const libraryItems = options.libraryItems ?? [];
  const missions = options.missions ?? [];
  const missionViews = structuredClone(options.missionViews ?? {});
  const missionItems = options.missionItems ?? {};
  const missionReviewPreviews = options.missionReviewPreviews ?? {};
  const missionEventBodies = options.missionEventBodies ?? [""];
  let missionEventCallCount = 0;
  const thread = options.thread ?? { id: "thread-1", messages: [] };
  let runStreamCallCount = 0;
  const prismReview = options.prismReview;
  const prismProjectId = prismReview?.projectId ?? "latex-1";
  const prismLogicalKey = prismReview?.logicalKey ?? "section:introduction";
  const prismPath = prismReview?.path ?? "main.tex";
  const prismReason = prismReview?.reason ?? "feature_proposal";

  const savedPrismFiles = [
    {
      id: "saved-doc-1",
      path: "docs/论文框架大纲.md",
      content: "# 论文框架大纲\n\n## 方法\n- 系统设计\n\n## 研究方法\n- 对比实验",
      size_bytes: 256,
    },
    {
      id: "saved-doc-2",
      path: "docs/结构大纲.md",
      content: "# 结构大纲\n\n## 实验设计\n- 变量控制",
      size_bytes: 192,
    },
  ];

  function prismWorkspaceFile(file: {
    id: string;
    path: string;
    size_bytes?: number;
  }) {
    return {
      id: file.id,
      workspace_id: workspaceId,
      document_id: "prism-doc-main",
      path: file.path,
      file_role: "document",
      mime_type: "text/markdown",
      current_version_id: `${file.id}-v1`,
      content_hash: `${file.id}-hash`,
      sort_order: file.id === "saved-doc-1" ? 10 : 20,
      metadata_json: {},
      deleted_at: null,
      created_at: "2026-05-19T00:00:00Z",
      updated_at: "2026-05-19T00:00:00Z",
    };
  }

  function prismReviewItems() {
    if (!prismReview) {
      return [];
    }
    return [
      {
        id: prismLogicalKey,
        kind: "prism_file_change",
        logical_key: prismLogicalKey,
        status: "pending",
        title: prismPath,
        summary: prismReason,
        target: {
          kind: "prism_file_change",
          file_path: prismPath,
        },
        actions: [
          { action: "preview_prism_change", label: "预览 diff" },
          { action: "apply_prism_change", label: "应用到 Prism" },
          { action: "reject_prism_change", label: "忽略并保护" },
        ],
      },
    ];
  }

  await page.addInitScript(
    ({ storageKey, storageValue }) => {
      window.localStorage.setItem(storageKey, storageValue);
    },
    {
      storageKey: "auth-storage",
      storageValue: AUTH_STORAGE_VALUE,
    },
  );

  await page.route("**/api/**", async (route: Route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());

    if (pathname === "/api/models") {
      await route.fulfill(json({ models }));
      return;
    }

    if (pathname === `/api/workspaces/${workspaceId}`) {
      await route.fulfill(
        json({
          id: workspaceId,
          name: workspaceName,
          type: workspaceType,
          created_at: "2026-05-18T00:00:00Z",
          updated_at: "2026-05-18T00:00:00Z",
        }),
      );
      return;
    }

    if (pathname === `/api/workspaces/${workspaceId}/artifacts`) {
      await route.fulfill(json({ artifacts: [], count: 0 }));
      return;
    }

    if (pathname === `/api/workspaces/${workspaceId}/activity`) {
      await route.fulfill(json({ items: [], count: 0 }));
      return;
    }

    if (pathname === `/api/workspaces/${workspaceId}/references`) {
      await route.fulfill(json({ items: [], count: 0 }));
      return;
    }

    if (
      pathname === `/api/workspaces/${workspaceId}/library` &&
      request.method() === "GET"
    ) {
      await route.fulfill(json({ items: libraryItems, count: libraryItems.length }));
      return;
    }

    const libraryDetailMatch = pathname.match(
      new RegExp(`^/api/workspaces/${workspaceId}/library/([^/]+)$`),
    );
    if (libraryDetailMatch && request.method() === "GET") {
      const item = libraryItems.find(
        (candidate) =>
          String(candidate.id ?? candidate.source_id ?? "") === libraryDetailMatch[1],
      );
      await route.fulfill(json(item ?? { id: libraryDetailMatch[1], title: "未命名文献" }));
      return;
    }

    if (libraryDetailMatch && request.method() === "DELETE") {
      await route.fulfill(json({ ok: true }));
      return;
    }

    if (pathname === `/api/workspaces/${workspaceId}/compute/sessions`) {
      await route.fulfill(json({ items: [], count: 0 }));
      return;
    }

    if (pathname === `/api/workspaces/${workspaceId}/missions`) {
      await route.fulfill(json({ items: missions, next_cursor: null }));
      return;
    }

    if (pathname === `/api/workspaces/${workspaceId}/missions/summary`) {
      const statusCounts = missions.reduce<Record<string, number>>((counts, mission) => {
        const status = String(mission.status ?? "created");
        counts[status] = (counts[status] ?? 0) + 1;
        return counts;
      }, {});
      const active = missions.find((mission) => ["created", "planning", "running", "waiting"].includes(String(mission.status ?? ""))) ?? null;
      await route.fulfill(json({
        total: missions.length,
        status_counts: statusCounts,
        pending_review_count: missions.reduce((sum, mission) => sum + Number(mission.pending_review_count ?? 0), 0),
        evidence_count: missions.reduce((sum, mission) => sum + Number(mission.evidence_count ?? 0), 0),
        artifact_count: missions.reduce((sum, mission) => sum + Number(mission.artifact_count ?? 0), 0),
        latest: missions[0] ?? null,
        active,
      }));
      return;
    }

    if (pathname === `/api/workspaces/${workspaceId}/missions/events`) {
      const body =
        missionEventBodies[
          Math.min(missionEventCallCount, missionEventBodies.length - 1)
        ] ?? "";
      missionEventCallCount += 1;
      await route.fulfill({ status: 200, contentType: "text/event-stream", body });
      return;
    }

    const missionReviewMatch = pathname.match(
      /^\/api\/missions\/([^/]+)\/review-decisions$/,
    );

    const missionReviewPreviewMatch = pathname.match(
      /^\/api\/missions\/([^/]+)\/review-items\/([^/]+)\/preview$/,
    );
    if (missionReviewPreviewMatch && request.method() === "GET") {
      const reviewItemId = decodeURIComponent(missionReviewPreviewMatch[2]);
      const preview = missionReviewPreviews[reviewItemId];
      if (!preview) {
        await route.fulfill({ status: 404, body: "Preview not found" });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: preview.mimeType,
        body: Buffer.from(preview.bodyBase64, "base64"),
      });
      return;
    }
    if (missionReviewMatch && request.method() === "POST") {
      const id = decodeURIComponent(missionReviewMatch[1]);
      const current = missionViews[id];
      if (!current) {
        await route.fulfill({ status: 404, body: "Mission not found" });
        return;
      }
      const payload = request.postDataJSON() as {
        decisions?: Array<{ review_item_id: string; action: string }>;
      };
      const decisions = new Map(
        (payload.decisions ?? []).map((decision) => [
          decision.review_item_id,
          decision.action,
        ]),
      );
      const reviewItems = Array.isArray(current.review_items)
        ? (current.review_items as Array<Record<string, unknown>>)
        : [];
      for (const item of reviewItems) {
        const action = decisions.get(String(item.review_item_id));
        if (action) {
          item.status = action === "accept" ? "accepted" : action;
          item.commit_eligible = action === "accept";
          item.commit_block_reason = action === "accept"
            ? null
            : "review_item_not_accepted";
        }
      }
      const reviewSummary = (current.review_summary ?? {}) as Record<string, unknown>;
      reviewSummary.pending = reviewItems.filter((item) => item.status === "pending").length;
      reviewSummary.accepted = reviewItems.filter((item) => item.status === "accepted").length;
      reviewSummary.needs_more_evidence = reviewItems.filter(
        (item) => item.status === "needs_more_evidence",
      ).length;
      await route.fulfill(json({
        outcomes: [...decisions].map(([reviewItemId]) => ({
          review_item_id: reviewItemId,
          applied: true,
        })),
      }));
      return;
    }

    const missionCommitMatch = pathname.match(
      /^\/api\/missions\/([^/]+)\/commits$/,
    );
    if (missionCommitMatch && request.method() === "POST") {
      const id = decodeURIComponent(missionCommitMatch[1]);
      const current = missionViews[id];
      if (!current) {
        await route.fulfill({ status: 404, body: "Mission not found" });
        return;
      }
      const payload = request.postDataJSON() as { review_item_ids?: string[] };
      const selected = new Set(payload.review_item_ids ?? []);
      const reviewItems = Array.isArray(current?.review_items)
        ? (current.review_items as Array<Record<string, unknown>>)
        : [];
      for (const item of reviewItems) {
        if (selected.has(String(item.review_item_id))) {
          item.status = "committed";
          item.commit_status = "committed";
          item.commit_eligible = false;
          item.commit_block_reason = "already_committed";
        }
      }
      const reviewSummary = (current.review_summary ?? {}) as Record<string, unknown>;
      reviewSummary.accepted = reviewItems.filter((item) => item.status === "accepted").length;
      reviewSummary.committed = reviewItems.filter((item) => item.status === "committed").length;
      const commitSummary = (current.commit_summary ?? {}) as Record<string, unknown>;
      commitSummary.committed = selected.size;
      await route.fulfill(json({
        outcomes: [...selected].map((reviewItemId) => ({
          review_item_id: reviewItemId,
          committed: true,
        })),
      }));
      return;
    }

    const missionActionMatch = pathname.match(/^\/api\/missions\/([^/]+)\/actions$/);
    if (missionActionMatch && request.method() === "POST") {
      const id = decodeURIComponent(missionActionMatch[1]);
      const payload = request.postDataJSON() as { review_mode?: string };
      const mission = missionViews[id]?.mission as Record<string, unknown> | undefined;
      if (mission && payload.review_mode) mission.review_mode = payload.review_mode;
      await route.fulfill(json({ ok: true }));
      return;
    }

    const missionItemMatch = pathname.match(/^\/api\/missions\/([^/]+)\/items$/);
    if (missionItemMatch) {
      const id = decodeURIComponent(missionItemMatch[1]);
      await route.fulfill(json({ items: missionItems[id] ?? [], next_cursor: null }));
      return;
    }

    const missionMatch = pathname.match(/^\/api\/missions\/([^/]+)$/);
    if (missionMatch) {
      const id = decodeURIComponent(missionMatch[1]);
      await route.fulfill(json(missionViews[id] ?? {}));
      return;
    }

    if (pathname === `/api/workspaces/${workspaceId}/prism`) {
      await route.fulfill(
        json({
          workspace_id: workspaceId,
          prism_project_id: "prism-project-1",
          prism_document_id: "prism-doc-main",
          prism_files: savedPrismFiles.map(prismWorkspaceFile),
          latex_project_id: prismProjectId,
          surface_role: "primary_manuscript",
          url: `/workspaces/${workspaceId}/prism`,
          main_file: "main.tex",
          compile_status: null,
          has_pending_changes: prismReviewItems().length > 0,
          target_files: ["main.tex"],
          review_items: prismReviewItems(),
          source_links: [],
          protected_sections: [],
          decisions: [],
          memory_preferences: [],
          recent_activity: [],
          review_summary: {
            pending_count: prismReviewItems().length,
            applied_count: 0,
            source_link_count: 0,
            protected_section_count: 0,
          },
          context_summary: {
            decision_count: 0,
            memory_preference_count: 0,
            recent_activity_count: 0,
          },
        }),
      );
      return;
    }

    const prismFile = savedPrismFiles.find(
      (file) =>
        pathname === `/api/workspaces/${workspaceId}/prism/files/${file.id}`,
    );
    if (prismFile) {
      const file = prismWorkspaceFile(prismFile);
      await route.fulfill(
        json({
          file,
          current_version: {
            id: `${prismFile.id}-v1`,
            workspace_id: workspaceId,
            file_id: prismFile.id,
            version_no: 1,
            review_item_id: null,
            content_inline: prismFile.content,
            content_asset_id: null,
            content_hash: file.content_hash,
            created_by: "mission:mission-1",
            created_at: "2026-05-19T00:00:00Z",
            updated_at: "2026-05-19T00:00:00Z",
          },
        }),
      );
      return;
    }

    if (pathname === `/api/workspaces/${workspaceId}/events`) {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: ": connected\n\n",
      });
      return;
    }

    if (
      pathname === `/api/workspaces/${workspaceId}/thread` &&
      request.method() === "POST"
    ) {
      await route.fulfill(
        json({
          id: thread.id,
          workspace_id: workspaceId,
          model: "mock-model",
          messages: thread.messages,
          created_at: "2026-05-18T00:00:00Z",
          updated_at: "2026-05-18T00:00:00Z",
        }),
      );
      return;
    }

    if (
      pathname === `/api/threads/${thread.id}/runs/stream` &&
      request.method() === "POST"
    ) {
      if (options.onRunStream) {
        options.onRunStream(
          JSON.parse(request.postData() || "{}") as Record<string, unknown>,
        );
      }
      const runStreamBody =
        options.runStreamBodies?.[runStreamCallCount] ??
        options.runStreamBody ??
        buildEventStreamBody([]);
      runStreamCallCount += 1;
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: runStreamBody,
      });
      return;
    }

    await route.fulfill(json({}));
  });
}
