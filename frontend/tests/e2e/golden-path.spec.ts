import { test, expect } from "@playwright/test";

import { clearLLM, queueLLM, setupCleanWorkspace } from "./fixtures/scripted-llm";

/**
 * Spec §12 happy path (Plan 3 T7).
 *
 * Verifies the agent emits clean blocks (text + status_line + result_card),
 * the chat thread renders them in order, and no jargon leaks through. The
 * right-panel phase column is driven by `subagent.updated` SSE events from
 * the runtime — those aren't emitted by the scripted-LLM hook alone, so this
 * spec only asserts chat-thread state. Right-panel rendering is exercised
 * by component-level tests under tests/unit/components/live-workflow/.
 */
test("paper analysis golden path", async ({ page }) => {
  const { workspaceId } = await setupCleanWorkspace();
  await clearLLM();

  await queueLLM([
    {
      blocks: [
        { kind: "text", content: "好，方向挺新。我先去扫这个交叉的文献版图。" },
        {
          kind: "status_line",
          label: "启动 phase 1 · 检索文献",
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
          label: "phase 1 完成 · 12 篇高相关 → 启动 phase 2",
          run_id: "r1",
          phase_index: 1,
          tone: "info",
        },
      ],
    },
    {
      blocks: [
        {
          kind: "status_line",
          label: "phase 2 完成 → 启动 phase 3 · 提炼",
          run_id: "r1",
          phase_index: 2,
          tone: "info",
        },
      ],
    },
    {
      blocks: [
        {
          kind: "status_line",
          label: "正在汇总结果（约 10-20s）",
          run_id: "r1",
          tone: "info",
        },
        {
          kind: "result_card",
          run_id: "r1",
          title: "📑 论文分析 · 完成",
          tldr: "3 个角度可切，最有价值是通信效率 ↔ 隐私强度",
          findings: [
            { id: "1", text: "异构客户端缺口" },
            { id: "2", text: "联邦预训练 vs 联邦微调供需错位" },
            { id: "3", text: "trade-off 量化空白" },
          ],
          recommend: { label: "推荐切入", body: "三维 trade-off 曲线" },
          links: [{ icon: "📄", label: "详细报告", href: "#" }],
          feedback: {
            question: "这个结论你怎么看？",
            pills: [
              { kind: "primary", label: "进入选题", intent: "next" },
              { kind: "warn", label: "换方向", intent: "redirect" },
            ],
            allow_free_input: true,
          },
          stats: { duration_ms: 102000, subagents: 13, tokens: 8400 },
        },
      ],
    },
  ]);

  await page.goto(
    `/workspaces/${workspaceId}/chat?feature=paper_analysis&skill=paper-analyst&entry=open&paper_title=${encodeURIComponent("联邦学习+大模型")}`,
  );

  await expect(page.getByText(/方向挺新/)).toBeVisible();
  await expect(page.getByText(/phase 1 完成/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/phase 2 完成/)).toBeVisible();
  await expect(page.getByText(/正在汇总结果/)).toBeVisible();

  await expect(page.getByText(/3 个角度可切/)).toBeVisible();
  await expect(page.getByText(/异构客户端缺口/)).toBeVisible();
  await expect(page.getByText(/推荐切入/)).toBeVisible();
  await expect(page.getByRole("button", { name: /进入选题/ })).toBeVisible();

  // Spec §12: agent must not output jargon, debug tokens, or self-reporting.
  for (const banned of [
    "message_feature_proposal",
    "意图置信度",
    "我会先复用",
  ]) {
    await expect(page.getByText(banned)).toHaveCount(0);
  }
});
