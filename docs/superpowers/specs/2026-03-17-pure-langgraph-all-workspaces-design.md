# Pure LangGraph for All Workspaces

**Date**: 2026-03-17
**Status**: Draft
**Author**: AI Agent (brainstorming session)

## 1. Overview

Migrate all 5 workspace types from a LangGraph-first + Handler-fallback architecture to a **pure LangGraph** architecture. This involves:

1. Creating a unified `workspace_lead_agent.py` to replace `thesis_lead_agent.py`
2. Implementing 9 new LangGraph sub-graphs for SCI, Proposal, Software Copyright, and Patent workspaces
3. Removing all handler files and fallback paths
4. Updating dispatch logic, tests, and artifact mappings

### Decision Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Fallback strategy | Remove Handler fallback, pure LangGraph | Eliminate dual code paths; reduce maintenance |
| Scope | All 4 workspaces at once (9 features) | One consistent migration |
| Complexity | Same as Thesis (multi-phase pipeline) | Full LLM-driven capabilities |
| Handler disposition | Delete completely | No dead code |
| Architecture | Unified Lead Agent + lazy loading | Code reuse + workspace isolation |

## 2. Architecture

### 2.1 New Execution Chain

```
API Request (any workspace)
  |
  v
workspace_feature_handler.execute_workspace_feature()
  +-- identify workspace_type + feature_id
  +-- workspace_lead_agent.execute_feature_graph(workspace_type, feature_id, payload)
  |     +-- _ensure_graphs_loaded(workspace_type)   <-- lazy load per workspace
  |     +-- _load_memory(user_id, workspace_id)      <-- workspace-scoped memory
  |     +-- _build_initial_state(workspace_type, payload, memory_text)
  |     +-- graph_fn(initial_state, payload)          <-- execute graph
  +-- _persist_artifacts(...)
  +-- _schedule_memory_extraction(...)
  +-- _wrap_standard_result(...)
  |
  v
Standardized Result -> Frontend
```

### 2.2 Unified Lead Agent (`workspace_lead_agent.py`)

Replaces `thesis_lead_agent.py`. Key design:

```python
_FEATURE_GRAPH_REGISTRY: dict[str, Callable] = {}
_LOADED_WORKSPACES: set[str] = set()

def register_feature_graph(feature_id: str, workspace_type: str | None = None):
    """Register a graph function.
    Key: "{workspace_type}.{feature_id}" or "{feature_id}" for backward compat.
    """

def _ensure_graphs_loaded(workspace_type: str) -> None:
    """Lazy-load graph modules per workspace type.
    Uses importlib.import_module(f"src.agents.graphs.{workspace_type}")
    with per-workspace try/except isolation.
    """

async def execute_feature_graph(
    workspace_type: str,
    feature_id: str,
    payload: dict[str, Any],
    *,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Unified entry point for all workspace graph execution.
    Lookup order: "{workspace_type}.{feature_id}" -> "{feature_id}" (compat)
    """
```

### 2.3 Lazy Loading Isolation

Each workspace's graphs are loaded independently:

```python
def _ensure_graphs_loaded(workspace_type: str) -> None:
    if workspace_type in _LOADED_WORKSPACES:
        return
    try:
        importlib.import_module(f"src.agents.graphs.{workspace_type}")
    except ImportError:
        logger.warning("Graphs for workspace '%s' not available", workspace_type)
    _LOADED_WORKSPACES.add(workspace_type)
```

A bug in `sci/writing.py` will not prevent `thesis` graphs from loading.

### 2.4 Special Task Type Routing: `thesis_generation` and `deep_research`

The codebase has **three** dispatch paths in `task/tasks/base.py`:

1. `task_type="workspace_feature"` → `execute_workspace_feature()` — **primary migration target**
2. `task_type="thesis_generation"` → `execute_thesis_generation()` — **special thesis routing**
3. `task_type="deep_research"` → LangGraph first, then skill handler fallback — **special thesis routing**

