# 目标架构：Wenjin Compute Architecture

更新时间：2026-04-29
状态：Current
适用范围：`/home/cjz/wenjin`

## 1. 背景

问津曾经把 chat、feature 触发、确认、stream、billing、memory capture、状态投影和部分 subagent 能力压在同一条执行链路上。这解决了早期 workflow 能力的产品化问题，但也让 chat 从用户入口侵入 feature 执行域，引起架构漂移。

当前架构已将系统收敛为：

```text
Chat 负责问与控，Compute 负责做与看，Feature 负责交付。
```

即：

```text
Chat Control Plane
  -> Compute Work Plane
    -> Feature Transaction Plane
      -> Agent / Sandbox Execution Plane
        -> Artifact / Activity / Knowledge Plane
```

## 2. 核心目标

1. 保留 chat 作为统一用户入口，但移除 chat 对 feature 执行权的持有。
2. 引入 Compute Stage，作为长任务、sandbox、文件、日志、runtime blocks、subagents 和 artifacts 的主展示面。
3. 显式 feature launch/resume 直接进入 `FeatureIngressService`，不再经过 lead-agent tool loop。
4. 以 `ExecutionSession` 作为 feature 业务生命周期唯一事实源。
5. 以 feature runtime profile 管理每个 feature 的执行模式、agent policy、sandbox policy 和 review gate。
6. 将 DeerFlow、Claude Agent SDK、Codex SDK 等能力收束为 `AgentHarness` provider，只能在 Compute 内部运行。
7. 本轮迁移一次性完成，不保留旧链路 fallback、兼容入口或双运行时。

## 3. 非目标

1. 不把问津改造成 DeerFlow fork。
2. 不让 Claude/Codex SDK 接管主业务 runtime。
3. 不让 chat message 成为 feature 当前状态事实源。
4. 不保留旧的 chat-driven feature 自由工具调用路径。
5. 不做面向旧前端、旧 API、旧数据结构的兼容层。
6. 不引入新的 public task creation surface。

## 4. 产品信息架构

### 4.1 Workspace Shell

```text
Workspace Shell
  ├── Chat Dock
  │     ├── 普通问答
  │     ├── 任务发起
  │     ├── 缺参追问
  │     ├── 人工确认
  │     └── 最终摘要
  │
  ├── Compute Stage
  │     ├── 当前 execution session
  │     ├── plan / phases / runtime blocks
  │     ├── sandbox files
  │     ├── browser / terminal / logs
  │     ├── subagents
  │     ├── artifacts
  │     └── review gates
  │
  └── Knowledge / Artifact Rail
        ├── 文献
        ├── 历史产物
        ├── activity
        └── workspace memory
```

### 4.2 交互模式

普通状态：

```text
Chat Dock 占主区域，Compute Stage 收起或展示最近任务摘要。
```

启动长任务：

```text
Compute Stage 自动展开，占据大部分屏幕。
Chat Dock 缩为控制区，继续承载追问、确认、取消、补充说明和最终摘要。
```

任务完成：

```text
Compute Stage 保留过程、文件和产物。
Chat Dock 写入完成摘要和下一步建议。
```

## 5. 后端分层

### 5.1 Chat Control Plane

职责：

- 保存 user/assistant message。
- 处理 pure chat 问答。
- 接收用户对 feature 的启动、补充、确认、取消和状态查询。
- 生成 feature 启动卡片、缺参卡片、完成摘要卡片。

不负责：

- feature task 创建。
- feature billing。
- feature 幂等。
- feature graph/subagent 编排。
- artifact 最终写回。
- execution session 状态决策。

核心模块：

```text
backend/src/application/handlers/chat_turn_router.py
backend/src/application/handlers/chat_turn_handler.py
backend/src/application/handlers/feature_command_handler.py
```

### 5.2 Compute Work Plane

职责：

- 将 `ExecutionSession`、`TaskRecord`、runtime blocks、subagents、sandbox files、artifacts 和 activity 投影为用户可见任务工作台。
- 提供当前 compute session 的 active view、阶段进度、文件树、日志、预览和 review gate 状态。
- 通过 workspace events / SSE 推送增量更新。

不负责：

- 业务执行策略。
- LLM 调用策略。
- feature 计费和幂等。

建议模块：

```text
backend/src/compute/session_service.py
backend/src/compute/projection_service.py
backend/src/compute/events.py
backend/src/compute/sandbox_projection.py
frontend/components/compute/
frontend/stores/compute.ts
```

