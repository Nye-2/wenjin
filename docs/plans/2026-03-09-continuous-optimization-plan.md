# AcademiaGPT v2 Continuous Optimization Plan

> **For Claude:** Autonomous execution plan. No user interaction required. Execute tasks sequentially with review loops.

**Goal:** Complete all remaining features, optimize code quality, achieve 400+ tests, production-ready state.

**Current State:** 281 tests passing, 7/28 tasks completed from previous plan.

**Execution Mode:** Autonomous loop - implement → test → review → optimize → commit → next task

---

## Execution Principles

1. **Never ask user questions** - Make reasonable decisions autonomously
2. **Always write tests** - Minimum 10 tests per feature
3. **Always run full test suite** - Catch regressions immediately
4. **Commit after each task** - Atomic, reviewable commits
5. **Review own code** - Self-check before marking complete
6. **Fix issues immediately** - Don't leave broken tests

---

## Phase 1: Backend Services Completion (Priority: P0)

### Task 1.4: Artifact Service
**Files:** `src/academic/services/artifact_service.py`, `tests/academic/services/test_artifact_service.py`
**Methods:** create, get, list_by_workspace, update, delete, list_by_type
**Tests:** 15+

### Task 1.5: Paper Service
**Files:** `src/academic/services/paper_service.py`, `tests/academic/services/test_paper_service.py`
**Methods:** create, get, get_by_doi, list_by_workspace, update, delete, search
**Tests:** 15+

---

## Phase 2: Skill Implementations (Priority: P0)

### Task 2.2: Deep Research Skill
**Files:** `src/skills/implementations/deep_research.py`, `tests/skills/implementations/test_deep_research.py`
**Features:** Literature search, gap analysis, idea generation
**Tests:** 12+

### Task 2.3: Framework Designer Skill
**Files:** `src/skills/implementations/framework_designer.py`, `tests/skills/implementations/test_framework_designer.py`
**Features:** Abstract generation, outline creation
**Tests:** 12+

### Task 2.4: Fullpaper Writer Skill
**Files:** `src/skills/implementations/fullpaper_writer.py`, `tests/skills/implementations/test_fullpaper_writer.py`
**Features:** Section writing, citation management
**Tests:** 12+

### Task 2.5: Literature Review Skill
**Files:** `src/skills/implementations/literature_review.py`, `tests/skills/implementations/test_literature_review.py`
**Features:** Synthesis, comparison matrix
**Tests:** 12+

---

## Phase 3: Gateway API Routers (Priority: P1)

### Task 3.2: Workspaces Router
**Files:** `src/gateway/routers/workspaces.py`, `tests/gateway/routers/test_workspaces.py`
**Endpoints:** GET/POST/PUT/DELETE /workspaces, GET /workspaces/{id}/papers
**Tests:** 15+

### Task 3.3: Papers Router
**Files:** `src/gateway/routers/papers.py`, `tests/gateway/routers/test_papers.py`
**Endpoints:** GET/POST/PUT/DELETE /papers, POST /papers/upload
**Tests:** 15+

### Task 3.4: Artifacts Router
**Files:** `src/gateway/routers/artifacts.py`, `tests/gateway/routers/test_artifacts.py`
**Endpoints:** GET/POST/PUT/DELETE /artifacts
**Tests:** 12+

---

## Phase 4: Frontend Implementation (Priority: P1)

### Task 4.1: Authentication Pages
**Files:** `frontend/app/(auth)/login/page.tsx`, `frontend/app/(auth)/register/page.tsx`, `frontend/stores/auth.ts`
**Features:** Login form, register form, auth state management
**Tests:** Component rendering tests

### Task 4.2: Workspace Management UI
**Files:** `frontend/components/workspace/workspace-create-modal.tsx`, `frontend/components/workspace/workspace-settings.tsx`
**Features:** Create workspace modal, workspace list, settings
**Tests:** Component tests

### Task 4.3: Paper Upload UI
**Files:** `frontend/components/paper/paper-upload.tsx`, `frontend/components/paper/paper-list.tsx`
**Features:** Drag-drop upload, paper list, paper detail view
**Tests:** Component tests

