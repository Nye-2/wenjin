# AcademiaGPT-V2 功能模块扩展说明书

## 1. 文档目的

这份文档用于指导后续在当前架构下新增或扩展 workspace feature。

目标不是“写一个能跑的 feature”，而是“按统一规范增加一个可维护、可测试、可插拔的能力模块”。

## 2. 先理解当前 feature 的标准链路

一个标准 feature 的执行链路如下：

1. 前端工作台加载 workspace
2. 前端调用 `/workspaces/{workspace_id}/features`
3. 后端从 `workspace_features/registry.py` 返回 feature 元数据
4. 用户点击 quick action
5. 前端调用 `/workspaces/{workspace_id}/features/{feature_id}/execute`
6. router 做鉴权与 workspace ownership 校验
7. router 通过 `TaskService` 提交异步任务
8. task handler 通过 `handler_key` 调到具体 feature handler
9. handler 执行业务逻辑，必要时持久化 artifact
10. handler 返回统一 result contract
11. 前端轮询 `/tasks/{task_id}`
12. 前端根据 `refresh_targets` 刷新 artifacts / papers / workspace

## 3. 新增 feature 时必须遵守的原则

### 3.1 不要在 router 中写 feature 业务逻辑

router 只能做：

- 鉴权
- workspace ownership 校验
- task payload 组装
- task 提交

业务逻辑必须写进 handler。

### 3.2 不要在前端手写 feature 配置

feature 元数据的唯一来源是：

- `backend/src/workspace_features/registry.py`

前端通过接口发现，不要单独维护另一套常量。

### 3.3 新增能力必须绑定 `handler_key`

每个 feature 都必须有稳定的 `handler_key`，格式建议为：

- `{workspace_type}.{feature_name}`

例如：

- `software_copyright.copyright_materials`
- `patent.prior_art_search`
- `proposal.background_research`

### 3.4 能落 artifact 的 feature，优先先落 artifact

不要一开始就做复杂编辑器。

第一阶段的标准闭环应该是：

- feature 执行成功
- 结果持久化为 artifact
- knowledge panel 能看到
- task result 返回 `refresh_targets=["artifacts"]`

## 4. 新增 feature 的标准流程

### Step 1: 确定 feature 所属 workspace 与输出物

先回答 4 个问题：

1. 它属于哪个 canonical workspace type？
2. 它的核心输出是什么？
3. 输出应该先落 artifact、paper 还是 workspace config？
4. 它需要用户输入参数吗？没有参数时能否先生成模板？

如果这 4 个问题回答不清，不要开始写代码。

### Step 2: 在 registry 中注册 feature

文件：

- `backend/src/workspace_features/registry.py`

必须定义：

- `workspace_type`
- `id`
- `name`
- `description`
- `icon`
- `agent`
- `agent_label`
- `handler_key`
- `task_type`
- `panel`
- `stages`
- `color`

要求：

- `id` 在同一 workspace type 下唯一
- `handler_key` 全局唯一
- `task_type` 默认使用 `workspace_feature`
- 如果是 thesis 真 workflow，使用 `thesis_generation`

### Step 3: 选择 artifact type

artifact type 必须来自共享 taxonomy：

- `backend/src/artifacts/types.py`

如果确实需要新增 artifact type：

1. 先在共享 taxonomy 中加
2. 不要只改 ORM，不要只改 validator
3. 评估 knowledge panel 是否需要更合适的 icon / color

### Step 4: 实现 handler

推荐位置：

- `backend/src/workspace_features/handlers/<workspace_type>.py`

推荐模式：

1. 使用 `@register_feature_handler("<handler_key>")`
2. handler 签名使用 `WorkspaceFeatureExecutionContext`
3. 通过 `context.params` 读参数
4. 通过 `context.update(...)` 发进度
5. 通过 `context.persist_artifacts(...)` 持久化结果
6. 返回 `WorkspaceFeatureExecutionResult`

### Step 5: 定义标准 result contract

非 thesis feature 的标准返回字段：

- `message`
- `artifacts`
- `refresh_targets`
- `next_steps`
- `data`
- `success`

约定：

- 如果生成了 artifact，`refresh_targets` 必须包含 `artifacts`
- 如果修改了文献列表，`refresh_targets` 必须包含 `papers`
- 如果修改了 workspace 基本信息或配置，`refresh_targets` 必须包含 `workspace`

### Step 6: 必要时补前端展示语义

如果新增 artifact type，检查：

- `frontend/app/(workbench)/workspaces/[id]/components/KnowledgePanel.tsx`

