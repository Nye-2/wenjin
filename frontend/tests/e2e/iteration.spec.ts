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
    commitResponse: {
      committed: { documents: 1, tasks: 1 },
      room_targets: {
        documents: [{ output_id: "doc-1", item_id: "saved-doc-1" }],
        library: [],
      },
    },
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

  await page.getByRole("button", { name: "查看结果" }).click();
  await expect(
    page.getByRole("button", { name: /论文分析报告/ }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "保存到工作区" }).click();

  await expect(page.getByText("已保存到工作区")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "打开已保存的 论文分析报告" }),
  ).toBeVisible();
  await expect
    .poll(() => commitPayload)
    .toEqual({ accept_all: true });
});

test("Prism review links open the workspace surface before committing room outputs", async ({
  page,
  context,
}) => {
  let commitPayload: Record<string, unknown> | null = null;
  const workbenchUrl =
    "/workspaces/ws-1?feature=paper_analysis&skill=paper-analyst&entry=open&paper_title=x";

  await installWorkspaceRouteMocks(page, context, {
    prismReview: {
      projectId: "latex-1",
      logicalKey: "section:introduction",
      path: "main.tex",
      reason: "feature_proposal",
      initialContent:
        "\\documentclass{article}\\begin{document}Workspace manuscript\\end{document}",
      pendingContent:
        "\\documentclass{article}\\begin{document}Generated workspace manuscript\\end{document}",
    },
    commitResponse: {
      committed: { documents: 1 },
      room_targets: {
        documents: [{ output_id: "doc-1", item_id: "saved-doc-1" }],
        library: [],
      },
    },
    onCommit: (payload) => {
      commitPayload = payload;
    },
    runStreamBody: buildEventStreamBody([
      {
        event: "block",
        data: {
          block: {
            kind: "result_card",
            run_id: "run-prism",
            title: "主稿写入待确认",
            tldr: "章节写作已进入 Prism 待确认区。",
            findings: [],
            recommend: null,
            links: [
              {
                icon: "sparkles",
                label: "预览待确认修改",
                href: "/workspaces/ws-1/prism?focus=file_changes&review_item_id=section%3Aintroduction&logical_key=section%3Aintroduction",
              },
            ],
            feedback: {
              question: "是否继续？",
              pills: [],
              allow_free_input: true,
            },
            stats: { duration_ms: 1200, subagents: 1, tokens: 320 },
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
              capability_name: "章节写作",
              status: "completed",
              narrative: "已生成可保存到工作区的章节摘要。",
              review_items: [
                {
                  id: "section:introduction",
                  kind: "prism_file_change",
                  logical_key: "section:introduction",
                  status: "pending",
                  title: "main.tex",
                  summary: "feature_proposal",
                  target: {
                    kind: "prism_file_change",
                    file_path: "main.tex",
                  },
                  preview: {
                    mode: "diff",
                    pending_hash: "pending-hash",
                    current_hash: "current-hash",
                  },
                  actions: [
                    { action: "preview_prism_change", label: "预览 diff" },
                    { action: "apply_prism_change", label: "应用到 Prism" },
                    { action: "reject_prism_change", label: "忽略并保护" },
                  ],
                },
              ],
              outputs: [
                {
                  id: "doc-1",
                  kind: "document",
                  preview: "章节摘要",
                  default_checked: true,
                  data: {
                    name: "chapter-summary.md",
                    mime_type: "text/markdown",
                    storage_path: "/tmp/chapter-summary.md",
                    size_bytes: 128,
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

  await page.goto(workbenchUrl);

  await expect(page.getByText("Prism 有 1 项待确认修改")).toBeVisible();
  const prismReviewLinks = page.getByRole("link", { name: "预览待确认修改" });
  await expect(prismReviewLinks.first()).toBeVisible();
  await prismReviewLinks.first().click();

  await expect(page).toHaveURL(
    /\/workspaces\/ws-1\/prism\?focus=file_changes&review_item_id=section%3Aintroduction&logical_key=section%3Aintroduction/,
  );
  await expect(page.getByText("Prism 待确认写入")).toBeVisible();
  await expect(page.getByText("main.tex").first()).toBeVisible();
  await expect(page.getByText(/Generated workspace manuscript/).first()).toBeVisible();

  await page.getByRole("button", { name: "应用到 Prism" }).click();

  await expect(page.getByText("Prism 已写入变更")).toBeVisible();
  await expect(page.getByText("已写入稿件修改: main.tex")).toBeVisible();
  await expect(page.locator("textarea").last()).toHaveValue(
    /Generated workspace manuscript/,
  );

  await page.getByRole("button", { name: "保护当前文件" }).click();
  await expect(page.getByText("当前文件已保护")).toBeVisible();
  await expect(page.getByText("保护段落")).toBeVisible();

  await page.goto(workbenchUrl);
  await page.getByRole("button", { name: "查看结果" }).click();
  await page.getByRole("button", { name: "保存到工作区" }).click();

  await expect(page.getByText("已保存到工作区")).toBeVisible();
  await expect
    .poll(() => commitPayload)
    .toEqual({ accept_all: true });
});

test("saved result links open the document drawer without resetting the chat state", async ({
  page,
  context,
}) => {
  await installWorkspaceRouteMocks(page, context, {
    commitResponse: {
      committed: { documents: 1 },
      room_targets: {
        documents: [{ output_id: "doc-1", item_id: "saved-doc-1" }],
        library: [],
      },
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
              ],
            },
          },
        },
      },
    ]),
  });

  await page.route("**/api/workspaces/ws-1/documents", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "saved-doc-1",
          name: "论文分析报告",
          mime_type: "text/markdown",
          doc_kind: "draft",
          size_bytes: 128,
          created_at: "2026-05-19T00:00:00Z",
          updated_at: "2026-05-19T00:00:00Z",
        },
      ]),
    });
  });

  await page.route("**/api/workspaces/ws-1/documents/saved-doc-1", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "saved-doc-1",
        name: "论文分析报告",
        mime_type: "text/markdown",
        doc_kind: "draft",
        size_bytes: 128,
        created_at: "2026-05-19T00:00:00Z",
        updated_at: "2026-05-19T00:00:00Z",
        metadata_json: {
          content: "# 论文分析报告\n\n## 研究方法\n- 对比实验",
        },
      }),
    });
  });

  await page.goto(
    "/workspaces/ws-1?feature=paper_analysis&skill=paper-analyst&entry=open&paper_title=x",
  );

  await page.getByRole("button", { name: "查看结果" }).click();
  await page.getByRole("button", { name: "保存到工作区" }).click();
  await page.getByRole("link", { name: "打开已保存的 论文分析报告" }).click();

  await expect(page.getByTestId("documents-drawer")).toBeVisible();
  await expect(page.getByText("研究方法")).toBeVisible();
  await expect(page.getByText("对比实验")).toBeVisible();
  await expect(page.getByText("已生成可提交的分析产物。")).toBeVisible();
});

