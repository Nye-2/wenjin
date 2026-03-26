# Continuous Optimization Plan

更新时间: 2026-03-26
状态: Active
适用项目: `academiagpt-v2`

## 1. 目标

本计划不是一次性“收尾计划”，而是面向长期迭代的持续优化机制，目标覆盖:

1. 跑通主链和所有关键全链路。
2. 跑通五类 workspace 下所有功能模块。
3. 持续清理技术债务和死代码。
4. 收敛架构偏移，统一事实源和边界。
5. 提升代码规范性、测试覆盖、运行稳定性和可维护性。

## 2. 当前基线

基于当前仓库代码，项目已经具备以下基础:

- 五类 canonical workspace:
  `thesis` / `sci` / `proposal` / `software_copyright` / `patent`
- `workspace feature registry` 已形成单一事实源:
  `backend/src/workspace_features/registry.py`
- 当前 registry 共 20 个 canonical feature
- 主执行入口已收敛到:
  `POST /api/workspaces/{workspace_id}/features/{feature_id}/execute`
- chat cockpit rollout 默认已覆盖五类 workspace:
  `frontend/lib/workspace-rollout.ts`
- 前端已具备 workspace 驾驶舱首页、chat panel、task summary、feature 深度页
- 已有基础 smoke / matrix 测试:
  `backend/tests/workspace_features/test_five_workspace_smoke.py`
  `backend/tests/workspace_features/test_workspace_e2e_matrix.py`

当前仍然存在的现实问题:

1. “能执行”不等于“全链路完备”，部分 feature 还缺少更细粒度的 service 测试、artifact 验证和 chat 编排验证。
2. 各 workspace 的实现深度不均衡，当前 thesis 相关测试和细化实现明显更完整。
3. chat 虽已恢复为驾驶舱主入口，但“自动补参 + 自动调度 feature + 结果结构化回写”仍需继续打磨。
4. 基础设施层已显露出单例生命周期、双事实源、重复入口、历史兼容残留这类长期债务风险。
5. 文档、测试、代码边界需要形成持续同步机制，而不是靠阶段性回顾补漏。

### 2.1 2026-03-26 Checkpoint

本轮新增确认与修复:

1. `ExecutionMiddleware` 已从“实现存在但未接线”修成 lead agent 真正可用的 tool runtime。
2. `DynamicToolNode` 已支持 tool 级 middleware hook，`before_tool/after_tool` 不再是空接口。
3. lead agent 可以按 middleware 能力选择性暴露 execution tools，避免污染 subagent 运行时。
4. memory runtime 已补齐 chat capture 默认开启、recent-context 排序和精确 token 预算。
5. subagent graph / executor / API 默认配置已统一切到带 execution middleware 的 runtime。
6. task 级 `system_prompt/tools` 现在会真实进入 subagent graph，而不是只停留在 payload。
7. backend 全量回归当前为 `2282 passed, 6 skipped`。

本轮详细 review 记录见:

- `docs/product/migration-phase-review-2026-03-26.md`

## 3. 非协商规则

后续所有优化都必须遵守以下规则:

1. 不新增旁路主链。新能力只能接入 canonical workspace feature pipeline。
2. 不恢复已移除的 legacy route / legacy task type /兼容入口。
3. 不允许业务参数重新平铺到 task payload 顶层，`params` 继续作为业务输入唯一来源。
4. 不允许把 workspace 退化成 session，thread 继续作为 workspace 内会话主线或分支。
5. 每次改动都必须顺手清理死代码、重复状态源和无效适配层。
6. 每个阶段都必须带 review 任务，review 不是收尾附属动作，而是阶段内必做项。

## 4. 持续优化工作流

本项目采用“主线推进 + 债务偿还 + 阶段 review”三轨并行方式，而不是只做功能堆叠。

### 4.1 每轮迭代固定动作

每轮必须至少完成:

1. 一个主链目标:
   跑通一个新的端到端场景，或补齐一个 workspace 的完整 feature 面。
2. 一个债务目标:
   删除死代码、收敛事实源、统一契约、减少重复入口或修正架构偏移。
3. 一个质量目标:
   补测试、补类型约束、补文档、补观测或补自动化校验。

### 4.2 每轮收尾固定 review

每轮开发结束必须执行:

1. 变更文件 review:
   看是否引入新双事实源、旁路入口、重复数据模型或生命周期隐患。
2. 死代码 review:
   删除已失效路由、旧 contract、无引用 helper、冗余适配层。
3. 回归 review:
   至少运行改动相关 focused tests；涉及主链时补跑 workspace matrix / gateway / task / mcp 相关回归。
4. 文档 review:
   若契约、入口、架构边界变化，必须同步更新 docs。
5. Backlog review:
   重新排序下一轮优先级，不让 backlog 失真。

### 4.3 阶段 review 节点

