# 04 StageAcceptanceContract Spec

Status: Implemented
Updated: 2026-07-15

Depends on: `02_mission_runtime.md`, `05_capability_skill_lite.md`, `06_subagent_runtime.md`, `07_review_commit_runtime.md`

## Goal

Give the WorkspaceAgent freedom to plan and execute while making stage progression deterministic. Quality is built during generation: the Agent freezes its best complete candidate, StageAcceptance verifies it against receipt-backed facts, and a failed stage returns to repair. A user review happens only after quality passes and controls protected workspace writes.

## Code Anchors

| Responsibility | Current source |
|---|---|
| Contract schema | `backend/src/contracts/stage_acceptance.py` |
| Pure evaluator | `backend/src/agents/harness/stage_acceptance.py` |
| Receipt reconstruction | `backend/src/mission_runtime/production.py` |
| Stage/runtime guards | `backend/src/mission_runtime/runtime.py` |
| Provider action schema | `backend/src/agents/workspace_agent/mission_loop.py` |
| Policy seeds | `backend/seed/mission_policies/*/stages.yaml` |

## Contract Shape

```text
schema_version=stage_acceptance_contract.v2
contract_id
version
mission_policy_id
workspace_type
stage_id
stage_goal
minimum_criteria[]
excellent_criteria[]
required_evidence_surfaces[]
required_artifacts[]
failure_modes[]
allowed_actions_if_failed[]
max_revision_attempts
no_progress_limit
recommended_model_effort
prerequisite_stage_ids[]
instantiation
all_item_prerequisite_templates[]
all_item_source_context_key
advance_condition
stop_condition
exemplar_refs[]
require_exemplar_comparison
anti_examples[]
```

The contract states outcomes, not a graph or prescribed chain of thought. It contains no fixed team, mandatory critic, or worker verdict.

## Quality-By-Construction Loop

1. WorkspaceAgent researches, computes, or writes with canonical tools.
2. It calls `artifact.create_candidate` for a complete markdown result, or `academic_visual.render_candidate` for a visual.
3. The tool returns an immutable internal candidate ref. Text candidate identity hashes its complete metadata and body; Sandbox-backed evidence points to sealed content-addressed objects.
4. The server projects a bounded `quality_reference_inventory` from durable candidate/evidence receipts. The Agent emits `quality` by copying exact refs from that inventory with its criterion judgments.
5. `PinnedStageAssessmentBuilder` reconstructs artifacts and evidence from persisted verified MissionItems. Model-authored artifact manifests, hashes, source identity, and output refs have no authority.
6. The pure evaluator returns `pass`, `revise`, `ask_user`, or `stop`.
7. `revise` requires new stage progress and a new complete candidate before another assessment.
8. Only a passed candidate may become a `MissionReviewItem`. That item is user approval for materialization, not a second content-quality gate.

An optional `quality-critic` subagent may be used only when the user explicitly asks to audit an existing output. Ordinary uncertainty remains in the main generation loop and is repaired through evidence, computation, or rewriting. The critic reads the internal candidate through `artifact.read_candidate`, returns findings and repair actions, and never grants or denies stage acceptance.

## Trust Boundary

StageAcceptance accepts only:

- candidate refs whose verified artifact MissionItem belongs to the current stage;
- text candidates whose body, content hash, metadata hash, and candidate ref still agree;
- academic visual candidates with a valid render receipt and manifest;
- evidence refs reconstructed from verified tool/source receipts;
- evidence surfaces permitted by the canonical evidence kind/metadata;
- claim ids explicitly supported by a receipt for claim-evidence alignment;
- exemplar comparisons against pinned exemplar refs.

Every requested candidate must verify. Invalid candidates are not silently dropped. Criterion `supporting_refs` must be a subset of the reconstructed authoritative refs.

Invented, stale, or mismatched quality refs fail provider-decision validation before StageAcceptance runs. The same bounded slice receives precise protocol feedback and may issue a corrected structured action; a malformed ref cannot consume a scientific revision attempt.

## Durable Result

Every check appends one `quality_check` MissionItem and updates the bounded `MissionRun.snapshot_json.stage_acceptance[stage_id]` projection:

```text
contract_ref
stage_id
contract_stage_id
sequence_index
operation_id
result: pass | revise | ask_user | stop
satisfied_criteria[]
missing_criteria[]
missing_evidence_surfaces[]
missing_artifact_kinds[]
missing_exemplar_refs[]
evidence_refs[]
artifact_refs[]
blocking_user_inputs[]
partial_output_refs[]
next_action
failure_fingerprint
progress_state
```

`progress_state` tracks attempt, revision, no-progress count, latest attempt/pass sequence, failed criteria, and next repair action. The immutable MissionItem is the audit record; the bounded snapshot is the fast restore projection.

## Failure Actions

```text
revise_existing
retrieve_more_evidence
ask_user
degrade_with_notice
stop_execution
```

- `revise_existing` repairs the same semantic output and creates a new complete candidate.
- `retrieve_more_evidence` adds verified evidence before rewriting or reassessing.
- `ask_user` creates a durable pause only when required input is genuinely unavailable.
- `degrade_with_notice` may preserve a partial draft but never returns `pass` with missing hard criteria.
- `stop_execution` applies after revision/no-progress limits or an unrecoverable policy boundary and preserves safe partial work.

Reasoning effort is exactly `low | medium | high | xhigh`. `recommended_model_effort` is advice, never a hidden pass condition. The runtime does not silently escalate it.

## Sequential Modeling

Per-item contracts instantiate exact stage ids such as `question_1_model` and `question_1_solution_validation`. The quality decision that passes the policy-defined understanding stage must declare the exact `quality_item_counts` entries for every workload unlocked by that pass. MissionRuntime validates each known `source_context_key`, the 1-100 range, projected prerequisite receipts, and absence of per-item work, then atomically persists stage acceptance and cardinality. Missing or unrelated counts reject the whole quality action; `continue`, a subagent report, generated prose, client parameter, and UI state cannot define cardinality. Completion expands all required per-item stage families from this canonical snapshot value. A single stage that depends on every item must declare `all_item_source_context_key`; template scanning or inferred count sources are forbidden. Prerequisite templates make Question 2 unreachable until the required Question 1 stages pass.

## User Review Boundary

- Review creation requires a passed result for the same stage.
- Review candidates must be among that result's exact `artifact_refs`.
- The server derives preview, source sequence, source refs, content hash, expiry, and materialization descriptor from the accepted receipt.
- The model cannot recopy or replace candidate content in the review action.
- The exact final active-stage candidates must be exposed as current user-reviewable items before Mission completion; intermediate candidates remain internal unless the user requested a checkpoint.
- Mission completion requires the preview to exist, not a user decision. Accept/reject/needs-evidence/commit may happen later and are facts owned by `MissionReviewItem` and `MissionCommit`; they do not alter the quality verdict retroactively.

## Tests

- Missing criteria, evidence surfaces, artifacts, or exemplars return `revise`.
- Unknown criterion or supporting ref is rejected with repairable protocol feedback before stage evaluation.
- A candidate from another stage is rejected.
- A changed body/hash/ref is rejected.
- Every requested candidate must reconstruct from a verified receipt.
- Optional critic output has no acceptance authority.
- Reassessment without new stage progress is rejected.
- Per-item prerequisites block later questions.
- All-item prerequisites without one explicit count source are rejected.
- Review before `pass`, review of a different candidate, and completion without a user-reviewable final candidate are rejected; completion with a pending final review is allowed.
- Lower effort can pass with complete evidence; higher effort cannot pass missing evidence.
