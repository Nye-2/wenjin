# AGENTS.md

## Project

Wenjin (问津) — AI workbench for academic research and writing. Five workspace types: thesis, sci, proposal, software_copyright, patent.

## Architecture

- **Two-agent topology**: Chat Agent (left panel, conversation/intent) + Lead Agent (right panel, runs LangGraph subagents). 1:1 mapping, lead-busy blocks new dispatches.
- **8 workspace rooms**: Library, Documents, Decisions, Memory, Run History, Sandbox, Tasks, Settings — isolated data layer per workspace.
- **Capability data-driven**: YAML seed + DB-backed capabilities. Admin can edit at runtime. No draft/review cycle — lead agent has runtime discretion.
- **Curated result_card flow**: Execution outputs staged → user reviews via checkboxes → commit writes to rooms. Default all-checked + one-click "全部接受".
- **Block protocol**: 7 block types — `text`, `thinking`, `status_line`, `question_card`, `result_card`, `tool_invocation`, `tool_result`. Blocks stored in arrival order (thinking never prepended).
- **Execution UX projection**: Chat launch receipt, LiveWorkflowPanel Current run, and Runs drawer share `frontend/lib/execution-run-view.ts`; `run-ui-store` only tracks UI focus/badges.
- **Frontend workspace UI**: System-grade research workbench. Trusted chrome, quiet content, compact right-side team/evidence/review panel. New UI uses `--wjn-*`; `--v2-*` remains compatibility only.

## Key Files

| Area | Entry Point |
|------|-------------|
| Chat agent | `backend/src/agents/chat_agent/agent.py` |
| Chat agent prompts | `backend/src/agents/chat_agent/prompts/` |
| Lead agent v2 | `backend/src/agents/lead_agent/v2/runtime.py` |
| TeamKernel runtime | `backend/src/agents/lead_agent/v2/team/kernel.py` |
| Lead compiler | `backend/src/agents/lead_agent/v2/compiler.py` |
| Output mapping | `backend/src/agents/lead_agent/v2/output_mapping.py` |
| Expert presentation contracts | `backend/src/contracts/team_presentation.py` |
| Expert runtime contracts | `backend/src/contracts/team_expert.py` |
| Subagent registry | `backend/src/subagents/v2/registry.py` |
| Execution engine | `backend/src/execution/engine.py` |
| Commit service | `backend/src/services/execution_commit_service.py` |
| Task contracts | `backend/src/agents/contracts/task_brief.py` |
| Output contracts | `backend/src/agents/contracts/task_report.py` |
| Workspace page | `frontend/app/(workbench)/workspaces/[id]/page.tsx` |
| Chat store | `frontend/stores/chat-store.ts` |
| Execution store | `frontend/stores/execution-store.ts` |
| Run view projection | `frontend/lib/execution-run-view.ts` |
| Run UI focus store | `frontend/stores/run-ui-store.ts` |
| Chat panel | `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx` |
| Workflow panel | `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx` |
| CSS variables | `frontend/app/globals.css` (`--wjn-*` tokens; `--v2-*` compatibility only) |
| Design language | `docs/current/wenjin-research-navigation-uiux.md` |

## Commands

```bash
# Backend
cd backend && .venv/bin/python -m pytest tests/ -v    # run all tests
cd backend && .venv/bin/python -m pytest tests/path -v # run specific tests
cd backend && alembic upgrade head                     # run migrations

# Frontend
cd frontend && npm run dev        # dev server
cd frontend && npm run build      # production build
cd frontend && npm run typecheck  # type check
cd frontend && npx vitest run     # unit tests

# Docker
docker compose up -d              # standard full stack
docker compose -f docker-compose.yml -f docker-compose.local-build.yml up -d --build # explicit local rebuild
```

## Docs

- `docs/current/architecture.md` — current architecture source of truth
- `docs/current/workspace-current-state.md` — workspace / thread / execution current behavior
- `docs/current/frontend-feature-plugin-contract.md` — frontend/backend capability and execution contract
- `docs/current/workspace-feature-catalog.md` — capability / skill / expert template catalog truth
- `docs/current/wenjin-research-navigation-uiux.md` — current UIUX and visual system truth

## Conventions

- Backend: Python 3.13, FastAPI, SQLAlchemy async, Pydantic v2, LangGraph
- Frontend: Next.js 16, React 19, TypeScript, Tailwind, Zustand, @xyflow/react
- UI design: new surfaces use `--wjn-*`; do not introduce 古风 tokens, decorative orbs, raw log panels, or fixed technical sidebars in default UX
- No compatibility layers or fallback code — clean migrations only
- All chat through chat_agent → lead_agent pipeline — no bypass routers
- Tests must pass before commit
- Capability YAML seeds: `backend/seed/capabilities/{workspace_type}/`
- DB tests use SQLite mock models from `backend/tests/database/conftest.py`
