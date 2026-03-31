# Architecture Optimizations Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate the three remaining architectural debt points: the `resolve_feature_params` if-elif chain in feature_bridge_intents.py, hardcoded frontend follow-up prompts that should come from the API, and duplicated `_emit_bound_runtime` helpers scattered across 5+ service files.

**Architecture:** Three independent phases. Phase 1 replaces a 150-line if-elif chain with a registry of per-feature async resolver callables (same pattern as the artifact builder refactor). Phase 2 adds `follow_up_prompt` to `WorkspaceFeatureDefinition`, exposes it via the `/features` API, and removes the hardcoded frontend dict. Phase 3 extracts the duplicated `_emit_bound_runtime` helper into a single shared location and adds a drift-detection test.

**Tech Stack:** Python 3.12, FastAPI, TypeScript/Next.js, pytest-asyncio, frozen dataclasses.

---

## Baseline check (run before starting anything)

```bash
cd /home/cjz/wenjin/backend && python -m pytest tests/ -q --tb=no 2>&1 | tail -3
```

Note the pass/fail counts. Pre-existing failures are expected (3 in test_upload_paper.py).

---

## Phase 1 — feature_bridge_intents.resolve_feature_params → registry dispatch

**Context:** `src/agents/lead_agent/feature_bridge_intents.py` has a 150-line `if feature_id == "..."` elif chain in `resolve_feature_params()`. Each branch is an async param-extraction routine. We replace it with a `_PARAM_RESOLVERS` dict of per-feature async callables.

**Files:**
- Modify: `backend/src/agents/lead_agent/feature_bridge_intents.py`
- Test: `backend/tests/agents/test_feature_bridge_intents.py` (check if exists first)

---

### Task 1.1 — Write failing test

**Step 1: Check if a test file already exists**

```bash
ls /home/cjz/wenjin/backend/tests/agents/ 2>/dev/null
grep -rn "resolve_feature_params\|feature_bridge_intents" \
  /home/cjz/wenjin/backend/tests/ --include="*.py" | head -10
```

**Step 2: Write the dispatch coverage test**

File: `backend/tests/agents/test_feature_bridge_intents_dispatch.py`

```python
"""feature_bridge_intents: every registry feature must have a param resolver."""

import pytest
from src.agents.lead_agent.feature_bridge_intents import _PARAM_RESOLVERS
from src.workspace_features.registry import iter_workspace_features


def test_every_feature_has_param_resolver():
    """Every registered workspace feature must have an entry in _PARAM_RESOLVERS."""
    missing = [
        f.id for f in iter_workspace_features()
        if f.id not in _PARAM_RESOLVERS
    ]
    assert not missing, f"Features missing param resolver: {missing}"


def test_param_resolvers_are_callable():
    """Every resolver in _PARAM_RESOLVERS must be an async callable."""
    import asyncio
    import inspect
    non_callable = [k for k, v in _PARAM_RESOLVERS.items() if not callable(v)]
    assert not non_callable, f"Non-callable resolvers: {non_callable}"
    non_async = [k for k, v in _PARAM_RESOLVERS.items() if not inspect.iscoroutinefunction(v)]
    assert not non_async, f"Non-async resolvers: {non_async}"
```

**Step 3: Run to verify failure**

```bash
cd /home/cjz/wenjin/backend && \
  python -m pytest tests/agents/test_feature_bridge_intents_dispatch.py -v
```
Expected: `FAILED` — `ImportError: cannot import name '_PARAM_RESOLVERS'`

**Step 4: Commit test**

```bash
cd /home/cjz/wenjin/backend && \
  git add tests/agents/test_feature_bridge_intents_dispatch.py && \
  git commit -m "test(bridge): add dispatch coverage test for resolve_feature_params"
```

---

### Task 1.2 — Implement registry dispatch

**Step 1: Read the full feature_bridge_intents.py**

