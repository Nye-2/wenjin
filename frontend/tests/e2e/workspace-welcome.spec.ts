import { expect, test } from "@playwright/test";

import { installWorkspaceRouteMocks } from "./fixtures/workspace-route-mocks";

test("empty SCI workspace shows Wenjin welcome without auto-dispatching chips", async ({
  page,
  context,
}) => {
  const runPayloads: Record<string, unknown>[] = [];

  await installWorkspaceRouteMocks(page, context, {
    workspaceId: "ws-welcome-sci",
    workspaceName: "联邦学习选题",
    workspaceType: "sci",
    onRunStream: (payload) => runPayloads.push(payload),
  });

  await page.goto("/workspaces/ws-welcome-sci");

  await expect(page.getByTestId("workspace-welcome")).toContainText(
    "问津 · SCI 论文工作台",
  );
  await expect(page.getByTestId("workspace-welcome")).toContainText(
    "联邦学习选题",
  );
  await expect(page.getByTestId("workspace-welcome-chip")).toHaveCount(4);

  await page.getByRole("button", { name: "梳理研究空白" }).click();
  await expect(page.getByTestId("chat-composer-input")).toHaveValue(
    "我想先梳理研究空白和可写创新点，方向是：",
  );
  expect(runPayloads).toHaveLength(0);
});

test("math modeling welcome prompts users to upload the problem PDF", async ({
  page,
  context,
}) => {
  await installWorkspaceRouteMocks(page, context, {
    workspaceId: "ws-welcome-math",
    workspaceName: "国赛训练",
    workspaceType: "math_modeling",
  });

  await page.goto("/workspaces/ws-welcome-math");

  await expect(page.getByTestId("workspace-welcome")).toContainText(
    "问津 · 数学建模工作台",
  );
  await expect(page.getByTestId("workspace-welcome")).toContainText(
    "上传赛题 PDF",
  );
  await expect(page.getByPlaceholder("上传赛题 PDF，或描述题目、数据和你想先解决的问题...")).toBeVisible();

  const [chooser] = await Promise.all([
    page.waitForEvent("filechooser"),
    page.getByRole("button", { name: "上传赛题 PDF" }).click(),
  ]);
  expect(chooser.isMultiple()).toBe(true);
  await expect(page.getByTestId("chat-composer-input")).toHaveValue(
    "我准备上传数模赛题 PDF 和附件，请你先读题、拆解任务和数据需求。",
  );
});
