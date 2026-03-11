# Stability & Quality Optimization Phase Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to create implementation plan.

**Goal:** Fix blocking issues, improve code quality, and enhance test coverage to production-ready standards.

**Architecture:** Incremental improvements in 4 sub-phases: Critical fixes → Quality improvements → Error handling → Test coverage.

**Tech Stack:** Python 3.12, Pydantic V2, pytest, SQLAlchemy async

---

## Overview

This phase focuses on stability and quality improvements to prepare the system for production deployment. We address blocking issues first, then systematically improve code quality, error handling, and test coverage.

## Current State Analysis

### Test Results
- **Total Tests**: 1,236
- **Passing**: 1,160 (93.8%)
- **Failing**: 29 (2.3%)
- **Blocked by Import Errors**: 47 (3.8%)

### Code Quality Metrics
- **Type Annotation Coverage**: 23% (69/298 files)
- **Test Coverage**: 67%
- **Custom Exceptions**: 22 classes

### Identified Issues

**Critical (Blocking):**
1. `src/__init__.py` missing module exports → `AttributeError: module 'src' has no attribute 'models'`
2. Docker unavailable in test environment → 2 test failures
3. Duplicate test module names → `test_models.py` collision

**High Priority:**
1. Pydantic V2 migration incomplete → 3 routers with deprecated `class Config`
2. Test class constructor warnings → 11 classes with `__init__`
3. Low type annotation coverage → 23%

**Medium Priority:**
1. No structured logging
2. No domain-specific exceptions
3. Inconsistent error responses

---

## Phase 4A: Critical Fixes (3 tasks)

### Task 1: Fix Module Exports in `src/__init__.py`

**File:** `src/__init__.py`

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

__all__ = [
    "models",
    "database",
    "agents",
    "services",
    "academic",
]
```

**Test:** `pytest tests/agents/test_lead_agent.py -v`

---

### Task 2: Add Docker Availability Detection

**Files:**
- `tests/conftest.py` - Add Docker check fixture
- `tests/execution/test_latex_integration.py` - Skip if Docker unavailable

**Implementation:**
```python
# tests/conftest.py
import pytest
import subprocess

@pytest.fixture(scope="session")
def docker_available():
    """Check if Docker is available."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False

@pytest.fixture
def skip_without_docker(docker_available):
    """Skip test if Docker is not available."""
    if not docker_available:
        pytest.skip("Docker not available")
```

**Usage in tests:**
```python
def test_compile_latex(skip_without_docker):
    ...
```

---

### Task 3: Rename Duplicate Test Modules

**Files:**
- `tests/academic/database/test_models.py` → `tests/academic/database/test_paper_models.py`
- `tests/subagents/test_models.py` → `tests/subagents/test_subagent_models.py`

**Test:** `pytest tests/academic/database/ tests/subagents/ -v`

---

## Phase 4B: Code Quality Improvements (3 tasks)

### Task 4: Complete Pydantic V2 Migration

**File:** `src/gateway/routers/academic.py`

**Changes:** Replace `class Config` with `model_config = ConfigDict(...)`

**Example:**
```python
# Before
class CitationRequest(BaseModel):
    paper_ids: list[str]

    class Config:
        json_schema_extra = {"example": {"paper_ids": ["uuid-1", "uuid-2"]}}

# After
from pydantic import ConfigDict

class CitationRequest(BaseModel):
    paper_ids: list[str]

    model_config = ConfigDict(
        json_schema_extra={"example": {"paper_ids": ["uuid-1", "uuid-2"]}}
    )
```

**Test:** `pytest tests/gateway/routers/ -v`

---

### Task 5: Fix Test Class Constructor Warnings

**Files:**
- `tests/academic/services/test_artifact_service.py`
- `tests/integration/conftest.py`

**Changes:** Remove `__init__` methods and use pytest fixtures instead.

**Example:**
```python
# Before
class TestArtifactService:
    def __init__(self):
        self.service = ArtifactService()

# After
@pytest.fixture
def service(self, db_session):
    return ArtifactService(db_session)

class TestArtifactService:
    def test_create_artifact(self, service):
        ...
```

---

### Task 6: Add Type Annotations to Core Modules

**Priority files:**
1. `src/services/workspace_service.py`
2. `src/services/paper_service.py`
3. `src/agents/lead_agent/agent.py`
4. `src/gateway/routers/workspaces.py`

**Target:** Improve type annotation coverage from 23% to 50%

---

## Phase 4C: Error Handling Enhancement (4 tasks)

### Task 7: Define Domain Exception Hierarchy

**File:** `src/exceptions.py`

```python
"""Domain-specific exceptions for AcademiaGPT."""


class AcademiaGPTError(Exception):
    """Base exception for AcademiaGPT."""
    def __init__(self, message: str, code: str | None = None):
        self.message = message
        self.code = code or "UNKNOWN_ERROR"
        super().__init__(message)


# Literature exceptions
class LiteratureError(AcademiaGPTError):
    """Base exception for literature module."""
    pass


class PaperNotFoundError(LiteratureError):
    """Paper not found in database or external source."""
    def __init__(self, paper_id: str):
        super().__init__(f"Paper not found: {paper_id}", "PAPER_NOT_FOUND")


class ExternalAPIError(LiteratureError):
    """External API request failed."""
    def __init__(self, source: str, message: str):
        super().__init__(f"{source} API error: {message}", "EXTERNAL_API_ERROR")


# Citation exceptions
class CitationError(AcademiaGPTError):
    """Base exception for citation module."""
    pass


class InvalidBibTeXError(CitationError):
    """Invalid BibTeX format."""
    def __init__(self, message: str):
        super().__init__(f"Invalid BibTeX: {message}", "INVALID_BIBTEX")


# Execution exceptions
class ExecutionError(AcademiaGPTError):
    """Base exception for execution module."""
    pass


class DockerUnavailableError(ExecutionError):
    """Docker is not available."""
    def __init__(self):
        super().__init__("Docker is not available", "DOCKER_UNAVAILABLE")


class CompilationError(ExecutionError):
    """LaTeX compilation failed."""
    def __init__(self, message: str):
        super().__init__(f"Compilation failed: {message}", "COMPILATION_ERROR")
```

---

### Task 8: Add Structured Logging

**File:** `src/logging_config.py`

```python
"""Structured logging configuration."""

import logging
import sys
from pythonjsonlogger import jsonlogger


def setup_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging."""
    log_handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s "
        "%(correlation_id)s %(user_id)s %(workspace_id)s"
    )
    log_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(log_handler)
