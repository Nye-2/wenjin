# 其他 Workspace 开发总指南（用于新 AI 批量接力）

## 1. 目标与范围

本文用于指导新 AI 基于已跑通的 thesis workspace 样板，批量开发以下 workspace：

1. `sci`
2. `proposal`
3. `software_copyright`
4. `patent`

目标不是一次性做“大而全”，而是每个 workspace 先拿到至少 1-2 个真实闭环 feature，再逐步扩展。

---

## 2. 必须遵守的架构约束

### 2.1 主流程不变

统一链路保持为：

`registry -> router execute -> task dispatch -> workspace feature handler -> artifact persist -> dashboard refresh`

不要新起并行架构，不要绕开 task 体系直接在 router 做重业务。

### 2.2 分层职责

1. `registry.py`：
   - 只放 feature 元数据（id、name、handler_key、task_type、stages 等）。
2. `gateway/routers/features.py`：
   - 只做鉴权、参数校验、payload 组装、任务提交。
3. `workspace_features/handlers/*.py`：
   - 只做编排与进度上报。
   - 具体业务逻辑下沉到 `workspace_features/services/*.py`。
4. `workspace_features/services/*.py`：
   - 实现可复用业务能力（组装、调用工具、降级策略、payload 结构统一）。
5. `ArtifactService`：
   - 统一持久化产出，保证 dashboard/knowledge panel 可见。

---

## 3. Feature 开发标准模板

每开发一个 feature，按以下固定步骤推进。

## 3.1 步骤 A：定义能力元数据

1. 在 `backend/src/workspace_features/registry.py` 添加/确认 feature 定义。
2. 明确 `handler_key` 与 `task_type`。
3. 明确前端页面路由（若无专页，先走主工作台触发也可）。

## 3.2 步骤 B：实现后端执行逻辑

1. 在 `workspace_features/services/` 新增或复用 service 函数：
   - 输入：context params + workspace context。
   - 输出：可直接作为 artifact content 的结构化 payload。
2. 在 `workspace_features/handlers/` 挂 handler：
   - 进度上报（10/40/100 或类似分段）。
   - 调 service。
   - 持久化 artifact。
   - 返回 `refresh_targets=["artifacts"]`。
3. 若依赖外部 provider，必须提供降级路径：
   - 失败仍落库可执行源码/模板草稿/中间结构。

## 3.3 步骤 C：前端闭环

统一采用：

1. `executeWorkspaceFeature(...)` 提交任务。
2. `pollTaskUntilTerminal(...)` 轮询任务。
3. 完成后 `fetchArtifacts(workspaceId)` 刷新。

参考工具：

- `frontend/lib/taskPolling.ts`

## 3.4 步骤 D：Dashboard 接通

1. 在 `DashboardService` 增加对应模块状态聚合。
2. 聚合依据必须是 task/artifact 的真实数据，不要写“假状态”。

## 3.5 步骤 E：测试与验收

每个 feature 至少补三类测试：

1. router 层：`execute` 是否正确提交 payload。
2. handler 层：artifact 是否真实落库、content 字段是否符合约定。
3. dashboard 层：模块状态是否随 artifact/task 变化。

---

## 4. Artifact 设计原则

### 4.1 内容结构原则

1. 必须包含 `generated_at` 或可追踪时间字段。
2. 必须包含“结果状态字段”（如 `status`/`compile_status`/`generation_mode`）。
3. 若有降级，必须保留：
   - 原始源码/提示词/模板文本；
   - 错误原因；
   - 后续升级元数据。

### 4.2 类型原则

优先复用 `src/artifacts/types.py` 中已有类型，避免新增大量同义类型。

---

## 5. 批量开发建议节奏

建议按 workspace 并行度较低的顺序推进，降低上下文切换成本：

1. `sci`（可先做文献检索/分析闭环）
2. `proposal`（文档生成类，依赖最少）
3. `patent`（同样文档类，但检索逻辑更复杂）
4. `software_copyright`（已有一个样板 feature，可继续扩展）

---

## 6. DoD（完成定义）

某个 workspace 视为“第一阶段完成”，需满足：

1. 至少 1 个 feature 达成真实闭环（execute -> task -> artifact -> dashboard）。
2. 前端页面可触发、可轮询、可看到结果。
3. 关键测试通过（router + handler + dashboard）。
4. 文档补齐（输入参数、artifact 结构、降级策略、后续升级点）。

---

## 7. 交付给下一位 AI 的最小上下文

每次交接都应给到以下信息：

1. 当前 workspace 已实现 feature 列表与状态（真实/降级/占位）。
2. 未完成 TODO 的文件路径与函数名。
3. 本轮新增 artifact content 契约示例。
4. 已跑测试命令与结果。
5. 下一步优先级（严格到 feature 级）。
