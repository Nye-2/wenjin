# Capability Output Mapping Design

## Context

Capability executions produce structured output from subagent nodes (`node_results.{task_name}.output`), but the runtime's `_collect_outputs()` currently returns an empty list. This means the ResultCard UI always shows zero outputs — users cannot review and commit execution results to workspace rooms.

The missing piece: a declarative mapping in capability YAML that transforms subagent output dicts into typed `ResultOutput` objects, which the frontend ResultCard can render and users can commit to Library, Documents, Memory, Decisions, or Tasks rooms.

## Design Decisions

- **Approach**: Inline YAML mapping on each task (Option A). Each task in `graph_template.phases[].tasks[]` gets an optional `outputs` list.
- **Scope**: All 5 ResultOutput kinds: `library_item`, `document`, `memory_fact`, `decision`, `task`.
- **Template syntax**: `{{output.xxx}}` for task-level output fields, `{{item.xxx}}` for iteration items, literal strings for constants.

## YAML Schema

### New field: `outputs` on task definitions

```yaml
tasks:
  - name: literature_search
    subagent_type: scholar_searcher
    prompt_template: "..."
    tools: [...]
    outputs:                              # optional, default []
      - kind: library_item                # ResultOutput discriminator
        iterate_on: "output.papers"      # optional — if set, iterate over array
        default_checked: true             # optional, default true
        mapping:
          title: "{{item.title}}"
          authors: "{{item.authors}}"
          year: "{{item.year}}"
          doi: "{{item.doi}}"
          abstract: "{{item.abstract}}"
```

### Template expressions

| Expression | Scope | Meaning |
|---|---|---|
| `{{output.xxx}}` | Any | Dot-path into current task's `node_results.{task_name}.output` dict |
| `{{item.xxx}}` | `iterate_on` body | Dot-path into current iteration element |
| `"literal string"` | Any | Used as-is |

Nested dot-paths are supported: `{{output.meta.keywords}}` resolves `output["meta"]["keywords"]`.

**Interpolated strings**: Expressions mixing `{{...}}` segments with literal text are supported. E.g. `"{{item.name}}：{{item.summary}}"` resolves both template segments and joins with the literal separator. Missing values resolve to empty strings in interpolated context.

### Mapping fields per kind

Fields map 1:1 to the existing Pydantic `*Data` models in `backend/src/agents/contracts/task_report.py`.

#### library_item → Library room

| Field | Type | Required | Notes |
|---|---|---|---|
| `title` | str | yes | |
| `authors` | list[str] | yes | |
| `year` | int | no | |
| `doi` | str | no | |
| `url` | str | no | |
| `abstract` | str | no | |
| `metadata` | dict | no | |

#### document → Documents room

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | str | yes | Display name |
| `mime_type` | str | yes | |
| `storage_path` | str | yes | |
| `size_bytes` | int | yes | |
| `doc_kind` | str | no | draft/outline/report, default "generic" |
| `parent_id` | str | no | |

#### memory_fact → Memory room

| Field | Type | Required | Notes |
|---|---|---|---|
| `content` | str | yes | |
| `category` | str | no | preference/fact/constraint, default "general" |
| `confidence` | float | no | 0-1, default 1.0 |

#### decision → Decisions room

| Field | Type | Required | Notes |
|---|---|---|---|
| `key` | str | yes | e.g. "citation_style" |
| `value` | str | yes | e.g. "APA" |
| `confidence` | float | no | 0-1, default 1.0 |

#### task → Tasks room

| Field | Type | Required | Notes |
|---|---|---|---|
| `title` | str | yes | |
| `description` | str | no | |
| `priority` | str | no | normal/high/low, default "normal" |

## Architecture

### Component: OutputMappingResolver

New class in `backend/src/agents/lead_agent/v2/output_mapping.py`.

