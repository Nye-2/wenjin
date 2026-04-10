# LangGraph Workspace Architecture

Last Updated: 2026-04-10
Status: Current

## Overview

Wenjin executes workspace features through a single canonical pipeline:

1. FastAPI router receives a feature execution request.
2. Application handler validates ownership, quotas, and feature metadata.
3. Task service creates an internal async task.
4. Worker dispatches the task to the workspace feature handler.
5. `workspace_lead_agent` resolves and runs the registered feature graph.
6. Results are normalized into artifacts, task state, and workspace refresh events.

LangGraph 在当前架构中以进程内 graph runtime 形式存在，不要求独立外部 LangGraph 服务参与主链路。

## Canonical Entry

- User-facing execution entry:
  - `POST /api/workspaces/{workspace_id}/features/{feature_id}/execute`

- Supporting read APIs:
  - `GET /api/workspaces/{workspace_id}/features`
  - `GET /api/tasks/{task_id}`
  - `GET /api/tasks/{task_id}/stream`

There is no separate public `/api/workspace-features/execute` compatibility entry.
当 chat 需要触发 feature 时，也统一通过 `run_workspace_feature` 接回这条链。

## Execution Layers

### Gateway

- Location: `backend/src/gateway/routers/`
- Responsibility:
  - request parsing
  - auth dependency injection
  - response serialization

### Application

- Location: `backend/src/application/handlers/`
- Responsibility:
  - workspace ownership checks
  - feature lookup from registry
  - credit / policy checks
  - task submission

### Task Runtime

- Location: `backend/src/task/`
- Responsibility:
  - async execution
  - progress updates
  - SSE exposure
  - terminal state persistence

### Feature Graphs

- Registry:
  - `backend/src/workspace_features/registry.py`
- Graph resolver/executor:
  - `backend/src/agents/workspace_lead_agent.py`
- Graph implementations:
  - `backend/src/agents/graphs/`

Feature metadata is defined once in the registry and executed through registered graph functions.
chat skills 不是独立 graph runtime；它们只是 lead-agent 在 chat 层使用的 feature 入口语义。

## Workspace Graph Modules

- `backend/src/agents/graphs/thesis/`
- `backend/src/agents/graphs/sci/`
- `backend/src/agents/graphs/proposal/`
- `backend/src/agents/graphs/patent/`
- `backend/src/agents/graphs/software_copyright/`
- `backend/src/agents/graphs/_shared/`

These modules should stay thin: orchestration and result shaping belong here, while reusable domain logic belongs in service modules.

## Service Layer

- Location:
  - `backend/src/workspace_features/services/`

The service layer owns:

- model invocation and fallback behavior
- domain-specific normalization
- generation-mode decisions
- stable result payload assembly

## Result Contract

Feature runs are normalized before persistence. The important result surfaces are:

- task status and progress
- artifact creation / update
- workspace refresh targets
- structured runtime blocks for frontend presentation

The registry, task runtime, and artifact contracts must remain aligned. New features should plug into this pipeline instead of inventing parallel execution paths.
