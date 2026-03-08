# AcademiaGPT v2 Review and Improvement Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Comprehensive review and improvement of AcademiaGPT v2 to make it production-ready.

**Current State:** 148 tests passing, core architecture complete, but many features are placeholders or incomplete.

**Priority Order:** Backend Services > Skills Implementation > Frontend > Integration Tests > Documentation

---

## Phase 1: Backend Service Layer Completion (Priority: P0)

### Task 1.1: Paper Extraction Service Implementation

**Files:**
- Create: `backend/src/academic/services/extraction_service.py`
- Create: `backend/tests/academic/services/test_extraction_service.py`

**Description:** Implement the paper extraction service that processes PDFs and extracts structured data (TOC, sections, metadata).

**Step 1: Create the extraction service interface**

```python
"""Paper extraction service for PDF processing."""

from typing import Optional
from pathlib import Path

from src.academic.literature.extraction.pdf_extractor import PDFExtractor
from src.database.models import Paper, PaperExtraction, PaperSection
from src.database.session import get_session


class ExtractionService:
    """Service for extracting structured data from academic papers.

    Supports two-tier extraction:
    - Tier 1: Engineering extraction (GROBID, PyMuPDF) - instant
    - Tier 2: LLM extraction (Haiku, Qwen-Turbo) - seconds
    """

    def __init__(self, pdf_extractor: PDFExtractor | None = None):
        self.pdf_extractor = pdf_extractor or PDFExtractor()

    async def extract_paper(
        self,
        paper_id: str,
        file_path: str,
        tier: int = 1,
    ) -> PaperExtraction:
        """Extract structured data from a paper PDF.

        Args:
            paper_id: UUID of the paper
            file_path: Path to the PDF file
            tier: Extraction tier (1=engineering, 2=LLM)

        Returns:
            PaperExtraction with structured_data
        """
        ...

    async def extract_sections(
        self,
        paper_id: str,
        workspace_id: str,
        file_path: str,
    ) -> list[PaperSection]:
        """Extract paper sections for index-based navigation.

        Args:
            paper_id: UUID of the paper
            workspace_id: UUID of the workspace
            file_path: Path to the PDF file

        Returns:
            List of PaperSection objects
        """
        ...

    async def get_or_extract(self, paper: Paper, workspace_id: str) -> PaperExtraction:
        """Get existing extraction or create new one.

        Implements caching to avoid re-extraction.
        """
        ...
```

**Step 2: Implement extraction logic**

- Use PDFExtractor for Tier 1 extraction
- Implement TOC parsing and section splitting
- Store results in database

**Step 3: Write tests**

```python
"""Tests for extraction service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.academic.services.extraction_service import ExtractionService


class TestExtractionService:
    """Tests for ExtractionService."""

    @pytest.fixture
    def service(self):
        return ExtractionService()

    @pytest.mark.asyncio
    async def test_extract_paper_tier1_returns_extraction(self, service):
        """Test Tier 1 extraction returns structured data."""
        ...

    @pytest.mark.asyncio
    async def test_extract_sections_creates_paper_sections(self, service):
        """Test section extraction creates PaperSection records."""
        ...

    @pytest.mark.asyncio
    async def test_get_or_extract_returns_cached(self, service):
        """Test cached extraction is returned without re-processing."""
        ...
```

**Step 4: Run tests and verify**

```bash
cd backend && uv run pytest tests/academic/services/test_extraction_service.py -v
```

**Step 5: Commit**

```bash
git add backend/src/academic/services/extraction_service.py backend/tests/academic/services/test_extraction_service.py
git commit -m "feat: add paper extraction service with tier 1 support"
```

---

### Task 1.2: User Service Implementation

**Files:**
- Create: `backend/src/services/user_service.py`
- Create: `backend/tests/services/test_user_service.py`

**Description:** Implement user CRUD operations for the authentication system.

**Step 1: Create user service**

```python
"""User service for user management operations."""

from typing import Optional
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.database.models import User
from src.services.auth import hash_password, verify_password


class UserService:
    """Service for user management."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_user(
        self,
        email: str,
        password: str,
        name: Optional[str] = None,
    ) -> User:
        """Create a new user.

        Args:
            email: User email
            password: Plain text password
            name: Optional display name

        Returns:
            Created User object

        Raises:
            ValueError: If email already exists
        """
        ...

    async def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        ...

    async def get_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        ...

    async def authenticate(self, email: str, password: str) -> Optional[User]:
        """Authenticate user with email and password.

        Returns User if authenticated, None otherwise.
        """
        ...

    async def update_last_login(self, user_id: str) -> None:
        """Update user's last login timestamp."""
        ...
```

