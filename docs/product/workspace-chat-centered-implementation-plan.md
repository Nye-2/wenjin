# Workspace Chat-Centered Implementation Plan

更新时间: 2026-03-23
状态: Draft
适用项目: `academiagpt-v2`
关联文档:

- `docs/product/workspace-chat-centered-redesign.md`
- `docs/product/workspace-feature-catalog.md`
- `docs/product/frontend-feature-plugin-contract.md`
- `docs/product/release-gate-checklist.md`

## 1. Review 结论

基于当前仓库代码，上一版改版方案方向正确，但还需要进一步收紧实施边界和依赖顺序。

当前可以直接确认的结论:

1. `workspace != session`，而应是“一个完整任务”。
2. `thread` 已经真实存在于数据层和前端 store，不应删除，只应降级为弱感知对象。
3. chat 基础设施并没有消失，真正缺失的是 thesis workspace 首屏入口，以及 chat 对 feature 的统一编排能力。
4. 双路长短期记忆目前不是“架构上不能做”，而是“闭环没有补完整”。
5. 原 AcademiaGPT 的高价值能力仍有明显缺口，必须单列回补计划，不能混在入口改版里一起泛化。

仓库级关键依据:

- chat 路由和 thread 持久化已存在:
  - `backend/src/gateway/routers/chat.py`
  - `backend/src/services/chat_thread_service.py`
- feature 执行链已支持 `thread_id`:
  - `frontend/lib/api.ts`
  - `backend/src/application/handlers/feature_execution_handler.py`
- workspace layout 已会自动恢复最近 thread:
  - `frontend/app/(workbench)/workspaces/[id]/layout.tsx`
- thesis workspace 当前没有嵌入 chat，其他 workspace 有:
  - `frontend/app/(workbench)/workspaces/[id]/page.tsx`
- chat memory 持久化链路存在明显缺口:
  - `backend/src/agents/middlewares/memory.py`
  - `backend/src/agents/memory/queue.py`
- feature 完成后已经有一条独立 memory 落库路径:
  - `backend/src/task/handlers/workspace_feature_handler.py`

## 2. 当前差距清单

### 2.1 入口与交互

1. thesis workspace 首页仍是纯卡片面板，没有 chat 驾驶舱。
2. `ChatPanel` 已支持 thread 切换、skill 选择、快捷动作，但仍偏“消息面板”，不是“任务编排中枢”。
3. `QuickActions` 仍是全量 feature 平铺按钮，不是“推荐下一步”。
4. `DashboardService` 只有模块状态和最近产出，没有任务摘要、风险、下一步推荐。

### 2.2 编排与数据契约

1. lead agent 还没有 `run_workspace_feature` / `list_workspace_features` / `list_workspace_artifacts` 这类 workspace 级工具。
2. chat 消息契约只有纯文本，缺少任务卡、结果卡、下一步卡的结构化消息块。
3. feature 结果可以沉淀到 artifact，但 chat 里没有稳定的结构化回显承接。

### 2.3 记忆与上下文

1. `MemoryMiddleware.after_model()` 只调用 `enqueue(thread_id, messages)`，没有 callback，防抖后的持久化实际上大概率不会发生。
2. 当前可用的长期记忆表是 `UserKnowledge`，可承接 user/workspace 记忆，但 workspace facts 还没有单独的产品语义层。
3. 当前 thread history、workspace facts、user preferences 三层语义没有在接口和 UI 中显式区分。

### 2.4 能力回补

对照旧仓库 `AcademiaGPT` 的 README、路由和模块入口，以下能力在新仓库中尚未完整回补或未进入统一 registry:

1. 文献综述
2. 论文框架 / 摘要与大纲
3. 同行评审
4. 期刊推荐
5. 实验设计
6. 政策分析
7. AI 配图增强

旧仓库依据:

- `AcademiaGPT/README.md`
- `AcademiaGPT/frontend/src/router/index.ts`

## 3. 实施原则

