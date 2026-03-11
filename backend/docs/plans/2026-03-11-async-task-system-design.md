# Async Task System Design

> **Status:** Approved
> **Date:** 2026-03-11

## Overview

通用异步任务系统，支持长时间运行的任务（论文生成、Deep Research、文献检索等），提供实时进度追踪和状态管理。

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Client    │────▶│  FastAPI     │────▶│   Celery     │
│  (Frontend) │     │  Gateway     │     │   Worker     │
└─────────────┘     └──────────────┘     └─────────────┘
       │                   │                    │
       │ SSE               │ Redis Broker        │
       ▼                   ▼                    ▼
┌─────────────────────────────────────────────────────┐
│                    Redis                              │
│  - Task Queue (celery)                               │
│  - Task Status (hash)                                │
│  - Progress Updates (pub/sub for SSE)                │
└─────────────────────────────────────────────────────┘
                            │
                            ▼
                   ┌─────────────┐
                   │ PostgreSQL  │
                   │ (History)   │
                   └─────────────┘
```

## Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Task Queue | Celery | 成熟稳定，支持分布式，未来可扩展到 RabbitMQ |
| Broker | Redis (existing) | 无需新依赖，初期够用 |
| Progress Push | SSE | 复用现有基础设施，单向推送足够 |
| Runtime State | Redis | 快速读写，支持 pub/sub |
| Persistent Storage | PostgreSQL | 历史查询、统计分析 |

## Core Components

### 1. TaskService
- 任务创建、查询、取消
- 输入验证、权限检查
- 任务类型路由

### 2. ProgressTracker
- 进度更新（0-100）
- 消息推送
- SSE 事件发布

### 3. TaskStore
- Redis 运行时状态
- PostgreSQL 持久化
- 状态迁移（完成后 Redis → PG）

### 4. Celery App
- Worker 配置
- 任务注册
- 重试策略

## API Design

### Endpoints

```python
# 任务提交
POST /api/tasks/
Request:
{
    "task_type": "thesis_generation",  # deep_research, literature_search, etc.
    "priority": 5,  # 1-10, default 5
    "payload": {
        "workspace_id": "xxx",
        "config": {...}
    }
}
Response:
{
    "task_id": "xxx",
    "status": "pending"
}

# 任务状态查询
GET /api/tasks/{task_id}
Response:
{
    "task_id": "xxx",
    "status": "running",
    "progress": 45,
    "message": "正在生成第3章...",
    "created_at": "2024-...",
    "started_at": "2024-..."
}

# 实时进度流 (SSE)
GET /api/tasks/{task_id}/stream
Event Format:
{
    "task_id": "xxx",
    "status": "running",
    "progress": 45,
    "message": "正在生成第3章...",
    "timestamp": "2024-..."
}

# 任务列表
GET /api/tasks/?status=running&task_type=thesis
Response:
{
    "tasks": [...],
    "count": 5
}

# 取消任务
DELETE /api/tasks/{task_id}
Response:
{
    "success": true,
    "task_id": "xxx"
}
```

## Data Models

### PostgreSQL: TaskRecord

```python
class TaskRecord(Base):
    __tablename__ = "task_records"

    id: UUID = Column(primary_key=True)
    user_id: str = Column(String(36), index=True)
    task_type: str = Column(String(50), index=True)
    status: str = Column(String(20))  # pending, running, success, failed, cancelled
    priority: int = Column(Integer, default=5)

    # Request/Response
    payload: dict = Column(JSON)
    result: dict | None = Column(JSON)
    error: str | None = Column(Text)

    # Progress
    progress: int = Column(Integer, default=0)  # 0-100
    message: str | None = Column(Text)

    # Timestamps
    created_at: datetime = Column(DateTime)
    started_at: datetime | None = Column(DateTime)
    completed_at: datetime | None = Column(DateTime)
```

### Redis: Runtime State

```
Key: task:{task_id}
Type: Hash
TTL: 24 hours

{
    "status": "running",
    "progress": 45,
    "message": "正在生成第3章...",
    "current_step": "section_3",
    "worker_id": "celery@worker1",
    "updated_at": "2024-..."
}
```

### Redis: Progress Channel (Pub/Sub)

```
Channel: task_progress:{task_id}

