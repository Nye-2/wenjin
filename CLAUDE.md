# CLAUDE.md

## Project

Wenjin (问津) — AI workbench for academic research and writing. Five workspace types: thesis, sci, proposal, software_copyright, patent.

## Architecture

- **Chat = control plane**: All chat turns go through `lead_agent` (LangGraph `create_react_agent`). Agent decides when to call `launch_feature` tool to start Compute features.
- **Compute = work plane**: Async Celery tasks execute features (literature search, deep research, paper writing, etc.). Progress via `subagent.updated` and `task.updated` SSE events.
- **AgentBlock protocol**: 4 block types only — `text`, `status_line`, `question_card`, `result_card`. No legacy types.
- **Frontend**: Chat panel (left) + LiveWorkflowPanel (right). Messages flow flat (no run grouping). Result cards use card style, text uses bubble style.

## Key Files

| Area | Entry Point |
|------|-------------|
| Lead agent | `backend/src/agents/lead_agent/agent.py` |
| System prompt | `backend/src/agents/lead_agent/prompts/system.py` |
| Block schema | `backend/src/agents/lead_agent/blocks.py` |
| launch_feature tool | `backend/src/tools/builtins/launch_feature.py` |
| Feature ingress | `backend/src/application/services/feature_ingress_service.py` |
| Celery task runner | `backend/src/task/tasks/base.py` |
| Subagent manager | `backend/src/subagents/manager.py` |
| Chat page | `frontend/app/(workbench)/workspaces/[id]/chat/page.tsx` |
| Message list | `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/MessageList.tsx` |
| Block renderers | `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/` |
| Workflow store | `frontend/stores/workflow-store.ts` |
| Thread store | `frontend/stores/thread.ts` |
| CSS variables | `frontend/app/globals.css` |

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

# Docker
docker compose up --build         # full stack
```

## Docs

- `docs/architecture/` — system architecture, execution pipeline, API surface
- `docs/product/` — workspace behavior, feature catalog, reference library
- `docs/infrastructure/` — deployment, env vars, troubleshooting
- `docs/documentation-map.md` — full doc navigation

## Conventions

- Backend: Python 3.13, FastAPI, SQLAlchemy async, Pydantic v2, LangGraph
- Frontend: Next.js 16, React 19, TypeScript, Tailwind, Zustand
- No compatibility layers or fallback code — clean migrations only
- All chat through lead_agent — no bypass routers
- Tests must pass before commit
