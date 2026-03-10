# Phase 3: Academic Agents Integration Design Document

> Created: 2026-03-10
> Status: Approved
> Author: Claude + User

## 1. Overview

### 1.1 Background

Phase 1 (Sandbox System) and Phase 2 (Subagent System Core) are complete. Phase 3 integrates the existing academic subagents (Scout, Writer, Synthesizer, Analyst) into the GlobalSubagentManager infrastructure.

### 1.2 Goals

- Integrate 4 academic subagents into GlobalSubagentManager
- Provide type-based API for spawning academic agents
- Support hybrid tool access (predefined + dynamic)
- Enable academic-specific system prompts through graph templates

### 1.3 Scope

**In Scope:**
- AcademicAgentResolver for config resolution
- API extension for `subagent_type` and `tools` parameters
- Academic graph templates with custom system prompts
- Tool validation and merging logic

**Out of Scope (Future Phases):**
- Subagent chain execution
- Advanced workflow orchestration
- Distributed execution

## 2. Architecture

### 2.1 Component Diagram

```
+-----------------------------------------------------------------+
|                        FastAPI Application                       |
+-----------------------------------------------------------------+
|  POST /api/threads/{thread_id}/subagents/spawn                  |
|  {                                                              |
|    "prompt": "...",                                             |
|    "subagent_type": "scout",     <-- NEW parameter              |
|    "tools": ["custom_tool"],     <-- Optional tool override     |
|    "graph_template": "default"   <-- Optional                   |
|  }                                                              |
+-----------------------------------------------------------------+
|  GlobalSubagentManager                                          |
|  +-- AcademicAgentResolver (NEW)                                |
|  |   +-- resolve_config(subagent_type, requested_tools)         |
|  |   +-- Returns: SubagentConfig with merged tools              |
|  +-- GraphTemplateRegistry                                      |
|  |   +-- academic/* templates (scout, writer, etc.)             |
|  +-- ... (existing Phase 2 components)                          |
+-----------------------------------------------------------------+
|  Academic Subagent Registry (src/subagents/academic/)           |
|  +-- registry.py                                                |
|  |   +-- SUBAGENT_REGISTRY {scout, writer, synthesizer, analyst}|
|  +-- prompts.py                                                 |
|  +-- resolver.py (NEW)                                          |
+-----------------------------------------------------------------+
```

### 2.2 File Structure

```
src/subagents/
+-- academic/
|   +-- __init__.py
|   +-- registry.py         # (existing) SubagentConfig, SUBAGENT_REGISTRY
|   +-- prompts.py          # (existing) System prompts
|   +-- resolver.py         # (NEW) AcademicAgentResolver
+-- graph.py                # (extend) add create_academic_agent_graph
+-- manager.py              # (minor) integrate resolver
+-- ...

src/api/
+-- subagents.py            # (extend) add subagent_type, tools params

tests/subagents/
+-- academic/
|   +-- __init__.py
|   +-- test_resolver.py    # (NEW) Test AcademicAgentResolver
|   +-- test_integration.py # (NEW) End-to-end academic agent tests
+-- test_api.py             # (extend) Test new spawn params
```

## 3. Component Design

### 3.1 AcademicAgentResolver

```python
# src/subagents/academic/resolver.py

class AcademicAgentResolver:
    """Resolves academic agent configuration based on type and requested tools."""

    def __init__(self, sandbox_tools: dict[str, Any]):
        self._sandbox_tools = sandbox_tools
        self._tool_categories = {
            "search": ["semantic_scholar_search", "web_search", "arxiv_search"],
            "file": ["read_file", "get_paper_section", "get_paper_toc"],
            "code": ["python_exec", "data_analysis"],
        }

    def resolve_config(
        self,
        subagent_type: str,
        requested_tools: list[str] | None = None
    ) -> SubagentConfig:
        """
        Resolve agent configuration with merged tools.

        Args:
            subagent_type: Type from registry (scout, writer, synthesizer, analyst)
            requested_tools: Optional override tools

        Returns:
            SubagentConfig with merged tools
        """
        # Get base config from registry
        base_config = get_subagent_config(subagent_type)

        # Merge tools: requested > default > base
        if requested_tools:
            tools = self._validate_tools(requested_tools)
        else:
            tools = self._merge_default_tools(base_config.tools)

        return SubagentConfig(
            name=base_config.name,
            description=base_config.description,
            system_prompt=base_config.system_prompt,
            tools=tools,
            max_turns=base_config.max_turns,
        )

    def _validate_tools(self, tool_names: list[str]) -> list[str]:
        """Validate and return only available tools."""
        valid_tools = []
        invalid_tools = []
        for name in tool_names:
            if name in self._sandbox_tools:
                valid_tools.append(name)
            else:
                invalid_tools.append(name)

        if invalid_tools:
            logger.warning(f"Requested tools not available: {invalid_tools}")

        if not valid_tools:
            raise InvalidToolError(tool_names[0], list(self._sandbox_tools.keys()))

        return valid_tools

    def _merge_default_tools(self, base_tools: list[str]) -> list[str]:
        """Merge base tools with all available sandbox tools."""
        # Start with base tools
        merged = set(base_tools)
        # Add all sandbox tools (user selected all tool categories)
        merged.update(self._sandbox_tools.keys())
        return list(merged)
```

