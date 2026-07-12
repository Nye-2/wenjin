# Wenjin Current Documentation Map

> Status: Current source-of-truth index
> Updated: 2026-07-11

`docs/current/` is the only directory that states production behavior. Design/migration specs under `docs/superpowers/specs/mission-runtime/` explain decisions and acceptance history; they do not override current code or this directory.

## Canonical documents

| Document | Sole ownership |
|---|---|
| `architecture.md` | system topology, runtime/data/tool/review/sandbox boundaries, migrations |
| `workspace-current-state.md` | current user-visible workspace, chat, Mission, review, and recovery behavior |
| `frontend-mission-contract.md` | Mission API/SSE, MissionView, chat block, frontend ownership contract |
| `workspace-mission-catalog.md` | MissionPolicy, WorkerSkill, stage and tool-group catalog semantics |
| `workspace-reference-library.md` | Library/source/evidence/BibTeX domain truth |
| `wenjin-research-navigation-uiux.md` | interaction, information architecture, visual/accessibility language |
| `deployment-runbook.md` | Compose topology, rollout, probe, and smoke procedure |
| `environment-variables.md` | configuration meaning and production requirements |
| `release-gate-checklist.md` | release invariants and executable verification |
| `troubleshooting.md` | symptom-first operational diagnosis |

## Reading order

1. `architecture.md`
2. `workspace-current-state.md`
3. the relevant frontend, catalog, Library, or UX contract
4. deployment/release/troubleshooting for operations
5. migration specs only when implementation rationale is needed

## Governance

1. Do not add another current architecture, runtime state, API contract, or catalog truth document.
2. Code wins when a current document disagrees; fix the owning current document in the same change.
3. A concept is defined once and linked elsewhere. Avoid copy-pasted schemas and test results.
4. Historical architecture names may appear only in an explicitly marked retired migration record.
5. New migrations update `architecture.md`, deployment/release docs, and the migration spec index.
6. Mission API/View changes update the frontend contract and workspace state.
7. Policy/skill/stage/tool-group changes update the catalog document.
8. Review/commit/Prism/Library provenance changes update workspace state and the owning domain document.
9. Queue, lease, reconciliation, model probe, search, or sandbox changes update architecture, release gates, and troubleshooting.
10. Visual/interaction changes update the UI/UX document and corresponding browser acceptance.

## Migration design record

The entry point for the completed clean cut is `docs/superpowers/specs/mission-runtime/00_index.md`. `mission-runtime-overview.md` and the numbered specs are design records. Status and remaining acceptance work must be maintained there, but current operational truth remains here.
