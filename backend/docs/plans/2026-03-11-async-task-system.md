# Async Task System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a general-purpose async task system using Celery + Redis for long-running tasks (thesis generation, deep research, literature search).

**Architecture:** Celery workers consume tasks from Redis queue. Task status stored in Redis (runtime) and PostgreSQL (history). SSE streams progress updates to clients via Redis pub/sub.

**Tech Stack:** Celery, Redis (existing), PostgreSQL, FastAPI, SSE

---

## Phase 1: Core Infrastructure

### Task 1: Add Celery Dependencies

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add celery and flower to dependencies**

```toml
# Add to dependencies array in pyproject.toml
"celery[redis]>=5.4.0",
"flower>=2.0.0",  # Celery monitoring UI
```

**Step 2: Install dependencies**

Run: `pip install celery[redis] flower`

**Step 3: Verify installation**

Run: `python -c "import celery; print(celery.__version__)"`

Expected: `5.4.0` or higher

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add celery and flower dependencies"
```

---

### Task 2: Create Task Configuration

**Files:**
- Create: `src/config/task_config.py`

**Step 1: Write the configuration module**

```python
"""Task system configuration."""

from pydantic_settings import BaseSettings


class TaskSettings(BaseSettings):
    """Celery and task system settings."""

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

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

    # Rate limits
    max_concurrent_tasks_per_user: int = 3
    max_priority_for_non_admin: int = 7

    class Config:
        env_prefix = "TASK_"


# Global instance
task_settings = TaskSettings()
```

**Step 2: Verify import**

Run: `python -c "from src.config.task_config import task_settings; print(task_settings.celery_broker_url)"`

Expected: `redis://localhost:6379/1`

**Step 3: Commit**

```bash
git add src/config/task_config.py
git commit -m "feat(task): add task system configuration"
```

---

### Task 3: Create Celery App

**Files:**
- Create: `src/task/celery_app.py`
- Create: `src/task/__init__.py`

**Step 1: Create task module init**

```python
"""Async task system package."""

from src.task.celery_app import celery_app

__all__ = ["celery_app"]
```

**Step 2: Write the Celery app configuration**

```python
"""Celery application configuration."""

from celery import Celery

from src.config.task_config import task_settings

# Create Celery app
celery_app = Celery(
    "academiagpt",
    broker=task_settings.celery_broker_url,
    backend=task_settings.celery_result_backend,
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Worker settings
    worker_concurrency=task_settings.worker_concurrency,
    worker_prefetch_multiplier=task_settings.worker_prefetch_multiplier,

    # Task execution
    task_acks_late=task_settings.task_acks_late,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=task_settings.task_soft_time_limit,
    task_time_limit=task_settings.task_time_limit,

    # Result settings
    result_expires=task_settings.task_redis_ttl,

    # Task routing (will be populated by task registry)
    task_routes={},

    # Default queue
    task_default_queue="default",
    task_default_exchange="tasks",
    task_default_routing_key="task.default",
)

# Auto-discover tasks from registered modules
celery_app.autodiscover_tasks([
    "src.task.tasks",
])
```

**Step 3: Verify Celery app loads**

Run: `python -c "from src.task import celery_app; print(celery_app.main)"`

Expected: `academiagpt`

**Step 4: Commit**

```bash
git add src/task/__init__.py src/task/celery_app.py
git commit -m "feat(task): create celery app configuration"
```

---

### Task 4: Create TaskRecord Model

**Files:**
- Create: `src/database/models/task.py`
- Modify: `src/database/models/__init__.py`

**Step 1: Write the TaskRecord model**

```python
"""Task record model for persistent storage."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database.models.base import Base


class TaskRecord(Base):
    """Persistent record of task execution."""

    __tablename__ = "task_records"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    # Request
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Response
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Progress tracking
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_task_records_user_status", "user_id", "status"),
        Index("ix_task_records_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<TaskRecord {self.id[:8]} type={self.task_type} status={self.status}>"
```

**Step 2: Export from models init**

Add to `src/database/models/__init__.py`:

```python
from src.database.models.task import TaskRecord

__all__ = [
    # ... existing exports
    "TaskRecord",
]
```

**Step 3: Verify model imports**

Run: `python -c "from src.database.models import TaskRecord; print(TaskRecord.__tablename__)"`

Expected: `task_records`

**Step 4: Commit**

```bash
git add src/database/models/task.py src/database/models/__init__.py
git commit -m "feat(task): add TaskRecord model"
```

---

### Task 5: Create Database Migration

**Files:**
- Create: migration file (via alembic)

**Step 1: Create migration**

Run: `alembic revision --autogenerate -m "add task_records table"`

**Step 2: Review generated migration**

Run: `cat alembic/versions/*task_records*.py | head -50`

**Step 3: Apply migration**

Run: `alembic upgrade head`

**Step 4: Verify table exists**

Run: `python -c "import asyncio; from src.database import get_db_session; from sqlalchemy import text; async def check(): async with get_db_session() as db: result = await db.execute(text('SELECT * FROM task_records LIMIT 1')); print('OK'); asyncio.run(check())"`

