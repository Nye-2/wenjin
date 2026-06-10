# Wenjin Native Harness External Gap Matrix

Updated: 2026-06-10

This document records what Wenjin should learn from Codex and deer-flow while keeping Wenjin's execution chain as the source of truth:

`ChatAgent -> LeadAgent -> TeamKernel -> ReactSubagent -> Wenjin Harness -> DataService/Sandbox/Review`

Do not introduce Codex SDK/app-server, cc-switch protocol bridges, deer-flow run stores, deer-flow agent factory, ACP workspace, a generic shell runtime, or a second frontend execution stream.

## Sampled Sources

Codex:

- `/Users/ze/codex/codex-rs/execpolicy/src/policy.rs`
- `/Users/ze/codex/codex-rs/linux-sandbox/src/bwrap.rs`
- `/Users/ze/codex/codex-rs/core/src/turn_diff_tracker.rs`
- `/Users/ze/codex/codex-rs/core/src/unified_exec/head_tail_buffer.rs`
- `/Users/ze/codex/codex-rs/core/src/session/turn.rs`
- `/Users/ze/codex/codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs`
- `/Users/ze/codex/codex-rs/app-server-protocol/schema/typescript/v2/CommandExecParams.ts`
- `/Users/ze/codex/codex-rs/app-server-protocol/schema/typescript/v2/ThreadItem.ts`

deer-flow:

- `/Users/ze/deer-flow/backend/packages/harness/deerflow/agents/middlewares/tool_output_budget_middleware.py`
- `/Users/ze/deer-flow/backend/packages/harness/deerflow/agents/middlewares/sandbox_audit_middleware.py`
- `/Users/ze/deer-flow/backend/packages/harness/deerflow/tools/builtins/task_tool.py`
- `/Users/ze/deer-flow/backend/packages/harness/deerflow/runtime/journal.py`
- `/Users/ze/deer-flow/backend/packages/harness/deerflow/sandbox/*`
- `/Users/ze/deer-flow/backend/packages/harness/deerflow/sandbox/security.py`
- `/Users/ze/deer-flow/backend/packages/harness/deerflow/sandbox/tools.py`
- `/Users/ze/deer-flow/backend/packages/harness/deerflow/sandbox/file_operation_lock.py`
- `/Users/ze/deer-flow/backend/packages/harness/deerflow/sandbox/local/local_sandbox.py`
- `/Users/ze/deer-flow/backend/packages/harness/deerflow/agents/lead_agent/prompt.py`

## Migration Matrix