### 5.3 Feature Transaction Plane

职责：

- feature launch/resume 的唯一业务入口。
- execution session 创建、恢复、缺参追问、事务状态更新。
- owner check、credit、policy、lock、idempotency。
- task payload 构造与提交。

核心模块：

```text
FeatureIngressService
FeatureSubmissionService
ExecutionSessionService
TaskService
TaskStore
```

约束：

```text
所有 feature 启动必须经过 FeatureIngressService。
任何 router、chat、panel、agent tool 都不得绕过 FeatureIngressService 直调 FeatureSubmissionService、task handler 或 graph。
```

### 5.4 Feature Runtime Plane

职责：

- 根据 feature runtime profile 执行确定性 workflow、LangGraph graph、AgentHarness 或 sandbox task。
- 发布 runtime blocks。
- 汇总 evidence/draft/review pack。
- 调用 artifact contract 写回。

核心模块：

```text
backend/src/agents/feature_leader/runtime.py
backend/src/workspace_features/runtime_profiles.py
backend/src/agents/graphs/
backend/src/workspace_features/services/
```

### 5.5 Agent / Sandbox Execution Plane

职责：

- 在受控 ComputeSession 内提供 agentic 执行能力。
- 管理 subagents、tools、MCP、browser、terminal、filesystem、code runner。
- 输出结构化 pack，而不是直接写最终业务结果。

建议接口：

```python
class AgentHarness:
    async def run_subtask(self, request: SubtaskRequest) -> SubtaskResult:
        ...

    async def run_session(self, request: AgentSessionRequest) -> AgentSessionResult:
        ...
```

Provider：

```text
NativeWenjinAgentHarness
DeerFlowHarnessAdapter
ClaudeAgentSdkAdapter
CodexAgentAdapter
```

约束：

```text
AgentHarness 只能在 execution_session_id + compute_session_id + sandbox_session_id 绑定后运行。
AgentHarness 不接管 workspace、thread、billing、artifact、activity、task lifecycle。
```

## 6. 核心实体

### 6.1 Thread

事实范围：

- messages
- title
- skill
- model
- workspace binding

非事实范围：

- feature 当前状态
- subagent 当前状态
- artifact 当前状态
- task 当前状态

### 6.2 Run

事实范围：

- 一次 chat transport 生命周期。
- stream、interrupt、replay、run status。

非事实范围：

- feature 业务状态。
- task 业务状态。

### 6.3 ExecutionSession

事实范围：

- feature 业务事务唯一事实源。
- launch/resume 状态。
- params。
- task ids。
- runtime snapshot 指针。
- artifact ids。
- next actions。
- missing context advisory。

### 6.4 ComputeSession

事实范围：

- execution session 的用户可见工作台投影。
- active view。
- sandbox session 指针。
- UI 展开/收起状态。
- 当前可展示 runtime/files/logs/artifacts/subagents 聚合快照。

约束：

```text
ComputeSession 不成为第二套业务事实源。
业务状态必须从 ExecutionSession、TaskRecord、Artifact、Activity、SubagentRecord 聚合。
```

### 6.5 TaskRecord

事实范围：

- worker 异步执行事实源。
- pending/running/success/failed/cancelled。
- progress。
- runtime state。
- result snapshot。

### 6.6 SandboxSession

事实范围：

- compute 内部执行环境。
- virtual paths。
- file operations。
- browser/terminal/code runner session。
- logs。

### 6.7 Artifact / Activity / SubagentRecord

事实范围：

- Artifact：最终产物。
- Activity：用户可追溯历史。
- SubagentRecord：agent 子任务记录，必须绑定 `execution_session_id`。

## 7. TurnRouter

新增 `ChatTurnRouter`，在进入 lead-agent 前确定 turn mode。

```text
pure_chat
feature_launch
feature_resume
feature_status
feature_proposal
```

路由优先级：

1. `metadata.orchestration.intent == "resume"` -> `feature_resume`
2. `metadata.orchestration.intent == "launch"` -> `feature_launch`
3. feature/skill/activity/artifact 显式入口 -> `feature_launch` 或 `feature_status`
4. 当前 active `ExecutionSession` 处于 `awaiting_user_input` 且用户回复补充信息 -> 前端携带 `execution_session_id` 显式进入 `feature_resume`
5. 普通自然语言聊天 -> `pure_chat`
6. lead-agent 认为可能需要 feature -> `feature_proposal`