test("markdown links inside result previews open workspace rooms without resetting the current thread", async ({
  page,
  context,
}) => {
  await installWorkspaceRouteMocks(page, context, {
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
              narrative: "我把后续阅读路线也串进结果预览里了。",
              outputs: [
                {
                  id: "doc-1",
                  kind: "document",
                  preview: "论文分析报告",
                  default_checked: true,
                  data: {
                    name: "analysis.md",
                    mime_type: "text/markdown",
                    size_bytes: 128,
                    doc_kind: "draft",
                    content:
                      "# 论文分析报告\n\n接下来建议先看[核心参考文献](/workspaces/ws-1?room=library&item_id=lib-1&query=Deep%20Learning)。",
                  },
                },
              ],
            },
          },
        },
      },
    ]),
  });

  await page.route("**/api/workspaces/ws-1/library", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "lib-1",
          title: "Deep Learning",
          authors: ["Smith"],
          year: 2024,
          source: "search_result",
          added_by: "assistant",
          created_at: "2026-05-19T00:00:00Z",
        },
      ]),
    });
  });

  await page.route("**/api/workspaces/ws-1/library/lib-1", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "lib-1",
        title: "Deep Learning",
        authors: ["Smith"],
        year: 2024,
        abstract: "A compact survey of deep learning systems.",
        source: "search_result",
        created_at: "2026-05-19T00:00:00Z",
      }),
    });
  });

  await page.goto(
    "/workspaces/ws-1?feature=paper_analysis&skill=paper-analyst&entry=open&paper_title=x",
  );

  await page.getByRole("button", { name: "查看结果" }).click();
  await expect(page.getByRole("link", { name: "核心参考文献" })).toBeVisible();
  await page.getByRole("link", { name: "核心参考文献" }).click();

  await expect(page.getByTestId("library-drawer")).toBeVisible();
  await expect(page.getByText("A compact survey of deep learning systems.")).toBeVisible();
  await expect(page.getByText("我把后续阅读路线也串进结果预览里了。")).toBeVisible();
});