| External pattern | Wenjin status | Decision | Reason |
| --- | --- | --- | --- |
| Codex argv/prefix command policy | Implemented for Lead-owned `run_python`, `install_dependencies`, and `smoke_check` | Keep narrow | Wenjin now records a compact allow/forbid decision with operation, risk, network, billable, blocked-before-job, and preview; this still intentionally stops short of a general shell. |
| Codex head/tail output buffer | Implemented via `output_budget.py` | Keep and harden | Bounded preview + output refs is aligned with long-running research tasks. |
| Codex turn diff tracker | Implemented via `diff_tracker.py` | Keep domain-specific | Wenjin tracks sandbox file changes and Prism review items; no need to import Codex patch runtime. |
| Codex unified exec lifecycle envelope | Implemented narrowly for `sandbox.run_python` jobs | Keep narrow | Wenjin now records `execution_lifecycle(schema=wenjin.sandbox.execution_lifecycle.v1)` in DataService sandbox job metadata and harness payload: queued/final status, command preview/argv, cwd, env keys, timeout, network profile, environment/runtime, output refs, artifact count and exit code. It deliberately omits raw stdout/stderr/script text and still does not open a persistent shell session. |
| Codex apply_patch interception and turn-level diff | Partially implemented through `sandbox.apply_patch` + file-change summaries | Adopt UX pattern later | Wenjin has safe structured patches and compact diffs, but still lacks a polished review surface for multi-file sandbox diffs comparable to Codex turn diffs. |
| Codex explicit approval/runtime policy | Partially implemented | Adopt concept only | Wenjin maps this to capability/skill policy and DataService review, not interactive CLI approval. |
| Codex writable-root + read-only/deny carveouts | Partially implemented at harness file boundary | Adopt fail-closed boundary, not bwrap runtime | Wenjin already rejects protected/internal paths and symlink escapes at tool boundary; guidance/manifest paths now also fail closed for direct write tools while structured register tools remain allowed. |
| Codex unified exec sessions | Not implemented | Do not migrate | Wenjin should not expose a generic persistent shell. Experiments run through `sandbox.run_python` and lead-owned job runner. |
| Codex SDK/app-server | Removed from current direction | Do not migrate | Too heavy for Wenjin's vertical workflow; would create a second run/thread model. |
| deer-flow tool-output externalization | Implemented, now read-only output refs are supported | Keep and refine | Explicit refs let agent recover omitted content without listing/searching hidden internals. |
| deer-flow sandbox audit middleware | Partially implemented | Adopt selected checks | Regex/shlex risk classification is useful for install/run audit; keep Wenjin's command contract narrower. |
| deer-flow task/subagent tool | Wenjin has TeamKernel + templates | Do not migrate runtime | The useful idea is delegated context isolation; implementation remains TeamKernel member execution. |
| deer-flow parent-child subagent usage reporting | Implemented as harness member transcript projection | Keep as existing metadata projection | `task_tool` reports subagent usage back to `RunJournal`; Wenjin now rolls member tool usage, duration, token usage, scratch refs and evidence paths into `ExecutionNodeRecord.node_metadata.harness.member_execution_transcript`, without creating a parallel RunJournal. |
| deer-flow subagent lifecycle stream | Partially implemented as TeamKernel/RunView progress | Adopt vocabulary only | `task_started` / `task_running` / `task_completed` / timeout/cancel is a useful lifecycle vocabulary. Wenjin should keep existing execution events and team roster projection. |
| deer-flow run journal | Partially implemented as harness node metadata/events | Adopt projection shape only | Wenjin already has ExecutionNodeRecord/DataService events; no new run-event table. |
| deer-flow skills prompt injection | Wenjin has capability/skill templates | Adopt caching/selection idea, reject self-evolution loop | Skills remain DataService/capability-driven; dynamic cache/selection is useful, but mutable SOUL or autonomous skill evolution would drift from admin-managed capability contracts. |
| deer-flow sandbox providers | Wenjin has Local/Docker providers | Learn hygiene only | One workspace owns one sandbox; no cross-thread sandbox manager or `/mnt/user-data` alias. Borrowed hygiene stays provider-local: Docker provider reconciles Wenjin-labeled ephemeral exec containers and retries cleanup after transient failures without adding a second sandbox manager. |
| deer-flow local path gate and file-operation lock | Partially implemented | Adopt selected hygiene | Wenjin validates virtual `/workspace` paths, resolved physical targets and symlink escapes. Direct guidance/manifest writes now fail closed; a future slice can add per-workspace/path async write locks if concurrent same-path writes show up in real runs. |

## Final Boundary Decision Table

| External pattern | Bring into Wenjin | Do not bring |
| --- | --- | --- |
| Codex structured tool evidence | Bounded harness tool-call metadata, file diffs, output refs, command audits, lifecycle summaries | Codex SDK runtime, provider bridge, generic terminal agent |
| Codex sandbox/file discipline | Explicit path policy, protected/internal path masking, read-only output refs, task-scoped cwd/env evidence | `/mnt/user-data`, ACP workspace root, persistent shell sessions |
| deer-flow planner/reporter discipline | TeamKernel quality gates, bounded replan signals, final report/evidence checks | deer-flow graph runtime, message bus, run store |
| deer-flow regression density | Small deterministic tests for path rules, truncation, tool evidence, lifecycle summaries, and replan semantics | Broad compatibility layer or fallback runtime |

## Current Wenjin Gaps

