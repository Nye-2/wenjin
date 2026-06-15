# Release Gate Checklist

更新时间: 2026-06-15
状态: Current

本文件只保留发布前 Go/No-Go 的当前门禁。历史验证流水不在 current docs 中维护；需要追溯时查 Git 历史。

## 1. Core Gate

发布前必须满足：

1. Chat Agent 只能通过 `launch_feature` 进入 execution；missing params advisory 不创建 execution、不扣积分、不触发外部检索。
2. `ExecutionRecord` / `ExecutionNodeRecord` 是执行事实源；前端 LiveWorkflowPanel、Runs drawer、chat result 共享 `frontend/lib/execution-run-view.ts`。
3. ResultCard / ReviewItem / Prism review flow 保持 review-first：生成内容先进入可审阅状态，用户接受后才写 rooms 或 Prism。
4. DataService 是 workspace、catalog、model、pricing、credit、sandbox、source、review、execution persistence 的边界；Gateway/worker 不直接绕过到 DB session。
5. Capability / skill / agent template 均来自 DataService Catalog；不得新增旧 workflow alias、fallback resolver 或双读兼容层。
6. 用户可见 capability 必须带 `routing` 合约并通过 schema/admin 写入校验；Chat Agent 只用 LLM route-card 做渐进承诺，不引入 embedding/vector index、关键词硬路由、前端 matcher 或第二套 router service。
7. TeamKernel 默认流程只展示 `team_prepare`、`team_recruit`、`team_dispatch`、`team_quality_gate`、`team_finish`；实名专家从 `agent_invocation` node metadata 投影。
8. Agent harness 只能由 Lead Agent graph / TeamKernel subagent 调用；不得暴露用户侧 sandbox console、公开 arbitrary exec endpoint 或第二套 execution stream。
9. Workspace 最多一个 active sandbox environment；任务容器可短生命周期，workspace `/workspace` 文件和环境保持连续。
10. Sandbox file tools 必须隐藏 protected/internal paths，拒绝 host paths、symlink escape、guidance/manifest direct writes 和 generic shell widening。
11. `sandbox.run_python`、依赖安装、artifact discovery、dataset/artifact manifest register 必须保留 bounded evidence、command audit、output refs、file diffs 和 reviewable artifact metadata。
12. Research evidence gate 必须覆盖 workflow trace、citation/source audit、experiment interpretation、paper relevance、statistical robustness、Prism semantic/style contracts 等已声明 surfaces。
13. Admin model catalog 不暴露明文 API key 或敏感 header；生产 runtime model discovery 来自 DataService runtime cache，不从 `LLM_MODELS` fallback，且每个 enabled billable model 必须绑定 enabled `model_usage` pricing policy。
14. Credit admission 使用 `spendable_credits = credits - reserved_credits`；sandbox start 和 token/model usage 走 DataService pricing / reservation / transaction 链路。
15. UI 默认视图不展示 raw stdout/stderr、raw args、template id、schema id、internal refs 或日志墙；复杂证据进入预览/诊断层。

## 2. Required Commands

后端：

```bash
cd backend
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m ruff check src tests
```

前端：

```bash
cd frontend
npm run lint
npm run typecheck
npm test
```

浏览器 smoke：

```bash
cd frontend
npm run dev -- --port 3099 --webpack
npx playwright test tests/e2e/golden-path.spec.ts --project=chromium -g "expert team preview"
```

仓库检查：

```bash
git diff --check
```

同时确认 README、AGENTS 和 `docs/current` 没有引用已删除的过程文档路径。

## 3. Focused Suites

当改动范围较窄，可先跑 focused suite；合并前仍建议跑 Required Commands。

Execution / TeamKernel / expert team：

```bash
cd backend
.venv/bin/python -m pytest \
  tests/architecture/test_dataservice_boundaries.py \
  tests/contracts/test_team_expert.py \
  tests/contracts/test_team_presentation.py \
  tests/agents/lead_agent/v2/test_team_policy.py \
  tests/agents/lead_agent/v2/test_team_kernel.py \
  tests/agents/lead_agent/v2/test_team_kernel_harness_replan.py -q
```

Harness / sandbox：

```bash
cd backend
.venv/bin/python -m pytest \
  tests/agents/harness \
  tests/agents/lead_agent/v2/test_sandbox_runtime.py \
  tests/agents/lead_agent/v2/test_sandbox_artifact_discovery.py \
  tests/sandbox/test_workspace_layout.py \
  tests/integration/test_harness_mock_sandbox_e2e.py -q
```

Frontend execution projection：

```bash
cd frontend
npx vitest run \
  tests/unit/hooks/useWorkspaceEventStream.test.tsx \
  tests/unit/v2/ResultCard.test.tsx \
  tests/unit/v2/execution-run-view.test.ts \
  tests/unit/v2/LiveWorkflowPanel.test.tsx \
  tests/unit/v2/live-workflow-view-model.test.ts
```

Capability routing：

```bash
cd backend
.venv/bin/python -m pytest \
  tests/services/test_capability_schema.py \
  tests/dataservice/test_catalog_domain.py \
  tests/seed/test_capability_seeds_load.py \
  tests/agents/chat_agent/test_capability_route_cards.py \
  tests/agents/chat_agent/test_capability_routing_eval.py \
  tests/agents/chat_agent/test_prompts_snapshot.py -q
```

## 4. Manual Smoke

1. 创建或打开 workspace，发送能触发 capability 的任务。
2. Chat 显示 launch receipt，右侧自动进入当前 run。
3. 团队面板显示实名专家、阶段摘录和可预览产出；默认视图不出现 raw JSON / stdout / template id。
4. 任务完成后 ResultCard 可接受结果；Prism 变更进入 review queue。
5. Prism 编译、PDF 对照、AI 改稿浮层、review apply/reject/revert 可用。
6. Admin models/pricing/credits 页面可读写配置，敏感 key 不回显。