```

---

### Task 9: Standardize API Error Responses

**File:** `src/gateway/middleware/error_handler.py`

```python
"""Standardized error response middleware."""

from fastapi import Request
from fastapi.responses import JSONResponse
from src.exceptions import AcademiaGPTError


async def error_handler_middleware(request: Request, call_next):
    """Handle exceptions and return standardized responses."""
    try:
        return await call_next(request)
    except AcademiaGPTError as e:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": e.code,
                    "message": e.message,
                }
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred",
                }
            }
        )
```

---

### Task 10: Add Request Tracing ID

**File:** `src/gateway/middleware/correlation.py`

```python
"""Correlation ID middleware for request tracing."""

import uuid
from fastapi import Request


async def correlation_middleware(request: Request, call_next):
    """Add correlation ID to all requests."""
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    request.state.correlation_id = correlation_id

    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response
```

---

## Phase 4D: Test Coverage Improvement (3 tasks)

### Task 11: Add Skills Module Tests

**Files:**
- `tests/skills/implementations/test_framework_designer.py`
- `tests/skills/implementations/test_fullpaper_writer.py`
- `tests/skills/implementations/test_literature_review.py`

**Target:** 80% coverage for skills module

---

### Task 12: Add MCP Tools Tests

**Files:**
- `tests/mcp/tools/test_doi.py`
- `tests/mcp/tools/test_pubmed.py`

**Target:** 80% coverage for MCP tools

---

### Task 13: Run Full Test Suite and Verify Coverage

**Commands:**
```bash
pytest tests/ -v --cov=src --cov-report=term-missing
```

**Target:**
- Test pass rate: 95%+
- Code coverage: 80%+

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
| 4A | 5 | Module exports, Docker detection, Test renames |
| 4B | 5 | Pydantic V2, Constructor fixes, Type annotations |
| 4C | 4 | Exceptions, Logging, Error middleware, Correlation |
| 4D | 6 | New test files |

**Total:** 20 files modified/created

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Pydantic V2 breaking changes | High | Test all affected endpoints |
| Test restructure breaking CI | Medium | Run full suite after each task |
| New dependencies | Low | Minimal new packages (pythonjsonlogger) |

---

## Next Steps

After approval, invoke `superpowers:writing-plans` to create detailed implementation plan with TDD steps for each task.
