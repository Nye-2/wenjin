import type { BrowserContext, Page, Route } from "@playwright/test";

const AUTH_COOKIE = JSON.stringify({
  state: { isAuthenticated: true },
});
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
  capabilities?: Array<Record<string, unknown>>;
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
  onRunStream?: (payload: Record<string, unknown>) => void;
  onCommit?: (payload: Record<string, unknown>) => void;
  commitResponse?: unknown;
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
  context: BrowserContext,
  options: MockOptions = {},
): Promise<void> {
  const workspaceId = options.workspaceId ?? "ws-1";
  const workspaceName = options.workspaceName ?? "Mock Workspace";
  const workspaceType = options.workspaceType ?? "sci";
  const capabilities = options.capabilities ?? [
    {
      id: "paper_analysis",
      name: "论文分析",
      description: "分析论文内容与价值",
      display_name: "论文分析",
      ui_meta: { icon: "microscope" },
    },
  ];
  const thread = options.thread ?? { id: "thread-1", messages: [] };
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

  await context.addCookies([
    {
      name: "auth-storage",
      value: encodeURIComponent(AUTH_COOKIE),
      domain: "localhost",
      path: "/",
    },
  ]);
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
    const { pathname, searchParams } = new URL(request.url());

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

    if (pathname === `/api/workspaces/${workspaceId}/capabilities`) {
      await route.fulfill(json({ features: capabilities }));
      return;
    }

    if (pathname === "/api/capabilities") {
      await route.fulfill(
        json({
          items:
            searchParams.get("workspace_type") === workspaceType
              ? capabilities.map((item) => ({
                  id: item.id,
                  display_name: item.display_name ?? item.name,
                  description: item.description ?? "",
                  ui_meta: item.ui_meta ?? {},
                }))
              : [],
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

    if (pathname === `/api/workspaces/${workspaceId}/compute/sessions`) {
      await route.fulfill(json({ items: [], count: 0 }));
      return;
    }

    if (pathname === `/api/workspaces/${workspaceId}/prism`) {
      await route.fulfill(
        json({
          workspace_id: workspaceId,
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
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: options.runStreamBody ?? buildEventStreamBody([]),
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

    if (
      pathname === "/api/executions/ex-1/commit" &&
      request.method() === "POST"
    ) {
      if (options.onCommit) {
        options.onCommit(
          JSON.parse(request.postData() || "{}") as Record<string, unknown>,
        );
      }
      await route.fulfill(json(options.commitResponse ?? { ok: true }));
      return;
    }

    await route.fulfill(json({}));
  });
}
