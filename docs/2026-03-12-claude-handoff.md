# AcademiaGPT-V2 交接文档（给 Claude）

## 1. 文档目的

这份文档用于让新的接手者快速理解：

1. 这一轮已经完成了什么
2. 当前架构真实到了什么阶段
3. 接下来应该优先做什么
4. 哪些边界不要再打破

这不是理想化设计文档，而是基于当前仓库代码的实际交接说明。

## 2. 当前结论

当前项目已经不适合继续大规模重构主干，应该进入“稳定主干上持续补能力模块”的阶段。

已经具备的基础：

- 5 个 canonical workspace type 已统一
- feature 元数据已中心化
- thesis 与非 thesis feature 的执行分流已明确
- 非 thesis feature 已有统一 runtime / handler 骨架
- chat thread 已持久化
- artifact type 已有共享 taxonomy
- 前端 task 完成后的刷新行为已泛化，不再写死单个 feature

当前最重要的判断：

- 架构主干基本可用
- 真正缺的是能力层实现数量
- 后续工作重点应放在继续补 feature handler，而不是再做一轮大改架构

## 3. 术语说明

### 3.1 canonical workspace type

当前唯一认可的 5 个 workspace type：

- `sci`
- `thesis`
- `proposal`
- `software_copyright`
- `patent`

定义位置：

- `backend/src/workspace_features/registry.py`

不要再新增旁路类型名。

### 3.2 non-thesis feature

这里的 “non-thesis feature” 指的是 `thesis` 之外的 4 类 workspace feature：

- `sci`
- `proposal`
- `software_copyright`
- `patent`

当前 thesis 继续走已有 thesis workflow；
当前非 thesis feature 开始统一走 `workspace_features` runtime + handler 机制。

## 4. 这一轮已经完成的工作

### 4.1 修正了 feature 定义散落问题

已完成：

- 把 canonical feature 元数据统一收敛到 `backend/src/workspace_features/registry.py`
- router 不再维护自己的 feature 常量表
- feature 通过 registry 暴露给前端

效果：

- 后续新增 feature 不再需要在 router / frontend 重复写定义
- feature 的 `handler_key`、`agent`、`stages`、`panel`、`task_type` 有了唯一来源

### 4.2 建立了非 thesis feature 的统一执行骨架

新增：

- `backend/src/workspace_features/contracts.py`
- `backend/src/workspace_features/runtime.py`
- `backend/src/workspace_features/handlers/__init__.py`

已打通的模式：

1. registry 提供 `handler_key`
2. task bridge 根据 payload 与 feature 定义分流
3. runtime 通过 decorator 注册 handler
4. handler 使用统一 context 读取 workspace / params / progress
5. handler 通过统一 result contract 返回 `artifacts` / `refresh_targets` / `data`

这层就是后续“插拔式补能力”的基础。

### 4.3 做通了第一个真实的非 thesis 功能闭环

已实现：

- `software_copyright.copyright_materials`

核心文件：

- `backend/src/workspace_features/handlers/software_copyright.py`

它现在会：

- 读取 workspace context 与 params
- 生成真实的软著材料清单
- 持久化为 artifact
- 返回 `refresh_targets=["artifacts"]`

这说明当前架构不只是“能路由”，而是已经能完成一条真实的非 thesis 产物闭环。

### 4.4 统一了 artifact taxonomy，解决多处 enum 漂移

新增：

- `backend/src/artifacts/types.py`
- `backend/src/artifacts/__init__.py`

并统一到：

- `backend/src/database/models/artifact.py`
- `backend/src/gateway/validators/artifact.py`

意义：

- artifact type 不再在 ORM / validator / feature 各写一套
- 后续新增 artifact type 必须只从这个共享 taxonomy 扩展

### 4.5 修复了 chat thread 的架构性问题

已完成 chat thread 持久化，不再使用 router 内内存字典。

新增：

- `backend/src/database/models/chat_thread.py`
- `backend/src/services/chat_thread_service.py`
- `backend/alembic/versions/003_add_chat_threads_table.py`

相关 router 已改为：

- `backend/src/gateway/routers/chat.py`

收益：

- 服务重启不丢 thread
- thread owner isolation 可测试
- router 结构更清晰

### 4.6 统一了 feature execute 的任务桥接

核心文件：

- `backend/src/task/handlers/workspace_feature_handler.py`

当前逻辑：

- thesis payload -> thesis workflow
- non-thesis payload -> `execute_registered_feature(...)`

这意味着 thesis 与非 thesis 已经共享同一套 task 基础设施，但执行实现分层清晰。

### 4.7 丰富了 feature 执行上下文

`features` router 在提交 task 时，现在会注入：

- `workspace_name`
- `workspace_description`
- `workspace_discipline`
- `workspace_config`

