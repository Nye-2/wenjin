# 12 ToolOrchestrator Spec

Status: Implemented; provider search capability currently conditional
Updated: 2026-07-15

Implementation outcome: the frozen canonical ToolCatalog, all Mission tool groups, operation ledger, fencing, policy narrowing, receipts, error taxonomy, model profiles, and independent Responses SSE native-search adapter are implemented. Search-required missions remain correctly unavailable until a live probe returns complete search/source/citation receipts.
Depends on: `02_mission_runtime.md`, `05_capability_skill_lite.md`, `09_permission_pause.md`, `10_sandbox_vnext.md`

## Goal

Give WorkspaceAgent and every subagent one canonical tool boundary. ToolOrchestrator owns discovery, policy resolution, permission/budget preflight, stable operation identity, dispatch, retry discipline, outcome normalization, provenance, and bounded progress projection.

It does not own MissionRun lifecycle, subagent lifecycle, stage acceptance, user-facing narration, MissionReviewItem decisions, MissionCommit, or room-domain writes.

## Cutover Baseline

The table records pre-cutover ownership and the completed target action; it is not a map of current runtime paths.

| Current file | Current responsibility | Target action |
|---|---|---|
| `backend/src/agents/harness/business_tools.py` | Business tool registry and direct dispatch | Move registry/dispatch into ToolOrchestrator; remove direct runtime calls |
| `backend/src/agents/harness/contracts.py` | Tool policy and harness contracts | Split into ToolDescriptor, ToolPolicy, ToolOperation, ResearchToolOutcome |
| `backend/src/agents/harness/command_audit.py` | Sandbox command policy decision | Keep as mandatory SandboxRuntime policy evidence |
| `backend/src/agents/harness/output_budget.py` | Bounds and externalizes large outputs | Keep as common outcome payload boundary |
| `backend/src/services/search/sources/*` | Search provider registry and adapters | Delete old providers; expose only model-native web search tool |
| `backend/src/services/search/sources/model_web_search.py` | Sends `web_search_preview` to ordinary Chat Completions and parses model-authored JSON/Markdown as results | Delete implementation; replace with provider-structured native search adapter after capability probe |
| `backend/src/database/models/model_catalog.py`, `backend/src/models/factory.py`, `backend/src/services/model_gateway.py` | Broad protocol enum, manually declared booleans, Chat Completions model construction | Add versioned ModelCapabilityProfile/probes and strict action adapters; keep Model Catalog as owner |
| `backend/src/subagents/v2/registry.py` | Worker tool-name validation | Rebind validation to versioned ToolCatalog descriptors |
| capability/skill/template allowed-tools fields | Static tool declarations | Resolve through MissionPolicy and ToolPolicy refs, not raw strings alone |

## Canonical Tool Catalog

Every callable tool has one versioned descriptor:

```text
tool_id
tool_version
schema_hash
kind: read | compute | sandbox_mutation | write_candidate
input_schema_ref
output_schema_ref
side_effect_class: none | idempotent | non_idempotent
allowed_callers
required_permissions
network_profile
budget_class
default_timeout
payload_limits
provenance_requirements
```

Rules:

- Tool ids are runtime identifiers, not user labels.
- Unknown tool ids fail explicitly before model execution; they never downgrade to a plain LLM call.
- MissionPolicy, worker skill, workspace type, actor permissions, and subagent scope only narrow availability.
- Deferred/progressive disclosure may hide irrelevant tools from the model context, but the catalog remains the single validation source.
- A descriptor version/hash is captured in MissionRun runtime context before use.
- Model-facing tools are accepted only as provider-structured tool frames with schema-valid arguments. Assistant text containing XML, JSON, Markdown, or a tool name is never parsed into an executable call.

## Policy Resolution

Before dispatch, ToolOrchestrator resolves:

```text
actor/workspace access
mission policy and current stage
caller kind and subagent scope
tool descriptor/version
validated arguments and target refs
permission/approval requirement
budget/credit reservation
network and sandbox profile
side-effect and retry class
```

Unknown high-risk operations fail closed. A tool cannot expand its permissions through prompt text, returned content, MCP metadata, or a nested subagent.

Permission, external-data, and budget interruptions use `09_permission_pause.md`; ToolOrchestrator creates the durable request and returns control to MissionRuntime instead of waiting inside the tool.

## Stable Operation Contract

Every call receives a stable operation identity before any side effect:

```text
mission_id
operation_id
operation_key
command_id
stage_id
caller_id
tool_id
tool_version
args_hash
policy_snapshot_ref
lease_epoch
attempt
```

`operation_key` is derived from mission intent and the atomic effect, not from a random retry. Duplicate queue delivery or model repetition must resolve to the same operation when the intended effect is the same.