Expected: `OK`

**Step 5: Commit**

```bash
git add alembic/versions/*task_records*.py
git commit -m "db: add task_records migration"
```

---

### Task 6: Create Task Type Registry

**Files:**
- Create: `src/task/registry.py`

**Step 1: Write the task registry**

```python
"""Task type registry for configuration and validation."""

from dataclasses import dataclass
from enum import Enum


class TaskQueue(str, Enum):
    """Available task queues."""
    DEFAULT = "default"
    LONG_RUNNING = "long_running"
    PRIORITY = "priority"


@dataclass
class TaskTypeConfig:
    """Configuration for a task type."""
    queue: str = TaskQueue.DEFAULT
    timeout: int = 600  # seconds
    retry: int = 2
    retry_delay: int = 60  # seconds
    description: str = ""


# Task type registry
TASK_REGISTRY: dict[str, TaskTypeConfig] = {
    "deep_research": TaskTypeConfig(
        queue=TaskQueue.DEFAULT,
        timeout=600,
        retry=2,
        description="Deep research: literature search, analysis, and summary",
    ),
    "thesis_generation": TaskTypeConfig(
        queue=TaskQueue.LONG_RUNNING,
        timeout=3600,
        retry=1,
        description="Thesis generation: full academic paper writing",
    ),
    "literature_search": TaskTypeConfig(
        queue=TaskQueue.DEFAULT,
        timeout=300,
        retry=3,
        description="Literature search: Semantic Scholar, arXiv search",
    ),
    "paper_processing": TaskTypeConfig(
        queue=TaskQueue.DEFAULT,
        timeout=120,
        retry=2,
        description="Paper processing: PDF parsing, metadata extraction",
    ),
}


def get_task_config(task_type: str) -> TaskTypeConfig | None:
    """Get configuration for a task type."""
    return TASK_REGISTRY.get(task_type)


def is_valid_task_type(task_type: str) -> bool:
    """Check if task type is registered."""
    return task_type in TASK_REGISTRY


def get_registered_task_types() -> list[str]:
    """Get all registered task types."""
    return list(TASK_REGISTRY.keys())
```

**Step 2: Verify registry**

Run: `python -c "from src.task.registry import TASK_REGISTRY; print(list(TASK_REGISTRY.keys()))"`

Expected: `['deep_research', 'thesis_generation', 'literature_search', 'paper_processing']`

**Step 3: Commit**

```bash
git add src/task/registry.py
git commit -m "feat(task): add task type registry"
```

---

### Task 7: Create TaskStore (Redis + PostgreSQL)

**Files:**
- Create: `src/task/store.py`

**Step 1: Write the TaskStore class**

```python
"""Task storage layer - Redis for runtime, PostgreSQL for persistence."""

import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.task_config import task_settings
from src.database.models.task import TaskRecord

logger = logging.getLogger(__name__)


class TaskStore:
    """Manages task state in Redis and PostgreSQL."""

    def __init__(self, redis_client, db_session: AsyncSession):
        self._redis = redis_client
        self._db = db_session

    # === Redis Operations (Runtime State) ===

    def _task_key(self, task_id: str) -> str:
        """Redis key for task state."""
        return f"task:{task_id}"

    async def set_task_state(
        self,
        task_id: str,
        status: str,
        progress: int = 0,
        message: str | None = None,
        current_step: str | None = None,
        worker_id: str | None = None,
    ) -> None:
        """Set task state in Redis."""
        key = self._task_key(task_id)
        data = {
            "status": status,
            "progress": progress,
            "message": message or "",
            "current_step": current_step or "",
            "worker_id": worker_id or "",
            "updated_at": datetime.utcnow().isoformat(),
        }
        await self._redis.client.hset(key, mapping={k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in data.items()})
        await self._redis.client.expire(key, task_settings.task_redis_ttl)

    async def get_task_state(self, task_id: str) -> dict | None:
        """Get task state from Redis."""
        key = self._task_key(task_id)
        data = await self._redis.client.hgetall(key)
        if not data:
            return None
        return {
            "status": data.get("status", "unknown"),
            "progress": int(data.get("progress", 0)),
            "message": data.get("message", ""),
            "current_step": data.get("current_step", ""),
            "worker_id": data.get("worker_id", ""),
            "updated_at": data.get("updated_at", ""),
        }

    async def delete_task_state(self, task_id: str) -> None:
        """Delete task state from Redis."""
        key = self._task_key(task_id)
        await self._redis.client.delete(key)

    # === PostgreSQL Operations (Persistence) ===

    async def create_task_record(
        self,
        task_id: str,
        user_id: str,
        task_type: str,
        priority: int,
        payload: dict,
    ) -> TaskRecord:
        """Create a new task record in PostgreSQL."""
        record = TaskRecord(
            id=task_id,
            user_id=user_id,
            task_type=task_type,
            status="pending",
            priority=priority,
            payload=payload,
        )
        self._db.add(record)
        await self._db.commit()
        await self._db.refresh(record)
        return record

    async def get_task_record(self, task_id: str) -> TaskRecord | None:
        """Get task record from PostgreSQL."""
        result = await self._db.execute(
            select(TaskRecord).where(TaskRecord.id == task_id)
        )
        return result.scalar_one_or_none()

    async def update_task_record(
        self,
        task_id: str,
        **updates,
    ) -> TaskRecord | None:
        """Update task record in PostgreSQL."""
        record = await self.get_task_record(task_id)
        if not record:
            return None

        for key, value in updates.items():
            if hasattr(record, key):
                setattr(record, key, value)

        await self._db.commit()
        await self._db.refresh(record)
        return record

    async def list_user_tasks(
        self,
        user_id: str,
        status: str | None = None,
        task_type: str | None = None,
        limit: int = 20,
    ) -> list[TaskRecord]:
        """List tasks for a user."""
        query = select(TaskRecord).where(TaskRecord.user_id == user_id)

        if status:
            query = query.where(TaskRecord.status == status)
        if task_type:
            query = query.where(TaskRecord.task_type == task_type)

        query = query.order_by(TaskRecord.created_at.desc()).limit(limit)
        result = await self._db.execute(query)
        return list(result.scalars().all())

    async def mark_task_started(self, task_id: str, worker_id: str | None = None) -> None:
        """Mark task as started."""
        await self.update_task_record(
            task_id,
            status="running",
            started_at=datetime.utcnow(),
        )
        await self.set_task_state(task_id, "running", worker_id=worker_id)

    async def mark_task_completed(
        self,
        task_id: str,
        success: bool,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        """Mark task as completed (success or failed)."""
        status = "success" if success else "failed"
        await self.update_task_record(
            task_id,
            status=status,
            result=result,
            error=error,
            completed_at=datetime.utcnow(),
            progress=100 if success else None,
        )
        # Keep Redis state for a while for queries, then cleanup
        await self.set_task_state(task_id, status, progress=100 if success else 0, message=error)
```

