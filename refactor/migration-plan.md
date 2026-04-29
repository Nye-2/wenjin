# 一次性迁移计划

更新时间：2026-04-29
状态：Completed
适用范围：`/home/cjz/wenjin`

## 0. 当前进度快照

更新时间：2026-04-29 11:20 CST

已完成：

1. Phase 0 文档和目标架构沉淀。
2. Phase 1 feature runtime profile，所有 registry feature 均有 profile，`FeatureLeaderRuntime.workflow.py` 不再维护复杂 feature 硬编码集合。
3. Phase 2 `ChatTurnRouter` 与 `FeatureCommandHandler`，显式 launch/resume 绕过 lead-agent。
4. Phase 3 `ComputeSession`、compute projection、workspace event、compute read API。
5. Phase 4 前端 Compute Stage 初版、compute store、event hydrate、刷新恢复。
6. Phase 5 删除旧 pure chat `run_workspace_feature` tool loop 和旧 confirmation replay。
7. Phase 6 初版 `AgentHarness` contract 与 `NativeWenjinAgentHarness`，feature leader 不再直接构造 subagent executor；agentic workflow 缺少 `execution_session_id` 会直接失败，不再生成 `adhoc-*` session；workflow 失败不再 fallback 到 direct graph。
8. Phase 6.5 清理旧控制面和死代码：删除 public subagent API、lead-agent `task` subagent tool、thread message 反推 execution 的前端逻辑、旧 `FeaturePanelHost` 工作台、旧 feature redirect shell，并将 thread feature card presenter 移出 `agents/lead_agent`。
9. Phase 7 第一段：Compute projection 已从 `ExecutionSession`、`TaskRecord`、runtime blocks 中归一化 `sandbox`、`files`、`logs`、`review_gate`，前端 `ComputeStage` 已展示 sandbox 文件、执行日志和 review gate，不再只展示 task/artifact id。
10. Phase 7 第二段基础切片：Compute projection 已显式投影 WenjinPrism 关系，包括 `latex_project_id`、主文件、目标文件、compile 状态和 file changes；`open_prism` 被归类为非阻塞后续入口，不再误判为 required review gate。
11. Phase 7 Prism 待确认写入处理切片：Compute projection 已以 Prism 项目当前 metadata 刷新 file changes，前端 ComputeStage 可直接对 Prism 待确认写入执行 discard / apply，处理后刷新 projection。
12. Phase 7 Prism 写入门禁切片：workspace LaTeX bridge 不再对已有 Prism 文件执行“安全直写”；已有文件内容变化统一进入 Prism 待确认写入队列，新建项目初始化仍允许一次性 seed；带待确认写入的 compile 流程会返回 `blocked_by_review`，避免编译旧稿。
13. Phase 7 Prism file-change API 切片：旧 `resolve-conflict` 路径已替换为 `file-changes/preview|apply|discard|revert`；apply 必须使用 preview 产生的签名，revert 使用 apply 后写入 metadata 的 undo payload 做 hash 校验。
14. Phase 7 Prism 前端闭环切片：Compute projection 透出 `applied_file_changes`；ComputeStage 和 WenjinPrism 均可预览 file-change diff、应用/丢弃待确认写入，并对已应用写入执行带签名和 hash 校验的撤回。
15. Phase 8 文档收口切片：`docs/architecture`、`docs/product`、根 README、backend/frontend README 已改为 ChatTurnRouter / FeatureIngressService / ComputeSession / WenjinPrism 当前事实源；新增文档守卫测试防止旧 chat-feature tool loop 文案回流。
16. 最终收口切片：前端 feature resume metadata 改由 active `ExecutionSession` 生成，不再从 assistant message metadata 反推；feature graph registry 从旧的 workspace lead-agent 命名迁入 `agents/feature_leader/graph_registry.py`，并新增架构守卫。

待继续：

1. 无迁移阻塞项；后续只保留常规产品迭代与回归。

## 1. 迁移前提

