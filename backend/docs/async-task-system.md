# Async Task System

Last Updated: 2026-06-23
Status: Current

## Overview

Wenjin runs long-lived research work through an execution-first async task system backed by Celery, Redis, and PostgreSQL.

The task system is internal infrastructure. Public APIs do not create generic tasks directly; domain endpoints submit canonical execution or domain tasks through application handlers.

## Responsibilities

- enqueue long-running work
- persist task history
- expose runtime progress
- stream updates to the frontend
- support cancellation where handlers allow it

## Main Components

### Registry

- Location: `backend/src/task/registry.py`
- Defines:
  - task types
  - queues
  - retry/timeout policy

### Service

- Location: `backend/src/task/service.py`
- Handles:
  - task creation
  - status lookup
  - cancellation
  - persistence coordination

### Store

- Location: `backend/src/task/store.py`
- Storage split:
  - Redis for runtime state and fast reads
  - PostgreSQL for durable task records

### Progress Tracking

- Location: `backend/src/task/progress.py`
- Used by handlers to publish:
  - progress percentage
  - current step
  - human-readable message

### Worker Dispatch

- Celery app:
  - `backend/src/task/celery_app.py`
- Worker task dispatch:
  - `backend/src/task/tasks/base.py`

## Canonical Public APIs

Tasks are normally created through domain-specific runtime entrypoints such as:

- thread / orchestration flows that dispatch canonical `ExecutionRecord` runs
- paper extraction and similar domain routes

Task read APIs:

- `GET /api/tasks/{task_id}`
- `GET /api/tasks/{task_id}/stream`
- `DELETE /api/tasks/{task_id}` when cancellation is supported

`POST /api/tasks` is not part of the public surface.

## Handler Model

Canonical handlers live under:

- `backend/src/task/handlers/`

Typical flow:

1. application layer performs preflight / orchestration
2. execution or domain task is dispatched to Celery
3. worker executes canonical handler
4. progress tracker emits runtime updates
5. final state is persisted and exposed to SSE/API consumers

## Task States

The runtime uses a small terminal-state model:

- `pending`
- `running`
- `success`
- `failed`
- `cancelled`

Frontend code should treat terminal states as immutable snapshots unless a new task id is created.

## Operational Notes

- Redis availability affects live progress and SSE responsiveness.
- PostgreSQL remains the durable source for completed task history.
- Timeout and retry settings should be adjusted in the registry, not duplicated in handlers.
- Generic long-running background work must integrate with the existing task pipeline.
- Workspace capability execution is execution-first and should not reintroduce a parallel task-bridge orchestrator.
- User-visible run state should be projected through execution / RunView surfaces rather than raw task internals.
