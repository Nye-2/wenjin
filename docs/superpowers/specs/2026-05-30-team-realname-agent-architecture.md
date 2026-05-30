# Team Real-Name Agent Architecture

Date: 2026-05-30
Status: Design ready for review
Scope: Lead Agent v2 runtime, capability team policy, agent templates, dynamic subagent invocation, execution UX projection

## Goal

Build Wenjin's agent system into a user-visible, domain-specific expert team while keeping the runtime architecture converged and auditable.

The goal is not to make agents look friendlier by renaming fixed workflow nodes. The goal is to improve:

1. User experience: users can understand who is working, what each member is responsible for, and why a result is credible.
2. Output quality: literature, evidence, code, experiments, figures, writing, review, and formatting all close their own quality loops.
3. Runtime flexibility: the Lead Agent can recruit suitable members during a run instead of being limited to a precompiled static task graph.
4. Architecture convergence: dynamic teams must fit the existing Chat Agent -> Lead Agent -> ExecutionRecord -> result_card -> Rooms flow, not create a second runtime.

The selected architecture is **B+: Capability-driven Dynamic Team Kernel**.

## Non-Negotiable Constraints

- Keep the two-agent topology: Chat Agent launches work; Lead Agent owns execution.
- Do not bypass the curated `result_card` flow. Team members stage outputs; users still accept before commit.
- DataService remains the long-term source of truth for capability, skill, template, execution, and room data.
- Frontend execution UI must project from execution facts. Do not add a second independent run state system.
- Do not add compatibility layers, fallback routers, alias runtimes, or dual write paths.
- Do not make agent capabilities artificially weak. The system should preserve a high work ceiling, then control risk through sandboxing, staged writes, audit logs, runtime gates, and budget limits.
- Subagents do not recruit other subagents in the first version. Recruitment stays owned by the Lead Agent.

## Current Architecture Fit

Current Wenjin already has the right backbone:

- Capability YAML + DB define executable missions.
- Lead Agent v2 compiles capability graph templates into LangGraph runs.
- Subagent registry and skills provide worker execution hooks.
- `ExecutionRecord` is the canonical execution fact.
- `frontend/lib/execution-run-view.ts` projects execution data into chat receipt, LiveWorkflowPanel, and run drawer.
- `TaskReport` and `result_card` stage outputs before commit into Library, Documents, Decisions, Memory, Tasks, Sandbox, or Prism.

The mismatch is that current `graph_template.tasks` are mostly static. A team-real-name system needs dynamic recruitment and iterative quality closure without mutating LangGraph topology at runtime.

## Core Decision

Use a fixed LangGraph team kernel and represent runtime dynamicity as `AgentInvocation` facts.

```text
Chat Agent
  -> Lead Agent selects capability
  -> Capability.team_policy defines team boundary
  -> Team Kernel runs a stable LangGraph control loop
  -> Lead Agent recruits AgentTemplate instances as AgentInvocations
  -> Subagents produce structured reports and artifacts
  -> Quality gates decide finish, revise, or recruit more
  -> Leader emits result_card
  -> User accepts
  -> Commit service writes rooms
```

This keeps LangGraph stable and checkpointable while allowing the user-visible team to change during execution.

## Runtime Modes

`runtime.mode` is the first-class capability runtime selector:

```yaml
runtime:
  mode: static_graph | team_kernel
```

- `static_graph`: existing deterministic capability graph. It remains for capabilities that are not migrated yet.
- `team_kernel`: new dynamic team architecture.

This is not a fallback layer. The mode is explicit and validated. A capability has exactly one runtime mode.

When a capability is migrated to `team_kernel`, its old static graph entry is removed or replaced cleanly. Runtime code should not silently fall back from one mode to another.

## Concept Model

### Capability

A user-started mission. It defines the product goal, required input, expected outputs, available team pool, quality pipeline, budget, and runtime mode.

Capability should answer: "What outcome did the user ask Wenjin to produce?"

### Team Kernel

A fixed Lead Agent runtime loop that plans, recruits, dispatches, collects, reviews, and iterates.