约束：

```text
feature_launch 和 feature_resume 不进入 make_lead_agent。
pure_chat 不创建 task_record。
feature_proposal 只建议，不执行。
```

## 8. 核心链路

### 8.1 普通聊天

```text
User
  -> ChatTurnRouter(pure_chat)
  -> ThreadTurnHandler
  -> LeadAgent
  -> assistant message
  -> thread token billing
  -> memory capture
```

### 8.2 显式 feature launch

```text
User / UI seed / skill / activity retry
  -> ChatTurnRouter(feature_launch)
  -> FeatureCommandHandler
  -> FeatureIngressService.launch
  -> ExecutionSession created
  -> ComputeSession created/activated
  -> FeatureSubmissionService
  -> TaskService.submit_task
  -> Chat writes launch pointer card
  -> Compute Stage opens
```

### 8.3 feature resume

```text
User reply
  -> ChatTurnRouter(feature_resume)
  -> FeatureIngressService.launch(..., execution_session_id=...)
  -> same ExecutionSession
  -> TaskService.submit_task
  -> Chat writes resume pointer card
```

### 8.4 worker execution

```text
Celery worker
  -> workspace_feature_handler
  -> FeatureLeaderRuntime
  -> feature_leader.graph_registry
  -> feature graph/service
  -> optional AgentHarness
  -> runtime blocks
  -> artifact/activity/task writeback
  -> execution session completed/failed
  -> compute.updated events
```

## 9. Feature Runtime Mode

每个 feature 必须声明 runtime profile。

```python
class FeatureRuntimeMode(str, Enum):
    CHAT_ONLY = "chat_only"
    DETERMINISTIC = "deterministic"
    COMPUTE_WORKFLOW = "compute_workflow"
    COMPUTE_AGENTIC = "compute_agentic"
```

建议 profile 字段：

```python
runtime_mode: FeatureRuntimeMode
requires_compute: bool
requires_sandbox: bool
allowed_subagents: tuple[str, ...]
max_subagents: int
agent_harness_provider: str | None
output_contract: str
review_gate: str | None
```

初始建议：

| Feature | Mode |
| --- | --- |
| deep_research | `compute_agentic` |
| literature_management | `compute_workflow` |
| opening_research | `compute_workflow` |
| thesis_writing | `compute_workflow` |
| figure_generation | `compute_workflow` 或 `compute_agentic` |
| literature_search | `compute_agentic` |
| paper_analysis | `compute_workflow` |
| writing | `compute_workflow` |
| literature_review | `compute_workflow` |
| framework_outline | `compute_workflow` |
| peer_review | `compute_workflow` |
| journal_recommend | `compute_workflow` |
| proposal_outline | `compute_workflow` |
| background_research | `compute_agentic` |
| experiment_design | `compute_workflow` |
| copyright_materials | `compute_workflow` |
| technical_description | `compute_workflow` |
| patent_outline | `compute_workflow` |
| prior_art_search | `compute_agentic` |

## 10. 输出契约

AgentHarness 和 subagents 不直接写最终 artifact。它们输出 pack：

```json
{
  "kind": "evidence_pack",
  "source": "subagent.scout",
  "confidence": "medium",
  "claims": [],
  "citations": [],
  "risks": [],
  "file_refs": [],
  "suggested_next_steps": []
}
```

可选 pack：

```text
evidence_pack
draft_pack
review_pack
file_change_pack
diagnostic_pack
```

最终 artifact 只能由 feature graph/service 通过 artifact contract 写回。

## 11. 事件模型

### 11.1 compute.updated

```json
{
  "type": "compute.updated",
  "workspace_id": "ws_xxx",
  "execution_session_id": "exec_xxx",
  "compute_session_id": "compute_xxx",
  "status": "running",
  "active_view": "sandbox",
  "runtime": {},
  "files": [],
  "artifacts": [],
  "subagents": []
}
```

### 11.2 compute.step

```json
{
  "type": "compute.step",
  "execution_session_id": "exec_xxx",
  "compute_session_id": "compute_xxx",
  "phase": "literature_discovery",
  "actor": "scout",
  "message": "正在筛选近五年高相关论文",
  "file_refs": [],
  "artifact_refs": []
}
```

### 11.3 chat pointer card

Thread message 只存指针：