位置：

- `backend/src/gateway/routers/features.py`

这样后续 handler 不需要每次自己回查 workspace。

### 4.8 前端刷新闭环已泛化

已修改：

- `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`

当前行为：

- task 成功后读取 `status.result.refresh_targets`
- 根据目标刷新 `artifacts` / `papers` / `workspace`

这非常关键，因为后续新增 feature 时不需要在前端写：

- `if featureId === xxx then refresh yyy`

### 4.9 前端知识区已补充新 artifact 类型展示语义

已修改：

- `frontend/app/(workbench)/workspaces/[id]/components/KnowledgePanel.tsx`

已补：

- 新 artifact type 的 icon / color mapping
- type label 展示优化

### 4.10 新增了两份长期文档

已创建：

- `docs/2026-03-12-architecture-assessment.md`
- `docs/2026-03-12-feature-module-extension-guide.md`

用途：

- 第一份用于后续架构迭代判断
- 第二份用于后续新增 feature 的标准说明书

### 4.11 本轮最后补掉的两个框架级问题

#### 问题 A：用户 params 可以覆盖 canonical task payload 字段

原先 `features` router 在组装 payload 时把 `request.params` 平铺到顶层，存在覆盖以下字段的风险：

- `workspace_id`
- `workspace_type`
- `feature_id`
- `handler_key`
- `agent`

这属于真正的路由安全与一致性问题。

现已修复：

- `backend/src/gateway/routers/features.py`

并补了测试：

- `backend/tests/gateway/routers/test_features.py`

#### 问题 B：subagent cleanup 存在漏 await

现已修复：

- `backend/src/subagents/manager.py`
- `backend/tests/subagents/test_limiter.py`

效果：

- 清掉了这轮全量测试里最明显的 runtime warning 之一

## 5. 当前建议坚持的架构边界

后续继续开发时，请尽量不要打破以下边界。

### 5.1 router 不写 feature 业务逻辑

router 只负责：

- 鉴权
- workspace ownership 校验
- task payload 组装
- 提交任务
- 返回 task id

不要把 feature 的真实执行写回 router。

### 5.2 registry 是 feature 元数据唯一来源

位置：

- `backend/src/workspace_features/registry.py`

不要在前端单独写一套 feature 配置，也不要在 router 再复制一套定义。

### 5.3 非 thesis feature 一律通过 `handler_key` 扩展

正确模式：

- registry: feature -> `handler_key`
- runtime: `handler_key` -> handler

不要继续堆：

- `workspace_type + if/else`
- `feature_id + if/else`

### 5.4 artifact 是非 thesis feature 的第一落点

大多数非 thesis feature 第一阶段都应该：

- 先产出 artifact
- 让 KnowledgePanel 能看到
- 再考虑复杂编辑器

因为 artifact 是当前最稳定、最通用、最可复用的中间层。

### 5.5 前端刷新依赖 `refresh_targets`

不要重新回到按 `featureId` 写死刷新逻辑。

当前正确做法是：

- handler 决定 `refresh_targets`
- ChatPanel 统一消费 `refresh_targets`

## 6. Claude 接手时建议先读的文件

优先级从高到低如下：

1. `docs/2026-03-12-architecture-assessment.md`
2. `docs/2026-03-12-feature-module-extension-guide.md`
3. `docs/2026-03-12-claude-handoff.md`
4. `backend/src/workspace_features/registry.py`
5. `backend/src/workspace_features/runtime.py`
6. `backend/src/task/handlers/workspace_feature_handler.py`
7. `backend/src/workspace_features/handlers/software_copyright.py`
8. `backend/src/gateway/routers/features.py`
9. `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`
10. `frontend/app/(workbench)/workspaces/[id]/components/KnowledgePanel.tsx`
11. `backend/src/gateway/routers/chat.py`
12. `backend/src/services/chat_thread_service.py`

## 7. 当前验证结果

已完成验证：

### 7.1 后端全量回归

执行命令：

```bash
uv run pytest -q --ignore=tests/execution/test_latex_integration.py
```

结果：

- `1557 passed, 3 skipped, 102 warnings`

说明：

- 当前架构状态下，后端主干是稳定的
- 已知排除的 `latex integration` 仍然是外部 Docker 拉取限制问题，不是这轮代码引起

### 7.2 前端构建验证

执行命令：

```bash
npm run build
```

结果：

- 构建通过

### 7.3 定向回归

还单独跑过：

- `tests/gateway/routers/test_features.py`
- `tests/subagents/test_limiter.py`
- `tests/subagents/test_manager.py`

用于确认最后一轮框架修复没有引入回归。

## 8. 当前仍存在但不阻塞继续开发的问题

### 8.1 生产 JWT 密钥仍是默认值警告

位置：

