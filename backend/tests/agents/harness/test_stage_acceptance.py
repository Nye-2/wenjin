"""StageAcceptanceContract progression, repair and stop semantics."""

from src.agents.harness.stage_acceptance import (
    can_start_stage,
    evaluate_stage_acceptance,
    required_contract_stages_passed,
    resolve_stage_instance,
)
from src.contracts.research_evidence import ArtifactRecord, EvidenceRecord
from src.contracts.stage_acceptance import (
    ArtifactRequirement,
    CriterionAssessment,
    CritiqueAssessment,
    ExemplarComparison,
    StageAcceptanceContract,
    StageAssessmentInput,
    StageCriterion,
    StageInstantiationRule,
)
from src.contracts.versioned import ImmutableContentRef


def _contract(**updates) -> StageAcceptanceContract:
    values = {
        "schema_version": "stage_acceptance_contract.v1",
        "contract_id": "sci_research.research_question",
        "version": 1,
        "mission_policy_id": "sci_research",
        "workspace_type": "sci",
        "stage_id": "research_question",
        "stage_goal": "Produce a grounded research question.",
        "minimum_criteria": (
            StageCriterion(
                criterion_id="real_gap",
                description="Gap is source-grounded.",
                required_evidence_surfaces=("claim_evidence_alignment",),
            ),
        ),
        "required_evidence_surfaces": ("claim_evidence_alignment",),
        "required_artifacts": (ArtifactRequirement(kind="research_question_brief"),),
        "reviewer_roles": ("research_question_reviewer",),
        "allowed_actions_if_failed": (
            "revise_existing",
            "retrieve_more_evidence",
            "spawn_reviewer",
            "ask_user",
            "degrade_with_notice",
            "stop_execution",
        ),
        "max_revision_attempts": 2,
        "no_progress_limit": 2,
        "recommended_model_effort": "xhigh",
        "advance_condition": "All minimum criteria pass.",
        "stop_condition": "No feasible question remains.",
    }
    values.update(updates)
    return StageAcceptanceContract.model_validate(values)


def _passing_assessment(**updates) -> StageAssessmentInput:
    values = {
        "stage_id": "research_question",
        "operation_id": "quality:1",
        "criterion_assessments": (
            CriterionAssessment(
                criterion_id="real_gap",
                status="pass",
                supporting_refs=("evidence-1",),
            ),
        ),
        "evidence": (
            EvidenceRecord(
                evidence_id="evidence-1",
                surface="claim_evidence_alignment",
                kind="claim_map",
                status="verified",
                source_ref="mission-item:1",
            ),
        ),
        "artifacts": (
            ArtifactRecord(
                artifact_id="brief-1",
                kind="research_question_brief",
                content_hash="sha256:brief",
            ),
        ),
        "critiques": (
            CritiqueAssessment(
                reviewer_role="research_question_reviewer",
                verdict="pass",
                criterion_ids=("real_gap",),
            ),
        ),
        "actual_model_effort": "low",
        "item_seq": 10,
    }
    values.update(updates)
    return StageAssessmentInput.model_validate(values)


def test_lower_effort_passes_when_hard_evidence_is_complete() -> None:
    result = evaluate_stage_acceptance(_contract(), _passing_assessment())

    assert result.result == "pass"
    assert result.progress_state.last_passed_item_seq == 10


def test_missing_evidence_revises_even_at_xhigh_effort() -> None:
    assessment = _passing_assessment(
        evidence=(),
        actual_model_effort="xhigh",
    )

    result = evaluate_stage_acceptance(_contract(), assessment)

    assert result.result == "revise"
    assert result.next_action == "retrieve_more_evidence"
    assert result.missing_evidence_surfaces == ("claim_evidence_alignment",)


def test_model_criterion_pass_without_independent_critique_does_not_pass() -> None:
    result = evaluate_stage_acceptance(
        _contract(),
        _passing_assessment(critiques=()),
    )

    assert result.result == "revise"
    assert result.missing_criteria == ("real_gap",)
    assert result.missing_reviewer_roles == ("research_question_reviewer",)


def test_blocking_user_input_pauses_instead_of_false_pass() -> None:
    assessment = _passing_assessment(
        criterion_assessments=(),
        blocking_user_inputs=("target_population",),
    )

    result = evaluate_stage_acceptance(_contract(), assessment)

    assert result.result == "ask_user"
    assert result.partial_output_refs == ()


def test_repeated_identical_user_blocker_stops_at_no_progress_limit() -> None:
    contract = _contract(max_revision_attempts=5, no_progress_limit=2)
    blocked = _passing_assessment(
        criterion_assessments=(),
        blocking_user_inputs=("target_population",),
    )

    first = evaluate_stage_acceptance(contract, blocked)
    second = evaluate_stage_acceptance(contract, blocked, previous_state=first.progress_state)
    third = evaluate_stage_acceptance(contract, blocked, previous_state=second.progress_state)

    assert first.result == "ask_user"
    assert second.result == "ask_user"
    assert third.result == "stop"


def test_repeated_no_progress_stops_and_preserves_partial_outputs() -> None:
    contract = _contract(max_revision_attempts=5, no_progress_limit=2)
    failing = _passing_assessment(evidence=(), partial_output_refs=("draft:partial",))

    first = evaluate_stage_acceptance(contract, failing)
    second = evaluate_stage_acceptance(contract, failing, previous_state=first.progress_state)
    third = evaluate_stage_acceptance(contract, failing, previous_state=second.progress_state)

    assert first.result == "revise"
    assert second.result == "revise"
    assert third.result == "stop"
    assert third.next_action == "stop_execution"
    assert third.partial_output_refs == ("draft:partial",)


