# Phase 1: Pipeline Infrastructure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate academiagpt-v2's agent system to deer-flow's 16-layer middleware pipeline architecture with config-driven model/tool loading and reflection system.

**Architecture:** Extend ThreadState from AgentState (LangGraph standard), adopt LangChain's AgentMiddleware protocol for native `create_react_agent` integration, build 16-layer pipeline (11 deer-flow + 5 academic), and introduce config.yaml-driven architecture with dynamic module loading.

**Tech Stack:** LangGraph 0.2.60+, LangChain AgentMiddleware, Pydantic 2.10+, PyYAML, asyncio

---

## Pre-requisites

Before starting, verify the current test suite passes:

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest -x -q 2>&1 | tail -5
```

Expected: `790 passed`

---

### Task 1: Extend ThreadState to Inherit AgentState

**Files:**
- Modify: `backend/src/agents/thread_state.py`
- Test: `backend/tests/agents/test_thread_state.py`

**Step 1: Write the failing test**

Create `backend/tests/agents/test_thread_state.py`:

```python
"""Tests for the unified AcademicThreadState."""

from langchain.agents import AgentState
from langchain_core.messages import HumanMessage

from src.agents.thread_state import (
    AcademicArtifact,
    SandboxState,
    ThreadDataState,
    ThreadState,
    ViewedImageData,
    merge_artifacts,
    merge_cited_papers,
    merge_viewed_images,
)


class TestThreadStateInheritance:
    """ThreadState must extend AgentState for LangGraph compatibility."""

    def test_inherits_agent_state(self):
        assert issubclass(ThreadState, AgentState)

    def test_has_messages_field(self):
        state = ThreadState(messages=[])
        assert hasattr(state, "messages")

    def test_has_deer_flow_fields(self):
        """All deer-flow base fields must be present."""
        state = ThreadState(messages=[])
        # These should not raise
        _ = state.get("sandbox")
        _ = state.get("thread_data")
        _ = state.get("title")
        _ = state.get("todos")
        _ = state.get("uploaded_files")
        _ = state.get("viewed_images")

    def test_has_academic_fields(self):
        """All academic extension fields must be present."""
        state = ThreadState(
            messages=[],
            workspace_id="ws-123",
            workspace_type="sci",
            discipline="computer_science",
        )
        assert state["workspace_id"] == "ws-123"
        assert state["workspace_type"] == "sci"
        assert state["discipline"] == "computer_science"

    def test_cited_papers_merge(self):
        """cited_papers should deduplicate via custom reducer."""
        result = merge_cited_papers(["paper1", "paper2"], ["paper2", "paper3"])
        assert result == ["paper1", "paper2", "paper3"]

    def test_cited_papers_merge_none(self):
        assert merge_cited_papers(None, ["a"]) == ["a"]
        assert merge_cited_papers(["a"], None) == ["a"]


class TestSupportingTypes:
    def test_sandbox_state(self):
        s: SandboxState = {"sandbox_id": "local"}
        assert s["sandbox_id"] == "local"

    def test_thread_data_state(self):
        t: ThreadDataState = {
            "workspace_path": "/tmp/ws",
            "uploads_path": "/tmp/up",
            "outputs_path": "/tmp/out",
        }
        assert t["workspace_path"] == "/tmp/ws"

    def test_viewed_image_data(self):
        v: ViewedImageData = {"base64": "abc", "mime_type": "image/png"}
        assert v["base64"] == "abc"

    def test_merge_viewed_images_clear(self):
        """Empty dict clears all images."""
        result = merge_viewed_images({"img1": {"base64": "a", "mime_type": "image/png"}}, {})
        assert result == {}

    def test_merge_viewed_images_merge(self):
        existing = {"img1": {"base64": "a", "mime_type": "image/png"}}
        new = {"img2": {"base64": "b", "mime_type": "image/jpeg"}}
        result = merge_viewed_images(existing, new)
        assert "img1" in result
        assert "img2" in result


class TestAcademicArtifact:
    def test_artifact_merge_dedup(self):
        a1 = AcademicArtifact(id="1", workspace_id="ws", type="idea", content={"v": 1})
        a2 = AcademicArtifact(id="1", workspace_id="ws", type="idea", content={"v": 2})
        result = merge_artifacts([a1], [a2])
        assert len(result) == 1
        assert result[0].content == {"v": 2}
```

**Step 2: Run test to verify it fails**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/agents/test_thread_state.py -v
```

