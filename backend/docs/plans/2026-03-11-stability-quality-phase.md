# Stability & Quality Optimization Phase Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Fix blocking issues, improve code quality, and enhance test coverage to production-ready standards.

**Architecture:** Incremental improvements in 4 sub-phases: Critical fixes → Quality improvements → Error handling → Test coverage. Build on existing infrastructure rather than replacing.

**Tech Stack:** Python 3.12, Pydantic V2, pytest, SQLAlchemy async, FastAPI

---

## Current State Analysis

### Test Results
- **Total Tests**: 1,236
- **Passing**: 1,160 (93.8%)
- **Failing**: 29 (2.3%)
- **Blocked by Import Errors**: 47 (3.8%)

### Existing Infrastructure (Don't Rebuild)
- `src/gateway/exceptions.py` - Base exception hierarchy exists
- `src/gateway/middleware/error_handler.py` - Error handlers registered
- Docker tests already use `@pytest.mark.skipif` (but implementation needs fix)

### Actual Gaps
1. `src/__init__.py` missing module exports → `AttributeError: module 'src' has no attribute 'models'`
2. Pydantic V2 migration incomplete → 3 response models with deprecated `class Config`
3. No structured JSON logging
4. No correlation ID middleware
5. Missing domain-specific exceptions (extend existing base)
6. Test coverage gaps in skills and MCP modules

---

## Phase 4A: Critical Fixes (3 tasks)

### Task 1: Fix Module Exports in `src/__init__.py`

**Files:**
- Modify: `src/__init__.py`

**Current State:**
```python
# AcademiaGPT v2 Backend
```

**Target State:**
```python
"""AcademiaGPT v2 Backend package."""

from src import models
from src import database
from src import agents
from src import services
from src import academic
from src import gateway
from src import execution
from src import config

__all__ = [
    "models",
    "database",
    "agents",
    "services",
    "academic",
    "gateway",
    "execution",
    "config",
]
```

**Step 1: Update the file**

Edit `src/__init__.py` to add proper exports.

**Step 2: Verify imports work**

Run: `python -c "from src import models, database, agents; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add src/__init__.py
git commit -m "fix(core): add module exports to src/__init__.py"
```

---

### Task 2: Add Docker Availability Detection

**Files:**
- Modify: `tests/conftest.py`

**Current Issue:**
The latex integration test uses `pytest.importorskip` incorrectly - it's used in `@pytest.mark.skipif` which expects a boolean, not a module.

**Step 1: Add Docker detection fixture**

Add to `tests/conftest.py`:

```python
import subprocess


@pytest.fixture(scope="session")
def docker_available():
    """Check if Docker is available and running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False
```

**Step 2: Update test files to use fixture**

Modify `tests/execution/test_latex_integration.py`:

Change from:
```python
@pytest.mark.skipif(
    not pytest.importorskip("docker", reason="Docker not installed"),
    reason="Docker not available"
)
```

To:
```python
@pytest.mark.skipif(
    "not docker_available",
    reason="Docker not available"
)
```

And add `docker_available` as a fixture parameter to tests that need it.

**Step 3: Run tests**

Run: `pytest tests/execution/test_latex_integration.py -v`
Expected: Tests skip gracefully if Docker unavailable, pass if available

**Step 4: Commit**

```bash
git add tests/conftest.py tests/execution/test_latex_integration.py
git commit -m "fix(tests): add proper Docker availability detection"
```

---

### Task 3: Fix Import Errors in Tests

**Files:**
- Various test files with import errors

**Step 1: Run test suite to identify import errors**

Run: `pytest tests/ --collect-only 2>&1 | grep -i "importerror\|module" | head -20`

**Step 2: Fix identified import issues**

Common patterns to fix:
- Missing `__init__.py` in test directories
- Wrong import paths
- Missing dependencies

**Step 3: Verify collection works**

Run: `pytest tests/ --collect-only -q`
Expected: All tests collected without errors

**Step 4: Commit**

```bash
git add tests/
git commit -m "fix(tests): resolve import errors in test modules"
```

---

## Phase 4B: Code Quality Improvements (3 tasks)

### Task 4: Complete Pydantic V2 Migration in academic.py

**Files:**
- Modify: `src/gateway/routers/academic.py`

**Models to migrate:**
1. `WorkspaceResponse` (line 42-43)
2. `PaperResponse` (line 74-75)
3. `ArtifactResponse` (line 115-116)

**Step 1: Add ConfigDict import**

Change:
```python
from pydantic import BaseModel
```

To:
```python
from pydantic import BaseModel, ConfigDict
```

**Step 2: Migrate WorkspaceResponse**