#### `thesis_generation` Path

`execute_thesis_generation()` handles multiple actions:
- `generate_outline` — calls `thesis_writing_service.build_outline_payload()`
- `write_chapter` — calls `thesis_writing_service.build_chapter_payload()`
- `write_all` — calls `run_thesis_workflow_request()` (full thesis workflow runner)
- `review_section` / `revise_section` / `review_and_revise` — routes to `thesis_writing` LangGraph sub-graph

**Decision**: `execute_thesis_generation()` is **retained and refactored**:
- The `_THESIS_WRITING_LANGGRAPH_ACTIONS` routing (review/revise) continues to use `workspace_lead_agent.execute_feature_graph("thesis", "thesis_writing", ...)`
- The `generate_outline`, `write_chapter`, `write_all` actions remain in `execute_thesis_generation()` as they use the thesis workflow runner, which is a distinct subsystem (not a handler)
- Remove only the Handler fallback from `execute_workspace_feature()`, not from `execute_thesis_generation()`

#### `deep_research` Path

`deep_research` in `base.py` currently: LangGraph first → skill handler fallback.

**Decision**: Remove the skill handler fallback. After migration:
- `deep_research` dispatches directly to `workspace_lead_agent.execute_feature_graph("thesis", "deep_research", ...)`
- On failure, raise the exception (no silent fallback to skill handler)
- Update `base.py` to use the unified lead agent instead of importing `_try_langgraph_execution` directly

#### Existing Thesis Graphs: Import Path

The 6 existing thesis graphs currently import `register_feature_graph` from `thesis_lead_agent.py`. After migration:
- `thesis_lead_agent.py` will re-export `register_feature_graph` from `workspace_lead_agent.py`
- No changes to existing thesis graph files needed (backward compatible)

### 2.5 Service Layer Disposition

The 6 service files in `workspace_features/services/` contain valuable business logic (LLM calls, JSON parsing, template fallback, payload construction):

| Service File | Lines | Decision |
|-------------|-------|----------|
| `thesis_feature_service.py` | 1061 | **Keep** — called by thesis graphs and `execute_thesis_generation()` |
| `thesis_writing_service.py` | 165 | **Keep** — called by `execute_thesis_generation()` |
| `sci_feature_service.py` | 798 | **Keep** — new SCI graphs will call these functions |
| `proposal_feature_service.py` | 720 | **Keep** — new Proposal graphs will call these functions |
| `patent_feature_service.py` | 599 | **Keep** — new Patent graphs will call these functions |
| `software_copyright_feature_service.py` | 427 | **Keep** — new SW Copyright graphs will call these functions |

**Rationale**: LangGraph graphs orchestrate multi-phase pipelines. Within each phase, they call existing service functions for LLM interactions, template fallback, and payload construction. This avoids rewriting ~3500 lines of battle-tested service logic.

**Graph-Service relationship**:
```
LangGraph Graph (new)
  +-- Phase 1: param normalization (graph code)
  +-- Phase 2: service.build_xxx_payload()  <-- reuse existing service
  +-- Phase 3: cross-validation (graph code, new LLM call)
  +-- Phase 4: assembly (graph code)
```

The service layer provides the "single LLM call + template fallback" building block. The graph layer adds multi-phase orchestration, parallel execution, cross-validation, and memory injection on top.

### 2.6 Error Handling / Degradation Strategy

Since handlers with template_fallback are being removed from the dispatch path, each LangGraph graph must handle failures internally:

**Per-phase error handling**:
- Each phase wraps its LLM call in try/except
- On LLM failure, the phase falls back to the service layer's built-in `template_fallback` mode
- The service functions already implement this: they return `generation_mode: "template_fallback"` on failure

**Graph-level generation mode**:
```python
# At graph completion, detect overall generation mode
step_results = {"phase2_llm": True, "phase3_validation": False}
generation_mode = detect_generation_mode(step_results)
# "llm", "partial_llm", or "template_fallback"
```

