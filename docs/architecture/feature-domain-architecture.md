# Workspace Feature 域当前架构

更新时间：2026-04-28
状态：Current  
适用项目：`wenjin`

本文档定义 workspace 场景下 `Chat Control Plane / Compute Work Plane / Feature Transaction Plane / AgentHarness + subagents` 的当前关系与边界，作为实现与验收依据。

## 1. 目标与约束

### 1.1 目标

1. 用户侧严格单入口：`/workspaces/{workspace_id}/chat`。
2. 领域侧严格单入口：所有 feature 启动都必须收敛到 `FeatureIngressService`。
3. feature 作为执行域/事务域：完整生命周期、状态、中间结果、最终结果都落在 execution session 中。
4. feature 域使用专职 runtime：chat 负责入口与收口，不兼职 feature 执行编排。
5. feature 缺参时回 chat 追问后继续：同一 execution session 内续跑，不新开事务。
6. Compute Stage 是长任务工作面，但不成为业务状态事实源。

### 1.2 非目标

1. 不引入新的用户入口页面替代 chat 主路由。
2. 不把 skills 重新做成独立执行框架。
3. 不把 subagent runtime 暴露为面向用户的单独产品主链。
4. 不让 thread message 承载 feature 当前状态。

## 2. 核心关系模型

```text
User/UI (Chat / Feature API / Activity Retry / Automation)
        │
        ├─ Chat Control Plane
        │        └─ lead_agent + launch_feature tool
        ├─ Feature API Adapter
        └─ Automation Adapter
                 │
                 ▼
        FeatureIngressService.launch/resume
                 │
                 ├─ ExecutionSession（feature lifecycle）
                 ├─ ComputeSession（work plane shell）
                 │
                 ▼
        FeatureSubmissionService + TaskService
                 │
                 ▼
        workspace_feature_handler (async task)
                 │
                 ▼
        Feature Leader Runtime / AgentHarness
                 │
                 ├─ LangGraph nodes
                 └─ Subagent runtime（execution_session 绑定）
                 │
                 ▼
        ExecutionSession + Task + Artifact + Activity + WorkspaceEvents
                 │
       ┌─────────┼─────────┐
       ▼                   ▼
Compute Stage（过程面）     Chat 总结消息（收口面）
```

## 3. 组件职责边界

| 组件 | 应负责 | 不应负责 |
| --- | --- | --- |
| Chat Control Plane | 普通问答、显式 feature 命令接入、追问交互、最终收口摘要 | 直接执行 feature graph、直接驱动 subagent 编排、持有 feature 当前状态 |
| FeatureLaunchCommand | 统一承载 launch/resume 输入（workspace、feature、params、thread、skill、session、source） | 执行业务策略、读取数据库 |
| FeatureIngressService | 接收 `FeatureLaunchCommand`，完成 launch/resume 统一入口、事务初始化、上下文标准化、幂等与会话绑定 | 业务图执行细节 |
| FeatureSubmissionService | 权限/额度/策略检查、task payload 构造、任务提交 | UI 交互编排 |
| Feature Leader Runtime | 读取 feature 执行上下文、编排 LangGraph/subagents、发布过程事件 | 处理 chat 会话文本策略 |
| ComputeSession / Projection | 工作台 shell、runtime/files/logs/review gate/Prism 投影 | 业务状态决策、直接执行 feature |
| Skills Catalog | `skill -> feature + defaults + follow-up` 语义映射 | feature 运行态管理 |
| Subagent Runtime | 专项子任务执行与状态回写 | feature 入口分发、用户交互追问 |
| WenjinPrism | 主稿工程、文件、编译、PDF/SyncTeX、feedback rewrite、file-change apply/revert | feature 生成过程编排、Compute runtime |

## 4. Skills / Features / Leader / Subagent 的关系

### 4.1 Skills

1. skills 是 chat 层入口语义，负责“怎么聊、聊到哪里触发 feature”。
2. skill 绑定 canonical feature，可附默认参数和 follow-up skill。
3. skill 不直接承载事务执行。

### 4.2 Features

1. feature 是执行域与事务域的最小业务单元。
2. 每次 feature 执行必须对应一个 execution session（含 task ids、runtime、artifacts、next actions）。
3. 每个 feature 必须声明 runtime profile，用于约束 runtime mode、Compute、sandbox、subagents、AgentHarness 和 review gate。
4. feature 的完成态由统一结果契约输出，并投影到 Compute 和 chat。

### 4.3 Chat / Feature Leader

1. chat lead-agent（LangGraph `create_react_agent`）：处理 pure chat、建议、workspace read，同时通过内置 `launch_feature` tool 决定何时启动 feature。
2. lead-agent 根据 workspace skills 上下文判断是否需要调用 `launch_feature`，无需上游 router。
3. `launch_feature` tool 直接调用 `FeatureIngressService.launch()`，是 chat 域进入 feature 域的唯一路径。
4. feature leader：进入 feature 域后，独立负责编排节点、AgentHarness 与 subagents。

### 4.4 Subagents（Compute 内部）

1. subagent 由 feature leader / AgentHarness 在节点中按任务生成与回收。
2. subagent 必须绑定 `execution_session_id`，否则拒绝执行。
3. subagent 状态通过 workspace events 和 compute projection 进入 Compute Stage 与 activity 流。
4. public subagent API 已移除，subagent 不是独立用户入口。