- `backend/src/config/app_config.py`

这不是当前开发阻塞，但部署前必须处理。

### 8.2 测试中仍有 deprecation warnings

主要包括：

- `datetime.utcnow()` 相关 warning
- `HTTP_422_UNPROCESSABLE_ENTITY` 旧常量 warning
- LangGraph 旧导入 warning

这些不阻塞功能开发，但建议作为一轮工程清理任务处理。

### 8.3 非 thesis 能力层仍然偏薄

当前真正跑通的非 thesis feature 只有一个代表性样板：

- `software_copyright.copyright_materials`

这不是架构问题，而是能力层还没补满。

## 9. 后续建议的开发顺序

不建议先改大架构。建议按下面顺序继续。

### Phase 1: 补第二个真实 non-thesis handler

首选：

- `software_copyright.technical_description`

原因：

- 与已完成的 `copyright_materials` 同 workspace
- 复用当前 runtime / artifact / refresh 流程最顺手
- 能把 soft copyright workspace 的能力层样板再拉完整一步

实现建议：

- 输出 artifact type: `technical_description`
- 返回 `refresh_targets=["artifacts"]`
- 尽量支持“无参数也能先生成模板”

### Phase 2: 每个非 thesis workspace 至少跑通一个真实 feature

建议顺序：

1. `software_copyright.technical_description`
2. `proposal.background_research`
3. `patent.prior_art_search` 或等价 feature
4. `sci.paper_analysis` 或 `sci.literature_search`

目标：

- 让 4 个非 thesis workspace 都有一个真实闭环样板
- 这样后续并行开发才真正有模板可抄

### Phase 3: 补 feature 参数规范

建议下一步在 registry 上逐步引入可选字段：

- `params_schema`
- `default_params`
- `result_channels`

收益：

- 前端可以自动生成输入表单
- feature 输入不再完全依赖 quick action 的“零参数触发”

### Phase 4: 补 artifact 详情展示层

当前 KnowledgePanel 更像 timeline。

建议后续补：

- artifact detail drawer / modal
- 不同 artifact type 的 renderer

但这件事优先级低于继续补 handler。

### Phase 5: 工程告警和遗留清理

建议后续择机做：

- 清 JWT 默认密钥 warning
- 清 `utcnow()` deprecation
- 清 422 常量 deprecation
- 清 LangGraph 导入 deprecation
- 持续清理旧 `academic.*` 路径残留

## 10. 后续新增 feature 时的固定流程

如果 Claude 要新增功能模块，建议严格遵循以下流程：

1. 先确定它属于哪个 canonical workspace type
2. 确定它的第一输出落点是 artifact / papers / workspace
3. 在 `registry.py` 注册 feature
4. 如需新 artifact type，先改共享 taxonomy
5. 在 `workspace_features/handlers/` 中实现 handler
6. 通过 `context.update(...)` 发进度
7. 通过 `context.persist_artifacts(...)` 落结果
8. 返回标准 result contract
9. 必要时补 KnowledgePanel 映射
10. 补 router / handler / 回归测试

不要跳过 registry，不要跳过测试，不要把逻辑塞回 router。

## 11. 这轮涉及的关键文件索引

### 后端主线

- `backend/src/workspace_features/registry.py`
- `backend/src/workspace_features/contracts.py`
- `backend/src/workspace_features/runtime.py`
- `backend/src/workspace_features/handlers/software_copyright.py`
- `backend/src/task/handlers/workspace_feature_handler.py`
- `backend/src/gateway/routers/features.py`
- `backend/src/artifacts/types.py`
- `backend/src/database/models/chat_thread.py`
- `backend/src/services/chat_thread_service.py`
- `backend/src/gateway/routers/chat.py`
- `backend/alembic/versions/003_add_chat_threads_table.py`

### 前端主线

- `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/KnowledgePanel.tsx`

### 测试

- `backend/tests/gateway/routers/test_features.py`
- `backend/tests/task/test_workspace_feature_handler.py`
- `backend/tests/gateway/routers/test_chat.py`
- `backend/tests/services/test_chat_thread_service.py`
- `backend/tests/subagents/test_limiter.py`

## 12. 最后结论

当前项目的状态可以概括为：

- 架构主干已经收住
- thesis 主链路继续保留
- non-thesis 已经有统一扩展骨架
- 第一个真实 non-thesis 样板已经通了
- 后续最值当的事情是继续补能力层，而不是再次重构主干

如果让 Claude 接手，最合理的第一步不是“重新 review 一遍再设计”，而是：

1. 读完上面列出的 3 份文档
2. 以 `software_copyright.technical_description` 为下一个样板继续落 handler
3. 然后把 `proposal / patent / sci` 各补一个真实 feature

这样推进，和当前代码库最匹配，成本最低，收益最高。
