# Agent Harness Architecture Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all architecture issues identified in the agent harness review — middleware ordering fragility, ParallelExecutor missing timeouts/error cascade, hardcoded discipline norms, import-time bootstrap, and citation validation gaps.

**Architecture:** Add declarative middleware ordering metadata with runtime validation, phase-level timeouts and fail-fast to ParallelExecutor, externalize discipline norms to YAML config, defer MCP bootstrap to first request, and add structured citation validation with logging.

**Tech Stack:** Python 3.12, asyncio, pytest, PyYAML (already in deps), LangGraph, dataclasses

---

### Task 1: Add Middleware Ordering Metadata and Validation

**Files:**
- Modify: `backend/src/agents/middlewares/base.py`
- Modify: `backend/src/agents/lead_agent/agent.py:491-591`
- Modify: `backend/tests/agents/test_pipeline_assembly.py`

**Step 1: Write the failing test**

Add to `backend/tests/agents/test_pipeline_assembly.py`:

```python
def test_pipeline_validates_ordering_constraints(self):
    """build_pipeline must raise if ClarificationMiddleware is not last."""
    from src.agents.lead_agent.agent import build_pipeline, validate_pipeline
    from src.agents.middlewares.base import Middleware

    config = _pipeline_config(subagent_enabled=False)

    with patch("src.agents.lead_agent.agent.get_app_config", return_value=_mock_app_config()), patch(
        "src.agents.lead_agent.agent.get_sandbox_provider",
        return_value=None,
    ), patch(
        "src.thesis.execution.get_execution_service",
        side_effect=RuntimeError("execution disabled"),
    ):
        pipeline = build_pipeline(config=config)

    # validate_pipeline should succeed on valid pipeline
    validate_pipeline(pipeline)

def test_pipeline_validation_rejects_wrong_clarification_position(self):
    """validate_pipeline must raise if ClarificationMiddleware is not last."""
    from src.agents.lead_agent.agent import validate_pipeline
    from src.agents.middlewares.clarification import ClarificationMiddleware
    from src.agents.middlewares.thread_data import ThreadDataMiddleware

    pipeline = [ClarificationMiddleware(), ThreadDataMiddleware()]
    with pytest.raises(ValueError, match="ClarificationMiddleware must be last"):
        validate_pipeline(pipeline)

def test_pipeline_validation_rejects_wrong_thread_data_position(self):
    """validate_pipeline must raise if ThreadDataMiddleware is not first."""
    from src.agents.lead_agent.agent import validate_pipeline
    from src.agents.middlewares.clarification import ClarificationMiddleware
    from src.agents.middlewares.discipline_context import DisciplineContextMiddleware
    from src.agents.middlewares.thread_data import ThreadDataMiddleware

    pipeline = [DisciplineContextMiddleware(), ThreadDataMiddleware(), ClarificationMiddleware()]
    with pytest.raises(ValueError, match="ThreadDataMiddleware must be first"):
        validate_pipeline(pipeline)

def test_middleware_ordering_metadata(self):
    """Each middleware class should expose ordering metadata."""
    from src.agents.middlewares.base import Middleware
    from src.agents.middlewares.thread_data import ThreadDataMiddleware
    from src.agents.middlewares.clarification import ClarificationMiddleware

    assert ThreadDataMiddleware.position == "first"
    assert ClarificationMiddleware.position == "last"
    assert Middleware.position is None  # default
```

**Step 2: Run test to verify it fails**

Run: `cd /home/cjz/wenjin/backend && python -m pytest tests/agents/test_pipeline_assembly.py::TestPipelineAssembly::test_pipeline_validates_ordering_constraints -xvs`
Expected: FAIL (validate_pipeline not found, position not found)

**Step 3: Write minimal implementation**

In `backend/src/agents/middlewares/base.py`, add class attribute:

```python
class Middleware(ABC):
    position: str | None = None  # "first", "last", or None
    # ... rest unchanged
```

In `backend/src/agents/middlewares/thread_data.py`, add:

```python
class ThreadDataMiddleware(Middleware):
    position = "first"
    # ... rest unchanged
```

In `backend/src/agents/middlewares/clarification.py`, add:

```python
class ClarificationMiddleware(Middleware):
    position = "last"
    # ... rest unchanged
```

In `backend/src/agents/lead_agent/agent.py`, add validate function and call it at end of `build_pipeline`:

```python
def validate_pipeline(pipeline: list[Middleware]) -> None:
    """Validate middleware ordering constraints.

    Raises ValueError if constraints are violated.
    """
    if not pipeline:
        return

    for i, mw in enumerate(pipeline):
        if getattr(mw, "position", None) == "first" and i != 0:
            raise ValueError(f"{type(mw).__name__} must be first in the pipeline, found at index {i}")
        if getattr(mw, "position", None) == "last" and i != len(pipeline) - 1:
            raise ValueError(f"{type(mw).__name__} must be last in the pipeline, found at index {i}")
```

Add `validate_pipeline(pipeline)` as the last line before `return pipeline` in `build_pipeline()`.

**Step 4: Run test to verify it passes**

Run: `cd /home/cjz/wenjin/backend && python -m pytest tests/agents/test_pipeline_assembly.py -xvs`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/agents/middlewares/base.py backend/src/agents/middlewares/thread_data.py backend/src/agents/middlewares/clarification.py backend/src/agents/lead_agent/agent.py backend/tests/agents/test_pipeline_assembly.py
git commit -m "feat: add middleware ordering metadata and pipeline validation"
```

---

### Task 2: Add Phase-Level Timeout to ParallelExecutor

**Files:**
- Modify: `backend/src/subagents/parallel.py:89-171`
- Modify: `backend/tests/subagents/test_parallel.py`

**Step 1: Write the failing test**

Add to `backend/tests/subagents/test_parallel.py`:

```python
class TestParallelExecutorTimeout:
    @pytest.mark.asyncio
    async def test_phase_timeout_raises_on_slow_task(self):
        """Phase execution should raise TimeoutError when phase_timeout is exceeded."""
        executor = ParallelExecutor(phase_timeout=0.1)

        plan = PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="slow_phase",
                    tasks=[{"subagent_type": "scout", "prompt": "slow task"}],
                ),
            ],
        )

        mock_manager = _make_manager(output="result")
        mock_manager.wait_for_completion = AsyncMock(side_effect=lambda *a, **kw: asyncio.sleep(10))

        with patch("src.subagents.parallel.get_manager", return_value=mock_manager):
            results = await executor.execute_plan(plan, context={"workspace_id": "test"})

        assert results[0].success is False
        assert "timed out" in results[0].error.lower()

    @pytest.mark.asyncio
    async def test_phase_timeout_default_is_none(self):
        """Default phase_timeout should be None (no timeout)."""
        executor = ParallelExecutor()
        assert executor.phase_timeout is None

    @pytest.mark.asyncio
    async def test_phase_completes_within_timeout(self):
        """Phase should succeed when completing within timeout."""
        executor = ParallelExecutor(phase_timeout=10.0)

        plan = PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="fast_phase",
                    tasks=[{"subagent_type": "scout", "prompt": "fast task"}],
                ),
            ],
        )

        mock_manager = _make_manager(output="quick result")

        with patch("src.subagents.parallel.get_manager", return_value=mock_manager):
            results = await executor.execute_plan(plan, context={"workspace_id": "test"})

        assert results[0].success is True