**Step 2: Verify import**

Run: `python -c "from src.task.store import TaskStore; print('OK')"`

Expected: `OK`

**Step 3: Commit**

```bash
git add src/task/store.py
git commit -m "feat(task): add TaskStore for Redis and PostgreSQL"
```

---

### Task 8: Create TaskService

**Files:**
- Create: `src/task/service.py`

**Step 1: Write the TaskService class**

```python
"""Task service for task management operations."""

import logging
from uuid import uuid4

from celery.result import AsyncResult

from src.config.task_config import task_settings
from src.task import celery_app
from src.task.registry import get_task_config, is_valid_task_type
from src.task.store import TaskStore

logger = logging.getLogger(__name__)


class TaskService:
    """Service for task management."""

    def __init__(self, store: TaskStore):
        self._store = store

    async def submit_task(
        self,
        user_id: str,
        task_type: str,
        payload: dict,
        priority: int = 5,
    ) -> str:
        """Submit a new task.

        Args:
            user_id: User submitting the task
            task_type: Type of task (must be registered)
            payload: Task-specific parameters
            priority: Task priority (1-10, lower = higher priority)

        Returns:
            Task ID

        Raises:
            ValueError: If task_type is invalid
        """
        if not is_valid_task_type(task_type):
            raise ValueError(f"Unknown task type: {task_type}")

        # Validate priority
        priority = max(1, min(10, priority))

        # Generate task ID
        task_id = str(uuid4())

        # Create database record
        await self._store.create_task_record(
            task_id=task_id,
            user_id=user_id,
            task_type=task_type,
            priority=priority,
            payload=payload,
        )

        # Get task config
        config = get_task_config(task_type)

        # Submit to Celery
        # Note: Actual task function will be implemented in Phase 3
        # For now, we use a placeholder task
        celery_app.send_task(
            "src.task.tasks.execute_task",
            args=[task_id, task_type, payload],
            queue=config.queue if config else "default",
            priority=10 - priority,  # Celery uses inverse priority
            task_id=task_id,
        )

        logger.info(f"Task submitted: {task_id} type={task_type} user={user_id}")

        return task_id

    async def get_task_status(self, task_id: str, user_id: str) -> dict | None:
        """Get task status.

        Args:
            task_id: Task ID
            user_id: User ID (for access control)

        Returns:
            Task status dict or None if not found/not authorized
        """
        # Check database record
        record = await self._store.get_task_record(task_id)
        if not record:
            return None

        # Access control
        if record.user_id != user_id:
            return None

        # Get runtime state from Redis for running tasks
        if record.status in ("pending", "running"):
            runtime_state = await self._store.get_task_state(task_id)
            if runtime_state:
                return {
                    "task_id": task_id,
                    "task_type": record.task_type,
                    "status": runtime_state.get("status", record.status),
                    "progress": runtime_state.get("progress", 0),
                    "message": runtime_state.get("message", ""),
                    "created_at": record.created_at.isoformat(),
                    "started_at": record.started_at.isoformat() if record.started_at else None,
                }

        return {
            "task_id": task_id,
            "task_type": record.task_type,
            "status": record.status,
            "progress": record.progress,
            "message": record.message,
            "result": record.result,
            "error": record.error,
            "created_at": record.created_at.isoformat(),
            "started_at": record.started_at.isoformat() if record.started_at else None,
            "completed_at": record.completed_at.isoformat() if record.completed_at else None,
        }

    async def list_tasks(
        self,
        user_id: str,
        status: str | None = None,
        task_type: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """List tasks for a user."""
        records = await self._store.list_user_tasks(
            user_id=user_id,
            status=status,
            task_type=task_type,
            limit=limit,
        )
        return [
            {
                "task_id": r.id,
                "task_type": r.task_type,
                "status": r.status,
                "progress": r.progress,
                "message": r.message,
                "created_at": r.created_at.isoformat(),
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in records
        ]

    async def cancel_task(self, task_id: str, user_id: str) -> bool:
        """Cancel a task.

        Args:
            task_id: Task ID
            user_id: User ID (for access control)

        Returns:
            True if cancelled, False if not found/not authorized
        """
        record = await self._store.get_task_record(task_id)
        if not record or record.user_id != user_id:
            return False

        # Can only cancel pending or running tasks
        if record.status not in ("pending", "running"):
            return False

        # Revoke Celery task
        celery_app.control.revoke(task_id, terminate=True)

        # Update database
        await self._store.update_task_record(
            task_id,
            status="cancelled",
            completed_at=__import__('datetime').datetime.utcnow(),
        )
        await self._store.set_task_state(task_id, "cancelled", message="Cancelled by user")

        logger.info(f"Task cancelled: {task_id}")

        return True
```