Responsibilities:
1. Parse `outputs` declarations from the resolved capability's `graph_template`
2. For each task that declares outputs, resolve template expressions against actual `node_results`
3. Return a flat `list[ResultOutput]`

```python
class OutputMappingResolver:
    def resolve(self, graph_template: dict, node_results: dict) -> list[ResultOutput]:
        """Walk all phases/tasks, resolve mapping declarations against actual results."""
```

### Integration point: `_collect_outputs` in runtime.py

Replace the empty implementation:

```python
def _collect_outputs(self, state: dict, cap: Any) -> list[ResultOutput]:
    graph_template = cap.graph_template
    node_results = state.get("node_results", {})
    return OutputMappingResolver().resolve(graph_template, node_results)
```

### Template resolution

Single function:

```python
def _resolve_value(expr: str, output: dict, item: dict | None = None) -> Any:
    if expr.startswith("{{") and expr.endswith("}}"):
        path = expr[2:-2].strip()
        if path.startswith("output."):
            return _dot_get(output, path[7:])
        if path.startswith("item."):
            return _dot_get(item, path[5:])
    return expr  # literal
```

### Validation

Extend `CapabilityResolver.validate_capability()` to validate `outputs` declarations:
- `kind` must be one of the 5 valid kinds
- `mapping` must contain all required fields for the given kind
- `iterate_on` expression must start with `output.`
- No unknown fields in mapping for a given kind

### Preview generation

`ResultOutputBase.preview` is auto-generated when not explicitly mapped:
- `library_item`: `"{title} — {authors_str}, {year}"`
- `document`: `"{name} ({mime_type})"`
- `memory_fact`: first 80 chars of `content`
- `decision`: `"{key}: {value}"`
- `task`: `"{title}"`

`ResultOutputBase.id` is auto-generated as `f"{task_name}-{kind}-{index}"`.

### DB persistence

The `outputs` field is part of `TaskReport`, which is serialized via `model_dump(mode="json")` and stored in:
- `ExecutionRecord.result["task_report"]["outputs"]` — full output list
- Published via `execution.completed` event — frontend receives complete `ResultCardData`

No schema migration needed — `outputs` is already a JSONB field.

## Data Flow

```
Capability YAML (outputs declarations)
    ↓
CapabilityResolver resolves capability → graph_template with outputs
    ↓
LeadAgentRuntime runs graph → node_results populated by compiler
    ↓
_collect_outputs() → OutputMappingResolver.resolve(graph_template, node_results)
    ↓
TaskReport(outputs=[...ResultOutput...]) → execution.completed event
    ↓
Frontend chat-store receives ResultCardData.outputs — ResultCard renders checkboxes
    ↓
User selects → commit → routed to workspace rooms by kind
```

## Error Handling

- **Task produced no output**: outputs declaration skipped, no error raised
- **Template path not found**: field set to `None` (if optional) or skipped entirely (if required and missing)
- **Interpolated template with missing value**: missing segment resolves to empty string
- **iterate_on path is not an array**: treated as empty, no outputs generated
- **Type mismatch** (e.g. string where int expected): best-effort coercion, log warning

## Testing

- Unit tests for `OutputMappingResolver` with sample graph_templates and node_results
- Each of the 5 kinds tested individually
- `iterate_on` vs single-output modes
- Edge cases: missing paths, empty arrays, type coercion
- Integration: capability YAML seed files validated by `validate_capability()`

## Files

| File | Action |
|---|---|
| `backend/src/agents/lead_agent/v2/output_mapping.py` | CREATE — OutputMappingResolver |
| `backend/src/agents/lead_agent/v2/runtime.py` | MODIFY — wire _collect_outputs |
| `backend/src/services/capability_resolver.py` | MODIFY — add outputs validation |
| `backend/seed/capabilities/*/` | MODIFY — add outputs declarations to existing YAML |
| `backend/tests/agents/lead_agent/v2/test_output_mapping.py` | CREATE — unit tests |