```bash
cat /home/cjz/wenjin/backend/src/agents/lead_agent/feature_bridge_intents.py
```

Understand:
- The exact signature of `resolve_feature_params` (all keyword args)
- Each elif branch: what it reads from `params`, `message`, `workspace`, and what it returns

**Step 2: Add registry infrastructure at top of feature_bridge_intents.py**

After the existing imports, add:

```python
from collections.abc import Callable, Awaitable

# Type for per-feature param resolver functions.
# Signature mirrors resolve_feature_params but scoped to one feature.
ParamResolverFn = Callable[
    ...,  # same kwargs as resolve_feature_params minus feature_id
    Awaitable[tuple[dict, str | None, str | None]],
]
_PARAM_RESOLVERS: dict[str, ParamResolverFn] = {}


def _resolver(feature_id: str):
    """Decorator to register a param resolver for a feature."""
    def decorator(fn: ParamResolverFn) -> ParamResolverFn:
        _PARAM_RESOLVERS[feature_id] = fn
        return fn
    return decorator
```

**Step 3: For each elif branch in `resolve_feature_params`, extract to a `@_resolver` function**

The function signature for each resolver:

```python
@_resolver("feature_id_here")
async def _resolve_feature_id_here(
    *,
    params: dict,
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict, str | None, str | None]:
    # Copy the branch body EXACTLY
    ...
```

The return type is always `(filled_params_dict, error_message_or_None, suggested_feature_id_or_None)`.

**Step 4: Replace resolve_feature_params body**

```python
async def resolve_feature_params(
    *,
    feature_id: str,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    resolver = _PARAM_RESOLVERS.get(feature_id)
    if resolver is None:
        return params, None, None
    return await resolver(
        params=params,
        workspace_type=workspace_type,
        workspace=workspace,
        message=message,
        load_latest_draft_summary=load_latest_draft_summary,
    )
```

**Step 5: Run the dispatch coverage test**

```bash
cd /home/cjz/wenjin/backend && \
  python -m pytest tests/agents/test_feature_bridge_intents_dispatch.py -v
```
Expected: both tests PASSED

**Step 6: Run the broader test suite**

```bash
cd /home/cjz/wenjin/backend && \
  python -m pytest tests/agents/ -q --tb=short 2>&1 | tail -20
```

**Step 7: Commit**

```bash
cd /home/cjz/wenjin/backend && \
  git add src/agents/lead_agent/feature_bridge_intents.py && \
  git commit -m "refactor(bridge): replace resolve_feature_params if-elif with registry dispatch"
```

---

## Phase 2 — Frontend follow-up prompts via API

**Context:** `frontend/lib/workspace-feature-actions.ts` has 20 hardcoded follow-up prompt strings keyed by feature_id. The backend registry already defines all features. We add `follow_up_prompt` to `WorkspaceFeatureDefinition`, expose it through the `/features` API, and remove the frontend hardcode.

**Files:**
- Modify: `backend/src/workspace_features/registry.py`
- Modify: `backend/src/gateway/routers/features.py`
- Modify: `frontend/lib/workspace-feature-actions.ts`
- Test: `backend/tests/workspace_features/test_registry_spec.py`

The 20 follow-up prompts (copy verbatim from frontend):

