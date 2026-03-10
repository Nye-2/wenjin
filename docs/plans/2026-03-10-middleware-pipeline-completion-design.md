# 16层中间件管道完善设计文档

> 创建日期: 2026-03-10
> 状态: 已批准
> 作者: Claude + 用户

## 1. 概述

### 1.1 背景

AcademiaGPT-V2 当前已实现 12 层中间件管道，但缺少 4 个关键中间件来完成与 deer-flow 架构的对齐：

- SandboxMiddleware - 沙箱生命周期管理
- MemoryMiddleware - 长期记忆持久化
- TodoListMiddleware - Plan 模式任务追踪
- ViewImageMiddleware - Vision 模型图片注入

### 1.2 目标

完成 16 层完整中间件管道，确保：

1. 沙箱系统能正确集成到代理执行流程
2. 记忆系统能跨会话持久化学术上下文
3. Plan 模式支持复杂多步骤任务追踪
4. Vision 模型支持图片输入处理

## 2. 完整管道架构

### 2.1 16层管道（严格执行顺序）

```
┌─ 基础设施层 (Infrastructure) ───────────────────────────┐
│  1. ThreadDataMiddleware       → 创建线程目录             │
│  2. UploadsMiddleware          → 追踪上传文件             │
│  3. SandboxMiddleware          → 获取沙箱实例 (新增)      │
├─ 修复层 (Fix) ──────────────────────────────────────────┤
│  4. DanglingToolCallMiddleware → 修补缺失 ToolMessage    │
├─ 上下文管理层 (Context Management) ─────────────────────┤
│  5. SummarizationMiddleware    → Token 超限自动摘要      │
│  6. MemoryMiddleware           → 异步记忆更新 (新增)     │
├─ 学术上下文层 (Academic Context) ───────────────────────┤
│  7. WorkspaceContextMiddleware → 加载 workspace 配置     │
│  8. LiteratureContextMiddleware→ ToC 文献导航注入        │
│  9. KnowledgeContextMiddleware → 加载知识库 artifacts    │
│ 10. DisciplineContextMiddleware→ 注入学科写作规范        │
├─ 交互层 (Interaction) ──────────────────────────────────┤
│ 11. TodoListMiddleware         → Plan 模式任务追踪 (新增) │
│ 12. ViewImageMiddleware        → Vision 模型图片 (新增)  │
│ 13. SubagentLimitMiddleware    → 子 Agent 并发限制       │
├─ 后处理层 (Post-processing) ────────────────────────────┤
│ 14. TitleMiddleware            → 自动生成线程标题        │
│ 15. CitationContextMiddleware  → 引用追踪                │
│ 16. ClarificationMiddleware    → 拦截 ask_clarification  │
└──────────────────────────────────────────────────────────┘
```

### 2.2 层序设计理由

| 层级 | 位置理由 |
|------|---------|
| 基础设施层 (1-3) | 最先执行，确保目录/文件/沙箱准备就绪 |
| 修复层 (4) | 在注入上下文前修补消息完整性 |
| 上下文管理层 (5-6) | 处理"对话历史"维度，在学术上下文之前 |
| 学术上下文层 (7-10) | 处理"领域知识"维度，在摘要之后避免被压缩 |
| 交互层 (11-13) | 与 Agent 执行直接相关的控制 |
| 后处理层 (14-16) | 模型输出后的处理，ClarificationMiddleware 必须最后 |

### 2.3 条件启用

| 中间件 | 启用条件 |
|--------|----------|
| SandboxMiddleware | config.sandbox.enabled |
| SummarizationMiddleware | config.middlewares.summarization.enabled |
| MemoryMiddleware | config.memory.enabled |
| WorkspaceContextMiddleware | state.workspace_id 存在 |
| LiteratureContextMiddleware | state.workspace_id 存在 |
| KnowledgeContextMiddleware | state.workspace_id 存在 |
| TodoListMiddleware | config.configurable.is_plan_mode |
| ViewImageMiddleware | model.supports_vision |
| SubagentLimitMiddleware | config.configurable.subagent_enabled |
| CitationContextMiddleware | state.workspace_id 存在 |

## 3. 新增中间件详细设计

### 3.1 SandboxMiddleware

**职责**: 管理 SandboxProvider 的生命周期

**接口**:
```python
class SandboxMiddleware(Middleware):
    def __init__(self, provider: SandboxProvider):
        self.provider = provider

    async def before_model(self, state: ThreadState, config: RunnableConfig) -> dict:
        thread_id = config.get("configurable", {}).get("thread_id")
        sandbox = await self.provider.acquire(thread_id)
        return {"sandbox": {"sandbox_id": sandbox.sandbox_id}}

    async def after_model(self, state: ThreadState, config: RunnableConfig) -> dict:
        # 沙箱在会话结束时释放（由 provider 管理）
        return {}
```

**依赖**: `src/sandbox/providers/base.py:SandboxProvider`

### 3.2 MemoryMiddleware

**职责**: 异步更新长期记忆

**接口**:
```python
class MemoryMiddleware(Middleware):
    def __init__(self, memory_queue: MemoryQueue, memory_updater: MemoryUpdater):
        self.queue = memory_queue
        self.updater = memory_updater

    async def after_model(self, state: ThreadState, config: RunnableConfig) -> dict:
        # 过滤出用户输入 + 最终 AI 响应
        messages = self._filter_messages(state["messages"])
        # 加入防抖队列
        await self.queue.enqueue(messages)
        return {}
```

