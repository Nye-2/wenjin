# Agent A LangGraph Implementation Plan

**Date**: 2026-03-17
**Status**: Ready for Implementation
**Scope**: Agent A tasks from handoff document

## Overview

This plan covers Agent A's responsibilities:
- Create shared infrastructure (workspace_lead_agent.py, _shared/utils.py)
- Implement 5 LangGraph sub-graphs (3 for SCI, 2 for Patent)
- Refactor handler and dispatcher code
- Run tests to verify implementation

## Execution Steps

### Step A1: Create Shared Infrastructure

**Files to create:**
- `backend/src/agents/workspace_lead_agent.py`
- `backend/src/agents/graphs/_shared/__init__.py`
- `backend/src/agents/graphs/_shared/utils.py`

**Tasks:**
1. Create `workspace_lead_agent.py`:
   - Extract common logic from `thesis_lead_agent.py`
   - Support composite key `{workspace_type}.{feature_id}`
   - Implement lazy loading per workspace type
   - Create `execute_feature_graph(workspace_type, feature_id, payload, user_id)`

2. Create `_shared/utils.py`:
   - `parse_json_response()` - JSON parsing from LLM responses
   - `create_model_safe()` - Safe model creation with error handling
   - `detect_generation_mode()` - Determine overall generation mode

3. Update `thesis_lead_agent.py`:
   - Re-export from `workspace_lead_agent.py`
   - Maintain backward compatibility

**Verification:**
```bash
pytest -q tests/agents/test_workspace_lead_agent.py
```

### Step A2: Implement SCI Workspace Graphs

**Files to create:**
- `backend/src/agents/graphs/sci/__init__.py`
- `backend/src/agents/graphs/sci/literature_search.py`
- `backend/src/agents/graphs/sci/paper_analysis.py`
- `backend/src/agents/graphs/sci/writing.py`
- `backend/tests/agents/graphs/sci/test_literature_search.py`
- `backend/tests/agents/graphs/sci/test_paper_analysis.py`
- `backend/tests/agents/graphs/sci/test_writing.py`

**Implementation Pattern (per graph):**
1. Import `register_feature_graph` from `workspace_lead_agent`
2. Define graph function with 4-phase pipeline
3. Call existing service functions (from `sci_feature_service.py`)
4. Implement template fallback on LLM failure
5. Return standardized payload with `generation_mode`

**Verification:**
```bash
pytest -q tests/agents/graphs/sci
```

### Step A3: Implement Patent Workspace Graphs

**Files in create:**
- `backend/src/agents/graphs/patent/__init__.py`
- `backend/src/agents/graphs/patent/patent_outline.py`
- `backend/src/agents/graphs/patent/prior_art_search.py`
- `backend/tests/agents/graphs/patent/test_patent_outline.py`
- `backend/tests/agents/graphs/patent/test_prior_art_search.py`

**Implementation Pattern (per graph):**
1. Import `register_feature_graph` from `workspace_lead_agent`
2. Define graph function with 4-phase pipeline
3. Call existing service functions (from `patent_feature_service.py`)
4. Implement template fallback on LLM failure
5. Return standardized payload with `generation_mode`

**Verification:**
```bash
pytest -q tests/agents/graphs/patent
```

### Step A4: Refactor workspace_feature_handler.py

**File to modify:** `backend/src/task/handlers/workspace_feature_handler.py`

**Changes:**
1. Remove `if workspace_type == "thesis"` conditional
2. All workspaces go through `workspace_lead_agent.execute_feature_graph()`
3. Extend `_build_langgraph_artifact_drafts()` for all workspace types
4. Remove `_ensure_graphs_loaded()` function
5. Update `execute_thesis_generation()` to use `workspace_lead_agent`

**Verification:**
```bash
pytest -q tests/task/test_workspace_feature_handler.py
```

### Step A5: Refactor base.py (deep_research path)

**File to modify:** `backend/src/task/tasks/base.py`

**Changes:**
1. Update deep_research dispatch to use `workspace_lead_agent.execute_feature_graph()`
2. Remove skill handler fallback
3. Update imports

**Verification:**
```bash
pytest -q tests/task/test_langgraph_dispatch.py
```

### Step A6: Run Full Test Matrix

**Commands:**
```bash
# Graph unit tests
pytest -q tests/agents/graphs/thesis
pytest -q tests/agents/graphs/sci
pytest -q tests/agents/graphs/patent

# Handler and dispatch tests
pytest -q tests/task/test_workspace_feature_handler.py
pytest -q tests/task/test_langgraph_dispatch.py
pytest -q tests/task/test_workspace_feature_runtime.py
pytest -q tests/task/test_workspace_feature_registry.py

# Infrastructure tests
pytest -q tests/academic/services/test_artifact_versioning.py
pytest -q tests/services/test_knowledge_service.py tests/services/test_memory_compaction.py
pytest -q tests/agents/middleware/test_memory.py

# E2E tests
pytest -q tests/workspace_features/test_five_workspace_smoke.py tests/workspace_features/test_workspace_e2e_matrix.py
```

## Non-Negotiable Contracts

1. Feature Result Payload: success, feature_id, feature_name, workspace_type, handler_key, message, artifacts, refresh_targets, data
2. Artifact versioning: App-level lock + DB unique constraint (workspace_id, type, title, version)
3. Knowledge Service SSOT: Only use src/services/knowledge_service.py
4. Memory Non-Blocking: Async fire-and-forget, failures don't block feature completion
5. Frontend Contracts: TaskFeedbackBanner, WorkspaceResultPanel, refresh_targets unchanged

## Dependencies
- Step A1 must be completed first (other agents may depend on workspace_lead_agent.py)
- Each SCI/Patent graph is independent after Step A1
- Step A4 and A5 should be done after graph implementations
- Step A6 should be done last

## Rollback Plan
- All files are tracked in git
- Can revert individual changes
- Handler files exist in git history if needed
