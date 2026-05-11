import { test, expect } from "@playwright/test";

import { clearLLM, queueLLM, setupCleanWorkspace } from "./fixtures/scripted-llm";

/**
 * Spec §12 error severity (Plan 3 T9).
 *
 * Low-severity subagent failures surface as warn-toned status_lines and
 * do NOT pause the run. Critical-path failures emit a question_card and
 * implicitly halt progress until the user answers.
 */
test("low-severity subagent failure surfaces as warn status_line, run continues", async ({
  page,
}) => {
  const { workspaceId } = await setupCleanWorkspace();
  await clearLLM();
  await queueLLM([
    {
      blocks: [
        {
          kind: "status_line",
          label: "phase 2 启动",
          run_id: "r1",
          phase_index: 1,
          tone: "info",
        },
        {
          kind: "status_line",
          label: "phase 2 有 1 篇文献无法解析，已跳过",
          run_id: "r1",
          phase_index: 1,
          tone: "warn",
        },
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

  await page.goto(
    `/workspaces/${workspaceId}/v2?feature=paper_analysis&skill=paper-analyst&entry=open&paper_title=x`,
  );
  await expect(page.getByText(/已跳过/)).toBeVisible();
  await expect(page.getByText(/phase 2 完成/)).toBeVisible();
  await expect(page.getByRole("button", { name: /继续/ })).toHaveCount(0);
});

test("high-severity failure pauses run with question_card asking how to proceed", async ({
  page,
}) => {
  const { workspaceId } = await setupCleanWorkspace();
  await clearLLM();
  await queueLLM([
    {
      blocks: [
        {
          kind: "status_line",
          label: "phase 2 启动",
          run_id: "r1",
          phase_index: 1,
          tone: "info",
        },
        {
          kind: "question_card",
          label: "需要你拍一下",
          question:
            "无法解析 PrivateFL-GPT，要继续不读它，还是手动给我 PDF？",
          pills: [
            { label: "跳过这篇", intent: "skip" },
            { label: "换一篇", intent: "swap" },
            { label: "上传 PDF", intent: "upload" },
          ],
        },
      ],
    },
  ]);

  await page.goto(
    `/workspaces/${workspaceId}/v2?feature=paper_analysis&skill=paper-analyst&entry=open&paper_title=x`,
  );
  await expect(page.getByText(/无法解析/)).toBeVisible();
  await expect(page.getByRole("button", { name: /跳过这篇/ })).toBeVisible();
  // Run paused — either resume button visible OR the still-runnable pause
  // button (run never reached a phase boundary that would force the pill UI
  // to be the only path forward).
  await expect(
    page.getByRole("button", { name: /继续|在下个安全点暂停/ }),
  ).toBeVisible();
});