| feature_id | follow_up_prompt |
|---|---|
| deep_research | 请基于这次深度调研继续收敛研究问题，并给出更具体的创新点与验证路径。 |
| literature_management | 请基于这次文献盘点继续指出还缺哪些关键文献，并给出下一轮补充与筛选建议。 |
| literature_search | 请基于这次检索结果筛出最值得精读的文献，并说明各自对后续写作的价值。 |
| paper_analysis | 请基于这次论文分析继续拆解方法亮点、实验弱点和最值得复用的写法。 |
| writing | 请基于这次章节草稿继续指出证据缺口、论证薄弱点和下一步最该补写的内容。 |
| literature_review | 请基于这次文献综述继续细化研究空白，并给出 3 个可写成 SCI 的问题陈述。 |
| framework_outline | 请基于这次框架结果继续细化摘要、关键词和章节 focus，并指出下一步最适合先写哪一章。 |
| opening_research | 请基于这次研究报告继续补齐研究意义、可行性和技术路线中的薄弱环节。 |
| thesis_writing | 请基于这次写作结果继续指出结构缺口、逻辑断点和下一步最该补写的部分。 |
| figure_generation | 请基于这次图表结果继续优化图意表达，并给出适合写入正文的说明文字。 |
| compile_export | 请基于这次编译结果继续定位错误或优化排版，并给出下一步修复建议。 |
| peer_review | 请基于这次同行评审把修改建议按优先级排序，并给出可直接落稿的改写方案。 |
| journal_recommend | 请基于这次期刊推荐比较前 3 个候选期刊的适配度、风险和投稿策略。 |
| proposal_outline | 请基于这次申报书大纲继续细化研究目标、技术路线和里程碑安排。 |
| background_research | 请基于这次背景调研继续收敛关键问题，并输出可直接写进申报书的现状综述。 |
| experiment_design | 请基于这次实验设计继续细化变量定义、样本方案、实验步骤和评估指标。 |
| copyright_materials | 请基于这次软著材料清单继续指出还缺哪些证明材料、代码页和截图要求。 |
| technical_description | 请基于这次技术说明书继续补齐章节细节，并指出最需要补充的技术实现信息。 |
| patent_outline | 请基于这次专利框架继续收敛权利要求边界，并指出说明书还需要补哪些实施细节。 |
| prior_art_search | 请基于这次现有技术检索继续评估新颖性风险，并给出可执行的规避改写建议。 |

---

### Task 2.1 — Add follow_up_prompt to registry

**Step 1: Write the failing test first**

Append to `backend/tests/workspace_features/test_registry_spec.py`:

```python
def test_every_feature_has_follow_up_prompt():
    """Every registered feature must have a non-empty follow_up_prompt."""
    from src.workspace_features.registry import iter_workspace_features
    missing = [
        f.id for f in iter_workspace_features()
        if not getattr(f, "follow_up_prompt", None)
    ]
    assert not missing, f"Features missing follow_up_prompt: {missing}"
```

Run to verify FAIL:

```bash
cd /home/cjz/wenjin/backend && \
  python -m pytest tests/workspace_features/test_registry_spec.py::test_every_feature_has_follow_up_prompt -v
```
Expected: FAILED — `AttributeError` or missing prompt

**Step 2: Add field to WorkspaceFeatureDefinition**

In `backend/src/workspace_features/registry.py`, add to the dataclass (after `runtime_profile_key`):

```python
follow_up_prompt: str | None = None
```

**Step 3: Populate follow_up_prompt for every feature definition in registry.py**

Using the table above, add `follow_up_prompt="..."` to each `WorkspaceFeatureDefinition(...)` call.

**Step 4: Add to to_api_dict()**

In `registry.py` `to_api_dict()` method, add:

```python
"followUpPrompt": self.follow_up_prompt,
```

**Step 5: Run the test**

```bash
cd /home/cjz/wenjin/backend && \
  python -m pytest tests/workspace_features/test_registry_spec.py -v
```
Expected: all PASSED

**Step 6: Commit**

```bash
cd /home/cjz/wenjin/backend && \
  git add src/workspace_features/registry.py tests/workspace_features/test_registry_spec.py && \
  git commit -m "feat(registry): add follow_up_prompt to WorkspaceFeatureDefinition"
```

---

### Task 2.2 — Expose follow_up_prompt in features API

**Step 1: Update the Pydantic response model in features.py**

In `backend/src/gateway/routers/features.py`, update `WorkspaceFeature`:

```python
class WorkspaceFeature(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    agent: str
    agentLabel: str
    taskType: str = WORKSPACE_FEATURE_TASK
    handlerKey: str | None = None
    panel: str | None = None
    stages: list[FeatureStage] = Field(default_factory=list)
    color: str | None = None
    followUpPrompt: str | None = None   # <-- add this
```

**Step 2: Verify the _feature_to_response helper**

Read `features.py` to find `_feature_to_response()` or similar — it should call `feature.to_api_dict()` which now includes `followUpPrompt`. If it uses `WorkspaceFeature(**feature.to_api_dict())`, it will work automatically. If it manually constructs the dict, add `followUpPrompt=feature.follow_up_prompt`.

**Step 3: Write an API contract test**

Append to `backend/tests/workspace_features/test_registry_spec.py`:

```python
def test_api_dict_includes_follow_up_prompt():
    """to_api_dict() must include followUpPrompt key."""
    from src.workspace_features.registry import iter_workspace_features
    for feature in iter_workspace_features():
        api = feature.to_api_dict()
        assert "followUpPrompt" in api, f"{feature.id} missing followUpPrompt in to_api_dict()"
        assert api["followUpPrompt"] is not None, f"{feature.id} followUpPrompt is None"
        break  # one is enough for contract test
```

Run:
```bash
cd /home/cjz/wenjin/backend && \
  python -m pytest tests/workspace_features/test_registry_spec.py -v
```

**Step 4: Commit**

```bash
cd /home/cjz/wenjin/backend && \
  git add src/gateway/routers/features.py tests/workspace_features/test_registry_spec.py && \
  git commit -m "feat(api): expose followUpPrompt in /features response"
```

---

### Task 2.3 — Frontend reads follow_up_prompt from API

**Step 1: Read the full workspace-feature-actions.ts**

```bash
cat /home/cjz/wenjin/frontend/lib/workspace-feature-actions.ts
```

**Step 2: Read the TypeScript feature type definition**

```bash
grep -rn "followUpPrompt\|follow_up_prompt\|WorkspaceFeature" \
  /home/cjz/wenjin/frontend/lib/ \
  /home/cjz/wenjin/frontend/types/ 2>/dev/null \
  --include="*.ts" --include="*.tsx" | head -20
grep -rn "interface WorkspaceFeature\|type WorkspaceFeature" \
  /home/cjz/wenjin/frontend/ --include="*.ts" --include="*.tsx" | head -10
```

**Step 3: Add followUpPrompt to the TypeScript type**

Find the `WorkspaceFeature` interface/type and add:
```typescript
followUpPrompt?: string | null
```

**Step 4: Update getFeatureFollowUpPrompt to use API data**

In `frontend/lib/workspace-feature-actions.ts`, replace the hardcoded object with a function that reads from the feature object:

```typescript
// Before: a function with a hardcoded object mapping feature_id → string
export function getFeatureFollowUpPrompt(featureId: string): string { ... }

// After: reads from a feature object that came from the API
export function getFeatureFollowUpPrompt(
  feature: { id: string; followUpPrompt?: string | null }
): string {
  return feature.followUpPrompt ?? ""
}
```

**IMPORTANT**: Check where `getFeatureFollowUpPrompt` is called in the codebase first:
```bash
grep -rn "getFeatureFollowUpPrompt" \
  /home/cjz/wenjin/frontend/ --include="*.ts" --include="*.tsx"
```

Update all call sites to pass the feature object instead of just `featureId`.

**Step 5: Verify TypeScript compiles**

```bash
cd /home/cjz/wenjin/frontend && npx tsc --noEmit 2>&1 | head -20
```
Expected: zero errors related to our change

**Step 6: Commit**

```bash
cd /home/cjz/wenjin/frontend && \
  git add lib/workspace-feature-actions.ts && \
  git add $(git diff --name-only | grep -v workspace-feature-actions) 2>/dev/null; \
  cd /home/cjz/wenjin && \
  git add frontend/ && \
  git commit -m "refactor(frontend): read follow_up_prompt from API instead of hardcoded dict"
```