1. **Output refs have moved under task scratch and now have an explicit recovery tool.**

   New internal refs are now under `/workspace/tmp/tasks/.harness/outputs`, classified as internal, hidden from listing/search/artifact discovery, and read-only through explicit `sandbox.read_output_ref` refs. `sandbox.read_file` remains bounded-compatible for explicit refs, but model guidance should prefer the dedicated facade.

2. **Command audit is strong for current sandbox actions but not a reusable shell policy language.**

   The current decision contract covers `run_python`, dependency install, and smoke checks with `operation`, `decision`, `risk_level`, `reason`, `network_profile`, `billable`, `blocked_before_job`, and `command_preview`. Wenjin should still not copy Codex's full execpolicy DSL unless a future dedicated `sandbox.run_command` design is approved with DataService policy, output budget, artifact discovery, kill/cancel, and UI audit.

3. **Context recovery after large omitted output has a facade and run tool companion.**

   The harness now permits bounded `sandbox.read_output_ref` on explicit output refs and auto-exposes it beside `sandbox.read_file` and `sandbox.run_python`. `execution_lifecycle` output refs now roll into `sandbox_execution_summary.output_refs`, and context assembly preserves only explicit `/workspace/tmp/tasks/.harness/outputs/**` refs there. `sandbox_execution_summary` itself is now an allowlisted compact projection, so raw stdout, stderr, tracebacks, command strings and arbitrary runtime payloads cannot enter downstream prompt context; large-output recovery stays behind `output_ref_recovery(schema=wenjin.harness.output_ref_recovery.v1)` with explicit read-tool guidance. This keeps internal refs hidden from list/search/artifact discovery while making omitted stdout/stderr or large diff recovery visible to later members only when they deliberately read the safe ref. Member transcripts now also record `output_refs_read` for refs actually read through `sandbox.read_output_ref`, and deterministic `workflow_trace` projects the filtered refs plus `output_ref_read_count`. The optional `output_ref_reuse` research-task surface now fails when recoverable refs exist but no member reads one through the companion tool, so SCI workflow gates can enforce "inspect prior expensive output before rerunning" without exposing hidden refs to list/search/artifact discovery. Remaining real-task tuning is deciding when repeated commands are acceptable because inputs changed versus when the team prompt should prefer ref reuse.

4. **Workspace filesystem contract is usable; real-task scratch usage still needs tuning.**

   Status: partially closed. Common layout remains shared across workspace types, and domain differences stay in `workspace_profile`, not new directories. `tmp/tasks` is the canonical task scratch root; harness context injects a safe per-execution/member `task_scratch_path`, Lead-owned `sandbox.run_python` now creates `/workspace/tmp/tasks/{execution_id}/{node_id}`, executes with that directory as cwd, and injects `WENJIN_TASK_SCRATCH` / `WENJIN_WORKSPACE_ROOT`. Safe upstream scratch dirs now flow to later members through top-level `scratch_refs[]` from raw upstream sandbox outputs and from existing `member_execution_transcript.scratch_refs`, without being promoted to reviewable artifact candidates. `build_workspace_task_contract(schema=wenjin.workspace_sandbox.task_contract.v1)` is now the single source for task scratch, internal output-ref root, manifest paths, and reviewable artifact roots; `build_agent_workspace_task_contract()` is the safe projection shared by context assembly and Lead-owned run job metadata. It omits raw `output_ref_root`, so internal refs still enter context only when explicitly recoverable through `output_ref_recovery`. TeamKernel syncs current harness evidence after each core batch, so capabilities that declare `max_parallel_invocations=1` get sequential long-chain handoff. Layout guidance/manifest paths are now machine-readable contract files rather than ordinary writable files: direct `sandbox.write_file` / `sandbox.str_replace` / `sandbox.apply_patch` reject them, while `sandbox.register_dataset` and `sandbox.register_artifact` remain the structured manifest update path. `build_agent_workspace_contract()` now exposes `operation_policy(schema=wenjin.workspace_sandbox.operation_policy.v1)` and context assembly projects it to `sandbox.operation_policy`, so tool-using agents see direct write roots, root-level project file compatibility, and structured manifest tools without parsing prose. Borrowing deer-flow's file-operation lock idea but keeping Wenjin's one-sandbox-per-workspace model, `WorkspaceToolScheduler` now uses a workspace read/write queue: read_file/read_output_ref/list_dir/glob/grep can run concurrently, while writes, manifest updates and run_python remain exclusive and writer-prioritized. Reviewable output still belongs under `outputs`/`reports`; the remaining work is real-task tuning: deciding which intermediates become review artifacts, which stay scratch-only, and which workflows should run sequentially versus in parallel.

