# Chat & Feature Metadata Unification Implementation Plan

> 归档说明: 本文档为历史阶段性计划快照，可能包含已过时路由、线程模型或状态描述。当前实现请以 `docs/product/workspace-current-state.md` 与相关当前契约文档为准。

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bring chat and feature metadata into the same `router → application → runtime` architecture, with `FeatureSpecRegistry` as a true single source of truth for all feature behaviour.

**Architecture:** Five self-contained phases. Each phase ships independently and has its own green-test checkpoint. No phase requires another to be complete first — except Phase 2 (FeatureSpec v2) which must precede Phase 3 (TaskRecord) since we want the new columns populated from the registry at write time.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, LangGraph, pytest-asyncio, ruff (linter).

---

## Current-state baseline (read before touching anything)

| Claim from review | Actual state found | Action needed |
|---|---|---|
| `feature_execution_handler.py` imports FastAPI | **Already clean** — no FastAPI imports | Add lint guard to prevent regression |
| `papers_handler.py` imports UploadFile | **Already clean** — no FastAPI imports | Add lint guard to prevent regression |
| chat is a fat router | **Partially fixed** — `ChatTurnHandler` exists and runs turn logic; but chat.py still leaks private application functions as gateway-level wrappers | Clean up wrapper artifacts |
| `registry.py` not single source of truth | Confirmed — credit, runtime, artifacts each have separate hardcoded tables | Phase 2 |
| `task.py` missing first-class columns | Confirmed — `workspace_id`, `feature_id` queried via `payload["workspace_id"].as_string()` | Phase 3 |
| `_FIGURE_STRATEGY_BY_TYPE` duplicated | Confirmed — defined in both `thesis_feature_service.py` AND `figure_generation.py` with comment "mirrors thesis_feature_service" | Phase 4 |

---

## Phase 0 — Architecture guardrails

**Goal:** Freeze the good state, prevent regression.

**Files:**
- Create: `backend/pyproject.toml` or `backend/.ruff.toml` (whichever is the project linter config)
- Create: `backend/tests/architecture/test_layer_boundaries.py`

**Before you start:** Run `cat backend/pyproject.toml` and `ls backend/*.toml backend/*.cfg` to find the existing linter config. Also check `backend/tests/architecture/` — there may already be tests there.

---

### Task 0.1 — Add import boundary lint rule

**Step 1: Find the linter config**

```bash
ls wenjin/backend/pyproject.toml wenjin/backend/.ruff.toml 2>/dev/null
cat wenjin/backend/pyproject.toml | grep -A 20 '\[tool.ruff'
```

**Step 2: Write a pytest architecture boundary test**

File: `backend/tests/architecture/test_layer_boundaries.py`

```python
"""Enforce ADR-platform-boundaries: application handlers must not import HTTP layer."""

import ast
from pathlib import Path

HANDLERS_DIR = Path(__file__).parents[2] / "src" / "application" / "handlers"

FORBIDDEN_MODULES = (
    "fastapi",
    "starlette",
    "src.gateway",
)


def _collect_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.append(node.module)
    return modules


def test_application_handlers_have_no_http_imports():
    """Application handlers must not import FastAPI, Starlette, or gateway deps."""
    violations: list[str] = []
    for py_file in HANDLERS_DIR.glob("*.py"):
        if py_file.name.startswith("_"):
            continue
        for module in _collect_imports(py_file):
            for forbidden in FORBIDDEN_MODULES:
                if module == forbidden or module.startswith(forbidden + "."):
                    violations.append(f"{py_file.name}: imports {module!r}")
    assert not violations, (
        "Application handlers must not import HTTP/gateway modules:\n"
        + "\n".join(violations)
    )
```

**Step 3: Run to confirm it passes (current state is already clean)**

```bash
cd wenjin/backend && python -m pytest tests/architecture/test_layer_boundaries.py -v
```
Expected: `PASSED`

**Step 4: Commit**

```bash
git add backend/tests/architecture/test_layer_boundaries.py
git commit -m "test(arch): enforce no HTTP imports in application handlers"
```

---

### Task 0.2 — Contract test for feature execution response shape

**Step 1: Check existing contract/integration tests**

```bash
ls wenjin/backend/tests/architecture/
ls wenjin/backend/tests/application/
```

**Step 2: Write the test**

File: `backend/tests/architecture/test_feature_execution_contract.py`

