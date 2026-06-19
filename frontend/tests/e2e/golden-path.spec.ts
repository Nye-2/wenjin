import { expect, test } from "@playwright/test";

import {
  buildEventStreamBody,
  installWorkspaceRouteMocks,
} from "./fixtures/workspace-route-mocks";

test("paper analysis auto-entry renders the current chat completion chain", async ({
  page,
  context,
}) => {
  const paperAnalysisOutput = {
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
  };
  await installWorkspaceRouteMocks(page, context, {
    executions: [
      {
        id: "ex-1",
        user_id: "user-1",
        workspace_id: "ws-1",
        execution_type: "capability",
        feature_id: "paper_analysis",
        status: "completed",
        params: {},
        result: {
          task_report: {
            execution_id: "ex-1",
            capability_id: "paper_analysis",
            status: "completed",
            narrative: "3 个角度可切，最有价值是通信效率 ↔ 隐私强度",
            duration_seconds: 12,
            outputs: [paperAnalysisOutput],
            review_items: [],
            errors: [],
          },
        },
        node_states: {},
        graph_structure: { mode: "team_kernel", nodes: [], edges: [] },
        artifact_ids: [],
        next_actions: [],
        child_execution_ids: [],
        progress: 100,
        created_at: "2026-06-13T00:00:00Z",
        updated_at: "2026-06-13T00:00:12Z",
      },
    ],
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
              outputs: [paperAnalysisOutput],
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
  await expect(page.getByRole("button", { name: "查看详情" })).toBeVisible();
  await page.getByRole("button", { name: "查看详情" }).click();
  await expect(
    page.getByRole("button", { name: /异构客户端缺口/ }).first(),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "保存已勾选" })).toBeVisible();

  for (const banned of [
    "message_feature_proposal",
    "意图置信度",
    "我会先复用",
  ]) {
    await expect(page.getByText(banned)).toHaveCount(0);
  }
});

test("sandbox artifact review items render as artifact saves, not Prism edits", async ({
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
              execution_id: "ex-sandbox-artifact",
              capability_name: "实验复现",
              status: "completed",
              narrative: "已生成可保存的实验分析报告。",
              outputs: [],
              review_items: [
                {
                  id: "review-artifact-1",
                  kind: "sandbox_artifact",
                  status: "pending",
                  title: "Accept sandbox artifact: sandbox_report",
                  summary: "/workspace/reports/analysis.md",
                  source: {
                    type: "sandbox_job",
                    execution_id: "ex-sandbox-artifact",
                    job_id: "job-1",
                  },
                  target: {
                    kind: "sandbox_artifact",
                    path: "/workspace/reports/analysis.md",
                    artifact_kind: "sandbox_report",
                    asset_id: "asset-1",
                    sandbox_artifact_id: "artifact-1",
                  },
                  preview: {
                    mode: "artifact",
                    path: "/workspace/reports/analysis.md",
                    mime_type: "text/markdown",
                    content_hash: "sha256:analysis",
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

  await expect(page.getByText("产物有 1 项待确认保存")).toBeVisible();
  await expect(
    page.getByText("Accept sandbox artifact: sandbox_report"),
  ).toBeVisible();
  await expect(page.getByText("/workspace/reports/analysis.md")).toBeVisible();
  await expect(page.getByText(/Prism 有/)).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "预览待确认修改" }),
  ).toHaveCount(0);
});

test("workbench previews sandbox figure review items without Prism handoff", async ({
  page,
  context,
}) => {
  const figureReviewItem = {
    id: "review-figure-1",
    kind: "sandbox_artifact",
    status: "pending",
    title: "Federated accuracy figure",
    summary: "/workspace/outputs/figures/fed_curve/figure.png",
    source: {
      type: "sandbox_job",
      execution_id: "ex-figure",
      task_id: "figure_table_engineer.v1__1",
      job_id: "job-figure-1",
    },
    target: {
      kind: "sandbox_artifact",
      path: "/workspace/outputs/figures/fed_curve/figure.png",
      artifact_kind: "figure",
      sandbox_artifact_id: "artifact-figure-1",
    },
    preview: {
      mode: "artifact",
      path: "/workspace/outputs/figures/fed_curve/figure.png",
      mime_type: "image/png",
      content_hash: "sha256:figure",
    },
    reproducibility: {
      source_script: "/workspace/scripts/fed_curve.py",
      dataset_paths: ["/workspace/datasets/results.csv"],
      content_hash: "sha256:figure",
    },
  };
  await installWorkspaceRouteMocks(page, context, {
    executions: [
      {
        id: "ex-figure",
        user_id: "user-1",
        workspace_id: "ws-1",
        execution_type: "capability",
        feature_id: "figure_generation",
        status: "completed",
        params: {},
        result: {
          task_report: {
            execution_id: "ex-figure",
            capability_id: "figure_generation",
            status: "completed",
            narrative: "图表工程师已生成可预览的实验图。",
            duration_seconds: 6,
            outputs: [],
            review_items: [figureReviewItem],
            errors: [],
          },
        },
        review_items: [figureReviewItem],
        node_states: {},
        graph_structure: { mode: "team_kernel", nodes: [], edges: [] },
        artifact_ids: [],
        next_actions: [],
        child_execution_ids: [],
        progress: 100,
        created_at: "2026-06-19T00:00:00Z",
        updated_at: "2026-06-19T00:00:06Z",
      },
    ],
  });

  await page.goto("/workspaces/ws-1");
  await expect(page.getByText("图表产物").first()).toBeVisible();
  await expect(page.getByRole("button", { name: /Federated accuracy figure/ })).toBeVisible();
  await page.getByRole("button", { name: /Federated accuracy figure/ }).click();

  await expect(page.getByTestId("result-preview-image")).toBeVisible();
  await expect(page.getByText("/workspace/outputs/figures/fed_curve/figure.png")).toBeVisible();
  await expect(page.getByText("fed_curve.py")).toBeVisible();
  await expect(page.getByText("Prism 文件级修改")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "全部保存" })).toHaveCount(0);
  await expect(page.getByText(/保存或忽略会由产物确认入口处理/)).toBeVisible();
});