1. 当前项目仍处于开发阶段，没有真实用户。
2. 不需要兼容旧数据、旧 API、旧前端行为或旧 chat-feature tool loop。
3. 允许破坏性修改表结构、接口、前端状态、测试和文档。
4. 不设计 fallback、兼容层、灰度、双写、旧入口转发或旧链路保留。
5. 迁移完成后，旧实现应删除或重写，避免新旧链路共存。

## 2. 迁移目标

迁移完成后必须达到：

```text
Chat = control plane
Compute = work plane
FeatureIngress = domain ingress
ExecutionSession = feature source of truth
TaskService = async execution source of truth
AgentHarness = optional execution capability inside Compute
```

验收规则：

1. 显式 feature launch 不调用 lead-agent。
2. feature resume 不新建 execution session。
3. pure chat 不创建 task record。
4. pure chat 不暴露 `run_workspace_feature` 自由执行工具。
5. subagent 没有 `execution_session_id` 不能运行。
6. Compute 当前状态不从 thread message 推断。
7. Artifact 只通过 feature/artifact contract 写回。
8. Chat 可缩小或关闭，Compute task 继续运行。
9. Compute 可恢复，状态来自 execution session、task、artifact、activity、subagent projection。

## 3. 总体迁移顺序

```text
Phase 0: 文档与冻结旧方向
Phase 1: 后端 feature runtime profile
Phase 2: ChatTurnRouter 和 FeatureCommandHandler
Phase 3: ComputeSession 与 projection
Phase 4: 前端 Compute Stage
Phase 5: 移除旧 chat-feature tool loop
Phase 6: AgentHarness 抽象
Phase 6.5: 旧控制面和死代码清理
Phase 7: Sandbox/文件/日志产品化
Phase 8: 测试和文档收口
```

## 4. Phase 0：文档与冻结旧方向

目标：

- 明确本轮迁移不保留旧链路。
- 将未来改动统一对齐到 `refactor/target-architecture.md`。

动作：

1. 新增本目录和目标架构文档。
2. 新增一次性迁移计划文档。
3. 在后续代码改动 PR 中引用本目录为目标事实源。
4. 暂停继续增强旧 `run_workspace_feature` chat tool loop。
5. 暂停继续在 `FeatureLeaderRuntime.workflow.py` 中硬编码复杂 feature 规则。

完成标准：

- `refactor/README.md`
- `refactor/target-architecture.md`
- `refactor/migration-plan.md`

## 5. Phase 1：后端 feature runtime profile

目标：

- 每个 feature 的执行模式、agent policy、sandbox policy、review gate 回到 registry/profile。
- 删除散落在 feature leader workflow 中的 feature 分类硬编码。

新增：

```text
backend/src/workspace_features/runtime_profiles.py
```

建议结构：

```python
class FeatureRuntimeMode(str, Enum):
    CHAT_ONLY = "chat_only"
    DETERMINISTIC = "deterministic"
    COMPUTE_WORKFLOW = "compute_workflow"
    COMPUTE_AGENTIC = "compute_agentic"

@dataclass(frozen=True, slots=True)
class FeatureRuntimeProfile:
    workspace_type: str
    feature_id: str
    runtime_mode: FeatureRuntimeMode
    requires_compute: bool
    requires_sandbox: bool
    allowed_subagents: tuple[str, ...] = ()
    max_subagents: int = 0
    agent_harness_provider: str | None = None
    output_contract: str = "feature_result"
    review_gate: str | None = None
```

修改：

```text
backend/src/workspace_features/registry.py
backend/src/agents/feature_leader/workflow.py
backend/src/agents/feature_leader/runtime.py
```

动作：

1. 为所有 23 个 feature 建立 runtime profile。
2. 从 `workflow.py` 删除 `_COMPLEX_FEATURES`。
3. `FeatureLeaderRuntime` 只读取 profile 决定是否运行 agentic workflow。
4. 非 agentic feature 不允许启动 subagent fanout。
5. 写测试覆盖 profile 完整性：registry 中每个 feature 都有 profile。