```python
"""Contract: FeatureExecutionOutcome must carry the canonical result fields."""

import pytest
from src.application.results import FeatureExecutionOutcome, FeatureTaskSubmission


def test_feature_task_submission_has_required_fields():
    """task_id and advisory must always be present."""
    sub = FeatureTaskSubmission(task_id="t-1", advisory=None)
    assert sub.task_id == "t-1"


def test_feature_execution_outcome_fields():
    """outcome carries submission + optional advisory."""
    sub = FeatureTaskSubmission(task_id="t-1", advisory=None)
    outcome = FeatureExecutionOutcome(submission=sub)
    assert outcome.submission.task_id == "t-1"
```

**Step 3: Run**

```bash
cd wenjin/backend && python -m pytest tests/architecture/test_feature_execution_contract.py -v
```
Expected: `PASSED`

**Step 4: Read `src/application/results.py`** to verify the exact field names before writing the test — adjust the field names if they differ.

**Step 5: Commit**

```bash
git add backend/tests/architecture/test_feature_execution_contract.py
git commit -m "test(arch): contract test for FeatureExecutionOutcome shape"
```

---

## Phase 1 — Clean up chat.py legacy wrapper artefacts

**Goal:** chat.py should contain zero private-function aliases from the application layer. The stream/chat endpoints already use `ChatTurnHandler` correctly; this phase removes the dead wrapper scaffolding.

**Files:**
- Modify: `backend/src/gateway/routers/chat.py`
- Read first: `backend/src/gateway/routers/chat_lifecycle.py`
- Read first: `backend/src/gateway/routers/chat_runtime.py`
- Read first: `backend/src/application/handlers/chat_turn_handler.py` (focus on what `_build_chat_initial_state` and `_build_chat_runtime_config` actually do — are they used anywhere outside the test suite?)

---

### Task 1.1 — Audit whether wrapper functions are used outside chat.py

**Step 1: Search for all usages**

```bash
cd wenjin/backend
grep -rn "_build_chat_runtime_config\|_build_chat_initial_state\|_ensure_chat_turn_budget\|_generate_chat_response" src/ tests/
```

**Step 2: Read chat_lifecycle.py and chat_runtime.py**

```bash
cat wenjin/backend/src/gateway/routers/chat_lifecycle.py
cat wenjin/backend/src/gateway/routers/chat_runtime.py
```

**Step 3: Record findings**
- If the wrapper functions are only referenced inside `chat.py` itself → they can be deleted (the `POST /chat` and `POST /chat/stream` endpoints already use `handler.run_turn()` and `handler.prepare_turn()` / `handler.complete_turn()`)
- If they're used in `chat_lifecycle.py` or `chat_runtime.py` → those callers must be updated to call `ChatTurnHandler` methods directly, then the wrappers are deleted

---

### Task 1.2 — Remove wrapper functions from chat.py

Only execute this after Task 1.1 is complete.

**Step 1: Write regression test for chat endpoints**

File: `backend/tests/gateway/test_chat_router_shape.py`

```python
"""Smoke test: chat router endpoints exist and accept well-formed requests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_chat_endpoint_exists(async_client: AsyncClient):
    """POST /chat is registered and reachable (will 401 without auth)."""
    response = await async_client.post("/api/chat", json={})
    assert response.status_code in (401, 422)  # unauthenticated or validation error


@pytest.mark.asyncio
async def test_chat_stream_endpoint_exists(async_client: AsyncClient):
    """POST /chat/stream is registered and reachable."""
    response = await async_client.post("/api/chat/stream", json={})
    assert response.status_code in (401, 422)
```

**Step 2: Run to confirm baseline passes**

```bash
cd wenjin/backend && python -m pytest tests/gateway/test_chat_router_shape.py -v
```

**Step 3: Delete wrapper functions from chat.py**

In `backend/src/gateway/routers/chat.py`, remove:
- The import block that aliases `_build_chat_initial_state as _application_build_chat_initial_state`, `_build_chat_runtime_config as _application_build_chat_runtime_config`, `ensure_chat_turn_budget as _application_ensure_chat_turn_budget`, `generate_chat_response as _application_generate_chat_response`
- The functions `_build_chat_runtime_config()`, `_build_chat_initial_state()`, `_ensure_chat_turn_budget()`, `_generate_chat_response()`

Keep: `_to_turn_attachment()`, `_to_turn_request()` — these are thin DTO adapters that legitimately belong in the router.

