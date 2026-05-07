import { test, expect } from "@playwright/test";

import { clearLLM, queueLLM, setupCleanWorkspace } from "./fixtures/scripted-llm";

/**
 * Spec §12 pause / resume / cancel (Plan 3 T8).
 *
 * Pause sends an interrupt; the chat shows a status_line confirming the
 * pause and the right-panel button toggles to "继续". Resume re-queues the
 * next agent message. Cancel terminates the run and returns to idle
 * composer state.
 */
test("pause stops at next phase boundary; resume continues", async ({ page }) => {
  const { workspaceId } = await setupCleanWorkspace();
  await clearLLM();
  await queueLLM([
    {
      blocks: [
        { kind: "text", content: "开始" },
        {
          kind: "status_line",
          label: "phase 1 启动",
          run_id: "r1",
          phase_index: 0,
          tone: "info",
        },
      ],
    },
    {
      blocks: [
        {
          kind: "status_line",
          label: "phase 1 完成",
          run_id: "r1",
          phase_index: 1,
          tone: "info",
        },
      ],
    },
  ]);

  await page.goto(
    `/workspaces/${workspaceId}/chat?feature=paper_analysis&skill=paper-analyst&entry=open&paper_title=x`,
  );
  await expect(page.getByText(/phase 1 启动/)).toBeVisible();

  await page.getByRole("button", { name: /在下个安全点暂停/ }).click();
  await expect(page.getByRole("button", { name: /继续/ })).toBeVisible();

  await queueLLM([
    {
      blocks: [
        {
          kind: "status_line",
          label: "phase 2 完成",
          run_id: "r1",
          phase_index: 2,
          tone: "info",
        },
      ],
    },
  ]);
  await page.getByRole("button", { name: /继续/ }).click();
  await expect(page.getByText(/phase 2 完成/)).toBeVisible({ timeout: 5000 });
});

test("cancel mid-run stops execution and returns to idle composer", async ({ page }) => {
  const { workspaceId } = await setupCleanWorkspace();
  await clearLLM();
  await queueLLM([
    {
      blocks: [
        { kind: "text", content: "正在跑" },
        {
          kind: "status_line",
          label: "phase 1 启动",
          run_id: "r1",
          phase_index: 0,
          tone: "info",
        },
      ],
    },
  ]);

  await page.goto(
    `/workspaces/${workspaceId}/chat?feature=paper_analysis&skill=paper-analyst&entry=open&paper_title=x`,
  );
  await expect(page.getByText(/正在跑/)).toBeVisible();
  await page.getByRole("button", { name: /中断当前任务/ }).click();
  await expect(page.getByRole("button", { name: /中断当前任务/ })).toHaveCount(0);
});