Change:
```python
class WorkspaceResponse(BaseModel):
    # ... fields ...

    class Config:
        from_attributes = True
```

To:
```python
class WorkspaceResponse(BaseModel):
    # ... fields ...

    model_config = ConfigDict(from_attributes=True)
```

**Step 3: Migrate PaperResponse**

Same pattern as Step 2.

**Step 4: Migrate ArtifactResponse**

Same pattern as Step 2.

**Step 5: Run tests**

Run: `pytest tests/gateway/routers/ -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add src/gateway/routers/academic.py
git commit -m "refactor(pydantic): migrate academic.py to ConfigDict"
```

---

### Task 5: Add Type Annotations to Core Modules

**Files:**
- Modify: `src/services/workspace_service.py`
- Modify: `src/services/paper_service.py`

**Step 1: Add type hints to workspace_service.py**

Key areas to annotate:
- Method parameters
- Return types
- Class attributes

Example pattern:
```python
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

class WorkspaceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        user_id: str,
        name: str,
        type: str,
        discipline: str | None = None,
        description: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> Workspace:
        ...
```

**Step 2: Add type hints to paper_service.py**

Apply same pattern.

**Step 3: Run mypy to verify**

Run: `mypy src/services/workspace_service.py src/services/paper_service.py --ignore-missing-imports`
Expected: No errors

**Step 4: Commit**

```bash
git add src/services/workspace_service.py src/services/paper_service.py
git commit -m "refactor(types): add type annotations to core services"
```

---

### Task 6: Fix Test Class Constructor Warnings

**Files:**
- Search and fix classes with `__init__` in test files

**Step 1: Find test classes with __init__**

Run: `grep -r "def __init__" tests/ --include="*.py" | head -20`

**Step 2: Convert to fixtures**

Pattern to replace:
```python
class TestSomething:
    def __init__(self):
        self.service = SomeService()
```

To:
```python
@pytest.fixture
def service(db_session):
    return SomeService(db_session)

class TestSomething:
    def test_method(self, service):
        ...
```

**Step 3: Run tests**

Run: `pytest tests/ -v -W error::pytest.PytestCollectionWarning`
Expected: No warnings

**Step 4: Commit**

```bash
git add tests/
git commit -m "refactor(tests): convert __init__ to fixtures"
```

---

## Phase 4C: Error Handling Enhancement (4 tasks)

### Task 7: Add Domain-Specific Exceptions

**Files:**
- Modify: `src/gateway/exceptions.py`

**Step 1: Add literature exceptions**

```python
# Literature exceptions
class LiteratureError(AcademiaGPTException):
    """Base exception for literature module."""

    pass


class PaperNotFoundError(LiteratureError):
    """Paper not found in database or external source."""

    def __init__(self, paper_id: str):
        super().__init__(f"Paper not found: {paper_id}", code="PAPER_NOT_FOUND")


class ExternalAPIError(LiteratureError):
    """External API request failed."""

    def __init__(self, source: str, message: str):
        super().__init__(f"{source} API error: {message}", code="EXTERNAL_API_ERROR")
```

**Step 2: Add citation exceptions**

```python
# Citation exceptions
class CitationError(AcademiaGPTException):
    """Base exception for citation module."""

    pass


class InvalidBibTeXError(CitationError):
    """Invalid BibTeX format."""

    def __init__(self, message: str):
        super().__init__(f"Invalid BibTeX: {message}", code="INVALID_BIBTEX")
```

**Step 3: Add execution exceptions**

```python
# Execution exceptions
class ExecutionError(AcademiaGPTException):
    """Base exception for execution module."""

    pass


class DockerUnavailableError(ExecutionError):
    """Docker is not available."""

    def __init__(self):
        super().__init__("Docker is not available", code="DOCKER_UNAVAILABLE")


class CompilationError(ExecutionError):
    """LaTeX compilation failed."""

    def __init__(self, message: str):
        super().__init__(f"Compilation failed: {message}", code="COMPILATION_ERROR")
```

**Step 4: Update status mapping**

Add to `map_exception_to_status`:
```python
"PAPER_NOT_FOUND": status.HTTP_404_NOT_FOUND,
"EXTERNAL_API_ERROR": status.HTTP_502_BAD_GATEWAY,
"INVALID_BIBTEX": status.HTTP_400_BAD_REQUEST,
"DOCKER_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
"COMPILATION_ERROR": status.HTTP_422_UNPROCESSABLE_CONTENT,
```

**Step 5: Commit**

```bash
git add src/gateway/exceptions.py
git commit -m "feat(exceptions): add domain-specific exceptions"
```

