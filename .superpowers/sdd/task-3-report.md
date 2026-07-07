# Task 3 Report: Mission State Projection

## Scope

- Added `RunView.mission` projection in `frontend/lib/execution-run-view.ts`.
- Kept raw execution/runtime/result parsing inside the projection layer.
- Added focused unit coverage in `frontend/tests/unit/lib/execution-run-view.test.ts`.

## TDD Evidence

### RED

Command:

```bash
cd frontend && npx vitest run tests/unit/lib/execution-run-view.test.ts
```

Observed failure summary:

```text
tests/unit/lib/execution-run-view.test.ts (26 tests | 5 failed)
- projects an active TeamKernel mission with human stage labels
- marks mission critique as blocked when the review packet has blockers
- bounds research-state open questions and next actions in the mission projection
- separates used evidence from merely found evidence in mission counts
- returns a null mission when there is no selected execution state to project
```

### GREEN

Command:

```bash
cd frontend && npx vitest run tests/unit/lib/execution-run-view.test.ts
```

Observed pass summary:

```text
Test Files  1 passed (1)
Tests  26 passed (26)
```

## Acceptance Checks

### Focused unit tests

```bash
cd frontend && npx vitest run tests/unit/lib/execution-run-view.test.ts
```

Result:

```text
Test Files  1 passed (1)
Tests  26 passed (26)
```

### Typecheck

```bash
cd frontend && npm run typecheck
```

Result:

```text
> wenjin-frontend@2.0.0 typecheck
> next typegen && tsc --noEmit

Generating route types...
✓ Types generated successfully
```

## Self-Review

- `RunView.mission` is derived only from existing execution/task-report/runtime data.
- No backend files, capability YAML, Zustand stores, or component-layer raw parsing were added.
- Historical/result-card projections return `mission: null`; live execution projections carry the mission state.