5. **Quality gates now include workflow trace and early outcome-quality scoring.**

   Literature, experiment, Prism writing evidence, and team `workflow_trace` now have deterministic structure checks. The workflow trace check consumes existing `member_execution_transcript` metadata so a SCI workflow can fail release-gate evaluation when review items exist but no team member transcript shows completed tool activity. `citation_strength` checks strong citation/source support. `experiment_interpretation` checks that sandbox-backed results have method, metric, verified-result, limitation, artifact, and dataset evidence aligned with reproducibility metadata. `paper_relevance` checks that cited/selected papers include topic-aligned refs and no off-topic refs. `statistical_robustness` checks method, sample size, metrics, passed robustness checks, limitations, and artifact/dataset alignment while rejecting critical failed checks. `writing_semantic_preservation` checks Prism review items for bounded structure/semantic-preservation contracts before they count as low-risk writing evidence. SCI sandbox-heavy capability seeds now declare `research_evidence.required_surfaces`, `LeadAgentRuntime._capability_policy()` projects that contract, and `required_surfaces_from_capability_policy()` is the narrow evaluator reader used by the mock SCI E2E to derive required surfaces from capability data instead of hard-coding them in the test. TeamKernel now also enforces capability-required, node-metadata-verifiable research surfaces such as `workflow_trace`, `experiment_interpretation`, `citation_strength`, `paper_relevance`, `statistical_robustness`, and `output_ref_reuse` through the same deterministic evaluator; report/review-item-dependent surfaces such as literature, experiment, writing, and Prism semantic preservation remain final-report/release-gate checks. Remaining gap: reviewer-facing scoring and whether writing edits improve academic style beyond structural semantic preservation.

6. **Member-level usage and execution transcript now has a backend projection.**

   Status: backend projection closed. Codex and deer-flow both make the execution lifecycle easy to audit: command cwd/env/process/output in Codex, caller-bucketed token usage and progress snapshots in deer-flow. Wenjin now projects `member_execution_transcript(schema=wenjin.harness.member_execution_transcript.v1)` from existing `ExecutionNodeRecord.tool_calls` into `node_metadata.harness` and bounded harness context. It records tool counts/names, failures, changed paths, sandbox job/environment ids, safe task scratch refs, explicit output refs read through `sandbox.read_output_ref`, generated artifact count, token usage and duration without raw args, scripts, stdout/stderr, protected paths, arbitrary internal paths, a new run table or a new stream. Context assembly now also allowlists transcript fields and nested usage/billing keys, so accidental raw tool args, scripts, provider payloads or stale `output_ref_read_count` cannot enter downstream prompts. Remaining gap: frontend/team roster visualization and real-task tuning should decide how much of this execution memory is user-visible versus agent-only context.

   Billing is included only as a compact `billing.credits_charged` projection from existing tool calls. It is not a new billing source and does not replace DataService credit transactions.

## Near-Term Implementation Order

1. Run one real SCI workflow through the runtime `research_evidence_required` gate with `workflow_trace` and optional `output_ref_reuse` required, then tune prompts/tools from the failures.
2. Tune prompt/tool guidance from real runs where `output_ref_reuse` fails despite recoverable output refs, or where repeated commands are justified by changed inputs.
3. Add reviewer-facing quality scoring for academic style improvement beyond bounded structural semantic preservation.
4. Design frontend/team-roster and quality-evidence display only after real runs prove which transcript and eval fields help users.
5. If a future generic command tool becomes necessary, design it as a first-class DataService policy feature instead of widening `run_python`.