```json
{
  "orchestration": {
    "mode": "feature_execution",
    "feature_id": "deep_research",
    "execution_session_id": "exec_xxx",
    "compute_session_id": "compute_xxx",
    "task_id": "task_xxx",
    "status_at_emit": "running"
  }
}
```

约束：

```text
status_at_emit 只是卡片创建时状态。
当前状态必须从 execution/task/compute projection 查询。
```

## 12. Billing

```text
pure_chat:
  thread token billing

feature_launch / feature_resume:
  feature credit billing
  不执行 thread turn token billing，除非额外调用 LLM 生成长篇 chat summary

feature_completion_summary:
  固定模板卡片不计 chat token
  LLM 总结按 thread usage 计费
```

## 13. Review Gate

涉及文件覆盖、LaTeX apply、artifact promote、专利/申报书最终稿写回时，必须经过 review gate。

```text
preview -> apply -> revert
```

review gate 由 feature runtime 或 sandbox projection 提供，前端只负责展示和触发。

### 13.1 WenjinPrism 与 Compute 的边界

写作/LaTeX 类 feature 不直接成为主稿编辑器，Compute 也不持有 LaTeX 工程事实源。

```text
生成在 Feature
过程在 Compute
确认在 Review Gate
落稿在 WenjinPrism
精修在 WenjinPrism
摘要回 Chat
```

职责边界：

1. 写作/LaTeX feature 生成 `draft_pack`、`review_pack`、`file_change_pack`、`latex_sync_pack`。
2. Compute 投影 `latex_project_id`、目标文件、compile 状态、待确认 file changes、已应用 file changes、diff/review gate，并提供 “打开 WenjinPrism”。
3. WenjinPrism 持有主稿工程文件、模板、编译、PDF/SyncTeX、feedback anchors、rewrite apply/revert。
4. AgentHarness 可以读取 Prism 快照并生成候选变更，但不能直接写 Prism 文件。
5. Prism 文件写入必须走 `preview -> apply -> revert`，并执行签名、hash、结构和编译门禁。

当前迁移态：

1. workspace LaTeX bridge 对新建 Prism 项目允许初始化 seed。
2. 对已有 Prism 文件，feature 生成内容不再自动覆盖；变化统一写入 Prism metadata 的待确认写入队列。
3. `feature_proposal` 表示非冲突生成更新，`user_modified/user_protected` 表示当前稿件与 feature 生成内容存在需要确认的差异。
4. Compute 和 WenjinPrism 都可以触发 diff preview、discard / apply / revert；确认后以 Prism metadata 为准刷新 Compute projection。
5. 有待确认写入时，compile 返回 `blocked_by_review`，避免把旧稿 PDF 当作新结果。
6. Prism file-change API 已收敛为 `preview -> apply -> discard/revert`；apply 必须携带 preview 签名，revert 必须携带 apply 后写入 metadata 的 undo 签名。
7. ComputeStage 和 WenjinPrism 前端已接入 diff preview 和 apply 后 revert；`applied_file_changes` 由 Prism metadata 透出并在撤回后清理。
8. `docs/architecture`、`docs/product` 和 README 入口已同步为当前 Compute-centered 事实源，并由文档守卫测试防止旧 chat-feature tool loop 描述回流。
9. feature graph registry 已从旧 workspace lead-agent 命名迁入 `backend/src/agents/feature_leader/graph_registry.py`，避免 feature 执行域继续挂在 chat lead-agent 语义下。
10. 前端缺参继续执行由 active `ExecutionSession` 生成 resume metadata，不再从 thread message metadata 反推当前执行状态。

## 14. 架构守卫

1. 显式 feature launch/resume 不调用 `make_lead_agent`。
2. pure chat lead-agent 不暴露 feature 自由执行工具。
3. 所有 feature launch/resume 必须经过 `FeatureIngressService`。
4. `ExecutionSession` 是 feature 状态唯一事实源。
5. `ComputeSession` 只能做 UI projection，不做业务状态决策。
6. `SubagentRecord` 必须绑定 `execution_session_id`。
7. AgentHarness 只能在 ComputeSession 内运行。
8. Artifact 只能通过 artifact contract 写回。
9. Thread message 不复制完整运行态，只保存 pointer。
10. 本轮迁移删除旧链路，不保留 fallback 或兼容层。
11. Feature graph 注册与执行属于 `FeatureLeaderRuntime` 边界，不使用 workspace lead-agent 命名或导入路径。
