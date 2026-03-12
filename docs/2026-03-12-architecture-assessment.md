# AcademiaGPT-V2 架构评估与后续演进建议

## 1. 文档目的

这份文档用于沉淀当前 `AcademiaGPT-V2` 的真实架构状态、核心约束、已完成的统一化工作、仍需控制的风险点，以及后续架构迭代时应遵守的边界。

它不是“理想架构图”，而是面向当前代码库的工程判断文档。

## 2. 当前架构总览

当前项目已经形成了一个可继续扩展的三层结构：

1. 前端工作台层
   - `frontend/app/(workbench)/workspaces/[id]/...`
   - 负责 workspace 工作台、feature 触发、chat、artifact/paper 展示、任务轮询

2. 网关编排层
   - `backend/src/gateway/routers/*`
   - 负责认证、workspace 鉴权、API 合同、任务提交、结果读取

3. 后端能力执行层
   - `backend/src/task/*`
   - `backend/src/thesis/*`
   - `backend/src/workspace_features/*`
   - 负责异步任务调度、thesis workflow、通用 workspace feature runtime、artifact 持久化

这三层之间的职责边界，当前已经基本清晰：

- 前端不再关心具体 feature 如何执行，只关心 feature 元数据和 task 状态
- router 不再承载 feature 定义和复杂业务逻辑，只做鉴权和编排
- feature 的具体实现开始沉到 `workspace_features` 运行时和 handler 中

## 3. 已完成的关键统一化

### 3.1 Workspace type 已统一

当前 canonical workspace type 固定为：

- `sci`
- `thesis`
- `proposal`
- `software_copyright`
- `patent`

这 5 个类型已经成为前后端共享的事实标准，不应再新增旁路类型名。

### 3.2 Feature 定义中心化

当前 feature 元数据统一收敛到：

- `backend/src/workspace_features/registry.py`

该 registry 现在承载：

- workspace_type
- feature_id
- 文案、icon、agent、panel、color、stages
- `task_type`
- `handler_key`

这意味着后续新增 feature 时，不需要再去 router 中堆 if/else 或复制定义。

### 3.3 Async task 合同统一

当前 feature 执行已经统一走：

1. `/workspaces/{workspace_id}/features/{feature_id}/execute`
2. `TaskService.submit_task(...)`
3. `/tasks/{task_id}` 轮询状态

前端已不再需要按 workspace 分裂不同任务轮询协议。

### 3.4 Chat thread 持久化

之前 chat thread 是 router 内部内存字典，这在功能跑通后会立刻成为稳定性和鉴权风险点。

现在已经改成：

- ORM 模型：`backend/src/database/models/chat_thread.py`
- Service：`backend/src/services/chat_thread_service.py`
- Router 只做 owner isolation 和 agent pipeline 编排

这一步非常关键，因为它消除了：

- 服务重启即丢失线程
- 多用户线程隔离依赖内存约定
- chat router 无法测试的结构性问题

### 3.5 Feature handler 运行时骨架已建立

当前新增了：

- `backend/src/workspace_features/contracts.py`
- `backend/src/workspace_features/runtime.py`
- `backend/src/workspace_features/handlers/*`

这一层提供了后续“插拔式”扩展能力层的基础：

- 通过 `handler_key` 定位能力模块
- 通过 decorator 注册 handler
- 通过统一 context 访问 workspace/params/progress
- 通过统一 result contract 返回 `artifacts`、`refresh_targets`、`data`

## 4. 当前架构的优点

### 4.1 主干已足够稳定，不需要再推翻

当前主干已经可以承载后续 4 个非 thesis workspace 的并行开发。继续大规模改架构，收益已经明显低于成本。

### 4.2 扩展入口已从“改核心”变成“挂能力”

理想状态下，新增一个 feature 模块只需要：

1. 在 registry 注册 feature
2. 实现 handler
3. 补测试
4. 前端自动通过 `/features` 发现它

这就是可维护系统和“演示型代码”的分水岭。

### 4.3 前后端合同正在收敛

现在重要的 contract 已逐渐固定：

- workspace type
- feature metadata
- async task polling
- chat thread ownership
- artifact refresh behavior

这为后续迭代减少了大量隐性沟通成本。

## 5. 当前仍然存在的不足

### 5.1 非 thesis 能力层仍然薄