```

**Step 2: Run test to verify it fails**

Run: `cd /home/cjz/wenjin/backend && python -m pytest tests/subagents/test_parallel.py::TestParallelExecutorTimeout -xvs`
Expected: FAIL (TypeError: unexpected keyword argument 'phase_timeout')

**Step 3: Write minimal implementation**

In `backend/src/subagents/parallel.py`, modify `ParallelExecutor.__init__` and `_execute_phase`:

```python
class ParallelExecutor:
    def __init__(self, max_concurrent: int = 4, phase_timeout: float | None = None):
        self.max_concurrent = max_concurrent
        self.phase_timeout = phase_timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._phase_events: dict[str, asyncio.Event] = {}

    async def _execute_phase(
        self,
        phase: ExecutionPhase,
        context: dict[str, Any],
    ) -> PhaseResult:
        """Execute a single phase with optional timeout."""
        try:
            if self.phase_timeout is not None:
                return await asyncio.wait_for(
                    self._execute_phase_inner(phase, context),
                    timeout=self.phase_timeout,
                )
            return await self._execute_phase_inner(phase, context)
        except asyncio.TimeoutError:
            return PhaseResult(
                phase_name=phase.name,
                task_results=[],
                error=f"Phase '{phase.name}' timed out after {self.phase_timeout}s",
            )

    async def _execute_phase_inner(
        self,
        phase: ExecutionPhase,
        context: dict[str, Any],
    ) -> PhaseResult:
        """Execute a single phase (possibly with parallel tasks)."""
        task_results = []

        if phase.is_parallel():
            tasks = [
                self._execute_task(task, context)
                for task in phase.tasks
            ]
            task_results = await asyncio.gather(*tasks)
        else:
            for task in phase.tasks:
                result = await self._execute_task(task, context)
                task_results.append(result)

        return PhaseResult(
            phase_name=phase.name,
            task_results=list(task_results),
        )
```

Note: PhaseResult `__post_init__` sets `self.success = True` for empty `task_results`, but we need the timeout case to be `success=False`. The `error` field being set means we need to add a check: if `self.error` is not None, set `self.success = False` at the end of `__post_init__`.

Add to `PhaseResult.__post_init__`:
```python
def __post_init__(self) -> None:
    # ... existing logic ...
    if self.error is not None:
        self.success = False
```

**Step 4: Run test to verify it passes**

Run: `cd /home/cjz/wenjin/backend && python -m pytest tests/subagents/test_parallel.py -xvs`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/subagents/parallel.py backend/tests/subagents/test_parallel.py
git commit -m "feat: add phase-level timeout to ParallelExecutor"
```

---

### Task 3: Add Fail-Fast Error Cascade to ParallelExecutor

**Files:**
- Modify: `backend/src/subagents/parallel.py:89-145`
- Modify: `backend/tests/subagents/test_parallel.py`

**Step 1: Write the failing test**

Add to `backend/tests/subagents/test_parallel.py`:

```python
class TestParallelExecutorFailFast:
    @pytest.mark.asyncio
    async def test_fail_fast_skips_dependent_phases(self):
        """When fail_fast=True, phases depending on a failed phase should be skipped."""
        executor = ParallelExecutor(fail_fast=True)

        plan = PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="phase1",
                    tasks=[{"subagent_type": "scout", "prompt": "task"}],
                ),
                ExecutionPhase(
                    name="phase2",
                    tasks=[{"subagent_type": "synthesizer", "prompt": "task"}],
                    depends_on=["phase1"],
                ),
            ],
        )

        mock_manager = _make_manager(
            status=SubagentStatus.FAILED,
            output=None,
            error="task failed",
        )

        with patch("src.subagents.parallel.get_manager", return_value=mock_manager):
            results = await executor.execute_plan(plan, context={"workspace_id": "test"})

        assert len(results) == 2
        assert results[0].success is False
        assert results[1].success is False
        assert "skipped" in results[1].error.lower()

    @pytest.mark.asyncio
    async def test_fail_fast_default_is_false(self):
        """Default fail_fast should be False."""
        executor = ParallelExecutor()
        assert executor.fail_fast is False

    @pytest.mark.asyncio
    async def test_fail_fast_false_continues_after_failure(self):
        """When fail_fast=False, dependent phases still execute."""
        executor = ParallelExecutor(fail_fast=False)

        plan = PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="phase1",
                    tasks=[{"subagent_type": "scout", "prompt": "task"}],
                ),
                ExecutionPhase(
                    name="phase2",
                    tasks=[{"subagent_type": "scout", "prompt": "task"}],
                    depends_on=["phase1"],
                ),
            ],
        )

        call_count = 0
        async def varying_result(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return SubagentResult(task_id="t1", status=SubagentStatus.FAILED, output=None, error="failed")
            return SubagentResult(task_id="t2", status=SubagentStatus.COMPLETED, output="ok", error=None)

        mock_manager = _make_manager()
        mock_manager.wait_for_completion = AsyncMock(side_effect=varying_result)

        with patch("src.subagents.parallel.get_manager", return_value=mock_manager):
            results = await executor.execute_plan(plan, context={"workspace_id": "test"})

        assert len(results) == 2
        assert results[0].success is False
        assert results[1].success is True  # Still executed despite phase1 failure
```