**Step 2: Verify import**

Run: `python -c "from src.task.service import TaskService; print('OK')"`

Expected: `OK`

**Step 3: Commit**

```bash
git add src/task/service.py
git commit -m "feat(task): add TaskService for task management"
```

---

### Task 9: Create Task API Router

**Files:**
- Create: `src/gateway/routers/tasks.py`
- Modify: `src/gateway/app.py`

**Step 1: Write the tasks router**

```python
"""Task API router."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.task.service import TaskService
from src.task.store import TaskStore

router = APIRouter(prefix="/tasks", tags=["tasks"])


# === Request/Response Models ===

class TaskSubmitRequest(BaseModel):
    """Task submission request."""
    task_type: str = Field(..., description="Type of task to execute")
    priority: int = Field(5, ge=1, le=10, description="Task priority (1-10)")
    payload: dict = Field(..., description="Task-specific parameters")


class TaskSubmitResponse(BaseModel):
    """Task submission response."""
    task_id: str
    status: str = "pending"


class TaskStatusResponse(BaseModel):
    """Task status response."""
    task_id: str
    task_type: str
    status: str
    progress: int
    message: str | None
    result: dict | None = None
    error: str | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


class TaskListResponse(BaseModel):
    """Task list response."""
    tasks: list[TaskStatusResponse]
    count: int


# === Dependencies ===

async def get_current_user_id() -> str:
    """Get current user ID from request context."""
    # TODO: Replace with actual auth when available
    return "default-user"


async def get_task_service() -> TaskService:
    """Get TaskService instance."""
    from src.academic.cache.redis_client import redis_client
    from src.database import get_db_session

    async with get_db_session() as db:
        store = TaskStore(redis_client, db)
        yield TaskService(store)


# === Endpoints ===

@router.post("/", response_model=TaskSubmitResponse, status_code=201)
async def submit_task(
    request: TaskSubmitRequest,
    user_id: str = Depends(get_current_user_id),
    task_service: TaskService = Depends(get_task_service),
):
    """Submit a new async task."""
    try:
        task_id = await task_service.submit_task(
            user_id=user_id,
            task_type=request.task_type,
            payload=request.payload,
            priority=request.priority,
        )
        return TaskSubmitResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    task_service: TaskService = Depends(get_task_service),
):
    """Get task status."""
    status = await task_service.get_task_status(task_id, user_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatusResponse(**status)


@router.get("/{task_id}/stream")
async def stream_task_progress(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    task_service: TaskService = Depends(get_task_service),
):
    """Stream task progress via SSE."""
    # Verify access
    status = await task_service.get_task_status(task_id, user_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")

    from src.task.sse import create_task_sse_stream
    return StreamingResponse(
        create_task_sse_stream(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/", response_model=TaskListResponse)
async def list_tasks(
    status: str | None = Query(None, description="Filter by status"),
    task_type: str | None = Query(None, description="Filter by task type"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    user_id: str = Depends(get_current_user_id),
    task_service: TaskService = Depends(get_task_service),
):
    """List tasks for current user."""
    tasks = await task_service.list_tasks(
        user_id=user_id,
        status=status,
        task_type=task_type,
        limit=limit,
    )
    return TaskListResponse(
        tasks=[TaskStatusResponse(**t) for t in tasks],
        count=len(tasks),
    )


@router.delete("/{task_id}")
async def cancel_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    task_service: TaskService = Depends(get_task_service),
):
    """Cancel a task."""
    success = await task_service.cancel_task(task_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found or cannot be cancelled")
    return {"success": True, "task_id": task_id}
```

