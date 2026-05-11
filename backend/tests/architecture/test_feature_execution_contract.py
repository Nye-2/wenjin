"""Contract: FeatureExecutionOutcome must carry the canonical result fields.

These tests document the interface of the feature execution result types and
verify that field names remain stable as the codebase evolves.
"""

from src.application.results import (
    FeatureExecutionAdvisory,
    FeatureExecutionOutcome,
    FeatureTaskSubmission,
)


def test_feature_task_submission_has_required_fields():
    """task_id, feature_id, and message must always be present."""
    sub = FeatureTaskSubmission(
        task_id="task-abc",
        feature_id="feature-xyz",
        message="Task queued successfully",
    )
    assert sub.task_id == "task-abc"
    assert sub.feature_id == "feature-xyz"
    assert sub.message == "Task queued successfully"


def test_feature_task_submission_reused_defaults_to_false():
    """reused_existing_task must default to False when not supplied."""
    sub = FeatureTaskSubmission(
        task_id="task-abc",
        feature_id="feature-xyz",
        message="Task queued successfully",
    )
    assert sub.reused_existing_task is False


def test_feature_task_submission_reused_can_be_true():
    """reused_existing_task can be explicitly set to True."""
    sub = FeatureTaskSubmission(
        task_id="task-abc",
        feature_id="feature-xyz",
        message="Reusing existing task",
        reused_existing_task=True,
    )
    assert sub.reused_existing_task is True


def test_feature_execution_advisory_has_required_fields():
    """feature_id, code, and message must always be present on an advisory."""
    advisory = FeatureExecutionAdvisory(
        feature_id="feature-xyz",
        code="RATE_LIMITED",
        message="Too many requests; please retry later",
    )
    assert advisory.feature_id == "feature-xyz"
    assert advisory.code == "RATE_LIMITED"
    assert advisory.message == "Too many requests; please retry later"


def test_feature_execution_advisory_context_defaults_to_none():
    """context must default to None when not supplied."""
    advisory = FeatureExecutionAdvisory(
        feature_id="feature-xyz",
        code="RATE_LIMITED",
        message="Too many requests; please retry later",
    )
    assert advisory.context is None


def test_feature_execution_advisory_context_can_hold_data():
    """context accepts an arbitrary dict when provided."""
    advisory = FeatureExecutionAdvisory(
        feature_id="feature-xyz",
        code="QUOTA_EXCEEDED",
        message="Monthly quota reached",
        context={"quota": 1000, "used": 1000},
    )
    assert advisory.context == {"quota": 1000, "used": 1000}


def test_feature_execution_outcome_accepts_submission():
    """FeatureExecutionOutcome is satisfied by a FeatureTaskSubmission instance."""
    outcome: FeatureExecutionOutcome = FeatureTaskSubmission(
        task_id="task-abc",
        feature_id="feature-xyz",
        message="Task queued",
    )
    assert isinstance(outcome, FeatureTaskSubmission)


def test_feature_execution_outcome_accepts_advisory():
    """FeatureExecutionOutcome is satisfied by a FeatureExecutionAdvisory instance."""
    outcome: FeatureExecutionOutcome = FeatureExecutionAdvisory(
        feature_id="feature-xyz",
        code="NOT_AVAILABLE",
        message="Feature not available in current plan",
    )
    assert isinstance(outcome, FeatureExecutionAdvisory)


def test_feature_task_submission_to_dict():
    """to_dict must return all fields with correct names."""
    sub = FeatureTaskSubmission(
        task_id="task-abc",
        feature_id="feature-xyz",
        message="Task queued",
        reused_existing_task=True,
    )
    result = sub.to_dict()
    assert result == {
        "task_id": "task-abc",
        "feature_id": "feature-xyz",
        "message": "Task queued",
        "reused_existing_task": True,
        "execution_id": None,
    }


def test_feature_execution_advisory_to_dict():
    """to_dict must return all fields with correct names."""
    advisory = FeatureExecutionAdvisory(
        feature_id="feature-xyz",
        code="RATE_LIMITED",
        message="Slow down",
        context={"retry_after": 30},
    )
    result = advisory.to_dict()
    assert result == {
        "feature_id": "feature-xyz",
        "code": "RATE_LIMITED",
        "message": "Slow down",
        "context": {"retry_after": 30},
    }
