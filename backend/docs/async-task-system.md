# Async Task System

> 异步任务系统 - 基于 Celery + Redis + PostgreSQL 的分布式任务处理框架

## 概述

Async Task System 是 AcademiaGPT v2 的核心基础设施，用于处理长时间运行的学术研究任务。系统支持任务提交、进度追踪、实时流式更新和任务取消等功能。

### 核心特性

- **异步执行**: 基于 Celery 的分布式任务队列
- **进度追踪**: 实时进度更新，支持 SSE 流式推送
- **优先级队列**: 支持高/中/低优先级任务
- **持久化存储**: PostgreSQL 存储任务历史记录
- **运行时状态**: Redis 存储实时状态，支持快速查询
- **可扩展**: 插件式任务处理器，易于扩展新任务类型

---

## 架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Client Layer                                   │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐              │
│  │   REST API   │    │  SSE Stream  │    │    Web UI    │              │
│  │  POST /tasks │    │ GET /stream  │    │   (Future)   │              │
│  └──────┬───────┘    └──────┬───────┘    └──────────────┘              │
└─────────┼───────────────────┼────────────────────────────────────────────┘
          │                   │
          ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Gateway Layer                                   │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  src/gateway/routers/tasks.py                                     │  │
│  │  • POST /tasks/          → submit_task()                          │  │
│  │  • GET  /tasks/{id}      → get_task_status()                      │  │
│  │  • GET  /tasks/          → list_tasks()                           │  │
│  │  • DELETE /tasks/{id}    → cancel_task()                          │  │
│  │  • GET  /tasks/{id}/stream → SSE progress stream                  │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Service Layer                                   │
│  ┌─────────────────────┐    ┌─────────────────────┐                     │
│  │ src/task/service.py │    │ src/task/progress.py│                     │
│  │    TaskService      │    │  ProgressTracker    │                     │
│  │  • submit_task()    │    │  • update()         │                     │
│  │  • get_task_status()│    │  • complete()       │                     │
│  │  • cancel_task()    │    │  • fail()           │                     │
│  └──────────┬──────────┘    └──────────┬──────────┘                     │
└─────────────┼──────────────────────────┼─────────────────────────────────┘
              │                          │
              ▼                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Storage Layer                                   │
│  ┌───────────────────────────┐    ┌─────────────────────────────────┐   │
│  │   src/task/store.py       │    │ src/database/models/task.py     │   │
│  │      TaskStore            │    │      TaskRecord                 │   │
│  │  • Redis: Runtime state   │    │  • PostgreSQL: Persistence      │   │
│  │  • PostgreSQL: Records    │    │  • Full task history            │   │
│  └───────────────────────────┘    └─────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Task Execution Layer                              │
│  ┌─────────────────┐    ┌─────────────────────────────────────────┐     │
│  │  Celery Broker  │    │         Celery Worker                   │     │
│  │    (Redis)      │───▶│    src/task/tasks/base.py              │     │
│  │                 │    │    execute_task() → _dispatch_task()    │     │
│  └─────────────────┘    └──────────────────┬──────────────────────┘     │
└─────────────────────────────────────────────┼────────────────────────────┘
                                              │
                                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Task Handlers (Plug-in Point)                       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐          │
│  │  deep_research  │  │thesis_generation│  │literature_search│          │
│  │   文献调研       │  │    论文生成      │  │    语义搜索     │          │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘          │
│  ┌─────────────────┐                                                      │
│  │paper_processing │  ← 在 registry.py 注册新任务类型                      │
│  │    PDF解析      │                                                      │
│  └─────────────────┘                                                      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 文件结构

```
src/task/
├── __init__.py           # 模块导出
├── celery_app.py         # Celery 应用配置
├── registry.py           # 任务类型注册表 + TaskStatus/TaskQueue 枚举
├── store.py              # TaskStore (Redis + PostgreSQL)
├── service.py            # TaskService (业务逻辑)
├── progress.py           # ProgressTracker (进度追踪)
├── sse.py                # SSE 实时流
├── worker.py             # Worker 启动入口
└── tasks/
    ├── __init__.py       # 任务模块导出
    └── base.py           # execute_task + _dispatch_task

src/database/models/
└── task.py               # TaskRecord SQLAlchemy 模型

src/config/
└── task_config.py        # TaskSettings (Pydantic 配置)

src/gateway/routers/
└── tasks.py              # FastAPI 路由
```

---

## 核心组件

### 1. TaskStatus (任务状态)