---

### Task 8: Add Structured Logging

**Files:**
- Create: `src/logging_config.py`
- Modify: `src/gateway/app.py`

**Step 1: Create logging_config.py**

```python
"""Structured logging configuration for AcademiaGPT."""

import logging
import sys
from datetime import datetime


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured log output."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured text."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        if hasattr(record, "correlation_id"):
            log_data["correlation_id"] = record.correlation_id
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "workspace_id"):
            log_data["workspace_id"] = record.workspace_id

        # Format as key=value pairs (readable but structured)
        return " ".join(f"{k}={v}" for k, v in log_data.items())


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    log_handler = logging.StreamHandler(sys.stdout)
    log_handler.setFormatter(StructuredFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(log_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("docker").setLevel(logging.WARNING)
```

**Step 2: Import and use in app.py**

Add at top of `src/gateway/app.py`:
```python
from src.logging_config import setup_logging

# Call early in app startup
setup_logging()
```

**Step 3: Commit**

```bash
git add src/logging_config.py src/gateway/app.py
git commit -m "feat(logging): add structured logging configuration"
```

---

### Task 9: Add Request Correlation ID

**Files:**
- Create: `src/gateway/middleware/correlation.py`
- Modify: `src/gateway/app.py`

**Step 1: Create correlation middleware**

```python
"""Correlation ID middleware for request tracing."""

import uuid
from contextvars import ContextVar
from typing import Callable

from fastapi import Request, Response

# Context variable for correlation ID
correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


async def correlation_middleware(request: Request, call_next: Callable) -> Response:
    """Add correlation ID to all requests.

    Args:
        request: The incoming request.
        call_next: The next middleware/handler.

    Returns:
        The response with correlation ID header.
    """
    # Get or generate correlation ID
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))

    # Store in context
    correlation_id_var.set(correlation_id)

    # Process request
    response = await call_next(request)

    # Add to response headers
    response.headers["X-Correlation-ID"] = correlation_id

    return response


def get_correlation_id() -> str | None:
    """Get current correlation ID from context.

    Returns:
        The correlation ID if set, None otherwise.
    """
    return correlation_id_var.get()
```

**Step 2: Register middleware in app.py**

```python
from src.gateway.middleware.correlation import correlation_middleware

# Add middleware
app.middleware("http")(correlation_middleware)
```

**Step 3: Commit**

```bash
git add src/gateway/middleware/correlation.py src/gateway/app.py
git commit -m "feat(middleware): add correlation ID for request tracing"
```

---

### Task 10: Enhance Error Logging with Context

**Files:**
- Modify: `src/gateway/middleware/error_handler.py`

**Step 1: Add correlation ID to error logs**

```python
from src.gateway.middleware.correlation import get_correlation_id


async def academia_exception_handler(request: Request, exc: AcademiaGPTException) -> JSONResponse:
    """Handle all AcademiaGPT custom exceptions."""
    correlation_id = get_correlation_id()

    logger.warning(
        "AcademiaGPT exception: %s - %s (path: %s, correlation_id: %s)",
        exc.code,
        exc.message,
        request.url.path,
        correlation_id,
    )

    response_content = {
        "error": {
            "code": exc.code,
            "message": exc.message,
        }
    }

    if correlation_id:
        response_content["correlation_id"] = correlation_id

    return JSONResponse(
        status_code=map_exception_to_status(exc),
        content=response_content,
    )
```

**Step 2: Apply same pattern to other handlers**

Update `validation_exception_handler`, `http_exception_handler`, and `generic_exception_handler`.

**Step 3: Commit**

```bash
git add src/gateway/middleware/error_handler.py
git commit -m "feat(error-handler): add correlation ID to error responses"
```

---

## Phase 4D: Test Coverage Improvement (3 tasks)

### Task 11: Add Skills Module Tests

**Files:**
- Create: `tests/skills/__init__.py`
- Create: `tests/skills/implementations/__init__.py`
- Create: `tests/skills/implementations/test_literature_review.py`

**Step 1: Create test directory structure**

```bash
mkdir -p tests/skills/implementations
touch tests/skills/__init__.py
touch tests/skills/implementations/__init__.py
```

**Step 2: Create literature_review test**

