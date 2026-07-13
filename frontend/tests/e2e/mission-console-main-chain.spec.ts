import { expect, test } from "@playwright/test";
import { installWorkspaceRouteMocks } from "./fixtures/workspace-route-mocks";

const MISSION_ID = "mission-main-chain";
const summary = {
  mission_id: MISSION_ID,
  workspace_id: "ws-mission",
  thread_id: "thread-1",
  title: "联邦微调研究空白",
  objective: "梳理研究空白",
  status: "running",
  review_mode: "balanced_default",
  active_stage_id: "literature",
  snapshot_json: {
    required_stage_ids: ["scope", "literature", "position"],
    stage_acceptance: {
      scope: { title: "收敛研究问题", status: "passed" },
      literature: { title: "查找与核验证据", status: "active", summary: "正在交叉核验方法与评测文献" },
      position: { title: "形成贡献定位", status: "pending" },
    },
    team_summary: "从方法、评测和隐私三个侧面推进",
    subagent_summary: { latest: [{ job_id: "member-1", display_name: "严谨派阿澈", role_label: "方法与实验审校", status: "running", result_brief: "核验 Non-IID 实验设定" }] },
  },
  pending_review_count: 2,
  evidence_count: 2,
  artifact_count: 1,
  active_subagent_count: 1,
  state_version: 3,
  last_item_seq: 5,
  created_at: "2026-07-11T07:58:00Z",
  updated_at: "2026-07-11T08:00:00Z",
  started_at: "2026-07-11T07:58:00Z",
  completed_at: null,
};
const view = {
  mission: summary,
  attention_request: null,
  review_summary: { pending: 2, accepted: 0, needs_more_evidence: 0, committed: 0 },
  commit_summary: { pending: 0, applying: 0, committed: 0, failed: 0 },
  review_items: [
    { review_item_id: "review-1", mission_id: MISSION_ID, title: "核心创新点", summary: "将异构性与自适应秩聚合联系起来", target_kind: "claim", risk_level: "high", status: "pending", review_required_reason: "涉及论文核心论断，需要逐项确认", preview_json: { claim: "异构性与自适应秩聚合存在可验证关联" }, preview_ref: null, requires_explicit_review: true, batch_acceptable: false, suggested_selected: false },
    { review_item_id: "review-2", mission_id: MISSION_ID, title: "文献脉络草稿", summary: "整理方法演进与主要基线", target_kind: "document", risk_level: "medium", status: "pending", review_required_reason: "保存前建议确认", preview_json: {}, preview_url: null, requires_explicit_review: false, batch_acceptable: true, suggested_selected: true },
  ],
  commits: [],
  required_stage_ids: ["scope", "literature", "position"],
  stage_summaries: [
    { stage_id: "scope", title: "收敛研究问题", status: "passed" },
    { stage_id: "literature", title: "查找与核验证据", status: "active", summary: "正在交叉核验方法与评测文献" },
    { stage_id: "position", title: "形成贡献定位", status: "pending" },
  ],
  team_summary: "从方法、评测和隐私三个侧面推进",
  subagents: [{ subagent_id: "member-1", display_name: "严谨派阿澈", role_label: "方法与实验审校", status: "running", summary: "核验 Non-IID 实验设定" }],
  evidence_items: [{ item_id: "ev-1", seq: 4, title: "联邦 PEFT 基线", source_type: "paper", source_label: "arXiv", summary: "Federated Parameter-Efficient Fine-Tuning", citation: null, verified: true }],
  evidence_page: { total: 1, returned: 1, next_cursor: null },
  artifact_items: [],
  artifact_page: { total: 0, returned: 0, next_cursor: null },
  review_policy: { mode: "balanced_default", protected_outputs_require_confirmation: true, draft_outputs_may_be_automatic: true },
  quality_highlights: ["研究范围已通过验收"],
  refresh_token: "mission-main-chain:3:5",
};

