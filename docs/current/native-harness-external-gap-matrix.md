# Wenjin Native Harness External Gap Matrix

Updated: 2026-06-09

This document records what Wenjin should learn from Codex and deer-flow while keeping Wenjin's execution chain as the source of truth:

`ChatAgent -> LeadAgent -> TeamKernel -> ReactSubagent -> Wenjin Harness -> DataService/Sandbox/Review`

Do not introduce Codex SDK/app-server, cc-switch protocol bridges, deer-flow run stores, deer-flow agent factory, ACP workspace, a generic shell runtime, or a second frontend execution stream.

## Sampled Sources

Codex:

- `/Users/ze/codex/codex-rs/execpolicy/src/policy.rs`
- `/Users/ze/codex/codex-rs/core/src/turn_diff_tracker.rs`
- `/Users/ze/codex/codex-rs/core/src/unified_exec/head_tail_buffer.rs`
- `/Users/ze/codex/codex-rs/core/src/session/turn.rs`
- `/Users/ze/codex/codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs`

deer-flow:

- `/Users/ze/deer-flow/backend/packages/harness/deerflow/agents/middlewares/tool_output_budget_middleware.py`
- `/Users/ze/deer-flow/backend/packages/harness/deerflow/agents/middlewares/sandbox_audit_middleware.py`
- `/Users/ze/deer-flow/backend/packages/harness/deerflow/tools/builtins/task_tool.py`
- `/Users/ze/deer-flow/backend/packages/harness/deerflow/runtime/journal.py`
- `/Users/ze/deer-flow/backend/packages/harness/deerflow/sandbox/*`
- `/Users/ze/deer-flow/backend/packages/harness/deerflow/agents/lead_agent/prompt.py`

## Migration Matrix

| External pattern | Wenjin status | Decision | Reason |
| --- | --- | --- | --- |
| Codex argv/prefix command policy | Partially implemented in `command_audit.py` | Adopt further | Wenjin needs explicit allow/forbid evidence for `run_python`, installs, and future smoke checks, but not a general shell. |
| Codex head/tail output buffer | Implemented via `output_budget.py` | Keep and harden | Bounded preview + output refs is aligned with long-running research tasks. |
| Codex turn diff tracker | Implemented via `diff_tracker.py` | Keep domain-specific | Wenjin tracks sandbox file changes and Prism review items; no need to import Codex patch runtime. |
| Codex explicit approval/runtime policy | Partially implemented | Adopt concept only | Wenjin maps this to capability/skill policy and DataService review, not interactive CLI approval. |
| Codex unified exec sessions | Not implemented | Do not migrate | Wenjin should not expose a generic persistent shell. Experiments run through `sandbox.run_python` and lead-owned job runner. |
| Codex SDK/app-server | Removed from current direction | Do not migrate | Too heavy for Wenjin's vertical workflow; would create a second run/thread model. |
| deer-flow tool-output externalization | Implemented, now read-only output refs are supported | Keep and refine | Explicit refs let agent recover omitted content without listing/searching hidden internals. |
| deer-flow sandbox audit middleware | Partially implemented | Adopt selected checks | Regex/shlex risk classification is useful for install/run audit; keep Wenjin's command contract narrower. |
| deer-flow task/subagent tool | Wenjin has TeamKernel + templates | Do not migrate runtime | The useful idea is delegated context isolation; implementation remains TeamKernel member execution. |
| deer-flow run journal | Partially implemented as harness node metadata/events | Adopt projection shape only | Wenjin already has ExecutionNodeRecord/DataService events; no new run-event table. |
| deer-flow skills prompt injection | Wenjin has capability/skill templates | Adopt caching/selection idea | Skills remain DataService/capability-driven; no mutable SOUL or skill evolution loop for now. |
| deer-flow sandbox providers | Wenjin has Local/Docker providers | Learn hygiene only | One workspace owns one sandbox; no cross-thread sandbox manager or `/mnt/user-data` alias. |

## Current Wenjin Gaps

1. **Output refs have moved under task scratch and now have an explicit recovery tool.**

   New internal refs are now under `/workspace/tmp/tasks/.harness/outputs`, classified as internal, hidden from listing/search/artifact discovery, and read-only through explicit `sandbox.read_output_ref` refs. `sandbox.read_file` remains bounded-compatible for explicit refs, but model guidance should prefer the dedicated facade.

2. **Command audit is strong for Python execution but not yet a reusable policy language.**

   Wenjin should not copy Codex's full execpolicy DSL, but it should expose a compact internal decision object for all sandbox actions: `decision`, `risk_level`, `reason`, `command_preview`, `install_billable=false`, and `blocked_before_job=true`.

3. **Context recovery after large omitted output has a facade, but usage quality still needs real-task tuning.**

   The harness now permits bounded `sandbox.read_output_ref` on explicit output refs and auto-exposes it beside `sandbox.read_file`. The remaining improvement is measuring whether agents actually use refs instead of repeating expensive commands in real SCI workflows.

4. **Workspace filesystem contract is usable but task scratch semantics should keep tightening.**

   Common layout should remain shared across workspace types. Domain differences should stay in `workspace_profile`, not new directories. `tmp/tasks` is the canonical task scratch surface, while reviewable output stays under `outputs`/`reports`.

5. **Quality gates are structural, not yet outcome-quality complete.**

   Literature, experiment, and Prism writing evidence now have deterministic structure checks. The remaining gap is task-quality eval: relevance of papers, citation strength, experiment interpretation, and whether writing edits improve academic style without semantic drift.

## Near-Term Implementation Order

1. Add a compact command-policy decision contract test shared by `run_python`, install, and future smoke checks.
2. Add targeted quality evals for one real SCI workflow: literature package, experiment result, and Prism revision.
3. Tune prompt/tool guidance from real runs where agents repeat commands instead of using output refs.
