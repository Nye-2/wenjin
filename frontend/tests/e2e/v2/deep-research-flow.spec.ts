import { test, expect } from "@playwright/test";

/**
 * Workspace Deep Research Flow E2E tests.
 *
 * Tests the v2 workspace layout rendering and basic interactions
 * using Playwright page mocks to simulate API responses (no real backend needed).
 */

// Cookie value matching proxy.ts readAuthCookie() expectations
const AUTH_COOKIE = JSON.stringify({
  state: { isAuthenticated: true },
});

test.describe("Workspace Deep Research Flow", () => {
  test.beforeEach(async ({ page, context }) => {
    // Set auth cookie so the proxy middleware lets us through
    await context.addCookies([
      {
        name: "auth-storage",
        value: encodeURIComponent(AUTH_COOKIE),
        domain: "localhost",
        path: "/",
      },
    ]);

    // Mock the workspace shell APIs in one handler so specific room responses
    // are not shadowed by the generic catch-all route.
    await page.route("**/api/**", async (route) => {
      const { pathname } = new URL(route.request().url());

      if (pathname === "/api/workspaces/ws-1") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: "ws-1",
            name: "Test Workspace",
            type: "thesis",
            created_at: "2025-01-01T00:00:00Z",
          }),
        });
        return;
      }

      if (pathname === "/api/workspaces/ws-1/library") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ items: [], count: 0 }),
        });
        return;
      }

      if (pathname.startsWith("/api/workspaces/ws-1/features")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ features: [] }),
        });
        return;
      }

      if (pathname.startsWith("/api/workspaces/ws-1/skills")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ skills: [] }),
        });
        return;
      }

      if (pathname.startsWith("/api/workspaces/ws-1/artifacts")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ artifacts: [] }),
        });
        return;
      }

      if (pathname.startsWith("/api/workspaces/ws-1/activity")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ activity: [] }),
        });
        return;
      }

      if (pathname.startsWith("/api/workspaces/ws-1/compute")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ sessions: [] }),
        });
        return;
      }

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
    });

    // Navigate to the canonical workspace route
    await page.goto("/workspaces/ws-1");
    await page.waitForLoadState("networkidle");
  });

  test("renders workspace layout", async ({ page }) => {
    // Verify the 3 primary zones of the workspace layout
    await expect(page.getByTestId("chat-panel")).toBeVisible();
    await expect(page.getByTestId("workflow-panel")).toBeVisible();
    await expect(page.getByTestId("rooms-topbar")).toBeVisible();
  });

  test("shows empty state when no execution", async ({ page }) => {
    await expect(
      page.getByText("当前还没有进行中的工作面。先在对话里描述任务，问津会创建并打开对应工作面。"),
    ).toBeVisible();
    await expect(page.getByText("等待新的工作")).toBeVisible();
  });

  test("renders chat input placeholder", async ({ page }) => {
    await expect(page.getByPlaceholder("输入消息...")).toBeVisible();
  });

  test("renders room buttons in topbar", async ({ page }) => {
    // 7 user-facing room buttons: Library, Documents, Decisions, Memory, Runs, Tasks, Settings
    const buttons = page.locator('[data-testid="rooms-topbar"] button');
    await expect(buttons).toHaveCount(7);
    await expect(page.getByRole("button", { name: "Sandbox" })).toHaveCount(0);
  });

  test("topbar room buttons are clickable", async ({ page }) => {
    // Click Library button (first) — should open the drawer without crashing
    await page.locator('[data-testid="rooms-topbar"] button').first().click();
    await expect(page.getByTestId("library-drawer")).toBeVisible();
    await expect(page.getByTestId("drawer-empty")).toBeVisible();
  });

  test("chat input is enabled in current state", async ({ page }) => {
    const input = page.getByPlaceholder("输入消息...");
    await expect(input).toBeEnabled();
  });

  test("topbar displays workspace label", async ({ page }) => {
    // Scope to the rooms-topbar to avoid matching other "Workspace" text on the page
    await expect(
      page.getByTestId("rooms-topbar").getByText("Workspace"),
    ).toBeVisible();
  });

  test("sandbox room deep link is ignored", async ({ page }) => {
    await page.goto("/workspaces/ws-1?room=sandbox");
    await page.waitForLoadState("networkidle");

    await expect(page.getByTestId("settings-page")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Sandbox" })).toHaveCount(0);
  });
});