**Step 2: Register router in app.py**

Add to `src/gateway/app.py` after other router imports:

```python
from .routers import academic, artifacts, auth, chat, models, papers, tasks, workspaces  # noqa: E402

# ... existing routers ...

app.include_router(tasks.router, prefix="/api", tags=["tasks"])
```

**Step 3: Verify router loads**

Run: `python -c "from src.gateway.routers import tasks; print(len(tasks.router.routes))"`

Expected: `5`

**Step 4: Commit**

```bash
git add src/gateway/routers/tasks.py src/gateway/app.py
git commit -m "feat(task): add task API router"
```

---

## Phase 2: Progress & SSE

### Task 10: Create Progress Tracker

**Files:**
- Create: `src/task/progress.py`

**Step 1: Write the ProgressTracker class**

```python
"""Progress tracking for tasks."""

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ProgressTracker:
    """Tracks and broadcasts task progress."""

    def __init__(self, redis_client, task_id: str):
        self._redis = redis_client
        self._task_id = task_id

    def _channel_name(self) -> str:
        """Redis pub/sub channel for this task."""
        return f"task_progress:{self._task_id}"

    async def update(
        self,
        progress: int,
        message: str | None = None,
        current_step: str | None = None,
    ) -> None:
        """Update progress and broadcast to subscribers.

        Args:
            progress: Progress percentage (0-100)
            message: Human-readable status message
            current_step: Identifier for current step
        """
        progress = max(0, min(100, progress))

        # Update Redis state
        from src.task.store import TaskStore
        from src.database import get_db_session
        from src.academic.cache.redis_client import redis_client

        async with get_db_session() as db:
            store = TaskStore(redis_client, db)
            await store.set_task_state(
                self._task_id,
                status="running",
                progress=progress,
                message=message,
                current_step=current_step,
            )

        # Broadcast to SSE subscribers
        event_data = json.dumps({
            "task_id": self._task_id,
            "status": "running",
            "progress": progress,
            "message": message,
            "current_step": current_step,
            "timestamp": datetime.utcnow().isoformat(),
        })
        await self._redis.client.publish(self._channel_name(), event_data)

        logger.debug(f"Task {self._task_id}: {progress}% - {message}")

    async def complete(self, message: str = "Task completed") -> None:
        """Mark task as completed."""
        await self.update(100, message)

        # Broadcast completion
        event_data = json.dumps({
            "task_id": self._task_id,
            "status": "success",
            "progress": 100,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        })
        await self._redis.client.publish(self._channel_name(), event_data)

    async def fail(self, error: str) -> None:
        """Mark task as failed."""
        event_data = json.dumps({
            "task_id": self._task_id,
            "status": "failed",
            "progress": 0,
            "message": error,
            "timestamp": datetime.utcnow().isoformat(),
        })
        await self._redis.client.publish(self._channel_name(), event_data)


def get_progress_tracker(task_id: str) -> ProgressTracker:
    """Get a progress tracker for a task."""
    from src.academic.cache.redis_client import redis_client
    return ProgressTracker(redis_client.client, task_id)
```

**Step 2: Verify import**

Run: `python -c "from src.task.progress import ProgressTracker; print('OK')"`

Expected: `OK`

**Step 3: Commit**

```bash
git add src/task/progress.py
git commit -m "feat(task): add ProgressTracker"
```

---

### Task 11: Create SSE Stream

**Files:**
- Create: `src/task/sse.py`

**Step 1: Write the SSE stream generator**

```python
"""Server-Sent Events for task progress."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)


async def create_task_sse_stream(task_id: str) -> AsyncGenerator[str, None]:
    """Create SSE stream for task progress updates.

    Args:
        task_id: Task ID to stream

    Yields:
        SSE formatted strings
    """
    from src.academic.cache.redis_client import redis_client

    channel = f"task_progress:{task_id}"
    pubsub = redis_client.client.pubsub()
    await pubsub.subscribe(channel)

    try:
        # Send initial status
        from src.task.store import TaskStore
        from src.database import get_db_session

        async with get_db_session() as db:
            store = TaskStore(redis_client, db)
            initial_state = await store.get_task_state(task_id)
            if initial_state:
                yield _format_sse_event(initial_state)

        # Listen for updates
        timeout = 3600  # 1 hour max
        last_ping = asyncio.get_event_loop().time()

        async for message in pubsub.listen():
            if message["type"] == "message":
                data = json.loads(message["data"])
                yield _format_sse_event(data)

                # Check if task is done
                if data.get("status") in ("success", "failed", "cancelled"):
                    break

            # Send keepalive ping every 30 seconds
            now = asyncio.get_event_loop().time()
            if now - last_ping > 30:
                yield ": ping\n\n"
                last_ping = now

            # Check timeout
            if now - last_ping > timeout:
                break

    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()


def _format_sse_event(data: dict) -> str:
    """Format data as SSE event."""
    return f"data: {json.dumps(data)}\n\n"
```

