# AGENTS.md

## Project

Wenjin (问津) is a chat-native AI workbench for academic research and writing. Workspace types: `sci`, `thesis`, `proposal`, `software_copyright`, `math_modeling`, and `patent`.

## Current architecture

- **Single agent topology**: `WorkspaceAgent` owns conversation, intent, Mission start/steer, and the structured Mission loop. It may spawn isolated workers through `SubagentRuntime`; there is no separate conversational/leader agent layer.
- **Durable Mission aggregate**: `MissionRun`, ordered `MissionItem`, atomic `MissionReviewItem`, and idempotent `MissionCommit` are the only long-task persistence model.
- **Transient chat transport**: `ChatTurnRun` streams one conversational turn. Redis atomically holds the actor-global request index and recoverable dispatch intent; Celery delivery is at-least-once and worker terminal effects are execution-owner fenced. It is not research history or a durable workflow aggregate. `ThreadTurnBilling` is a separate financial authorization/settlement record, never a run store.
- **Outcome-first methodology**: `MissionPolicy` pins goals, completion targets, stage contracts, tool groups, review, and budget. `WorkerSkill` supplies compact guidance/examples. The agent loop chooses the internal plan.
- **Quality progression**: the main Agent freezes a content-addressed candidate, then `StageAcceptanceContract` deterministically blocks downstream stages until receipt-backed evidence, artifacts, and criteria pass. Optional critic workers are diagnostic only.
- **Canonical tools**: a frozen `ToolCatalog` plus `ToolOrchestrator` owns tool ids, policy, operation identity, lease fencing, receipts, and typed failures.
- **Reviewed writes**: only stage-accepted candidates become user review items; `ReviewCommitRuntime` handles decisions, conflict checks, partial materialization, and commit receipts.
- **Sandbox vNext**: Docker-only typed operations, pinned image, restricted network profiles, read-before-write, bounded outputs, and immutable content-addressed artifact objects.
- **Frontend**: Chat is task navigation. `MissionView` is the only research-task projection. The right Mission Console is closed by default and expands on demand.
- **DataService boundary**: DataService owns all runtime database transactions. Redis/Celery/SSE messages are delivery/invalidation hints only.

## Persistence and queues

- Mission tables: `mission_runs`, `mission_items`, `mission_review_items`, `mission_commits`.
- Chat finance table: `thread_turn_billings`; it atomically binds one user message, bounded hold, assistant message, exact usage, and credit transaction, and survives thread deletion as audit truth.
- Catalog tables: `mission_policies`, `worker_skills`.
- Default worker queues: `default,priority`.
- Mission worker queue: `long_running`, two replicas, each concurrency 1 and prefetch 1; global subagent quantum capacity 4.
- Current migration head: `110_deduplicate_mission_references`.
- Migrations 086-110 are irreversible development cutovers; use drop/reseed, never compatibility layers. Migration 107 rejects non-empty development data.

## Model and search

- Only `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna` are enabled for chat, Mission loop, and workers; Terra is the default.
- Main generation uses Chat Completions with `store=false`.
- Reasoning efforts are exactly `low`, `medium`, `high`, and `xhigh`; default is `xhigh`.
- Model capability is probe-backed and hash-bound, not controlled by static support flags.
- Native web search is a separate Responses SSE tool transport. It is valid only with verified `web_search_call`, source receipts, URL citations, and completion boundary. No alternate search-provider fallback.

## Key files

| Area | Entry point |
|---|---|
| Workspace agent | `backend/src/agents/workspace_agent/agent.py` |
| Mission loop | `backend/src/agents/workspace_agent/mission_loop.py` |
| Chat turn transport | `backend/src/runtime/chat_turns/` |
| Chat turn billing | `backend/src/dataservice/domains/thread_turn_billing/` |
| Mission inputs | `backend/src/contracts/mission_input.py`, `backend/src/services/mission_inputs.py` |
| Mission runtime | `backend/src/mission_runtime/runtime.py` |
| Production composition | `backend/src/mission_runtime/composition.py` |
| Mission persistence | `backend/src/dataservice/domains/mission/` |
| Mission models | `backend/src/database/models/mission.py` |
| Mission API | `backend/src/gateway/routers/missions.py` |
| Subagents | `backend/src/subagent_runtime/` |
| Tool orchestrator | `backend/src/tools/orchestrator/` |
| Mission tool catalog | `backend/src/tools/mission/catalog.py` |
| Mission policy/stages | `backend/src/contracts/mission_policy.py`, `backend/src/contracts/stage_acceptance.py` |
| Policy loader | `backend/src/services/mission_policy_loader.py` |
| Review/permissions | `backend/src/review_commit_runtime/`, `backend/src/permission_runtime/` |
| Sandbox | `backend/src/sandbox/` |
| Model capability | `backend/src/models/capability_profile.py`, `backend/src/models/capability_probe.py` |
| Native search | `backend/src/services/search/model_native.py` |
| Frontend Mission API | `frontend/lib/api/missions.ts` |
| Mission Console | `frontend/app/(workbench)/workspaces/[id]/components/mission-console/` |
| Current architecture | `docs/current/architecture.md` |
| Migration specs | `docs/superpowers/specs/mission-runtime/00_index.md` |

## Commands

```bash
# Backend
cd backend && .venv/bin/python -m pytest tests/ -q
cd backend && .venv/bin/python -m ruff check src tests
cd backend && .venv/bin/python -m compileall -q src
cd backend && .venv/bin/python -m alembic heads
cd backend && .venv/bin/python -m src.quality.mission_cutover_gate --project-root ..

# Frontend
cd frontend && npm run typecheck
cd frontend && npx vitest run
cd frontend && npm run build
cd frontend && npx playwright test tests/e2e/mission-console-main-chain.spec.ts --project=chromium

# Docker
docker compose up -d
docker compose -f docker-compose.yml -f docker-compose.local-build.yml up -d --build
```

## Conventions

- Backend: Python 3.13, FastAPI, SQLAlchemy async, Pydantic v2, Celery.
- Frontend: Next.js 16, React 19, TypeScript, Tailwind, Zustand.
- New UI uses `--wjn-*` tokens and Mission terminology.
- Frontend is Chinese-only (no i18n layer) and single-theme (warm paper); colors, radius, and shadows must come from the `--wjn-*` tokens in `app/globals.css`, never hardcoded hex or stock Tailwind palettes.
- Copy follows the two-level naming spec: panel-level 「来源与结果」; material type chips 文献源/数据/代码/结果/图表/材料 via `components/ui/type-chip.tsx`; status pills 已查证/待你确认/待你补充 via `components/ui/status-pill.tsx`. Avoid 证据/已核验 wording in user-visible copy.
- No compatibility aliases, dual reads/writes, fallback routers, or stale serializer fields.
- Long research work always flows through WorkspaceAgent to MissionRuntime.
- Tools must be registered in the canonical catalog and narrowed by pinned Mission policy.
- Protected workspace writes always pass review/commit.
- Tests and the strict anti-compat gate must pass before commit.
- Never commit provider keys, `.env`, raw prompts, protected paths, or unbounded tool output.