每个 phase 固定包含三次 review:

1. Phase Start Review:
   确认当前事实源、目标边界、不可回退项。
2. Mid-Phase Review:
   检查是否出现双轨执行、临时适配层固化、事实源分叉。
3. Exit Review:
   检查是否满足退出标准，是否还有死代码和文档漂移未清理。

## 5. 长期优化主线

### Phase 0: Baseline Stabilization

目标:

- 保证 gateway / worker / langgraph / nginx / postgres / redis 的运行主链稳定
- 保证 DB、Redis、MCP、任务执行器等基础生命周期没有 fork / loop / readiness 类问题
- 保证 compose、镜像、健康检查和本地开发入口一致

关键任务:

1. 清点所有运行时单例与进程边界对象，持续收敛生命周期。
2. 清理重复入口、重复初始化、重复注册信号等基础设施债务。
3. 保持 `/livez`、`/readyz`、worker ping、nginx 代理健康检查可用。
4. 固化 backend image、依赖安装、compose 复用和容器启动语义。

阶段 review:

1. 基础设施入口 review
2. 生命周期与单例 review
3. readiness / observability review

退出标准:

- 核心容器稳定 healthy
- worker 可稳定消费任务
- 健康检查真实反映依赖状态

### Phase 1: Full-Link Closure

目标:

- 跑通“创建 workspace -> 进入 chat / 模块 -> 启动 feature -> task -> artifact -> dashboard / summary / thread 回写”的主用户链路
- 让 chat 和模块页都成为同一主链的不同入口，而不是两套行为

关键任务:

1. 补齐 main thread 自动恢复、branch thread 基本语义和 chat 上下文一致性。
2. 补齐 feature completion card、artifact 二次执行、继续追问、直接跳转这类闭环动作。
3. 补齐 paper / artifact / task / summary 刷新的串联关系。
4. 把主链里还残留的同步旁路或临时适配层纳入统一 application + task 编排。

阶段 review:

1. chat-centered mainline review
2. task writeback / artifact writeback review
3. workspace summary / dashboard consistency review

退出标准:

- 用户从 chat 或模块页都能完成完整任务闭环
- 任务、artifact、summary、thread 状态一致

### Phase 2: Workspace Feature Parity

目标:

- 五类 workspace 的所有 feature 都达到“可发现、可执行、可回写、可跳转、可测试”的统一标准

统一验收模板:

1. registry 已注册
2. 前端可发现并可导航
3. 后端有 canonical execute path
4. 结果能写入 artifact 或明确写回目标
5. chat 卡片支持继续推进
6. 有 focused tests

建议推进顺序:

1. `thesis`
2. `sci`
3. `proposal`
4. `software_copyright`
5. `patent`

说明:

- 当前 thesis 能力最深，适合作为标杆。
- 当前 workspace smoke 已覆盖五类代表 feature，但 service 级和 artifact 级覆盖仍不均衡，应向非 thesis workspace 补齐。

阶段 review:

1. 每完成一个 workspace，做一次 workspace-specific review
2. 每补完一类 feature，做一次 registry / route / artifact / test 四联 review
3. 全部 workspace 补齐后，做一次 matrix exit review

退出标准:

- 五类 workspace 的所有 feature 均满足统一验收模板
- 不再存在“已展示但不可执行”或“已执行但无回写”的 feature

### Phase 3: Chat-Centered Orchestration

目标:

- 让 chat 真正成为任务驾驶舱，而不是仅作为消息面板

关键任务:

1. 完善 feature bridge 的意图识别、最小补参和执行确认。
2. 统一 assistant 任务建议卡、运行卡、结果卡、next-step 卡的结构。
3. 建立 thread memory / workspace memory / user memory 的产品边界和服务边界。
4. 让 chat 能驱动 feature 启动、继续追问、基于 artifact 二次执行。
5. 补齐 branch thread 的用户体验和恢复策略。

阶段 review:

1. chat intent / feature routing review
2. memory boundary review
3. thread UX review

退出标准:

- chat 成为 workspace 默认入口
- feature orchestration 不依赖硬编码快捷按钮
- thread 与 workspace 的职责边界清晰

### Phase 4: Architecture Debt Paydown

目标:

- 收敛恶性架构偏移，减少双轨执行和多事实源

重点债务类型:

1. 同一能力存在多条执行主链
2. payload / artifact / summary / dashboard 存在多处事实源
3. router、application、task、service 边界回流
4. legacy compatibility 代码已无业务价值但仍驻留主仓
5. workspace feature 与前端视图之间存在手工映射漂移

关键任务:

1. 系统性删除死代码和无效兼容层。
2. 收敛 canonical artifact contract，避免同一 feature 多种结果形态并存。
3. 收敛 workspace summary、dashboard、thread status 的事实源。
4. 用 ADR 和 architecture tests 固化边界。