**Step 2: Verify import**

Run: `python -c "from src.task.sse import create_task_sse_stream; print('OK')"`

Expected: `OK`

**Step 3: Commit**

```bash
git add src/task/sse.py
git commit -m "feat(task): add SSE stream for progress updates"
```

---

### Task 12: Create Base Task Executor

**Files:**
- Create: `src/task/tasks/__init__.py`
- Create: `src/task/tasks/base.py`

**Step 1: Create tasks module init**

```python
"""Task implementations package."""

from src.task.tasks.base import execute_task

__all__ = ["execute_task"]
```

**Step 2: Write the base task executor**

```python
"""Base task execution function."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="src.task.tasks.execute_task")
def execute_task(self, task_id: str, task_type: str, payload: dict) -> dict:
    """Execute a task based on its type.

    This is the main entry point for all async tasks.
    Task-specific handlers are dispatched based on task_type.

    Args:
        self: Celery task instance
        task_id: Unique task identifier
        task_type: Type of task to execute
        payload: Task-specific parameters

    Returns:
        Task result dict
    """
    import asyncio

    return asyncio.run(_execute_task_async(self, task_id, task_type, payload))


async def _execute_task_async(
    celery_task,
    task_id: str,
    task_type: str,
    payload: dict,
) -> dict:
    """Async task execution logic."""
    from src.academic.cache.redis_client import redis_client
    from src.database import get_db_session
    from src.task.progress import ProgressTracker
    from src.task.store import TaskStore

    # Connect Redis if needed
    if redis_client._client is None:
        await redis_client.connect()

    # Get dependencies
    progress = ProgressTracker(redis_client, task_id)

    async with get_db_session() as db:
        store = TaskStore(redis_client, db)

        try:
            # Mark task as started
            await store.mark_task_started(task_id, worker_id=celery_task.request.hostname)
            await progress.update(0, "Task started")

            # Dispatch to task-specific handler
            result = await _dispatch_task(task_type, payload, progress)

            # Mark as completed
            await store.mark_task_completed(task_id, success=True, result=result)
            await progress.complete("Task completed successfully")

            return result

        except Exception as e:
            logger.exception(f"Task {task_id} failed: {e}")
            await store.mark_task_completed(task_id, success=False, error=str(e))
            await progress.fail(str(e))
            raise


async def _dispatch_task(task_type: str, payload: dict, progress) -> dict:
    """Dispatch task to appropriate handler.

    In Phase 3, this will route to actual skill implementations.
    For now, returns a placeholder result.
    """
    from src.task.registry import is_valid_task_type

    if not is_valid_task_type(task_type):
        raise ValueError(f"Unknown task type: {task_type}")

    # Placeholder implementation - will be replaced in Phase 3
    await progress.update(50, f"Processing {task_type}...")

    # Simulate work (remove in Phase 3)
    import asyncio
    await asyncio.sleep(2)

    return {
        "task_type": task_type,
        "status": "completed",
        "message": "Task executed successfully (placeholder)",
    }
```

**Step 3: Verify task loads**

Run: `python -c "from src.task.tasks import execute_task; print(execute_task.name)"`

Expected: `src.task.tasks.execute_task`

**Step 4: Commit**

```bash
git add src/task/tasks/__init__.py src/task/tasks/base.py
git commit -m "feat(task): add base task executor"
```

---

## Phase 3: Integration Tests

### Task 13: Create Task System Tests

**Files:**
- Create: `tests/task/__init__.py`
- Create: `tests/task/test_service.py`
- Create: `tests/task/test_store.py`

**Step 1: Create test init**

```python
"""Task system tests."""
```

**Step 2: Write store tests**

```python
"""Tests for TaskStore."""

import pytest
import pytest_asyncio

from src.task.store import TaskStore


@pytest_asyncio.fixture
async def task_store(test_session):
    """Create TaskStore instance."""
    from src.academic.cache.redis_client import redis_client
    await redis_client.connect()
    store = TaskStore(redis_client, test_session)
    yield store


class TestTaskStore:
    """Tests for TaskStore."""

    @pytest.mark.asyncio
    async def test_create_task_record(self, task_store):
        """Test creating a task record."""
        record = await task_store.create_task_record(
            task_id="test-task-1",
            user_id="user-1",
            task_type="deep_research",
            priority=5,
            payload={"query": "test"},
        )

        assert record.id == "test-task-1"
        assert record.user_id == "user-1"
        assert record.task_type == "deep_research"
        assert record.status == "pending"

    @pytest.mark.asyncio
    async def test_get_task_record(self, task_store):
        """Test getting a task record."""
        await task_store.create_task_record(
            task_id="test-task-2",
            user_id="user-1",
            task_type="literature_search",
            priority=5,
            payload={},
        )

        record = await task_store.get_task_record("test-task-2")
        assert record is not None
        assert record.task_type == "literature_search"

    @pytest.mark.asyncio
    async def test_update_task_record(self, task_store):
        """Test updating a task record."""
        await task_store.create_task_record(
            task_id="test-task-3",
            user_id="user-1",
            task_type="deep_research",
            priority=5,
            payload={},
        )

        updated = await task_store.update_task_record(
            "test-task-3",
            status="running",
            progress=50,
        )

        assert updated.status == "running"
        assert updated.progress == 50

    @pytest.mark.asyncio
    async def test_list_user_tasks(self, task_store):
        """Test listing user tasks."""
        for i in range(3):
            await task_store.create_task_record(
                task_id=f"test-task-{i+10}",
                user_id="user-list",
                task_type="deep_research",
                priority=5,
                payload={},
            )

        tasks = await task_store.list_user_tasks("user-list")
        assert len(tasks) == 3

    @pytest.mark.asyncio
    async def test_redis_state(self, task_store):
        """Test Redis state operations."""
        await task_store.set_task_state(
            "test-task-redis",
            status="running",
            progress=30,
            message="Processing...",
        )

        state = await task_store.get_task_state("test-task-redis")
        assert state is not None
        assert state["status"] == "running"
        assert state["progress"] == 30
```