Message:
{
    "task_id": "xxx",
    "progress": 50,
    "message": "正在生成第4章...",
    "timestamp": "2024-..."
}
```

## Task Type Registry

```python
TASK_REGISTRY = {
    "deep_research": {
        "queue": "default",
        "timeout": 600,  # 10 minutes
        "retry": 2,
        "description": "深度研究：文献检索、分析、总结",
    },
    "thesis_generation": {
        "queue": "long_running",
        "timeout": 3600,  # 1 hour
        "retry": 1,
        "description": "论文生成：完整学术论文写作",
    },
    "literature_search": {
        "queue": "default",
        "timeout": 300,  # 5 minutes
        "retry": 3,
        "description": "文献检索：Semantic Scholar, arXiv 搜索",
    },
    "paper_processing": {
        "queue": "default",
        "timeout": 120,
        "retry": 2,
        "description": "论文处理：PDF 解析、元数据提取",
    },
}
```

## Task Lifecycle

```
                    ┌──────────┐
                    │ PENDING  │
                    └────┬─────┘
                         │ Worker picks up
                         ▼
                    ┌──────────┐
         ┌─────────▶│ RUNNING  │◀─────────┐
         │          └────┬─────┘          │
         │               │                │
    Retry on failure    │ Success    Progress updates
         │               │                │
         │               ▼                │
         │          ┌──────────┐          │
         └──────────│  FAILED  │          │
                    └──────────┘          │
                                          │
                    ┌──────────┐          │
                    │ SUCCESS  │◀─────────┘
                    └──────────┘

                    ┌──────────┐
                    │CANCELLED │ (user request)
                    └──────────┘
```

## Error Handling

### Retry Strategy
- Exponential backoff: 2^retry_count seconds
- Max retries defined per task type
- Dead letter queue for failed tasks

### Error Categories
```python
class TaskError(Exception):
    """Base task error"""

class TaskTimeoutError(TaskError):
    """Task exceeded timeout"""

class TaskCancelledError(TaskError):
    """Task was cancelled by user"""

class TaskDependencyError(TaskError):
    """Required dependency not available"""
```

## Integration Points

### With Thesis Module (另一个进程)
```python
# Thesis module 注册任务类型
TASK_REGISTRY["thesis_generation"] = {...}

# Thesis module 实现任务
@celery_app.task(bind=True)
def thesis_generation_task(self, task_id: str, payload: dict):
    # 更新进度
    update_progress(task_id, 10, "正在分析研究主题...")
    # ... 执行任务
    update_progress(task_id, 100, "论文生成完成")
```

### With Deep Research Skill
```python
@celery_app.task(bind=True)
def deep_research_task(self, task_id: str, payload: dict):
    workspace_id = payload["workspace_id"]
    query = payload["query"]

    update_progress(task_id, 10, "正在检索文献...")
    papers = search_papers(query)

    update_progress(task_id, 40, f"找到 {len(papers)} 篇文献，正在分析...")
    analysis = analyze_papers(papers)

    update_progress(task_id, 100, "研究完成")
    return {"analysis": analysis}
```

## Configuration

```python
# src/config/task_config.py

class TaskSettings(BaseSettings):
    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Worker
    worker_concurrency: int = 4
    worker_prefetch_multiplier: int = 2

    # Task defaults
    task_soft_time_limit: int = 600  # 10 minutes
    task_time_limit: int = 900  # 15 minutes
    task_acks_late: bool = True

    # Progress
    progress_update_interval: int = 2  # seconds

    # Storage
    task_redis_ttl: int = 86400  # 24 hours
```

## Security Considerations

1. **User Isolation**: Users can only view/cancel their own tasks
2. **Rate Limiting**: Max concurrent tasks per user
3. **Payload Validation**: Strict schema validation for task payloads
4. **Priority Limits**: Non-admin users max priority = 7

## Monitoring & Observability

1. **Task Metrics**:
   - Tasks submitted/running/completed/failed
   - Average task duration by type
   - Queue length

2. **Health Checks**:
   - Worker heartbeat
   - Queue backlog
   - Redis connectivity

## Migration Path (Redis Broker → RabbitMQ)

When needed, migration is straightforward:
```python
# Just change broker URL
CELERY_BROKER_URL = "amqp://user:pass@rabbitmq:5672//"
# No code changes required
```

## Future Extensions

1. **Task Scheduling**: `apply_async(..., countdown=60)` or `eta`
2. **Task Chaining**: `chain(task1.s(), task2.s())`
3. **Task Groups**: `group(task.s(i) for i in range(10))`
4. **Task Priority Queues**: Worker priority routing

---

## Implementation Phases

### Phase 1: Core Infrastructure (本 Phase)
- Celery app configuration
- TaskRecord model + migration
- TaskService + TaskStore
- Basic API endpoints

### Phase 2: Progress & SSE
- ProgressTracker
- SSE streaming endpoint
- Redis pub/sub integration

### Phase 3: Integration
- Integrate with Deep Research skill
- Integrate with Thesis module (协调另一个进程)
- Task cancellation support

### Phase 4: Production Ready
- Worker deployment config
- Monitoring endpoints
- Error handling refinement
