# Environment Variables

> Status: Current
> Updated: 2026-07-11

`.env.example` is the exhaustive template. This document records architectural meaning and production requirements. `.env` is local and must never be committed.

## Model

| Variable | Meaning |
|---|---|
| `LLM_MODELS` | bootstrap/test seed; current LLM list contains GPT-5.6 Sol/Terra/Luna only |
| `LLM_IMAGE_MODELS` | bootstrap/test seed; current image list contains `gpt-image-2` only |
| `LLM_DEFAULT_MODEL` | bootstrap default, currently `gpt-5.6-terra` |
| `LLM_TIMEOUT` | provider request timeout |
| `LLM_MAX_RETRIES` | bounded transport retry count |
| `LLM_AGENT_TIMEOUT` | bounded agent-turn timeout |
| `LLM_TOOL_TIMEOUT` | per-tool timeout |
| `LLM_TOOL_OUTPUT_MAX_CHARS` | inline tool-output budget |
| `MODEL_SECRET_KEY` / `MODEL_SECRET_KEY_FILE` | stable 32-byte key for encrypted model credentials |
| `MISSION_PREVIEW_ROOT` | private filesystem root for expiring Mission review previews |
| `MISSION_PREVIEW_TTL_SECONDS` | preview lifetime before cleanup |
| `MISSION_PREVIEW_MAX_BYTES` | maximum accepted preview object size |
| `WORKSPACE_ASSET_ROOT` | controlled root for accepted WorkspaceAsset bytes |

Runtime model discovery is DataService-backed. `LLM_MODELS` and `LLM_IMAGE_MODELS` are bootstrap seeds, not runtime fallbacks. GPT-5.6 rows use `generation_api: "chat_completions"`; `gpt-image-2` uses the Images API adapter. Both use the `/v1` provider base URL, a model-usage pricing policy, and disabled response storage where the protocol supports it.

The independent native-search transport derives its Responses endpoint from the verified model config. There is no separate search-provider API key or alternate research provider. Availability comes from receipt-backed probe evidence, not an environment boolean.

Reasoning effort wire values are `low`, `medium`, `high`, and `xhigh`. Deployment default is `xhigh`.

## Data and runtime

| Variable | Requirement |
|---|---|
| `DATABASE_URL` | PostgreSQL async URL; Gateway must not use it as a Mission transaction shortcut |
| `DATASERVICE_URL` | internal DataService base URL |
| `DATASERVICE_INTERNAL_TOKEN` | strong shared internal credential |
| `DATASERVICE_TIMEOUT_SECONDS` | bounded client timeout |
| `REDIS_ENABLED` | `true` for Gateway/worker deployment |
| `REDIS_URL` | workspace event/cache Redis DB |
| `REDIS_STREAM_MAX_CONNECTIONS` | dedicated stream pool capacity |
| `CELERY_ENABLED` | `true` for chat and Mission work |
| `CELERY_BROKER_URL` | Celery broker, normally Redis DB 1 |
| `CELERY_RESULT_BACKEND` | Celery results, normally Redis DB 2 |
| `CELERY_TASK_SOFT_TIME_LIMIT` | task soft limit; Mission work is sliced before this |
| `CELERY_TASK_TIME_LIMIT` | task hard limit |

Queue names and Mission worker prefetch are deployment commands in `docker-compose.yml`, not user-configurable workflow data. `worker` consumes `default,priority`; `mission-worker` consumes `long_running` with prefetch 1.

## Sandbox vNext

| Variable | Requirement |
|---|---|
| `SANDBOX_PROVIDER` | only `docker` |
| `SANDBOX_DEPLOYMENT_MODE` | `development`, `test`, or `production` |
| `SANDBOX_ROOT_DIR` | managed workspace/environment/output root |
| `SANDBOX_OUTPUT_REF_TTL_SECONDS` | temporary referenced-output lifetime |
| `SANDBOX_DOCKER_SOCKET` | host unix socket mounted only into `mission-worker`; remote Docker endpoints are rejected |
| `SANDBOX_DOCKER_GID` | required container-visible socket GID mapped only into `mission-worker`; there is no default |
| `SANDBOX_DOCKER__IMAGE` | operation image name |
| `SANDBOX_DOCKER__IMAGE_DIGEST` | immutable sha256 digest; mandatory for Mission compute |
| `SANDBOX_DOCKER__USER_UID/GID` | non-root container identity |
| `SANDBOX_DOCKER__SECCOMP_PROFILE` | confined profile; `unconfined` is rejected |
| `SANDBOX_DOCKER__WORKSPACE_QUOTA_ATTESTED` | production storage control attestation |
| `SANDBOX_DOCKER__BIND_MOUNT_IDENTITY_ATTESTED` | production mount identity attestation |

Package installation additionally requires the nested egress network, proxy, HTTPS package index, explicit host allowlist, and `ENFORCEMENT_ATTESTED=true`. Partial configuration fails validation. Provider-native search does not give the sandbox general internet access.

The shared `.env` file is loaded by backend containers, but the default Celery worker starts through `src.sandbox.preflight --strip-sandbox-env`, which removes every `SANDBOX_*` variable before replacing itself with the worker process. Only `mission-worker` receives the Docker socket, supplemental socket group, explicit sandbox deployment settings, and sandbox authority. Its entry point runs `python -m src.sandbox.preflight --release` before joining `long_running`; failure exits the container instead of exposing a degraded worker.

Set the group from the socket metadata as it appears inside a Linux container. This is authoritative on Linux and Docker Desktop, where the host and bind-mounted GIDs may differ:

```bash
export SANDBOX_DOCKER_SOCKET="${SANDBOX_DOCKER_SOCKET:-/var/run/docker.sock}"
export SANDBOX_DOCKER_GID="$(docker run --rm \
  -v "$SANDBOX_DOCKER_SOCKET:/var/run/docker.sock" \
  --entrypoint stat \
  "${BACKEND_GATEWAY_IMAGE:-junze0514/wenjin-backend:latest}" \
  -c '%g' /var/run/docker.sock)"
```

Release preflight verifies actual process access to the mounted unix socket, Docker daemon isolation and seccomp, immutable image identity and image environment, workspace/quota and bind identity attestations, proxy-only package network enforcement, and a live temporary read-before-write policy probe. Attestation variables record externally provisioned controls; set them to `true` only after those controls have been independently established.

## Security and bootstrap

Production must replace `JWT_SECRET_KEY`, `ADMIN_PASSWORD`, `DB_PASSWORD`, `DATASERVICE_INTERNAL_TOKEN`, `GRAFANA_PASSWORD`, and model credentials. `E2E_TEST_HOOKS_ENABLED` must be `false`. Development-only rootful sandbox acceptance must be `false` in production.

`ENVIRONMENT`, `CORS_ORIGINS`, SMTP, Sentry, Prometheus, layout parsing, image VLM, LaTeX, and image generation variables keep their domain-specific meanings from `.env.example`; they do not alter the Mission architecture.

## Frontend

- `NEXT_PUBLIC_API_URL`: browser API prefix, normally `/api`;
- `WENJIN_DEV_API_PROXY_TARGET`: local Next.js proxy target;

## Validation rules

1. No secrets in git, logs, Mission items, or model probe payloads.
2. Three enabled LLMs: GPT-5.6 Sol/Terra/Luna, with Terra as the sole default.
3. Model profile hash must match endpoint/model/API configuration.
4. Native search cannot be enabled by configuration alone.
5. Production sandbox must pass preflight before readiness is healthy.
6. Redis and Celery are required for Gateway runtime mode.