**Step 3: Write service tests**

```python
"""Tests for TaskService."""

import pytest
import pytest_asyncio

from src.task.service import TaskService
from src.task.store import TaskStore


@pytest_asyncio.fixture
async def task_service(test_session):
    """Create TaskService instance."""
    from src.academic.cache.redis_client import redis_client
    await redis_client.connect()
    store = TaskStore(redis_client, test_session)
    yield TaskService(store)


class TestTaskService:
    """Tests for TaskService."""

    @pytest.mark.asyncio
    async def test_submit_task(self, task_service):
        """Test submitting a task."""
        task_id = await task_service.submit_task(
            user_id="user-1",
            task_type="deep_research",
            payload={"query": "machine learning"},
            priority=5,
        )

        assert task_id is not None
        assert len(task_id) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_submit_invalid_task_type(self, task_service):
        """Test submitting invalid task type."""
        with pytest.raises(ValueError, match="Unknown task type"):
            await task_service.submit_task(
                user_id="user-1",
                task_type="invalid_type",
                payload={},
            )

    @pytest.mark.asyncio
    async def test_get_task_status(self, task_service):
        """Test getting task status."""
        task_id = await task_service.submit_task(
            user_id="user-1",
            task_type="literature_search",
            payload={"query": "test"},
        )

        status = await task_service.get_task_status(task_id, "user-1")
        assert status is not None
        assert status["task_type"] == "literature_search"
        assert status["status"] == "pending"

    @pytest.mark.asyncio
    async def test_get_task_status_wrong_user(self, task_service):
        """Test getting task status with wrong user."""
        task_id = await task_service.submit_task(
            user_id="user-1",
            task_type="deep_research",
            payload={},
        )

        status = await task_service.get_task_status(task_id, "user-2")
        assert status is None

    @pytest.mark.asyncio
    async def test_list_tasks(self, task_service):
        """Test listing tasks."""
        for i in range(3):
            await task_service.submit_task(
                user_id="user-list",
                task_type="deep_research",
                payload={"index": i},
            )

        tasks = await task_service.list_tasks("user-list")
        assert len(tasks) >= 3

    @pytest.mark.asyncio
    async def test_list_tasks_filter_by_status(self, task_service):
        """Test listing tasks with status filter."""
        task_id = await task_service.submit_task(
            user_id="user-filter",
            task_type="deep_research",
            payload={},
        )

        tasks = await task_service.list_tasks("user-filter", status="pending")
        assert len(tasks) >= 1
```

**Step 4: Run tests**

Run: `python -m pytest tests/task/ -v`

**Step 5: Commit**

```bash
git add tests/task/__init__.py tests/task/test_service.py tests/task/test_store.py
git commit -m "test(task): add task system tests"
```

---

### Task 14: Create Integration Test

**Files:**
- Create: `tests/integration/test_task_flow.py`

**Step 1: Write integration test**