**No silent swallowing**: Errors are logged with context and recorded in `data.generation_error`.

## 3. LangGraph Sub-Graph Designs

### 3.1 SCI Workspace (3 graphs)

#### `sci/literature_search.py` — Literature Search

**Pipeline (4 phases):**

| Phase | Operation | Input | Output |
|-------|-----------|-------|--------|
| 1 | Query normalization + DB literature load | query, discipline | existing_papers, normalized_query |
| 2 | Parallel LLM (keyword expansion + literature recommendation + trend analysis) | Phase 1 output + memory | candidate_papers, expanded_keywords, trends |
| 3 | Relevance ranking + dedup | Phase 2 output | ranked_papers |
| 4 | Structured output assembly | All phases | papers, top_hits, filters, summary |

- **Output language**: English
- **External queries**: `LiteratureService` (load workspace literature)
- **Artifact type**: `LITERATURE_SEARCH_RESULTS`
- **Memory injection**: Research direction, literature preferences

#### `sci/paper_analysis.py` — Paper Analysis

**Pipeline (4 phases):**

| Phase | Operation | Input | Output |
|-------|-----------|-------|--------|
| 1 | Paper data loading (from paper_id or abstract) | paper_id, paper_title, paper_abstract | full_paper_data |
| 2 | Parallel LLM analysis (methodology + experiments + innovations + conclusions) | Phase 1 | section_analyses |
| 3 | Quality assessment (rigor, completeness, contribution) | Phase 2 | quality_scores |
| 4 | Synthesis + recommendations | All phases | structured_analysis |

- **Output language**: English
- **External queries**: `PaperService` (load paper details)
- **Artifact type**: `PAPER_ANALYSIS`
- **Memory injection**: Discipline expertise

#### `sci/writing.py` — SCI Paper Writing

**Pipeline (4 phases):**

| Phase | Operation | Input | Output |
|-------|-----------|-------|--------|
| 1 | Context artifact loading (analysis, search, drafts) | workspace_id | context_summaries |
| 2 | Section planning (based on section_type) | section_type, context | section_structure |
| 3 | LLM content generation (8 section types supported) | Phase 2 + memory | draft_content |
| 4 | Academic language polish + reference integration | Phase 3 | final_content, references |

- **Output language**: English (SCI is always English)
- **External queries**: `ArtifactService` (load context artifacts)
- **Artifact type**: `PAPER_DRAFT`
- **Supported section_types**: abstract, introduction, related_work, methodology, experiments, results, discussion, conclusion

### 3.2 Proposal Workspace (2 graphs)

#### `proposal/proposal_outline.py` — Proposal Outline

**Pipeline (4 phases):**

| Phase | Operation | Input | Output |
|-------|-----------|-------|--------|
| 1 | Parameter normalization (proposal_type alias mapping, period validation) | params | normalized_config |
| 2 | Parallel LLM generation of 5 main sections | topic, proposal_type, period + memory | sections[] |
| 3 | Milestone planning + risk analysis | sections + period | milestones[], risks[] |
| 4 | Cross-section coherence check + structured output | All phases | final_outline |

- **Output language**: Chinese
- **External queries**: None (pure LLM)
- **Artifact type**: `PROPOSAL` (existing enum value)
- **5 sections**: 立项依据, 研究目标与内容, 研究方案与技术路线, 计划进度, 经费预算

#### `proposal/background_research.py` — Background Research

**Pipeline (4 phases):**

| Phase | Operation | Input | Output |
|-------|-----------|-------|--------|
| 1 | Keyword expansion + scope definition | keywords, industry_scope, time_range | search_config |
| 2 | Parallel LLM generation of 3 research sections | Phase 1 + memory | sections[] |
| 3 | Reference supplementation + cross-validation | Phase 2 | validated_sections, references[] |
| 4 | Comprehensive research report assembly | All phases | final_report |