It should answer: "How does this run stay controlled while still letting the Lead Agent adapt?"

### AgentTemplate

A DataService-managed expert archetype, not a hardcoded person name.

It defines domain role, working style, default skills, tool affinity, risk profile, output contracts, and quality expectations.

Templates answer: "What kind of expert can be recruited?"

### AgentInvocation

A concrete recruited member inside one execution.

It records display name, template, assignment, recruitment reason, effective tools/skills, inputs, outputs, artifacts, status, usage, and errors.

Invocations answer: "Who was actually recruited, what did they do, and what did they produce?"

### Skill

A reusable working method or instruction pack, such as citation screening, experiment reproduction, academic rewriting, or format compliance checking.

Skills answer: "How should this kind of work be performed?"

### Tool

A runtime capability boundary, such as web search, library read, sandbox execution, artifact creation, citation parsing, or staged document writing.

Tools answer: "What external or internal operation can this worker perform?"

### TeamBlackboard

A compact structured shared state maintained by the Lead Agent. It contains confirmed findings, evidence gaps, citation gaps, experiment gaps, writing risks, pending decisions, rejected claims, and quality history.

The blackboard prevents every subagent from reading every transcript and keeps quality review auditable.

### QualityGate

A structured check that turns vague "looks good" judgments into pass/warning/fail decisions with required fixes and suggested recruits.

Quality gates answer: "Is this output good enough to show to the user or commit?"

## AgentTemplate Design

Templates should be domain archetypes, not many one-off named workers.

Initial template set:

| Template ID | Display Role | Responsibility |
| --- | --- | --- |
| `research_scholar.v1` | 文献专家 | Literature search, source screening, evidence extraction, citation quality |
| `methodologist.v1` | 方法专家 | Research design, variables, metrics, methods, feasibility |
| `code_engineer.v1` | 代码工程师 | Code implementation, debugging, scripts, reproducible patches |
| `experiment_runner.v1` | 实验工程师 | Sandbox runs, reproduction logs, parameter records, generated artifacts |
| `data_analyst.v1` | 数据分析师 | Data cleaning, statistics, tables, charts, interpretation |
| `figure_table_specialist.v1` | 图表专家 | Figure/table specs, chart scripts, captions, visual consistency |
| `writing_editor.v1` | 写作编辑 | Academic structure, section drafting, revision, coherence |
| `critical_reviewer.v1` | 质量审稿人 | Unsupported claim checks, logic breaks, missing evidence, risk review |
| `format_compliance_specialist.v1` | 格式审校员 | Thesis, SCI, proposal, patent, and software copyright format checks |
| `generalist_assistant.v1` | 综合助理 | Cleanup, summarization, routing support, low-risk filler work |

Domain-specific templates can be added later when the role is truly different:

- `patent_claim_specialist.v1`
- `grant_proposal_reviewer.v1`
- `sci_response_reviewer.v1`
- `software_doc_specialist.v1`

Runtime display names are generated per invocation:

```text
research_scholar.v1 -> 文献专家
code_engineer.v1 invocation 1 -> 代码工程师 A
code_engineer.v1 invocation 2 -> 代码工程师 B
critical_reviewer.v1 -> 质量审稿人
```

This gives users a concrete team without exploding the data model.

## AgentTemplate Contract

Agent templates should be DB-backed and seedable from YAML:

```yaml
id: research_scholar.v1
enabled: true
display_role: 文献专家
category: research
description: 检索、筛选、归纳文献，并检查引用与证据链质量。

persona_prompt: |
  You are a rigorous academic research specialist...

default_skills:
  - literature_search.v1
  - citation_screening.v1
  - evidence_synthesis.v1

tool_affinity:
  preferred:
    - web_search
    - library_read
    - citation_parser
  can_request:
    - document_read
    - library_write_staged
    - artifact_create

risk_profile:
  network: normal
  filesystem: no_direct_write
  code_execution: not_needed
  room_write: staged_only

output_contracts:
  - literature_evidence_report.v1
  - citation_quality_report.v1

quality_expectations:
  - claims must map to source ids
  - weak or missing evidence must be marked explicitly
  - citation candidates must include traceable metadata when available

runtime_defaults:
  max_turns: 8
  timeout_seconds: 300
```

