# Deployment Runbook

> Status: Current
> Updated: 2026-07-22

Wenjin is deployed with Docker Compose. PostgreSQL and DataService hold durable truth; Redis carries Celery and event hints; separate workers handle chat/short jobs and long Mission slices.

## 1. Prerequisites

- Docker Engine with Compose v2;
- a rootless Docker socket for Sandbox vNext, or a reviewed userns-remap equivalent;
- a pinned sandbox image digest;
- PostgreSQL/Redis volumes with adequate space;
- GPT-5.6 Sol/Terra/Luna provider credentials;
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
| `mission-worker` | two replicas for `long_running`; each concurrency 1, prefetch 1 |
| `celery-beat` | single scheduler for Mission reconciliation, ChatTurn dispatch recovery, bounded periodic credit grants, authorization expiry, and preview cleanup |
| `gateway` | HTTP, chat streams, Mission API/SSE |
| `frontend` | Next.js UI |

## 3. Configure

Start from `.env.example`. At minimum replace database/admin/JWT/DataService/model secrets and the sandbox digest. The language-model entries are GPT-5.6 Sol/Terra/Luna with `generation_api=chat_completions`; keep Terra as default unless the release decision changes. Do not add a second generation protocol as fallback.

Production Sandbox requirements:

- `SANDBOX_PROVIDER=docker`;
- `SANDBOX_DEPLOYMENT_MODE=production`;
- immutable `SANDBOX_DOCKER__IMAGE_DIGEST`;
- non-root uid/gid and confined seccomp;
- workspace quota and bind-mount identity attestations;
- package-index egress proxy/network only when dependency install is enabled;
- rootless socket or explicitly accepted equivalent.

Build the academic visual Sandbox, record its immutable image id, and configure that digest before starting Mission workers:

```bash
docker build -f backend/Dockerfile.visual-sandbox -t wenjin-visual-sandbox:latest backend
docker image inspect wenjin-visual-sandbox:latest --format '{{.Id}}'
```

Set `SANDBOX_DOCKER__IMAGE=wenjin-visual-sandbox:latest` and copy the returned `sha256:...` value into `SANDBOX_DOCKER__IMAGE_DIGEST`. The image contains pinned Matplotlib/Seaborn, Graphviz and fonts; do not install renderer packages during a Mission.

## 4. Validate configuration

```bash
docker compose config --quiet
docker compose -f docker-compose.yml -f docker-compose.local-build.yml config --quiet
cd backend && .venv/bin/python -m alembic heads
cd backend && .venv/bin/python -m src.quality.mission_cutover_gate --project-root ..
```

Alembic must report one head: `110_deduplicate_mission_references`. The cutover gate must report zero findings.

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
- DataService, Gateway, the default worker, both Mission worker replicas, and frontend are healthy;
- worker inspection includes two consumers for `long_running`, each with concurrency 1 and prefetch 1;
- the model response contains GPT-5.6 Sol, Terra, and Luna only;
- readiness reports DataService, Redis, task backend, and sandbox preflight correctly.

### Mission worker capacity and observability

`mission-worker` deliberately has no `container_name`; Compose creates two replicas from the same service definition. Keep each replica at concurrency 1 and prefetch 1. Scaling is performed by changing the reviewed replica count (or temporarily with `docker compose up -d --scale mission-worker=<n>`), never by increasing per-process concurrency. DataService permits one active dispatch and one active Mission lease per workspace because the current writable Sandbox is workspace-shared; the oldest due Mission receives the next workspace turn. Additional replicas increase cross-workspace throughput, not same-workspace write parallelism.

The reconciler publishes at most two newly runnable Missions per scheduled pass. Every queue message is bound to one dispatch owner/epoch and the default 900-second dispatch lifetime covers normal bounded queue bursts. A stale or superseded message cannot acquire a Mission lease. Subagent model/tool quanta have a separate Redis-backed global capacity of four; this prevents multiplying provider and Sandbox pressure when Mission replicas scale.

Prometheus discovers all Mission worker replicas with Docker DNS under the `wenjin-mission-worker` job. Alert on sustained queue wait, repeated fence loss, reconciliation publication failures, or capacity saturation using:

- `mission_queue_wait_seconds` (intentional countdown is excluded);
- `mission_slice_duration_seconds` and `mission_slices_total`;
- `mission_lease_events_total` and `mission_dispatch_events_total`;
- `mission_reconciliation_total`;
- `mission_subagent_capacity_total`.

Do not add `mission_id`, workspace id, or worker-generated UUIDs as metric labels. Queue wait approaching one slice duration is a capacity warning; repeated `stale_delivery` is normally harmless at-least-once cleanup, but a sustained rise indicates dispatch expiry, broker delay, or duplicate publication pressure.

### Mission preview lifecycle

`celery-beat` publishes `src.task.tasks.cleanup_mission_previews` every five minutes to the
`default` queue. Each bounded delivery uses one UTC cutoff and makes at most five DataService
calls of 200 review projections each. Filesystem cleanup starts only when one of those calls
returns an empty batch, proving that no database row remains expired at that cutoff. If all five
calls return work, the delivery leaves every preview file intact and the next beat continues the
backlog. Once drained, the worker removes expired filesystem refs and unreferenced
content-addressed objects with the same cutoff. Repeated delivery is idempotent. A filesystem
error fails and retries the task; it never rolls back the already-correct DataService transaction
or reports a successful cleanup.

Gateway, Mission workers, and default workers must resolve `MISSION_PREVIEW_ROOT` to the same
private shared volume. Alert on repeated `cleanup_mission_previews` failures and on sustained
growth under that root; do not delete preview files with an external cron job because it can
violate the projection-first ordering.

## 7. Model probes

Generation and native search are separate capability probes.

```bash
cd backend
.venv/bin/python -m src.models.capability_probe \
  --all-enabled-language-models \
  --persist \
  --require-native-search
```

Generation readiness requires strict structured tool arguments, clean Chat Completions streaming termination, xhigh effort support, and response storage disabled.

Docker Compose runs the same persisted probe as the one-shot `model-probe` service after catalog bootstrap. The service reads all enabled language models from the DataService catalog; no model list is duplicated in deployment configuration. `mission-worker` starts only after every enabled language model passes. Existing deployments reuse the completed one-shot container; a clean reseed or rebuilt backend image reruns the provider-bound probes.

Native search uses an independent Responses SSE request. It is usable only when the completed payload includes a `web_search_call`, source receipts, URL citations, and an accepted completion boundary. HTTP success or generated prose alone is not readiness. Search-required Mission policies fail closed while the probe is unavailable.

## 8. Migration policy

Migrations 086-107 are an irreversible development cutover. Do not recreate removed tables or add dual-read/dual-write code. Migration 107 intentionally rejects any existing users, pricing rows, Missions, or credit history because cumulative usage cannot be reconstructed without weakening the accounting contract. For a development database containing pre-cutover data:

1. stop all services;
2. drop the development database/volume;
3. recreate it;
4. run migrations and seed/bootstrap once;
5. verify catalog hashes and the model profile.

Production rollout must be based on a clean snapshot/backup and an explicitly reviewed reseed/import window; migration 107 is not an online historical-data migration.

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

Do not use `down -v` unless intentionally reseeding development data. Runtime code rollback across 086-107 is unsupported; restore a matching database snapshot with the matching application version.