- **Output language**: Chinese
- **External queries**: None
- **Artifact type**: `BACKGROUND_RESEARCH`
- **3 sections**: 现状综述, 问题清单, 可行技术方向

### 3.3 Software Copyright Workspace (2 graphs)

#### `software_copyright/copyright_materials.py` — Copyright Materials

**Pipeline (4 phases):**

| Phase | Operation | Input | Output |
|-------|-----------|-------|--------|
| 1 | Software info collection (name, version, publish date, etc.) | params | software_profile |
| 2 | LLM material list generation + module description | Phase 1 + memory | materials_list, module_desc |
| 3 | Completeness check + missing item prompts | Phase 2 | validated_materials, warnings[] |
| 4 | Structured output (checklist + suggestions) | All phases | final_materials |

- **Output language**: Chinese
- **External queries**: None
- **Artifact type**: `COPYRIGHT_MATERIALS`

#### `software_copyright/technical_description.py` — Technical Description

**Pipeline (4 phases):**

| Phase | Operation | Input | Output |
|-------|-----------|-------|--------|
| 1 | Existing artifact loading (copyright_materials -> extract defaults) | workspace_id | defaults, software_profile |
| 2 | Parallel LLM generation of 6 technical sections | Phase 1 + params + memory | sections[] |
| 3 | Technical consistency validation (module <-> flow <-> deployment cross-check) | Phase 2 | validated_sections |
| 4 | Format normalization + structured output | Phase 3 | final_description |

- **Output language**: Chinese
- **External queries**: `ArtifactService` (load COPYRIGHT_MATERIALS artifact)
- **Artifact type**: `TECHNICAL_DESCRIPTION`
- **6 sections**: 系统概述, 模块设计, 数据流程, 部署架构, 安全与权限, 操作步骤

### 3.4 Patent Workspace (2 graphs)

#### `patent/patent_outline.py` — Patent Outline

**Pipeline (4 phases):**

| Phase | Operation | Input | Output |
|-------|-----------|-------|--------|
| 1 | Innovation extraction + technical field classification | params + memory | innovation_points, tech_field |
| 2 | Parallel LLM generation of 5 specification sections | Phase 1 | sections[] |
| 3 | Claims drafting (independent + dependent claims) | Phase 2 + innovation_points | claims_draft |
| 4 | Evidence checklist + structured output | All phases | final_outline |

- **Output language**: Chinese
- **External queries**: None
- **Artifact type**: `PATENT_OUTLINE`
- **5 sections**: 技术领域, 背景技术, 发明内容, 附图说明, 具体实施方式

#### `patent/prior_art_search.py` — Prior Art Search

**Pipeline (4 phases):**

| Phase | Operation | Input | Output |
|-------|-----------|-------|--------|
| 1 | Search strategy construction (keywords + IPC codes + DB selection) | params | search_config |
| 2 | Parallel LLM analysis (prior art comparison + novelty risk assessment) | Phase 1 + memory | comparison_table, novelty_risks |
| 3 | Avoidance suggestions generation | Phase 2 | avoidance_suggestions[] |
| 4 | Next steps + structured output | All phases | final_analysis |

- **Output language**: Chinese
- **External queries**: None
- **Artifact type**: `PRIOR_ART_REPORT` (existing enum value)

## 4. Shared Utilities

### 4.1 Location

`backend/src/agents/graphs/_shared/utils.py`

### 4.2 Functions

```python
# JSON parsing (from thesis patterns)
def parse_json_response(text: str) -> dict[str, Any] | None
def parse_json_list_response(text: str) -> list[dict[str, Any]] | None

# Model creation with safety
async def create_model_safe(
    model_id: str | None = None,
    temperature: float = 0.3,
) -> BaseChatModel | None

# Generation mode detection
def detect_generation_mode(step_results: dict[str, bool]) -> str
    # Returns "llm", "partial_llm", or "template_fallback"

# Memory loading and formatting
async def build_memory_context(user_id: str | None, workspace_id: str | None) -> str

# Text utilities
def truncate_text(text: str, max_len: int = 280) -> str
```