Important distinction:

- Templates do not own unconditional tool access.
- Templates express tool affinity and risk profile.
- The runtime computes effective access from system, workspace, capability, template, sandbox, and user/account policies.

## Capability Team Policy

`team_policy` defines which members the Lead Agent may recruit for a capability and how aggressively it may iterate.

```yaml
runtime:
  mode: team_kernel

team_policy:
  core_templates:
    - research_scholar.v1
    - writing_editor.v1

  optional_templates:
    - methodologist.v1
    - code_engineer.v1
    - experiment_runner.v1
    - data_analyst.v1
    - figure_table_specialist.v1
    - critical_reviewer.v1
    - format_compliance_specialist.v1
    - generalist_assistant.v1

  recruitment_triggers:
    missing_sources:
      prefer: research_scholar.v1
    unsupported_claims:
      prefer: critical_reviewer.v1
    code_or_experiment_required:
      prefer:
        - code_engineer.v1
        - experiment_runner.v1
    tables_or_figures_required:
      prefer:
        - data_analyst.v1
        - figure_table_specialist.v1
    final_review_required:
      prefer:
        - critical_reviewer.v1
        - format_compliance_specialist.v1

  limits:
    max_iterations: 5
    max_parallel_invocations: 3
    max_invocations_total: 12
    max_invocations_per_template: 3
    no_progress_rounds_before_stop: 2

  budget:
    max_tokens_soft: 120000
    max_tokens_hard: 180000
    max_sandbox_seconds: 900
```

The team is flexible because the Lead Agent decides who to recruit and when. It is stable because the capability controls the available pool, limits, and quality pipeline.

## Tool And Skill Policy

The policy should be high-ceiling, not least-capability-by-default.

### Skills

Skills are reusable work methods:

- `literature_search.v1`
- `citation_screening.v1`
- `evidence_traceability.v1`
- `research_method_design.v1`
- `code_patch_planning.v1`
- `experiment_reproduction.v1`
- `data_analysis.v1`
- `figure_generation.v1`
- `academic_writing_revision.v1`
- `critical_review.v1`
- `format_compliance_check.v1`

A skill can reference recommended tools, prompts, schemas, and quality checks, but does not grant tool access by itself.

### Tools

Tools are runtime operations:

- `web_search`
- `library_read`
- `document_read`
- `memory_read`
- `sandbox_exec`
- `artifact_create`
- `citation_parser`
- `prism_read`
- `prism_change_staged`
- `room_write_staged`

Tools are granted at runtime as effective permissions:

```text
effective_tools =
  system_registered_tools
  filtered by workspace_type policy
  filtered by capability.team_policy
  filtered by agent_template.tool_affinity and risk_profile
  filtered by user/account entitlement
  filtered by sandbox/runtime risk gate
```

This should not become a rigid whitelist that blocks real work. If a high-value task needs a powerful tool, the runtime should allow it when the capability and sandbox policy permit it, then record the decision and keep writes staged.

`room_write_staged` and `prism_change_staged` are proposal tools, not commit tools. A subagent may prepare invocation-local staged proposals, but the Lead Agent still normalizes them into the execution's result card or Prism review items before the user can accept them. No subagent writes directly to a room or mutates a Prism document.

### Safety Boundary

High capability is safe only if dangerous effects are constrained:

- Direct room writes are prohibited for subagents.
- Prism changes are staged review items, not direct document mutation.
- Sandbox execution is isolated and artifact-producing.
- Network and filesystem access are policy-gated and logged.
- Tool calls are recorded per `AgentInvocation`.
- Lead Agent owns recruitment; subagents cannot recursively spawn teams.
- High-risk tool plans can be downgraded, warned, or routed through a safer tool.

## AgentInvocation Contract