完成标准：

- 没有硬编码复杂 feature 集合。
- 新增 feature 时测试会强制要求 runtime profile。

## 6. Phase 2：ChatTurnRouter 和 FeatureCommandHandler

目标：

- 显式 feature launch/resume 绕过 lead-agent。
- Chat 只作为入口和控制台。

新增：

```text
backend/src/application/handlers/chat_turn_router.py
backend/src/application/handlers/feature_command_handler.py
```

Turn mode：

```text
pure_chat
feature_launch
feature_resume
feature_status
feature_proposal
```

动作：

1. 在 `ThreadTurnHandler.prepare_turn` 后、`generate_thread_response` 前插入 `ChatTurnRouter`。
2. `metadata.orchestration.intent=launch` 直接调用 `FeatureCommandHandler.launch`。
3. `metadata.orchestration.intent=resume` 直接调用 `FeatureCommandHandler.resume`。
4. feature command 分支调用 `FeatureIngressService`。
5. feature command 分支只写 thread pointer card，不调用 `make_lead_agent`。
6. pure chat 分支保留当前 lead-agent 能力。
7. `ensure_thread_turn_budget` 只在 pure chat 分支执行。

需要重写：

```text
backend/src/application/handlers/thread_turn_handler.py
backend/src/runtime/runs/worker.py
backend/src/gateway/routers/thread_runs.py
backend/src/gateway/routers/runs.py
```

完成标准：

- 显式 launch/resume 测试断言 `make_lead_agent` 未调用。
- pure chat 测试断言没有 task record 创建。
- feature command 测试断言写入 assistant pointer card。
- feature resume 测试断言复用原 execution session。

## 7. Phase 3：ComputeSession 与 projection

目标：

- 将 execution session 投影为用户可见 Compute 工作台。
- Compute 不成为第二套业务事实源。

新增：

```text
backend/src/compute/__init__.py
backend/src/compute/models.py
backend/src/compute/session_service.py
backend/src/compute/projection_service.py
backend/src/compute/events.py
backend/src/compute/sandbox_projection.py
backend/src/gateway/routers/compute.py
```

数据库：

开发阶段允许破坏性 migration。可新增：

```text
compute_sessions
  id
  execution_session_id
  workspace_id
  user_id
  sandbox_session_id
  active_view
  ui_state
  created_at
  updated_at
```

动作：

1. `FeatureIngressService.launch` 创建 execution session 后创建 compute session。
2. `FeatureIngressService.resume` 查找并复用同一 compute session。
3. `ComputeProjectionService` 聚合 execution session、task、runtime、subagents、artifacts、activity。
4. 发布 `compute.updated` 和 `compute.step` workspace events。
5. 新增 compute read API：

```text
GET /api/workspaces/{workspace_id}/compute/sessions
GET /api/compute/sessions/{compute_session_id}
GET /api/compute/sessions/{compute_session_id}/projection
```

完成标准：

- 前端可不读 thread message 获得当前 compute 状态。
- execution session 完成、失败、awaiting_user_input 都能投影到 compute。

## 8. Phase 4：前端 Compute Stage

目标：

- 参考 Kimi Computer 交互，将长任务主展示面从 chat message 中移到 Compute Stage。

新增：

```text
frontend/components/compute/
frontend/stores/compute.ts
frontend/hooks/useComputeSession.ts
frontend/hooks/useComputeEvents.ts
```

动作：

1. Workspace workbench 中新增 Compute Stage 区域。
2. feature launch 后自动展开 Compute Stage。
3. Compute Stage 支持展开、缩小、恢复。
4. Compute Stage 展示：

```text
runtime blocks
phase timeline
task progress
subagent timeline
sandbox file tree
logs
artifacts
review gate
```

5. Chat message 中只显示启动、追问、完成、失败卡片。
6. Activity、artifact follow-up 点击后恢复对应 compute session。