## 5. Artifact Mapping

### 5.1 Artifact Types Status

All required artifact types already exist in `ArtifactType` enum (`backend/src/artifacts/types.py`):

| Artifact Type | Enum Value | Status |
|--------------|------------|--------|
| `LITERATURE_SEARCH_RESULTS` | `literature_search_results` | Already exists |
| `PAPER_ANALYSIS` | `paper_analysis` | Already exists |
| `PAPER_DRAFT` | `paper_draft` | Already exists |
| `PROPOSAL` | `proposal` | Already exists (use for proposal_outline) |
| `BACKGROUND_RESEARCH` | `background_research` | Already exists |
| `COPYRIGHT_MATERIALS` | `copyright_materials` | Already exists |
| `TECHNICAL_DESCRIPTION` | `technical_description` | Already exists |
| `PATENT_OUTLINE` | `patent_outline` | Already exists |
| `PRIOR_ART_REPORT` | `prior_art_report` | Already exists |

No new enum values needed.

### 5.2 Artifact Mapping Table

| Workspace | feature_id | Artifact Type | Title Pattern |
|-----------|-----------|---------------|---------------|
| SCI | `literature_search` | `LITERATURE_SEARCH_RESULTS` | `{name} - Literature Search` |
| SCI | `paper_analysis` | `PAPER_ANALYSIS` | `{name} - Paper Analysis` |
| SCI | `writing` | `PAPER_DRAFT` | `{name} - {section_type}` |
| Proposal | `proposal_outline` | `PROPOSAL` | `{name} - 申报书大纲` |
| Proposal | `background_research` | `BACKGROUND_RESEARCH` | `{name} - 背景调研报告` |
| SW Copyright | `copyright_materials` | `COPYRIGHT_MATERIALS` | `{name} - 著作权材料清单` |
| SW Copyright | `technical_description` | `TECHNICAL_DESCRIPTION` | `{name} - 技术说明书` |
| Patent | `patent_outline` | `PATENT_OUTLINE` | `{name} - 专利说明书框架` |
| Patent | `prior_art_search` | `PRIOR_ART_REPORT` | `{name} - 现有技术分析` |

### 5.3 `_build_langgraph_artifact_drafts()` Extension

This function in `workspace_feature_handler.py` needs to handle all workspace types, not just thesis. The mapping logic should be workspace-type-aware.

## 6. File Changes

### 6.1 New Files (14)

```
backend/src/agents/workspace_lead_agent.py
backend/src/agents/graphs/_shared/__init__.py
backend/src/agents/graphs/_shared/utils.py
backend/src/agents/graphs/sci/__init__.py
backend/src/agents/graphs/sci/literature_search.py
backend/src/agents/graphs/sci/paper_analysis.py
backend/src/agents/graphs/sci/writing.py
backend/src/agents/graphs/proposal/__init__.py
backend/src/agents/graphs/proposal/proposal_outline.py
backend/src/agents/graphs/proposal/background_research.py
backend/src/agents/graphs/software_copyright/__init__.py
backend/src/agents/graphs/software_copyright/copyright_materials.py
backend/src/agents/graphs/software_copyright/technical_description.py
backend/src/agents/graphs/patent/__init__.py
backend/src/agents/graphs/patent/patent_outline.py
backend/src/agents/graphs/patent/prior_art_search.py
```

### 6.2 Modified Files (5)