### 3.2 API Extension

```python
# src/api/subagents.py

class SpawnRequest(BaseModel):
    prompt: str
    subagent_type: str | None = None  # NEW: scout, writer, synthesizer, analyst
    tools: list[str] | None = None    # NEW: optional tool override
    graph_template: str = "default"
    max_turns: int = 10
    timeout: int = 900

@router.post("/threads/{thread_id}/subagents/spawn")
async def spawn_subagent(
    thread_id: str,
    request: SpawnRequest,
    manager: GlobalSubagentManager = Depends(get_manager)
):
    # Resolve agent config if subagent_type specified
    if request.subagent_type:
        resolver = AcademicAgentResolver(manager._tools)
        try:
            config = resolver.resolve_config(request.subagent_type, request.tools)
        except UnknownSubagentTypeError as e:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "UnknownSubagentType",
                    "message": str(e),
                    "valid_types": get_all_subagent_types()
                }
            )
        except InvalidToolError as e:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "InvalidTool",
                    "message": str(e),
                    "available_tools": e.available_tools
                }
            )

        tools = [manager._tools[t] for t in config.tools if t in manager._tools]
        system_prompt = config.system_prompt
    else:
        tools = list(manager._tools.values())
        system_prompt = None

    task = SubagentTask(
        task_id=str(uuid4()),
        thread_id=thread_id,
        prompt=request.prompt,
        graph_template=request.graph_template,
        max_turns=request.max_turns,
        timeout=request.timeout,
        created_at=datetime.now(),
        tools=request.tools or [],
        metadata={
            "subagent_type": request.subagent_type,
            "system_prompt": system_prompt
        }
    )

    await manager.spawn(task)
    return SpawnResponse(task_id=task.task_id, status="pending")
```

### 3.3 Graph Template Extension

```python
# src/subagents/graph.py

def create_academic_agent_graph(
    llm: Any,
    tools: list,
    system_prompt: str,
    max_turns: int = 10
) -> Any:
    """Create a ReAct agent with custom system prompt for academic tasks."""
    from langgraph.prebuilt import create_react_agent

    return create_react_agent(
        llm,
        tools=tools,
        state_modifier=system_prompt  # Apply academic-specific prompt
    )

def register_academic_templates(
    registry: GraphTemplateRegistry,
    llm: Any,
    tools: dict
) -> None:
    """Register academic agent graph templates."""
    for agent_type in ["scout", "writer", "synthesizer", "analyst"]:
        config = get_subagent_config(agent_type)
        agent_tools = [tools[t] for t in config.tools if t in tools]
        graph = create_academic_agent_graph(llm, agent_tools, config.system_prompt)
        registry.register(f"academic_{agent_type}", graph)
```

## 4. Data Flow

```
User Request -> API -> GlobalSubagentManager -> Execution

Detailed Flow:

1. Client sends request
   POST /api/threads/thread-123/subagents/spawn
   {
     "prompt": "Search for recent papers on transformer architectures",
     "subagent_type": "scout",
     "tools": null,
     "graph_template": "default"
   }

2. spawn_subagent() processes
   +-- Check subagent_type exists
   +-- AcademicAgentResolver.resolve_config("scout", null)
   |   +-- Get base_config = SCOUT_CONFIG
   |   +-- Merge default tools: semantic_scholar_search + all sandbox tools
   |   +-- Return merged SubagentConfig
   +-- Create SubagentTask (with tools and system_prompt)
   +-- Call manager.spawn(task)

3. GlobalSubagentManager.spawn()
   +-- Get/create ThreadContext
   +-- Get graph (from registry or create new)
   |   +-- If subagent_type specified, use academic_{type} template
   +-- Acquire execution slot via DualLayerLimiter
   +-- Async execute _execute_task()

4. _execute_task()
   +-- Publish task_started event
   +-- graph.ainvoke({"messages": [HumanMessage(prompt)]})
   +-- Collect results, publish task_completed event
   +-- Store SubagentResult

5. Client can get results via:
   - GET /status endpoint polling
   - GET /events SSE stream for real-time updates
```