**依赖**: `src/agents/memory/queue.py`, `src/agents/memory/updater.py`

**配置**:
```yaml
memory:
  enabled: true
  injection_enabled: true
  storage_path: "backend/.academiagpt/memory.json"
  debounce_seconds: 30
  max_facts: 100
  fact_confidence_threshold: 0.7
```

### 3.3 TodoListMiddleware

**职责**: Plan 模式下的任务列表管理

**接口**:
```python
class TodoListMiddleware(Middleware):
    def __init__(self):
        self._todos: list[TodoItem] = []

    async def before_model(self, state: ThreadState, config: RunnableConfig) -> dict:
        if not config.get("configurable", {}).get("is_plan_mode"):
            return {}
        # 注入 write_todos 工具说明
        return {"todos": self._todos}

    async def after_model(self, state: ThreadState, config: RunnableConfig) -> dict:
        # 处理 write_todos 工具调用
        return {}
```

**TodoItem 结构**:
```python
@dataclass
class TodoItem:
    content: str
    status: str  # pending, in_progress, completed
    priority: str  # high, medium, low
```

### 3.4 ViewImageMiddleware

**职责**: Vision 模型图片预处理

**接口**:
```python
class ViewImageMiddleware(Middleware):
    async def before_model(self, state: ThreadState, config: RunnableConfig) -> dict:
        # 检查模型是否支持 vision
        if not self._supports_vision(config):
            return {}

        # 处理 viewed_images 中的图片
        viewed_images = state.get("viewed_images", {})
        processed = {}

        for path, data in viewed_images.items():
            processed[path] = {
                "base64": data["base64"],
                "mime_type": data["mime_type"]
            }

        return {"viewed_images": processed}
```

## 4. ThreadState 扩展

### 4.1 新增字段

```python
class ThreadState(AgentState):
    # ... 现有字段 ...

    # 新增字段
    todos: NotRequired[list[TodoItem] | None]  # Plan 模式任务列表
```

### 4.2 字段验证

| 字段 | 类型 | Reducer | 说明 |
|------|------|---------|------|
| todos | list | 替换 | 任务列表 |
| viewed_images | dict | merge_viewed_images | 图片数据 |
| sandbox | dict | - | 沙箱状态 |

## 5. 实施计划

### Phase 1: 基础中间件 (2-3h)

1. **创建 SandboxMiddleware**
   - 文件: `src/agents/middlewares/sandbox.py`
   - 从 deer-flow 移植逻辑
   - 集成现有 SandboxProvider

2. **创建 MemoryMiddleware**
   - 文件: `src/agents/middlewares/memory.py`
   - 连接 memory/queue.py 和 memory/updater.py
   - 添加配置加载

3. **更新 middlewares/__init__.py**
   - 添加新中间件导出

### Phase 2: 交互中间件 (2-3h)

1. **创建 TodoListMiddleware**
   - 文件: `src/agents/middlewares/todo_list.py`
   - 实现 write_todos 工具处理
   - Plan 模式条件启用

2. **创建 ViewImageMiddleware**
   - 文件: `src/agents/middlewares/view_image.py`
   - Vision 模型检测
   - 图片 base64 转换

3. **更新 middlewares/__init__.py**
   - 添加新中间件导出

### Phase 3: 管道集成 (1-2h)

1. **更新 build_pipeline()**
   - 文件: `src/agents/lead_agent/agent.py`
   - 按 16 层顺序组装
   - 添加条件启用逻辑

2. **更新 ThreadState**
   - 验证所有字段定义
   - 添加缺失的 reducer

3. **添加配置支持**
   - 文件: `src/config/app_config.py`
   - 添加中间件配置项

### Phase 4: 测试与验证 (2-3h)

1. **单元测试**
   - 每个新中间件的独立测试
   - Mock 依赖组件

2. **集成测试**
   - 完整管道端到端测试
   - 条件启用场景覆盖

3. **回归测试**
   - 确保现有功能不受影响
   - 790+ 测试全部通过

## 6. 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| 管道顺序错误导致状态混乱 | 严格按照层级设计，添加顺序验证 |
| Memory 系统异步更新冲突 | 使用防抖队列 + 原子写入 |
| Sandbox 生命周期管理复杂 | 由 Provider 统一管理，中间件只负责获取 |
| 条件启用逻辑复杂 | 集中在 build_pipeline() 中处理 |

## 7. 验收标准

- [ ] 16 层中间件全部实现
- [ ] build_pipeline() 按正确顺序组装
- [ ] 条件启用逻辑正确工作
- [ ] Memory 系统跨会话持久化
- [ ] Plan 模式任务追踪可用
- [ ] Vision 模型图片处理可用
- [ ] 所有现有测试通过
- [ ] 新增测试覆盖率 > 80%

## 8. 文件清单

### 新增文件
- `src/agents/middlewares/sandbox.py`
- `src/agents/middlewares/memory.py`
- `src/agents/middlewares/todo_list.py`
- `src/agents/middlewares/view_image.py`

### 修改文件
- `src/agents/middlewares/__init__.py`
- `src/agents/lead_agent/agent.py`
- `src/agents/thread_state.py`
- `src/config/app_config.py`

### 测试文件
- `tests/unit/middlewares/test_sandbox.py`
- `tests/unit/middlewares/test_memory.py`
- `tests/unit/middlewares/test_todo_list.py`
- `tests/unit/middlewares/test_view_image.py`
- `tests/integration/test_middleware_pipeline.py`