---

## Phase 3 — Extract _emit_bound_runtime to shared utility

**Context:** The same ~8-line `_emit_bound_runtime` helper is copy-pasted into at least 5 files:
- `workspace_features/services/sci_feature_service.py`
- `workspace_features/services/proposal_feature_service.py`
- `workspace_features/services/patent_feature_service.py`
- `workspace_features/services/software_copyright_feature_service.py`
- Possibly `workspace_features/services/thesis_feature_service.py`
- Possibly `agents/graphs/*/` files

We extract it to `task/runtime_blocks.py` (already the home for runtime utilities) as a public helper.

---

### Task 3.1 — Audit all duplicates

**Step 1: Find all occurrences**

```bash
grep -rn "def _emit_bound_runtime" \
  /home/cjz/wenjin/backend/src/ --include="*.py"
```

**Step 2: Check they all have the same signature**

```bash
grep -A 10 "def _emit_bound_runtime" \
  /home/cjz/wenjin/backend/src/workspace_features/services/sci_feature_service.py \
  /home/cjz/wenjin/backend/src/workspace_features/services/proposal_feature_service.py
```

If any have a different signature, note it — the shared version will need to accommodate all variants.

---

### Task 3.2 — Write drift-detection test first

File: `backend/tests/workspace_features/test_shared_runtime_utils.py`

```python
"""Shared runtime utilities: _emit_bound_runtime must have single canonical source."""

import ast
from pathlib import Path


SERVICES_DIR = Path(__file__).parents[2] / "src" / "workspace_features" / "services"
GRAPHS_DIR = Path(__file__).parents[2] / "src" / "agents" / "graphs"


def _defines_emit_bound_runtime(path: Path) -> bool:
    """Return True if the file defines _emit_bound_runtime itself (not imports it)."""
    tree = ast.parse(path.read_text())
    return any(
        isinstance(node, ast.AsyncFunctionDef) and node.name == "_emit_bound_runtime"
        for node in ast.walk(tree)
    )


def test_no_service_defines_emit_bound_runtime():
    """workspace_features/services must not define _emit_bound_runtime locally."""
    offenders = [
        str(p.relative_to(Path(__file__).parents[2] / "src"))
        for p in SERVICES_DIR.rglob("*.py")
        if _defines_emit_bound_runtime(p)
    ]
    assert not offenders, (
        "_emit_bound_runtime must be imported from task.runtime_blocks, not redefined:\n"
        + "\n".join(offenders)
    )


def test_no_graph_defines_emit_bound_runtime():
    """agents/graphs must not define _emit_bound_runtime locally."""
    offenders = [
        str(p.relative_to(Path(__file__).parents[2] / "src"))
        for p in GRAPHS_DIR.rglob("*.py")
        if _defines_emit_bound_runtime(p)
    ]
    assert not offenders, (
        "_emit_bound_runtime must be imported from task.runtime_blocks, not redefined:\n"
        + "\n".join(offenders)
    )
```

Run to verify FAILS:

```bash
cd /home/cjz/wenjin/backend && \
  python -m pytest tests/workspace_features/test_shared_runtime_utils.py -v
```
Expected: FAILED — lists offending files

**Commit the test:**

```bash
cd /home/cjz/wenjin/backend && \
  git add tests/workspace_features/test_shared_runtime_utils.py && \
  git commit -m "test(runtime): add drift-detection test for _emit_bound_runtime"
```

---

### Task 3.3 — Add emit_bound_runtime to task/runtime_blocks.py

**Step 1: Read the canonical implementation** from any service file:

```bash
grep -A 12 "async def _emit_bound_runtime" \
  /home/cjz/wenjin/backend/src/workspace_features/services/sci_feature_service.py
```