**Step 4: Run tests**

```bash
cd wenjin/backend && python -m pytest tests/gateway/test_chat_router_shape.py tests/architecture/ -v
```
Expected: all `PASSED`

**Step 5: Commit**

```bash
git add backend/src/gateway/routers/chat.py backend/tests/gateway/test_chat_router_shape.py
git commit -m "refactor(chat): remove legacy wrapper functions shadowing application layer"
```

---

### Task 1.3 — Move Redis agent-status logic out of inline import

The `get_thread_agent_status` endpoint has a local `from src.academic.cache.redis_client import redis_client` inside the function body. This should be a top-level import or delegated to a service.

**Step 1: Read the full `get_thread_agent_status` function** (already read — lines 279-306 in chat.py)

**Step 2: Move the Redis reads into a helper in chat_turn_handler.py or a dedicated status service**

Option (simpler): Move the Redis import to module top-level in chat.py.

```python
# At top of chat.py, after other imports:
from src.academic.cache.redis_client import redis_client as _redis_client
from src.config import redis_settings as _redis_settings
```

Then in the function body, reference `_redis_client` and `_redis_settings`.

**Step 3: Run tests**

```bash
cd wenjin/backend && python -m pytest tests/gateway/ -v
```

**Step 4: Commit**

```bash
git add backend/src/gateway/routers/chat.py
git commit -m "refactor(chat): hoist Redis import to module level in agent-status endpoint"
```

---

## Phase 2 — FeatureSpec v2: registry as true single source of truth

**Goal:** `WorkspaceFeatureDefinition` in `registry.py` carries `credit_cost`, `runtime_profile_key`, `artifact_strategy`, and `dashboard_strategy_key`. The separate files (`feature_credit_policy.py`, `runtime_blocks.py`, `workspace_feature_artifacts.py`) become thin lookups into the registry rather than independent hardcoded tables.

**Files:**
- Modify: `backend/src/workspace_features/registry.py`
- Modify: `backend/src/services/feature_credit_policy.py`
- Modify: `backend/src/task/runtime_blocks.py`
- Modify: `backend/src/task/workspace_feature_artifacts.py`
- Test: `backend/tests/workspace_features/test_registry_spec.py`

**Before you start:** Run the full workspace_features test suite to get a baseline:
```bash
cd wenjin/backend && python -m pytest tests/workspace_features/ -v
```

---

### Task 2.1 — Extend WorkspaceFeatureDefinition with credit fields

**Step 1: Write the failing test**

File: `backend/tests/workspace_features/test_registry_spec.py`

```python
"""Registry v2: each feature definition carries its credit cost."""

import pytest
from src.workspace_features.registry import iter_workspace_features


def test_every_feature_has_credit_cost():
    """Every registered feature must declare a credit cost (int or dict)."""
    missing = []
    for feature in iter_workspace_features():
        if not hasattr(feature, "credit_cost") or feature.credit_cost is None:
            missing.append(feature.feature_id)
    assert not missing, f"Features missing credit_cost: {missing}"


def test_thesis_writing_has_action_costs():
    """thesis_writing declares per-action costs."""
    from src.workspace_features.registry import get_workspace_feature

    feature = get_workspace_feature("thesis", "thesis_writing")
    assert isinstance(feature.credit_cost, dict)
    assert "write_chapter" in feature.credit_cost
    assert "write_all" in feature.credit_cost
```

**Step 2: Run to verify it fails**

```bash
cd wenjin/backend && python -m pytest tests/workspace_features/test_registry_spec.py -v
```
Expected: `FAILED` — `AttributeError: 'WorkspaceFeatureDefinition' object has no attribute 'credit_cost'`

**Step 3: Add `credit_cost` to the dataclass**

In `backend/src/workspace_features/registry.py`, modify `WorkspaceFeatureDefinition`:

```python
@dataclass(frozen=True)
class WorkspaceFeatureDefinition:
    feature_id: str
    handler_key: str
    task_type: str
    stages: tuple[FeatureStageDefinition, ...]
    # --- new fields ---
    credit_cost: int | dict[str, int] | None = None
    runtime_profile_key: str | None = None   # key into _FEATURE_RUNTIME_CONFIG
    dashboard_strategy_key: str | None = None
```

**Step 4: Populate `credit_cost` for every feature in the registry**

Open `backend/src/services/feature_credit_policy.py` and read `FEATURE_COSTS` dict. Copy each value into the matching feature definition in `registry.py`. Example for `deep_research`:

```python
WorkspaceFeatureDefinition(
    feature_id="deep_research",
    handler_key="...",
    task_type="...",
    stages=(...),
    credit_cost=100,          # was FEATURE_COSTS["deep_research"] = 100
    runtime_profile_key="deep_research",
)
```

For `thesis_writing`:
```python
credit_cost={
    "generate_outline": 20,
    "write_chapter": 60,
    "write_all": 200,
    "default": 200,
},
```

**Step 5: Run the test**

```bash
cd wenjin/backend && python -m pytest tests/workspace_features/test_registry_spec.py -v
```
Expected: `PASSED`

**Step 6: Commit**

```bash
git add backend/src/workspace_features/registry.py backend/tests/workspace_features/test_registry_spec.py
git commit -m "feat(registry): add credit_cost and runtime_profile_key to WorkspaceFeatureDefinition"
```

---

### Task 2.2 — Make feature_credit_policy delegate to registry

**Step 1: Write the failing test**

```python
# Append to test_registry_spec.py

def test_get_feature_cost_reads_from_registry():
    """get_feature_cost() result must match registry credit_cost."""
    from src.services.feature_credit_policy import get_feature_cost
    from src.workspace_features.registry import get_workspace_feature_by_handler

    # Find any simple-cost feature and verify consistency
    from src.workspace_features.registry import iter_workspace_features
    for feature in iter_workspace_features():
        if isinstance(feature.credit_cost, int):
            policy_cost = get_feature_cost(feature.feature_id)
            assert policy_cost == feature.credit_cost, (
                f"{feature.feature_id}: registry={feature.credit_cost}, "
                f"policy={policy_cost}"
            )
            break  # one is enough for the contract test
```