1. 先补“入口”和“编排胶水层”，再补“能力数量”。
2. 首期不改写 canonical feature pipeline，只在其上增加 chat orchestration。
3. 首期不把 thread schema 改复杂，主线 / 分支语义可以先从文案和默认策略开始。
4. 记忆体系先修闭环、再做分层、最后再考虑独立 `workspace_facts` 表。
5. 任何新 feature 都必须先进 registry、走统一 task pipeline、产物落到 artifact。

## 4. 工作流依赖图

```text
Workspace Page / Layout
  -> Chat Store / Dashboard Store / Workspace Store
  -> Chat Router
  -> Lead Agent
  -> Workspace Tools
  -> FeatureExecutionHandler
  -> TaskService / WorkspaceFeatureHandler
  -> Artifact / Task / Workspace Event
  -> Dashboard Summary / Recommendation
  -> Chat Structured Cards
```

依赖顺序:

1. 先统一 dashboard 和 chat 入口。
2. 再补 workspace summary / next-step 数据契约。
3. 再补 lead agent workspace tools。
4. 再补 chat 结构化消息卡片。
5. 最后修 memory 分层和旧能力回补。

## 5. 推荐分期

建议按 6 个阶段推进:

1. Phase 0: 基线冻结与方案评审
2. Phase 1: Workspace 驾驶舱入口重构
3. Phase 2: Chat 编排 feature
4. Phase 3: 记忆闭环与推荐
5. Phase 4: 旧能力回补
6. Phase 5: 灰度发布与上线 review

## 6. Phase 0: 基线冻结与方案评审

目标:

- 冻结术语、范围和优先级
- 补齐旧能力缺口矩阵
- 确认首期不做项

退出标准:

1. `workspace / thread / feature / artifact / memory` 术语冻结。
2. Phase 1-3 范围冻结。
3. 能力回补优先级明确，避免实现期不断插单。

| ID | 类型 | 任务 | 目标文件 / 范围 | 依赖 | 完成定义 |
|---|---|---|---|---|---|
| P0-01 | Product | 冻结实体定义与首期范围 | `docs/product/workspace-chat-centered-redesign.md` | - | 明确 `workspace != session`，明确首期 non-goals |
| P0-02 | Product | 形成旧仓库能力差距矩阵 | `AcademiaGPT/README.md`, `AcademiaGPT/frontend/src/router/index.ts`, `docs/product/workspace-chat-centered-implementation-plan.md` | P0-01 | 明确高优先级回补项和映射 workspace 类型 |
| P0-03 | Tech | 形成 repo 级现状审计 | chat / feature / dashboard / memory 相关代码 | P0-01 | 明确可复用件、缺口、阻塞项 |
| RV0-01 | Review | 架构评审 | 产品 + 前端 + 后端 | P0-01 ~ P0-03 | 评审纪要确认 Phase 1-3 的接口边界和不做项 |
| QA0-01 | QA | 基线回归与命令清单确认 | `backend/tests/gateway/routers/test_chat.py`, `backend/tests/application/handlers/test_feature_execution_handler.py`, `backend/tests/gateway/routers/test_dashboard.py` | P0-03 | 确认后续每阶段必跑测试清单 |

## 7. Phase 1: Workspace 驾驶舱入口重构

目标:

- 五类 workspace 首页统一成“任务驾驶舱”
- thesis workspace 恢复 chat 主入口
- 首页只突出“任务状态 + 推荐下一步”，不再平铺模块心智

退出标准:

1. thesis / sci / proposal / software_copyright / patent 首页均带 chat panel。
2. 首页出现 task summary strip。
3. chat 区域文案完成主线 / 分支语义调整。
4. 推荐动作替代全量快捷按钮平铺。

