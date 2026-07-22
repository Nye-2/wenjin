# Mission Runtime Refactor Specs

Status: Implemented; production-environment acceptance pending
Updated: 2026-07-17
Parent overview: `docs/superpowers/specs/mission-runtime-overview.md`

This directory breaks the Mission Runtime overview into implementation-oriented specs. The specs are written for a clean cutover: no long-lived compatibility layer, no dual-write execution path, and no second frontend state system.

The parent overview is authoritative for cross-module boundaries and locked decisions. Before implementation, each owning spec must reflect the overview's 2026-07-10 decisions on lifecycle axes, immutable semantic items, lease fencing, event durability, bounded snapshots, commit granularity, and retention.

## Migration Status

The dependency-ordered clean cut completed in code. The strict anti-compat gate moved from an opening baseline of 490 findings to zero. Test counts are intentionally not frozen in this spec; rerun the commands in `AGENTS.md` for every release candidate.

Final schema chain:

- `086_mission_runtime_cutover`: four Mission tables and removal of retired run stores;
- `087_model_capability_profile`: probe-backed model profiles;
- `088_mission_linked_domains`: Mission provenance across credit/task/source/Prism/sandbox/memory/rooms and removal of retired review/runtime tables;
- `089_mission_policy_catalog`: `mission_policies` + `worker_skills`, old catalogs dropped;
- `090_auxiliary_task_cleanup`: remaining auxiliary task fields removed.
- `091_review_commit_consistency`: review-policy projection and expiring commit-attempt fencing.
- `092_mission_runtime_reliability`: dispatch fencing, operation claims and recovery hardening.
- `093_mission_billing_cutover`: Mission-owned billing linkage.
- `094_workspace_override_cleanup`: final workspace override path removed.
- `095_database_physical_integrity`: complete foreign-key index coverage and redundant-index removal.
- `096_mission_aggregate_references`: enforce same-Mission item/review/commit references at the database boundary.
- `097_workspace_sandbox_provider_cutover`: remove the obsolete configurable sandbox provider.
- `098_mission_user_projection_index`: index the canonical user Mission aggregate and recent-task projection.
- `099_thread_skill_cutover`: remove obsolete thread-level skill state.
- `100_review_output_key_cutover`: enforce one current review item per semantic output key.
- `101_workspace_reasoning_effort_cutover`: replace the obsolete binary thinking flag with the canonical four-level reasoning preference.
- `102_review_policy_projection_cutover`: derive review selection policy at projection time and uniquely fence Mission-created assets by review source.
- `103_dataservice_concurrency_fences`: serialize workspace decision and memory mutations and uniquely fence active partial decisions.
- `104_remove_dataservice_sandbox`: remove the obsolete DataService sandbox aggregate.
- `105_remove_latex_compile_history`: remove direct LaTeX execution and compile-history persistence.
- `106_remove_sandbox_pricing_policy`: converge pricing and credit reservations on Mission-owned billing.
- `107_runtime_accounting`: require Mission execution budgets and add atomic chat-turn authorization/settlement plus user-balance counters.
- `108_remove_workspace_discipline`: remove the unused workspace discipline field from persistence and public contracts.
- `109_subagent_progress_ssot`: remove duplicate snapshot-level worker projections and retain the subagent MissionItem ledger as SSOT.
- `110_deduplicate_mission_references`: project one Mission evidence entry per semantic reference while retaining operation receipts as immutable provenance.

Remaining production-environment acceptance includes the independent native-search probe, production Sandbox attestations, and a real-provider/real-Docker multi-turn browser scenario. Search-required policies correctly fail closed until valid receipts exist. A clean empty-database migration through `110` is the release baseline; 107 rejects non-empty development data and requires drop/reseed.

## Locked Decisions

1. Runtime SSOT is `MissionRun scalar + bounded snapshot + immutable MissionItem ledger`; MissionEvent is transient projection, not persisted truth.
2. Development data can drop/reseed old execution history. Demo preservation, if needed, uses one offline importer.
3. DataService is in scope and may be redesigned for mission runtime.
4. Mission tables must stay small and maintainable: no table per tool, subagent, node, or event type.
5. Admin capability editing is secondary to generation quality, UX, and runtime architecture.
6. Review is item-level at the data layer; frontend can offer review modes and batch actions.
7. First sandbox provider is Docker/rootless workspace provider.
8. `ChatTurnRun` is short-lived chat transport state only. It stays in Redis/memory with TTL and never becomes Mission history. `ThreadTurnBilling` is separate DataService financial truth and never becomes a workflow/run aggregate.
9. `MissionRun` is the only durable long-task run. User-facing Run History is mission history, not chat transport history.
10. `ReviewBatch`, `ChangeSet`, `accepted_ids`, and `accepted_unit_ids` are removed from the runtime review/commit path. `MissionReviewItem` + `MissionCommit` own those duties.
11. DataService migration includes every execution-linked domain: credit, sandbox, source/provenance, Prism, review, task, memory, rooms, and run history.
12. MissionRun status is execution-only: `created | planning | running | waiting | completed | failed | cancelled`. Review and commit are separate status axes.
13. One thread has at most one non-terminal foreground mission; one mission has one active driver protected by lease epoch fencing.
14. Queue delivery is at-least-once. Durable command items and stable operation keys make duplicate delivery safe; MissionEvent and SSE loss recover from snapshot/items.
15. MissionState is a typed runtime view, not a second persistent owner. Snapshot JSON never duplicates canonical scalar columns or stores unbounded detail lists.
16. MissionReviewItem is one atomic domain-write candidate; one MissionCommit applies one accepted item. Frontend batch action does not create a batch domain object.
17. Raw model trace, stdout/stderr, large tool payloads, and old review previews are externalized, redacted, bounded, and TTL-managed. Normalized provider usage is a small immutable `usage_receipt` MissionItem and its cumulative projection is DataService-owned.
18. Every MissionRun captures resolved model, `low | medium | high | xhigh` effort, and prompt/policy/tool/sandbox version refs or hashes.
19. A queue delivery drives one bounded `MissionDriveSlice`; safe checkpoint/yield happens before Celery hard/visibility limits, and the database reconciler owns continuation recovery.
20. MissionRun runnable fields plus immutable command items are the only dispatch intent; domain unique keys own idempotency. The unused DataService operations outbox/idempotency/migration-report domain is deleted.
21. Model actions must arrive as provider-structured tool frames under a probed ModelCapabilityProfile. Assistant text that resembles a tool/search call is never executable evidence.
22. Sandbox execution uses short-lived hardened operation containers with persistent content-addressed workspace/environment state; no long-lived container session becomes runtime truth.
23. Review mode is user-owned workspace/Mission policy injected by the server; the provider cannot select it in a Mission start action.
24. Readable attachments are sealed once as thread-bound `MissionInput` manifests and reach Mission/subagent tools only through `workspace.read_input`; upload markup and parallel attachment readers are deleted.

## Spec Set

| Spec | Purpose | Primary code areas |
|---|---|---|
| `01_workspace_agent.md` | Single WorkspaceAgent and separate chat transport | `backend/src/agents/workspace_agent`, `backend/src/runtime/chat_turns` |
| `02_mission_runtime.md` | MissionRun/MissionItem runtime loop, pause/resume, MissionStore | `backend/src/mission_runtime`, `backend/src/dataservice/domains/mission` |
| `03_dataservice_mission_schema.md` | DataService schema, indexes, API contracts, drop/reseed, execution-linked domain migration | `backend/src/dataservice*`, `backend/src/dataservice_client/*`, `backend/src/database/models/*` |
| `04_stage_acceptance_contract.md` | Stage quality contracts and deterministic assessment | `backend/src/contracts/stage_acceptance.py`, `backend/src/agents/harness/stage_acceptance.py` |
| `05_capability_skill_lite.md` | Two-table MissionPolicy/WorkerSkill catalog | `backend/src/database/models/mission_catalog.py`, `backend/src/services/mission_policy_loader.py` |
| `06_subagent_runtime.md` | Isolated bounded subagent lifecycle | `backend/src/subagent_runtime` |
| `07_review_commit_runtime.md` | MissionReviewItem/ReviewDecision/MissionCommit and review modes | `backend/src/review_commit_runtime` |
| `08_mission_console_frontend.md` | MissionView and on-demand Mission Console | `frontend/lib/api/missions.ts`, `frontend/app/(workbench)/workspaces/[id]/components/mission-console` |
| `09_permission_pause.md` | Mission-level pause, deferred tool approval, user question requests | `backend/src/permission_runtime`, MissionRuntime, tool orchestration, frontend action surfaces |
| `10_sandbox_vnext.md` | Docker/rootless workspace sandbox contract and artifact manifest | `backend/src/sandbox`, `backend/src/tools/mission/runtime.py` |
| `11_mission_trace_run_history.md` | Summary/full history, trace, subagent ledger, replay surface | DataService Mission domain, workspace Runs drawer |
| `12_tool_orchestrator.md` | Canonical tool catalog, model probes, operation lifecycle, native web search | `backend/src/tools/orchestrator`, `backend/src/tools/mission`, `backend/src/services/search/model_native.py` |
| `13_migration_release_gate.md` | Cutover order, deleted paths, anti-compat scan, tests | whole repo |
| `14_academic_visual_generation.md` | Chat-native multi-strategy academic visuals, Prism context, reproducibility, preview, review and commit | `backend/src/academic_visual_runtime`, Mission tools/review, Sandbox, Workspace assets, Prism, Mission Console |

## Cross-Spec Invariants

1. No `MissionRun` means no durable long task.
2. MissionRun scalar columns plus bounded snapshot are the fast restore source; duplicated lifecycle fields are forbidden.
3. `MissionItem` is the only durable process ledger, is immutable after append, and stores semantic milestones rather than raw deltas.
4. `MissionEvent` is a transient projection hint; reconnect uses MissionView plus MissionItems after the last sequence.
5. High-risk citation, claim, evidence, Prism edit, experiment conclusion, and memory writes require review no matter which review mode is selected.
6. Frontend stores cannot own lifecycle, review, commit, or node/subagent state.
7. All old execution runtime writes must disappear in the same cutover as MissionRuntime writes appear.
8. `ChatTurnRun` can be lost without research-state loss; recovery comes from Thread messages, `ThreadTurnBilling` idempotent settlement, and MissionRun snapshots.
9. No runtime code may expose `ReviewBatch` or `ChangeSet` as the task review SSOT after cutover.
10. A valid mission state write must carry the current state version and lease epoch; stale drivers are fenced out.
11. A completed mission may still have pending review items; pending review does not reopen or mutate mission execution status.
12. Active drivers poll durable commands at every safe loop boundary; a lost Redis/Celery hint cannot hide steer, pause, resume, or cancel input.
13. Native web search is exposed only after a live probe returns a real search receipt plus citation/source metadata.
14. `auto_draft`, `regenerate`, and `save_draft_only` are policy/actions, not extra MissionReviewItem lifecycle statuses.
15. Academic visuals route through the canonical `FigureSpec` and `AcademicVisualRuntime`; evidence-bearing figures cannot use generative image strategies.
16. Conversation threads carry chat and model state only; methodology is pinned by MissionPolicy and WorkerSkill, never by a thread-level skill selector.
17. StageAcceptance reconstructs exact current-stage candidates and evidence from verified receipts; optional critic workers have no acceptance authority.
18. MissionReviewItems expose only exact stage-accepted candidates, and Sandbox artifact reads resolve immutable content-addressed objects rather than mutable public paths.
19. Mission input manifests bind workspace, thread, source hash, extracted-content hash, and size; pending preprocessing may promote an attachment later without trusting a client path or requiring re-upload.
20. Terminal review rework resolves one exact source stage, creates a child Mission, and invalidates only its transitive dependency closure; missing lineage never becomes a guessed full replay.
21. Every protected domain write validates the same `MissionWriteAuthority` in the target DataService transaction.
22. All-item stage dependencies declare their cardinality source explicitly; template scanning is not a runtime contract.