test("MissionView opens on demand, reviews changes, and lazy-loads semantic trace", async ({ page, context }) => {
  let missionViewRequests = 0;
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === `/api/missions/${MISSION_ID}`) {
      missionViewRequests += 1;
    }
  });
  await installWorkspaceRouteMocks(page, context, {
    workspaceId: "ws-mission",
    workspaceName: "联邦学习选题",
    workspaceType: "sci",
    missions: [summary],
    missionViews: { [MISSION_ID]: view },
    missionItems: { [MISSION_ID]: [{ id: "item-1", mission_id: MISSION_ID, seq: 5, item_type: "evidence", phase: "completed", summary: "完成关键文献交叉核验", created_at: "2026-07-11T08:00:00Z" }] },
    missionEventBodies: [
      `data: ${JSON.stringify({ type: "mission.item.appended", missionId: MISSION_ID, stateVersion: 4, lastItemSeq: 9 })}\n\n`,
    ],
  });
  await page.goto("/workspaces/ws-mission");
  await expect(page.getByTestId("mission-console")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "打开研究任务" })).toBeVisible();
  await expect(page.getByText("严谨派阿澈")).not.toBeVisible();
  await page.getByRole("button", { name: "打开研究任务" }).click();
  await expect(page.getByTestId("mission-console")).toBeVisible();
  await page.getByRole("tab", { name: "进展" }).click();
  await expect(page.getByText("严谨派阿澈")).toBeVisible();
  await page.getByRole("tab", { name: /确认/ }).click();
  await expect(page.getByText("需逐项确认")).toBeVisible();
  await page.getByText("查看内容预览").first().click();
  await expect(page.getByText(/异构性与自适应秩聚合存在可验证关联/)).toBeVisible();
  await page.getByRole("button", { name: "确认此项" }).click();
  await expect(page.getByText("已确认，待保存")).toBeVisible();
  await page.getByRole("checkbox", { name: "选择 文献脉络草稿" }).check();
  await page.getByRole("button", { name: "需要补证", exact: true }).last().click();
  await expect(page.getByText("1 项内容还需要补充证据，暂不会写入工作区。" )).toBeVisible();
  await page.getByRole("button", { name: "保存已确认内容" }).click();
  await expect(page.getByText("已保存")).toBeVisible();
  await expect.poll(() => missionViewRequests).toBeGreaterThan(1);
  await page.getByRole("tab", { name: "轨迹" }).click();
  await expect(page.getByText("完成关键文献交叉核验")).not.toBeVisible();
  await page.getByRole("button", { name: "加载任务轨迹" }).click();
  await expect(page.getByText("完成关键文献交叉核验")).toBeVisible();
  await page.reload();
  await expect(page.getByTestId("mission-console")).toHaveCount(0);
  await expect(page.getByText(/blocked|high risk|provider|schema/i)).toHaveCount(0);
});

test("mobile keeps chat and mission on separate non-overlapping surfaces", async ({ page, context }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installWorkspaceRouteMocks(page, context, { workspaceId: "ws-mission-mobile", workspaceType: "sci", missions: [{ ...summary, workspace_id: "ws-mission-mobile" }], missionViews: { [MISSION_ID]: { ...view, mission: { ...summary, workspace_id: "ws-mission-mobile" } } } });
  await page.goto("/workspaces/ws-mission-mobile");
  await page.getByRole("button", { name: "打开研究任务" }).click();
  await expect(page.getByTestId("mission-region")).toBeVisible();
  await expect(page.getByTestId("chat-region")).toHaveCount(0);
  const box = await page.getByTestId("mission-region").boundingBox();
  expect(box?.x).toBeGreaterThanOrEqual(0);
  expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(390);
});