The current MissionRun lease epoch fences terminal receipts. A stale driver may return diagnostic trace, but cannot attach a terminal result, charge credits, create a review candidate, or advance a stage.

## Immutable Lifecycle Items

Tool lifecycle is represented by semantic MissionItems sharing `operation_id`:

```text
operation_claim / phase=started
tool_call / phase=started
tool_progress / phase=progress
tool_result / phase=completed | failed | cancelled
operation_terminal / phase=completed | failed
```

Claim and terminal receipts use the stable `operation_key` as their MissionItem operation id. DataService serializes claim/reclaim under the MissionRun row lock and validates the current lease epoch. No fifth operation table or snapshot receipt list participates in recovery.

Progress is bounded and product-oriented. Token chunks, raw provider payloads, full stdout/stderr, and repeated polling records are external refs or transient events, not MissionItems.

Only a terminal tool result can enter evidence, quality, review, or stage progression.

## Retry and Receipt Discipline

| Side-effect class | Retry rule |
|---|---|
| `none` | Retry with bounded backoff and dedupe; cached verified result may be reused |
| `idempotent` | Retry with the same operation key; provider receipt/result is reused |
| `non_idempotent` | Requires explicit policy/approval and a durable prepared item before dispatch; unknown receipt is not retried automatically |

Additional rules:

- Retry budget is shared with MissionRuntime loop budget.
- Same error/tool/args combination enters cooldown after configured repetition.
- No-progress detection can disable a tool for the current mission and force replan or user input.
- Provider success without required provenance is normalized as partial, not success.
- Cancellation prevents future dispatch; late results are recorded only as redacted diagnostics unless they match the active operation and lease.

## Tool State and Error Taxonomy

Per-mission tool state:

```text
available
active
cooldown
degraded
disabled_for_mission
```

Normalized terminal status:

```text
success | partial | error
```

Normalized error types:

```text
rate_limited
no_results
auth_required
permission_denied
tool_unavailable
invalid_input
policy_forbidden
timeout
unsafe_output
provenance_missing
receipt_unknown
capability_unverified
malformed_tool_arguments
```

Each error includes `recoverable_by_model`, `recommended_next_action`, optional `retry_after`, and a user-safe summary. Internal taxonomy may be precise; default UI must not expose provider stack traces or `blocked/high risk/schema` labels.

## ResearchToolOutcome

Terminal tools normalize into:

```text
operation_id
producer
tool_id/version
status/error_type
observed_at
input_refs
summary
evidence_refs
source_refs
artifact_refs
confidence
risk_level
verification_status
recommended_next_action
payload_ref
redaction_applied
```

ToolOrchestrator may create MissionOutput or MissionReviewItem candidates only through MissionRuntime/ReviewCommitRuntime contracts. It never writes a room, applies Prism changes, or updates long-term memory directly.

## ModelCapabilityProfile

Model Catalog owns one typed, versioned profile per model endpoint:

```text
profile_version
model_id
generation_api: chat_completions | responses
structured_tool_calls
strict_tool_arguments
streaming
reasoning_efforts: [low, medium, high, xhigh]
native_web_search
web_search_api: responses_web_search | chat_search_model | none
search_receipts: web_search_call | annotations_sources | none
structured_outputs
vision
observed_at
probe_hash
protocol_conformance
```

Declared config is not proof. Admin save/startup/release probes must verify the exact endpoint/model/API surface with harmless deterministic calls. MissionRuntime snapshots the resolved profile version/hash. A stale or failing capability can degrade health, but a mission requiring that capability fails preflight instead of trying a text fallback.

For LLM catalog entries, migrate the existing table in place: replace the single-value `provider_protocol` enum and drifting `supports_*` booleans with `generation_api`, typed `capability_profile_json`, `capability_probe_json/hash`, and `capability_observed_at`. Do not retain mirrored booleans or hydrate old flags into the new profile. The Model Catalog remains the owner and this adds no table.

Rules:

- Standard tool probe requires a provider tool frame, the expected function name, and schema-valid non-empty arguments.
- Native search probe requires a cleanly completed protocol response, a real search call receipt, and URL citation/source metadata. A plausible answer/URL in prose or a malformed/incomplete transport response is failure.
- User-selected models are never silently rerouted. WorkspaceAgent may ask to switch to a verified model or narrow the task.
- The current baseline enables only `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`, with Terra as the default. Main generation uses Chat Completions with the user's `low | medium | high | xhigh` effort and `store=false`. Native web search is a separate Responses SSE tool transport exposed only after the exact model/endpoint probe proves a completed `web_search_call`, source receipts, URL citations, and the final completion boundary. There is no alternate provider or protocol fallback.

