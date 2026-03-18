# LangGraph Workspace Architecture

> Last Updated: 2026-03-18
> Status: Completed

## Overview

This document describes the LangGraph-based workspace feature execution system implemented for all workspace types (thesis, sci, patent, proposal, software_copyright).

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           FastAPI Gateway                                 │
│  POST /api/workspace-features/execute                                   │
│  { workspace_type, feature_id, params }                                  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     workspace_feature_handler.py                         │
│  execute_workspace_feature()                                             │
│  └── _try_langgraph_execution()                                          │
│      └── execute_feature_graph()                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     workspace_lead_agent.py                               │
│  • register_feature_graph(feature_id, workspace_type)                   │
│  • execute_feature_graph(workspace_type, feature_id, payload)           │
│  • _ensure_graphs_loaded() - Lazy loading of graph modules              │
│  • _build_system_prompt() - Memory injection                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Workspace Graph Modules                              │
│  src/agents/graphs/                                                       │
│  ├── thesis/          → literature_management, opening_research, ...    │
│  ├── sci/             → literature_search, paper_analysis, writing      │
│  ├── patent/          → patent_outline, prior_art_search                │
│  ├── proposal/        → proposal_outline, background_research           │
│  ├── software_copyright/ → copyright_materials, technical_description   │
│  └── _shared/         → parse_json_response, _normalize_list, ...       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Service Layer                                        │
│  src/workspace_features/services/                                        │
│  ├── thesis_feature_service.py                                           │
│  ├── sci_feature_service.py                                              │
│  ├── patent_feature_service.py                                           │
│  ├── proposal_feature_service.py                                         │
│  └── software_copyright_feature_service.py                               │
└─────────────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. WorkspaceLeadAgent (`workspace_lead_agent.py`)

Central registry and executor for all workspace feature graphs.

```python
# Registration decorator
@register_feature_graph("literature_search", workspace_type="sci")
async def literature_search_graph(initial_state, payload):
    ...

# Execution
result = await execute_feature_graph(
    workspace_type="sci",
    feature_id="literature_search",
    payload={...},
    user_id="user123"
)
```

### 2. Shared Utilities (`_shared/utils.py`)

Common utilities used across all graph implementations:

- `parse_json_response()` - Parse JSON from LLM responses with markdown fence handling
- `parse_json_list_response()` - Parse JSON lists from LLM responses
- `detect_generation_mode()` - Determine LLM vs fallback generation mode
- `_normalize_list()` - Normalize comma-separated strings or lists
- `_read_optional_str()` / `_read_optional_int()` - Type-safe parameter extraction
- `_utc_now_iso()` - Consistent timestamp generation

### 3. Graph Function Signature

All graph functions follow a consistent signature:

```python
@register_feature_graph("feature_id", workspace_type="workspace_type")
async def feature_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Pipeline:
        1. Extract parameters from payload
        2. Call service layer (handles LLM + fallback)
        3. Build structured output
    """
    ...
```

### 4. WorkspaceFeatureHandler (`workspace_feature_handler.py`)

Unified handler that routes all workspace features through LangGraph:

- Validates feature exists in registry
- Executes LangGraph sub-graph
- Persists artifacts to database
- Schedules memory extraction

## Supported Features by Workspace Type

### Thesis
| Feature ID | Description |
|------------|-------------|
| `literature_management` | Literature inventory and management |
| `opening_research` | Opening report generation |
| `figure_generation` | Figure/diagram generation |
| `compile_export` | Compile and export thesis |
| `deep_research` | Deep research synthesis |

### SCI
| Feature ID | Description |
|------------|-------------|
| `literature_search` | Academic literature search |
| `paper_analysis` | Structured paper analysis |
| `writing` | Section writing assistance |

### Patent
| Feature ID | Description |
|------------|-------------|
| `patent_outline` | Patent specification outline |
| `prior_art_search` | Prior art analysis |

### Proposal
| Feature ID | Description |
|------------|-------------|
| `proposal_outline` | Grant proposal outline |
| `background_research` | Background research report |

### Software Copyright
| Feature ID | Description |
|------------|-------------|
| `copyright_materials` | Application materials checklist |
| `technical_description` | Technical documentation |

## Error Handling

All graph functions implement graceful degradation:

1. **LLM Success** → `generation_mode: "llm"`
2. **Partial LLM** → `generation_mode: "partial_llm"`
3. **LLM Failure** → `generation_mode: "template_fallback"`

## Testing

Graph tests are located in `tests/agents/graphs/`:

```bash
# Run all graph tests
pytest tests/agents/graphs/ -v

# Run specific workspace tests
pytest tests/agents/graphs/sci/ -v
pytest tests/agents/graphs/patent/ -v
```

## Migration Notes

The following were removed during the LangGraph migration:

- `src/workspace_features/handlers/thesis.py`
- `src/workspace_features/handlers/sci.py`
- `src/workspace_features/handlers/proposal.py`
- `src/workspace_features/handlers/patent.py`
- `src/workspace_features/handlers/software_copyright.py`

All business logic has been moved to:
- Graph files in `src/agents/graphs/{workspace_type}/`
- Service layer in `src/workspace_features/services/`