完成标准：

- 长任务过程不再堆在 ThreadPanel 消息区。
- 刷新页面后可恢复正在运行或最近的 compute session。

## 9. Phase 5：移除旧 chat-feature tool loop

目标：

- 删除旧的由 pure chat lead-agent 自由调用 `run_workspace_feature` 执行 feature 的路径。

动作：

1. pure chat `get_available_tools` 不再注册 `run_workspace_feature_tool`。
2. `run_workspace_feature_tool` 如保留，只允许在内部 feature command/runtime 测试场景使用。
3. 删除 prompt 中要求 lead-agent 优先调用 `run_workspace_feature` 的执行策略。
4. 将 lead-agent 对 feature 的输出改为 `feature_proposal`，由用户确认后走 `ChatTurnRouter(feature_launch)`。
5. 删除旧 confirmation 依赖 chat tool call 的逻辑。
6. 删除旧 direct/indirect feature bridge 残留说明。

涉及：

```text
backend/src/agents/lead_agent/agent.py
backend/src/tools/builtins/workspace.py
backend/src/application/services/thread_feature_service.py
backend/src/agents/lead_agent/thread_feature_cards.py
backend/src/workspace_features/skills.py
```

完成标准：

- pure chat agent tool schema 中没有 `run_workspace_feature`。
- 显式 feature 仍能通过 FeatureCommandHandler 启动。
- lead-agent 只能建议 feature，不直接执行 feature。

## 10. Phase 6：AgentHarness 抽象

目标：

- 把 DeerFlow、native subagent、Claude/Codex SDK 都收束为 Compute 内部 provider。

新增：

```text
backend/src/agents/harness/__init__.py
backend/src/agents/harness/contracts.py
backend/src/agents/harness/native.py
backend/src/agents/harness/deerflow_adapter.py
backend/src/agents/harness/claude_agent_adapter.py
backend/src/agents/harness/codex_adapter.py
```

动作：

1. 定义 `AgentHarness` protocol。
2. 定义 `SubtaskRequest`、`SubtaskResult`、`AgentSessionRequest`、`AgentSessionResult`。
3. native subagent 先实现默认 provider。
4. `FeatureLeaderRuntime` 不直接依赖 subagent manager，改依赖 harness。
5. DeerFlow adapter 初期只接 skills/tools/subagents，不接管主服务。
6. Claude/Codex adapter 暂以接口占位，后续按 feature profile 启用。

输出 contract：

```text
evidence_pack
draft_pack
review_pack
file_change_pack
diagnostic_pack
```

完成标准：

- feature runtime 不关心底层 provider 是 native、DeerFlow、Claude 还是 Codex。
- harness 输出不能直接写 artifact，必须回到 feature runtime 汇总。

## 11. Phase 6.5：旧控制面和死代码清理

目标：

- 在继续做 Compute 产品化前，删除会造成第二控制面的旧入口和旧 UI。
- 确保 subagent 只能通过 Compute 内部的 `AgentHarness` 运行。
- 确保前端不再从 thread message metadata 推断当前 execution 状态。

动作：

1. 删除 `/api/subagents/*` public router、mount 和 API 测试。
2. 删除 lead-agent `task` tool 注册、`subagent_enabled` runtime config、`SubagentLimitMiddleware` 和 `src/subagents/task_tool.py`。
3. 删除 frontend `maybeHydrateStructuredExecution` placeholder execution hydration。
4. 删除旧 `FeaturePanelHost` 及只服务于它的 panel/workbench/result/workflow 组件。
5. 删除 `/workspaces/[id]/features/[featureId]` redirect shell。
6. 将 thread feature card builders/presenters 迁到 `src/application/presenters`。

完成标准：

- main gateway 不挂载 public subagent task creation surface。
- pure chat lead-agent tool schema 中没有 `run_workspace_feature` 和 `task`。
- `FeaturePanelHost`、旧 feature redirect shell、message-derived execution placeholder 不存在。
- feature result pointer card 仍保留，但归属 application presenter 层。

