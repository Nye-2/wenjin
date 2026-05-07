import { test, expect } from "@playwright/test";

import { clearLLM, queueLLM, setupCleanWorkspace } from "./fixtures/scripted-llm";

/**
 * Spec §12 feedback iteration (Plan 3 T10).
 *
 * Clicking a result_card feedback pill submits the pill's intent as a
 * follow-up user message, which kicks off a new agent run. The previous
 * run folds into a collapsed "轮 N" container so the chat doesn't grow
 * unbounded; expanding it shows the prior content again.
 */
test("clicking a result_card pill triggers new run; previous run folds", async ({
  page,
}) => {
  const { workspaceId } = await setupCleanWorkspace();
  await clearLLM();
  await queueLLM([
    {
      blocks: [
        { kind: "text", content: "开始" },
        {
          kind: "result_card",
          run_id: "r1",
          title: "📑 完成",
          tldr: "x",
          findings: [{ id: "1", text: "a" }],
          links: [],
          feedback: {
            question: "下一步？",
            pills: [
              { kind: "normal", label: "深入第 ① 点", intent: "deep-dive-1" },
            ],
            allow_free_input: true,
          },
          stats: { duration_ms: 1000, subagents: 1, tokens: 100 },
        },
      ],
    },
  ]);

  await page.goto(
    `/workspaces/${workspaceId}/chat?feature=paper_analysis&skill=paper-analyst&entry=open&paper_title=x`,
  );
  await expect(page.getByText(/x/)).toBeVisible();

  // Queue the second run BEFORE clicking the pill.
  await queueLLM([
    {
      blocks: [
        { kind: "text", content: "好，深入分析中…" },
        {
          kind: "status_line",
          label: "phase 1 启动",
          run_id: "r2",
          phase_index: 0,
          tone: "info",
        },
      ],
    },
  ]);

  await page.getByRole("button", { name: /深入第 ① 点/ }).click();

  await expect(page.getByText(/深入分析中/)).toBeVisible();

  // Old run folded — the original "开始" text bubble should not be visible
  // while the run summary chip ("轮 1") remains clickable.
  await expect(page.getByRole("button", { name: /轮 1/ })).toBeVisible();
  await expect(page.getByText(/开始/).first()).not.toBeVisible();

  await page.getByRole("button", { name: /轮 1/ }).click();
  await expect(page.getByText(/开始/)).toBeVisible();
});
