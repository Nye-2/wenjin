import { test, expect } from "@playwright/test";

/**
 * V2 Deep Research Flow E2E tests.
 *
 * Tests the v2 workspace layout rendering and basic interactions
 * using Playwright page mocks to simulate API responses (no real backend needed).
 */

// Cookie value matching proxy.ts readAuthCookie() expectations
const AUTH_COOKIE = JSON.stringify({
  state: { isAuthenticated: true },
});

test.describe("V2 Deep Research Flow", () => {
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

    // Mock all workspace-related API calls made by the layout's useEffect.
    // The layout calls loadWorkspace, fetchFeatures, fetchSkills, fetchArtifacts,
    // fetchActivity, hydrateCompute — all go through the apiClient at localhost:8001/api.

    // Mock workspace GET
    await page.route("**/api/workspaces/ws-1", async (route) => {
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
    });

    // Mock workspace features
    await page.route("**/api/workspaces/ws-1/features*/**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ features: [] }),
      });
    });

    // Mock workspace skills
    await page.route("**/api/workspaces/ws-1/skills*/**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ skills: [] }),
      });
    });

    // Mock workspace artifacts
    await page.route("**/api/workspaces/ws-1/artifacts*/**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ artifacts: [] }),
      });
    });

    // Mock workspace activity
    await page.route("**/api/workspaces/ws-1/activity*/**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ activity: [] }),
      });
    });

    // Mock compute sessions
    await page.route("**/api/workspaces/ws-1/compute*/**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ sessions: [] }),
      });
    });

    // Catch-all for other API calls to avoid unhandled route errors
    await page.route("**/api/**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
    });

    // Navigate to v2 workspace
    await page.goto("/workspaces/ws-1/v2");
    await page.waitForLoadState("networkidle");
  });

  test("renders v2 workspace layout", async ({ page }) => {
    // Verify the 3 primary zones of the v2 layout
    await expect(page.getByTestId("chat-panel")).toBeVisible();
    await expect(page.getByTestId("workflow-panel")).toBeVisible();
    await expect(page.getByTestId("rooms-topbar")).toBeVisible();
  });

  test("shows empty state when no execution", async ({ page }) => {
    // Without any execution data, the workflow panel shows empty state
    await expect(page.getByText("No active execution")).toBeVisible();
  });

  test("renders chat input placeholder", async ({ page }) => {
    await expect(page.getByPlaceholder("输入消息...")).toBeVisible();
  });

  test("renders room buttons in topbar", async ({ page }) => {
    // 8 room buttons: Library, Documents, Decisions, Memory, Runs, Tasks, Sandbox, Settings
    const buttons = page.locator('[data-testid="rooms-topbar"] button');
    await expect(buttons).toHaveCount(8);
  });

  test("topbar room buttons are clickable", async ({ page }) => {
    // Click Library button (first) — should not crash
    await page.locator('[data-testid="rooms-topbar"] button').first().click();
    // Verify layout remains intact after interaction
    await expect(page.getByTestId("chat-panel")).toBeVisible();
    await expect(page.getByTestId("workflow-panel")).toBeVisible();
  });

  test("chat input is disabled in current state", async ({ page }) => {
    const input = page.getByPlaceholder("输入消息...");
    await expect(input).toBeDisabled();
  });

  test("topbar displays workspace label", async ({ page }) => {
    // Scope to the rooms-topbar to avoid matching other "Workspace" text on the page
    await expect(
      page.getByTestId("rooms-topbar").getByText("Workspace"),
    ).toBeVisible();
  });
});