阶段 review:

1. architecture drift review
2. fact-source review
3. dead-code removal review

退出标准:

- 主链不再出现双轨执行
- 关键实体只有一个 authoritative source
- 边界约束可被测试守住

### Phase 5: Quality and Standards

目标:

- 提高代码规范性、测试深度和长期可维护性

关键任务:

1. 补齐 workspace feature service tests，尤其是 `sci` / `proposal` / `software_copyright` / `patent`。
2. 扩展 gateway / task / mcp / execution / frontend store 的 focused regression 套件。
3. 收敛命名、目录、contract、schema version、错误处理格式。
4. 强化类型约束、lint、architecture tests、dead import / dead route 检测。
5. 文档与代码一起演进，避免 README 和真实实现偏离。

阶段 review:

1. test coverage review
2. naming / contract review
3. docs freshness review

退出标准:

- 新 feature 和重构默认带测试
- 文档能反映真实主链
- lint / type / focused regression 成为默认门禁

### Phase 6: Infrastructure and Operations Hardening

目标:

- 让系统在可部署、可恢复、可观测方面持续稳定

关键任务:

1. 持续补强 MCP server 生命周期、tool load/cache、OAuth runtime 注入链路。
2. 强化 Docker、Celery、Redis、Postgres、LangGraph 的启动和恢复策略。
3. 补齐监控指标、错误聚合、任务运行态和关键依赖告警。
4. 固化部署 runbook、故障排查 runbook 和环境变量文档。
5. 进行定期故障演练:
   worker 重启、redis 断连、MCP server 不可用、task 中断恢复。

阶段 review:

1. runtime resilience review
2. deployment review
3. observability review

退出标准:

- 常见故障可被检测、定位、恢复
- 运维文档和实际部署方式一致

## 6. Workspace 优化矩阵

后续所有 workspace 都按同一张矩阵推进:

| 维度 | 检查项 |
|---|---|
| Feature Catalog | registry、前端展示、路由映射一致 |
| Execute Path | API、application handler、task handler、graph/service 一致 |
| Artifact | 有 canonical result 和明确 artifact 落点 |
| Chat | 可从 chat 启动、查看结果、继续推进 |
| Dashboard | summary、progress、recent activity、risk 能反映执行结果 |
| Testing | smoke、service、handler、artifact、UI 行为至少覆盖核心路径 |
| Docs | feature catalog、API map、实施文档同步 |

## 7. 优先级排序规则

当 backlog 很大时，按以下优先级执行:

1. 先修主链断点和数据不一致问题
2. 再补 workspace 功能短板和全链路闭环
3. 再清理会继续放大成本的架构债务
4. 最后做纯视觉或局部 polish

更具体地说:

- 影响运行稳定性的问题，高于新功能
- 影响所有 workspace 的共性债务，高于单个页面小问题
- 能消除双事实源的问题，高于仅增加一层兼容代码

## 8. 持续衡量指标

每轮都要关注以下指标:

1. workspace feature 覆盖率:
   20 个 feature 中，多少已完成“发现 + 执行 + 回写 + chat + 测试”
2. workspace 完整度:
   五类 workspace 中，多少已具备完整任务闭环
3. 主链健康度:
   compose health、worker ping、gateway readyz、nginx readyz
4. 回归健康度:
   workspace smoke、matrix、task、gateway、mcp focused suites
5. 债务清理率:
   每轮删除的 dead code、旧入口、重复 contract 数量
6. 文档同步率:
   契约变更后文档是否同步更新

## 9. 立即执行的下一阶段建议

从当前仓库状态出发，下一阶段建议按以下顺序推进:

1. 建立 20 个 feature 的完整验收清单:
   registry / route / execute / artifact / chat / tests 六栏逐项盘点。
2. 先把五类 workspace 的 service-level tests 补齐到同一层级，不再只有 thesis 更完整。
3. 把 chat orchestration 的补参与 feature bridge 进一步收紧，减少“能聊但不能稳定发起任务”的灰区。
4. 持续清理 application / task / workspace summary / artifact 的多事实源和重复状态。
5. 把基础设施的 lifecycle、故障恢复、MCP runtime 和运行观测继续做厚。

## 10. 执行方式

本计划作为 living document 使用:

1. 每次进入新 phase 前，先更新本文件的“当前重点”。
2. 每完成一个阶段 review，补记录结论和剩余风险。
3. 每次发现新的恶性架构偏移，先写入本文件，再纳入后续迭代，不允许口头 backlog 漂移。

本文件与以下文档配合使用:

- `docs/product/workspace-chat-centered-implementation-plan.md`
- `docs/product/workspace-chat-centered-redesign.md`
- `docs/architecture/workspace-execution-pipeline.md`
- `docs/architecture/adr-platform-boundaries.md`
- `docs/product/release-gate-checklist.md`