## 5. Error Handling

### 5.1 Exception Classes

```python
class AcademicAgentError(Exception):
    """Base exception for academic agent errors."""
    pass

class UnknownSubagentTypeError(AcademicAgentError):
    """Raised when subagent_type is not recognized."""
    def __init__(self, subagent_type: str):
        self.subagent_type = subagent_type
        super().__init__(
            f"Unknown subagent type: {subagent_type}. "
            f"Valid types: scout, writer, synthesizer, analyst"
        )

class InvalidToolError(AcademicAgentError):
    """Raised when a requested tool is not available."""
    def __init__(self, tool_name: str, available_tools: list[str]):
        self.tool_name = tool_name
        self.available_tools = available_tools
        super().__init__(
            f"Tool '{tool_name}' not available. Available: {available_tools}"
        )
```

### 5.2 API Error Responses

```json
// HTTP 400 - Unknown Subagent Type
{
    "detail": {
        "error": "UnknownSubagentType",
        "message": "Unknown subagent type: researcher",
        "valid_types": ["scout", "writer", "synthesizer", "analyst"]
    }
}

// HTTP 400 - Invalid Tool
{
    "detail": {
        "error": "InvalidTool",
        "message": "Tool 'nonexistent_tool' not available",
        "available_tools": ["semantic_scholar_search", "read_file", ...]
    }
}
```

### 5.3 Edge Case Handling

| Scenario | Strategy |
|----------|----------|
| Invalid `subagent_type` | Return 400 error, list valid types |
| Invalid tools in list | Warning log, ignore invalid, continue with valid |
| All tools invalid | Raise InvalidToolError, return 400 |
| Both `subagent_type` and `graph_template` | `graph_template` takes precedence |
| No `subagent_type` specified | Use original behavior (default tool set) |

## 6. Testing Plan

### 6.1 Unit Tests

**test_resolver.py:**
- Test resolve_config with valid subagent_type
- Test resolve_config with invalid subagent_type
- Test tool validation with valid tools
- Test tool validation with mixed valid/invalid tools
- Test tool validation with all invalid tools
- Test default tool merging

**test_api.py (extensions):**
- Test spawn with valid subagent_type
- Test spawn with invalid subagent_type
- Test spawn with tool override
- Test spawn without subagent_type (backward compatibility)

### 6.2 Integration Tests

**test_integration.py:**
- End-to-end scout agent execution
- End-to-end writer agent execution
- End-to-end synthesizer agent execution
- End-to-end analyst agent execution
- Tool access verification
- Event stream for academic agents

### 6.3 Test Summary

| Test File | Tests | Focus |
|-----------|-------|-------|
| test_resolver.py | 8 | Config resolution, tool validation |
| test_api.py | 6 | API parameters, error handling |
| test_integration.py | 5 | End-to-end execution |

**Total: ~19 new tests**

## 7. Implementation Checklist

- [ ] Create `src/subagents/academic/resolver.py` with AcademicAgentResolver
- [ ] Create `src/subagents/academic/errors.py` with exception classes
- [ ] Extend `src/subagents/graph.py` with create_academic_agent_graph
- [ ] Extend `src/api/subagents.py` with new SpawnRequest parameters
- [ ] Create `tests/subagents/academic/test_resolver.py`
- [ ] Create `tests/subagents/academic/test_integration.py`
- [ ] Extend `tests/subagents/test_api.py`
- [ ] Update `src/subagents/__init__.py` exports
- [ ] Run all tests, ensure 100% pass rate

## 8. Dependencies

- Phase 2 components (GlobalSubagentManager, DualLayerLimiter, etc.)
- LangGraph (create_react_agent)
- Existing academic registry (SUBAGENT_REGISTRY)
- Sandbox tools

## 9. Success Criteria

1. All 4 academic agents spawnable via API with `subagent_type`
2. Tool override works correctly
3. Error handling returns proper HTTP status codes
4. All tests pass (target: 170+ total tests)
5. No regression in existing Phase 2 functionality
