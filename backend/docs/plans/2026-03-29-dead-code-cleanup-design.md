# Dead Code Cleanup Design

> 归档说明: 本文档为历史阶段性计划快照，可能包含已过时路由、线程模型或状态描述。当前实现请以 `docs/product/workspace-current-state.md` 与相关当前契约文档为准。

## Goal

Remove confirmed dead code and redundant architecture after migration to the super agent harness.

## Context

The project migrated to a LangGraph-based "super agent harness" with middleware pipeline, memory system, and thread state management. A `feat/phase1-pipeline-infrastructure` refactoring also extracts `subagents/runtime.py`, `subagents/task_builder.py`, and `gateway/deps/application.py`. After thorough import-graph analysis, the following items are confirmed dead.

## Verification Method

Each item was verified by:
1. Searching all imports and string references across entire `src/` and `tests/`
2. Tracing the import chain from gateway routes → handlers → services → modules
3. Confirming zero production callers (test-only or no callers at all)

## Phase 0: Merge phase1 infrastructure

Working tree has 58 modified files from `feat/phase1-pipeline-infrastructure`. This must land first as it already removes `subagents/executor.py` and adds proper replacements.

## Phase 1: Dead code removal

| # | Target | What | Evidence |
|---|--------|------|----------|
| 1 | `src/gateway/adapters/skill_adapter.py` | Entire SkillAdapter class | Zero imports in src/ |
| 2 | `src/gateway/adapters/workspace_adapter.py` | Entire WorkspaceAdapter class | In-memory mock, zero imports in src/ |
| 3 | `src/gateway/adapters/__init__.py` | Dead re-exports | Exports dead classes only |
| 4 | `src/skills/parser.py` | SkillParser + ParsedSkill | loader.py has own inline parsing |
| 5 | `src/skills/__init__.py` | Dead parser re-exports | SkillParser/ParsedSkill unused |
| 6 | `tests/skills/test_parser.py` | Orphaned test file | Tests dead module |
| 7 | `src/academic/literature/tools.py` | 7 dead workspace tool funcs | Not exported, not imported |
| 8 | `src/task/service.py` | `list_task_records()` method | Zero callers; `list_tasks()` used instead |
| 9 | `src/agents/middleware/` (singular) | Empty legacy directory | Renamed to `middlewares/` long ago |

## What's NOT dead (verified active)

- Task system (executor, worker, progress, recovery) — all wired into TaskService
- Feature bridge modules — all used in workspace feature orchestration
- Skills base/executor/loader — actively used by implementations
- Citation/bibtex modules — used by CitationService
- Execution/docker infrastructure — used by thesis execution
- All services, routers, models, observability — active
