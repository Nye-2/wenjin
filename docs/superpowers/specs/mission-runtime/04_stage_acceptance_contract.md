# 04 StageAcceptanceContract Spec

Status: Implemented
Updated: 2026-07-11

Implementation outcome: typed contracts and deterministic evaluation are implemented and production composition validates assessment refs against current candidates. Policy seeds resolve 28 stage contracts. No blocker remains.
Depends on: `02_mission_runtime.md`, `05_capability_skill_lite.md`, `06_subagent_runtime.md`

## Goal

Move Wenjin from fixed workflow progression to quality-gated agent loops. The agent can choose how to research, write, retrieve, and revise, but each stage must satisfy explicit acceptance criteria before advancing.

## Current Code Anchors

| Current file | Current responsibility | Target action |
|---|---|---|
| `backend/src/contracts/research_evidence.py` | Shared research evidence surfaces | Keep surface vocabulary; move into stage contracts |
| `backend/src/agents/harness/research_task_eval.py` | Deterministic eval over TaskReport/review packet/node metadata | Replace TaskReport dependency with MissionItem/MissionOutput/MissionReviewItem evidence |
| `backend/src/agents/harness/research_eval_surfaces.py` | Surface parsing/defaults | Keep as stage acceptance surface registry |
| `backend/src/agents/lead_agent/v2/team/kernel.py` | TeamKernel quality gates and revision routing | Split quality runtime from LeadAgent/TeamKernel |
| Capability YAML `quality_gates`, `research_evidence`, `methodology` | Current quality declarations | Convert into StageAcceptanceContract |

## Contract Shape

```text
contract_id
mission_policy_id
workspace_type
stage_id
stage_goal
minimum_criteria[]
excellent_criteria[]
required_evidence_surfaces[]
required_artifacts[]
failure_modes[]
reviewer_roles[]
allowed_actions_if_failed[]
max_revision_attempts
recommended_model_effort
advance_condition
stop_condition
exemplar_refs[]
anti_examples[]
```

The contract is data, not a graph. It tells the agent what "good enough" means.

## Stage Quality Snapshot

Every quality check appends a MissionItem:

```text
item_type=quality_check
stage_id
operation_id
phase=completed
payload_json={
  contract_id,
  result: pass | revise | ask_user | stop,
  satisfied_criteria,
  missing_criteria,
  evidence_refs,
  artifact_refs,
  reviewer_notes,
  next_action
}
```

`MissionRun.snapshot_json.stage_state_summaries[stage_id]` stores the latest compact snapshot.

The WorkspaceAgent proposes criterion judgments, but it is not an authority for evidence, artifacts, or reviewer verdicts. StageQuality reconstructs evidence from verified tool/source receipts, matches artifacts to persisted MissionReviewItem manifests and hashes, and accepts critiques only from completed isolated reviewer jobs whose structured result names the reviewed candidate refs and criterion ids. `StageGuard` checks prerequisites before continue, tool, subagent, or review execution, not only when the later quality action runs.

`stage_states[stage_id]` must also track:

```text
attempt_count
revision_count
last_attempt_item_seq
last_passed_item_seq
last_failed_criteria
next_repair_action
```

This is required for sequential tasks. A later stage cannot start because a subagent produced text; it advances only after StageQualityRuntime writes a passed quality snapshot for the current stage.

## SCI Example

Stages:

```text
scope_topic
literature_positioning
research_question
method_design
experiment_design
writing_or_revision
```

Examples:

- `research_question` cannot pass without narrow problem, real gap, feasible experiment path, and claim/evidence plan.
- `experiment_design` cannot pass without dataset/baseline/metric/ablation/reproducibility plan.
- `writing_or_revision` cannot pass when contribution claims lack source or artifact references.

## Math Modeling Example

Stages:

```text
problem_understanding
question_1_model
question_1_solution_validation
question_2_model
question_3_model
paper_integration
```

Question 2 cannot start until Question 1 has a valid model, computation path, explanation, and figure/table support.

## Runtime Behavior

When a stage fails:

```text
revise_existing
retrieve_more_evidence
spawn_reviewer
ask_user
degrade_with_notice
stop_execution
```

Agent cannot advance by natural language assertion. Stage advancement must be written by StageQualityRuntime.

Revision behavior:

- `revise_existing` keeps the mission in the same stage and appends a new attempt.
- `ask_user` pauses with `waiting_reason=user_input` or `waiting_reason=clarification`.
- `stop_execution` is used only after configured retries, no-progress detection, budget exhaustion, or a policy-forbidden path. It returns safe partial outputs and a structured failure reason rather than swallowing the result.
- `degrade_with_notice` can produce a draft candidate, but it cannot return `pass` or advance when required criteria are missing.
- High-stakes stages such as SCI research question, experiment design, patent claims, and math-modeling question validation recommend higher model effort and stricter reviewer roles. The effort label is advice, not a hidden pass criterion: outputs pass only by satisfying evidence/artifact/quality criteria. If actual revise/no-progress signals show the selected `low | medium | high | xhigh` effort is inadequate, the runtime asks for a transparent cost/quality confirmation or narrows the task; it neither silently changes effort nor fails solely because the label is lower.

## Deletions / Refactors

- Remove quality logic tied to `TaskReport.review_packet` as final gate.
- Remove LeadAgent-specific quality gate storage as runtime fact.
- Remove frontend interpretation of raw quality gate schema.
- Stop treating "member completed" as "stage passed".

## Tests

- Missing required evidence keeps stage in revise.
- Unsupported citation fails `claim_evidence_alignment`.
- Sandbox artifact without manifest fails experiment stage.
- Writing stage with high-risk Prism semantic contract fails.
- User can choose to continue with degraded state only when contract allows degradation.
- Mission cannot mark completed with failed required stage.
- Repeated revise attempts stop according to `max_revision_attempts` and preserve failure reasons in stage state.
- Math modeling Q2 cannot start when Q1 quality snapshot is not passed.
- `stop` returns available partial outputs and never fabricates missing evidence.
- A stage can pass at lower-than-recommended effort when every hard criterion is met, and cannot pass at higher effort when evidence is missing.