## 12. Phase 7：Sandbox/文件/日志产品化

目标：

- 将现有 sandbox 能力变成 Compute 可视化能力。
- 第一段先不新增业务事实源和数据库 schema，只从 execution/task/runtime 现有持久化数据投影出工作面能力。

动作：

1. 定义 `SandboxSession` projection。已完成第一段：`ComputeProjectionService` 输出 `sandbox.status/session_id/files/logs/file_count/log_count`。
2. 统一 virtual path、public URL、file refs。已完成第一段：projection 从 artifact ids、sandbox path、public URL、output files 中归一化 `files[]`。
3. Compute Stage 展示文件树、日志、预览、diff。已完成第一段：展示 sandbox 文件和执行日志；预览/diff 留到第二段。
4. 写作/LaTeX 类 feature 接入 review gate：

```text
preview -> apply -> revert
```

5. terminal/browser/code runner 初期只读展示，不开放任意用户命令入口。已完成第一段：仅展示执行日志和文件链接。
6. artifact promote 必须经过 artifact contract。
7. review gate 由 execution `next_actions/advisory_code` 归一化为 `status/required/items`，前端只消费 projection，不回读 thread message。
8. WenjinPrism 作为主稿工程事实源；Compute 只投影 Prism 关联、目标文件、编译状态、冲突和入口，不直接编辑 Prism 文件。
9. Compute 可处理 Prism file changes：discard 保护用户当前文件，apply 接受 feature 生成内容，处理后以 Prism metadata 为准刷新 projection。
10. workspace LaTeX bridge 对已有文件变化只登记待确认写入，不再自动覆盖；`reason=feature_proposal` 表示非冲突生成更新，`reason=user_modified/user_protected` 表示需要用户确认的稿件差异。
11. 带待确认写入的 compile 任务返回 `blocked_by_review`，必须先在 Compute 或 WenjinPrism 中确认写入，再编译主稿。
12. Prism file-change 写入 API 为 `preview -> apply -> discard/revert`；`apply` 校验 preview 签名，`revert` 校验 applied hash，避免绕过 review gate 或覆盖用户后续编辑。

完成标准：

- 用户能在 Compute 中看到任务生成了哪些文件。第一段完成。
- 用户能在 Compute 中看到运行日志、runtime activity、task error。第一段完成。
- 文件写回有 review gate。已有 Prism 文件变化已进入待确认写入队列，并已完成结构化 diff preview 与 apply 后 revert。
- artifact 与 sandbox 临时文件边界清晰。第一段通过 `kind=artifact/sandbox_file/linked_file/output_file` 区分；第二段补预览和 promote contract。
- 写作/LaTeX feature 与 Prism 的边界清晰。`prism` projection、已有文件强制写入门禁和独立 file change pack 已完成。
- Prism 冲突可以在 Compute 工作面直接处理，且 projection 不再受旧 task result 的过期冲突影响。

## 13. Phase 8：测试和文档收口

目标：

- 删除旧测试假设。
- 建立新架构守卫测试。
- 更新当前事实源文档。

必须新增测试：

```text
test_chat_turn_router.py
test_feature_command_handler.py
test_compute_projection_service.py
test_compute_events.py
test_feature_runtime_profiles.py
test_agent_harness_contracts.py
```

必须修改测试：

```text
backend/tests/application/handlers/test_thread_turn_handler.py
backend/tests/gateway/routers/test_threads_router.py
backend/tests/application/services/test_feature_launch_service.py
backend/tests/task/test_workspace_feature_runtime.py
```

必须删除或重写：

- 任何依赖 pure chat lead-agent 直接调用 `run_workspace_feature` 的测试。
- 任何把 thread message 当作 feature 当前状态事实源的测试。
- 任何允许 subagent 缺失 `execution_session_id` 执行的测试。
- public subagent API 和 lead-agent `task` tool 相关测试。