```python
"""Tests for literature review skill."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.skills.implementations.literature_review import LiteratureReviewSkill


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    return MagicMock()


@pytest.fixture
def skill(mock_db_session):
    """Create skill instance."""
    return LiteratureReviewSkill(db=mock_db_session)


class TestLiteratureReviewSkill:
    """Tests for LiteratureReviewSkill."""

    def test_skill_name(self, skill):
        """Should have correct name."""
        assert skill.name == "literature_review"

    def test_skill_description(self, skill):
        """Should have description."""
        assert len(skill.description) > 0

    @pytest.mark.asyncio
    async def test_execute_empty_query(self, skill):
        """Should handle empty query."""
        result = await skill.execute(query="")
        assert "error" in result or result.get("status") == "empty"

    @pytest.mark.asyncio
    async def test_execute_basic_query(self, skill):
        """Should execute basic query."""
        # Mock the internal search
        skill.search_papers = AsyncMock(return_value=[])
        result = await skill.execute(query="machine learning")
        assert result is not None
```

**Step 3: Run tests**

Run: `pytest tests/skills/ -v`
Expected: Tests pass

**Step 4: Commit**

```bash
git add tests/skills/
git commit -m "test(skills): add literature review skill tests"
```

---

### Task 12: Add MCP Tools Tests

**Files:**
- Create: `tests/mcp/__init__.py`
- Create: `tests/mcp/tools/__init__.py`
- Create: `tests/mcp/tools/test_doi.py`

**Step 1: Create test directory**

```bash
mkdir -p tests/mcp/tools
touch tests/mcp/__init__.py
touch tests/mcp/tools/__init__.py
```

**Step 2: Create DOI tool test**

```python
"""Tests for DOI MCP tool."""

import pytest
from unittest.mock import patch, AsyncMock

from src.mcp.tools.doi import resolve_doi, get_doi_metadata


class TestDOITools:
    """Tests for DOI MCP tools."""

    @pytest.mark.asyncio
    async def test_resolve_doi_valid(self):
        """Should resolve valid DOI."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = AsyncMock(
                status_code=200,
                json=lambda: {"title": "Test Paper"}
            )
            result = await resolve_doi("10.1000/test")
            assert result is not None

    @pytest.mark.asyncio
    async def test_resolve_doi_invalid(self):
        """Should handle invalid DOI."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = AsyncMock(status_code=404)
            result = await resolve_doi("invalid-doi")
            assert result is None or "error" in result

    @pytest.mark.asyncio
    async def test_get_doi_metadata(self):
        """Should get DOI metadata."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = AsyncMock(
                status_code=200,
                json=lambda: {
                    "title": ["Test Paper"],
                    "author": [{"given": "John", "family": "Doe"}],
                    "published": {"date-parts": [[2024]]}
                }
            )
            result = await get_doi_metadata("10.1000/test")
            assert result.get("title") == "Test Paper"
```

**Step 3: Run tests**

Run: `pytest tests/mcp/ -v`
Expected: Tests pass

**Step 4: Commit**

```bash
git add tests/mcp/
git commit -m "test(mcp): add DOI tool tests"
```

---

### Task 13: Run Full Test Suite and Verify Coverage

**Files:**
- None (verification task)

**Step 1: Run full test suite**

Run: `pytest tests/ -v --tb=short`

**Step 2: Run with coverage**

Run: `pytest tests/ --cov=src --cov-report=term-missing --cov-report=json`

**Step 3: Check coverage threshold**

Run: `coverage report | grep TOTAL`
Expected: Coverage >= 75% (target is 80%, this is incremental)

**Step 4: Document results**

Create/update coverage report in docs.

**Step 5: Commit any fixes**

```bash
git add .
git commit -m "chore(tests): verify coverage targets met"
```

---

## Success Criteria

| Metric | Before | After | Target |
|--------|--------|-------|--------|
| Test Pass Rate | 93.8% | - | 95%+ |
| Code Coverage | 67% | - | 80%+ |
| Type Annotation | 23% | - | 50%+ |
| Pydantic Warnings | 3 | - | 0 |
| Import Errors | 47 | - | 0 |

---

## Implementation Order

1. **Phase 4A** (Critical) - Fix blocking issues first
2. **Phase 4B** (High) - Code quality improvements
3. **Phase 4C** (Medium) - Error handling enhancement
4. **Phase 4D** (Medium) - Test coverage improvement

---

## Files Changed Summary

| Phase | Files | Changes |
|-------|-------|---------|
| 4A | 3 | Module exports, Docker detection, Import fixes |
| 4B | 4 | Pydantic V2, Type annotations, Test fixes |
| 4C | 5 | Domain exceptions, Logging, Correlation, Error handler |
| 4D | 6 | New test files |

**Total:** 18 files modified/created

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Pydantic V2 breaking changes | High | Test all affected endpoints |
| Test restructure breaking CI | Medium | Run full suite after each task |
| New dependencies | Low | No new packages required |

---

## Next Steps

Ready for execution. Two options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints
