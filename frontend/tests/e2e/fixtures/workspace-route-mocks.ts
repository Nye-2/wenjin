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
  missionEventBodies?: string[];
  prismReview?: {
    projectId?: string;
    logicalKey?: string;
    path?: string;
    reason?: string;
    initialContent?: string;
    pendingContent?: string;
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
      name: "gpt-5.5",
      display_name: "GPT-5.5 (Default)",
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
  const missionEventBodies = options.missionEventBodies ?? [""];
  let missionEventCallCount = 0;
  const thread = options.thread ?? { id: "thread-1", messages: [] };
  let runStreamCallCount = 0;
  const prismReview = options.prismReview;
  const prismProjectId = prismReview?.projectId ?? "latex-1";
  const prismLogicalKey = prismReview?.logicalKey ?? "section:introduction";
  const prismPath = prismReview?.path ?? "main.tex";
  const prismReason = prismReview?.reason ?? "feature_proposal";
  const prismInitialContent =
    prismReview?.initialContent ??
    "\\documentclass{article}\\begin{document}Workspace manuscript\\end{document}";
  const prismPendingContent =
    prismReview?.pendingContent ??
    "\\documentclass{article}\\begin{document}Generated workspace manuscript\\end{document}";
  let prismContent = prismInitialContent;
  let prismApplied = false;
  let prismProtected = false;

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

  function prismFileChanges() {
    if (!prismReview || prismApplied) {
      return [];
    }
    return [
      {
        logical_key: prismLogicalKey,
        path: prismPath,
        reason: prismReason,
        pending_content: prismPendingContent,
        current_hash: "current-hash",
        pending_hash: "pending-hash",
      },
    ];
  }

  function prismAppliedFileChanges() {
    if (!prismReview || !prismApplied) {
      return {};
    }
    return {
      [prismLogicalKey]: {
        logical_key: prismLogicalKey,
        path: prismPath,
        previous_hash: "current-hash",
        applied_hash: "pending-hash",
        revert_signature: "b".repeat(64),
      },
    };
  }

  function latexProjectPayload() {
    return {
      id: prismProjectId,
      user_id: "user-1",
      name: "Workspace Manuscript",
      template_id: null,
      main_file: "main.tex",
      tags: [],
      archived: false,
      trashed: false,
      trashed_at: null,
      file_order: {},
      workspace_id: workspaceId,
      surface_role: "primary_manuscript",
      llm_config: {
        workspace_id: workspaceId,
        bridge: "workspace_latex_project",
        metadata: {},
      },
      created_at: "2026-05-18T00:00:00Z",
      updated_at: "2026-05-18T00:00:00Z",
    };
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
        if (action) item.status = action === "accept" ? "accepted" : action;
      }
      const reviewSummary = (current.review_summary ?? {}) as Record<string, unknown>;
      reviewSummary.pending = reviewItems.filter((item) => item.status === "pending").length;
      reviewSummary.accepted = reviewItems.filter((item) => item.status === "accepted").length;
      reviewSummary.needs_more_evidence = reviewItems.filter(
        (item) => item.status === "needs_more_evidence",
      ).length;
      await route.fulfill(json({ ok: true }));
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
        if (selected.has(String(item.review_item_id))) item.status = "committed";
      }
      current.commits = [...selected].map((reviewItemId) => ({
        review_item_id: reviewItemId,
        status: "committed",
      }));
      const reviewSummary = (current.review_summary ?? {}) as Record<string, unknown>;
      reviewSummary.accepted = reviewItems.filter((item) => item.status === "accepted").length;
      reviewSummary.committed = reviewItems.filter((item) => item.status === "committed").length;
      const commitSummary = (current.commit_summary ?? {}) as Record<string, unknown>;
      commitSummary.committed = selected.size;
      await route.fulfill(json({ ok: true }));
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
          has_pending_changes: prismFileChanges().length > 0,
          target_files: ["main.tex"],
          file_changes: prismFileChanges(),
          applied_file_changes: Object.values(prismAppliedFileChanges()),
          review_items: prismFileChanges().map((change) => ({
            id: change.logical_key,
            kind: "prism_file_change",
            logical_key: change.logical_key,
            status: "pending",
            title: change.path,
            summary: change.reason ?? null,
            target: {
              kind: "prism_file_change",
              file_path: change.path,
            },
            actions: [
              { action: "preview_prism_change", label: "预览 diff" },
              { action: "apply_prism_change", label: "应用到 Prism" },
              { action: "reject_prism_change", label: "忽略并保护" },
            ],
          })),
          source_links: [],
          protected_sections: prismProtected
            ? [
                {
                  id: "protected-current-file",
                  workspace_id: workspaceId,
                  latex_project_id: prismProjectId,
                  file_path: prismPath,
                  section_key: "",
                  scope: "file",
                  reason: "user_manual_protect",
                  source: "manual_edit",
                  updated_at: "2026-05-18T00:04:00Z",
                },
              ]
            : [],
          decisions: [],
          memory_preferences: [],
          recent_activity: [
            ...(prismApplied
              ? [
                  {
                    id: `prism_review:${prismLogicalKey}`,
                    kind: "prism_review",
                    workspace_id: workspaceId,
                    title: `已写入稿件修改: ${prismPath}`,
                    summary: prismReason,
                    status: "applied",
                    occurred_at: "2026-05-18T00:03:00Z",
                    metadata: {
                      latex_project_id: prismProjectId,
                      review_item_id: prismLogicalKey,
                      logical_key: prismLogicalKey,
                      target_file_path: prismPath,
                    },
                  },
                ]
              : []),
            ...(prismProtected
              ? [
                  {
                    id: "prism_review:manual-protect",
                    kind: "prism_review",
                    workspace_id: workspaceId,
                    title: `已保护稿件文件: ${prismPath}`,
                    summary: "user_manual_protect",
                    status: "protected",
                    occurred_at: "2026-05-18T00:04:00Z",
                    metadata: {
                      latex_project_id: prismProjectId,
                      target_file_path: prismPath,
                    },
                  },
                ]
              : []),
          ],
          review_summary: {
            pending_count: prismFileChanges().length,
            applied_count: Object.values(prismAppliedFileChanges()).length,
            source_link_count: 0,
            protected_section_count: prismProtected ? 1 : 0,
          },
          context_summary: {
            decision_count: 0,
            memory_preference_count: 0,
            recent_activity_count: (prismApplied ? 1 : 0) + (prismProtected ? 1 : 0),
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
          skill: "paper-analyst",
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

    if (pathname === `/api/prism/latex-adapter/projects/${prismProjectId}`) {
      await route.fulfill(json(latexProjectPayload()));
      return;
    }

    if (pathname === `/api/prism/latex-adapter/projects/${prismProjectId}/tree`) {
      await route.fulfill(
        json({
          items: [{ path: prismPath, type: "file" }],
          file_order: {},
        }),
      );
      return;
    }

    if (pathname === `/api/prism/latex-adapter/projects/${prismProjectId}/file`) {
      await route.fulfill(
        json({
          content: prismContent,
        }),
      );
      return;
    }

    if (pathname === `/api/prism/latex-adapter/projects/${prismProjectId}/feedback`) {
      await route.fulfill(json({ items: [] }));
      return;
    }

    if (
      pathname === `/api/prism/latex-adapter/projects/${prismProjectId}/file-changes/preview` &&
      request.method() === "POST"
    ) {
      await route.fulfill(
        json({
          ok: true,
          logical_key: prismLogicalKey,
          path: prismPath,
          reason: prismReason,
          current_hash: "current-hash",
          pending_hash: "pending-hash",
          change_signature: "a".repeat(64),
          diff: {
            hunks: [
              {
                old_start: 0,
                old_end: prismInitialContent.length,
                new_start: 0,
                new_end: prismPendingContent.length,
                ops: [
                  {
                    op: "replace",
                    old_text: prismInitialContent,
                    new_text: prismPendingContent,
                    old_start: 0,
                    old_end: prismInitialContent.length,
                    new_start: 0,
                    new_end: prismPendingContent.length,
                    token_kind: "text",
                  },
                ],
              },
            ],
            stats: {
              chars_added: Math.max(
                prismPendingContent.length - prismInitialContent.length,
                0,
              ),
              chars_deleted: Math.max(
                prismInitialContent.length - prismPendingContent.length,
                0,
              ),
              tokens_changed: 1,
              citation_changed: 0,
              label_changed: 0,
            },
            risk_flags: [],
          },
        }),
      );
      return;
    }

    if (
      pathname === `/api/prism/latex-adapter/projects/${prismProjectId}/file-changes/apply` &&
      request.method() === "POST"
    ) {
      prismContent = prismPendingContent;
      prismApplied = true;
      await route.fulfill(
        json({
          ok: true,
          applied: true,
          logical_key: prismLogicalKey,
          path: prismPath,
          file_hash: "pending-hash",
          undo: {
            logical_key: prismLogicalKey,
            path: prismPath,
            previous_hash: "current-hash",
            applied_hash: "pending-hash",
            revert_signature: "b".repeat(64),
          },
        }),
      );
      return;
    }

    if (
      pathname === `/api/prism/latex-adapter/projects/${prismProjectId}/protected-sections` &&
      request.method() === "POST"
    ) {
      prismProtected = true;
      await route.fulfill(
        json({
          ok: true,
          protected: true,
          path: prismPath,
          section_key: "",
          scope: "file",
          reason: "user_manual_protect",
        }),
      );
      return;
    }

    await route.fulfill(json({}));
  });
}