```
backend/src/task/handlers/workspace_feature_handler.py
  - Remove fallback logic in execute_workspace_feature()
  - All workspace_feature task_type goes through workspace_lead_agent
  - Extend _build_langgraph_artifact_drafts() for all workspace types
  - Remove _ensure_graphs_loaded() (moved to workspace_lead_agent)
  - Keep execute_thesis_generation() (refactor to use workspace_lead_agent for review/revise actions)

backend/src/task/tasks/base.py
  - Update deep_research dispatch to use workspace_lead_agent directly
  - Remove skill handler fallback for deep_research
  - Update imports

backend/src/workspace_features/runtime.py
  - Remove register_feature_handler() and handler dispatch logic
  - Remove WorkspaceFeatureExecutionContext (no longer needed)
  - Keep utility functions if any are used by service layer

backend/src/agents/thesis_lead_agent.py
  - Re-export register_feature_graph and execute_thesis_feature_graph from workspace_lead_agent
  - Maintains backward compat for existing thesis graph imports

backend/src/workspace_features/__init__.py
  - Remove exports of handler-related functions (execute_registered_feature, etc.)
```

### 6.3 Deleted Files (5)

```
backend/src/workspace_features/handlers/thesis.py
backend/src/workspace_features/handlers/sci.py
backend/src/workspace_features/handlers/proposal.py
backend/src/workspace_features/handlers/patent.py
backend/src/workspace_features/handlers/software_copyright.py
```

### 6.4 New Test Files (10)

```
backend/tests/agents/test_workspace_lead_agent.py
backend/tests/agents/graphs/sci/test_literature_search.py
backend/tests/agents/graphs/sci/test_paper_analysis.py
backend/tests/agents/graphs/sci/test_writing.py
backend/tests/agents/graphs/proposal/test_proposal_outline.py
backend/tests/agents/graphs/proposal/test_background_research.py
backend/tests/agents/graphs/software_copyright/test_copyright_materials.py
backend/tests/agents/graphs/software_copyright/test_technical_description.py
backend/tests/agents/graphs/patent/test_patent_outline.py
backend/tests/agents/graphs/patent/test_prior_art_search.py
```

### 6.5 Modified Test Files

```
backend/tests/task/test_workspace_feature_handler.py
  - Remove fallback tests
  - Add pure LangGraph path tests for all workspaces
  - Update execute_thesis_generation tests (keep action routing tests)

backend/tests/task/test_langgraph_dispatch.py
  - Update to use workspace_lead_agent
  - Add dispatch tests for all workspace types

backend/tests/workspace_features/test_five_workspace_smoke.py
  - Verify all 5 workspaces go through LangGraph

backend/tests/workspace_features/test_workspace_e2e_matrix.py
  - Update E2E matrix

backend/tests/task/test_thesis_handlers.py
  - Delete (handlers no longer exist)

backend/tests/task/test_workspace_feature_runtime.py
  - Update: remove handler-related tests

backend/tests/task/test_workspace_feature_registry.py
  - Verify: should pass without changes (registry unchanged)
```

### 6.6 Playbook-Required Test Matrix

Per `workspace-ai-modification-playbook.md` Section 5, ALL of these must pass:

```bash
pytest -q tests/agents/graphs/thesis
pytest -q tests/agents/graphs/sci
pytest -q tests/agents/graphs/proposal
pytest -q tests/agents/graphs/software_copyright
pytest -q tests/agents/graphs/patent
pytest -q tests/task/test_workspace_feature_handler.py
pytest -q tests/task/test_langgraph_dispatch.py
pytest -q tests/task/test_workspace_feature_runtime.py
pytest -q tests/task/test_workspace_feature_registry.py
pytest -q tests/academic/services/test_artifact_versioning.py
pytest -q tests/services/test_knowledge_service.py tests/services/test_memory_compaction.py
pytest -q tests/agents/middleware/test_memory.py
pytest -q tests/workspace_features/test_five_workspace_smoke.py tests/workspace_features/test_workspace_e2e_matrix.py
```

## 7. Migration Strategy

### 7.1 Execution Order (tests pass at every step)

