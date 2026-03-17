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
- **Artifact type**: `PROPOSAL_OUTLINE`
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
- **Artifact type**: `PRIOR_ART_ANALYSIS`

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

### 5.1 New Artifact Types Needed

Check `ArtifactType` enum and add if missing:
- `LITERATURE_SEARCH_RESULTS`
- `PAPER_ANALYSIS`
- `PROPOSAL_OUTLINE`
- `BACKGROUND_RESEARCH`
- `COPYRIGHT_MATERIALS`
- `TECHNICAL_DESCRIPTION`
- `PATENT_OUTLINE`
- `PRIOR_ART_ANALYSIS`

### 5.2 Artifact Mapping Table

| Workspace | feature_id | Artifact Type | Title Pattern |
|-----------|-----------|---------------|---------------|
| SCI | `literature_search` | `LITERATURE_SEARCH_RESULTS` | `{name} - Literature Search` |
| SCI | `paper_analysis` | `PAPER_ANALYSIS` | `{name} - Paper Analysis` |
| SCI | `writing` | `PAPER_DRAFT` | `{name} - {section_type}` |
| Proposal | `proposal_outline` | `PROPOSAL_OUTLINE` | `{name} - 申报书大纲` |
| Proposal | `background_research` | `BACKGROUND_RESEARCH` | `{name} - 背景调研报告` |
| SW Copyright | `copyright_materials` | `COPYRIGHT_MATERIALS` | `{name} - 著作权材料清单` |
| SW Copyright | `technical_description` | `TECHNICAL_DESCRIPTION` | `{name} - 技术说明书` |
| Patent | `patent_outline` | `PATENT_OUTLINE` | `{name} - 专利说明书框架` |
| Patent | `prior_art_search` | `PRIOR_ART_ANALYSIS` | `{name} - 现有技术分析` |

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

### 6.2 Modified Files (3-4)

```
backend/src/task/handlers/workspace_feature_handler.py
  - Remove fallback logic
  - Use workspace_lead_agent.execute_feature_graph() for all workspaces
  - Extend _build_langgraph_artifact_drafts() for all types
  - Remove _ensure_graphs_loaded() (moved to workspace_lead_agent)

backend/src/workspace_features/runtime.py
  - Remove handler dispatch logic (keep utility functions)

backend/src/artifacts/types.py (if ArtifactType enum needs new values)

backend/src/agents/thesis_lead_agent.py
  - Redirect to workspace_lead_agent or delete
```

### 6.3 Deleted Files (5)

```
backend/src/workspace_features/handlers/thesis.py
backend/src/workspace_features/handlers/sci.py
backend/src/workspace_features/handlers/proposal.py
backend/src/workspace_features/handlers/patent.py
backend/src/workspace_features/handlers/software_copyright.py
```

### 6.4 New Test Files (9)

```
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

backend/tests/workspace_features/test_five_workspace_smoke.py
  - Verify all 5 workspaces go through LangGraph

backend/tests/workspace_features/test_workspace_e2e_matrix.py
  - Update E2E matrix

backend/tests/task/test_thesis_handlers.py
  - Delete or refactor (handlers no longer exist)
```

## 7. Migration Strategy

### 7.1 Execution Order (tests pass at every step)

```
Step 1: Create workspace_lead_agent.py
  - Extract common logic from thesis_lead_agent.py
  - Keep thesis graphs working
  - thesis_lead_agent.py redirects to workspace_lead_agent

Step 2: Create shared utilities (agents/graphs/_shared/utils.py)

Step 3: Implement 9 new graphs + unit tests
  - Each graph + test implemented together
  - Run graph-specific tests after each

Step 4: Update workspace_feature_handler.py
  - All workspaces use LangGraph via workspace_lead_agent
  - Remove "thesis" workspace_type check
  - Remove fallback-to-handler path

Step 5: Delete handler files + handler-specific tests

Step 6: Update smoke and E2E tests

Step 7: Run full test matrix
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

- [ ] All 15 features execute via LangGraph (no handler fallback)
- [ ] 9 new graph unit tests pass
- [ ] Existing thesis graph tests pass (no regression)
- [ ] 5-workspace smoke test passes
- [ ] E2E matrix test passes
- [ ] Feature result payload contract validated for all workspaces
- [ ] Artifact versioning works for all new artifact types
- [ ] Memory extraction triggers for all workspaces (non-blocking)
- [ ] Frontend renders results correctly (no UI changes needed)
- [ ] No handler files remain in codebase
