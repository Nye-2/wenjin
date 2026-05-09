# CLAUDE.md

## Project

Wenjin (问津) — AI workbench for academic research and writing. Five workspace types: thesis, sci, proposal, software_copyright, patent.

## Architecture

- **Two-agent topology**: Chat Agent (left panel, conversation/intent) + Lead Agent (right panel, runs LangGraph subagents). 1:1 mapping, lead-busy blocks new dispatches.
- **8 workspace rooms**: Library, Documents, Decisions, Memory, Run History, Sandbox, Tasks, Settings — isolated data layer per workspace.
- **Capability data-driven**: YAML seed + DB-backed capabilities. Admin can edit at runtime. No draft/review cycle — lead agent has runtime discretion.
- **Curated result_card flow**: Execution outputs staged → user reviews via checkboxes → commit writes to rooms. Default all-checked + one-click "全部接受".
- **Block protocol**: 7 block types — `text`, `thinking`, `status_line`, `question_card`, `result_card`, `tool_invocation`, `tool_result`. Blocks stored in arrival order (thinking never prepended).
- **Frontend v2**: Glass/visionOS design language. Left minimal white chat (ChatGPT-style) + right glassmorphism panel with purple/blue light orbs. `--v2-*` CSS tokens.

## Key Files

| Area | Entry Point |
|------|-------------|
| Chat agent | `backend/src/agents/chat_agent/agent.py` |
| Chat agent prompts | `backend/src/agents/chat_agent/prompts.py` |
| Lead agent v2 | `backend/src/agents/lead_agent/v2/agent.py` |
| Lead compiler | `backend/src/agents/lead_agent/v2/compiler.py` |
| Lead runtime | `backend/src/agents/lead_agent/v2/runtime.py` |
| Subagent registry | `backend/src/subagents/v2/registry.py` |
| Execution engine v2 | `backend/src/execution/engine_v2.py` |
| Task contracts | `backend/src/agents/contracts/task_brief.py` |
| V2 workspace page | `frontend/app/(workbench)/workspaces/[id]/v2/page.tsx` |
| Chat store v2 | `frontend/stores/chat-store-v2.ts` |
| Execution store | `frontend/stores/execution-store.ts` |
| Chat panel | `frontend/app/(workbench)/workspaces/[id]/v2/components/ChatPanel.tsx` |
| Workflow panel | `frontend/app/(workbench)/workspaces/[id]/v2/components/LiveWorkflowPanel.tsx` |
| CSS variables (v2) | `frontend/app/globals.css` (`--v2-*` tokens) |
| Design language | `docs/superpowers/specs/2026-05-09-v2-design-language.md` |

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
docker compose up --build         # full stack
```

## Docs

- `docs/superpowers/specs/2026-05-09-wenjin-workspace-rebuild-design.md` — v2 rebuild spec (source of truth)
- `docs/superpowers/specs/2026-05-09-v2-design-language.md` — Glass/visionOS design language
- `docs/superpowers/plans/2026-05-09-wenjin-workspace-rebuild.md` — 12-week implementation plan
- `docs/architecture/` — legacy architecture docs
- `docs/product/` — workspace behavior, feature catalog

## Conventions

- Backend: Python 3.13, FastAPI, SQLAlchemy async, Pydantic v2, LangGraph
- Frontend: Next.js 16, React 19, TypeScript, Tailwind, Zustand, @xyflow/react
- v2 design: `--v2-*` CSS tokens only in new components. No 古风 tokens (--brand-ink, --brand-paper etc.)
- No compatibility layers or fallback code — clean migrations only
- All chat through chat_agent → lead_agent pipeline — no bypass routers
- Tests must pass before commit
- Capability YAML seeds: `backend/seed/capabilities/{workspace_type}/`
- DB tests use SQLite mock models from `backend/tests/database/conftest.py`