```python
# src/task/registry.py
class TaskStatus(str, Enum):
    PENDING = "pending"      # 等待执行
    RUNNING = "running"      # 执行中
    SUCCESS = "success"      # 成功完成
    FAILED = "failed"        # 执行失败
    CANCELLED = "cancelled"  # 已取消

    @classmethod
    def terminal_statuses(cls) -> set["TaskStatus"]:
        """返回终态状态集合"""
        return {cls.SUCCESS, cls.FAILED, cls.CANCELLED}
```

### 2. TaskQueue (任务队列)

```python
# src/task/registry.py
class TaskQueue(str, Enum):
    DEFAULT = "default"           # 默认队列
    LONG_RUNNING = "long_running" # 长时间运行任务
    PRIORITY = "priority"         # 高优先级队列
```

### 3. TaskTypeConfig (任务配置)

```python
# src/task/registry.py
@dataclass
class TaskTypeConfig:
    queue: str = TaskQueue.DEFAULT    # 目标队列
    timeout: int = 600                # 超时时间 (秒)
    retry: int = 2                    # 重试次数
    retry_delay: int = 60             # 重试延迟 (秒)
    description: str = ""             # 任务描述
```

### 4. TASK_REGISTRY (任务注册表)

```python
# src/task/registry.py
TASK_REGISTRY: dict[str, TaskTypeConfig] = {
    "deep_research": TaskTypeConfig(
        queue=TaskQueue.DEFAULT,
        timeout=600,
        retry=2,
        description="深度研究: 文献搜索、分析和总结",
    ),
    "thesis_generation": TaskTypeConfig(
        queue=TaskQueue.LONG_RUNNING,
        timeout=3600,
        retry=1,
        description="论文生成: 完整学术论文写作",
    ),
    "literature_search": TaskTypeConfig(
        queue=TaskQueue.DEFAULT,
        timeout=300,
        retry=2,
        description="文献搜索: Semantic Scholar, arXiv 搜索",
    ),
    "paper_processing": TaskTypeConfig(
        queue=TaskQueue.DEFAULT,
        timeout=120,
        retry=1,
        description="论文处理: PDF 解析, 元数据提取",
    ),
}
```

---

## API 接口

### 提交任务

```http
POST /api/tasks/
Content-Type: application/json

{
    "task_type": "deep_research",
    "priority": 5,
    "payload": {
        "query": "machine learning in healthcare"
    }
}
```

**响应:**
```json
{
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "pending"
}
```

### 查询任务状态

```http
GET /api/tasks/{task_id}
```

**响应:**
```json
{
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "task_type": "deep_research",
    "status": "running",
    "progress": 45,
    "message": "Searching Semantic Scholar...",
    "result": null,
    "error": null,
    "created_at": "2024-01-15T10:30:00+00:00",
    "started_at": "2024-01-15T10:30:01+00:00",
    "completed_at": null
}
```

### 列出任务

```http
GET /api/tasks/?status=running&task_type=deep_research&limit=20
```

**响应:**
```json
{
    "tasks": [...],
    "count": 5
}
```

### 取消任务

```http
DELETE /api/tasks/{task_id}
```

**响应:**
```json
{
    "success": true,
    "task_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### SSE 进度流

```http
GET /api/tasks/{task_id}/stream
Accept: text/event-stream
```

**响应流:**
```
data: {"task_id":"...","status":"running","progress":10,"message":"Starting..."}

data: {"task_id":"...","status":"running","progress":50,"message":"Processing..."}

data: {"task_id":"...","status":"success","progress":100,"message":"Completed"}
```

---

## 使用指南

### 方式一: 自动对接 Skill (推荐)

系统会自动将注册的 Skill 映射到对应的任务类型:

```
Task Type          → Skill Name
───────────────────────────────────
deep_research      → deep-research
thesis_generation  → thesis-generation
literature_search  → literature-search
paper_processing   → paper-processing
```

**添加新 Skill 自动对接:**

1. 在 `src/skills/implementations/` 创建新的 Skill 类

2. 在 `src/task/handlers/skill_handler.py` 的 `TASK_TO_SKILL_MAP` 添加映射:

```python
TASK_TO_SKILL_MAP = {
    # ... 现有映射
    "my_new_task": "my-new-skill",  # 添加这行
}
```

3. 在 `src/task/registry.py` 的 `TASK_REGISTRY` 添加配置:

```python
TASK_REGISTRY["my_new_task"] = TaskTypeConfig(
    queue=TaskQueue.DEFAULT,
    timeout=300,
    retry=2,
    description="我的新任务描述",
)
```

4. 重启 Worker 即可生效！

### 方式二: 从其他模块调用

```python
from src.task import TaskService, TaskStore
from src.academic.cache.redis_client import redis_client
from src.database import get_db_session