文档更新：

```text
README.md
docs/architecture/tech-stack-and-main-chain.md
docs/architecture/workspace-execution-pipeline.md
docs/architecture/feature-domain-architecture.md
docs/product/workspace-current-state.md
docs/product/frontend-feature-plugin-contract.md
docs/documentation-map.md
```

完成标准：

- 文档只描述新架构。
- 旧 chat-feature tool loop 不再作为当前事实源出现。
- 测试覆盖新主链。

## 14. 建议执行顺序明细

建议按以下提交粒度推进：

1. `refactor-docs`: 新增 `refactor/` 文档。
2. `runtime-profiles`: 新增 feature runtime profiles，删除 feature complexity 硬编码。
3. `turn-router`: 新增 ChatTurnRouter，显式 launch/resume 绕过 lead-agent。
4. `feature-command`: 新增 FeatureCommandHandler，统一写 chat pointer card。
5. `compute-backend`: 新增 ComputeSession、projection、events、API。
6. `compute-frontend`: 新增 Compute Stage 和 store。
7. `remove-chat-tool-loop`: pure chat 移除 `run_workspace_feature` 自由工具。
8. `agent-harness`: 新增 AgentHarness protocol 和 native provider。
9. `dead-code-cleanup`: 删除旧 public subagent API、lead-agent subagent tool、旧工作台和旧 redirect shell。
10. `sandbox-projection`: Compute 接入 sandbox files/logs/review gate。
11. `docs-tests-cleanup`: 更新文档、删除旧测试、补新测试。

由于没有真实用户，不需要在提交之间维持旧链路可用。每个提交只需保证新目标态逐步收敛，最终提交后全量测试通过。

## 15. 删除清单

迁移过程中应主动删除：

1. pure chat prompt 中的 feature 执行指令。
2. pure chat tool schema 中的 `run_workspace_feature`。
3. 旧 confirmation 依赖 tool call 的路径。
4. 旧 direct feature bridge 文档残留。
5. `workflow.py` 中硬编码 `_COMPLEX_FEATURES`。
6. thread message 作为 feature 当前状态来源的前端逻辑。
7. 任何为旧链路保留的 compatibility route、adapter 或 fallback。
8. public subagent task creation API。
9. lead-agent `task` subagent delegation tool。
10. 旧 `FeaturePanelHost` 工作台和旧 feature redirect shell。

## 16. 风险和处理

### 16.1 一次性迁移会破坏现有前端流程

处理：

```text
接受破坏。前端同步迁移到 Compute Stage，不保留旧 ThreadPanel 长任务展示。
```

### 16.2 测试会大面积失败

处理：

```text
接受破坏。删除旧行为测试，重写新架构守卫测试。
```

### 16.3 数据库 migration 可能破坏本地数据

处理：

```text
接受破坏。开发阶段允许清库或重建迁移，不设计旧数据兼容。
```

### 16.4 AgentHarness 抽象过早复杂化

处理：

```text
先只实现 NativeWenjinAgentHarness。DeerFlow/Claude/Codex adapter 保持薄接口，不提前接管主链。
```

## 17. 最终验收

全局验收清单：

1. `metadata.orchestration.intent=launch` 不调用 `make_lead_agent`。
2. `metadata.orchestration.intent=resume` 不调用 `make_lead_agent`。
3. pure chat 不创建 execution session、compute session 或 task record。
4. feature launch 创建 execution session 和 compute session。
5. feature resume 复用 execution session 和 compute session。
6. Compute Stage 可以展示 running、awaiting_user_input、completed、failed。
7. Thread message 只保存 pointer card。
8. feature 状态从 compute projection 查询。
9. subagent 必须绑定 execution session。
10. artifact 写回只走 artifact contract。
11. pure chat billing 和 feature billing 分离，二者都从 `services/billing_policy.py` 按 token usage 结算。
12. 旧 chat-feature tool loop 已删除。
