# Final Review Fix Report

## Scope

- Removed the deterministic capability auto-launch path.
- Kept feature/run identifiers in structured metadata/config only.
- Added Mission Console focused/selected run metadata forwarding for ordinary ChatPanel submits.

## RED Evidence

- `cd backend && .venv/bin/python -m pytest tests/application/handlers/test_thread_turn_runtime_config.py -v`
  - Failed as expected on `launch_feature_id` still being set for intake approval metadata.
  - Failed as expected on persisted orchestration metadata rendering `feature=` / `execution_id=` into model-visible text.
- `cd backend && .venv/bin/python -m pytest tests/agents/test_lead_agent.py -v`
  - Failed as expected because `CapabilityAutoLaunchMiddleware` was still present in the Chat Agent middleware chain.
- `cd frontend && npx vitest run tests/unit/lib/workspace-thread-entry.test.ts tests/unit/v2/ChatPanel.test.tsx`
  - Failed as expected because resume prompts included raw `execution_id`.
  - Failed as expected because normal manual sends did not include selected/focused run metadata.

## GREEN Evidence

- `cd backend && .venv/bin/python -m pytest tests/application/handlers/test_thread_turn_runtime_config.py -v` -> 12 passed.
- `cd backend && .venv/bin/python -m pytest tests/agents/test_lead_agent.py -v` -> 23 passed.
- `cd backend && .venv/bin/python -m pytest tests/integration/test_chat_to_feature_launch.py -v` -> 15 passed, 1 existing deprecation warning.
- `cd backend && .venv/bin/python -m pytest tests/agents/chat_agent/test_capability_route_cards.py -v` -> 10 passed.
- `cd backend && .venv/bin/python -m pytest tests/gateway/routers/test_threads_router.py -v` -> 28 passed.
- `cd frontend && npx vitest run tests/unit/lib/workspace-thread-entry.test.ts tests/unit/v2/ChatPanel.test.tsx` -> 42 passed.
- `cd frontend && npm run typecheck` -> passed.
- Required scan found no production `CapabilityAutoLaunchMiddleware`, `capability_auto_launch`, or `launch_feature_id` references; remaining matches are structured metadata fields and tests asserting absence.

## Files Changed

- `backend/src/application/handlers/thread_turn_handler.py`
- `backend/src/agents/chat_agent/agent.py`
- `backend/src/agents/middlewares/__init__.py`
- `backend/src/agents/middlewares/capability_auto_launch.py` (deleted)
- `backend/tests/agents/chat_agent/test_capability_auto_launch.py` (deleted)
- `backend/tests/application/handlers/test_thread_turn_runtime_config.py`
- `backend/tests/agents/test_lead_agent.py`
- `backend/tests/gateway/routers/test_threads_router.py`
- `frontend/lib/workspace-thread-entry.ts`
- `frontend/tests/unit/lib/workspace-thread-entry.test.ts`
- `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`
- `frontend/tests/unit/v2/ChatPanel.test.tsx`

## Self-Review

- Durable launches now require the Chat Agent model/tool path: route cards -> model decision -> `launch_feature`.
- `launch_feature_params` remains available for the `launch_feature` tool, but no `launch_feature_id` config key is set or consumed.
- Persisted message reconstruction no longer injects raw orchestration or block-action markers into model-visible content.
- Resume prompts keep `execution_id` only in metadata.
- Normal ChatPanel submits merge focused/selected mission `execution_id` structurally and do not alter prompt text.

## Commit

- Commit hash: pending; final hash is reported after commit.