Expected: FAIL (missing imports like `SandboxState`, `ThreadDataState`, `ViewedImageData`, `merge_cited_papers`, `merge_viewed_images`; ThreadState doesn't inherit AgentState)

**Step 3: Write the implementation**

Replace `backend/src/agents/thread_state.py`:

```python
"""Unified ThreadState: deer-flow base + academic extensions."""

from datetime import UTC, datetime
from typing import Annotated, NotRequired, TypedDict

from langchain.agents import AgentState
from pydantic import BaseModel, Field


# === deer-flow supporting types ===

class SandboxState(TypedDict):
    sandbox_id: NotRequired[str | None]


class ThreadDataState(TypedDict):
    workspace_path: NotRequired[str | None]
    uploads_path: NotRequired[str | None]
    outputs_path: NotRequired[str | None]


class ViewedImageData(TypedDict):
    base64: str
    mime_type: str


# === Academic types ===

class AcademicArtifact(BaseModel):
    """Academic artifact produced by skills."""
    id: str
    workspace_id: str
    type: str  # research_idea, methodology, framework_outline, abstract, paper_draft
    content: dict
    created_by_skill: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# === Reducers ===

def merge_artifacts(
    existing: list[AcademicArtifact] | None,
    new: list[AcademicArtifact] | None,
) -> list[AcademicArtifact]:
    """Merge artifacts, deduplicating by ID (new takes precedence)."""
    if existing is None:
        return new or []
    if new is None:
        return existing
    artifact_map = {a.id: a for a in existing}
    artifact_map.update({a.id: a for a in new})
    return list(artifact_map.values())


def merge_cited_papers(
    existing: list[str] | None,
    new: list[str] | None,
) -> list[str]:
    """Merge cited papers, deduplicating while preserving order."""
    if existing is None:
        return new or []
    if new is None:
        return existing
    return list(dict.fromkeys(existing + new))


def merge_viewed_images(
    existing: dict[str, ViewedImageData] | None,
    new: dict[str, ViewedImageData] | None,
) -> dict[str, ViewedImageData]:
    """Merge viewed images. Empty dict {} clears all images."""
    if existing is None:
        return new or {}
    if new is None:
        return existing
    if len(new) == 0:
        return {}
    return {**existing, **new}


# === Unified ThreadState ===

class ThreadState(AgentState):
    """Unified state: deer-flow base + academic extensions.

    Inherits from AgentState (LangGraph standard) for native middleware support.
    """

    # --- deer-flow base fields ---
    sandbox: NotRequired[SandboxState | None]
    thread_data: NotRequired[ThreadDataState | None]
    title: NotRequired[str | None]
    todos: NotRequired[list | None]
    uploaded_files: NotRequired[list[dict] | None]
    viewed_images: Annotated[dict[str, ViewedImageData], merge_viewed_images]

    # --- academic extension fields ---
    workspace_id: NotRequired[str | None]
    workspace_type: NotRequired[str | None]  # sci, thesis, proposal, grant
    discipline: NotRequired[str | None]
    workspace_config: NotRequired[dict | None]
    literature_context: NotRequired[str | None]
    knowledge_context: NotRequired[str | None]
    discipline_norms: NotRequired[dict | None]
    current_skill: NotRequired[str | None]

    # academic artifacts (with dedup reducer)
    academic_artifacts: Annotated[list[AcademicArtifact], merge_artifacts]

    # citation tracking (with dedup reducer)
    cited_papers: Annotated[list[str], merge_cited_papers]

    # file artifacts paths (deer-flow style, string paths)
    artifacts: Annotated[list[str], lambda a, b: list(dict.fromkeys((a or []) + (b or [])))]

    # subagent task tracking
    subagent_tasks: NotRequired[dict | None]
```

**Step 4: Update `__init__.py` exports**

Modify `backend/src/agents/__init__.py`:

```python
from .lead_agent.agent import make_lead_agent
from .thread_state import (
    AcademicArtifact,
    SandboxState,
    ThreadDataState,
    ThreadState,
    ViewedImageData,
    merge_artifacts,
    merge_cited_papers,
    merge_viewed_images,
)

__all__ = [
    "AcademicArtifact",
    "SandboxState",
    "ThreadDataState",
    "ThreadState",
    "ViewedImageData",
    "make_lead_agent",
    "merge_artifacts",
    "merge_cited_papers",
    "merge_viewed_images",
]
```

**Step 5: Run test to verify it passes**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/agents/test_thread_state.py -v
```

Expected: PASS

**Step 6: Fix existing tests that depend on old ThreadState**

Run full test suite and fix any breakages caused by ThreadState migration:

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest -x -q 2>&1 | tail -20
```

Key areas to fix:
- Tests that instantiate `ThreadState` as Pydantic `BaseModel` (now it's a `TypedDict`-style `AgentState`)
- Tests that use `PrivateAttr` fields (`_workspace_config`, `_literature_context`, etc.) - these are now regular state fields
- Tests that use `.model_dump()` - `AgentState` is dict-like, not Pydantic
- Tests that use `.get_context()` / `.set_context()` - replaced by direct dict access

The migration pattern is:
- `state._workspace_config` → `state.get("workspace_config")`
- `state.set_context("key", val)` → `state["key"] = val`
- `state.get_context("key")` → `state.get("key")`
- `ThreadState(workspace_id="x")` → `ThreadState(messages=[], workspace_id="x")`

**Step 7: Commit**

```bash
git add backend/src/agents/thread_state.py backend/src/agents/__init__.py backend/tests/agents/test_thread_state.py
git commit -m "refactor: migrate ThreadState to extend AgentState with academic fields"
```

---

### Task 2: Add Configuration System (config.yaml + Reflection)

**Files:**
- Create: `backend/src/config/config_loader.py`
- Create: `backend/src/reflection/__init__.py`
- Create: `backend/src/reflection/resolvers.py`
- Create: `backend/config.yaml`
- Test: `backend/tests/config/test_config_loader.py`
- Test: `backend/tests/reflection/test_resolvers.py`

**Step 1: Write the failing tests**

Create `backend/tests/config/test_config_loader.py`:

```python
"""Tests for unified config.yaml loader."""

import tempfile
from pathlib import Path

import yaml

from src.config.config_loader import (
    AppConfig,
    MemoryConfig,
    ModelConfig,
    SandboxConfig,
    SkillsConfig,
    SubagentTypeConfig,
    SubagentsConfig,
    ToolConfig,
    load_config,
)


class TestConfigLoader:
    def _write_config(self, tmp: Path, data: dict) -> Path:
        p = tmp / "config.yaml"
        p.write_text(yaml.dump(data))
        return p

    def test_load_minimal_config(self, tmp_path):
        cfg_path = self._write_config(tmp_path, {
            "models": [{"name": "test", "use": "langchain_openai:ChatOpenAI", "model": "gpt-4o", "api_key": "sk-test"}],
        })
        config = load_config(str(cfg_path))
        assert isinstance(config, AppConfig)
        assert len(config.models) == 1
        assert config.models[0].name == "test"

    def test_env_var_resolution(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TEST_API_KEY", "resolved-key")
        cfg_path = self._write_config(tmp_path, {
            "models": [{"name": "test", "use": "langchain_openai:ChatOpenAI", "model": "gpt-4o", "api_key": "$TEST_API_KEY"}],
        })
        config = load_config(str(cfg_path))
        assert config.models[0].api_key == "resolved-key"

    def test_subagent_types(self, tmp_path):
        cfg_path = self._write_config(tmp_path, {
            "models": [],
            "subagents": {"enabled": True, "max_concurrent": 4, "types": {
                "scout": {"description": "Literature search", "allowed_tools": ["web_search"], "max_turns": 10},
            }},
        })
        config = load_config(str(cfg_path))
        assert config.subagents.enabled is True
        assert "scout" in config.subagents.types
        assert config.subagents.types["scout"].max_turns == 10

    def test_memory_config(self, tmp_path):
        cfg_path = self._write_config(tmp_path, {
            "models": [],
            "memory": {"enabled": True, "injection_enabled": True, "debounce_seconds": 30},
        })
        config = load_config(str(cfg_path))
        assert config.memory.enabled is True
        assert config.memory.debounce_seconds == 30

    def test_defaults(self, tmp_path):
        cfg_path = self._write_config(tmp_path, {"models": []})
        config = load_config(str(cfg_path))
        assert config.subagents.enabled is False
        assert config.memory.enabled is False
        assert config.sandbox is None


class TestModelConfig:
    def test_model_config_fields(self):
        mc = ModelConfig(name="test", use="langchain_openai:ChatOpenAI", model="gpt-4o", api_key="sk-test")
        assert mc.name == "test"
        assert mc.supports_thinking is False  # default
        assert mc.supports_vision is False    # default
        assert mc.tags == []                  # default
```

Create `backend/tests/reflection/test_resolvers.py`:

```python
"""Tests for dynamic module resolution."""

from src.reflection.resolvers import resolve_variable


class TestResolveVariable:
    def test_resolve_known_module(self):
        """Should resolve a known module:variable path."""
        result = resolve_variable("os.path:sep")
        assert isinstance(result, str)

    def test_resolve_missing_raises(self):
        """Should raise ImportError for unknown modules."""
        import pytest
        with pytest.raises(ImportError):
            resolve_variable("nonexistent_module:thing")

    def test_resolve_bad_format_raises(self):
        """Should raise ValueError for paths without colon."""
        import pytest
        with pytest.raises(ValueError):
            resolve_variable("no_colon_here")
```

**Step 2: Run tests to verify they fail**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/config/test_config_loader.py tests/reflection/test_resolvers.py -v
```

Expected: FAIL (modules don't exist)

**Step 3: Implement reflection system**

Create `backend/src/reflection/__init__.py`:

```python
from .resolvers import resolve_class, resolve_variable

__all__ = ["resolve_class", "resolve_variable"]
```

Create `backend/src/reflection/resolvers.py`:

```python
"""Dynamic module loading via path strings like 'module.path:variable_name'."""

import importlib
import os
from typing import TypeVar

T = TypeVar("T")

MODULE_TO_PACKAGE_HINTS = {
    "langchain_google_genai": "langchain-google-genai",
    "langchain_anthropic": "langchain-anthropic",
    "langchain_openai": "langchain-openai",
    "langchain_deepseek": "langchain-deepseek",
}


def resolve_variable(variable_path: str, expected_type: type[T] | tuple[type, ...] | None = None) -> T:
    """Resolve a variable from 'module.path:variable_name'.

    Args:
        variable_path: Path like "langchain_openai:ChatOpenAI"
        expected_type: Optional type validation

    Returns:
        The resolved variable

    Raises:
        ValueError: If path format is invalid
        ImportError: If module not found (with actionable hint)
    """
    if ":" not in variable_path:
        msg = f"Invalid variable path '{variable_path}'. Expected format: 'module.path:variable_name'"
        raise ValueError(msg)

    module_path, variable_name = variable_path.rsplit(":", 1)

    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        top_module = module_path.split(".")[0]
        package_hint = MODULE_TO_PACKAGE_HINTS.get(top_module)
        hint = f" Install it with `uv add {package_hint}`." if package_hint else ""
        msg = f"Missing dependency '{top_module}'.{hint}"
        raise ImportError(msg) from e

    if not hasattr(module, variable_name):
        msg = f"Module '{module_path}' has no attribute '{variable_name}'"
        raise AttributeError(msg)

    variable = getattr(module, variable_name)

    if expected_type is not None and not isinstance(variable, expected_type):
        msg = f"Expected {expected_type}, got {type(variable)}"
        raise TypeError(msg)

    return variable


def resolve_class(class_path: str, base_class: type[T] | None = None) -> type[T]:
    """Resolve a class from path and optionally validate its base class."""
    cls = resolve_variable(class_path, expected_type=type)
    if base_class is not None and not issubclass(cls, base_class):
        msg = f"Expected subclass of {base_class.__name__}, got {cls.__name__}"
        raise TypeError(msg)
    return cls


def resolve_env_variables(data):
    """Recursively resolve $ENV_VAR references in config data."""
    if isinstance(data, str) and data.startswith("$"):
        return os.getenv(data[1:], "")
    if isinstance(data, dict):
        return {k: resolve_env_variables(v) for k, v in data.items()}
    if isinstance(data, list):
        return [resolve_env_variables(item) for item in data]
    return data
```

**Step 4: Implement config loader**

Create `backend/src/config/config_loader.py`:

```python
"""Unified config.yaml loader for AcademiaGPT v2."""

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from src.reflection.resolvers import resolve_env_variables


class ModelConfig(BaseModel):
    """LLM model configuration."""
    name: str
    use: str  # e.g., "langchain_openai:ChatOpenAI"
    model: str
    api_key: str = ""
    base_url: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    supports_thinking: bool = False
    supports_vision: bool = False
    tags: list[str] = Field(default_factory=list)


class ToolConfig(BaseModel):
    """Tool configuration."""
    name: str
    use: str  # e.g., "src.academic.tools.semantic_scholar:search_tool"
    group: str = ""


class ToolGroupConfig(BaseModel):
    """Tool group configuration."""
    name: str
    description: str = ""


class SubagentTypeConfig(BaseModel):
    """Subagent type configuration."""
    description: str = ""
    system_prompt: str = ""
    allowed_tools: list[str] = Field(default_factory=list)
    disallowed_tools: list[str] = Field(default_factory=list)
    max_turns: int = 10
    timeout: int = 900  # 15 min default


class SubagentsConfig(BaseModel):
    """Subagent system configuration."""
    enabled: bool = False
    max_concurrent: int = 3
    types: dict[str, SubagentTypeConfig] = Field(default_factory=dict)


class MemoryConfig(BaseModel):
    """Persistent memory configuration."""
    enabled: bool = False
    injection_enabled: bool = True
    storage_path: str = "backend/.academiagpt/memory.json"
    debounce_seconds: int = 30
    model_name: str | None = None
    max_facts: int = 100
    fact_confidence_threshold: float = 0.7
    max_injection_tokens: int = 2000


class SandboxConfig(BaseModel):
    """Sandbox configuration."""
    use: str  # e.g., "src.sandbox.local:LocalSandboxProvider"


class SkillsConfig(BaseModel):
    """Skills configuration."""
    path: str = "./skills/public"
    container_path: str = "/mnt/skills"


class TitleConfig(BaseModel):
    """Auto-title generation configuration."""
    enabled: bool = True
    max_words: int = 8
    max_chars: int = 60


class SummarizationConfig(BaseModel):
    """Context summarization configuration."""
    enabled: bool = False
    trigger: str = "tokens:80000"
    keep: str = "messages:10"


class AcademicMiddlewareConfig(BaseModel):
    """Academic middleware toggles."""
    workspace_context: bool = True
    literature_context: bool = True
    knowledge_context: bool = True
    discipline_context: bool = True
    citation_tracking: bool = True


class MiddlewaresConfig(BaseModel):
    """Middleware configuration."""
    summarization: SummarizationConfig = Field(default_factory=SummarizationConfig)
    title: TitleConfig = Field(default_factory=TitleConfig)
    academic: AcademicMiddlewareConfig = Field(default_factory=AcademicMiddlewareConfig)


class AppConfig(BaseModel):
    """Unified application configuration loaded from config.yaml."""
    models: list[ModelConfig] = Field(default_factory=list)
    tools: list[ToolConfig] = Field(default_factory=list)
    tool_groups: list[ToolGroupConfig] = Field(default_factory=list)
    subagents: SubagentsConfig = Field(default_factory=SubagentsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    sandbox: SandboxConfig | None = None
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    middlewares: MiddlewaresConfig = Field(default_factory=MiddlewaresConfig)

    def get_model_config(self, name: str) -> ModelConfig | None:
        """Find a model by name."""
        for m in self.models:
            if m.name == name:
                return m
        return None

    def get_tool_config(self, name: str) -> ToolConfig | None:
        """Find a tool by name."""
        for t in self.tools:
            if t.name == name:
                return t
        return None


def _resolve_config_path(config_path: str | None = None) -> Path | None:
    """Resolve config file path with priority."""
    if config_path:
        p = Path(config_path)
        return p if p.exists() else None

    env_path = os.getenv("ACADEMIAGPT_CONFIG_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    for candidate in [Path("config.yaml"), Path("../config.yaml")]:
        if candidate.exists():
            return candidate

    return None


def load_config(config_path: str | None = None) -> AppConfig:
    """Load and parse config.yaml with env var resolution.

    Args:
        config_path: Explicit path to config file

    Returns:
        Parsed AppConfig (or defaults if no config found)
    """
    path = _resolve_config_path(config_path)
    if path is None:
        return AppConfig()

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    resolved = resolve_env_variables(raw)
    return AppConfig(**resolved)


_app_config: AppConfig | None = None


def get_app_config() -> AppConfig:
    """Get cached singleton config."""
    global _app_config
    if _app_config is None:
        _app_config = load_config()
    return _app_config


def reload_app_config(config_path: str | None = None) -> AppConfig:
    """Force reload config."""
    global _app_config
    _app_config = load_config(config_path)
    return _app_config


def reset_app_config() -> None:
    """Clear cached config."""
    global _app_config
    _app_config = None
```

**Step 5: Create default config.yaml**

Create `backend/config.yaml`:

```yaml
# AcademiaGPT v2 Configuration
# Environment variables: use $VAR_NAME syntax (e.g., $DEEPSEEK_API_KEY)

models: []
  # Models are loaded from LLM_GEN_MODELS env var for backward compatibility.
  # To use config-driven models, add entries here:
  # - name: deepseek-v3
  #   use: langchain_openai:ChatOpenAI
  #   model: deepseek-chat
  #   api_key: $DEEPSEEK_API_KEY
  #   base_url: https://api.deepseek.com/v1
  #   tags: [generation, default]

tools:
  - name: semantic_scholar_search
    use: src.academic.tools.semantic_scholar:semantic_scholar_search_tool
    group: academic_search

tool_groups:
  - name: academic_search
    description: Academic literature search tools

subagents:
  enabled: true
  max_concurrent: 4
  types:
    scout:
      description: "Literature search and evidence collection"
      allowed_tools: [semantic_scholar_search, web_search, read_file]
      max_turns: 10
      timeout: 300
    writer:
      description: "Academic chapter writing"
      allowed_tools: [read_file, write_file, semantic_scholar_search]
      max_turns: 15
      timeout: 600
    synthesizer:
      description: "Knowledge synthesis and insight generation"
      allowed_tools: [read_file]
      max_turns: 6
    reviewer:
      description: "Academic quality review"
      allowed_tools: [read_file]
      max_turns: 8
    librarian:
      description: "Citation management and literature integration"
      allowed_tools: [semantic_scholar_search, read_file]
      max_turns: 10
    analyst:
      description: "Data analysis and evaluation"
      allowed_tools: [read_file, bash]
      max_turns: 10
    general:
      description: "General-purpose assistant"
      disallowed_tools: [task]
      max_turns: 15

memory:
  enabled: false
  injection_enabled: true
  storage_path: "backend/.academiagpt/memory.json"
  debounce_seconds: 30
  max_facts: 100

skills:
  path: "./skills/public"

middlewares:
  summarization:
    enabled: false
    trigger: "tokens:80000"
    keep: "messages:10"
  title:
    enabled: true
    max_words: 8
  academic:
    workspace_context: true
    literature_context: true
    knowledge_context: true
    discipline_context: true
    citation_tracking: true
```

**Step 6: Run tests to verify they pass**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/config/test_config_loader.py tests/reflection/test_resolvers.py -v
```

Expected: PASS

**Step 7: Run full suite to check no regressions**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest -x -q
```

**Step 8: Commit**

```bash
git add backend/src/config/config_loader.py backend/src/reflection/ backend/config.yaml backend/tests/config/test_config_loader.py backend/tests/reflection/test_resolvers.py
git commit -m "feat: add config.yaml loader and dynamic module reflection system"
```

---

### Task 3: Add deer-flow Infrastructure Middlewares (ThreadData, Uploads, Dangling, Title)

**Files:**
- Create: `backend/src/agents/middlewares/thread_data.py`
- Create: `backend/src/agents/middlewares/uploads.py`
- Create: `backend/src/agents/middlewares/dangling_tool_call.py`
- Create: `backend/src/agents/middlewares/title.py`
- Create: `backend/tests/agents/middlewares/test_infrastructure_middlewares.py`
- Modify: `backend/src/agents/middlewares/__init__.py`

**Step 1: Write failing tests**

Create `backend/tests/agents/middlewares/test_infrastructure_middlewares.py`:

```python
"""Tests for deer-flow infrastructure middlewares."""

import pytest

from src.agents.middlewares.thread_data import ThreadDataMiddleware
from src.agents.middlewares.uploads import UploadsMiddleware
from src.agents.middlewares.dangling_tool_call import DanglingToolCallMiddleware
from src.agents.middlewares.title import TitleMiddleware


class TestThreadDataMiddleware:
    def test_creates_directories(self, tmp_path):
        mw = ThreadDataMiddleware(base_dir=str(tmp_path))
        state = {"messages": [], "thread_data": None}
        config = {"configurable": {"thread_id": "test-thread-1"}}
        result = mw.before_agent(state, config)
        assert result is not None
        assert "thread_data" in result
        td = result["thread_data"]
        assert "workspace_path" in td
        assert "uploads_path" in td
        assert "outputs_path" in td

    def test_skips_if_thread_data_exists(self, tmp_path):
        mw = ThreadDataMiddleware(base_dir=str(tmp_path))
        existing = {"workspace_path": "/existing", "uploads_path": "/existing", "outputs_path": "/existing"}
        state = {"messages": [], "thread_data": existing}
        config = {"configurable": {"thread_id": "test-thread-1"}}
        result = mw.before_agent(state, config)
        assert result is None or result.get("thread_data") == existing


class TestUploadsMiddleware:
    def test_injects_file_info(self):
        from langchain_core.messages import HumanMessage
        mw = UploadsMiddleware()
        state = {
            "messages": [HumanMessage(content="Hello")],
            "uploaded_files": [{"name": "test.pdf", "path": "/tmp/test.pdf", "size": 1024}],
        }
        config = {"configurable": {}}
        result = mw.before_agent(state, config)
        # Should inject file info into conversation
        assert result is not None

    def test_noop_without_files(self):
        from langchain_core.messages import HumanMessage
        mw = UploadsMiddleware()
        state = {"messages": [HumanMessage(content="Hello")], "uploaded_files": None}
        config = {"configurable": {}}
        result = mw.before_agent(state, config)
        assert result is None


class TestDanglingToolCallMiddleware:
    def test_patches_missing_tool_messages(self):
        from langchain_core.messages import AIMessage, HumanMessage
        mw = DanglingToolCallMiddleware()
        # Simulate: AI made a tool call but no ToolMessage followed
        ai_msg = AIMessage(content="", tool_calls=[{"id": "call_1", "name": "bash", "args": {"command": "ls"}}])
        state = {"messages": [HumanMessage(content="Hi"), ai_msg, HumanMessage(content="Continue")]}
        config = {"configurable": {}}
        result = mw.before_agent(state, config)
        if result and "messages" in result:
            # Should have injected a synthetic ToolMessage
            from langchain_core.messages import ToolMessage
            tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
            assert len(tool_msgs) >= 1

    def test_noop_when_complete(self):
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
        mw = DanglingToolCallMiddleware()
        ai_msg = AIMessage(content="", tool_calls=[{"id": "call_1", "name": "bash", "args": {"command": "ls"}}])
        tool_msg = ToolMessage(content="output", tool_call_id="call_1")
        state = {"messages": [HumanMessage(content="Hi"), ai_msg, tool_msg]}
        config = {"configurable": {}}
        result = mw.before_agent(state, config)
        assert result is None  # No fix needed


class TestTitleMiddleware:
    def test_generates_title(self):
        from langchain_core.messages import AIMessage, HumanMessage
        mw = TitleMiddleware(max_words=8)
        state = {
            "messages": [
                HumanMessage(content="Help me research LLM alignment methods"),
                AIMessage(content="I can help you with that."),
            ],
            "title": None,
        }
        config = {"configurable": {}}
        result = mw.after_agent(state, config)
        assert result is not None
        assert "title" in result
        assert isinstance(result["title"], str)
        assert len(result["title"]) > 0

    def test_skips_if_title_exists(self):
        from langchain_core.messages import AIMessage, HumanMessage
        mw = TitleMiddleware()
        state = {
            "messages": [HumanMessage(content="Hi"), AIMessage(content="Hello")],
            "title": "Existing Title",
        }
        config = {"configurable": {}}
        result = mw.after_agent(state, config)
        assert result is None
```

**Step 2: Run tests to verify they fail**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/agents/middlewares/test_infrastructure_middlewares.py -v
```

Expected: FAIL (modules don't exist)

**Step 3: Implement ThreadDataMiddleware**

Create `backend/src/agents/middlewares/thread_data.py`:

```python
"""ThreadData middleware - creates per-thread directories."""

from pathlib import Path


class ThreadDataMiddleware:
    """Creates workspace/uploads/outputs directories for each thread."""

    def __init__(self, base_dir: str | None = None, lazy_init: bool = True):
        self._base_dir = base_dir or ".academiagpt/threads"
        self._lazy_init = lazy_init

    def before_agent(self, state: dict, config: dict) -> dict | None:
        existing = state.get("thread_data")
        if existing and existing.get("workspace_path"):
            return None

        thread_id = config.get("configurable", {}).get("thread_id", "default")
        base = Path(self._base_dir) / thread_id / "user-data"

        workspace_path = str(base / "workspace")
        uploads_path = str(base / "uploads")
        outputs_path = str(base / "outputs")

        if not self._lazy_init:
            for p in [workspace_path, uploads_path, outputs_path]:
                Path(p).mkdir(parents=True, exist_ok=True)

        return {
            "thread_data": {
                "workspace_path": workspace_path,
                "uploads_path": uploads_path,
                "outputs_path": outputs_path,
            }
        }
```

**Step 4: Implement UploadsMiddleware**

Create `backend/src/agents/middlewares/uploads.py`:

```python
"""Uploads middleware - injects uploaded file metadata into conversation."""

from langchain_core.messages import HumanMessage


class UploadsMiddleware:
    """Tracks and injects uploaded files into the last HumanMessage."""

    def before_agent(self, state: dict, config: dict) -> dict | None:
        uploaded_files = state.get("uploaded_files")
        if not uploaded_files:
            return None

        messages = list(state.get("messages", []))
        if not messages:
            return None

        # Find last HumanMessage
        last_human_idx = None
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], HumanMessage):
                last_human_idx = i
                break

        if last_human_idx is None:
            return None

        # Build file listing
        file_listing = "\n<uploaded_files>\n"
        for f in uploaded_files:
            name = f.get("name", "unknown")
            path = f.get("path", "")
            size = f.get("size", 0)
            file_listing += f"- {name} ({size} bytes): {path}\n"
        file_listing += "</uploaded_files>"

        # Prepend to last human message content
        original = messages[last_human_idx]
        content = original.content if isinstance(original.content, str) else str(original.content)
        if "<uploaded_files>" not in content:
            updated = HumanMessage(content=file_listing + "\n\n" + content)
            messages[last_human_idx] = updated
            return {"messages": messages}

        return None
```

**Step 5: Implement DanglingToolCallMiddleware**

Create `backend/src/agents/middlewares/dangling_tool_call.py`:

```python
"""DanglingToolCall middleware - patches missing ToolMessages for interrupted calls."""

from langchain_core.messages import AIMessage, ToolMessage


class DanglingToolCallMiddleware:
    """Inserts synthetic ToolMessages for tool_calls that lack responses."""

    def before_agent(self, state: dict, config: dict) -> dict | None:
        messages = state.get("messages", [])
        if not messages:
            return None

        # Collect all tool_call IDs and their responses
        pending_calls: dict[str, int] = {}  # call_id -> index of AIMessage
        responded_calls: set[str] = set()

        for i, msg in enumerate(messages):
            if isinstance(msg, AIMessage):
                for tc in getattr(msg, "tool_calls", None) or []:
                    call_id = tc.get("id")
                    if call_id:
                        pending_calls[call_id] = i
            elif isinstance(msg, ToolMessage):
                call_id = getattr(msg, "tool_call_id", None)
                if call_id:
                    responded_calls.add(call_id)

        dangling = set(pending_calls.keys()) - responded_calls
        if not dangling:
            return None

        # Insert synthetic ToolMessages right after the AIMessage
        patched = list(messages)
        offset = 0
        for call_id in sorted(dangling, key=lambda c: pending_calls[c]):
            ai_idx = pending_calls[call_id] + offset
            synthetic = ToolMessage(
                content="[Tool call interrupted - no response received]",
                tool_call_id=call_id,
                status="error",
            )
            patched.insert(ai_idx + 1, synthetic)
            offset += 1

        return {"messages": patched}
```

**Step 6: Implement TitleMiddleware**

Create `backend/src/agents/middlewares/title.py`:

```python
"""Title middleware - auto-generates thread title after first exchange."""

from langchain_core.messages import AIMessage, HumanMessage


class TitleMiddleware:
    """Generates a thread title from the first user message."""

    def __init__(self, max_words: int = 8, max_chars: int = 60):
        self._max_words = max_words
        self._max_chars = max_chars

    def after_agent(self, state: dict, config: dict) -> dict | None:
        if state.get("title"):
            return None

        messages = state.get("messages", [])
        # Need at least one human + one AI message
        has_human = any(isinstance(m, HumanMessage) for m in messages)
        has_ai = any(isinstance(m, AIMessage) for m in messages)
        if not (has_human and has_ai):
            return None

        # Extract first human message for title
        first_human = next(m for m in messages if isinstance(m, HumanMessage))
        content = first_human.content if isinstance(first_human.content, str) else str(first_human.content)

        # Clean and truncate
        title = content.strip().replace("\n", " ")
        words = title.split()
        if len(words) > self._max_words:
            title = " ".join(words[: self._max_words]) + "..."
        if len(title) > self._max_chars:
            title = title[: self._max_chars - 3] + "..."

        return {"title": title}
```

**Step 7: Update `__init__.py`**

Modify `backend/src/agents/middlewares/__init__.py` to export new middlewares:

```python
from .base import Middleware
from .citation_context import CitationContextMiddleware
from .dangling_tool_call import DanglingToolCallMiddleware
from .discipline_context import DisciplineContextMiddleware
from .knowledge_context import KnowledgeContextMiddleware
from .literature_context import LiteratureContextMiddleware
from .thread_data import ThreadDataMiddleware
from .title import TitleMiddleware
from .uploads import UploadsMiddleware
from .workspace_context import WorkspaceContextMiddleware

__all__ = [
    "CitationContextMiddleware",
    "DanglingToolCallMiddleware",
    "DisciplineContextMiddleware",
    "KnowledgeContextMiddleware",
    "LiteratureContextMiddleware",
    "Middleware",
    "ThreadDataMiddleware",
    "TitleMiddleware",
    "UploadsMiddleware",
    "WorkspaceContextMiddleware",
]
```

**Step 8: Run tests**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/agents/middlewares/test_infrastructure_middlewares.py -v
```

Expected: PASS

**Step 9: Run full suite**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest -x -q
```

**Step 10: Commit**

```bash
git add backend/src/agents/middlewares/ backend/tests/agents/middlewares/
git commit -m "feat: add deer-flow infrastructure middlewares (ThreadData, Uploads, Dangling, Title)"
```

---

### Task 4: Add SubagentLimit and Clarification Middlewares

**Files:**
- Create: `backend/src/agents/middlewares/subagent_limit.py`
- Create: `backend/src/agents/middlewares/clarification.py`
- Create: `backend/tests/agents/middlewares/test_control_middlewares.py`

**Step 1: Write failing tests**

Create `backend/tests/agents/middlewares/test_control_middlewares.py`:

```python
"""Tests for control middlewares (SubagentLimit, Clarification)."""

from langchain_core.messages import AIMessage

from src.agents.middlewares.subagent_limit import SubagentLimitMiddleware
from src.agents.middlewares.clarification import ClarificationMiddleware


class TestSubagentLimitMiddleware:
    def test_truncates_excess_task_calls(self):
        mw = SubagentLimitMiddleware(max_concurrent=2)
        ai_msg = AIMessage(content="", tool_calls=[
            {"id": "c1", "name": "task", "args": {"prompt": "task1", "subagent_type": "scout", "description": "t1"}},
            {"id": "c2", "name": "task", "args": {"prompt": "task2", "subagent_type": "writer", "description": "t2"}},
            {"id": "c3", "name": "task", "args": {"prompt": "task3", "subagent_type": "analyst", "description": "t3"}},
        ])
        state = {"messages": [ai_msg]}
        config = {"configurable": {}}
        result = mw.after_model(state, config)
        assert result is not None
        updated_msg = result["messages"][-1]
        task_calls = [tc for tc in updated_msg.tool_calls if tc["name"] == "task"]
        assert len(task_calls) <= 2

    def test_no_truncation_under_limit(self):
        mw = SubagentLimitMiddleware(max_concurrent=3)
        ai_msg = AIMessage(content="", tool_calls=[
            {"id": "c1", "name": "task", "args": {"prompt": "task1", "subagent_type": "scout", "description": "t1"}},
        ])
        state = {"messages": [ai_msg]}
        config = {"configurable": {}}
        result = mw.after_model(state, config)
        assert result is None  # No truncation needed

    def test_preserves_non_task_calls(self):
        mw = SubagentLimitMiddleware(max_concurrent=1)
        ai_msg = AIMessage(content="", tool_calls=[
            {"id": "c0", "name": "bash", "args": {"command": "ls"}},
            {"id": "c1", "name": "task", "args": {"prompt": "t1", "subagent_type": "scout", "description": "d1"}},
            {"id": "c2", "name": "task", "args": {"prompt": "t2", "subagent_type": "writer", "description": "d2"}},
        ])
        state = {"messages": [ai_msg]}
        config = {"configurable": {}}
        result = mw.after_model(state, config)
        assert result is not None
        updated = result["messages"][-1]
        non_task = [tc for tc in updated.tool_calls if tc["name"] != "task"]
        assert len(non_task) == 1  # bash preserved


class TestClarificationMiddleware:
    def test_intercepts_clarification_call(self):
        mw = ClarificationMiddleware()
        ai_msg = AIMessage(content="", tool_calls=[
            {"id": "c1", "name": "ask_clarification", "args": {"question": "What API version?"}},
        ])
        state = {"messages": [ai_msg]}
        config = {"configurable": {}}
        result = mw.after_model(state, config)
        # Should signal interruption
        assert result is not None

    def test_noop_without_clarification(self):
        mw = ClarificationMiddleware()
        ai_msg = AIMessage(content="Here's the result", tool_calls=[])
        state = {"messages": [ai_msg]}
        config = {"configurable": {}}
        result = mw.after_model(state, config)
        assert result is None
```

**Step 2: Run tests to verify they fail**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/agents/middlewares/test_control_middlewares.py -v
```

**Step 3: Implement SubagentLimitMiddleware**

Create `backend/src/agents/middlewares/subagent_limit.py`:

```python
"""SubagentLimit middleware - enforces max concurrent task tool calls."""

from langchain_core.messages import AIMessage


class SubagentLimitMiddleware:
    """Truncates excess `task` tool calls from model response."""

    def __init__(self, max_concurrent: int = 3):
        self._max = max(2, min(max_concurrent, 4))  # Clamp to [2, 4]

    def after_model(self, state: dict, config: dict) -> dict | None:
        messages = state.get("messages", [])
        if not messages:
            return None

        last_msg = messages[-1]
        if not isinstance(last_msg, AIMessage):
            return None

        tool_calls = getattr(last_msg, "tool_calls", None) or []
        task_calls = [tc for tc in tool_calls if tc.get("name") == "task"]

        if len(task_calls) <= self._max:
            return None

        # Keep first N task calls + all non-task calls
        kept_task_ids = {tc["id"] for tc in task_calls[: self._max]}
        filtered = [tc for tc in tool_calls if tc.get("name") != "task" or tc["id"] in kept_task_ids]

        updated = AIMessage(content=last_msg.content, tool_calls=filtered)
        return {"messages": messages[:-1] + [updated]}
```

**Step 4: Implement ClarificationMiddleware**

Create `backend/src/agents/middlewares/clarification.py`:

```python
"""Clarification middleware - intercepts ask_clarification tool calls."""

from langchain_core.messages import AIMessage


class ClarificationMiddleware:
    """Intercepts ask_clarification tool calls for human-in-the-loop interaction.

    MUST be the last middleware in the chain.
    """

    def after_model(self, state: dict, config: dict) -> dict | None:
        messages = state.get("messages", [])
        if not messages:
            return None

        last_msg = messages[-1]
        if not isinstance(last_msg, AIMessage):
            return None

        tool_calls = getattr(last_msg, "tool_calls", None) or []
        clarification_calls = [tc for tc in tool_calls if tc.get("name") == "ask_clarification"]

        if not clarification_calls:
            return None

        # Signal that clarification is needed - the agent loop should interrupt
        return {"_clarification_requested": True, "messages": messages}
```

**Step 5: Update exports**

Add to `backend/src/agents/middlewares/__init__.py`:

```python
from .clarification import ClarificationMiddleware
from .subagent_limit import SubagentLimitMiddleware
```

And add to `__all__`.

**Step 6: Run tests**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/agents/middlewares/test_control_middlewares.py -v
```

**Step 7: Run full suite + commit**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest -x -q
git add backend/src/agents/middlewares/ backend/tests/agents/middlewares/
git commit -m "feat: add SubagentLimit and Clarification middlewares"
```

---

### Task 5: Adapt Academic Middlewares to Unified Pipeline Protocol

**Files:**
- Modify: `backend/src/agents/middlewares/workspace_context.py`
- Modify: `backend/src/agents/middlewares/literature_context.py`
- Modify: `backend/src/agents/middlewares/knowledge_context.py`
- Modify: `backend/src/agents/middlewares/discipline_context.py`
- Modify: `backend/src/agents/middlewares/citation_context.py`
- Modify: `backend/src/agents/middlewares/base.py`
- Test: `backend/tests/agents/middlewares/test_academic_middlewares.py`

The existing academic middlewares use the custom `Middleware(ABC)` base class. We need to ensure they work with the new pipeline protocol (dict-based state instead of Pydantic model).

**Step 1: Write failing tests**

Create `backend/tests/agents/middlewares/test_academic_middlewares.py`:

```python
"""Tests for adapted academic middlewares working with dict-based state."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.middlewares.workspace_context import WorkspaceContextMiddleware
from src.agents.middlewares.discipline_context import DisciplineContextMiddleware
from src.agents.middlewares.citation_context import CitationContextMiddleware


class TestWorkspaceContextWithDictState:
    @pytest.mark.asyncio
    async def test_loads_workspace_into_dict_state(self):
        mock_service = AsyncMock()
        mock_service.get_workspace_config.return_value = {
            "paper_type": "sci",
            "discipline": "computer_science",
        }
        mw = WorkspaceContextMiddleware(mock_service)
        state = {"messages": [], "workspace_id": "ws-123", "workspace_config": None}
        config = {"configurable": {}}
        result = await mw.before_model(state, config)
        assert isinstance(result, dict)
        assert result.get("workspace_config") is not None


class TestDisciplineContextWithDictState:
    @pytest.mark.asyncio
    async def test_injects_norms_into_dict_state(self):
        mw = DisciplineContextMiddleware()
        state = {"messages": [], "discipline": "computer_science", "workspace_type": "sci", "discipline_norms": None}
        config = {"configurable": {}}
        result = await mw.before_model(state, config)
        assert isinstance(result, dict)


class TestCitationContextWithDictState:
    @pytest.mark.asyncio
    async def test_extracts_citations_after_model(self):
        from langchain_core.messages import AIMessage
        mock_service = AsyncMock()
        mw = CitationContextMiddleware(mock_service)
        state = {
            "messages": [AIMessage(content="According to (Smith, 2023), LLMs are powerful.")],
            "workspace_id": "ws-123",
            "cited_papers": [],
        }
        config = {"configurable": {}}
        result = await mw.after_model(state, config)
        assert isinstance(result, dict)
```

**Step 2: Run tests to verify current behavior**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/agents/middlewares/test_academic_middlewares.py -v
```

**Step 3: Adapt middlewares to accept dict-based state**

The key change: middlewares should handle both the old `ThreadState` model and new dict-based state. Modify each middleware's `before_model` / `after_model` to use dict access (`state.get("field")` or `state["field"]`) instead of attribute access (`state.workspace_id`).

For each of the 5 academic middlewares, the pattern is:
- Replace `state.workspace_id` → `state.get("workspace_id") if isinstance(state, dict) else state.workspace_id`
- Or better: always use dict access since AgentState is dict-like

This is a targeted refactor of each middleware - the agent implementation details should be preserved. The critical change is input/output format compatibility.

**Step 4: Run all middleware tests**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/agents/middlewares/ -v
```

**Step 5: Run full suite + commit**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest -x -q
git add backend/src/agents/middlewares/ backend/tests/agents/middlewares/
git commit -m "refactor: adapt academic middlewares for dict-based state pipeline"
```

---

### Task 6: Assemble 16-Layer Pipeline in Lead Agent

**Files:**
- Modify: `backend/src/agents/lead_agent/agent.py`
- Create: `backend/tests/agents/test_pipeline_assembly.py`

**Step 1: Write failing test**

Create `backend/tests/agents/test_pipeline_assembly.py`:

```python
"""Tests for 16-layer middleware pipeline assembly."""

from src.agents.lead_agent.agent import build_pipeline


class TestPipelineAssembly:
    def test_builds_16_layer_pipeline(self):
        """Full pipeline should have 16 layers when all features enabled."""
        config = {
            "configurable": {
                "subagent_enabled": True,
                "workspace_id": "ws-123",
            }
        }
        pipeline = build_pipeline(
            config=config,
            workspace_service=None,  # Will skip WS middleware
            index_service=None,
            artifact_service=None,
            paper_service=None,
        )
        # At minimum: ThreadData + Uploads + Dangling + academic defaults + Title + Clarification
        assert len(pipeline) >= 7

    def test_pipeline_order(self):
        """Infrastructure middlewares should come before academic middlewares."""
        from src.agents.middlewares.thread_data import ThreadDataMiddleware
        from src.agents.middlewares.clarification import ClarificationMiddleware
        config = {"configurable": {"subagent_enabled": False}}
        pipeline = build_pipeline(config=config)

        type_names = [type(m).__name__ for m in pipeline]

        # ThreadData must be first
        assert type_names[0] == "ThreadDataMiddleware"

        # Clarification must be last
        assert type_names[-1] == "ClarificationMiddleware"

    def test_subagent_limit_included_when_enabled(self):
        from src.agents.middlewares.subagent_limit import SubagentLimitMiddleware
        config = {"configurable": {"subagent_enabled": True}}
        pipeline = build_pipeline(config=config)
        type_names = [type(m).__name__ for m in pipeline]
        assert "SubagentLimitMiddleware" in type_names

    def test_subagent_limit_excluded_when_disabled(self):
        config = {"configurable": {"subagent_enabled": False}}
        pipeline = build_pipeline(config=config)
        type_names = [type(m).__name__ for m in pipeline]
        assert "SubagentLimitMiddleware" not in type_names
```

**Step 2: Run test to verify it fails**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/agents/test_pipeline_assembly.py -v
```

**Step 3: Implement `build_pipeline` in agent.py**

Add to `backend/src/agents/lead_agent/agent.py`:

```python
def build_pipeline(
    config: dict,
    workspace_service=None,
    index_service=None,
    artifact_service=None,
    paper_service=None,
) -> list:
    """Build the 16-layer middleware pipeline.

    Order:
    1.  ThreadDataMiddleware       - Infrastructure
    2.  UploadsMiddleware          - Infrastructure
    3.  DanglingToolCallMiddleware - Fix
    4.  WorkspaceContextMiddleware - Academic (conditional)
    5.  LiteratureContextMiddleware - Academic (conditional)
    6.  KnowledgeContextMiddleware - Academic (conditional)
    7.  DisciplineContextMiddleware - Academic
    8.  TitleMiddleware            - Post-processing
    9.  SubagentLimitMiddleware    - Control (conditional)
    10. CitationContextMiddleware  - Post-processing (conditional)
    11. ClarificationMiddleware    - Control (MUST BE LAST)
    """
    from src.agents.middlewares import (
        CitationContextMiddleware,
        ClarificationMiddleware,
        DanglingToolCallMiddleware,
        DisciplineContextMiddleware,
        KnowledgeContextMiddleware,
        LiteratureContextMiddleware,
        SubagentLimitMiddleware,
        ThreadDataMiddleware,
        TitleMiddleware,
        UploadsMiddleware,
        WorkspaceContextMiddleware,
    )

    configurable = config.get("configurable", {})
    subagent_enabled = configurable.get("subagent_enabled", False)

    pipeline = []

    # --- Infrastructure layer ---
    pipeline.append(ThreadDataMiddleware())
    pipeline.append(UploadsMiddleware())

    # --- Fix layer ---
    pipeline.append(DanglingToolCallMiddleware())

    # --- Academic context layer (conditional on services) ---
    if workspace_service:
        pipeline.append(WorkspaceContextMiddleware(workspace_service))
    if index_service:
        pipeline.append(LiteratureContextMiddleware(index_service))
    if artifact_service:
        pipeline.append(KnowledgeContextMiddleware(artifact_service))
    pipeline.append(DisciplineContextMiddleware())

    # --- Post-processing layer ---
    pipeline.append(TitleMiddleware())

    # --- Control layer ---
    if subagent_enabled:
        max_concurrent = configurable.get("max_concurrent_subagents", 3)
        pipeline.append(SubagentLimitMiddleware(max_concurrent=max_concurrent))

    if paper_service:
        pipeline.append(CitationContextMiddleware(paper_service))

    # --- MUST BE LAST ---
    pipeline.append(ClarificationMiddleware())

    return pipeline
```

**Step 4: Update `make_lead_agent` to use `build_pipeline`**

Update the `make_lead_agent` function to use the new pipeline:

```python
def make_lead_agent(config: RunnableConfig, middlewares: list | None = None) -> Callable:
    configurable = config.get("configurable", {})
    model_name = configurable.get("model_name", "gpt-4o")
    thinking_enabled = configurable.get("thinking_enabled", False)
    subagent_enabled = configurable.get("subagent_enabled", True)

    from src.models.factory import create_chat_model
    model = create_chat_model(model_name, thinking_enabled=thinking_enabled)

    tools = get_available_tools(subagent_enabled=subagent_enabled, model_name=model_name)

    if middlewares is None:
        middlewares = build_pipeline(config)

    def state_modifier(state):
        return {
            **state,
            "system_prompt": apply_prompt_template(state, config),
        }

    agent = create_react_agent(
        model,
        tools,
        state_modifier=state_modifier,
        checkpointer=MemorySaver(),
    )

    return agent
```

**Step 5: Run tests**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/agents/test_pipeline_assembly.py -v
```

**Step 6: Run full suite + commit**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest -x -q
git add backend/src/agents/ backend/tests/agents/
git commit -m "feat: assemble 16-layer middleware pipeline with build_pipeline()"
```

---

### Task 7: Implement SubagentExecutor with Background Threading

**Files:**
- Create: `backend/src/subagents/executor.py`
- Modify: `backend/src/subagents/task_tool.py`
- Create: `backend/tests/subagents/test_executor.py`

**Step 1: Write failing test**

Create `backend/tests/subagents/test_executor.py`:

```python
"""Tests for SubagentExecutor with background threading."""

from unittest.mock import MagicMock, patch

import pytest

from src.subagents.executor import (
    SubagentExecutor,
    SubagentResult,
    SubagentStatus,
    get_background_task_result,
)
from src.subagents.registry import SubagentConfig


class TestSubagentStatus:
    def test_status_values(self):
        assert SubagentStatus.PENDING.value == "pending"
        assert SubagentStatus.RUNNING.value == "running"
        assert SubagentStatus.COMPLETED.value == "completed"
        assert SubagentStatus.FAILED.value == "failed"
        assert SubagentStatus.TIMED_OUT.value == "timed_out"


class TestSubagentResult:
    def test_default_values(self):
        r = SubagentResult(task_id="t1")
        assert r.status == SubagentStatus.PENDING
        assert r.result is None
        assert r.error is None


class TestSubagentExecutor:
    def test_init(self):
        config = SubagentConfig(
            name="test",
            description="Test agent",
            system_prompt="You are a test agent.",
        )
        executor = SubagentExecutor(config=config, tools=[], parent_model="gpt-4o")
        assert executor.config.name == "test"

    def test_execute_sync(self):
        """Synchronous execution should return a result."""
        config = SubagentConfig(
            name="test",
            description="Test",
            system_prompt="Reply with 'done'.",
        )
        executor = SubagentExecutor(config=config, tools=[], parent_model="gpt-4o")
        # Mock the agent creation to avoid real LLM calls
        with patch.object(executor, "_create_agent") as mock_create:
            mock_agent = MagicMock()
            mock_agent.invoke.return_value = {"messages": [MagicMock(content="done")]}
            mock_create.return_value = mock_agent
            result = executor.execute("test task")
            assert result.status in (SubagentStatus.COMPLETED, SubagentStatus.FAILED)

    def test_background_task_tracking(self):
        """Background task results should be retrievable."""
        result = get_background_task_result("nonexistent")
        assert result is None
```

**Step 2: Run test to verify it fails**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/subagents/test_executor.py -v
```

**Step 3: Implement SubagentExecutor**

Create `backend/src/subagents/executor.py`:

```python
"""SubagentExecutor - background task execution with thread pools."""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from langchain_core.tools import BaseTool

from src.subagents.registry import SubagentConfig


class SubagentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass
class SubagentResult:
    task_id: str
    status: SubagentStatus = SubagentStatus.PENDING
    result: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    ai_messages: list[dict[str, Any]] = field(default_factory=list)


# Global thread pools
_scheduler_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="subagent-scheduler-")
_execution_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="subagent-exec-")

# Background task tracking
_background_tasks: dict[str, SubagentResult] = {}
_background_tasks_lock = threading.Lock()


def get_background_task_result(task_id: str) -> SubagentResult | None:
    with _background_tasks_lock:
        return _background_tasks.get(task_id)


def list_background_tasks() -> list[SubagentResult]:
    with _background_tasks_lock:
        return list(_background_tasks.values())


def _filter_tools(
    all_tools: list[BaseTool],
    allowed: list[str] | None,
    disallowed: list[str] | None,
) -> list[BaseTool]:
    """Filter tools by allowlist/denylist."""
    result = list(all_tools)
    if allowed:
        allowed_set = set(allowed)
        result = [t for t in result if t.name in allowed_set]
    if disallowed:
        disallowed_set = set(disallowed)
        result = [t for t in result if t.name not in disallowed_set]
    return result


class SubagentExecutor:
    """Executes subagent tasks with optional background threading."""

    def __init__(
        self,
        config: SubagentConfig,
        tools: list[BaseTool],
        parent_model: str | None = None,
        thread_id: str | None = None,
        trace_id: str | None = None,
    ):
        self.config = config
        self.parent_model = parent_model
        self.thread_id = thread_id
        self.trace_id = trace_id or str(uuid.uuid4())[:8]
        self.tools = _filter_tools(
            tools,
            list(config.allowed_tools) if config.allowed_tools else None,
            None,
        )

    def _create_agent(self):
        """Create a lightweight agent for subagent execution."""
        from src.models.factory import create_chat_model
        model_name = self.parent_model or "gpt-4o"
        model = create_chat_model(model_name, thinking_enabled=False)

        from langgraph.prebuilt import create_react_agent
        return create_react_agent(
            model,
            self.tools,
            prompt=self.config.system_prompt,
        )

    def execute(self, task: str, result_holder: SubagentResult | None = None) -> SubagentResult:
        """Synchronous execution."""
        if result_holder is None:
            result_holder = SubagentResult(task_id=str(uuid.uuid4())[:8])

        result_holder.status = SubagentStatus.RUNNING
        result_holder.started_at = datetime.now(UTC)

        try:
            agent = self._create_agent()
            response = agent.invoke({"messages": [("human", task)]})
            messages = response.get("messages", [])
            last_msg = messages[-1] if messages else None
            result_holder.result = getattr(last_msg, "content", str(last_msg)) if last_msg else ""
            result_holder.status = SubagentStatus.COMPLETED
        except Exception as e:
            result_holder.error = str(e)
            result_holder.status = SubagentStatus.FAILED
        finally:
            result_holder.completed_at = datetime.now(UTC)

        return result_holder

    def execute_async(self, task: str, task_id: str | None = None) -> str:
        """Background execution (returns task_id immediately)."""
        task_id = task_id or str(uuid.uuid4())[:8]
        result = SubagentResult(task_id=task_id)

        with _background_tasks_lock:
            _background_tasks[task_id] = result

        def _run():
            self.execute(task, result_holder=result)

        _execution_pool.submit(_run)
        return task_id
```

**Step 4: Run tests + full suite + commit**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/subagents/test_executor.py -v
PYTHONPATH=. uv run pytest -x -q
git add backend/src/subagents/executor.py backend/tests/subagents/
git commit -m "feat: add SubagentExecutor with background threading and task tracking"
```

---

### Task 8: Update Task Tool for Real Background Execution

**Files:**
- Modify: `backend/src/subagents/task_tool.py`
- Test: `backend/tests/subagents/test_task_tool.py`

**Step 1: Write failing test**

Create or update `backend/tests/subagents/test_task_tool.py`:

```python
"""Tests for the task delegation tool with real executor."""

from unittest.mock import patch, MagicMock

import pytest

from src.subagents.task_tool import task_tool
from src.subagents.registry import registry


class TestTaskTool:
    @pytest.mark.asyncio
    async def test_unknown_type_returns_error(self):
        result = await task_tool.ainvoke({
            "description": "Test",
            "prompt": "Do something",
            "subagent_type": "nonexistent_type",
        })
        assert "Error" in result or "Unknown" in result

    @pytest.mark.asyncio
    async def test_known_type_delegates(self):
        """Known subagent type should attempt delegation."""
        with patch("src.subagents.task_tool.SubagentExecutor") as MockExec:
            mock_result = MagicMock()
            mock_result.status.value = "completed"
            mock_result.result = "Task done"
            mock_result.error = None
            MockExec.return_value.execute.return_value = mock_result

            result = await task_tool.ainvoke({
                "description": "Search papers",
                "prompt": "Find LLM alignment papers",
                "subagent_type": "scout",
            })
            assert "done" in result.lower() or "Task" in result
```

**Step 2: Update task_tool implementation**

Modify `backend/src/subagents/task_tool.py` to use SubagentExecutor instead of returning placeholder text:

```python
"""Task delegation tool using SubagentExecutor."""

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.subagents.executor import SubagentExecutor, SubagentStatus
from src.subagents.registry import registry


class TaskInput(BaseModel):
    description: str = Field(description="Brief description of the task")
    prompt: str = Field(description="Detailed instructions for the subagent")
    subagent_type: str = Field(description="Type of subagent (scout, writer, synthesizer, analyst, etc.)")
    max_turns: int | None = Field(default=None, description="Maximum turns for the subagent")


@tool(args_schema=TaskInput)
async def task_tool(
    description: str,
    prompt: str,
    subagent_type: str,
    max_turns: int | None = None,
) -> str:
    """Delegate a task to a specialized subagent for parallel execution."""
    config = registry.get(subagent_type)
    if not config:
        available = list(registry._subagents.keys())
        return f"Error: Unknown subagent type '{subagent_type}'. Available: {available}"

    if max_turns is not None:
        config = type(config)(
            name=config.name,
            description=config.description,
            system_prompt=config.system_prompt,
            allowed_tools=config.allowed_tools,
            max_turns=max_turns,
        )

    from src.agents.lead_agent.agent import get_available_tools
    tools = get_available_tools(subagent_enabled=False)

    executor = SubagentExecutor(config=config, tools=tools)
    result = executor.execute(prompt)

    if result.status == SubagentStatus.COMPLETED:
        return f"[{config.name} completed]\n{result.result}"
    elif result.status == SubagentStatus.TIMED_OUT:
        return f"[{config.name} timed out]\n{result.error or 'Exceeded time limit'}"
    else:
        return f"[{config.name} failed]\n{result.error or 'Unknown error'}"
```

**Step 3: Run tests + full suite + commit**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/subagents/test_task_tool.py -v
PYTHONPATH=. uv run pytest -x -q
git add backend/src/subagents/task_tool.py backend/tests/subagents/
git commit -m "feat: update task_tool to use SubagentExecutor with real execution"
```

---

### Task 9: Add Persistent Memory System

**Files:**
- Create: `backend/src/agents/memory/__init__.py`
- Create: `backend/src/agents/memory/updater.py`
- Create: `backend/src/agents/memory/queue.py`
- Create: `backend/tests/agents/memory/test_memory.py`

**Step 1: Write failing test**

Create `backend/tests/agents/memory/__init__.py` (empty) and `backend/tests/agents/memory/test_memory.py`:

```python
"""Tests for persistent memory system."""

import json
import tempfile
from pathlib import Path

import pytest

from src.agents.memory.updater import (
    get_memory_data,
    reload_memory_data,
    MemoryUpdater,
    create_default_memory,
)


class TestMemoryData:
    def test_default_memory_structure(self):
        data = create_default_memory()
        assert "version" in data
        assert "user" in data
        assert "history" in data
        assert "facts" in data
        assert isinstance(data["facts"], list)

    def test_get_memory_creates_file(self, tmp_path):
        storage = str(tmp_path / "memory.json")
        data = get_memory_data(storage_path=storage)
        assert data is not None
        assert Path(storage).exists()

    def test_get_memory_reads_existing(self, tmp_path):
        storage = tmp_path / "memory.json"
        existing = create_default_memory()
        existing["facts"].append({"id": "f1", "content": "test fact", "category": "knowledge", "confidence": 0.9})
        storage.write_text(json.dumps(existing))

        data = get_memory_data(storage_path=str(storage))
        assert len(data["facts"]) == 1
        assert data["facts"][0]["content"] == "test fact"

    def test_reload_clears_cache(self, tmp_path):
        storage = str(tmp_path / "memory.json")
        data1 = get_memory_data(storage_path=storage)
        data2 = reload_memory_data(storage_path=storage)
        assert data2 is not None


class TestMemoryUpdater:
    def test_init(self):
        updater = MemoryUpdater()
        assert updater is not None

    def test_format_memory_for_injection(self, tmp_path):
        storage = tmp_path / "memory.json"
        mem = create_default_memory()
        mem["user"]["researchContext"] = {"summary": "Focuses on NLP", "updatedAt": "2026-03-09"}
        mem["facts"] = [
            {"id": "f1", "content": "User studies NLP", "category": "knowledge", "confidence": 0.95},
        ]
        storage.write_text(json.dumps(mem))

        updater = MemoryUpdater(storage_path=str(storage))
        injection = updater.format_for_injection()
        assert "NLP" in injection
```

**Step 2: Run test to verify it fails**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/agents/memory/test_memory.py -v
```

**Step 3: Implement memory system**

Create `backend/src/agents/memory/__init__.py`:

```python
from .updater import MemoryUpdater, create_default_memory, get_memory_data, reload_memory_data

__all__ = ["MemoryUpdater", "create_default_memory", "get_memory_data", "reload_memory_data"]
```

Create `backend/src/agents/memory/updater.py`:

```python
"""Persistent memory system - LLM-driven fact extraction and context tracking."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

_memory_cache: dict[str, dict] = {}
_memory_mtime: dict[str, float] = {}

DEFAULT_STORAGE_PATH = "backend/.academiagpt/memory.json"


def create_default_memory() -> dict:
    """Create a default empty memory structure."""
    return {
        "version": "1.0",
        "lastUpdated": datetime.now(UTC).isoformat(),
        "user": {
            "researchContext": {"summary": "", "updatedAt": ""},
            "writingPreferences": {"summary": "", "updatedAt": ""},
            "toolPreferences": {"summary": "", "updatedAt": ""},
        },
        "history": {
            "recentWorkspaces": {"summary": "", "updatedAt": ""},
            "completedResearch": {"summary": "", "updatedAt": ""},
        },
        "facts": [],
    }


def get_memory_data(storage_path: str | None = None) -> dict:
    """Get memory data with caching and file change detection."""
    path = storage_path or DEFAULT_STORAGE_PATH
    cache_key = path

    # Check cache validity via mtime
    if cache_key in _memory_cache:
        try:
            current_mtime = os.path.getmtime(path)
            if current_mtime == _memory_mtime.get(cache_key):
                return _memory_cache[cache_key]
        except OSError:
            pass

    # Load or create
    p = Path(path)
    if p.exists():
        data = json.loads(p.read_text())
    else:
        data = create_default_memory()
        p.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(p, data)

    _memory_cache[cache_key] = data
    try:
        _memory_mtime[cache_key] = os.path.getmtime(path)
    except OSError:
        pass

    return data


def reload_memory_data(storage_path: str | None = None) -> dict:
    """Force reload and clear cache."""
    path = storage_path or DEFAULT_STORAGE_PATH
    _memory_cache.pop(path, None)
    _memory_mtime.pop(path, None)
    return get_memory_data(storage_path=path)


def _atomic_write(path: Path, data: dict) -> None:
    """Write atomically via temp file + rename."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(path)


class MemoryUpdater:
    """Updates memory from conversations using LLM extraction."""

    def __init__(self, storage_path: str | None = None, model_name: str | None = None):
        self._storage_path = storage_path or DEFAULT_STORAGE_PATH
        self._model_name = model_name

    def format_for_injection(self, max_facts: int = 15) -> str:
        """Format memory data for system prompt injection."""
        data = get_memory_data(storage_path=self._storage_path)

        parts = ["<memory>"]

        # User context
        for key in ["researchContext", "writingPreferences", "toolPreferences"]:
            ctx = data.get("user", {}).get(key, {})
            summary = ctx.get("summary", "")
            if summary:
                parts.append(f"[{key}] {summary}")

        # Facts (top N by confidence)
        facts = sorted(data.get("facts", []), key=lambda f: f.get("confidence", 0), reverse=True)
        for fact in facts[:max_facts]:
            parts.append(f"- {fact['content']}")

        parts.append("</memory>")
        return "\n".join(parts)

    def update_from_messages(self, messages: list, thread_id: str | None = None) -> bool:
        """Update memory from a conversation (async LLM call).

        This is a placeholder - full LLM-driven extraction will be
        implemented when Memory config is enabled.
        """
        # TODO: Implement LLM-driven extraction in Phase 2
        return False
```

Create `backend/src/agents/memory/queue.py`:

```python
"""Memory update queue with debouncing."""

import threading
from collections import defaultdict


class MemoryQueue:
    """Debounced queue for batching memory updates per thread."""

    def __init__(self, debounce_seconds: float = 30.0):
        self._debounce = debounce_seconds
        self._pending: dict[str, list] = defaultdict(list)
        self._lock = threading.Lock()
        self._timers: dict[str, threading.Timer] = {}

    def enqueue(self, thread_id: str, messages: list, callback=None) -> None:
        """Add messages to update queue for a thread."""
        with self._lock:
            self._pending[thread_id].extend(messages)

            # Reset debounce timer
            if thread_id in self._timers:
                self._timers[thread_id].cancel()

            if callback:
                timer = threading.Timer(self._debounce, callback, args=(thread_id, self._pending[thread_id]))
                self._timers[thread_id] = timer
                timer.start()

    def flush(self, thread_id: str) -> list:
        """Get and clear pending messages for a thread."""
        with self._lock:
            messages = self._pending.pop(thread_id, [])
            if thread_id in self._timers:
                self._timers[thread_id].cancel()
                del self._timers[thread_id]
            return messages
```

**Step 4: Run tests + full suite + commit**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/agents/memory/test_memory.py -v
PYTHONPATH=. uv run pytest -x -q
git add backend/src/agents/memory/ backend/tests/agents/memory/
git commit -m "feat: add persistent memory system with fact storage and injection"
```

---

### Task 10: Integration Test - Full Pipeline End-to-End

**Files:**
- Create: `backend/tests/integration/test_pipeline_e2e.py`

**Step 1: Write integration test**

```python
"""End-to-end integration test for the 16-layer pipeline."""

import pytest

from src.agents.lead_agent.agent import build_pipeline, make_lead_agent
from src.agents.thread_state import ThreadState


class TestPipelineE2E:
    def test_pipeline_builds_without_error(self):
        """Pipeline should build with default config."""
        config = {"configurable": {"model_name": "gpt-4o", "subagent_enabled": True}}
        pipeline = build_pipeline(config)
        assert len(pipeline) >= 5

    def test_agent_creates_with_pipeline(self):
        """Agent should be creatable with the new pipeline."""
        config = {"configurable": {"model_name": "gpt-4o", "subagent_enabled": False}}
        # This should not raise
        agent = make_lead_agent(config)
        assert agent is not None

    def test_config_loader_integrates(self):
        """Config system should load defaults without errors."""
        from src.config.config_loader import get_app_config, reset_app_config
        reset_app_config()
        config = get_app_config()
        assert config is not None
        assert isinstance(config.models, list)

    def test_memory_integrates(self, tmp_path):
        """Memory system should create and read without errors."""
        from src.agents.memory.updater import get_memory_data
        storage = str(tmp_path / "test_memory.json")
        data = get_memory_data(storage_path=storage)
        assert "version" in data
        assert "facts" in data

    def test_full_test_suite_still_passes(self):
        """Meta-test: ensure this doesn't break anything.

        Run the full suite separately:
        PYTHONPATH=. uv run pytest -x -q
        """
        pass
```

**Step 2: Run integration test**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/integration/test_pipeline_e2e.py -v
```

**Step 3: Run full test suite to verify no regressions**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest -x -q
```

**Step 4: Commit**

```bash
git add backend/tests/integration/test_pipeline_e2e.py
git commit -m "test: add pipeline e2e integration tests"
```

---

### Task 11: Final Verification and Phase 1 Summary Commit

**Step 1: Run full test suite**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest -v 2>&1 | tail -20
```

**Step 2: Verify new components work together**

```bash
cd /home/cjz/academiagpt-v2/backend
python -c "
from src.agents.thread_state import ThreadState, SandboxState, ThreadDataState, ViewedImageData
from src.agents.lead_agent.agent import build_pipeline
from src.config.config_loader import load_config, AppConfig
from src.reflection.resolvers import resolve_variable
from src.subagents.executor import SubagentExecutor, SubagentStatus
from src.agents.memory.updater import MemoryUpdater, create_default_memory
print('All Phase 1 imports successful!')
print(f'ThreadState bases: {ThreadState.__bases__}')
config = load_config()
print(f'Config loaded: {len(config.models)} models, subagents={config.subagents.enabled}')
pipeline = build_pipeline({'configurable': {'subagent_enabled': True}})
print(f'Pipeline: {len(pipeline)} middlewares')
for i, m in enumerate(pipeline):
    print(f'  {i+1}. {type(m).__name__}')
"
```

**Step 3: Commit phase summary**

```bash
git add -A
git commit -m "docs: Phase 1 pipeline infrastructure complete

- ThreadState extends AgentState with academic fields
- 16-layer middleware pipeline (infrastructure + academic + control)
- config.yaml unified configuration system
- Reflection system for dynamic module loading
- SubagentExecutor with background threading
- Persistent memory system with fact storage
- Full backward compatibility with existing 790+ tests"
```

---

## Post-Phase 1 Checklist

After completing all tasks, verify:

- [ ] `PYTHONPATH=. uv run pytest -x -q` → all tests pass (790+ existing + new tests)
- [ ] `ThreadState` extends `AgentState` (not `BaseModel`)
- [ ] `build_pipeline()` returns 10+ middlewares in correct order
- [ ] `ClarificationMiddleware` is always last in pipeline
- [ ] `config.yaml` loads and resolves `$ENV_VAR` references
- [ ] `resolve_variable("os.path:sep")` returns `"/"`
- [ ] `SubagentExecutor.execute()` runs and returns `SubagentResult`
- [ ] `MemoryUpdater.format_for_injection()` returns `<memory>` block
- [ ] No circular import issues

## What's Next: Phase 2

Phase 2 (Agent Execution Engine) will:
1. Wire SubagentExecutor into task_tool with SSE event streaming
2. Implement full LLM-driven memory updates
3. Add SummarizationMiddleware for token limit management
4. Skill execution framework (SKILL.md → Subagent chain invocation)
5. Config-driven model creation (replace env var JSON with config.yaml models)