| ID | 类型 | 任务 | 目标文件 / 范围 | 依赖 | 完成定义 |
|---|---|---|---|---|---|
| P1-01 | FE | 抽取统一 workspace cockpit shell | `frontend/app/(workbench)/workspaces/[id]/page.tsx`, `frontend/app/(workbench)/workspaces/[id]/layout.tsx` | RV0-01 | thesis 与非 thesis 不再分裂成两套首页逻辑 |
| P1-02 | FE | 新增 `TaskSummaryStrip` 组件 | 建议新增 `frontend/components/workspace/TaskSummaryStrip.tsx`，并接入 workspace 首页 | P1-01 | 首页可展示当前阶段、下一步、最近活动、风险提醒 |
| P1-03 | BE | 提供 workspace summary 聚合接口 | 建议新增 `backend/src/services/workspace_summary_service.py`，扩展 `backend/src/gateway/routers/workspaces.py` 或新增 summary route | RV0-01 | 前端不再靠本地拼接 summary 数据 |
| P1-04 | FE | `QuickActions` 升级为 `RecommendedActions` | `frontend/components/workspace/QuickActions.tsx`, `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx` | P1-03 | 默认只显示 3-5 个推荐动作，支持“更多工具”入口 |
| P1-05 | FE | 调整 chat thread 文案和默认策略 | `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`, `frontend/stores/chat.ts` | P1-01 | “新会话”改“新分支”，“历史会话”改“主线 / 分支记录” |
| P1-06 | FE | 将 `TaskRuntimePanel` / `RecentArtifacts` 重新编排进首屏 | `frontend/components/workspace/TaskRuntimePanel.tsx`, `frontend/app/(workbench)/workspaces/[id]/page.tsx`, `frontend/app/(workbench)/workspaces/[id]/components/RecentArtifacts.tsx` | P1-01 | 用户在首页即可看到任务运行态和产出快照 |
| RV1-01 | Review | 交互评审 | 首页信息架构、移动端、首屏信息密度 | P1-01 ~ P1-06 | thesis 和 sci 两条任务链的首页走查通过 |
| QA1-01 | QA | 首屏回归 | `npm run lint`, `npx tsc --noEmit`, workspace 手工走查 | P1-01 ~ P1-06 | 五类 workspace 页面无 404、无明显布局断裂 |

## 8. Phase 2: Chat 编排 Feature

目标:

- 让 assistant 可以通过 chat 启动 feature
- 在 chat 中承接任务状态和结果回显
- 把 chat 从“对话面板”升级为“任务编排中枢”

退出标准:

1. lead agent 可调用 `run_workspace_feature` 等 workspace 级工具。
2. chat 内可以看到任务卡、结果卡、下一步动作卡。
3. feature 执行与当前 `thread_id` 绑定。
4. 对缺参 feature，assistant 能先补问，不能乱跑默认值。

| ID | 类型 | 任务 | 目标文件 / 范围 | 依赖 | 完成定义 |
|---|---|---|---|---|---|
| P2-01 | BE | 新增 workspace agent tools | 建议新增 `backend/src/tools/builtins/workspace.py`，更新 `backend/src/tools/builtins/__init__.py`, `backend/src/tools/__init__.py`, `backend/src/agents/lead_agent/agent.py` | RV1-01 | 至少提供 `run_workspace_feature`, `list_workspace_features`, `list_workspace_artifacts` |
| P2-02 | BE | 增加 feature 参数桥接层 | 建议新增 `backend/src/agents/lead_agent/feature_bridge.py` 或同级模块，联动 `backend/src/application/handlers/feature_execution_handler.py` | P2-01 | 对高频 feature 有明确参数映射和缺参提示策略 |
| P2-03 | BE | 扩展 chat 消息契约支持结构化 block | `backend/src/gateway/routers/chat.py`, `backend/src/services/chat_thread_service.py` | P2-01 | assistant message 可持久化 `blocks/metadata`，兼容旧纯文本消息 |
| P2-04 | FE | 扩展 chat API 和 store 数据结构 | `frontend/lib/api.ts`, `frontend/stores/chat.ts` | P2-03 | 前端可消费结构化消息块，不破坏旧 thread 数据 |
| P2-05 | FE | 在 `ChatPanel` 中渲染任务卡 / 结果卡 / 下一步卡 | `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`, 复用 `frontend/components/workspace/TaskRuntimePanel.tsx`, `frontend/components/workspace/WorkspaceResultPanel.tsx` | P2-04 | 用户无需跳页就能理解任务状态与结果摘要 |
| P2-06 | FE/BE | 把 quick action 和 chat 编排统一到同一执行入口 | `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`, `frontend/lib/api.ts`, `backend/src/gateway/routers/features.py` | P2-02, P2-05 | 按钮触发和 chat 触发共用同一 feature pipeline 与 thread_id 传递 |
| RV2-01 | Review | 编排策略评审 | 10 条典型指令样本评审 | P2-01 ~ P2-06 | 覆盖“直接执行 / 补问 / 警告 / 跳转深度页”四种路径 |
| QA2-01 | QA | 编排回归 | `backend/tests/gateway/routers/test_chat.py`, `backend/tests/application/handlers/test_feature_execution_handler.py`, 新增 workspace tool tests | P2-01 ~ P2-06 | chat 发起 feature 后可稳定拿到 task / warning / error |