def test_new_evidence_resets_no_progress_even_if_stage_still_fails() -> None:
    contract = _contract(max_revision_attempts=5, no_progress_limit=2)
    first = evaluate_stage_acceptance(contract, _passing_assessment(evidence=()))
    improved = _passing_assessment(
        evidence=(
            EvidenceRecord(
                evidence_id="new-but-unverified",
                surface="claim_evidence_alignment",
                kind="claim_map",
                status="unverified",
            ),
        )
    )

    second = evaluate_stage_acceptance(
        contract,
        improved,
        previous_state=first.progress_state,
    )

    assert second.result == "revise"
    assert second.progress_state.no_progress_count == 0


def test_excellent_example_comparison_changes_acceptance() -> None:
    exemplar = ImmutableContentRef(ref_id="excellent-1", sha256="a" * 64)
    contract = _contract(
        exemplar_refs=(exemplar,),
        require_exemplar_comparison=True,
    )
    below = _passing_assessment(exemplar_comparisons=(ExemplarComparison(exemplar_ref_id="excellent-1", verdict="below"),))
    meets = below.model_copy(update={"exemplar_comparisons": (ExemplarComparison(exemplar_ref_id="excellent-1", verdict="meets"),)})

    assert evaluate_stage_acceptance(contract, below).result == "revise"
    assert evaluate_stage_acceptance(contract, meets).result == "pass"


def test_math_question_two_cannot_start_before_question_one_passes() -> None:
    validation_rule = StageInstantiationRule(
        mode="per_item",
        source_context_key="problem_questions",
        instance_id_template="question_{index}_solution_validation",
        same_item_prerequisite_templates=("question_{index}_model",),
    )
    q1_contract = _contract(
        contract_id="math_modeling_solution.question_solution_validation",
        mission_policy_id="math_modeling_solution",
        workspace_type="math_modeling",
        stage_id="question_solution_validation",
        instantiation=validation_rule,
        prerequisite_stage_ids=(),
    )
    q1_assessment = _passing_assessment(
        stage_id="question_1_solution_validation",
        contract_stage_id="question_solution_validation",
        sequence_index=1,
    )
    q1_result = evaluate_stage_acceptance(q1_contract, q1_assessment)
    q2_contract = _contract(
        contract_id="math_modeling_solution.question_model",
        mission_policy_id="math_modeling_solution",
        workspace_type="math_modeling",
        stage_id="question_model",
        prerequisite_stage_ids=("problem_understanding",),
        instantiation=StageInstantiationRule(
            mode="per_item",
            source_context_key="problem_questions",
            instance_id_template="question_{index}_model",
            previous_item_prerequisite_templates=("question_{index}_solution_validation",),
        ),
    )

    allowed, missing = can_start_stage(q2_contract, {}, sequence_index=2)
    assert allowed is False
    assert missing == ("problem_understanding", "question_1_solution_validation")

    allowed, missing = can_start_stage(
        q2_contract,
        {
            "problem_understanding": q1_result,
            "question_1_solution_validation": q1_result,
        },
        sequence_index=2,
    )
    assert allowed is True
    assert missing == ()


def test_paper_gate_requires_every_parsed_question_instance() -> None:
    contract = _contract(
        stage_id="paper_integration",
        all_item_prerequisite_templates=("question_{index}_solution_validation",),
    )

    instance = resolve_stage_instance(contract, total_items=4)

    assert instance.prerequisite_stage_ids == (
        "question_1_solution_validation",
        "question_2_solution_validation",
        "question_3_solution_validation",
        "question_4_solution_validation",
    )


def test_dynamic_completion_requires_every_question_family_instance() -> None:
    model_contract = _contract(
        stage_id="question_model",
        prerequisite_stage_ids=(),
        instantiation=StageInstantiationRule(
            mode="per_item",
            source_context_key="problem_questions",
            instance_id_template="question_{index}_model",
        ),
    )
    validation_contract = _contract(
        contract_id="math.question_validation",
        stage_id="question_solution_validation",
        prerequisite_stage_ids=(),
        instantiation=StageInstantiationRule(
            mode="per_item",
            source_context_key="problem_questions",
            instance_id_template="question_{index}_solution_validation",
        ),
    )
    base = evaluate_stage_acceptance(_contract(), _passing_assessment())
    results = {
        "question_1_model": base.model_copy(update={"stage_id": "question_1_model", "contract_stage_id": "question_model"}),
        "question_1_solution_validation": base.model_copy(
            update={
                "stage_id": "question_1_solution_validation",
                "contract_stage_id": "question_solution_validation",
            }
        ),
        "question_2_model": base.model_copy(update={"stage_id": "question_2_model", "contract_stage_id": "question_model"}),
    }

    assert (
        required_contract_stages_passed(
            ("question_model", "question_solution_validation"),
            (model_contract, validation_contract),
            results,
            item_counts={"problem_questions": 2},
        )
        is False
    )

    results["question_2_solution_validation"] = base.model_copy(
        update={
            "stage_id": "question_2_solution_validation",
            "contract_stage_id": "question_solution_validation",
        }
    )
    assert (
        required_contract_stages_passed(
            ("question_model", "question_solution_validation"),
            (model_contract, validation_contract),
            results,
            item_counts={"problem_questions": 2},
        )
        is True
    )