**Step 2: Run test to verify it fails**

Run: `cd /home/cjz/wenjin/backend && python -m pytest tests/subagents/test_parallel.py::TestParallelExecutorFailFast -xvs`
Expected: FAIL (TypeError: unexpected keyword argument 'fail_fast')

**Step 3: Write minimal implementation**

In `backend/src/subagents/parallel.py`, modify `ParallelExecutor`:

```python
def __init__(self, max_concurrent: int = 4, phase_timeout: float | None = None, fail_fast: bool = False):
    self.max_concurrent = max_concurrent
    self.phase_timeout = phase_timeout
    self.fail_fast = fail_fast
    self._semaphore = asyncio.Semaphore(max_concurrent)
    self._phase_events: dict[str, asyncio.Event] = {}
```

In `execute_plan`, track failed phases and skip dependents:

```python
async def execute_plan(self, plan, context=None, phase_callback=None):
    # ... existing setup ...
    failed_phases: set[str] = set()

    for phase in plan.phases:
        for dep in phase.depends_on:
            await self._phase_events[dep].wait()

        # Check if any dependency failed and fail_fast is on
        if self.fail_fast and any(dep in failed_phases for dep in phase.depends_on):
            failed_deps = sorted(set(phase.depends_on) & failed_phases)
            phase_result = PhaseResult(
                phase_name=phase.name,
                task_results=[],
                error=f"Skipped: dependency phase(s) {', '.join(failed_deps)} failed",
            )
        else:
            phase_result = await self._execute_phase(phase, context)

        results[phase.name] = phase_result

        if not phase_result.success:
            failed_phases.add(phase.name)

        if phase_callback is not None:
            await phase_callback(phase_result)

        self._phase_events[phase.name].set()

    return list(results.values())
```

**Step 4: Run test to verify it passes**

Run: `cd /home/cjz/wenjin/backend && python -m pytest tests/subagents/test_parallel.py -xvs`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/subagents/parallel.py backend/tests/subagents/test_parallel.py
git commit -m "feat: add fail-fast error cascade to ParallelExecutor"
```

---

### Task 4: Externalize Discipline Norms to YAML Config

**Files:**
- Create: `backend/src/agents/middlewares/discipline_norms.yaml`
- Modify: `backend/src/agents/middlewares/discipline_context.py`
- Create: `backend/tests/agents/middlewares/test_discipline_norms.py`

**Step 1: Write the failing test**

Create `backend/tests/agents/middlewares/test_discipline_norms.py`:

```python
"""Tests for externalized discipline norms."""

from pathlib import Path

import yaml

from src.agents.middlewares.discipline_context import (
    DisciplineRegistry,
    DISCIPLINE_NORMS_PATH,
)


def test_discipline_norms_yaml_exists():
    """YAML config file must exist."""
    assert DISCIPLINE_NORMS_PATH.exists()


def test_discipline_norms_yaml_is_valid():
    """YAML file must parse without error and contain expected keys."""
    data = yaml.safe_load(DISCIPLINE_NORMS_PATH.read_text(encoding="utf-8"))
    assert "disciplines" in data
    assert "workspace_types" in data
    assert len(data["disciplines"]) >= 4