test("result card can deep-link into an expert team preview", async ({
  page,
  context,
}) => {
  const expertPreviewId = "preview-literature-1";
  await installWorkspaceRouteMocks(page, context, {
    executions: [
      {
        id: "ex-team-preview",
        user_id: "user-1",
        workspace_id: "ws-1",
        execution_type: "capability",
        feature_id: "paper_analysis",
        status: "completed",
        params: {},
        result: {
          task_report: {
            execution_id: "ex-team-preview",
            capability_id: "paper_analysis",
            status: "completed",
            narrative: "文献猎手 Nora 已整理候选文献。",
            duration_seconds: 8,
            outputs: [
              {
                id: "team-output-1",
                kind: "document",
                preview: "候选文献列表",
                default_checked: true,
                data: {
                  name: "候选文献列表.md",
                  mime_type: "text/markdown",
                  doc_kind: "team_member_report",
                  content: "12 篇候选文献和筛选理由。",
                },
              },
            ],
            review_items: [],
            preview_item_id: expertPreviewId,
            errors: [],
          },
        },
        node_states: {
          "team.1.research_scout_v1.1": {
            status: "completed",
            node_type: "agent_invocation",
            label: "文献猎手 Nora",
            node_metadata: {
              team: true,
              template_id: "research_scout.v1",
              display_name: "文献猎手 Nora",
              assigned_role: "文献检索专家",
              expert_profile: {
                public_name: "文献猎手 Nora",
                role_title: "文献检索专家",
                avatar_label: "文",
              },
              harness: {
                expert_snapshots: [
                  {
                    snapshot_id: "snap-literature-1",
                    execution_id: "ex-team-preview",
                    workspace_id: "ws-1",
                    agent_invocation_id: "team.1.research_scout_v1.1",
                    agent_template_id: "research_scout.v1",
                    role_key: "research_scout",
                    role_name: "文献检索专家",
                    display_name: "文献猎手 Nora",
                    status: "completed",
                    update_kind: "finding",
                    stage: { label: "检索完成" },
                    headline: "找到 12 篇候选文献",
                    body: "主要集中在隐私保护、通信压缩和个性化微调三个方向。",
                    chips: [{ label: "候选", value: "12 篇", tone: "success" }],
                    created_at: "2026-06-13T00:00:01Z",
                  },
                ],
                expert_preview_items: [
                  {
                    preview_item_id: expertPreviewId,
                    execution_id: "ex-team-preview",
                    workspace_id: "ws-1",
                    owner_agent_invocation_id: "team.1.research_scout_v1.1",
                    owner_role_name: "文献检索专家",
                    title: "候选文献列表",
                    kind: "literature_list",
                    summary: "12 篇候选文献和筛选理由。",
                    status: "ready",
                    created_at: "2026-06-13T00:00:02Z",
                  },
                ],
              },
            },
          },
        },
        graph_structure: {
          mode: "team_kernel",
          nodes: [
            {
              id: "team.1.research_scout_v1.1",
              type: "agent_invocation",
              label: "文献猎手 Nora",
            },
          ],
          edges: [],
        },
        artifact_ids: [],
        next_actions: [],
        child_execution_ids: [],
        progress: 100,
        created_at: "2026-06-13T00:00:00Z",
        updated_at: "2026-06-13T00:00:08Z",
      },
    ],
    runStreamBody: buildEventStreamBody([
      {
        event: "block",
        data: {
          block: {
            kind: "result_card",
            data: {
              execution_id: "ex-team-preview",
              capability_name: "论文分析",
              status: "completed",
              narrative: "文献猎手 Nora 已整理候选文献。",
              outputs: [
                {
                  id: "team-output-1",
                  kind: "document",
                  preview: "候选文献列表",
                  default_checked: true,
                  data: {
                    name: "候选文献列表.md",
                    mime_type: "text/markdown",
                    doc_kind: "team_member_report",
                    content: "12 篇候选文献和筛选理由。",
                  },
                },
              ],
              review_items: [],
              preview_item_id: expertPreviewId,
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

  await expect(page.getByText("文献猎手 Nora 已整理候选文献。")).toBeVisible();
  await page.getByRole("button", { name: "查看详情" }).click();
  await expect(page.getByRole("region", { name: "结果预览" })).toBeVisible();
  await expect(page.getByText("候选文献列表")).toBeVisible();
  await expect(page.getByText("12 篇候选文献和筛选理由。")).toBeVisible();
});

test("canonical result card links open workspace rooms without resetting the current thread", async ({
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
            run_id: "run-1",
            title: "论文框架已整理",
            tldr: "我先给你收成了一个可继续迭代的大纲。",
            findings: [
              { id: "1", text: "研究问题和实验设计已经拆开。" },
            ],
            links: [
              {
                icon: "file-text",
                label: "查看已保存大纲",
                href: "/workspaces/ws-1?room=documents&item_id=saved-doc-1&query=论文框架大纲",
              },
            ],
            feedback: {
              question: "接下来要继续补文献综述，还是先压方法章节？",
              pills: [],
              allow_free_input: true,
            },
            stats: {
              duration_ms: 1420,
              subagents: 2,
              tokens: 1840,
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
          name: "论文框架大纲",
          mime_type: "text/markdown",
          doc_kind: "outline",
          size_bytes: 256,
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
        name: "论文框架大纲",
        mime_type: "text/markdown",
        doc_kind: "outline",
        size_bytes: 256,
        created_at: "2026-05-19T00:00:00Z",
        updated_at: "2026-05-19T00:00:00Z",
        metadata_json: {
          content: "# 论文框架大纲\n\n## 方法\n- 系统设计",
        },
      }),
    });
  });

  await page.goto(
    `/workspaces/ws-1?feature=paper_analysis&skill=paper-analyst&entry=open&paper_title=${encodeURIComponent(
      "联邦学习+大模型",
    )}`,
  );

  await expect(page.getByText("论文框架已整理")).toBeVisible();
  await page.getByRole("link", { name: "查看已保存大纲" }).click();

  await expect(page.getByTestId("documents-drawer")).toBeVisible();
  await expect(page.getByText("系统设计")).toBeVisible();
  await expect(page.getByText("论文框架已整理")).toBeVisible();
});

test("markdown links in assistant text open workspace rooms without resetting the current thread", async ({
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
            content:
              "我已经把结构大纲放进工作区了，[打开文档](/workspaces/ws-1?room=documents&item_id=saved-doc-2&query=结构大纲)。",
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
          id: "saved-doc-2",
          name: "结构大纲",
          mime_type: "text/markdown",
          doc_kind: "outline",
          size_bytes: 192,
          created_at: "2026-05-19T00:00:00Z",
          updated_at: "2026-05-19T00:00:00Z",
        },
      ]),
    });
  });

  await page.route("**/api/workspaces/ws-1/documents/saved-doc-2", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "saved-doc-2",
        name: "结构大纲",
        mime_type: "text/markdown",
        doc_kind: "outline",
        size_bytes: 192,
        created_at: "2026-05-19T00:00:00Z",
        updated_at: "2026-05-19T00:00:00Z",
        metadata_json: {
          content: "# 结构大纲\n\n## 实验设计\n- 变量控制",
        },
      }),
    });
  });

  await page.goto(
    `/workspaces/ws-1?feature=paper_analysis&skill=paper-analyst&entry=open&paper_title=${encodeURIComponent(
      "联邦学习+大模型",
    )}`,
  );

  await expect(page.getByText("我已经把结构大纲放进工作区了")).toBeVisible();
  await page.getByRole("link", { name: "打开文档" }).click();

  await expect(page.getByTestId("documents-drawer")).toBeVisible();
  await expect(page.getByText("变量控制")).toBeVisible();
  await expect(page.getByText("我已经把结构大纲放进工作区了")).toBeVisible();
});