**Step 2: Write comprehensive tests**

**Step 3: Run tests and commit**

---

### Task 1.3: Workspace Service Implementation

**Files:**
- Create: `backend/src/academic/services/workspace_service.py`
- Create: `backend/tests/academic/services/test_workspace_service.py`

**Description:** Complete the workspace service with full CRUD operations.

**Implementation:**

```python
"""Workspace service for workspace management."""

from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.database.models import Workspace, WorkspaceType


class WorkspaceService:
    """Service for workspace management."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: str,
        name: str,
        type: str,
        discipline: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Workspace:
        """Create a new workspace."""
        ...

    async def get(self, workspace_id: str) -> Optional[Workspace]:
        """Get workspace by ID."""
        ...

    async def list_by_user(self, user_id: str) -> List[Workspace]:
        """List all workspaces for a user."""
        ...

    async def update(self, workspace_id: str, **kwargs) -> Optional[Workspace]:
        """Update workspace fields."""
        ...

    async def delete(self, workspace_id: str) -> bool:
        """Delete a workspace."""
        ...

    async def add_paper(self, workspace_id: str, paper_id: str, **kwargs) -> None:
        """Add a paper to a workspace."""
        ...

    async def remove_paper(self, workspace_id: str, paper_id: str) -> bool:
        """Remove a paper from a workspace."""
        ...
```

---

### Task 1.4: Artifact Service Implementation

**Files:**
- Create: `backend/src/academic/services/artifact_service.py`
- Create: `backend/tests/academic/services/test_artifact_service.py`

**Description:** Implement artifact CRUD for academic outputs (research ideas, methodologies, etc.).

---

### Task 1.5: Paper Service Implementation

**Files:**
- Create: `backend/src/academic/services/paper_service.py`
- Create: `backend/tests/academic/services/test_paper_service.py`

**Description:** Implement paper management operations including search and metadata updates.

---

## Phase 2: Skills Implementation (Priority: P0)

### Task 2.1: Skill Execution Framework

**Files:**
- Create: `backend/src/skills/executor.py`
- Create: `backend/src/skills/base.py`
- Create: `backend/tests/skills/test_executor.py`

**Description:** Create the framework for executing skills dynamically.

**Step 1: Create base skill class**

```python
"""Base skill implementation."""

from abc import ABC, abstractmethod
from typing import Any, Optional
from pydantic import BaseModel
from datetime import datetime

from src.agents.thread_state import ThreadState


class SkillInput(BaseModel):
    """Base input for skills."""
    workspace_id: str
    user_query: str
    context: dict = {}


class SkillOutput(BaseModel):
    """Base output from skills."""
    success: bool
    content: str
    artifacts: list[dict] = []
    metadata: dict = {}


class BaseSkill(ABC):
    """Abstract base class for all skills."""

    name: str
    description: str
    version: str = "1.0.0"

    @abstractmethod
    async def execute(self, input: SkillInput, state: ThreadState) -> SkillOutput:
        """Execute the skill.

        Args:
            input: Skill input parameters
            state: Current thread state

        Returns:
            SkillOutput with results
        """
        pass

    def validate_input(self, input: SkillInput) -> Optional[str]:
        """Validate input before execution.

        Returns error message if invalid, None if valid.
        """
        return None
```

**Step 2: Create skill executor**

```python
"""Skill executor for running skills."""

from typing import Optional
import importlib
from pathlib import Path

from src.skills.base import BaseSkill, SkillInput, SkillOutput
from src.agents.thread_state import ThreadState


class SkillExecutor:
    """Executor for running academic skills."""

    def __init__(self, skills_dir: str = "skills/public"):
        self.skills_dir = Path(skills_dir)
        self._skills: dict[str, BaseSkill] = {}

    def register_skill(self, skill: BaseSkill) -> None:
        """Register a skill instance."""
        self._skills[skill.name] = skill

    async def execute(
        self,
        skill_name: str,
        input: SkillInput,
        state: ThreadState,
    ) -> SkillOutput:
        """Execute a skill by name.

        Args:
            skill_name: Name of the skill to execute
            input: Skill input
            state: Current thread state

        Returns:
            SkillOutput from the skill

        Raises:
            ValueError: If skill not found
        """
        skill = self._skills.get(skill_name)
        if not skill:
            raise ValueError(f"Skill '{skill_name}' not found")

        # Validate input
        error = skill.validate_input(input)
        if error:
            return SkillOutput(success=False, content=error)

        return await skill.execute(input, state)

    def list_skills(self) -> list[str]:
        """List all registered skills."""
        return list(self._skills.keys())
```

