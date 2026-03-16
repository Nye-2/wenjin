# ADR: Platform Layer Boundaries

- Status: Accepted
- Date: 2026-03-16
- Decision: Establish strict layer boundaries for AcademiaGPT-V2

## Context

AcademiaGPT-V2 has grown organically, resulting in routers that contain business
orchestration logic (credit billing, literature thresholds, task submission,
failure compensation). This makes routers hard to test, audit, and evolve
independently.

## Decision

### Layer Definitions

| Layer | Location | Responsibility | Prohibited |
|-------|----------|---------------|------------|
| **Router** | `gateway/routers/` | HTTP adaptation: auth, param binding, call handler, return contract | Business orchestration, direct DB queries for billing, direct service calls for credit/literature |
| **Handler** | `application/handlers/` | Request-level orchestration: qualification checks, credit billing, task submission, failure compensation, error mapping | Direct DB access, HTTP concerns |
| **Feature/Service** | `workspace_features/`, `services/` | Business logic implementation | HTTP concerns, cross-cutting orchestration |
| **Task** | `task/` | Async task lifecycle: submission, polling, progress, completion | HTTP concerns |
| **Contract** | `gateway/contracts/` | Shared DTOs, error models, pagination models | Business logic |
| **Access Control** | `gateway/access_control.py` | Owner isolation, workspace ownership verification | Business logic beyond auth |

### Migration Order

1. Phase 1: Unify auth + owner isolation + error envelope across all routers
2. Phase 2: Extract business orchestration from `features.py` into `application/handlers/`
3. Phase 3: Task system idempotency and reliability
4. Phase 4+: Upstream unification, observability, frontend convergence

### Prohibited Patterns

1. **Router MUST NOT** import or call `CreditService` directly
2. **Router MUST NOT** contain conditional business logic (literature threshold checks, etc.)
3. **Router MUST NOT** implement failure compensation (refund on queue failure)
4. **Router MUST** use `get_current_user` for all mutating endpoints
5. **Router MUST** verify workspace ownership for workspace-bound operations

### API Lifecycle

| Route Group | Status | Action |
|------------|--------|--------|
| `/api/workspaces/{id}/features/{id}/execute` | **Active** | Primary entry point for all feature execution |
| `/api/thesis/*` | **Deprecated** | Retain for 1 release cycle (min 30 days), add deprecation headers |
| `/api/papers/*` | **Active** | Add auth + owner isolation |
| `/api/artifacts/*` | **Active** | Add auth + owner isolation |
| `/api/academic/papers/*` | **Deprecated** | Retain for compatibility, no new capabilities |
| `/api/academic/workspaces/*/artifacts/*` | **Deprecated** | Retain for compatibility, no new capabilities |

## Consequences

- Routers become thin HTTP adapters, easier to test and audit
- Business logic changes don't require router changes
- Clear ownership boundaries reduce merge conflicts
- Migration is incremental: each phase is independently deployable and rollback-safe