```
Step 1: Create workspace_lead_agent.py
  - Extract common logic from thesis_lead_agent.py
  - Keep thesis graphs working via backward-compat re-exports in thesis_lead_agent.py
  - Add lazy-loading per workspace type

Step 2: Create shared utilities (agents/graphs/_shared/utils.py)

Step 3: Implement 9 new graphs + unit tests (per workspace)
  - Each graph + test implemented together
  - Run graph-specific tests after each
  - Service layer functions are CALLED, not rewritten

Step 4: Update workspace_feature_handler.py
  - execute_workspace_feature(): all workspace types use workspace_lead_agent
  - Remove "thesis" workspace_type check and handler fallback path
  - Extend _build_langgraph_artifact_drafts() for all workspace types
  - Keep execute_thesis_generation() (refactor review/revise to use workspace_lead_agent)

Step 5: Update base.py deep_research dispatch
  - Use workspace_lead_agent.execute_feature_graph() directly
  - Remove skill handler fallback

Step 6: Delete handler files + handler-specific tests
  - handlers/thesis.py, sci.py, proposal.py, patent.py, software_copyright.py
  - test_thesis_handlers.py

Step 7: Clean up runtime.py
  - Remove handler registration/dispatch code
  - Keep any utility functions needed by service layer

Step 8: Update smoke, E2E, and dispatch tests

Step 9: Run full playbook-required test matrix (Section 6.6)

Step 10: Update workspace-ai-modification-playbook.md
  - Reflect pure LangGraph architecture
  - Update Quick Decision Guide (remove handler references)
  - Update "How To Add Or Modify A Workspace Feature" section
```

### 7.2 Rollback Plan

If issues arise after migration:
- Handler files are in git history
- `workspace_feature_handler.py` can be reverted to re-enable fallback
- Each workspace can be individually reverted by removing its graph module

## 8. Frontend Impact

**Zero frontend changes required.**

Frontend consumes standardized task result payloads:
- `success`, `message`, `artifacts`, `refresh_targets`, `data`

This schema is identical between LangGraph and Handler paths.

**Verification needed**: Ensure LangGraph result `data` field keys are compatible with existing `WorkspaceResultViewModel` mapping logic in `WorkspaceResultPanel.tsx`.

## 9. Non-Negotiable Contracts (from playbook)

All contracts from `workspace-ai-modification-playbook.md` remain enforced:

1. **Feature Result Payload Contract** — All graph results wrapped with `success`, `feature_id`, `feature_name`, `workspace_type`, `handler_key`, `message`, `artifacts`, `refresh_targets`, `data`
2. **Artifact Persistence Contract** — App-level lock + DB unique constraint preserved
3. **Knowledge Service SSOT** — Single `KnowledgeService` at `src/services/knowledge_service.py`
4. **Memory Non-Blocking** — Async extraction, failures don't block feature completion
5. **Frontend Contracts** — `TaskFeedbackBanner`, `WorkspaceResultPanel`, `refresh_targets` unchanged

## 10. Success Criteria

- [ ] All `workspace_feature` task_type features execute via LangGraph (no handler fallback)
- [ ] `thesis_generation` task_type: `execute_thesis_generation()` refactored, review/revise use workspace_lead_agent
- [ ] `deep_research` task_type: dispatches to workspace_lead_agent, no skill handler fallback
- [ ] 9 new graph unit tests pass
- [ ] `workspace_lead_agent` unit tests pass
- [ ] Existing thesis graph tests pass (no regression)
- [ ] 5-workspace smoke test passes
- [ ] E2E matrix test passes
- [ ] Full playbook-required test matrix passes (Section 6.6)
- [ ] Feature result payload contract validated for all workspaces
- [ ] Artifact versioning works for all artifact types
- [ ] Memory extraction triggers for all workspaces (non-blocking)
- [ ] Frontend renders results correctly (no UI changes needed)
- [ ] No handler files remain in `workspace_features/handlers/`
- [ ] Service layer files preserved and functional
- [ ] `workspace-ai-modification-playbook.md` updated
