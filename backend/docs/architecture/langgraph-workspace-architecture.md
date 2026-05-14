# Compute Workspace Architecture

Last Updated: 2026-04-28
Status: Current

## Overview

Wenjin executes workspace features through the Compute-centered pipeline:

1. Chat receives user intent and stays the control plane.
2. All chat turns enter lead-agent (`create_react_agent`), which handles pure chat and decides when to launch features.
3. lead-agent calls the builtin `launch_feature` tool, which directly invokes `FeatureIngressService.launch()` for feature lifecycle creation.
4. Feature ingress creates `Execution` and `ComputeSession` records as the source of truth.
5. `TaskService` dispatches execution into the registered feature runtime.
6. The feature runtime uses `FeatureLeaderRuntime` / AgentHarness / LangGraph modules to run the work.
7. Runtime progress and artifacts are projected into Compute; manuscript file changes are proposed to WenjinPrism through the file-change review gate.

LangGraph 在当前架构中以进程内 graph runtime 形式存在，不要求独立外部 LangGraph 服务参与主链路。它是 Compute 工作平面内部的执行实现，不是 chat 自由调用的 feature 工具入口。

## Canonical Entry

- Chat control-plane entry:
  - `POST /api/threads/{thread_id}/turns`

- Feature execution entry:
  - `POST /api/workspaces/{workspace_id}/features/{feature_id}/execute`

- Compute read/write APIs:
  - `GET /api/compute/sessions/{session_id}`
  - `GET /api/compute/sessions/{session_id}/events`

- Supporting task APIs:
  - `GET /api/workspaces/{workspace_id}/features`
  - `GET /api/tasks/{task_id}`
  - `GET /api/tasks/{task_id}/stream`

There is no separate public `/api/workspace-features/execute` compatibility entry.
Chat 触发 feature 时由 lead-agent 通过内置 `launch_feature` tool 直接调用 `FeatureIngressService.launch()` 进入 FeatureIngress。

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
  - feature lifecycle creation through FeatureIngress
  - task submission through the canonical task service

### Compute Runtime

- Location:
  - `backend/src/compute/`
  - `backend/src/database/models/compute_session.py`
- Responsibility:
  - session projection
  - activity and artifact presentation
  - subagent progress projection
  - Prism file-change review state

Compute is the work plane. Chat may summarize or launch work, but it does not own runtime state.

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
- Runtime profiles:
  - `backend/src/workspace_features/runtime_profiles.py`
- Graph resolver/executor:
  - `backend/src/agents/feature_leader/`
- Agent harness:
  - `backend/src/agents/harness/`
- Graph implementations:
  - `backend/src/agents/graphs/`

Feature metadata is defined once in the registry and executed through registered graph functions.
chat skills 不是独立 graph runtime；它们是 lead-agent 判断何时调用 `launch_feature` 的上下文语义。

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

- model invocation and runtime decisions
- domain-specific normalization
- generation-mode decisions
- stable result payload assembly

## Result And Manuscript Contract

Feature runs are normalized before persistence. The important result surfaces are:

- `Execution` lifecycle state
- `ComputeSession` projection state
- task status and progress
- artifact creation / update
- workspace refresh targets
- structured runtime blocks for frontend presentation
- Prism file changes awaiting preview / apply / discard / revert

Writing and LaTeX features follow this ownership split:

- generation happens in Feature runtime
- process visibility happens in Compute
- acceptance happens through the review gate
- committed manuscript state lives in WenjinPrism
- final summaries return to Chat

The registry, task runtime, Compute projection, and Prism file-change contracts must remain aligned. New features should plug into this pipeline instead of inventing parallel execution paths.