def test_registry_loads_from_yaml():
    """DisciplineRegistry should load norms from YAML file."""
    registry = DisciplineRegistry()
    norms = registry.get_norms("computer_science")
    assert norms["citation_style"] == "IEEE"
    assert "structure" in norms


def test_registry_falls_back_on_unknown_discipline():
    """Unknown discipline should fall back to computer_science defaults."""
    registry = DisciplineRegistry()
    norms = registry.get_norms("unknown_field")
    assert norms["citation_style"] == "IEEE"


def test_registry_merges_workspace_type():
    """Workspace type config should merge into norms."""
    registry = DisciplineRegistry()
    norms = registry.get_norms("biology", workspace_type="thesis")
    assert "paper_length" in norms
    assert norms["citation_style"] == "APA"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/cjz/wenjin/backend && python -m pytest tests/agents/middlewares/test_discipline_norms.py -xvs`
Expected: FAIL (DISCIPLINE_NORMS_PATH not found)

**Step 3: Create YAML config**

Create `backend/src/agents/middlewares/discipline_norms.yaml`:

```yaml
disciplines:
  computer_science:
    citation_style: IEEE
    structure:
      - Abstract
      - Introduction
      - Related Work
      - Methodology
      - Experiments
      - Results
      - Discussion
      - Conclusion
    terminology:
      deep learning: Deep Learning
      machine learning: Machine Learning
      neural network: Neural Network
      natural language processing: Natural Language Processing (NLP)
    writing_style: technical and precise

  biology:
    citation_style: APA
    structure:
      - Abstract
      - Introduction
      - Methods
      - Results
      - Discussion
      - Conclusion
    terminology: {}
    writing_style: descriptive and detailed

  physics:
    citation_style: APS
    structure:
      - Abstract
      - Introduction
      - Theory
      - Methods
      - Results
      - Discussion
      - Conclusion
    terminology: {}
    writing_style: mathematical and rigorous

  psychology:
    citation_style: APA
    structure:
      - Abstract
      - Introduction
      - Method
      - Results
      - Discussion
      - References
    terminology: {}
    writing_style: empirical and evidence-based

workspace_types:
  sci:
    paper_length: "6000-8000 words"
    sections: 8
    figures: "3-5"

  thesis:
    paper_length: "30000-50000 words"
    sections: 6
    figures: "10-20"

  proposal:
    paper_length: "2000-4000 words"
    sections: 5
    figures: "2-3"

  software_copyright:
    paper_length: "3000-6000 words"
    sections: 5
    figures: "2-4"

  patent:
    paper_length: "4000-8000 words"
    sections: 6
    figures: "3-5"
```

**Step 4: Modify discipline_context.py to load from YAML**

Replace the hardcoded dicts with YAML-loading code:

```python
"""Discipline context middleware for injecting academic norms."""

import logging
from pathlib import Path
from typing import Any

import yaml
from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState

logger = logging.getLogger(__name__)

DISCIPLINE_NORMS_PATH = Path(__file__).parent / "discipline_norms.yaml"

_DEFAULT_DISCIPLINE = "computer_science"


def _load_norms_config() -> dict[str, Any]:
    """Load discipline norms from YAML config."""
    return yaml.safe_load(DISCIPLINE_NORMS_PATH.read_text(encoding="utf-8"))


class DisciplineRegistry:
    """Registry for discipline-specific norms and configurations."""

    def __init__(self) -> None:
        config = _load_norms_config()
        self._disciplines: dict[str, Any] = config.get("disciplines", {})
        self._workspace_types: dict[str, Any] = config.get("workspace_types", {})

    def get_norms(self, discipline: str, workspace_type: str | None = None) -> dict:
        norms = self._disciplines.get(discipline, self._disciplines[_DEFAULT_DISCIPLINE])

        if workspace_type:
            type_config = self._workspace_types.get(workspace_type, {})
            norms = {**norms, **type_config}

        return norms