Each recruited worker creates an invocation fact:

```ts
type AgentInvocation = {
  id: string
  execution_id: string
  iteration: number
  template_id: string
  display_name: string
  assigned_role: string
  recruitment_reason: string
  input_brief: object
  effective_tools: string[]
  effective_skills: string[]
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled"
  started_at?: string
  completed_at?: string
  output_report?: TaskReport
  artifacts: ArtifactRef[]
  tool_calls: ToolCallSummary[]
  token_usage?: TokenUsage
  error?: InvocationError
}
```

`AgentInvocation` is the factual bridge between backend execution, audit logs, frontend team display, and future debugging.

## TeamBlackboard Contract

The blackboard is part of team kernel state and should be persisted or checkpointed with the execution.

```ts
type TeamBlackboard = {
  mission_summary: string
  confirmed_findings: Finding[]
  evidence_items: EvidenceItem[]
  citation_gaps: Gap[]
  experiment_gaps: Gap[]
  data_gaps: Gap[]
  figure_table_requirements: FigureTableRequirement[]
  writing_risks: Risk[]
  format_risks: Risk[]
  pending_decisions: DecisionRequest[]
  rejected_claims: RejectedClaim[]
  quality_gate_history: QualityGateResult[]
  latest_leader_summary: string
}
```

Subagents receive task-specific slices of the blackboard, not the entire run transcript by default.

The Lead Agent updates the blackboard after each collect phase. Updates should be structured and compact, because the blackboard becomes the stable context for later review and reruns.

## Quality Gate Contract

Quality gates are structured runtime checks:

```ts
type QualityGateResult = {
  gate_id: string
  status: "pass" | "warning" | "fail"
  severity: "low" | "medium" | "high"
  findings: Finding[]
  required_fixes: FixRequest[]
  suggested_recruits: SuggestedRecruit[]
  next_action: "finish" | "revise_existing" | "recruit_more" | "ask_user" | "stop_with_warning"
}
```

Core gates:

| Gate | Purpose |
| --- | --- |
| `evidence_traceability` | Every important claim should map to source, artifact, or explicit assumption |
| `citation_quality` | Citation candidates are relevant, recent enough when needed, and traceable |
| `method_soundness` | Research design, metrics, variables, or experiment plan are coherent |
| `experiment_reproducibility` | Code, parameters, logs, and artifacts are sufficient to rerun |
| `data_table_integrity` | Data transformations, tables, and figures are internally consistent |
| `writing_coherence` | Structure, argument flow, terminology, and academic tone are coherent |
| `critical_review` | Unsupported claims, missing caveats, contradictions, and weak evidence are flagged |
| `format_compliance` | Workspace-specific submission or document format rules are satisfied |

Capabilities choose a pipeline:

```yaml
quality_pipeline:
  - evidence_traceability
  - citation_quality
  - writing_coherence
  - critical_review
  - format_compliance
```

For code or empirical workflows:

```yaml
quality_pipeline:
  - method_soundness
  - experiment_reproducibility
  - data_table_integrity
  - critical_review
```

## Team Kernel Flow

The team kernel is a fixed LangGraph flow:

```text
prepare_context
  -> leader_plan
  -> recruit_members
  -> dispatch_invocations
  -> collect_reports
  -> update_blackboard
  -> quality_gate
  -> decide_next
      -> finish
      -> revise_existing
      -> recruit_more
      -> ask_user
      -> stop_with_warning
```

### prepare_context

Loads capability, workspace context, user brief, relevant room summaries, previous run hints, and entitlement/budget state.

### leader_plan

Creates the initial plan and decides the first team composition. The plan should be explicit enough to display but not so rigid that it prevents adaptation.

### recruit_members

Selects templates from `team_policy`, computes display names, creates `AgentInvocation` records, and resolves effective tools/skills.

### dispatch_invocations

Runs invocations concurrently up to `max_parallel_invocations`. Each invocation uses isolated context, task-specific blackboard slices, effective tools, effective skills, and sandbox policy.

### collect_reports