async def start_research(user_id: str, query: str) -> str:
    """提交深度研究任务"""
    async with get_db_session() as db:
        store = TaskStore(redis_client, db)
        service = TaskService(store)

        task_id = await service.submit_task(
            user_id=user_id,
            task_type="deep_research",
            payload={"query": query},
            priority=5,
        )
        return task_id
```

### 方式三: 在 Skill 中集成

```python
# src/skills/deep_research_skill.py
class DeepResearchSkill(BaseSkill):
    async def execute(self, query: str, user_id: str):
        # 提交异步任务
        task_id = await self.task_service.submit_task(
            user_id=user_id,
            task_type="deep_research",
            payload={"query": query},
        )

        # 返回任务ID供前端监听
        return {
            "task_id": task_id,
            "status": "pending",
            "stream_url": f"/api/tasks/{task_id}/stream"
        }
```

---

## 前端集成

### JavaScript/TypeScript 示例

```typescript
// 提交任务
async function submitTask(taskType: string, payload: any): Promise<string> {
    const response = await fetch('/api/tasks/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            task_type: taskType,
            priority: 5,
            payload: payload
        })
    });
    const { task_id } = await response.json();
    return task_id;
}

// 监听进度 (SSE)
function streamProgress(taskId: string, onUpdate: (data: any) => void) {
    const eventSource = new EventSource(`/api/tasks/${taskId}/stream`);

    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        onUpdate(data);

        // 检查是否完成
        if (['success', 'failed', 'cancelled'].includes(data.status)) {
            eventSource.close();
        }
    };

    eventSource.onerror = () => {
        eventSource.close();
    };

    return () => eventSource.close(); // 返回清理函数
}

// 使用示例
const taskId = await submitTask('deep_research', { query: 'AI in medicine' });
const cleanup = streamProgress(taskId, (data) => {
    console.log(`Progress: ${data.progress}% - ${data.message}`);
    if (data.status === 'success') {
        console.log('Result:', data.result);
    }
});
```

---

## 部署指南

### 启动 Worker

```bash
# 基本启动
python -m src.task.worker

# 指定并发数
python -m src.task.worker 8

# 使用 celery 命令
celery -A src.task.celery_app worker --concurrency=4 --loglevel=info

# 启动特定队列
celery -A src.task.celery_app worker -Q long_running --loglevel=info

# 启动多个队列
celery -A src.task.celery_app worker -Q default,long_running,priority
```

### Docker 部署

```dockerfile
# Dockerfile.worker
FROM python:3.13-slim

WORKDIR /app
COPY . .

RUN pip install -e .

CMD ["celery", "-A", "src.task.celery_app", "worker", "--concurrency=4", "--loglevel=info"]
```

```yaml
# docker-compose.yml
services:
  worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    depends_on:
      - redis
      - postgres
    environment:
      - TASK_CELERY_BROKER_URL=redis://redis:6379/1
      - TASK_CELERY_RESULT_BACKEND=redis://redis:6379/2
      - DATABASE_URL=postgresql://user:pass@postgres:5432/academiagpt
```

### 环境变量

```bash
# .env
TASK_CELERY_BROKER_URL=redis://localhost:6379/1
TASK_CELERY_RESULT_BACKEND=redis://localhost:6379/2
TASK_WORKER_CONCURRENCY=4
TASK_WORKER_PREFETCH_MULTIPLIER=2
TASK_TASK_SOFT_TIME_LIMIT=600
TASK_TASK_TIME_LIMIT=900
TASK_TASK_REDIS_TTL=86400
TASK_MAX_CONCURRENT_TASKS_PER_USER=3
```

---

## 监控

### Flower (Celery 监控 UI)

```bash
# 启动 Flower
celery -A src.task.celery_app flower --port=5555

# 访问 http://localhost:5555
```

### 健康检查

```python
# 检查 Worker 状态
from src.task import celery_app

def check_workers():
    inspect = celery_app.control.inspect()
    active = inspect.active()
    return active is not None
