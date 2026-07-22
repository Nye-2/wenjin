# Mission Release Gate Checklist

> Status: Current
> Updated: 2026-07-17

## Core invariants

- WorkspaceAgent is the single conversational and mission-navigation agent.
- Every long task is a `MissionRun`; MissionView is its only frontend projection.
- Mission persistence is the four-table aggregate and DataService owns transactions.
- ChatTurnRun is transient; `thread_turn_billings` is financial truth only, atomically fences message persistence and settlement, and survives thread deletion.
- Conversation history has no bulk-rebuild API; attachment metadata updates are atomic DataService commands, while long-task context belongs to Mission checkpoints.
- Policy, stages, tools, model profile, and review mode are pinned at mission start.
- ToolCatalog is frozen and every side effect has policy, operation id, fence, and receipt.
- Stage progression is governed by `StageAcceptanceContract`.
- Protected writes pass through `MissionReviewItem` and `MissionCommit`.
- Sandbox compute is Docker-only, typed, bounded, and read-before-write.
- Redis/Celery/SSE are hints, never durable truth.
- Retired runtime code, tables, routes, aliases, and dual projections are absent.

## Backend gates

```bash
cd backend
.venv/bin/python -m ruff check src tests
.venv/bin/python -m compileall -q src
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m alembic heads
.venv/bin/python -m src.quality.mission_cutover_gate --project-root ..
```

Expected baseline at this cutover: full backend suite green except explicitly documented skips; one Alembic head; zero anti-compat findings.

### PostgreSQL runtime accounting verification

The runtime-accounting release gate must run against a real disposable PostgreSQL instance, not the lock-free unit fakes or recorded Alembic operations:

```bash
cd backend
WENJIN_REQUIRE_POSTGRES_RELEASE_VERIFICATION=1 \
  .venv/bin/python -m pytest \
  tests/release_verification/test_runtime_accounting_postgres.py -q -rs
```

This command starts a uniquely named `pgvector/pgvector:pg16` container, binds it to a random loopback port, upgrades one randomly named empty database through `110_deduplicate_mission_references`, and provisions a sibling database at revision 108 for a data-bearing 108→110 cutover check. It removes the container plus its anonymous data volume after the run. The fixture constructs its own database URLs and never migrates the configured Wenjin database. Override the image only when required with `WENJIN_POSTGRES_VERIFICATION_IMAGE`.

The release result must contain six passed tests and zero skipped tests. Without Docker, the default test suite reports these tests as explicitly skipped; `WENJIN_REQUIRE_POSTGRES_RELEASE_VERIFICATION=1` converts missing Docker or image infrastructure into a release-blocking failure. The gate covers reflected columns, unique and partial indexes, checks, foreign keys and `ON DELETE` actions, the data-preserving 109 snapshot cleanup and 110 evidence-count repair, plus observed PostgreSQL row-lock waits for concurrent authorize, idempotent replay, settle/delete, and delete/release accounting transitions.

Architecture-focused coverage must include:

- MissionStore idempotency, optimistic version, lease fencing, stale queue hint, item ordering, command cursor, and cumulative resource-budget projection;
- bounded runtime slices, pause/resume/cancel, reconciliation, wakeups, billing settlement;
- WorkspaceAgent strict action frames; actor-global ChatTurn request replay; durable Redis dispatch intent and reconciler recovery; owner-fenced execution lease loss; atomic chat authorization, usage-required settlement, release, expiry, rollback, and settled replay;
- Subagent isolation, concurrency limits, allowed tools, stop reasons, report persistence;
- ToolCatalog registration/group validation, policy narrowing, receipts, retries, error taxonomy;
- model profile freshness and strict generation probe;
- native search receipt parser and fail-closed behavior;
- Sandbox preflight, path/symlink/network controls, manifests, read-before-write;
- review decisions, conflicts, partial commit, idempotency, linked-domain provenance;
- migrations 086-110 on an empty PostgreSQL database, 107 non-empty-data rejection, financial constraints, foreign-key index coverage, and DataService/Gateway import smoke.

## Frontend gates

```bash
cd frontend
npm run typecheck
npx vitest run
npm run build
npx playwright test tests/e2e/mission-console-main-chain.spec.ts --project=chromium
```

Verify the build contains no retired admin workflow routes. Unit/E2E coverage must include Mission start, console peek/open/close, SSE gap refetch, refresh recovery, dynamic roster, evidence/artifacts, review, request-more-evidence, partial save, history, model/effort menu, and mobile non-overlap.

## Protocol probes

Generation probe:

```bash
cd backend
.venv/bin/python -m src.models.capability_probe \
  --all-enabled-language-models \
  --persist \
  --require-native-search
```

Release requires current evidence for strict tool calls, schema-valid arguments, clean Chat Completions stream completion, `store=false`, and xhigh effort.

Search-required policies additionally require an independent Responses SSE native-search probe. The accepted result must contain:

1. a completed `web_search_call`;
2. non-empty source receipts;
3. URL citations/annotations bound to output;
4. the parser's verified completion boundary.

HTTP 200, prose that mentions sources, or a completed event without receipts is a failure. There is no fallback to another provider.

## Deployment gates

- `docker compose config --quiet` passes;
- migration and bootstrap one-shots succeed;
- DataService/Gateway/workers/frontend are healthy;
- `mission-worker` consumes only `long_running`, concurrency 1, prefetch 1;
- sandbox image digest and production attestations are real, not placeholders;
- readiness checks DataService, Redis, task backend, and sandbox;
- admin analytics reads `mission-stats`;
- GPT-5.6 Sol, Terra, and Luna are the only enabled LLMs; Terra is the sole default.

## Browser acceptance

Run one real-provider, real-Docker, multi-turn case for each high-value family before release, with at least SCI and math modeling mandatory:

- welcome and upload/intake;
- direct advisory chat;
- Mission start and visible real progress;
- subagent/tool activity;
- stage revision before advancement;
- evidence and cited source import;
- user steering during work;
- permission pause/resume;
- review decision and partial commit;
- Prism, Source, and WorkspaceAsset materialization with MissionWriteAuthority provenance;
- refresh/reconnect/history recovery;
- desktop and mobile interaction review.

## No-go conditions

- any core gate missing or failing;
- stale/unverified model profile;
- search-required policy starts without valid native-search receipts;
- duplicate side effect after lease loss/retry;
- unreviewed protected write reaches workspace truth;
- client and server disagree on mission/review/commit state;
- rootful/unpinned/unconfined production sandbox;
- any anti-compat scanner finding;
- browser flow claims work started while no MissionRun exists.
