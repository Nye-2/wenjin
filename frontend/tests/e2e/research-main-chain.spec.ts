import { expect, test, type Page, type TestInfo } from "@playwright/test";

import {
  buildEventStreamBody,
  installWorkspaceRouteMocks,
} from "./fixtures/workspace-route-mocks";

const WORKSPACE_ID = "ws-main-chain";
const EXECUTION_ID = "ex-main-chain";
const THREAD_ID = "thread-main-chain";
const INITIAL_TOPIC_MESSAGE =
  "我想写联邦学习结合大模型微调方向的论文，你觉得可以吗？";
const LAUNCH_TASK =
  "做研究空白与创新点梳理，优先用联网搜索和 Semantic Scholar 交叉验证。";
const ITERATION_TASK =
  "基于刚才的证据，把创新点收窄成一个本科生也能落地的实验主线。";

const literatureOutput = {
  id: "lib-fedpeft",
  kind: "library_item",
  preview: "联邦参数高效微调代表文献",
  default_checked: true,
  data: {
    title: "Federated Parameter-Efficient Fine-Tuning for Large Language Models",
    authors: ["Wenjin Research Scout"],
    year: 2026,
    venue: "Semantic Scholar + Web Search",
    url: "https://example.org/federated-peft-llm",
    abstract:
      "Semantic Scholar 与联网搜索共同支持：联邦 PEFT/LoRA 的通信效率、Non-IID 泛化和隐私预算仍缺少统一评测。",
  },
};

const draftOutput = {
  id: "draft-gap-map",
  kind: "document",
  preview: "研究空白与创新点梳理",
  default_checked: true,
  data: {
    name: "文献定位与创新点.md",
    mime_type: "text/markdown",
    doc_kind: "draft",
    content:
      "# 研究空白与创新点\n\n## 主线\nNon-IID 数据下的联邦 LoRA 聚合仍缺少通信效率、泛化和隐私预算的统一评测。\n\n## 可写贡献\n提出自适应客户端聚合与跨源证据审计。",
  },
};

const nextTaskOutput = {
  id: "task-noniid-baseline",
  kind: "task",
  preview: "补齐 Non-IID + LoRA 实验基线",
  default_checked: true,
  data: {
    title: "补齐 Non-IID + LoRA 实验基线",
    description:
      "对比 FedAvg-LoRA、个性化 LoRA 和通信压缩策略，记录数据划分、随机种子与显存开销。",
    priority: "high",
  },
};

const taskReport = {
  execution_id: EXECUTION_ID,
  capability_id: "sci_literature_positioning",
  status: "completed",
  narrative:
    "已完成文献定位与创新点梳理：优先聚焦 Non-IID 场景下的联邦 LoRA 聚合、通信效率和证据可追溯。",
  duration_seconds: 18,
  outputs: [draftOutput, literatureOutput, nextTaskOutput],
  review_items: [],
  errors: [],
  research_state: {
    schema_version: "wenjin.research_state.v1",
    goal: "联邦学习结合大模型微调的研究空白与创新点梳理",
    current_stage: "synthesize",
    key_decisions: [
      "聚焦 Non-IID 下 Federated PEFT / LoRA 的通信效率与泛化权衡。",
    ],
    evidence_packet: [
      {
        evidence_id: "sem-fedpeft",
        title: "Semantic Scholar: Federated PEFT for LLMs",
        status: "verified",
      },
      {
        evidence_id: "web-survey",
        title: "Web Search: 2026 survey trail",
        status: "verified",
      },
    ],
    next_actions: ["补齐实验基线", "收窄论文贡献表述"],
  },
};