```

---

## 最佳实践

### 1. 任务设计原则

- **幂等性**: 任务应该可以安全重试
- **进度报告**: 频繁调用 `progress.update()` 提供反馈
- **超时设置**: 根据任务复杂度设置合理的 timeout
- **错误处理**: 捕获并记录异常，使用 `progress.fail()` 通知

### 2. 性能优化

- **批量操作**: 合并多个小任务为一个大任务
- **进度节流**: 避免过于频繁的进度更新 (建议间隔 >= 1秒)
- **资源清理**: 任务完成后清理临时资源

### 3. 安全考虑

- **输入验证**: 在任务处理器中验证 payload
- **权限检查**: 确保用户只能访问自己的任务
- **敏感数据**: 避免在 payload 中传递敏感信息

---

## 故障排除

### 任务卡在 PENDING 状态

1. 检查 Worker 是否运行: `celery -A src.task.celery_app inspect active`
2. 检查 Redis 连接
3. 检查队列名称是否匹配

### 任务执行失败

1. 查看 Worker 日志
2. 检查 `TaskRecord.error` 字段
3. 验证 payload 格式

### SSE 连接断开

1. 检查 Nginx 配置 (需要禁用 buffering)
2. 增加超时时间
3. 实现客户端重连逻辑

---

## Skill 集成指南

### 自动对接机制

Async Task System 已内置与 Skill 系统的自动对接机制：

```
┌─────────────────────────────────────────────────────────────────┐
│                     Task → Skill 映射                            │
├─────────────────────────────────────────────────────────────────┤
│  Task Type              →  Skill Name                           │
│  ──────────────────────────────────────────────────────────────  │
│  deep_research           →  deep-research (DeepResearchSkillV2)  │
│  thesis_generation       →  thesis-generation                   │
│  literature_search       →  literature-search                   │
│  paper_processing        →  paper-processing                    │
└─────────────────────────────────────────────────────────────────┘
```

### 对接流程

```
1. 用户调用 API                2. TaskService              3. Celery Worker
   POST /api/tasks/      →     submit_task()       →      execute_task()
   {                       │     • 创建 DB 记录    │      • 启动 Progress
     task_type: "deep_   │     • 发送到 Celery    │      • 调用 _dispatch_task()
     research",           │                          │      ↓
     payload: {...}       │                          │   4. SkillTaskHandler
   }                       │                          │      • 查找 skill 映射
                          │                          │      • 创建 SkillInput
                          │                          │      • 调用 SkillExecutor
                          │                          │      ↓
                          │                          │   5. DeepResearchSkill
                          │                          │      • execute_async()
                          │                          │      • 进度更新
                          │                          │      • 返回结果
```

### 添加新任务类型

**步骤 1**: 在 `registry.py` 注册任务类型

```python
# src/task/registry.py
TASK_REGISTRY["my_new_task"] = TaskTypeConfig(
    queue=TaskQueue.DEFAULT,
    timeout=300,
    retry=2,
    description="我的新任务",
)
```

**步骤 2**: 创建对应的 Skill

```python
# src/skills/implementations/my_new_task.py
class MyNewTaskSkill(BaseSkill):
    name = "my-new-task"  # 注意: 使用 kebab-case
    description = "我的新任务 Skill"
    version = "1.0.0"

    def execute(self, input: SkillInput, state: ThreadState) -> SkillOutput:
        # 实现任务逻辑
        return SkillOutput(
            success=True,
            content="任务完成",
            metadata={"key": "value"}
        )
```

**步骤 3**: 在 `skill_handler.py` 添加映射

```python
# src/task/handlers/skill_handler.py
class SkillTaskHandler:
    TASK_TO_SKILL_MAP = {
        # ... 现有映射 ...
        "my_new_task": "my-new-task",  # 添加这行
    }
```

**步骤 4**: 在 `skill_handler.py` 注册 Skill

```python
# src/task/handlers/skill_handler.py
def _load_skills(self) -> None:
    # ... 现有导入 ...
    from src.skills.implementations.my_new_task import MyNewTaskSkill

    self._executor.register_skill(MyNewTaskSkill())
```

### 自动注册机制 (未来增强)

可以通过装饰器实现自动注册：

```python
# 未来方案: 自动注册装饰器
@skill_task(
    task_type="my_new_task",
    queue=TaskQueue.DEFAULT,
    timeout=300,
)
class MyNewTaskSkill(BaseSkill):
    name = "my-new-task"
    # ... 装饰器自动处理 TASK_REGISTRY 和 TASK_TO_SKILL_MAP
```

### 调用示例

```python
# 从业务代码提交任务
from src.task import TaskService, TaskStore
from src.academic.cache.redis_client import redis_client
from src.database import get_db_session

async def start_deep_research(user_id: str, workspace_id: str, query: str) -> str:
    async with get_db_session() as db:
        store = TaskStore(redis_client, db)
        service = TaskService(store)

        task_id = await service.submit_task(
            user_id=user_id,
            task_type="deep_research",
            payload={
                "workspace_id": workspace_id,
                "query": query,
                "context": {
                    "search_limit": 20,
                    "year_range": "2022-2024"
                }
            },
            priority=5,
        )
        return task_id

# 前端监听进度
# GET /api/tasks/{task_id}/stream
```

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2024-03 | 初始版本 - 核心 Task 系统实现 |

---

## 相关文档

- [Celery 官方文档](https://docs.celeryq.dev/)
- [Redis Pub/Sub](https://redis.io/docs/manual/pubsub/)
- [Server-Sent Events (SSE)](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
