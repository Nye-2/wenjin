import { expect, test } from "@playwright/test";

import {
  buildEventStreamBody,
  installWorkspaceRouteMocks,
} from "./fixtures/workspace-route-mocks";

test("result cards can commit all staged outputs in one click", async ({
  page,
  context,
}) => {
  let commitPayload: Record<string, unknown> | null = null;

  await installWorkspaceRouteMocks(page, context, {
    onCommit: (payload) => {
      commitPayload = payload;
    },
    runStreamBody: buildEventStreamBody([
      {
        event: "block",
        data: {
          block: {
            kind: "result_card",
            data: {
              execution_id: "ex-1",
              capability_name: "论文分析",
              status: "completed",
              narrative: "已生成可提交的分析产物。",
              outputs: [
                {
                  id: "doc-1",
                  kind: "document",
                  preview: "论文分析报告",
                  default_checked: true,
                  data: {
                    name: "analysis.md",
                    mime_type: "text/markdown",
                    storage_path: "/tmp/analysis.md",
                    size_bytes: 128,
                    doc_kind: "draft",
                  },
                },
                {
                  id: "task-1",
                  kind: "task",
                  preview: "补充对比实验",
                  default_checked: true,
                  data: {
                    title: "补充对比实验",
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
    "/workspaces/ws-1?feature=paper_analysis&skill=paper-analyst&entry=open&paper_title=x",
  );

  await expect(page.getByText(/论文分析报告/)).toBeVisible();
  await page.getByRole("button", { name: "全部接受" }).click();

  await expect(page.getByText("已保存")).toBeVisible();
  await expect
    .poll(() => commitPayload)
    .toEqual({ accept_all: true });
});