function mainChainExecution() {
  return {
    id: EXECUTION_ID,
    user_id: "user-1",
    workspace_id: WORKSPACE_ID,
    thread_id: THREAD_ID,
    execution_type: "capability",
    feature_id: "sci_literature_positioning",
    display_name: "文献定位与创新点",
    status: "completed",
    params: {
      topic: "联邦学习结合大模型微调",
    },
    result: {
      task_report: taskReport,
    },
    result_summary: taskReport.narrative,
    node_states: {
      "team.1.research_scout_v1.1": {
        status: "completed",
        node_type: "agent_invocation",
        label: "文献检索专家 Nora",
        output_preview:
          "Semantic Scholar 与 Web Search 交叉验证了 2 条线索，并标记了 1 个需要谨慎表述的论断。",
        output: {
          claim_evidence_map: [
            {
              claim_id: "claim-gap",
              claim_text:
                "Non-IID 下 PEFT 聚合的通信效率与泛化权衡仍缺少统一评测。",
              status: "verified",
              citation_keys: ["sem-fedpeft", "web-survey"],
              evidence_refs: ["sem-fedpeft", "web-survey"],
            },
          ],
          unsupported_claims: [
            {
              claim_id: "claim-venue-fit",
              claim_text: "该选题可以直接命中 AAAI 录用偏好。",
              required_fix: "只能表述为潜在投稿方向，必须补目标会议近年 CFP 和接收论文证据。",
            },
          ],
        },
        node_metadata: {
          team: true,
          template_id: "research_scout.v1",
          display_name: "文献检索专家 Nora",
          assigned_role: "文献检索专家",
          effective_tools: ["semantic_scholar_search", "web_search"],
          expert_profile: {
            public_name: "文献检索专家 Nora",
            role_title: "文献检索专家",
            avatar_label: "文",
          },
          harness: {
            expert_snapshots: [
              {
                snapshot_id: "snap-scout-1",
                status: "completed",
                update_kind: "finding",
                stage: { label: "跨源检索" },
                headline: "已完成跨源检索",
                body: "Semantic Scholar 与联网搜索都指向 Federated PEFT、Non-IID、通信压缩三个高价值 facet。",
                chips: [
                  { label: "Semantic Scholar", value: "1 条", tone: "success" },
                  { label: "Web Search", value: "1 条", tone: "success" },
                ],
                created_at: "2026-07-08T02:00:01Z",
              },
            ],
          },
        },
      },
      "team.2.quality_reviewer_v1.1": {
        status: "completed",
        node_type: "agent_invocation",
        label: "证据审阅专家 Lin",
        output_preview:
          "已通过引用支撑检查；会议适配性论断被降级为待补证据提醒。",
        output: {
          citation_key_audit: [
            {
              citation_key: "sem-fedpeft",
              claim_text:
                "Non-IID 下 PEFT 聚合的通信效率与泛化权衡仍缺少统一评测。",
              status: "supported",
              evidence_refs: ["sem-fedpeft"],
            },
          ],
        },
        node_metadata: {
          team: true,
          template_id: "quality_reviewer.v1",
          display_name: "证据审阅专家 Lin",
          assigned_role: "证据审阅专家",
          effective_tools: ["citation_audit", "web_search"],
          expert_profile: {
            public_name: "证据审阅专家 Lin",
            role_title: "证据审阅专家",
            avatar_label: "证",
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
          label: "文献检索专家 Nora",
        },
        {
          id: "team.2.quality_reviewer_v1.1",
          type: "agent_invocation",
          label: "证据审阅专家 Lin",
        },
      ],
      edges: [
        {
          source: "team.1.research_scout_v1.1",
          target: "team.2.quality_reviewer_v1.1",
        },
      ],
    },
    runtime_state: {
      team: {
        research_state: taskReport.research_state,
        methodology_contract: {
          stages: [
            { id: "scope", purpose: "确认主题边界" },
            { id: "literature", purpose: "跨源检索与 facet 拆分" },
            { id: "critique", purpose: "证据审阅" },
            { id: "synthesize", purpose: "综合成可写贡献" },
          ],
        },
        quality_gates: [
          {
            gate_id: "citation_strength",
            status: "pass",
            summary: "关键论断已绑定 Semantic Scholar 与联网搜索证据。",
            evidence: {
              strong_count: 2,
              weak_count: 1,
            },
          },
        ],
      },
    },
    review_items: [],
    artifact_ids: [],
    next_actions: [],
    child_execution_ids: [],
    progress: 100,
    created_at: "2026-07-08T02:00:00Z",
    started_at: "2026-07-08T02:00:00Z",
    completed_at: "2026-07-08T02:00:18Z",
    updated_at: "2026-07-08T02:00:18Z",
  };
}

function mainChainRunRecord() {
  return {
    id: EXECUTION_ID,
    workspace_id: WORKSPACE_ID,
    thread_id: THREAD_ID,
    capability_id: "sci_literature_positioning",
    capability_name: "文献定位与创新点",
    status: "completed",
    started_at: "2026-07-08T02:00:00Z",
    completed_at: "2026-07-08T02:00:18Z",
    summary: taskReport.narrative,
    progress: 100,
    primary_surface: "rooms",
    review_items_count: 0,
  };
}

async function attachWorkbenchScreenshot(
  page: Page,
  testInfo: TestInfo,
  name: string,
) {
  await testInfo.attach(name, {
    body: await page.getByTestId("workflow-panel").screenshot(),
    contentType: "image/png",
  });
}

test("agent-driven SCI research main chain covers chat launch, evidence, review writeback, and rooms", async ({
  page,
  context,
}, testInfo) => {
  const runPayloads: Array<Record<string, unknown>> = [];
  let commitPayload: Record<string, unknown> | null = null;

  await installWorkspaceRouteMocks(page, context, {
    workspaceId: WORKSPACE_ID,
    workspaceName: "联邦学习论文工作区",
    workspaceType: "sci",
    capabilities: [
      {
        id: "sci_literature_positioning",
        name: "文献定位与创新点",
        display_name: "文献定位与创新点",
        description: "建立相关工作、gap 和 contribution positioning",
        ui_meta: { icon: "search" },
      },
    ],
    thread: {
      id: THREAD_ID,
      messages: [],
    },
    executions: [mainChainExecution()],
    runRecords: [mainChainRunRecord()],
    libraryItems: [
      {
        id: "saved-lib-fedpeft",
        title:
          "Federated Parameter-Efficient Fine-Tuning for Large Language Models",
        authors: ["Wenjin Research Scout"],
        year: 2026,
        venue: "Semantic Scholar + Web Search",
        url: "https://example.org/federated-peft-llm",
        abstract:
          "Semantic Scholar 与联网搜索共同支持：联邦 PEFT/LoRA 的通信效率、Non-IID 泛化和隐私预算仍缺少统一评测。",
        added_by: "execution:ex-main-chain",
        source: "semantic_scholar + web_search",
        created_at: "2026-07-08T02:00:20Z",
      },
    ],
    commitResponse: {
      committed: { prism: 1, library: 1, tasks: 1 },
      room_targets: {
        prism: [
          {
            output_id: "draft-gap-map",
            item_id: "saved-doc-1",
            file_id: "saved-doc-1",
          },
        ],
        library: [
          {
            output_id: "lib-fedpeft",
            item_id: "saved-lib-fedpeft",
          },
        ],
        tasks: [
          {
            output_id: "task-noniid-baseline",
            item_id: "saved-task-noniid-baseline",
          },
        ],
      },
    },
    onRunStream: (payload) => runPayloads.push(payload),
    onCommit: (payload) => {
      commitPayload = payload;
    },
    runStreamBodies: [
      buildEventStreamBody([
        {
          event: "block",
          data: {
            block: {
              kind: "text",
              content:
                "可以做，但不要停在“联邦学习 + 大模型”的概念拼接。更自然的下一步是先做研究空白与创新点梳理，确认 Non-IID、PEFT/LoRA、通信效率和隐私保护之间哪个问题最可落地。",
            },
          },
        },
        {
          event: "block",
          data: {
            block: {
              kind: "text",
              content:
                "如果你准备继续，我建议先让我做研究空白与创新点梳理；信息足够后我再组织研究团队。",
            },
          },
        },
      ]),
      buildEventStreamBody([
      {
        event: "tool_result",
        data: {
          data: {
            status: "launched",
            execution_id: EXECUTION_ID,
            feature_id: "sci_literature_positioning",
            title: "文献定位与创新点",
            summary: "已启动研究团队，正在跨源检索和审阅证据。",
          },
        },
      },
      {
        event: "block",
        data: {
          block: {
            kind: "status_line",
            label: "正在启动研究团队",
            run_id: EXECUTION_ID,
            tone: "info",
          },
        },
      },
      {
        event: "block",
        data: {
          block: {
            kind: "text",
            content:
              "已启动：文献定位与创新点。问津会复用当前对话主题，不再让你从右侧能力卡重新开始。",
          },
        },
      },
      {
        event: "block",
        data: {
          block: {
            kind: "result_card",
            data: {
              execution_id: EXECUTION_ID,
              capability_name: "文献定位与创新点",
              status: "completed",
              narrative: taskReport.narrative,
              duration_seconds: taskReport.duration_seconds,
              outputs: taskReport.outputs,
              review_items: [],
            },
          },
        },
      },
      ]),
      buildEventStreamBody([
        {
          event: "block",
          data: {
            block: {
              kind: "status_line",
              label: "正在基于上一轮证据继续迭代",
              run_id: EXECUTION_ID,
              tone: "info",
            },
          },
        },
        {
          event: "block",
          data: {
            block: {
              kind: "text",
              content:
                "已承接上一轮证据包：建议把创新点收窄为 Non-IID 场景下的自适应 LoRA 聚合，并用通信量、客户端泛化和隐私预算三个指标做轻量实验。",
            },
          },
        },
      ]),
    ],
  });

  await page.goto(`/workspaces/${WORKSPACE_ID}`);

  await expect(page.getByTestId("chat-panel")).toBeVisible();
  await expect(page.getByTestId("workbench-panel-toggle")).toBeVisible();
  await expect(page.getByTestId("workbench-region")).toHaveAttribute(
    "data-panel-open",
    "false",
  );

  await page.getByTestId("chat-model-selector").click();
  await expect(page.getByTestId("chat-model-menu")).toBeVisible();
  await expect(page.getByTestId("chat-model-menu").getByText("速度")).toHaveCount(0);
  await page.getByTestId("chat-reasoning-option-high").click();
  await page.getByTestId("chat-model-submenu-trigger").click();
  await page.getByTestId("chat-model-option-gpt-5.3-codex-spark").click();
  await expect(page.getByTestId("chat-model-selector")).toContainText("5.3 Codex");
  await expect(page.getByTestId("chat-model-selector")).toContainText("高");

  await page.getByPlaceholder("输入消息... Shift+Enter 换行").fill(INITIAL_TOPIC_MESSAGE);
  await page.getByTestId("chat-send").click();

  await expect(page.getByText("不要停在“联邦学习 + 大模型”的概念拼接")).toBeVisible();
  await expect(page.getByText("信息足够后我再组织研究团队")).toBeVisible();
  await expect(page.getByTestId("workbench-region")).toHaveAttribute(
    "data-panel-open",
    "false",
  );
  expect(runPayloads[0]).toMatchObject({
    message: INITIAL_TOPIC_MESSAGE,
    workspace_id: WORKSPACE_ID,
    model: "gpt-5.3-codex-spark",
    reasoning_effort: "high",
  });

  await page.getByPlaceholder("输入消息... Shift+Enter 换行").fill(LAUNCH_TASK);
  await page.getByTestId("chat-send").click();

  await expect(page.getByText("正在启动研究团队")).toBeVisible();
  await expect(page.getByText("不再让你从右侧能力卡重新开始")).toBeVisible();
  await expect(page.getByText("研究空白与创新点梳理").first()).toBeVisible();
  expect(runPayloads[1]).toMatchObject({
    message: LAUNCH_TASK,
    workspace_id: WORKSPACE_ID,
    model: "gpt-5.3-codex-spark",
    reasoning_effort: "high",
  });

  await expect(page.getByTestId("workbench-region")).toHaveAttribute(
    "data-panel-open",
    "true",
  );
  await expect(page.getByTestId("workflow-panel")).toBeVisible();
  await expect(
    page.getByTestId("workflow-panel").getByText("文献定位与创新点").first(),
  ).toBeVisible();
  await page.getByTestId("workflow-panel").getByRole("button", { name: "总览" }).click();
  await expect(
    page.getByTestId("workflow-panel").getByText("当前任务").first(),
  ).toBeVisible();
  await expect(page.getByTestId("workflow-panel").getByText("已完成").first()).toBeVisible();
  await expect(page.getByText("确认主题边界").first()).toBeVisible();
  await expect(page.getByText("跨源检索与 facet 拆分").first()).toBeVisible();
  await expect(page.getByText("证据审阅").first()).toBeVisible();
  await expect(page.getByText("综合成可写贡献").first()).toBeVisible();
  await expect(page.getByText("2 项").first()).toBeVisible();
  await expect(page.getByText("已写入 0 · 风险 1").first()).toBeVisible();
  await expect(page.getByText("阻塞 0 · 待确认 0").first()).toBeVisible();
  await attachWorkbenchScreenshot(page, testInfo, "right-panel-overview-after-launch");

  await page.getByRole("button", { name: "收起研究任务" }).click();
  await expect(page.getByTestId("workbench-panel-toggle")).toBeVisible();
  await page.getByTestId("workbench-panel-toggle").click();
  await expect(page.getByTestId("workflow-panel")).toBeVisible();

  await page.getByTestId("workflow-panel").getByRole("button", { name: "进展" }).click();
  await expect(page.getByText("任务进展")).toBeVisible();
  await expect(page.getByText("5/5 步完成")).toBeVisible();
  await expect(page.getByText("正在准备任务")).toHaveCount(0);
  await expect(page.getByText("查找证据并起草内容").first()).toBeVisible();
  await expect(page.getByText("2/2 个成员完成").first()).toBeVisible();
  await expect(page.getByRole("region", { name: "执行团队" })).toBeVisible();
  await expect(page.getByTestId("workflow-panel").getByText("研究团队")).toBeVisible();
  await expect(
    page.getByTestId("workflow-panel").getByText("2 个团队成员 · 1 个质量检查"),
  ).toBeVisible();
  await expect(page.getByText("文献检索专家 Nora").first()).toBeVisible();
  await expect(page.getByText("证据审阅专家 Lin").first()).toBeVisible();
  await expect(page.getByText("Semantic Scholar 1 条").first()).toBeVisible();
  await expect(page.getByText("Web Search 1 条").first()).toBeVisible();
  await expect(page.getByText("引用支撑").first()).toBeVisible();
  await expect(page.getByText("通过").first()).toBeVisible();
  await attachWorkbenchScreenshot(page, testInfo, "right-panel-team-roster");

  await page.getByRole("button", { name: "详情" }).first().click();
  await expect(page.getByRole("region", { name: "文献检索专家 Nora详情" })).toBeVisible();
  await expect(page.getByText("思考摘录")).toBeVisible();
  await expect(page.getByText("跨源检索", { exact: true })).toBeVisible();
  await expect(page.getByText("已完成跨源检索")).toBeVisible();
  await attachWorkbenchScreenshot(page, testInfo, "right-panel-expert-detail");
  await page.getByRole("button", { name: "返回团队" }).click();

  await page
    .getByTestId("workflow-panel")
    .getByRole("button", { name: "查看证据" })
    .click();
  await expect(page.getByText("证据摘要")).toBeVisible();
  await expect(page.getByRole("group", { name: "已发现 2 项" })).toBeVisible();
  await expect(page.getByRole("group", { name: "已核验 2 项" })).toBeVisible();
  await expect(page.getByRole("button", { name: "论断", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "引用", exact: true })).toBeVisible();
  await expect(page.getByText("Semantic Scholar 与 Web Search").first()).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: /Non-IID 下 PEFT 聚合的通信效率与泛化权衡/,
    }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /该选题可以直接命中 AAAI 录用偏好/ }),
  ).toBeVisible();
  await attachWorkbenchScreenshot(page, testInfo, "right-panel-evidence-view");

  await page.getByTestId("workflow-panel").getByRole("button", { name: "复核" }).click();
  await expect(page.getByText("复核与保存")).toBeVisible();
  await expect(page.getByText("3 项内容待复核。")).toBeVisible();
  await expect(page.getByText("先检查暂存结果，再保存确认过的工作区内容。")).toBeVisible();
  await expect(page.getByText("研究空白与创新点梳理").first()).toBeVisible();
  await expect(
    page.getByText("Federated Parameter-Efficient Fine-Tuning").first(),
  ).toBeVisible();
  await attachWorkbenchScreenshot(page, testInfo, "right-panel-review-queue");

  await expect(page.getByPlaceholder("或对结果反馈、推翻、迭代")).toBeVisible();
  await page.getByPlaceholder("或对结果反馈、推翻、迭代").fill(ITERATION_TASK);
  await page.getByTestId("chat-send").click();
  await expect(page.getByText("正在基于上一轮证据继续迭代")).toBeVisible();
  await expect(page.getByText("自适应 LoRA 聚合")).toBeVisible();
  expect(runPayloads[2]).toMatchObject({
    message: ITERATION_TASK,
    workspace_id: WORKSPACE_ID,
    model: "gpt-5.3-codex-spark",
    reasoning_effort: "high",
    metadata: {
      orchestration: {
        execution_id: EXECUTION_ID,
        source: "mission_console",
      },
    },
  });

  await page
    .getByTestId("chat-panel")
    .getByRole("button", { name: "保存到工作区（3 项）" })
    .click();
  await expect(page.getByText("3 项结果已写入")).toBeVisible();
  await expect(page.getByRole("status", { name: "保存状态" })).toContainText(
    "已写入工作区",
  );
  await attachWorkbenchScreenshot(page, testInfo, "right-panel-after-writeback");
  expect(commitPayload).toMatchObject({
    accepted_ids: ["draft-gap-map", "lib-fedpeft", "task-noniid-baseline"],
  });

  await page
    .getByTestId("chat-panel")
    .getByRole("link", {
      name: /打开已保存的 Federated Parameter-Efficient Fine-Tuning/,
    })
    .click();
  await expect(page.getByTestId("library-drawer")).toBeVisible();
  await expect(
    page.getByTestId("library-drawer").getByTestId("result-preview-citation"),
  ).toContainText("Semantic Scholar 与联网搜索共同支持");
  await page.getByRole("button", { name: "关闭文献资料" }).click();
  await expect(page.getByTestId("library-drawer")).toHaveCount(0);

  await page.getByRole("button", { name: "资料库" }).click();
  await page.getByRole("button", { name: /运行记录/ }).click();
  await expect(page.getByTestId("runs-drawer")).toBeVisible();
  await expect(page.getByTestId("run-item").getByText("文献定位与创新点")).toBeVisible();
  await expect(page.getByTestId("run-status").getByText("已完成")).toBeVisible();
  await page.getByRole("button", { name: "关闭运行记录" }).click();

  await page
    .getByTestId("chat-panel")
    .getByRole("link", { name: /打开已保存的 研究空白与创新点梳理/ })
    .click();
  await expect(page.getByTestId("prism-workspace-shell")).toBeVisible();
  await expect(page.getByTestId("prism-file-preview").getByText("研究方法")).toBeVisible();
});
