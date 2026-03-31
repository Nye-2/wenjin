# ADR: Platform Layer Boundaries

- Status: Accepted
- Date: 2026-03-19
- Owner: Backend Platform

## Context

Wenjin 当前已形成统一任务执行链路，但仍需要持续约束各层职责，避免路由层回流业务逻辑、避免任务层与 HTTP 细节耦合，保证可测试性和可演进性。

## Decision

### Layer Responsibilities

| Layer | 代码位置 | 允许职责 | 明确禁止 |
|---|---|---|---|
| Router | `backend/src/gateway/routers/` | HTTP 协议适配、鉴权依赖注入、请求参数校验、返回模型 | 直接编排积分扣费、直接执行业务补偿、直接做跨服务流程控制 |
| Application Handler | `backend/src/application/handlers/` | 跨服务编排（权限校验、积分、幂等、任务提交） | 处理 HTTP 细节、返回 FastAPI 响应对象 |
| Task Handler | `backend/src/task/handlers/` | 异步任务执行、进度上报、调用 LangGraph、结果封装 | 处理 HTTP 请求/响应、做路由级权限判断 |
| Feature Registry | `backend/src/workspace_features/registry.py` | workspace feature 元数据单一事实源（feature_id/handler_key/task_type/stages） | 写业务流程分支、写 HTTP 协议逻辑 |
| Contracts | `backend/src/gateway/contracts/`、`backend/src/workspace_features/contracts.py` | 跨层数据契约与序列化结构 | 执行业务逻辑 |

### Non-negotiable Rules

1. Router 不直接调用积分服务、文献阈值规则等业务策略。
2. Feature 执行入口统一走 `FeatureExecutionHandler` + `TaskService`。
3. `workspace feature` 的定义以 `registry.py` 为唯一来源，不允许多处复制。
4. 任务执行结果需维持统一字段（`success`、`feature_id`、`artifacts`、`refresh_targets`、`data` 等）。
5. 已移除兼容层入口，新增能力只能接入 canonical route group。
6. `workspace feature` task payload 的业务输入只能存在于 `params`，顶层字段只承载编排元数据，不允许复制形成双事实源。

## Route Lifecycle Policy

| Route Group | Lifecycle |
|---|---|
| `/api/workspaces/{id}/features/*` | Active，主执行入口 |
| `/api/tasks/*` | Active，统一任务状态与流式进度；不再承担任务创建 |
| `/api/thesis/*` | Removed |
| `academic` tag routes | Removed |

## Consequences

- 路由层薄化后，接口回归与权限测试更稳定。
- 应用层可独立演进扣费、幂等、任务提交策略。
- 任务层围绕 LangGraph 执行语义收敛，降低跨 workspace 的分叉复杂度。
