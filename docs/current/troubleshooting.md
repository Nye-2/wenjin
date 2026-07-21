# Troubleshooting

> Status: Current
> Updated: 2026-07-11

## 1. Chat says work started, but Mission Console is empty

Check in order:

1. the assistant `status_line.run_id` is a Mission id;
2. `GET /api/missions/{id}` returns an owner-visible MissionView;
3. a `mission_runs` row exists with the expected workspace/thread/user;
4. the `long_running` worker is online;
5. the mission has a due `next_wakeup_at` or an active/expired lease as expected.

Do not infer success from assistant prose. A launch is real only after the Mission row exists. The frontend must refetch MissionView after the receipt.

## 2. Mission remains `created` or `planning`

Inspect `mission-worker` logs and worker queues. It must consume `long_running` with prefetch 1. Verify Celery/Redis, then inspect Mission lease fields and recent items.

Common causes:

- no worker for `long_running`;
- stale model profile or missing policy hash;
- policy references an unknown tool group/stage;
- budget preflight produced a durable wait;
- a provider capability required at start is unavailable.

Never repair this by updating status manually. Fix the prerequisite and resume/reconcile through runtime APIs.

## 3. Mission is `waiting`

Read the latest pause/permission/review item and MissionView waiting request. Waiting is a valid durable state, not a generic failure. Resolve it through:

- chat steering/resume;
- `POST /api/missions/{id}/actions`;
- `POST /api/missions/{id}/permissions/{request_id}/resolve`;
- review/commit endpoints.

A stale queue hint must not claim an undelayed waiting mission. If it does, treat it as a MissionStore regression.

## 4. Duplicate work or side effect

Collect `mission_id`, `operation_id`, item sequences, lease epoch/owner, state version, and commit/request id. Check that:

- only the current lease epoch executed the effect;
- tool operation start/completion receipts share one operation id;
- retries reused the idempotency key;
- commit materialization used the same request id;
- stale workers failed their fence before side effects.

Do not deduplicate by hiding duplicate UI rows. The durable operation/commit boundary must prevent the duplicate.

## 5. Mission SSE disconnects or skips sequence

Mission SSE is an invalidation channel. Reconnect with `Last-Event-ID`; on any gap, visibility restore, malformed event, or Redis interruption, fetch MissionView and needed items again. Do not replay hints into a local workflow state.

If events are absent but canonical state changes, the UI should still recover on polling/refocus/manual refresh. If events arrive for another owner/workspace, stop release and fix isolation.

## 6. Search-required Mission refuses to start

This is expected when native search cannot be verified. Check the model profile freshness and independent Responses SSE search capability.

Valid search requires a completed `web_search_call`, source receipts, URL citations, and the accepted completion boundary. These are failures:

- HTTP success without a search call;
- generated citations without provider source receipts;
- completed response with empty sources;
- transport ends before the verified completed payload;
- probe belongs to another endpoint/model/API hash.

Do not enable another provider or mark a static flag. Restore provider conformance, rerun the probe, and atomically update the model profile evidence.

## 7. Main GPT-5.6 chat fails

Verify the DataService model row is enabled/default and uses Chat Completions generation with the correct `/v1` base URL. Check decryption key stability and pricing policy. Then run the capability probe.

Strict structured tools, clean streaming termination, `store=false`, and the selected reasoning effort must pass. Responses is not a fallback generation protocol.

## 8. Unknown or forbidden tool

Inspect the pinned Mission tool policy and production ToolCatalog.

- `unknown`: the id/group is not registered; fix policy/catalog deployment.
- `policy_forbidden`: the mission or subagent scope does not grant it; do not widen at call time.
- `permission_required`: resolve the specific durable request.
- `tool_unavailable`: provider/runtime prerequisite is down.
- `provenance_missing`: output lacks required receipts/evidence.
- `rate_limited`: retry only according to the operation policy.

The catalog is frozen at worker startup and the mission pins exact ids. Restart/reseed after a deliberate catalog change.

## 9. Stage will not advance

Inspect the latest stage assessment and contract. Typical causes are missing required artifact/evidence, unsupported criterion refs, blockers, minimum effort, or exhausted iteration budget. The model cannot pass a stage with prose alone; supporting refs must belong to current candidates.

Revise the stage output or provide missing material. Do not bypass the contract or manually jump `active_stage_id`.

## 10. Review item cannot be accepted or saved

Check ownership, item status, review mode, preview availability/expiry, target, base revision/hash, and current document version.

- `needs_more_evidence`: generate supporting material first;
- stale base: regenerate preview against current content;
- protected item unchecked: review individually;
- accepted but unsaved: call commit with that item id;
- partial commit: inspect per-item results, not only the aggregate status.

Never write directly to Prism/rooms to work around review state.

## 11. Mission Console disagrees after refresh

The browser must hydrate from MissionView and Mission history. Clear only presentation focus if needed; do not preserve a client workflow state over the server projection. Verify the console uses `frontend/lib/api/missions.ts` and that History queries workspace missions.

## 12. Mission history is empty

Verify `GET /api/workspaces/{workspace_id}/missions`, owner identity, and workspace id. Chat turn run history is not research history. A direct advisory chat correctly creates no Mission entry.

## 13. Sandbox preflight fails

`mission-worker` runs release preflight before it consumes any task. Inspect the structured check report first:

```bash
docker compose logs mission-worker
docker compose run --rm --no-deps mission-worker python -m src.sandbox.preflight --release
```

Check:

- `SANDBOX_DOCKER_SOCKET` names a local unix socket and the source is mounted only at `/var/run/docker.sock` in `mission-worker`;
- `SANDBOX_DOCKER_GID` equals the container-visible mounted socket GID; after changing it, recreate rather than restart the container;
- rootless/userns requirement;
- pinned image digest exists or can be pulled by policy;
- non-root uid/gid;
- seccomp is not unconfined;
- root directory and bind identity;
- quota attestation;
- package egress network/proxy/index/allowlist completeness.

Production readiness must remain unhealthy until preflight passes. Do not switch to host execution.

For `docker_socket_access` failures, compare the report's process UID/GIDs with socket UID/GID/mode. Resolve the host value and recreate the worker:

```bash
export SANDBOX_DOCKER_SOCKET="${SANDBOX_DOCKER_SOCKET:-/var/run/docker.sock}"
export SANDBOX_DOCKER_GID="$(docker run --rm \
  -v "$SANDBOX_DOCKER_SOCKET:/var/run/docker.sock" \
  --entrypoint stat \
  "${BACKEND_GATEWAY_IMAGE:-junze0514/wenjin-backend:latest}" \
  -c '%g' /var/run/docker.sock)"
docker compose up -d --force-recreate mission-worker
```

Do not chmod the socket world-writable, mount it into the default worker, enable a TCP Docker endpoint, set an attestation merely to silence the gate, or enable rootful production fallback.

## 14. Sandbox cannot read/write a file

Confirm the path is inside the managed workspace, not protected/internal, and does not escape through a symlink. Mutation also requires read-before-write base hash/revision. Re-read the current file and regenerate the operation rather than dropping the precondition.

Large stdout/stderr/diffs become output refs. Absence from inline payload does not mean data loss; inspect the bounded receipt and allowed ref.

## 15. Mission worker died mid-slice

The lease should expire and the reconciler should republish a due mission. Verify no terminal status, `lease_expires_at`, `next_wakeup_at`, and the last durable item. A replacement worker must claim a new epoch and stale effects must fail fencing.

Do not clear lease columns manually except during controlled incident recovery with an audited DataService operation.

## 16. Credits are reserved but Mission failed

Inspect the Mission billing snapshot and `credit_reservations.mission_id`. Reservation must be idempotent. Settlement records zero or policy-defined actual charge for failed/cancelled work and estimated/actual charge for completed work. Missing durable reservation is a runtime error, not a reason to synthesize one in the UI.

## 17. Migration fails around 086-108

These are irreversible development migrations. Confirm the chain is linear and `alembic heads` reports `108_remove_workspace_discipline`. Migration 107 rejects non-empty users, pricing, Mission, or credit data by design. Drop/reseed instead of reconstructing removed tables or resetting cumulative counters. The release check runs the complete chain on an isolated empty PostgreSQL database as well as the migration contract tests.

## 18. DataService or Gateway import fails

Run:

```bash
cd backend
.venv/bin/python -c "from src.dataservice_app.app import app; print(app.title)"
.venv/bin/python -c "from src.gateway.app import app; print(app.title)"
```

Import errors after the clean cut usually indicate a stale contract/test import. Remove or migrate the caller; do not restore an alias module.

## 19. Anti-compat gate fails

```bash
cd backend
.venv/bin/python -m src.quality.mission_cutover_gate --project-root .. --json
```

Every production finding is release-blocking. Delete/migrate the path. Do not exclude another file merely to make the scan green.

## 20. Browser test looks successful but no real work occurred

Correlate the UI with Mission rows/items, worker logs, tool/subagent receipts, stage assessments, evidence, review items, and commit results. Require multiple observable state transitions and at least one refresh/reconnect. A mock-only Playwright pass is necessary but not sufficient for production acceptance.