```

Keep `DisciplineContextMiddleware` class unchanged (it already delegates to `DisciplineRegistry`).

**Step 5: Run test to verify it passes**

Run: `cd /home/cjz/wenjin/backend && python -m pytest tests/agents/middlewares/test_discipline_norms.py -xvs`
Expected: ALL PASS

**Step 6: Run full test suite to verify no regressions**

Run: `cd /home/cjz/wenjin/backend && python -m pytest tests/agents/ -x --timeout=30`
Expected: ALL PASS

**Step 7: Commit**

```bash
git add backend/src/agents/middlewares/discipline_norms.yaml backend/src/agents/middlewares/discipline_context.py backend/tests/agents/middlewares/test_discipline_norms.py
git commit -m "refactor: externalize discipline norms to YAML config"
```

---

### Task 5: Defer MCP Bootstrap to First Request (Lazy Init)

**Files:**
- Modify: `backend/src/agents/lead_agent/langgraph_entry.py`
- Create: `backend/tests/agents/lead_agent/test_langgraph_entry.py`

**Step 1: Write the failing test**

Create `backend/tests/agents/lead_agent/test_langgraph_entry.py`:

```python
"""Tests for lazy MCP bootstrap in langgraph entry."""

from unittest.mock import AsyncMock, patch

import pytest


def test_module_import_does_not_call_bootstrap():
    """Importing langgraph_entry should NOT trigger MCP bootstrap."""
    with patch("src.agents.lead_agent.langgraph_entry.activate_mcp_runtime") as mock_activate:
        import importlib
        import src.agents.lead_agent.langgraph_entry as entry_module
        importlib.reload(entry_module)
        mock_activate.assert_not_called()


def test_make_lead_agent_graph_triggers_lazy_bootstrap():
    """First call to make_lead_agent_graph should trigger MCP bootstrap."""
    with patch("src.agents.lead_agent.langgraph_entry._ensure_bootstrapped") as mock_boot, \
         patch("src.agents.lead_agent.langgraph_entry.make_lead_agent") as mock_make:
        import importlib
        import src.agents.lead_agent.langgraph_entry as entry_module
        importlib.reload(entry_module)
        entry_module.make_lead_agent_graph({"configurable": {}})
        mock_boot.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `cd /home/cjz/wenjin/backend && python -m pytest tests/agents/lead_agent/test_langgraph_entry.py -xvs`
Expected: FAIL (_ensure_bootstrapped not found)

**Step 3: Implement lazy bootstrap**

Replace `backend/src/agents/lead_agent/langgraph_entry.py`:

```python
"""LangGraph entrypoints with strict signatures required by langgraph-api."""

import asyncio
import atexit
import logging
import threading
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.lead_agent.agent import make_lead_agent
from src.config import get_extensions_config
from src.mcp import activate_mcp_runtime, shutdown_mcp_runtime

logger = logging.getLogger(__name__)

_bootstrapped = False
_bootstrap_lock = threading.Lock()


def _ensure_bootstrapped() -> None:
    """Lazily bootstrap MCP runtime on first request."""
    global _bootstrapped
    if _bootstrapped:
        return

    with _bootstrap_lock:
        if _bootstrapped:
            return

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                asyncio.run(
                    activate_mcp_runtime(
                        extensions_config=get_extensions_config(),
                        warmup=True,
                    )
                )
            except Exception as exc:
                logger.warning("LangGraph MCP runtime bootstrap skipped: %s", exc, exc_info=True)

            _bootstrapped = True
            atexit.register(_shutdown_langgraph_runtime)
            return

        logger.warning(
            "Skipping synchronous MCP bootstrap because an event loop is already running"
        )
        _bootstrapped = True
        atexit.register(_shutdown_langgraph_runtime)


def _shutdown_langgraph_runtime() -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.run(shutdown_mcp_runtime())
        except Exception:
            logger.debug("LangGraph MCP runtime shutdown skipped", exc_info=True)


def make_lead_agent_graph(config: RunnableConfig) -> Any:
    """Create the lead agent graph with langgraph-api compatible signature."""
    _ensure_bootstrapped()
    return make_lead_agent(config)
```

**Step 4: Run test to verify it passes**