至少要补：

- icon mapping
- color mapping

否则虽然能显示，但可读性会差。

### Step 7: 补测试

至少补 3 类测试：

1. Router test
   - feature 列表返回
   - execute payload 正确
   - owner isolation 正确

2. Handler test
   - handler 能执行
   - artifact 会被持久化
   - result contract 符合规范

3. 回归测试
   - task / workspace / frontend build 不被破坏

## 5. 推荐的目录落点

### 5.1 后端

- registry: `backend/src/workspace_features/registry.py`
- contracts: `backend/src/workspace_features/contracts.py`
- runtime: `backend/src/workspace_features/runtime.py`
- handlers: `backend/src/workspace_features/handlers/`
- task bridge: `backend/src/task/handlers/workspace_feature_handler.py`

### 5.2 前端

- feature discover/store: `frontend/stores/features.ts`
- task polling: `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`
- artifact timeline: `frontend/app/(workbench)/workspaces/[id]/components/KnowledgePanel.tsx`

## 6. 标准实现模板

### 6.1 Registry 模板

```python
WorkspaceFeatureDefinition(
    workspace_type="proposal",
    id="background_research",
    name="背景调研",
    description="调研项目背景和现状",
    icon="book",
    agent="scout",
    agent_label="Scout",
    handler_key="proposal.background_research",
    task_type="workspace_feature",
    panel="literature_panel",
    color="emerald",
    stages=(
        _stage("search", "搜索资料"),
        _stage("summarize", "整理归纳"),
    ),
)
```

### 6.2 Handler 模板

```python
@register_feature_handler("proposal.background_research")
async def build_background_research(
    context: WorkspaceFeatureExecutionContext,
) -> WorkspaceFeatureExecutionResult:
    await context.update(20, "收集背景资料", current_step="search")

    artifact = FeatureArtifactDraft(
        type=ArtifactType.BACKGROUND_RESEARCH.value,
        title=f"{context.workspace_name} 背景调研",
        content={"summary": "..."},
        created_by_skill=context.handler_key,
    )

    artifacts = await context.persist_artifacts([artifact])

    await context.update(90, "已保存背景调研结果", current_step="summarize")

    return WorkspaceFeatureExecutionResult(
        message="已生成背景调研初稿",
        artifacts=artifacts,
        refresh_targets=["artifacts"],
    )
```

## 7. 参数设计建议

如果 feature 有参数需求，优先遵守以下策略：

### 7.1 先支持“无参数模板输出”

先保证用户不填参数也能得到一个可编辑模板，而不是一上来就强依赖复杂表单。

### 7.2 参数放到 `params`

execute 请求的 feature-specific 参数统一放在：

- `request.params`

不要把 feature 私有参数直接铺在 router request 顶层。

### 7.3 优先从 workspace context 补默认值

handler 应优先使用：

- `workspace_name`
- `workspace_description`
- `workspace_discipline`
- `workspace_config`

这样 feature 才能在参数较少时仍然生成合理初稿。

## 8. 什么时候需要新增前端专属 UI

满足以下任一条件，再考虑加 feature-specific UI：

- 参数超过 5 个且具有明确结构
- 输出不是 artifact timeline 能承载的内容
- 用户需要在生成后立即编辑
- 需要多轮逐步配置

否则优先走 artifact 闭环。

## 9. 合格 feature 的完成标准

一个 feature 只有满足以下条件，才算真正接入完成：

1. 可以被 `/features` 自动发现
2. 可以通过 `/execute` 正确提交任务
3. 任务状态可轮询
4. 结果可以稳定落到 artifact / paper / workspace
5. 前端会根据 `refresh_targets` 自动刷新
6. 有至少一条 handler 测试
7. 不破坏现有回归测试

## 10. 当前推荐的后续扩展顺序

建议按以下顺序扩展能力层：

1. `software_copyright.technical_description`
2. `patent.patent_outline`
3. `proposal.background_research`
4. `sci.paper_analysis`

原因：

- 都可以先以 artifact 闭环落地
- 不依赖 thesis 那套复杂 workflow
- 能快速验证当前架构的复用性

## 11. 一条底线

后续每增加一个 feature，如果需要同时改：

- router 业务逻辑
- 前端 feature 常量
- task 分发 if/else
- 单独写死刷新逻辑

那就说明没有按当前架构正确扩展。

正确方向应当是：

- registry 扩定义
- handler 挂能力
- result contract 告诉前端刷新什么
- 前端通用机制自动消费