**Step 2: Run to verify it fails** (it won't fail if credit_policy still has its own dict — it will pass for the wrong reason. Check whether policy reads from registry now or from its own dict.)

```bash
cd wenjin/backend && python -m pytest tests/workspace_features/test_registry_spec.py::test_get_feature_cost_reads_from_registry -v
```

**Step 3: Rewrite `get_feature_cost` to use registry**

In `backend/src/services/feature_credit_policy.py`:

```python
from src.workspace_features.registry import iter_workspace_features

def get_feature_cost(feature_id: str, action: str | None = None) -> int:
    """Resolve credit cost from the feature registry."""
    for feature in iter_workspace_features():
        if feature.feature_id == feature_id:
            cost = feature.credit_cost
            if isinstance(cost, dict):
                if action and action in cost:
                    return cost[action]
                return cost.get("default", 0)
            return cost or 0
    return 0
```

Keep `FEATURE_COSTS`, `BILLABLE_TASK_TYPES`, `FEATURE_DISPLAY_NAMES`, `THESIS_ACTION_LABELS` for now (they may be used elsewhere). Only replace the `get_feature_cost` implementation.

**Step 4: Run full test suite**

```bash
cd wenjin/backend && python -m pytest tests/workspace_features/ tests/services/ -v
```
Expected: all `PASSED`

**Step 5: Commit**

```bash
git add backend/src/services/feature_credit_policy.py backend/tests/workspace_features/test_registry_spec.py
git commit -m "refactor(credit): get_feature_cost now delegates to registry"
```

---

### Task 2.3 — Add artifact_strategy to registry and replace if-elif chain

This is the highest-impact change in Phase 2. `workspace_feature_artifacts.py` has a 320-line if-elif-if chain across 6 workspace types × 20 features × action variants. We replace it with a per-feature artifact builder key registered in the registry.

**Step 1: Read the full if-elif chain**

```bash
sed -n '1,350p' wenjin/backend/src/task/workspace_feature_artifacts.py
```

**Step 2: Define an artifact strategy protocol**

In `backend/src/task/workspace_feature_artifacts.py`, add at the top:

```python
from collections.abc import Callable
from typing import Protocol

ArtifactBuilderFn = Callable[[str, str, str, dict], list]
_ARTIFACT_BUILDERS: dict[str, ArtifactBuilderFn] = {}


def register_artifact_builder(feature_id: str):
    """Decorator to register an artifact builder for a feature."""
    def decorator(fn: ArtifactBuilderFn) -> ArtifactBuilderFn:
        _ARTIFACT_BUILDERS[feature_id] = fn
        return fn
    return decorator
```

**Step 3: For each workspace type's feature block, extract to a decorated function**

Example for `literature_management`:

```python
@register_artifact_builder("literature_management")
def _build_literature_management_artifacts(
    feature_id: str, workspace_name: str, workspace_type: str, result: dict
) -> list:
    # move the existing block here verbatim
    ...
```

Repeat for each feature (one decorated function per feature_id). The existing function `build_langgraph_artifact_drafts` becomes:

```python
def build_langgraph_artifact_drafts(
    feature_id: str, workspace_name: str, workspace_type: str, result: dict
) -> list:
    builder = _ARTIFACT_BUILDERS.get(feature_id)
    if builder is None:
        return []
    return builder(feature_id, workspace_name, workspace_type, result)
```

**Step 4: Write the test**

File: `backend/tests/task/test_artifact_dispatch.py`

```python
"""Artifact builder dispatch: every registered feature has a builder."""

from src.task.workspace_feature_artifacts import _ARTIFACT_BUILDERS
from src.workspace_features.registry import iter_workspace_features


def test_every_feature_has_artifact_builder():
    """Every feature in the registry must have a registered artifact builder."""
    missing = [
        f.feature_id
        for f in iter_workspace_features()
        if f.feature_id not in _ARTIFACT_BUILDERS
    ]
    assert not missing, f"Features missing artifact builder: {missing}"
```

**Step 5: Run**

```bash
cd wenjin/backend && python -m pytest tests/task/test_artifact_dispatch.py -v
```

**Step 6: Run full suite**

```bash
cd wenjin/backend && python -m pytest tests/ -x -q
```

**Step 7: Commit**

```bash
git add backend/src/task/workspace_feature_artifacts.py backend/tests/task/test_artifact_dispatch.py
git commit -m "refactor(artifacts): replace if-elif chain with registry-dispatched builders"
```

---

## Phase 3 — TaskRecord structural fields

**Goal:** `workspace_id`, `feature_id`, `thread_id`, `action` as first-class columns; queries in `task/service.py`, `dashboard/shared.py`, `workspace_activity_service.py` drop JSONB path syntax.

**Files:**
- Modify: `backend/src/database/models/task.py`
- Create: `backend/alembic/versions/<timestamp>_task_structural_fields.py`
- Modify: `backend/src/task/service.py` (find_active_task)
- Modify: `backend/src/services/dashboard/shared.py`
- Modify: `backend/src/services/workspace_activity_service.py`

**Before you start:**
```bash
# Find where tasks are created (INSERT) to know what needs to populate the new columns
grep -rn "TaskRecord(" wenjin/backend/src/ | head -20
# Find Alembic config
ls wenjin/backend/alembic/
```

---

### Task 3.1 — Add columns to TaskRecord model

**Step 1: Write the failing test**

File: `backend/tests/database/test_task_model_fields.py`

```python
"""TaskRecord must have first-class columns for workspace context."""

from src.database.models.task import TaskRecord


def test_task_record_has_workspace_id_column():
    assert hasattr(TaskRecord, "workspace_id")


def test_task_record_has_feature_id_column():
    assert hasattr(TaskRecord, "feature_id")


def test_task_record_has_thread_id_column():
    assert hasattr(TaskRecord, "thread_id")


def test_task_record_has_action_column():
    assert hasattr(TaskRecord, "action")
```

**Step 2: Run to confirm failure**

```bash
cd wenjin/backend && python -m pytest tests/database/test_task_model_fields.py -v
```

**Step 3: Add the columns**

In `backend/src/database/models/task.py`, add after the `task_type` column:

```python
workspace_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
feature_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
thread_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
action: Mapped[str | None] = mapped_column(String, nullable=True)
```

Add composite index at the bottom of the class:

```python
__table_args__ = (
    Index("ix_task_user_status", "user_id", "status"),
    Index("ix_task_workspace_feature_status", "workspace_id", "feature_id", "status"),
)
```

**Step 4: Run the test**

```bash
cd wenjin/backend && python -m pytest tests/database/test_task_model_fields.py -v
```
Expected: `PASSED`

**Step 5: Commit model change**

```bash
git add backend/src/database/models/task.py backend/tests/database/test_task_model_fields.py
git commit -m "feat(task): add workspace_id, feature_id, thread_id, action columns to TaskRecord"
```

---

### Task 3.2 — Write and run Alembic migration

**Step 1: Generate migration**

```bash
cd wenjin/backend && alembic revision --autogenerate -m "task_structural_fields"
```

**Step 2: Review the generated migration**

```bash
ls wenjin/backend/alembic/versions/ | sort | tail -3
cat wenjin/backend/alembic/versions/<new-file>.py
```

Verify it adds the four columns and the composite index. If autogenerate missed anything, add manually.

**Step 3: Apply migration (dev database)**

```bash
cd wenjin/backend && alembic upgrade head
```

**Step 4: Commit**

```bash
git add backend/alembic/versions/
git commit -m "chore(db): migration — task structural fields (workspace_id, feature_id, thread_id, action)"
```

---

### Task 3.3 — Populate new columns at task creation

**Step 1: Find where TaskRecord rows are inserted**

```bash
grep -rn "TaskRecord(" wenjin/backend/src/ --include="*.py"
```

**Step 2: Read the task creation site(s)** — likely in `task/service.py` `submit_task()` or similar.

**Step 3: Extract workspace_id, feature_id, action from payload at creation time**

In the task creation code, add extraction logic:

```python
# Extract structured fields from payload (workspace feature tasks only)
_payload = payload or {}
_params = _payload.get("params", {})
task = TaskRecord(
    ...existing fields...,
    workspace_id=_payload.get("workspace_id") or _params.get("workspace_id"),
    feature_id=_payload.get("feature_id"),
    thread_id=_payload.get("thread_id"),
    action=_payload.get("action") or _params.get("action"),
)
```

**Step 4: Run existing task service tests**

```bash
cd wenjin/backend && python -m pytest tests/task/ -v
```

**Step 5: Commit**

```bash
git add backend/src/task/service.py  # or whichever file changed
git commit -m "feat(task): populate structural columns from payload at creation"
```

---

### Task 3.4 — Replace JSONB path queries with column filters

**Step 1: Update `_count_running_workspace_feature_tasks` in `dashboard/shared.py`**

Replace:
```python
.where(TaskRecord.payload["workspace_id"].as_string() == workspace_id)
.where(TaskRecord.task_type == WORKSPACE_FEATURE_TASK)
.where(TaskRecord.payload["feature_id"].as_string() == feature_id)
```

With:
```python
.where(TaskRecord.workspace_id == workspace_id)
.where(TaskRecord.task_type == WORKSPACE_FEATURE_TASK)
.where(TaskRecord.feature_id == feature_id)
```

**Step 2: Update `_get_task_activity` in `workspace_activity_service.py`**

Replace the `.where(TaskRecord.payload["workspace_id"].as_string() == workspace_id)` filter with:
```python
.where(TaskRecord.workspace_id == workspace_id)
```

**Step 3: Update `find_active_task` in `task/service.py`**

Replace the Python-side filtering of the last 50 tasks with a direct SQL query using the new column.

**Step 4: Run all affected tests**

```bash
cd wenjin/backend && python -m pytest tests/task/ tests/services/ tests/workspace_features/ -v
```

**Step 5: Commit**

```bash
git add backend/src/services/dashboard/shared.py \
        backend/src/services/workspace_activity_service.py \
        backend/src/task/service.py
git commit -m "refactor(task): replace JSONB path queries with first-class column filters"
```

---

## Phase 4 — Thesis domain convergence

**Goal:** Single canonical source for `_FIGURE_STRATEGY_BY_TYPE`. `src.thesis` and `workspace_features/services/thesis_feature_service.py` stop redefining the same data.

**Files:**
- Modify: `backend/src/workspace_features/services/thesis_feature_service.py` (keep as canonical)
- Modify: `backend/src/agents/graphs/thesis/figure_generation.py` (import from canonical)
- Audit: `backend/src/agents/graphs/thesis/compile_export.py`

---

### Task 4.1 — Export the strategy mapping from thesis_feature_service

**Step 1: Verify the two definitions are identical**

```bash
grep -A 15 "_FIGURE_STRATEGY_BY_TYPE" \
  wenjin/backend/src/workspace_features/services/thesis_feature_service.py \
  wenjin/backend/src/agents/graphs/thesis/figure_generation.py
```

**Step 2: Write a drift-detection test**

File: `backend/tests/workspace_features/test_thesis_strategy_consistency.py`

```python
"""thesis_feature_service is the single source for figure strategy mapping."""

from src.workspace_features.services.thesis_feature_service import (
    _FIGURE_STRATEGY_BY_TYPE as SERVICE_MAPPING,
)
from src.agents.graphs.thesis.figure_generation import (
    _FIGURE_STRATEGY_BY_TYPE as GRAPH_MAPPING,
)


def test_figure_strategy_mappings_are_identical():
    """Both references must point to the same canonical dict — no drift."""
    assert SERVICE_MAPPING is GRAPH_MAPPING, (
        "figure_generation.py must import _FIGURE_STRATEGY_BY_TYPE from "
        "thesis_feature_service.py, not define its own copy. "
        f"Diff: {set(SERVICE_MAPPING.items()) ^ set(GRAPH_MAPPING.items())}"
    )
```

**Step 3: Run to verify it fails (they are separate dicts)**

```bash
cd wenjin/backend && python -m pytest tests/workspace_features/test_thesis_strategy_consistency.py -v
```
Expected: `FAILED` — they are `is`-distinct objects

**Step 4: Fix figure_generation.py to import from thesis_feature_service**

In `backend/src/agents/graphs/thesis/figure_generation.py`, replace the duplicate definition:

```python
# Remove this block:
# _FIGURE_STRATEGY_BY_TYPE: dict[str, str] = {
#     "flowchart": "mermaid",
#     ...
# }

# Add this import at the top:
from src.workspace_features.services.thesis_feature_service import (
    _FIGURE_STRATEGY_BY_TYPE,
)
```

**Step 5: Run the test**

```bash
cd wenjin/backend && python -m pytest tests/workspace_features/test_thesis_strategy_consistency.py -v
```
Expected: `PASSED` — same object

**Step 6: Run full test suite**

```bash
cd wenjin/backend && python -m pytest tests/ -x -q
```

**Step 7: Commit**

```bash
git add backend/src/agents/graphs/thesis/figure_generation.py \
        backend/tests/workspace_features/test_thesis_strategy_consistency.py
git commit -m "refactor(thesis): figure_generation imports strategy map from thesis_feature_service"
```

---

### Task 4.2 — Audit other thesis parallel abstractions

**Step 1: Search for other thesis behaviour defined in multiple places**

```bash
grep -rn "thesis_feature_service\|src\.thesis\." \
  wenjin/backend/src/agents/graphs/thesis/ \
  --include="*.py" | grep -v "_FIGURE_STRATEGY"
```

```bash
grep -rn "def.*thesis\|thesis_writing\|thesis_schema" \
  wenjin/backend/src/workspace_features/services/thesis_feature_service.py \
  wenjin/backend/src/thesis/ \
  --include="*.py" | head -30
```

**Step 2: For each duplication found, create a sub-task following the same pattern:**
- Write a drift-detection test that `assert X is Y` (same object reference)
- Move the canonical definition to `thesis_feature_service.py` (or `registry.py` for pure data)
- Import in the consuming module
- Verify tests pass

**Step 3: Commit each convergence separately**

```bash
git commit -m "refactor(thesis): converge [specific thing] to single definition"
```

---

## Acceptance criteria (verify before declaring done)

Run all of these and confirm they pass:

```bash
cd wenjin/backend

# Architecture guardrails
python -m pytest tests/architecture/ -v

# No regression in workspace features
python -m pytest tests/workspace_features/ -v

# No regression in task layer
python -m pytest tests/task/ -v

# No regression in gateway
python -m pytest tests/gateway/ -v

# Full suite
python -m pytest tests/ -q --tb=short
```

Manual verification checklist:
- [ ] `git grep "from fastapi" src/application/` → zero results
- [ ] `git grep "from src.gateway" src/application/` → zero results
- [ ] `wc -l src/gateway/routers/chat.py` → under 250 lines (down from 307)
- [ ] `git grep "payload\[.workspace_id.\]" src/` → zero results (no more JSONB path queries)
- [ ] `git grep "_FIGURE_STRATEGY_BY_TYPE" src/agents/graphs/thesis/` → only an import line, not a definition

---

## Phase execution order recommendation

1. **Phase 0** (guardrails) — do this first, 30 min, prevents regression
2. **Phase 4** (thesis convergence) — do next, 45 min, highest quick-win clarity
3. **Phase 1** (chat.py cleanup) — do next, depends on audit result
4. **Phase 2** (FeatureSpec v2) — largest phase, do when you have 2+ hours
5. **Phase 3** (task structural fields) — do last, requires DB migration and deploy coordination
