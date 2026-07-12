# Deployment Runbook

> Status: Current
> Updated: 2026-07-11

Wenjin is deployed with Docker Compose. PostgreSQL and DataService hold durable truth; Redis carries Celery and event hints; separate workers handle chat/short jobs, long Mission slices, and memory jobs.

## 1. Prerequisites

- Docker Engine with Compose v2;
- a rootless Docker socket for Sandbox vNext, or a reviewed userns-remap equivalent;
- a pinned sandbox image digest;
- PostgreSQL/Redis volumes with adequate space;
- GPT-5.5 provider credentials;
- production secrets in `.env`, never committed.

## 2. Required services

| Service | Responsibility |
|---|---|
| `postgres` | durable application and Mission data |
| `redis` | Celery broker/result backend and event hints |
| `migrate` | one-shot Alembic migration to the single head |
| `dataservice` | sole runtime transaction boundary |
| `bootstrap-admin` | one-shot admin/catalog bootstrap |
| `worker` | `default,priority` queues |
| `mission-worker` | `long_running`, concurrency 1, prefetch 1 |
| `memory-worker` | `memory` queue |
| `gateway` | HTTP, chat streams, Mission API/SSE |
| `frontend` | Next.js UI |
| `texlive` | one-shot LaTeX runtime check |

## 3. Configure

Start from `.env.example`. At minimum replace database/admin/JWT/DataService/model secrets and the sandbox digest. The only language model entry is GPT-5.5 with `generation_api=chat_completions`; set it as default. Do not add a second generation protocol as fallback.

Production Sandbox requirements:

- `SANDBOX_PROVIDER=docker`;
- `SANDBOX_DEPLOYMENT_MODE=production`;
- immutable `SANDBOX_DOCKER__IMAGE_DIGEST`;
- non-root uid/gid and confined seccomp;
- workspace quota and bind-mount identity attestations;
- package-index egress proxy/network only when dependency install is enabled;
- rootless socket or explicitly accepted equivalent.

## 4. Validate configuration

```bash
docker compose config --quiet
docker compose -f docker-compose.yml -f docker-compose.local-build.yml config --quiet
cd backend && .venv/bin/python -m alembic heads
cd backend && .venv/bin/python -m src.quality.mission_cutover_gate --project-root ..
```

Alembic must report one head: `091_review_commit_consistency` until a later migration intentionally advances it. The cutover gate must report zero findings.

## 5. Start

Prebuilt images:

```bash
docker compose up -d
```

Explicit local rebuild:

```bash
docker compose -f docker-compose.yml -f docker-compose.local-build.yml up -d --build
```

Do not run a second ad-hoc frontend/backend stack on alternate ports as the normal deployment path.

## 6. Verify

```bash
docker compose ps
docker compose logs --tail=200 migrate dataservice gateway worker mission-worker frontend
curl -fsS http://localhost:2026/api/models?purpose=chat
curl -fsS http://localhost:2026/api/readyz
```

Check that:

- migration and bootstrap exited successfully;
- DataService, Gateway, all three workers, and frontend are healthy;
- worker inspection includes a consumer for `long_running`;
- the model response contains GPT-5.5 only;
- readiness reports DataService, Redis, task backend, and sandbox preflight correctly.

## 7. Model probes

Generation and native search are separate capability probes.

```bash
cd backend
.venv/bin/python -m src.models.capability_probe --model-id gpt-5.5
```

Generation readiness requires strict structured tool arguments, clean Chat Completions streaming termination, xhigh effort support, and response storage disabled.

Native search uses an independent Responses SSE request. It is usable only when the completed payload includes a `web_search_call`, source receipts, URL citations, and an accepted completion boundary. HTTP success or generated prose alone is not readiness. Search-required Mission policies fail closed while the probe is unavailable.

## 8. Migration policy

Migrations 086-096 are an irreversible development cutover. Do not recreate removed tables or add dual-read/dual-write code. For a development database containing pre-cutover runtime data:

1. stop all services;
2. drop the development database/volume;
3. recreate it;
4. run migrations and seed/bootstrap once;
5. verify catalog hashes and the model profile.

Production rollout must be based on a clean snapshot/backup and an explicitly reviewed migration window.

## 9. Smoke test

Use a real browser and complete a multi-turn scenario:

1. create/open a workspace;
2. verify the non-persisted welcome state;
3. ask a direct question;
4. start a long research Mission through chat;
5. observe console peek, stage/team progress, and refresh recovery;
6. steer with another chat turn;
7. inspect evidence/artifacts;
8. review one item, request more evidence on another, and partially save;
9. confirm Mission History and Prism/room provenance;
10. repeat at mobile width.

## 10. Stop and rollback

```bash
docker compose down
```

Do not use `down -v` unless intentionally reseeding development data. Runtime code rollback across 086-096 is unsupported; restore a matching database snapshot with the matching application version.