## 5. 统一契约

### 5.1 Ingress Launch / Resume Command

```json
{
  "workspace_id": "ws_xxx",
  "thread_id": "thread_xxx",
  "feature_id": "deep_research",
  "entry_skill_id": "deep-research",
  "params": {},
  "launch_source": "chat|feature_api|automation",
  "launch_message": "用户触发文本",
  "execution_session_id": null,
  "idempotency_key": "optional"
}
```

语义：

1. `execution_session_id` 为空表示 launch；非空表示 resume。
2. adapters 只传业务意图，不直接触发 handler 或 graph。
3. launch/resume 均创建或复用对应 compute session。

### 5.2 过程事件契约（Compute 主消费）

```json
{
  "type": "execution.updated | compute.updated | subagent.updated | task.updated",
  "workspace_id": "ws_xxx",
  "execution_session_id": "exec_xxx",
  "compute_session_id": "compute_xxx",
  "feature_id": "deep_research",
  "status": "pending|running|awaiting_user_input|completed|failed|advisory",
  "runtime_snapshot": {},
  "subagents": []
}
```

### 5.3 Chat 收口契约（chat 主消费）

```json
{
  "orchestration": {
    "mode": "feature_execution",
    "feature_id": "deep_research",
    "execution_session_id": "exec_xxx",
    "compute_session_id": "compute_xxx",
    "status_at_emit": "pending|awaiting_user_input|completed|failed|advisory",
    "params": {},
    "task_id": "optional"
  }
}
```

约束：`status_at_emit` 只是消息写入时状态，当前状态必须从 execution/task/compute projection 查询。

## 6. 缺参回 chat 追问再继续

1. ingress 或 feature runtime 判断缺参，写入 execution session 状态：`awaiting_user_input`。
2. 同时发布可读追问项（问题、缺失字段、建议默认值）。
3. chat 面板展示追问，用户回复后携带同一 `execution_session_id`。
4. lead-agent 识别用户回复与待续执行上下文，调用 `launch_feature` tool 并传入 `execution_session_id`。
5. `launch_feature` tool 构造 `FeatureLaunchCommand` 并调用 `FeatureIngressService.launch(command)`。
6. ingress 在同一 session 上追加参数并继续执行，不新建事务。

约束：

1. `workspace_id/user_id/thread_id` 必须匹配该 execution session，否则拒绝 resume。
2. resume 必须幂等，避免重复提交并发 task。

## 7. Compute Stage 与 Chat 的分工

1. Compute Stage：过程态与中间产物（runtime blocks、subagents、sandbox files、logs、Review Gate、WenjinPrism 写入状态）。
2. chat 面板：发起确认、缺参追问、完成总结与下一步建议。
3. 写作类 feature：完成时输出 `latex_project_id/artifact_ids/file_changes`，由 chat 给出简要总结，正文和工程细节进入 WenjinPrism。
4. Thread message 不承载当前执行态，不能作为 Compute 恢复来源。

## 8. 现有代码映射到目标边界

| 现有位置 | 目标角色 |
| --- | --- |
| `backend/src/application/commands.py` | application command DTO（`FeatureLaunchCommand`） |
| `backend/src/application/services/feature_launch_service.py` | canonical ingress（`FeatureIngressService`） |
| `backend/src/application/services/feature_submission_service.py` | application 层策略编排 |
| `backend/src/task/handlers/workspace_feature_handler.py` | 调用专职 feature leader runtime |
| `backend/src/agents/feature_leader/runtime.py` | feature runtime 编排 |
| `backend/src/agents/feature_leader/graph_registry.py` | feature graph 注册与执行 |
| `backend/src/agents/harness/` | AgentHarness contract/provider |
| `backend/src/tools/builtins/launch_feature.py` | lead-agent 内置 feature launch/resume tool |
| `backend/src/agents/` (lead-agent) | chat 入口，`create_react_agent` 统一处理 pure chat 与 feature 启动 |
| `backend/src/compute/session_service.py` | compute session shell 创建/查询 |
| `backend/src/compute/projection_service.py` | compute projection 聚合 |
| `backend/src/gateway/routers/features.py` | ingress adapter（feature API 入口） |
| `backend/src/gateway/routers/compute.py` | compute read surface |
| `backend/src/gateway/routers/latex.py` | WenjinPrism file-change/rewrite/compile API |
| `backend/src/application/handlers/thread_turn_handler.py` | chat 入口与收口，不直接执行 feature |

## 9. 架构守卫（必须满足）

1. 不允许任何入口绕过 ingress 直调 `FeatureSubmissionService`、task handler 或 graph。
2. 不允许 chat 主链路直接承担 feature 图执行逻辑。
3. 不允许 subagent 在缺失 `execution_session_id` 时执行。
4. execution session 必须成为 feature 运行态与恢复态唯一聚合对象。
5. chat/feature API/automation 必须共享同一 launch/resume 语义与结果契约。
6. ComputeSession 只能做 UI projection，不做业务状态决策。
7. WenjinPrism 文件写入必须走 preview/apply/discard/revert，不允许 feature 直接覆盖已有主稿。
