# Workspace Feature 域目标架构（1B + 2B + 3）

更新时间：2026-04-15  
状态：Current  
适用项目：`wenjin`

本文档定义 workspace 场景下 `chat 主链路 / features / skills / leader agent / LangGraph subagents` 的当前关系与边界，作为实现与验收依据。

## 1. 目标与约束

### 1.1 目标

1. 用户侧严格单入口：`/workspaces/{workspace_id}/chat`。
2. 领域侧严格单入口（1B）：所有 feature 启动都必须收敛到一个 ingress 服务。
3. feature 作为执行域/事务域：完整生命周期、状态、中间结果、最终结果都落在 execution session 中。
4. feature 域使用专职 leader（2B）：chat 负责路由与收口，不兼职 feature 执行编排。
5. feature 缺参时回 chat 追问后继续（3）：同一 execution session 内续跑，不新开事务。

### 1.2 非目标

1. 不引入新的用户入口页面替代 chat 主路由。
2. 不把 skills 重新做成独立执行框架。
3. 不把 subagent runtime 暴露为面向用户的单独产品主链。

## 2. 核心关系模型

```text
User/UI (Chat / Panel / Automation)
        │
        ├─ Chat Mainline (唯一用户主入口)
        │        │
        │        └─ Feature Adapter
        │
        ├─ Panel Adapter
        └─ Automation Adapter
                 │
                 ▼
        FeatureIngressService.launch/resume   ← 领域单入口（1B）
                 │
                 ▼
        FeatureExecutionHandler + TaskService
                 │
                 ▼
        workspace_feature_handler (async task)
                 │
                 ▼
        Feature Leader Runtime（专职，2B）
                 │
                 ├─ LangGraph nodes
                 └─ Subagent runtime（execution_session 绑定）
                 │
                 ▼
        ExecutionSession + Task + Artifact + Activity + WorkspaceEvents
                 │
       ┌─────────┴─────────┐
       ▼                   ▼
Feature 右侧面板（过程面）   Chat 总结消息（收口面）
```

## 3. 组件职责边界

| 组件 | 应负责 | 不应负责 |
| --- | --- | --- |
| Chat Mainline | 用户意图识别、feature 路由、追问交互、最终收口摘要 | 直接执行 feature graph、直接驱动 subagent 编排 |
| FeatureIngressService | launch/resume 统一入口、事务初始化、上下文标准化、幂等与会话绑定 | 业务图执行细节 |
| FeatureExecutionHandler | 权限/额度/策略检查、task payload 构造、任务提交 | UI 交互编排 |
| Feature Leader Runtime | 读取 feature 执行上下文、编排 LangGraph/subagents、发布过程事件 | 处理 chat 会话文本策略 |
| Skills Catalog | `skill -> feature + defaults + follow-up` 语义映射 | feature 运行态管理 |
| Subagent Runtime | 专项子任务执行与状态回写 | feature 入口分发、用户交互追问 |
| Feature Panel Projection | 展示 execution/runtime/subagent 中间态 | 做 feature 业务决策 |

## 4. Skills / Features / Leader / Subagent 的关系

### 4.1 Skills

1. skills 是 chat 层入口语义，负责“怎么聊、聊到哪里触发 feature”。
2. skill 绑定 canonical feature，可附默认参数和 follow-up skill。
3. skill 不直接承载事务执行。

### 4.2 Features

1. feature 是执行域与事务域的最小业务单元。
2. 每次 feature 执行必须对应一个 execution session（含 task_ids、runtime、artifacts、next_actions）。
3. feature 的完成态由统一结果契约输出，并投影到 panel/chat。

### 4.3 Leader Agent（2B）

1. chat leader：只做路由与收口，判断是否进入 feature 域。
2. feature leader：进入 feature 域后，独立负责编排节点与 subagents。
3. 两者通过明确协议交接，避免一个 agent 同时承担会话策略和事务编排。

### 4.4 Subagents（LangGraph 节点内）

1. subagent 由 feature leader 在节点中按任务生成与回收。
2. subagent 必须绑定 `execution_session_id`，否则拒绝执行。
3. subagent 状态通过 workspace events 进入右侧 panel 与 activity 流。

## 5. 统一契约（目标态）

### 5.1 Ingress Launch / Resume Command

```json
{
  "workspace_id": "ws_xxx",
  "thread_id": "thread_xxx",
  "feature_id": "deep_research",
  "entry_skill_id": "deep-research",
  "params": {},
  "launch_source": "chat|panel|automation",
  "launch_message": "用户触发文本",
  "execution_session_id": null,
  "idempotency_key": "optional"
}
```

语义：

1. `execution_session_id` 为空表示 launch；非空表示 resume（策略 3）。
2. adapters 只传业务意图，不直接触发 handler 或 graph。

### 5.2 过程事件契约（panel 主消费）

```json
{
  "type": "execution.updated | subagent.updated | task.updated",
  "workspace_id": "ws_xxx",
  "execution_session_id": "exec_xxx",
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
    "status": "pending|awaiting_user_input|completed|failed|advisory",
    "params": {},
    "task_id": "optional"
  }
}
```

## 6. 缺参回 chat 追问再继续（策略 3）

1. feature leader 判断缺参，写入 execution session 状态：`awaiting_user_input`。
2. 同时发布可读追问项（问题、缺失字段、建议默认值）。
3. chat 面板展示追问，用户回复后携带同一 `execution_session_id`。
4. chat adapter 调用 `FeatureIngressService.resume(...)`。
5. ingress 在同一 session 上追加参数并继续执行，不新建事务。

约束：

1. `workspace_id/user_id/thread_id` 必须匹配该 execution session，否则拒绝 resume。
2. resume 必须幂等，避免重复提交并发 task。

## 7. 右侧 Feature 面板与 Chat 的分工

1. 右侧面板：过程态与中间产物（runtime blocks、subagents、阶段进度、节点输出）。
2. chat 面板：发起确认、缺参追问、完成总结与下一步建议。
3. 写作类 feature：完成时输出 `latex_project_id/artifact_ids`，由 chat 给出简要总结，正文和工程细节进入 `wenjinprism`。

## 8. 现有代码映射到目标边界

| 现有位置 | 目标角色 |
| --- | --- |
| `backend/src/application/services/feature_launch_service.py` | 升级为 canonical ingress（可重命名为 `FeatureIngressService`） |
| `backend/src/application/handlers/feature_execution_handler.py` | 继续承担 application 层策略编排 |
| `backend/src/task/handlers/workspace_feature_handler.py` | 调用专职 feature leader runtime |
| `backend/src/agents/workspace_lead_agent.py` | 逐步收敛为 feature leader runtime registry/adapter |
| `backend/src/tools/builtins/workspace.py` | ingress adapter（tool 入口） |
| `backend/src/gateway/routers/features.py` | ingress adapter（panel/api 入口） |
| `backend/src/application/handlers/thread_turn_handler.py` | ingress adapter（chat 入口）+ 收口，不直接执行 feature |

## 9. 架构守卫（必须满足）

1. 不允许任何入口绕过 ingress 直调 `FeatureExecutionHandler`、task handler 或 graph。
2. 不允许 chat 主链路直接承担 feature 图执行逻辑。
3. 不允许 subagent 在缺失 `execution_session_id` 时执行。
4. execution session 必须成为 feature 运行态与恢复态唯一聚合对象。
5. chat/panel/automation 必须共享同一 launch/resume 语义与结果契约。