Normalizes subagent outputs into `TaskReport`, artifact refs, tool summaries, and blackboard update candidates.

### update_blackboard

Merges accepted factual findings, known gaps, risks, and artifact references. Conflicts are recorded instead of silently overwritten.

### quality_gate

Runs configured quality gates. Gates can be deterministic checks, LLM review, artifact validation, citation validation, or sandbox verification.

### decide_next

Uses gate results and limits to choose:

- `finish`: produce final result card.
- `revise_existing`: ask one or more current roles to repair a specific gap.
- `recruit_more`: add a new member because the current team lacks expertise.
- `ask_user`: request missing required decision.
- `stop_with_warning`: return best available output when limits or external blockers prevent full closure.

## LangGraph Feasibility

LangGraph supports the required structure through stable graph nodes, conditional routing, checkpointed state, and parallel dispatch patterns such as `Send`.

The design does not require mutating the compiled graph after execution starts. This avoids a major instability risk.

Runtime dynamicity lives in:

- state fields
- `AgentInvocation` records
- conditional edges
- parallel dispatch payloads
- quality gate decisions

The kernel must set:

- recursion limit
- iteration limit
- invocation count limit
- per-template limit
- concurrency limit
- timeout/cancel handling
- no-progress detection

## Lessons From DeerFlow

The design intentionally borrows several stable patterns from ByteDance DeerFlow:

- Separate subagent config from invocation runtime.
- Use a registry to merge built-in and custom subagent definitions.
- Delegate through a task tool style interface with description, prompt, and subagent type.
- Run subagents in isolated contexts with explicit tool filtering.
- Disable recursive subagent spawning by default.
- Enforce concurrency limits around task calls.
- Detect repeated loop patterns and stop or redirect.
- Stream task started/running/completed/failed events.
- Preserve useful dynamic context while summarizing old context.
- Support timeout and cancellation for long subagent work.

Wenjin should adapt these ideas to its existing `ExecutionRecord`, result card, DataService, and workspace room architecture instead of copying DeerFlow's full runtime shape.

References reviewed:

- LangGraph Graph API documentation for static graph nodes, state, conditional routing, and parallel dispatch.
- LangGraph Deep Agents subagent documentation for isolated subagent contexts and task delegation patterns.
- ByteDance DeerFlow repository for subagent config, registry, task delegation, loop detection, concurrency limits, context summarization, and cancellation patterns.

## Frontend Execution UX

The frontend should show a dynamic team without inventing its own execution state.

Projection source:

```text
ExecutionRecord
  + execution events
  + AgentInvocation facts
  + QualityGateResult facts
  -> frontend/lib/execution-run-view.ts
  -> LiveWorkflowPanel / Runs drawer / chat launch receipt
```

Suggested panel structure:

```text
Current Run
  Mission summary
  Team
    文献专家: completed citation screening
    代码工程师 A: running sandbox experiment
    质量审稿人: waiting for draft
  Quality Gates
    引用质量: warning
    实验复现: running
    写作一致性: pending
  Outputs
    result_card
    artifacts
```

UI principles:

- Team roster is generated from invocations.
- Stage progress is generated from kernel state.
- Gate status is generated from quality results.
- Badges/focus remain UI-only in `run-ui-store`.
- Users should see understandable work status, not internal LangGraph node names.

## DataService And Admin

DataService should own these editable/configurable records:

- `AgentTemplate`
- `Capability`
- `CapabilityTeamPolicy`
- `CapabilitySkill`
- quality gate definitions
- tool/risk policy metadata where appropriate

Admin should allow editing templates and team policies without code changes, but runtime validation must reject invalid or unsafe configurations.

Validation examples:

- unknown template ids
- unknown skill ids
- unknown tool ids
- missing output contracts
- impossible quality pipeline
- max limits outside platform bounds
- high-risk tool request without sandbox policy

## Error Handling

### Subagent Failure

If one invocation fails:

- record failed invocation with error summary
- preserve successful sibling outputs
- let `quality_gate` decide whether to retry, recruit another template, ask user, or finish with warning