当前 thesis 是“真实 workflow”，其他 workspace feature 大多仍是 placeholder 或半成品。

也就是说：

- 架构主干基本到位
- 业务能力层还没有填满

这不是架构失败，而是开发阶段尚未进入能力扩张阶段。

### 5.2 Artifact taxonomy 曾经存在双标准问题

在这次整理前，artifact type 在 ORM 和 validator 层并不完全一致。

这类问题的本质不是“小 bug”，而是“系统的词汇表没有唯一来源”。

当前已经把 artifact type 抽成了共享 taxonomy，但后续新增类型必须继续走同一来源，不能再在 validator 或 router 各自加一份枚举。

### 5.3 启动路径中曾存在双数据库基座

网关启动时曾经走 `src.academic.database.session.init_db`，而实际运行期查询走的是 `src.database`。

这个问题已经修复，但说明项目内仍残留旧路径、旧抽象，需要持续清理。

### 5.4 Workspace feature 的参数输入层还较弱

当前 quick action 直接执行 feature，参数输入仍然很轻。

因此当前适合先做：

- checklist/template 型 feature
- 基于 workspace context 即可运行的 feature

后续如果要做复杂 feature，需要补：

- params schema
- feature-specific input form
- 更明确的 artifact preview / editor

## 6. 当前建议坚持的架构边界

后续迭代时，应尽量坚持以下边界：

### 6.1 Router 不写 feature 业务逻辑

router 只负责：

- 鉴权
- workspace 归属校验
- 输入校验
- 提交任务
- 返回任务 id

不要再把某个 feature 的真实业务逻辑直接写进 router。

### 6.2 Registry 是 feature 定义唯一来源

所有 feature 元数据必须登记到：

- `backend/src/workspace_features/registry.py`

不要在前端手写一套 feature 配置，不要在 router 里再复制一套。

### 6.3 Handler 只通过 `handler_key` 扩展

不要再通过：

- workspace_type + 一堆 if/else
- feature_id + 一堆 if/else

去堆能力。

正确做法是：

- registry 负责 feature -> `handler_key`
- runtime 负责 `handler_key` -> handler

### 6.4 Artifact 是 feature 输出的第一落点

对于绝大多数非 thesis feature，第一阶段不要追求复杂 UI 编辑器，先把结果稳定落成 artifact。

理由：

- artifact 是跨 feature 可复用的最稳定中间层
- knowledge panel 已经是天然展示位
- artifact 也便于后续接 agent context / lineage / version

### 6.5 前端刷新行为不要写死在单个 feature 上

当前已经改成由 task result 返回 `refresh_targets`，前端按目标刷新：

- `artifacts`
- `papers`
- `workspace`

后续新增 feature 不要在前端再写 “如果 featureId === xxx 就刷新 yyy”。

## 7. 后续架构演进建议

### 7.1 优先级最高：补能力，不重构主干

下一阶段优先做的是：

1. 为 `software_copyright` 补齐剩余 handler
2. 为 `patent`、`proposal`、`sci` 各跑通至少一个真实 handler
3. 逐步让 artifact 成为 feature 间共享资产

### 7.2 中优先级：补 feature params schema

建议后续在 registry 中引入可选字段：

- `params_schema`
- `default_params`
- `result_channels`

这样前端可以自动生成输入界面，不需要每次手写。

### 7.3 中优先级：统一 artifact viewer / editor

当前 knowledge panel 更像 artifact timeline。

后续建议补：

- artifact detail drawer / modal
- 针对不同 artifact type 的 renderer
- 针对可编辑 artifact 的 versioned update 流程

### 7.4 中优先级：清理 legacy 路径

建议逐步清理：

- `src.academic.database.*`
- 旧版 router / adapter 中与现状不一致的路径
- 重复的 enum / validator / DTO

## 8. 当前架构结论

当前 `AcademiaGPT-V2` 已经从“搭框架阶段”进入“沿稳定主干扩功能阶段”。

结论很明确：

- 不建议再做一次大规模架构重写
- 建议在现有主干上继续补能力层
- 未来扩展的核心标准是：`registry + handler_key + runtime + artifact + task result contract`

如果后续需要继续做架构级迭代，这份文档可以作为判断基线：

- 哪些是系统主干，不应反复折腾
- 哪些是能力层空白，应该直接补
- 哪些是历史遗留，需要渐进式清理
