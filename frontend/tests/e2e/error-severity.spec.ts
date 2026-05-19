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
            label: "phase 2 启动",
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
            label: "phase 2 有 1 篇文献无法解析，已跳过",
            run_id: "run-1",
            tone: "warn",
          },
        },
      },
      {
        event: "block",
        data: {
          block: {
            kind: "status_line",
            label: "phase 2 完成",
            run_id: "run-1",
            tone: "info",
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
            label: "需要你拍一下",
            question: "无法解析 PrivateFL-GPT，要继续不读它，还是手动给我 PDF？",
            pills: [],
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

test("question card actions preserve execution linkage when continuing a run", async ({
  page,
  context,
}) => {
  let runPayload: Record<string, unknown> | null = null;

  await installWorkspaceRouteMocks(page, context, {
    thread: {
      id: "thread-1",
      messages: [
        {
          id: "m-1",
          role: "assistant",
          metadata: {
            orchestration: {
              execution_id: "exec-123",
            },
          },
          blocks: [
            {
              kind: "question_card",
              label: "需要你拍一下",
              question: "无法解析 PrivateFL-GPT，要继续不读它，还是手动给我 PDF？",
              pills: [{ label: "跳过", intent: "skip_this_paper" }],
            },
          ],
        },
      ],
    },
    onRunStream: (payload) => {
      runPayload = payload;
    },
    runStreamBody: buildEventStreamBody([]),
  });

  await page.goto("/workspaces/ws-1");

  await page.getByRole("button", { name: "跳过" }).click();

  await expect
    .poll(() => runPayload)
    .toMatchObject({
      message: "skip_this_paper",
      metadata: {
        block_action: {
          action: "continue_thread",
          intent: "skip_this_paper",
          source_block_kind: "question_card",
        },
        orchestration: {
          execution_id: "exec-123",
        },
      },
    });
});
