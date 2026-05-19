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