Canonical selected refs are prefix-routed, never guessed. `mission-input:<sha256>` requires `workspace.read_input` and a manifest pinned to the current Mission; `prism-file:`, `artifact-candidate:`, and `sandbox-artifact:` resolve through their own typed readers. A verified `artifact-candidate:` is also valid provenance for a downstream candidate, preserving immutable inter-stage derivation. A subagent receives only refs readable by its pinned tool scope.

Sandbox process exit is distinct from platform failure. A non-zero user script exits as `execution_failed`, carries bounded stderr, is recoverable by a revised model operation, and is never retried inline under the same operation identity. Provider, orchestration, or infrastructure faults use their own typed failures; `internal_error` is not a label for a failed scientific assertion.

## Model-Native Web Search

The only runtime literature/web search tool is model-native web search backed by a probed ModelCapabilityProfile.

Required source metadata:

```text
canonical URL or source identifier
title
publisher/authors when available
observed_at
content hash or snapshot ref
supported claim refs
verification status
```

Rules:

- New integrations use Responses API `{type: "web_search"}`. A Chat Completions path is permitted only for a dedicated, probed search model using its documented search contract; generic chat models plus `tools=[web_search_preview]` are forbidden.
- Search-required stages set tool choice to required/specific search; `auto` cannot prove that retrieval happened.
- The model's prose is not evidence. Only provider `web_search_call`, URL citation annotations, and requested source lists establish retrieval; cited metadata and claim alignment then become evidence inputs.
- SearchResult/ResearchToolOutcome is built from those receipts. Model-authored JSON fields such as title/DOI/authors may enrich a candidate but cannot upgrade verification without a source receipt.
- `source_type` represents domain kind such as web page, paper, dataset, or user upload; it never encodes provider history.
- Semantic Scholar, curated academic, deep search, sandbox web search, and provider fallback are deleted from runtime.
- When native search is unavailable, return a structured evidence gap and partial result; do not fabricate or silently switch providers.

## Sandbox Integration

Sandbox tools are ToolDescriptors whose implementation delegates to SandboxRuntime:

```text
sandbox.run_python
sandbox.run_notebook
sandbox.smoke_check
sandbox.install_dependencies
sandbox.register_dataset
sandbox.register_artifact
sandbox.read_output_ref
```

ToolOrchestrator performs policy, approval, budget, stable operation identity, and outcome normalization. SandboxRuntime owns isolation, path/network/command enforcement, jobs, logs, and manifests. A compiled shell command is never a separate model-facing tool.

## Untrusted Inputs and Payloads

- External pages, papers, repos, and prompt-like content use a read-only delegate when policy requires isolation.
- Tool output cannot inject permissions, system instructions, memory facts, or new tool descriptors.
- Large payloads are externalized with bounded preview, content hash, retention class, and redaction metadata.
- Secret/API-key/raw-auth values never enter MissionItem payload, ResearchToolOutcome, MissionView, or model-visible recovery text.

## Migration

1. Define ToolDescriptor, ToolOperation, ToolPolicy, ToolResultMeta, and ResearchToolOutcome contracts.
2. Build one ToolCatalog and bind capability/skill/template validation to it.
3. Move business/search/sandbox dispatch behind ToolOrchestrator.
4. Add stable operation keys, lease fencing, retry/cooldown/no-progress, and payload externalization.
5. Redesign Model Catalog capability fields around ModelCapabilityProfile and add real endpoint probes.
6. Replace raw tool JSON/text parsing in TeamKernel, MissionRuntime, release gates, and frontend projection with provider-structured frames.
7. Delete the current fake-native `model_web_search.py`, old provider registries, direct subagent tool calls, unknown-tool LLM downgrade, and room-write tools.

## Tests

- Unknown tool fails explicitly and cannot downgrade to plain LLM output.
- MissionPolicy/subagent scope can narrow but never expand ToolCatalog permissions.
- Duplicate at-least-once delivery reuses the same operation and side effect.
- Stale lease epoch cannot attach terminal result, billing, review candidate, or quality evidence.
- Non-idempotent unknown receipt is not retried automatically.
- Retry/cooldown/no-progress limits stop repeated failing calls.
- Large/raw output is externalized and default UI receives only bounded safe summary.
- Model-native web search captures verifiable source metadata and no legacy provider fallback exists.
- Live contract test rejects a provider that returns prose/URLs but no native search receipt.
- Generic Chat Completions `tools=[web_search_preview]` and assistant-text tool parsing fail anti-compat gates.
- Strict tool probe rejects missing/invalid arguments and prevents tool-requiring mission launch on that model.
- Search unavailability returns evidence gap and partial result rather than fabricated citation.
- Sandbox tool cannot bypass SandboxRuntime command/network/path policy.
- Tool output cannot write rooms, Prism, or memory directly.
- Permission/budget pause survives refresh and resumes by stable request/operation id.