Run: `cd /home/cjz/wenjin/backend && python -m pytest tests/agents/lead_agent/test_langgraph_entry.py -xvs`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/agents/lead_agent/langgraph_entry.py backend/tests/agents/lead_agent/test_langgraph_entry.py
git commit -m "refactor: defer MCP bootstrap to first request (lazy init)"
```

---

### Task 6: Add Structured Citation Validation with Logging

**Files:**
- Modify: `backend/src/agents/middlewares/citation_context.py`
- Create: `backend/tests/agents/middlewares/test_citation_context.py`

**Step 1: Write the failing test**

Create `backend/tests/agents/middlewares/test_citation_context.py`:

```python
"""Tests for citation extraction and validation."""

import pytest

from src.agents.middlewares.citation_context import CitationContextMiddleware


class TestCitationExtraction:
    def setup_method(self):
        self.middleware = CitationContextMiddleware(paper_service=None)

    def test_extract_author_year(self):
        """Should extract (Author, Year) citations."""
        citations = self.middleware._extract_citations("As shown by (Smith, 2023)")
        assert any("Smith" in c and "2023" in c for c in citations)

    def test_extract_numbered_citations(self):
        """Should extract [N] citations."""
        citations = self.middleware._extract_citations("As shown in [1] and [2]")
        assert "1" in citations
        assert "2" in citations

    def test_extract_doi(self):
        """Should extract DOI citations."""
        citations = self.middleware._extract_citations("doi:10.1234/test.5678")
        assert any("10.1234/test.5678" in c for c in citations)

    def test_extract_et_al(self):
        """Should extract et al. citations."""
        citations = self.middleware._extract_citations("(Smith et al., 2023)")
        assert any("Smith" in c and "2023" in c for c in citations)

    def test_empty_content_returns_empty(self):
        citations = self.middleware._extract_citations("")
        assert citations == []

    def test_no_citations_returns_empty(self):
        citations = self.middleware._extract_citations("This is plain text.")
        assert citations == []

    def test_deduplicates_citations(self):
        """Repeated citations should be deduplicated."""
        citations = self.middleware._extract_citations("[1] and again [1]")
        assert citations.count("1") == 1


@pytest.mark.asyncio
class TestCitationValidation:
    async def test_after_model_skips_without_workspace_id(self):
        """Should skip when no workspace_id."""
        middleware = CitationContextMiddleware(paper_service=None)
        state = {"messages": []}
        result = await middleware.after_model(state, {})
        assert result == dict(state)

    async def test_after_model_skips_without_messages(self):
        """Should skip when no messages."""
        middleware = CitationContextMiddleware(paper_service=None)
        state = {"workspace_id": "ws-1", "messages": []}
        result = await middleware.after_model(state, {})
        assert result == dict(state)


class TestCitationLogging:
    def test_extraction_logs_count(self, caplog):
        """Citation extraction should be logged."""
        import logging
        middleware = CitationContextMiddleware(paper_service=None)
        with caplog.at_level(logging.DEBUG, logger="src.agents.middlewares.citation_context"):
            middleware._extract_citations("(Smith, 2023) and [1]")
        assert any("citation" in r.message.lower() for r in caplog.records)
```

**Step 2: Run test to verify it fails**

Run: `cd /home/cjz/wenjin/backend && python -m pytest tests/agents/middlewares/test_citation_context.py -xvs`
Expected: FAIL on logging test (no log output)

**Step 3: Add logging to citation_context.py**

Add logger and debug log to `_extract_citations`:

```python
import logging

logger = logging.getLogger(__name__)

class CitationContextMiddleware(Middleware):
    # ... existing code ...

    def _extract_citations(self, content: str) -> list[str]:
        """Extract citation identifiers from content."""
        citations = []

        for pattern in self.CITATION_PATTERNS:
            matches = re.findall(pattern, content)
            for match in matches:
                if isinstance(match, tuple):
                    citations.append(" ".join(match))
                else:
                    citations.append(match)

        unique = list(set(citations))
        if unique:
            logger.debug("Extracted %d citation(s) from response", len(unique))
        return unique
