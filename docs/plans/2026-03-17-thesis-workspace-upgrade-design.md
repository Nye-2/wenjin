# THESIS Workspace Full Upgrade Design

## Goal

Upgrade the THESIS workspace from template-based handlers to a LangGraph multi-agent architecture with deep LLM generation, context memory, and end-to-end feature closure.

## Scope

- **Workspace**: THESIS (6 features, highest complexity, pattern reusable to other 4 workspaces)
- **Three Dimensions**: LangGraph migration + LLM quality upgrade + deep context memory + end-to-end closure

## Current State

| Feature | Handler Type | LLM Calls | Quality |
|---------|-------------|-----------|---------|
| deep_research | ParallelExecutor (3-phase) | Subagent internal | Good |
| literature_management | Handler (template) | 0 | Statistics only |
| opening_research | Handler (template+LLM) | 0-1 | Template fallback dominant |
| thesis_writing | LangGraph workflow | N (per chapter) | Good |
| figure_generation | Handler (template) | 0 | Code generation only |
| compile_export | Handler (template) | 0 | Template assembly only |

**Key gaps**:
- UserKnowledge model defined but never used
- No cross-session context continuity
- Most features produce template-quality output
- Literature search uses LLM synthesis, not real APIs
- Artifacts overwritten without version history

---

## Design: 4 Modules

### Module 1: LangGraph Orchestration Engine Migration

**Architecture**:

```
                     +--- deep_research_graph (3-phase parallel)
                     |
ThesisLeadAgent -----+--- opening_research_graph (search -> analyze -> generate)
  (LangGraph +       |
   Middleware Chain)  +--- thesis_writing_graph (existing + memory injection)
                     |
                     +--- literature_management_graph (scan -> analyze -> report)
                     |
                     +--- figure_generation_graph (plan -> generate -> degrade?)
                     |
                     +--- compile_export_graph (collect -> convert -> compile)
```

**Key decisions**:
1. Create `ThesisLeadAgent` using deer-flow's `create_agent()` factory + middleware chain
2. Each feature = independent `StateGraph` sub-graph, invoked via `task` tool
3. Shared `AcademicAgentState` base schema, feature-specific sub-state extensions
4. Existing handlers retained as fallback (LangGraph failure -> template mode)

**Middleware reuse from deer-flow**:
- Direct reuse: `ThreadDataMiddleware`, `SandboxMiddleware`, `TitleMiddleware`, `DanglingToolCallMiddleware`
- Adapted: `MemoryMiddleware` -> `AcademicMemoryMiddleware` (backed by UserKnowledge DB)
- Not needed: `UploadsMiddleware`, `ViewImageMiddleware`, `ClarificationMiddleware`

**State schema**:

```python
class AcademicAgentState(AgentState):
    messages: Annotated[list[AnyMessage], add_messages]
    sandbox: NotRequired[SandboxState | None]
    thread_data: NotRequired[ThreadDataState | None]

    # Academic extensions
    workspace_id: str
    workspace_type: Literal["thesis", "sci", "proposal", "software_copyright", "patent"]
    discipline: NotRequired[str | None]
    workspace_config: NotRequired[dict | None]
    literature_context: NotRequired[str | None]
    user_memory: NotRequired[list[dict] | None]

    # Artifact management (DB-persisted)
    db_artifacts: Annotated[list[dict], merge_db_artifacts]
    cited_papers: Annotated[list[str], merge_cited_papers]
```

### Module 2: LLM Generation Quality Upgrade

**Per-feature upgrade plan**:

| Feature | Current | Upgraded LLM Pipeline |
|---------|---------|----------------------|
| Literature Management | Pure Counter stats | LLM topic clustering + quality assessment + smart recommendations |
| Opening Research | 1 LLM call for full text | 3-step: research status analysis -> methodology planning -> section generation |
| Thesis Writing | 1 LLM per chapter | + citation planning -> writing -> self-review -> revision loop |
| Figure Generation | Direct code generation | LLM chapter analysis -> figure type/data planning -> code generation |
| Compile Export | Template assembly | LLM consistency review -> abstract/keyword generation -> format optimization |
| Deep Research | Multi-agent parallel | + cross-validation node for result verification |