## 9. Phase 3: 记忆闭环与下一步推荐

目标:

- 修复 chat -> long-term memory 闭环
- 明确 thread / workspace / user 三层语义
- 让“下一步推荐”不再只是静态按钮

退出标准:

1. chat 对话的高置信信息可落库。
2. workspace summary 能展示当前阶段、推荐动作、风险。
3. 记忆抽取有降噪策略，不会把低价值对话全量入库。

| ID | 类型 | 任务 | 目标文件 / 范围 | 依赖 | 完成定义 |
|---|---|---|---|---|---|
| P3-01 | BE | 修复 `MemoryQueue` callback 闭环 | `backend/src/agents/memory/queue.py`, `backend/src/agents/middlewares/memory.py` | RV2-01 | debounce 到期后真实触发提取逻辑，而非只缓存消息 |
| P3-02 | BE | 为 memory 抽取补齐 user/workspace 上下文 | `backend/src/gateway/routers/chat.py`, `backend/src/agents/middlewares/memory.py`, `backend/src/agents/thread_state.py` 相关配置链 | P3-01 | 提取时能拿到 `user_id`, `workspace_id`, `thread_id` |
| P3-03 | BE | 明确三层记忆读写策略 | `backend/src/services/knowledge_service.py`, `backend/src/database/models/knowledge.py`, 相关 docs | P3-02 | 区分 user preferences、workspace context、thread history 的写入来源和阈值 |
| P3-04 | BE | 评估并按需引入 `workspace_facts` 独立存储 | 建议新增 `backend/src/database/models/workspace_fact.py`, `backend/alembic/versions/*`, `backend/src/services/workspace_fact_service.py` | P3-03 | 若 `UserKnowledge` 无法稳定承载 workspace facts，再做 schema 分离 |
| P3-05 | BE/FE | 推荐下一步接口与 UI 落地 | `backend/src/services/workspace_summary_service.py`, `frontend/components/workspace/TaskSummaryStrip.tsx`, `frontend/components/workspace/QuickActions.tsx` | P3-03 | 推荐动作根据模块状态、artifact、近期任务动态变化 |
| RV3-01 | Review | 记忆质量评审 | 真实对话样本人工抽查 | P3-01 ~ P3-05 | 错误记忆率、噪音率、漏记率达到可接受阈值 |
| QA3-01 | QA | 记忆与推荐回归 | 新增 `backend/tests/agents/middlewares/test_memory.py` 或同类测试，summary tests | P3-01 ~ P3-05 | 记忆闭环可回归验证，summary 推荐输出稳定 |

## 10. Phase 4: 旧能力回补

目标:

- 把旧仓库高价值能力迁回统一 registry / task / artifact 体系
- 所有回补能力都可被 chat 调用，而不是重新做孤立页面

退出标准:

1. 高优先级旧能力进入 registry。
2. 每个新 feature 都可由 chat 调度、由 task system 承接、由 artifact 沉淀。
3. 至少完成一轮 SCI / Proposal / Thesis 的能力闭环补齐。

### 10.1 回补优先级

| 优先级 | 能力 | 旧仓库依据 | 新仓库建议落点 |
|---|---|---|---|
| P4-A | 同行评审 | `AcademiaGPT/README.md`, `AcademiaGPT/frontend/src/router/index.ts` | `sci.peer_review` |
| P4-A | 文献综述 | `AcademiaGPT/README.md` | `sci.literature_review`, `thesis.literature_review` 或共享 support feature |
| P4-A | 论文框架 / 摘要大纲 | `AcademiaGPT/README.md` | `sci.framework_outline`, `thesis.outline_generation` |
| P4-B | 期刊推荐 | `AcademiaGPT/README.md`, `router/index.ts` | `sci.journal_recommend` |
| P4-B | 实验设计 | `AcademiaGPT/README.md` | `proposal.experiment_design`, `sci.experiment_design` |
| P4-C | AI 配图增强 | `AcademiaGPT/README.md` | 强化 `figure_generation` 或新增 support feature |
| P4-C | 政策分析 | `AcademiaGPT/README.md` | proposal / patent support feature |

### 10.2 回补任务单

| ID | 类型 | 任务 | 目标文件 / 范围 | 依赖 | 完成定义 |
|---|---|---|---|---|---|
| P4-01 | Product/BE | 形成旧能力到新 registry 的映射表 | `backend/src/workspace_features/registry.py`, 本文档 | RV3-01 | 每个回补 feature 有 workspace_type、artifact 类型、task 类型映射 |
| P4-02 | BE | 补 `peer_review` / `journal_recommend` | `backend/src/workspace_features/registry.py`, `backend/src/agents/graphs/sci/*`, `backend/src/workspace_features/services/sci_feature_service.py` | P4-01 | SCI 工作区可通过 chat 和模块页发起评审 / 期刊推荐 |
| P4-03 | BE | 补 `literature_review` / `framework_outline` | `backend/src/workspace_features/registry.py`, 对应 graphs/services | P4-01 | 论文主链关键缺口补齐 |
| P4-04 | BE | 补 `experiment_design` | registry + proposal/sci graphs/services | P4-01 | 支持作为主链旁路 feature 被 chat 调用 |
| P4-05 | FE | 为新增 feature 提供推荐动作与深度页入口 | `frontend/stores/features.ts`, workspace 路由页，`ChatPanel.tsx` | P4-02 ~ P4-04 | 新 feature 不需要额外硬编码入口策略 |
| RV4-01 | Review | 能力 ROI 评审 | 功能价值、复杂度、调用频次复盘 | P4-02 ~ P4-05 | 确认是否继续做 P4-C 类能力 |
| QA4-01 | QA | 新 feature 矩阵回归 | `backend/tests/workspace_features/test_workspace_e2e_matrix.py` 等 | P4-02 ~ P4-05 | 新增 feature 不破坏既有矩阵 |

## 11. Phase 5: 灰度发布与上线 Review

目标:

- 通过灰度方式上线 chat-centered workspace
- 用发布门禁把交互、编排、记忆三条线一起卡住

退出标准:

1. 内测 workspace 通过完整任务走查。
2. Release gate 全绿或有明确豁免。
3. 具备回滚路径。

| ID | 类型 | 任务 | 目标文件 / 范围 | 依赖 | 完成定义 |
|---|---|---|---|---|---|
| P5-01 | Release | 基于现有 `workspace.config` 增加灰度开关 | `backend/src/gateway/routers/workspaces.py`, `backend/src/academic/services/workspace_service.py`, `frontend/stores/workspace.ts` | RV4-01 | 支持按 workspace type 或 `workspace.config` 开启 chat cockpit |
| P5-02 | Release | 先灰度 thesis + sci | 发布配置、运维脚本、文档 | P5-01 | 先在最典型两类任务中验证 |
| P5-03 | Release | 完成全量回归清单 | `docs/product/release-gate-checklist.md` | P5-02 | 对照 release gate 执行并记录结果 |
| RV5-01 | Review | Go/No-Go 发布评审 | 产品、前端、后端、QA | P5-02, P5-03 | 明确放量、继续灰度或回滚 |
| QA5-01 | QA | 发布后观察与回滚演练 | 事件流、task、chat、artifact 观察项 | P5-03 | 任务失败、thread 丢失、记忆异常有明确处置路径 |

