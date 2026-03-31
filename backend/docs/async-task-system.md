# Async Task System

> 异步任务系统 - 基于 Celery + Redis + PostgreSQL 的分布式任务处理框架

## 概述

Async Task System 是 Wenjin 的核心基础设施，用于处理长时间运行的学术研究任务。系统支持任务提交、进度追踪、实时流式更新和任务取消等功能。

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
│                      Task Handlers (Canonical)                            │
│  ┌──────────────────────┐   ┌──────────────────────┐                     │
│  │  workspace_feature   │   │   paper_extraction   │                     │
│  │  workspace 功能执行   │   │   论文提取内部分发    │                     │
│  └──────────────────────┘   └──────────────────────┘                     │
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
    "paper_extraction": TaskTypeConfig(
        queue=TaskQueue.DEFAULT,
        timeout=300,
        retry=1,
        description="论文提取: 从 papers API 提交的内部异步任务",
    ),
    "workspace_feature": TaskTypeConfig(
        queue=TaskQueue.DEFAULT,
        timeout=300,
        retry=1,
        description="workspace 通用功能桥接任务",
    ),
}
```

---

## API 接口

### 创建任务的公共入口

`POST /api/tasks` 已删除。公共任务创建统一走 domain 入口，再由应用层转成内部任务。

**workspace feature 执行**

```http
POST /api/workspaces/{workspace_id}/features/{feature_id}/execute
Content-Type: application/json

{
    "params": {
        "query": "machine learning in healthcare"
    }
}
```

**论文提取**

```http
POST /api/papers/{paper_id}/extract?workspace_id={workspace_id}&tier=1
```

**典型响应**

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
    "task_type": "workspace_feature",
    "status": "running",
    "progress": 45,
    "message": "Running feature pipeline...",
    "result": null,
    "error": null,
    "created_at": "2024-01-15T10:30:00+00:00",
    "started_at": "2024-01-15T10:30:01+00:00",
    "completed_at": null
}
```

### 列出任务

```http
GET /api/tasks/?status=running&task_type=workspace_feature&limit=20
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

### 方式一: 通过公共 domain 入口发起任务

公开 API 只负责启动业务场景，不暴露原始 task submission。

```http
POST /api/workspaces/{workspace_id}/features/{feature_id}/execute
POST /api/papers/{paper_id}/extract?workspace_id={workspace_id}&tier=1
```

这两个入口都会返回 `task_id`，随后统一使用 `/api/tasks/{task_id}` 或 `/api/tasks/{task_id}/stream` 观察进度。

### 方式二: 在应用层编排中调用 TaskService

```python
from src.task import TaskService, TaskStore
from src.academic.cache.redis_client import redis_client
from src.database import get_db_session

async def queue_feature(
    user_id: str,
    workspace_id: str,
    workspace_type: str,
    feature_id: str,
    params: dict,
) -> str:
    async with get_db_session() as db:
        store = TaskStore(redis_client, db)
        service = TaskService(store)

        task_id = await service.submit_task(
            user_id=user_id,
            task_type="workspace_feature",
            payload={
                "workspace_id": workspace_id,
                "workspace_type": workspace_type,
                "feature_id": feature_id,
                "params": params,
            },
            priority=5,
        )
        return task_id
```

### 方式三: 提交论文提取内部任务

```python
async def queue_paper_extraction(
    user_id: str,
    workspace_id: str,
    paper_id: str,
    tier: int,
) -> str:
    async with get_db_session() as db:
        store = TaskStore(redis_client, db)
        service = TaskService(store)

        task_id = await service.submit_task(
            user_id=user_id,
            task_type="paper_extraction",
            payload={
                "workspace_id": workspace_id,
                "paper_id": paper_id,
                "tier": tier,
            },
        )
        return task_id
```

---

## 前端集成

### JavaScript/TypeScript 示例

```typescript
async function executeFeature(
  workspaceId: string,
  featureId: string,
  params: Record<string, unknown>,
): Promise<string> {
  const response = await fetch(
    `/api/workspaces/${workspaceId}/features/${featureId}/execute`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ params }),
    },
  );
  const { task_id } = await response.json();
  return task_id;
}

function streamProgress(taskId: string, onUpdate: (data: any) => void) {
  const eventSource = new EventSource(`/api/tasks/${taskId}/stream`);

  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    onUpdate(data);

    if (["success", "failed", "cancelled"].includes(data.status)) {
      eventSource.close();
    }
  };

  eventSource.onerror = () => {
    eventSource.close();
  };

  return () => eventSource.close();
}

const taskId = await executeFeature("ws-1", "deep_research", {
  query: "AI in medicine",
});
const cleanup = streamProgress(taskId, (data) => {
  console.log(`Progress: ${data.progress}% - ${data.message}`);
  if (data.status === "success") {
    console.log("Result:", data.result);
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
      - DATABASE_URL=postgresql://user:pass@postgres:5432/wenjin
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

## Workspace Feature 集成指南

### canonical 对接机制

Async Task System 当前只保留两类内部任务：

```
workspace_feature  → workspace_features.registry + workspace_feature_handler
paper_extraction   → papers handler + paper_extraction_handler
```

`workspace_feature` 内部再根据 `feature_id` 路由到具体 graph、tool 或 artifact 产物链路，而不是为每个功能暴露一个独立 raw task type。

### 对接流程

```text
1. 用户调用公共 API
   POST /api/workspaces/{workspace_id}/features/{feature_id}/execute
   POST /api/papers/{paper_id}/extract

2. Application Handler
   • 权限校验
   • 幂等/去重
   • 额度/配额处理
   • submit_task()

3. TaskService
   • 创建 DB 记录
   • 发送到 executor

4. Worker
   • execute_task()
   • _dispatch_task()
   • 进入 workspace_feature_handler 或 paper_extraction_handler
```

### 新增 workspace feature 的做法

1. 在 `src/workspace_features/registry.py` 注册 `feature_id` 与 handler 元数据。
2. 在对应 workspace feature service 或 graph 中实现具体业务。
3. 复用 `FeatureExecutionHandler` 提交 `workspace_feature` 任务，不新增 raw task route。
4. 如需前端显示结果，输出 canonical artifact，并通过 `/api/tasks/{task_id}` / SSE 暴露进度。

### 设计约束

- 不再新增 `POST /api/tasks` 这类公共原始提交入口。
- 不再为单个 feature 扩散新的 public raw task type。
- 可从 DB 重新获取的事实，尽量不要重复写进任务 payload。
- 任务结果结构应统一，便于 chat 卡片、workspace 活动流和 artifact 面板复用。

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
