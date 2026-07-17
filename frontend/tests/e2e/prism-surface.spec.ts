import { expect, test } from "@playwright/test";

import { installWorkspaceRouteMocks } from "./fixtures/workspace-route-mocks";

test("workspace Prism surface stays usable on mobile without extra room reloads", async ({
  page,
  context,
}) => {
  const requestedPaths: string[] = [];

  page.on("request", (request) => {
    const { pathname } = new URL(request.url());
    if (pathname.startsWith("/api/")) {
      requestedPaths.push(pathname);
    }
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await installWorkspaceRouteMocks(page, context, {
    prismReview: {
      path: "main.tex",
    },
  });

  await page.goto("/workspaces/ws-1/prism");

  await expect(page.getByRole("tab", { name: "Workbench" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Prism" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(page.getByTestId("prism-workspace-shell")).toBeVisible();
  await expect(page.getByRole("button", { name: /论文框架大纲\.md/ })).toBeVisible();
  await expect(page.getByTestId("prism-file-editor")).toBeVisible();
  await expect(page.getByTestId("prism-file-preview")).toBeVisible();
  await expect(page.getByTestId("prism-file-preview").getByText("系统设计")).toBeVisible();
  await expect
    .poll(() =>
      page
        .getByTestId("prism-file-editor")
        .evaluate((element) => element.getBoundingClientRect().height),
    )
    .toBeGreaterThan(180);

  expect(requestedPaths).toContain("/api/workspaces/ws-1/events");
  expect(
    requestedPaths.filter((path) =>
      /\/api\/workspaces\/ws-1\/(library|tasks|decisions|runs|settings)/.test(
        path,
      ),
    ),
  ).toEqual([]);
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    )
    .toBe(true);
});