**Step 2: Add public function to runtime_blocks.py**

In `backend/src/task/runtime_blocks.py`, append:

```python
async def emit_bound_runtime(
    *,
    message: str,
    current_phase: str,
    stage_transition: bool = False,
) -> None:
    """Emit a runtime progress update using the current task's runtime state.

    This is the canonical implementation — import from here, do not redefine locally.
    Uses the thread-local runtime state; silently no-ops if no runtime is active.
    """
    from src.task.progress import emit_runtime_update, get_runtime_state  # lazy: avoids circular

    runtime = get_runtime_state()
    if runtime is None:
        return
    await emit_runtime_update(
        progress_value=max(runtime_progress_for_phase(runtime), 5),
        message=message,
        current_phase=current_phase,
        runtime=runtime,
        stage_transition=stage_transition,
    )
```

Note: Use a lazy import to avoid circular import issues (same pattern as get_feature_cost fix).

**Step 3: Write a basic test for the function**

Append to `tests/workspace_features/test_shared_runtime_utils.py`:

```python
def test_emit_bound_runtime_is_exported_from_runtime_blocks():
    """emit_bound_runtime must be importable from task.runtime_blocks."""
    from src.task.runtime_blocks import emit_bound_runtime
    import inspect
    assert inspect.iscoroutinefunction(emit_bound_runtime)
```

Run:
```bash
cd /home/cjz/wenjin/backend && \
  python -m pytest tests/workspace_features/test_shared_runtime_utils.py::test_emit_bound_runtime_is_exported_from_runtime_blocks -v
```
Expected: PASSED

**Step 4: Commit**

```bash
cd /home/cjz/wenjin/backend && \
  git add src/task/runtime_blocks.py tests/workspace_features/test_shared_runtime_utils.py && \
  git commit -m "feat(runtime): add canonical emit_bound_runtime to task.runtime_blocks"
```

---

### Task 3.4 — Replace all duplicate definitions

For each file that defines `_emit_bound_runtime` locally:

1. Remove the local `async def _emit_bound_runtime(...)` function definition
2. Add import at the top: `from src.task.runtime_blocks import emit_bound_runtime as _emit_bound_runtime`
3. Run the test suite for that module to verify nothing broke

Example for sci_feature_service.py:
```python
# Add to imports:
from src.task.runtime_blocks import emit_bound_runtime as _emit_bound_runtime
```

Repeat for all files found in Task 3.1.

**After updating all files:**

```bash
cd /home/cjz/wenjin/backend && \
  python -m pytest tests/workspace_features/test_shared_runtime_utils.py -v
```
Expected: all tests PASSED (drift tests now green)

**Step: Run full test suite**

```bash
cd /home/cjz/wenjin/backend && python -m pytest tests/ -q --tb=short 2>&1 | tail -10
```

**Step: Commit**

```bash
cd /home/cjz/wenjin/backend && \
  git add src/workspace_features/services/ src/agents/graphs/ && \
  git commit -m "refactor(runtime): replace local _emit_bound_runtime with import from task.runtime_blocks"
```

---

## Acceptance criteria

Run all of these before declaring done:

```bash
cd /home/cjz/wenjin/backend

# Phase 1: no more if-elif in resolve_feature_params
python -m pytest tests/agents/test_feature_bridge_intents_dispatch.py -v

# Phase 2: registry has follow_up_prompt
python -m pytest tests/workspace_features/test_registry_spec.py -v

# Phase 3: no duplicate _emit_bound_runtime
python -m pytest tests/workspace_features/test_shared_runtime_utils.py -v

# Full suite
python -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

Manual checks:
- [ ] `grep -c "elif feature_id" src/agents/lead_agent/feature_bridge_intents.py` → 0
- [ ] `grep "followUpPrompt" src/workspace_features/registry.py` → present in to_api_dict
- [ ] `grep -rn "def _emit_bound_runtime" src/` → zero results