**Principles**:
- Every LLM node has explicit input/output schema
- All LLM calls retain template fallback (failure doesn't block basic output)
- `temperature=0.3` for academic rigor
- Multi-step reasoning over single-shot generation

### Module 3: Deep Context Memory System

**AcademicMemoryMiddleware**:

```
before_agent():
  1. Load UserKnowledge from DB
     - preference: citation style, language preference
     - knowledge: discipline terms, methodology
     - context: research topic, current progress
     - goal: research objectives, milestones
  2. Inject <academic_memory> into system prompt

after_agent():
  1. Filter conversation messages
  2. LLM extract new knowledge (debounce 30s)
  3. Write to UserKnowledge table
     - Dedup: same category+content updates confidence
     - workspace_context: associate with current workspace
```

**Memory injection**: Top 20 active knowledge items by confidence desc + workspace priority

**Write examples**:
- User selects APA -> `{category: "preference", content: "Prefers APA citation", confidence: 0.95}`
- Repeated abstract edits -> `{category: "behavior", content: "High quality bar for abstracts", confidence: 0.7}`
- Deep Research finds field -> `{category: "context", content: "Research direction: LLM in academic writing", confidence: 0.85}`

#### Memory Compaction (inspired by Claude Code /compact)

**Triggers**:
- Auto: workspace memory entries > 50
- Auto: single feature conversation > 20 turns
- Manual: system/user trigger

**Compaction flow**:
1. Collect all active knowledge (by workspace)
2. LLM merge/dedup/summarize:
   - Similar facts merged into higher confidence entry
   - Low confidence (<0.5) entries archived (is_active=False)
   - Context-type memories generate phase summaries
3. Write back to DB:
   - Merged entries replace originals
   - New `compacted_summary` type entry added
   - Original `created_at` preserved for traceability

**Output**: Workspace research progress panoramic summary + deduplicated knowledge + archived low-confidence entries

### Module 4: End-to-End Feature Closure

| Gap | Fix |
|-----|-----|
| Literature search is LLM-synthesized | Integrate Semantic Scholar SDK + CrossRef API in LangGraph nodes |
| MCP tools limited (3 only) | Add Google Scholar, CNKI, Web of Science MCP tools (lazy-loaded) |
| Artifacts overwritten without version | Add `version` field + `parent_id` chain to Artifact model |
| No execution resume | Leverage LangGraph checkpoint for feature mid-execution recovery |

---

## Implementation Priority

**Phase 1 (Foundation)**: Module 1 core + Module 3 basic
- Create `AcademicAgentState` schema
- Port deer-flow middleware chain
- Build `ThesisLeadAgent` with feature routing
- Implement `AcademicMemoryMiddleware` with UserKnowledge read/write
- Migrate Deep Research from ParallelExecutor to LangGraph sub-graph

**Phase 2 (LLM Upgrade)**: Module 2 for each feature
- Literature Management: LLM analysis nodes
- Opening Research: 3-step generation pipeline
- Figure Generation: LLM-driven planning
- Compile Export: LLM consistency review
- Thesis Writing: self-review + revision loop

**Phase 3 (Closure)**: Module 4 + Module 3 compact
- Real API integration (Semantic Scholar, CrossRef)
- Artifact versioning
- Memory compaction mechanism
- LangGraph checkpoint for execution resume

**Phase 4 (Replication)**: Apply pattern to SCI -> PROPOSAL -> SOFTWARE_COPYRIGHT -> PATENT

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| State schema incompatibility (deer-flow TypedDict vs AcademiaGPT Pydantic) | Unify on TypedDict for state, Pydantic for data structures only |
| Middleware execution order conflicts | Explicitly define Academic middleware priority, document dependencies |
| DB I/O blocking LangGraph execution | Async preload in before_agent, Redis cache layer, connection pool |
| LLM generation quality regression | A/B testing with template baseline, gradual rollout per feature |
| Memory extraction hallucination | Confidence threshold (>= 0.7), human review for high-impact preferences |

## Tech Stack

- LangGraph StateGraph (sub-graphs per feature)
- deer-flow middleware chain (adapted)
- UserKnowledge PostgreSQL model (existing)
- Redis caching (existing infrastructure)
- Semantic Scholar API / CrossRef API
- LangChain chat models (existing `create_chat_model()`)