**Step 3: Write tests**

---

### Task 2.2: Deep Research Skill Implementation

**Files:**
- Create: `backend/src/skills/implementations/deep_research.py`
- Create: `backend/tests/skills/implementations/test_deep_research.py`

**Description:** Implement the deep-research skill for comprehensive literature analysis.

**Step 1: Implement the skill**

```python
"""Deep research skill for comprehensive literature analysis."""

from typing import Optional
from datetime import datetime

from src.skills.base import BaseSkill, SkillInput, SkillOutput
from src.agents.thread_state import ThreadState
from src.academic.tools.semantic_scholar import search_papers


class DeepResearchSkill(BaseSkill):
    """Skill for deep literature research and idea generation."""

    name = "deep-research"
    description = "Comprehensive literature analysis and research idea generation"
    version = "1.0.0"

    async def execute(self, input: SkillInput, state: ThreadState) -> SkillOutput:
        """Execute deep research.

        Process:
        1. Search for relevant papers
        2. Analyze paper abstracts
        3. Identify research gaps
        4. Generate novel research ideas
        """
        # 1. Search papers
        papers = await search_papers(input.user_query, limit=20)

        # 2. Analyze and synthesize
        # ... implementation

        # 3. Generate ideas
        # ... implementation

        return SkillOutput(
            success=True,
            content="Research analysis complete...",
            artifacts=[{
                "type": "research_idea",
                "content": {...}
            }],
        )
```

---

### Task 2.3: Framework Designer Skill

**Files:**
- Create: `backend/src/skills/implementations/framework_designer.py`
- Create: `backend/tests/skills/implementations/test_framework_designer.py`

---

### Task 2.4: Fullpaper Writer Skill

**Files:**
- Create: `backend/src/skills/implementations/fullpaper_writer.py`
- Create: `backend/tests/skills/implementations/test_fullpaper_writer.py`

---

### Task 2.5: Literature Review Skill

**Files:**
- Create: `backend/src/skills/implementations/literature_review.py`
- Create: `backend/tests/skills/implementations/test_literature_review.py`

---

## Phase 3: Gateway API Completion (Priority: P1)

### Task 3.1: Auth Router Implementation

**Files:**
- Create: `backend/src/gateway/routers/auth.py`
- Create: `backend/tests/gateway/routers/test_auth.py`

**Description:** Implement authentication endpoints (login, register, refresh).

**Step 1: Create auth router**

```python
"""Authentication router."""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr

from src.services.user_service import UserService
from src.services.auth import create_tokens, verify_access_token, verify_refresh_token


router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/register", response_model=TokenResponse)
async def register(request: RegisterRequest):
    """Register a new user."""
    ...


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """Login with email and password."""
    ...


@router.post("/refresh", response_model=TokenResponse)
async def refresh(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Refresh access token."""
    ...


@router.get("/me")
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current user info."""
    ...
```

---

### Task 3.2: Workspaces Router Implementation

**Files:**
- Create: `backend/src/gateway/routers/workspaces.py`
- Create: `backend/tests/gateway/routers/test_workspaces.py`

---

### Task 3.3: Papers Router Implementation

**Files:**
- Create: `backend/src/gateway/routers/papers.py`
- Create: `backend/tests/gateway/routers/test_papers.py`

---

### Task 3.4: Artifacts Router Implementation

**Files:**
- Create: `backend/src/gateway/routers/artifacts.py`
- Create: `backend/tests/gateway/routers/test_artifacts.py`

---

### Task 3.5: Health Check Endpoint

**Files:**
- Modify: `backend/src/gateway/app.py`

**Description:** Add health check endpoint for Docker health checks.

```python
@app.get("/health")
async def health_check():
    """Health check endpoint for Docker."""
    return {"status": "healthy", "timestamp": datetime.utcnow()}
```

---

## Phase 4: Frontend Completion (Priority: P1)

### Task 4.1: Authentication Pages

**Files:**
- Create: `frontend/app/(auth)/login/page.tsx`
- Create: `frontend/app/(auth)/register/page.tsx`
- Create: `frontend/components/auth/login-form.tsx`
- Create: `frontend/components/auth/register-form.tsx`
- Create: `frontend/stores/auth.ts`

