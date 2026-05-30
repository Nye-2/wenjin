# Credit Billing Foundation Design

## Scope

This phase turns the existing credit ledger into a stronger billing foundation without adding payments, SKU pricing, invoices, subscriptions, or compatibility layers.

The implementation scope is:

- Settle workspace feature executions from measured token usage.
- Enforce configured overdraft ceilings during credit consumption.
- Present user-facing billing as credits only; token usage remains internal accounting metadata.
- Charge non-LLM sandbox operations as fixed-credit ledger transactions.
- Replace the registration invite-code stub with a real referrer lookup path.

## Architecture

Credit persistence remains owned by DataService. Runtime services continue to use the typed `AsyncDataServiceClient`; gateway and task orchestration do not import credit ORM models directly.

`CreditService` remains the runtime facade for admission checks, token-to-credit calculation, fixed operation billing, consumption, and refunds. DataService owns balance mutation, row locking, transaction creation, and idempotent refund lookup.

Feature execution billing is attached to the execution lifecycle, not the UI:

1. Lead execution collects provider token usage during runtime and records it in `ExecutionRecord.result_json.token_usage`.
2. The execution completion path settles token usage through `CreditService.consume_for_feature_usage`.
3. Billing metadata is persisted with the execution result so refund paths and dashboards can trace the charge.
4. Consumption commands carry a stable idempotency key so worker retries do not double-charge.
5. Failed or cancelled tasks refund by transaction id when one exists.

Thread billing keeps its current turn-level behavior, but user-facing dashboard and ledger projections expose credits only. Token counters and token-to-credit policy details are kept out of `/dashboard/me`, `/dashboard/me/credits/costs`, and the user credit-history metadata projection.

Sandbox billing is operation-based. `sandbox.run_python` consumes a configured fixed number of credits before the Docker sandbox is acquired. The transaction uses the same `workflow_consume` ledger type with `metadata.type = sandbox_operation_billing`, `feature_id = sandbox.run_python`, and an execution/node idempotency key.

## Overdraft Policy

The existing policy field `max_overdraft_credits` becomes enforceable. A consume request may take the balance below zero only down to `-max_overdraft_credits`.

When a calculated charge would exceed that floor, DataService rejects the consume command. Admission checks still block new work for users at zero or negative balance after free quotas are exhausted.

## Idempotency And Compensation

DataService is the idempotency boundary for credit consumption. Runtime callers pass `metadata.idempotency_key`; DataService checks that key while holding the user balance lock and returns the existing transaction instead of creating a duplicate.

Feature execution billing uses `feature_token_billing:{execution_id}`. Thread turn billing uses `thread_token_billing:{user_message_id}` once the user message has been persisted. Sandbox Python billing uses `sandbox_operation_billing:{execution_id}:{node_id}:run_python`.

If feature billing succeeds but execution completion persistence fails, the execution engine immediately refunds the billing transaction before marking the execution failed.

## Invite Codes

The registration `invite_code` field resolves to an existing user referrer instead of returning `None`. The first implementation uses a stable user-id based invite format and keeps referral bonus logic in `ReferralService`.

Invalid invite codes do not block registration; they simply do not create a referral. Self-referral remains rejected by `ReferralService`.

## Tests

Target tests cover:

- Feature usage settlement writes a `workflow_consume` transaction and stores billing metadata.
- Feature billing is skipped for zero/no token usage.
- Feature consumption is idempotent across execution retries.
- Sandbox Python operations charge fixed credits and replay idempotently for the same execution node.
- User dashboard and credit-history projections do not expose token counters or token policy fields.
- Feature billing is refunded when completion persistence fails.
- Runtime-collected provider token usage reaches `TaskReport.token_usage`.
- DataService rejects credit consumption beyond the configured overdraft floor.
- Thread and feature consume paths pass the overdraft policy into DataService.
- Thread turns carry user-message based idempotency metadata.
- Registration invite codes resolve an existing referrer and create referral records.