### Task 4.4: Chat Interface Polish
**Files:** `frontend/components/chat/message-list.tsx`, `frontend/components/chat/message-input.tsx`
**Features:** Message rendering, input with skill selector
**Tests:** Component tests

### Task 4.5: Knowledge Panel
**Files:** `frontend/components/artifact/artifact-list.tsx`, `frontend/components/artifact/artifact-card.tsx`
**Features:** Artifact list, artifact cards, artifact detail
**Tests:** Component tests

---

## Phase 5: Integration Tests (Priority: P2)

### Task 5.1: API Integration Tests
**Files:** `tests/integration/test_auth_flow.py`, `tests/integration/test_workspace_flow.py`, `tests/integration/test_paper_flow.py`
**Tests:** Full API flow tests (register → login → create workspace → add paper)
**Count:** 20+

### Task 5.2: Agent Integration Tests
**Files:** `tests/integration/test_agent_with_middlewares.py`, `tests/integration/test_skill_execution.py`
**Tests:** Agent pipeline tests, skill execution tests
**Count:** 15+

---

## Phase 6: Code Quality & Review (Priority: P2)

### Task 6.1: Linting and Type Checking
**Actions:** Run ruff, fix linting issues, run mypy, fix type errors
**Goal:** Zero linting errors, zero type errors

### Task 6.2: Code Review - Services
**Actions:** Review all service files, identify code smells, refactor if needed
**Files:** extraction_service.py, user_service.py, workspace_service.py, artifact_service.py, paper_service.py

### Task 6.3: Code Review - Routers
**Actions:** Review all router files, ensure consistency, add error handling
**Files:** auth.py, workspaces.py, papers.py, artifacts.py

### Task 6.4: Code Review - Skills
**Actions:** Review all skill implementations, ensure consistency with base classes
**Files:** deep_research.py, framework_designer.py, fullpaper_writer.py, literature_review.py

---

## Phase 7: Performance Optimization (Priority: P3)

### Task 7.1: Database Query Optimization
**Actions:** Review queries, add missing indexes, optimize N+1 queries
**Files:** All service files

### Task 7.2: Caching Implementation
**Actions:** Add Redis caching for frequently accessed data
**Files:** workspace_service.py, paper_service.py

### Task 7.3: Rate Limiting Middleware
**Files:** `src/gateway/middleware/rate_limit.py`
**Features:** IP-based rate limiting, Redis-backed

---

## Phase 8: Documentation (Priority: P3)

### Task 8.1: API Documentation
**Actions:** Add OpenAPI descriptions, add response examples
**Files:** All router files

### Task 8.2: README Updates
**Files:** `backend/README.md`, `frontend/README.md`, root `README.md`
**Content:** Setup, development, deployment instructions

### Task 8.3: Deployment Guide
**Files:** `docs/deployment.md`
**Content:** Docker Compose setup, environment variables, production config

---

## Phase 9: Final Review & Polish (Priority: P4)

### Task 9.1: Full Test Suite Review
**Actions:** Run all tests, fix flaky tests, ensure 100% pass rate
**Goal:** 400+ tests passing

### Task 9.2: Security Audit
**Actions:** Review auth implementation, check for SQL injection, XSS vulnerabilities
**Files:** All routers, all services

### Task 9.3: Performance Testing
**Actions:** Load test API endpoints, identify bottlenecks
**Tools:** locust or pytest-benchmark

---

## Execution Order

```
Phase 1 (Services) → Phase 2 (Skills) → Phase 3 (Routers) → Phase 4 (Frontend)
    ↓
Phase 5 (Integration Tests) → Phase 6 (Code Quality) → Phase 7 (Performance)
    ↓
Phase 8 (Documentation) → Phase 9 (Final Review)
```

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Test Count | 281 | 400+ |
| Code Coverage | ~60% | 80%+ |
| Linting Errors | Unknown | 0 |
| Type Errors | Unknown | 0 |
| API Endpoints | 4 | 20+ |
| Skills Implemented | 0 (framework only) | 4 |
| Frontend Pages | 3 | 10+ |

---

## Autonomous Execution Loop

For each task:
1. Read existing code/context
2. Implement feature
3. Write comprehensive tests
4. Run full test suite
5. Fix any failures
6. Self-review code quality
7. Commit with descriptive message
8. Move to next task

**Start immediately. No user interaction required.**