test("waiting mission explains the exact input needed", async ({ page, context }) => {
  const waitingSummary = { ...summary, status: "waiting" };
  const waitingView = {
    ...view,
    mission: waitingSummary,
    attention_request: {
      request_id: "request-dataset",
      reason: "external_data",
      title: "需要补充实验数据",
      summary: "请上传题目数据表后继续验证模型。",
      impact: "数据补齐前，问津会保留当前阶段和已有结果。",
      required_inputs: [
        {
          input_id: "dataset",
          label: "实验数据表",
          description: "CSV 或 XLSX 文件",
          input_type: "file",
          required: true,
        },
      ],
      actions: [
        {
          action_id: "upload",
          label: "添加材料",
          action_type: "upload_file",
          primary: true,
        },
      ],
    },
  };
  await installWorkspaceRouteMocks(page, context, {
    workspaceId: "ws-mission-waiting",
    workspaceType: "sci",
    missions: [{ ...waitingSummary, workspace_id: "ws-mission-waiting" }],
    missionViews: {
      [MISSION_ID]: {
        ...waitingView,
        mission: { ...waitingSummary, workspace_id: "ws-mission-waiting" },
      },
    },
  });

  await page.goto("/workspaces/ws-mission-waiting");
  await expect(page.getByText("需要补充实验数据")).toHaveCount(0);
  await page.getByRole("button", { name: "打开研究任务" }).click();
  await expect(page.getByRole("heading", { name: "需要补充实验数据", exact: true })).toBeVisible();
  await expect(page.getByText("请上传题目数据表后继续验证模型。")).toBeVisible();
  await expect(page.getByText("实验数据表")).toBeVisible();
  await expect(page.getByText("数据补齐前，问津会保留当前阶段和已有结果。")).toBeVisible();
  await expect(page.getByRole("button", { name: "添加材料" })).toBeVisible();
});

test("academic visual review loads authenticated preview bytes and supports zoom", async ({ page, context }) => {
  const visualItem = {
    review_item_id: "review-visual",
    mission_id: MISSION_ID,
    title: "联邦聚合机制图",
    summary: "依据当前方法段生成的说明图",
    target_kind: "workspace_asset",
    risk_level: "medium",
    status: "pending",
    review_required_reason: "保存学术图前请确认",
    preview_json: {
      artifact_kind: "figure",
      figure_type: "mechanism_illustration",
      strategy: "llm_image",
      evidence_level: "explanatory",
      mime_type: "image/svg+xml",
      caption: "联邦客户端向全局模型提交参数更新。",
      alt_text: "三个客户端连接到中央聚合节点",
      renderer_id: "gpt-image-2",
      reproducibility_status: "not_applicable",
    },
    preview_url: `/api/missions/${MISSION_ID}/review-items/review-visual/preview`,
    requires_explicit_review: true,
    batch_acceptable: false,
    suggested_selected: false,
  };
  const visualView: Record<string, unknown> = structuredClone(view);
  visualView.review_items = [visualItem];
  visualView.review_summary = { pending: 1, accepted: 0, needs_more_evidence: 0, committed: 0 };
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360"><rect width="640" height="360" fill="white"/><circle cx="320" cy="180" r="54" fill="#d7eee9" stroke="#176b62"/><circle cx="100" cy="80" r="30" fill="#eef2f1"/><circle cx="100" cy="180" r="30" fill="#eef2f1"/><circle cx="100" cy="280" r="30" fill="#eef2f1"/><path d="M130 80 L270 160 M130 180 L266 180 M130 280 L270 200" stroke="#4b6460" stroke-width="4"/></svg>';

  await installWorkspaceRouteMocks(page, context, {
    workspaceId: "ws-mission-visual",
    workspaceType: "sci",
    missions: [{ ...summary, workspace_id: "ws-mission-visual", pending_review_count: 1 }],
    missionViews: {
      [MISSION_ID]: {
        ...visualView,
        mission: { ...summary, workspace_id: "ws-mission-visual", pending_review_count: 1 },
      },
    },
    missionReviewPreviews: {
      "review-visual": {
        mimeType: "image/svg+xml",
        bodyBase64: Buffer.from(svg).toString("base64"),
      },
    },
  });

  await page.goto("/workspaces/ws-mission-visual");
  await page.getByRole("button", { name: "打开研究任务" }).click();
  await page.getByRole("tab", { name: /确认/ }).click();
  const preview = page.getByRole("img", { name: "三个客户端连接到中央聚合节点" });
  await expect(preview).toBeVisible();
  await expect(page.getByText("联邦客户端向全局模型提交参数更新。")).toBeVisible();
  await page.getByRole("button", { name: "放大视觉预览" }).click();
  await expect(page.getByRole("button", { name: "缩小视觉预览" })).toBeVisible();
});