```

**Step 4: Run test to verify it passes**

Run: `cd /home/cjz/wenjin/backend && python -m pytest tests/agents/middlewares/test_citation_context.py -xvs`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/agents/middlewares/citation_context.py backend/tests/agents/middlewares/test_citation_context.py
git commit -m "feat: add citation extraction tests and debug logging"
```

---

### Task 7: Add Cache Eviction Logging to MemoryMiddleware

**Files:**
- Modify: `backend/src/agents/middlewares/memory.py`
- Modify: `backend/tests/agents/middlewares/test_memory_middleware_cache.py`

**Step 1: Write the failing test**

Add to `backend/tests/agents/middlewares/test_memory_middleware_cache.py`:

```python
def test_cache_eviction_logs_warning(caplog):
    """Cache eviction should log at debug level."""
    import logging
    middleware = MemoryMiddleware(queue=None, enabled=True, max_cache_size=2)
    # Fill cache to capacity, then trigger eviction
    middleware._cache["key1"] = (time.time(), {"data": "1"})
    middleware._cache.move_to_end("key1")
    middleware._cache["key2"] = (time.time(), {"data": "2"})
    middleware._cache.move_to_end("key2")

    with caplog.at_level(logging.DEBUG, logger="src.agents.middlewares.memory"):
        # Adding a third entry should evict key1
        middleware._cache["key3"] = (time.time(), {"data": "3"})
        if len(middleware._cache) > middleware._max_cache_size:
            evicted_key, _ = middleware._cache.popitem(last=False)
            logger.debug("Memory cache evicted key: %s", evicted_key)

    # This tests that the eviction path exists; actual middleware caching
    # eviction happens in before_model which is tested elsewhere
```

Actually, this test approach is too convoluted. Instead:

```python
def test_cache_set_with_eviction_logs(caplog):
    """Evicting a cache entry should emit a debug log."""
    import logging

    middleware = MemoryMiddleware(queue=None, enabled=True, max_cache_size=1)
    # Pre-populate cache
    middleware._cache["old-key"] = (time.time(), {"data": "old"})

    with caplog.at_level(logging.DEBUG, logger="src.agents.middlewares.memory"):
        middleware._cache_set("new-key", {"data": "new"})

    assert any("evict" in r.message.lower() for r in caplog.records)
```

**Step 2: Run test to verify it fails**

Run: `cd /home/cjz/wenjin/backend && python -m pytest tests/agents/middlewares/test_memory_middleware_cache.py::test_cache_set_with_eviction_logs -xvs`
Expected: FAIL (_cache_set not found or no eviction log)

**Step 3: Extract cache-set logic with logging**

In `backend/src/agents/middlewares/memory.py`, add a `_cache_set` method and refactor the cache-store path to use it:

```python
def _cache_set(self, key: str, value: dict[str, Any]) -> None:
    """Store a value in cache, evicting LRU if at capacity."""
    if key in self._cache:
        self._cache.move_to_end(key)
    elif len(self._cache) >= self._max_cache_size:
        evicted_key, _ = self._cache.popitem(last=False)
        logger.debug("Memory cache evicted key: %s", evicted_key)
    self._cache[key] = (time.time(), value)
```

Update `before_model` to use `_cache_set` where the cache store currently happens.

**Step 4: Run test to verify it passes**

Run: `cd /home/cjz/wenjin/backend && python -m pytest tests/agents/middlewares/test_memory_middleware_cache.py -xvs`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/agents/middlewares/memory.py backend/tests/agents/middlewares/test_memory_middleware_cache.py
git commit -m "feat: add debug logging on memory cache eviction"
```

---

### Task 8: Full Suite Regression Run

**Files:** None (test-only)

**Step 1: Run full test suite**

Run: `cd /home/cjz/wenjin/backend && python -m pytest tests/ -x --timeout=60 -q`
Expected: All pass (except known pre-existing failures)

**Step 2: Commit nothing — this is verification only**
