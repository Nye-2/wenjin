from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from src.models.capability_profile import (
    CapabilityProfileAssessment,
    GenerationAPI,
    ModelCapabilityProbeEvidence,
    ModelCapabilityProfile,
    ProbeCheckStatus,
    assess_profile_freshness,
    gpt56_release_assessment,
)


def test_release_profile_is_probe_derived_and_search_is_fail_closed() -> None:
    assessment = gpt56_release_assessment("gpt-5.6-sol")

    assert assessment.profile.has_strict_tools() is True
    assert assessment.profile.streaming is True
    assert [item.value for item in assessment.profile.reasoning_efforts] == [
        "low",
        "medium",
        "high",
        "xhigh",
    ]
    assert assessment.profile.response_storage_disabled is True
    assert assessment.profile.native_web_search is False
    assert assessment.profile.probe_hash == assessment.evidence.evidence_hash()
    observations = {
        item.generation_api: item.protocol_conformance
        for item in assessment.profile.transport_observations
    }
    assert observations[GenerationAPI.CHAT_COMPLETIONS] is True
    assert GenerationAPI.RESPONSES not in observations


@pytest.mark.parametrize(
    "model_id",
    ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"],
)
def test_release_profile_is_bound_to_each_gpt56_model(model_id: str) -> None:
    assessment = gpt56_release_assessment(model_id)

    assert assessment.profile.model_id == model_id
    assert assessment.evidence.model_name == model_id
    assert assessment.profile.has_strict_tools() is True


def test_profile_becomes_stale_when_endpoint_identity_changes() -> None:
    assessment = gpt56_release_assessment("gpt-5.6-sol")

    freshness = assess_profile_freshness(
        assessment.profile,
        assessment.evidence,
        model_id="gpt-5.6-sol",
        model_name="gpt-5.6-sol",
        base_url="https://different.example/v1",
        generation_api=GenerationAPI.CHAT_COMPLETIONS,
    )

    assert freshness.current is False
    assert "endpoint_changed" in freshness.reasons


def test_profile_becomes_stale_when_probe_hash_is_modified() -> None:
    assessment = gpt56_release_assessment("gpt-5.6-sol")
    changed_evidence = ModelCapabilityProbeEvidence.model_validate(
        {
            **assessment.evidence.model_dump(mode="json"),
            "checks": [
                {
                    "name": check.name,
                    "status": (
                        ProbeCheckStatus.FAILED.value
                        if check.name == "strict_tool_arguments"
                        else check.status.value
                    ),
                    "detail_code": check.detail_code,
                }
                for check in assessment.evidence.checks
            ],
        }
    )

    freshness = assess_profile_freshness(
        assessment.profile,
        changed_evidence,
        model_id="gpt-5.6-sol",
        model_name="gpt-5.6-sol",
        base_url="https://api.nainai.love/v1",
        generation_api=GenerationAPI.CHAT_COMPLETIONS,
    )

    assert freshness.current is False
    assert "probe_hash_mismatch" in freshness.reasons
    assert "profile_not_probe_derived" in freshness.reasons


def test_assessment_rejects_a_manually_elevated_profile() -> None:
    assessment = gpt56_release_assessment("gpt-5.6-sol")
    elevated = assessment.profile.model_copy(update={"native_web_search": True})

    with pytest.raises(ValidationError, match="native web search requires"):
        CapabilityProfileAssessment(profile=elevated, evidence=assessment.evidence)


def test_profile_age_can_be_enforced_without_changing_hash_semantics() -> None:
    assessment = gpt56_release_assessment(
        "gpt-5.6-sol",
        observed_at=datetime(2026, 7, 1, tzinfo=UTC)
    )

    freshness = assess_profile_freshness(
        assessment.profile,
        assessment.evidence,
        model_id="gpt-5.6-sol",
        model_name="gpt-5.6-sol",
        base_url="https://api.nainai.love/v1",
        generation_api=GenerationAPI.CHAT_COMPLETIONS,
        now=datetime(2026, 7, 10, tzinfo=UTC),
        max_age=timedelta(days=7),
    )

    assert freshness.current is False
    assert freshness.reasons == ("probe_stale",)


def test_unknown_profile_and_probe_versions_are_rejected() -> None:
    assessment = gpt56_release_assessment("gpt-5.6-sol")

    with pytest.raises(ValidationError, match="probe_version"):
        ModelCapabilityProbeEvidence.model_validate(
            {
                **assessment.evidence.model_dump(mode="json"),
                "probe_version": "wenjin.model-capability-probe.v2",
            }
        )

    with pytest.raises(ValidationError, match="profile_version"):
        ModelCapabilityProfile.model_validate(
            {
                **assessment.profile.model_dump(mode="json"),
                "profile_version": "wenjin.model-capability-profile.v2",
            }
        )
