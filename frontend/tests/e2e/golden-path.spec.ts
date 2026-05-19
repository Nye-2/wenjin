import { expect, test } from "@playwright/test";

import {
  buildEventStreamBody,
  installWorkspaceRouteMocks,
} from "./fixtures/workspace-route-mocks";

test("paper analysis auto-entry renders the current chat completion chain", async ({
  page,
  context,
}) => {
  await installWorkspaceRouteMocks(page, context, {
    runStreamBody: buildEventStreamBody([
      {
        event: "block",
        data: {
          block: {
            kind: "text",
            content: "好，方向挺新。我先去扫这个交叉的文献版图。",
          },
        },
      },
      {
        event: "block",
        data: {
          block: {
            kind: "status_line",
            label: "phase 1 完成 · 12 篇高相关 → 启动 phase 2",
            run_id: "run-1",
            tone: "info",
          },
        },
      },
      {
        event: "block",
        data: {
          block: {
            kind: "status_line",
            label: "phase 2 完成 → 启动 phase 3 · 提炼",
            run_id: "run-1",
            tone: "info",
          },
        },
      },
      {
        event: "block",
        data: {
          block: {
            kind: "result_card",
            data: {
              execution_id: "ex-1",
              capability_name: "论文分析",
              status: "completed",
              narrative: "3 个角度可切，最有价值是通信效率 ↔ 隐私强度",
              outputs: [
                {
                  id: "doc-1",
                  kind: "document",
                  preview: "异构客户端缺口",
                  default_checked: true,
                  data: {
                    name: "paper-analysis.md",
                    mime_type: "text/markdown",
                    storage_path: "/tmp/paper-analysis.md",
                    size_bytes: 256,
                    doc_kind: "draft",
                  },
                },
              ],
            },
          },
        },
      },
    ]),
  });

  await page.goto(
    `/workspaces/ws-1?feature=paper_analysis&skill=paper-analyst&entry=open&paper_title=${encodeURIComponent(
      "联邦学习+大模型",
    )}`,
  );

  await expect(page.getByText(/联邦学习\+大模型/)).toBeVisible();
  await expect(page.getByText(/方向挺新/)).toBeVisible();
  await expect(page.getByText(/phase 1 完成/)).toBeVisible();
  await expect(page.getByText(/phase 2 完成/)).toBeVisible();
  await expect(page.getByText(/3 个角度可切/)).toBeVisible();
  await expect(page.getByText(/异构客户端缺口/)).toBeVisible();
  await expect(page.getByRole("button", { name: "全部接受" })).toBeVisible();

  for (const banned of [
    "message_feature_proposal",
    "意图置信度",
    "我会先复用",
  ]) {
    await expect(page.getByText(banned)).toHaveCount(0);
  }
});