**Description:** Implement login and registration pages.

---

### Task 4.2: Workspace Management UI

**Files:**
- Modify: `frontend/app/workspaces/page.tsx`
- Create: `frontend/components/workspace/workspace-create-modal.tsx`
- Create: `frontend/components/workspace/workspace-settings.tsx`

**Description:** Complete workspace creation and management UI.

---

### Task 4.3: Paper Upload UI

**Files:**
- Create: `frontend/components/paper/paper-upload.tsx`
- Create: `frontend/components/paper/paper-list.tsx`
- Create: `frontend/components/paper/paper-detail.tsx`

**Description:** Implement PDF upload with drag-and-drop.

---

### Task 4.4: Chat Interface Polish

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`
- Create: `frontend/components/chat/message-list.tsx`
- Create: `frontend/components/chat/message-input.tsx`
- Create: `frontend/components/chat/skill-invoker.tsx`

**Description:** Polish the chat interface with proper message rendering.

---

### Task 4.5: Knowledge Panel Implementation

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/KnowledgePanel.tsx`
- Create: `frontend/components/artifact/artifact-list.tsx`
- Create: `frontend/components/artifact/artifact-card.tsx`

**Description:** Implement the knowledge/artifacts panel.

---

## Phase 5: Integration Tests (Priority: P2)

### Task 5.1: API Integration Tests

**Files:**
- Create: `backend/tests/integration/test_auth_flow.py`
- Create: `backend/tests/integration/test_workspace_flow.py`
- Create: `backend/tests/integration/test_paper_flow.py`

**Description:** End-to-end tests for API flows.

---

### Task 5.2: Agent Integration Tests

**Files:**
- Create: `backend/tests/integration/test_agent_with_middlewares.py`
- Create: `backend/tests/integration/test_skill_execution.py`

**Description:** Test the full agent pipeline with middlewares.

---

## Phase 6: Documentation (Priority: P3)

### Task 6.1: API Documentation

**Files:**
- Modify: `backend/src/gateway/app.py`

**Description:** Add OpenAPI documentation with proper descriptions.

```python
app = FastAPI(
    title="AcademiaGPT API",
    description="Academic research and writing assistant API",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)
```

---

### Task 6.2: README Updates

**Files:**
- Modify: `backend/README.md`
- Modify: `frontend/README.md`
- Modify: `README.md` (root)

**Description:** Comprehensive documentation for setup and development.

---

### Task 6.3: Deployment Guide

**Files:**
- Create: `docs/deployment.md`

**Description:** Step-by-step deployment guide.

---

## Phase 7: Security & Performance (Priority: P2)

### Task 7.1: Input Validation

**Files:**
- Create: `backend/src/gateway/validators/`
- Create: `backend/tests/test_validators.py`

**Description:** Add comprehensive input validation for all endpoints.

---

### Task 7.2: Rate Limiting

**Files:**
- Create: `backend/src/gateway/middleware/rate_limit.py`

**Description:** Implement rate limiting middleware.

---

### Task 7.3: Error Handling

**Files:**
- Create: `backend/src/gateway/middleware/error_handler.py`
- Create: `backend/src/gateway/exceptions.py`

**Description:** Centralized error handling with proper HTTP status codes.

---

## Execution Summary

| Phase | Tasks | Priority | Estimated Tests |
|-------|-------|----------|-----------------|
| Phase 1: Backend Services | 5 | P0 | ~50 tests |
| Phase 2: Skills | 5 | P0 | ~40 tests |
| Phase 3: Gateway API | 5 | P1 | ~35 tests |
| Phase 4: Frontend | 5 | P1 | ~20 tests |
| Phase 5: Integration | 2 | P2 | ~15 tests |
| Phase 6: Documentation | 3 | P3 | N/A |
| Phase 7: Security | 3 | P2 | ~15 tests |

**Total:** 28 tasks, ~175 additional tests expected

---

## Red Flags to Watch

1. **Never skip tests** - Every implementation must have corresponding tests
2. **Always run full test suite** after each task
3. **Check for regressions** - Ensure existing tests still pass
4. **Validate imports** - Make sure all imports work after refactoring
5. **Check types** - Run mypy or pyright for type checking
6. **Review security** - No hardcoded secrets, validate all inputs

---

## Getting Started

To begin execution, choose:

1. **Subagent-Driven (this session)** - Use `superpowers:subagent-driven-development`
2. **Parallel Session (separate)** - Use `superpowers:executing-plans` in new session

Which approach would you like to use?
