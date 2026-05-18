import { expect, test } from "@playwright/test";

import {
  buildEventStreamBody,
  installWorkspaceRouteMocks,
} from "./fixtures/workspace-route-mocks";

test("warn status lines remain visible in the chat thread", async ({
  page,
  context,
}) => {
  await installWorkspaceRouteMocks(page, context, {
    runStreamBody: buildEventStreamBody([
      {
        event: "block",
        data: {
          block: {
            kind: "status_line",
            content: "phase 2 启动",
          },
        },
      },
      {
        event: "block",
        data: {
          block: {
            kind: "status_line",
            content: "phase 2 有 1 篇文献无法解析，已跳过",
          },
        },
      },
      {
        event: "block",
        data: {
          block: {
            kind: "status_line",
            content: "phase 2 完成",
          },
        },
      },
    ]),
  });

  await page.goto(
    "/workspaces/ws-1?feature=paper_analysis&skill=paper-analyst&entry=open&paper_title=x",
  );

  await expect(page.getByText(/已跳过/)).toBeVisible();
  await expect(page.getByText(/phase 2 完成/)).toBeVisible();
});

test("question cards render focused blocking questions in the current UI", async ({
  page,
  context,
}) => {
  await installWorkspaceRouteMocks(page, context, {
    runStreamBody: buildEventStreamBody([
      {
        event: "block",
        data: {
          block: {
            kind: "question_card",
            data: {
              question: "无法解析 PrivateFL-GPT，要继续不读它，还是手动给我 PDF？",
            },
          },
        },
      },
    ]),
  });

  await page.goto(
    "/workspaces/ws-1?feature=paper_analysis&skill=paper-analyst&entry=open&paper_title=x",
  );

  await expect(page.getByText(/无法解析 PrivateFL-GPT/)).toBeVisible();
});