## 12. 阶段性 Review 模板

每个阶段的 review 任务至少覆盖以下问题:

1. 用户是否更容易理解“当前阶段”和“下一步”。
2. chat 是否真的减少了页面切换，而不是只把按钮挪进聊天框。
3. feature 编排是否仍走统一 pipeline，没有出现第二套私有执行链。
4. artifact 是否继续作为统一结果落点。
5. thread / memory / task 三条状态链是否一致。

建议 review 输出统一包含:

- 通过项
- 阻塞项
- 不做项调整
- 下一阶段准入条件

## 13. 测试与验收清单

### 13.1 每阶段必跑

后端:

- `cd backend && pytest tests/gateway/routers/test_chat.py`
- `cd backend && pytest tests/application/handlers/test_feature_execution_handler.py`
- `cd backend && pytest tests/gateway/routers/test_dashboard.py`
- `cd backend && pytest tests/workspace_features/test_workspace_e2e_matrix.py`
- `cd backend && ruff check src tests`

前端:

- `cd frontend && npm run lint`
- `cd frontend && npx tsc --noEmit`

### 13.2 关键手工走查

1. Thesis workspace:
   从新建 workspace 到 chat 启动“开题调研 / 论文写作 / 编译导出”。
2. SCI workspace:
   从 chat 启动“文献检索 / 论文分析 / 写作 / 评审 / 期刊推荐”。
3. Proposal workspace:
   从 chat 启动“背景调研 / 申报书大纲 / 实验设计”。
4. Thread 行为:
   主线恢复、新分支创建、切换、删除、事件流同步。
5. Memory 行为:
   用户偏好写入、workspace 稳定事实写入、低价值噪音不过量入库。

## 14. 风险与回滚

### 14.1 主要风险

1. chat 工具编排太激进，导致 assistant 误触发 feature。
2. 结构化消息 block 契约设计不稳，前后端会出现兼容问题。
3. memory 抽取噪音过高，workspace facts 被污染。
4. 旧能力回补如果不先进 registry，会重新形成第二套架构。

### 14.2 控制策略

1. 高风险 feature 首期要求 assistant 明确确认后再执行。
2. chat message block 采用向后兼容 JSON 字段，旧线程继续可读。
3. memory 先做高置信、低频写入，先人工抽查再放量。
4. 能力回补必须以 registry + task + artifact 为准入门槛。

### 14.3 回滚路径

1. 首页层回滚:
   通过 workspace 配置关闭 chat cockpit，退回现有卡片布局。
2. 编排层回滚:
   关闭 lead agent workspace tools，仅保留按钮触发 feature。
3. 记忆层回滚:
   关闭 chat memory persistence，仅保留 feature 完成后的 memory 提取。

## 15. 建议先做的最小可交付组合

如果只做一轮高性价比迭代，建议先交付以下 8 项:

1. `P1-01` 统一 workspace cockpit shell
2. `P1-02` `TaskSummaryStrip`
3. `P1-03` workspace summary 聚合接口
4. `P1-05` 主线 / 分支语义文案调整
5. `P2-01` workspace agent tools
6. `P2-03` chat 结构化消息 block
7. `P2-05` chat 任务卡 / 结果卡
8. `P3-01` memory callback 闭环修复

这 8 项完成后，产品层会第一次真正满足:

- workspace 是完整任务
- chat 是任务驾驶舱
- thread 是任务内主线 / 分支
- memory 开始具备可持续演进的闭环基础