### Tool Denial

If a tool is denied by policy:

- record the denial as a tool event
- route to a safer tool when available
- ask Lead Agent to revise plan
- surface a warning only when it affects final output quality

### Quality Gate Failure

Gate failure should not always fail the whole run. It should usually create a targeted repair task.

Examples:

- citation gap -> recruit `research_scholar.v1`
- missing experiment log -> ask `experiment_runner.v1` to rerun and save parameters
- unsupported claim -> ask `critical_reviewer.v1` and `writing_editor.v1` to repair
- format issue -> ask `format_compliance_specialist.v1`

### Limit Reached

When limits are reached:

- stop further recruitment
- produce best available result
- mark unresolved risks in result card
- do not silently pretend the output passed

## Migration Strategy

This should be a clean staged migration:

1. Add team-kernel contracts and persistence behind DataService.
2. Add agent template seeds and validation.
3. Add `runtime.mode` validation to capability loading.
4. Implement team kernel for one narrow but valuable capability, preferably literature-heavy because it demonstrates expert team UX and citation quality.
5. Add frontend projection for team invocations and quality gates.
6. Migrate additional capabilities one by one.
7. Remove or rewrite old static graph definitions when each capability moves to team kernel.

There should be no hidden fallback from `team_kernel` to `static_graph`.

## Initial Capability Candidates

Recommended first capability:

```text
thesis / sci deep research or idea-to-manuscript planning
```

Reason:

- It benefits strongly from visible team roles.
- Literature and evidence gates are easy to explain to users.
- It does not require the full sandbox/code path on day one.
- It exercises research, writing, review, and result card integration.

Second wave:

- code/experiment capability with sandbox reproduction
- full manuscript draft with Prism staged changes
- proposal/patent drafting with format compliance gate

## Testing Strategy

### Contract Tests

- AgentTemplate schema validation.
- Capability `team_policy` validation.
- Runtime mode validation.
- Unknown template/skill/tool rejection.
- Effective tool/skill resolution.

### Runtime Tests

- team kernel finishes a simple run.
- team kernel recruits multiple roles across iterations.
- quality gate failure triggers repair.
- invocation failure does not lose sibling outputs.
- loop limit stops runaway recruitment.
- concurrency limit is enforced.
- subagent cannot recursively recruit.
- cancelled run stops pending invocations.

### Output Tests

- subagent output normalizes into `TaskReport`.
- leader output produces result card.
- room commit still happens only after user acceptance.
- artifacts retain execution and invocation provenance.

### Frontend Tests

- `execution-run-view.ts` projects dynamic team roster.
- LiveWorkflowPanel displays invocation status from facts.
- quality gate status renders pass/warning/fail.
- run-ui-store remains focus/badge only.
- old static graph runs still project through explicit `static_graph` mode.

### Architecture Guards

- subagent runtime cannot call room commit service directly.
- subagent runtime cannot create nested recruitment calls.
- frontend does not infer run facts from UI-only state.
- team kernel runtime does not silently fall back to static graph.
- high-risk tools require sandbox or risk gate metadata.

## Acceptance Criteria

The architecture is successful when:

1. A user can see a concrete expert team working on a run.
2. The Lead Agent can recruit different members in different runs of the same capability.
3. All recruited work is recorded as invocation facts.
4. Literature, evidence, experiment, writing, review, and format quality can be checked as structured gates.
5. High-capability tools are available when needed without direct unsafe writes.
6. Final outputs still go through result cards and user-controlled commit.
7. The frontend shows dynamic team progress from execution facts.
8. Static and team-kernel capabilities are explicit runtime modes, not fallback layers.

## Out Of Scope

- Replacing the Chat Agent.
- Changing the eight workspace room model.
- Allowing fully unbounded multi-agent swarms.
- Letting subagents commit directly to rooms.
- Adding nested subagent recruitment in the first version.
- Rebuilding the whole LiveWorkflowPanel visual design before the execution facts exist.
- Copying DeerFlow runtime code directly.
