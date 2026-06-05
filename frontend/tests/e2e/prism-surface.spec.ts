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
      pendingContent:
        "\\documentclass{article}\\begin{document}Mobile Prism manuscript\\end{document}",
    },
  });

  await page.goto("/workspaces/ws-1/prism?focus=file_changes");

  await expect(page.getByRole("tab", { name: "Workbench" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Prism" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(
    page.getByRole("button", { name: "AI 改稿", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("dialog", { name: "AI 改稿" })).toBeVisible();
  await expect(page.getByText("待确认写入")).toBeVisible();
  await expect(page.getByRole("button", { name: "编辑", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "对照", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "审阅", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "专注", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "打开 PDF 对照" })).toBeVisible();
  await expect(page.locator(".monaco-editor")).toBeVisible();
  await expect
    .poll(() =>
      page
        .locator(".monaco-editor")
        .evaluate((element) => element.getBoundingClientRect().height),
    )
    .toBeGreaterThan(240);

  expect(requestedPaths).toContain("/api/workspaces/ws-1/events");
  expect(
    requestedPaths.filter((path) =>
      /\/api\/workspaces\/ws-1\/(documents|library|tasks|memory|decisions|runs|settings)/.test(
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