```python
"""Integration tests for task flow."""

import pytest
from httpx import AsyncClient


class TestTaskFlow:
    """Tests for complete task flow."""

    @pytest.mark.asyncio
    async def test_submit_and_get_task(self, authenticated_client: AsyncClient):
        """Test submitting and retrieving a task."""
        # Submit task
        response = await authenticated_client.post(
            "/api/tasks/",
            json={
                "task_type": "deep_research",
                "priority": 5,
                "payload": {"query": "machine learning"},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "task_id" in data
        task_id = data["task_id"]

        # Get status
        response = await authenticated_client.get(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        status = response.json()
        assert status["task_id"] == task_id
        assert status["task_type"] == "deep_research"
        assert status["status"] in ("pending", "running")

    @pytest.mark.asyncio
    async def test_submit_invalid_task_type(self, authenticated_client: AsyncClient):
        """Test submitting invalid task type."""
        response = await authenticated_client.post(
            "/api/tasks/",
            json={
                "task_type": "invalid_type",
                "payload": {},
            },
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_list_tasks(self, authenticated_client: AsyncClient):
        """Test listing tasks."""
        # Submit a task first
        await authenticated_client.post(
            "/api/tasks/",
            json={
                "task_type": "literature_search",
                "payload": {"query": "test"},
            },
        )

        # List tasks
        response = await authenticated_client.get("/api/tasks/")
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        assert "count" in data

    @pytest.mark.asyncio
    async def test_get_nonexistent_task(self, authenticated_client: AsyncClient):
        """Test getting nonexistent task."""
        import uuid
        fake_id = str(uuid.uuid4())
        response = await authenticated_client.get(f"/api/tasks/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_task(self, authenticated_client: AsyncClient):
        """Test cancelling a task."""
        # Submit task
        response = await authenticated_client.post(
            "/api/tasks/",
            json={
                "task_type": "deep_research",
                "payload": {"query": "test"},
            },
        )
        task_id = response.json()["task_id"]

        # Cancel task
        response = await authenticated_client.delete(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify cancelled
        response = await authenticated_client.get(f"/api/tasks/{task_id}")
        status = response.json()
        # Task should be cancelled (if not already running)
        if status["status"] == "cancelled":
            assert True

    @pytest.mark.asyncio
    async def test_task_sse_endpoint_exists(self, authenticated_client: AsyncClient):
        """Test SSE endpoint exists."""
        import uuid
        fake_id = str(uuid.uuid4())
        response = await authenticated_client.get(f"/api/tasks/{fake_id}/stream")
        # Should return 404 for nonexistent task
        assert response.status_code == 404
```

**Step 2: Run integration tests**

Run: `python -m pytest tests/integration/test_task_flow.py -v`

**Step 3: Commit**

```bash
git add tests/integration/test_task_flow.py
git commit -m "test(task): add task flow integration tests"
```

---

## Phase 4: Production Ready

### Task 15: Add Worker Configuration

**Files:**
- Create: `src/task/worker.py`

**Step 1: Write worker configuration**

```python
"""Celery worker configuration and entry point."""

import logging

from src.task.celery_app import celery_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def start_worker(concurrency: int = 4, loglevel: str = "info"):
    """Start a Celery worker.

    Args:
        concurrency: Number of worker processes
        loglevel: Logging level
    """
    logger.info(f"Starting Celery worker with concurrency={concurrency}")

    celery_app.worker_main(
        argv=[
            "worker",
            f"--concurrency={concurrency}",
            f"--loglevel={loglevel}",
            "--without-gossip",
            "--without-mingle",
        ]
    )


if __name__ == "__main__":
    import sys
    concurrency = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    start_worker(concurrency=concurrency)
```

**Step 2: Verify worker script**

Run: `python -c "from src.task.worker import start_worker; print('OK')"`

Expected: `OK`

**Step 3: Commit**

```bash
git add src/task/worker.py
git commit -m "feat(task): add worker entry point"
```

---

### Task 16: Update Module Exports

**Files:**
- Modify: `src/task/__init__.py`

**Step 1: Update exports**

```python
"""Async task system package."""

from src.task.celery_app import celery_app
from src.task.progress import ProgressTracker, get_progress_tracker
from src.task.registry import (
    TASK_REGISTRY,
    TaskQueue,
    TaskTypeConfig,
    get_registered_task_types,
    get_task_config,
    is_valid_task_type,
)
from src.task.service import TaskService
from src.task.store import TaskStore

__all__ = [
    # Celery
    "celery_app",
    # Service
    "TaskService",
    "TaskStore",
    # Progress
    "ProgressTracker",
    "get_progress_tracker",
    # Registry
    "TASK_REGISTRY",
    "TaskQueue",
    "TaskTypeConfig",
    "get_task_config",
    "is_valid_task_type",
    "get_registered_task_types",
]
```

**Step 2: Verify all exports**

Run: `python -c "from src.task import TaskService, TaskStore, celery_app; print('OK')"`

Expected: `OK`

**Step 3: Commit**

```bash
git add src/task/__init__.py
git commit -m "feat(task): update module exports"
```

---

### Task 17: Run Full Test Suite

**Step 1: Run all tests**

Run: `python -m pytest tests/ -v --tb=short`

**Step 2: Verify task tests pass**

Run: `python -m pytest tests/task/ tests/integration/test_task_flow.py -v`

**Step 3: Fix any failures**

If tests fail, fix issues and re-run.

**Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix(task): resolve test failures"
```

---

## Summary

| Phase | Tasks | Description |
|-------|-------|-------------|
| Phase 1 | 1-9 | Core Infrastructure (Celery, Models, Store, Service, API) |
| Phase 2 | 10-12 | Progress & SSE (ProgressTracker, SSE Stream, Base Task) |
| Phase 3 | 13-14 | Integration Tests (Unit Tests, Integration Tests) |
| Phase 4 | 15-17 | Production Ready (Worker, Exports, Full Tests) |

**Total: 17 Tasks**
