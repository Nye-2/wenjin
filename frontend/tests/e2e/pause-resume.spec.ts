import { expect, test } from "@playwright/test";

import { installWorkspaceRouteMocks } from "./fixtures/workspace-route-mocks";

test("entry=resume restores history without auto-launching a new run", async ({
  page,
  context,
}) => {
  let runStreamCalls = 0;

  await installWorkspaceRouteMocks(page, context, {
    onRunStream: () => {
      runStreamCalls += 1;
    },
    thread: {
      id: "thread-1",
      messages: [
        {
          id: "assistant-1",
          role: "assistant",
          blocks: [
            {
              kind: "text",
              content: "上一轮已经完成初步分析，这里是历史记录。",
            },
          ],
          created_at: "2026-05-18T00:00:00Z",
        },
      ],
    },
  });

  await page.goto(
    "/workspaces/ws-1?feature=paper_analysis&skill=paper-analyst&entry=resume&paper_title=x",
  );

  await expect(page.getByText(/上一轮已经完成初步分析/)).toBeVisible();
  await expect
    .poll(() => runStreamCalls)
    .toBe(0);
});
