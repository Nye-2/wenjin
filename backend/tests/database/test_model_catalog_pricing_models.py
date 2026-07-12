"""Model catalog, pricing policy, and credit reservation ORM contracts."""

from src.database.models.credit_reservation import (
    CreditReservation,
    CreditReservationScope,
    CreditReservationStatus,
)
from src.database.models.model_catalog import (
    ModelCatalogEntry,
    ModelCategory,
    ModelHealthStatus,
    ModelTrustLevel,
)
from src.database.models.pricing_policy import PricingPolicy, PricingPolicyKind
from src.database.models.user import User
from src.models.capability_profile import (
    GenerationAPI,
    unverified_capability_assessment,
)


def test_model_catalog_entry_contract() -> None:
    assert ModelCatalogEntry.__tablename__ == "model_catalog_entries"
    assert GenerationAPI.CHAT_COMPLETIONS.value == "chat_completions"
    assert ModelCategory.LLM.value == "llm"
    assert ModelCategory.IMAGE.value == "image"
    assert ModelTrustLevel.CUSTOM.value == "custom"
    assert ModelHealthStatus.UNKNOWN.value == "unknown"

    index_names = {idx.name for idx in ModelCatalogEntry.__table__.indexes}
    assert "ix_model_catalog_enabled_category" in index_names
    assert "ix_model_catalog_default_category" in index_names

    assessment = unverified_capability_assessment(
        model_id="default-model",
        model_name="provider-model",
        base_url="https://api.example.com/v1",
        generation_api=GenerationAPI.CHAT_COMPLETIONS,
    )
    entry = ModelCatalogEntry(
        model_id="default-model",
        display_name="Default Model",
        generation_api=GenerationAPI.CHAT_COMPLETIONS,
        provider_name="Custom",
        category=ModelCategory.LLM,
        model_name="provider-model",
        base_url="https://api.example.com/v1",
        encrypted_api_key="ciphertext",
        api_key_last4="abcd",
        api_key_fingerprint="fingerprint",
        capability_profile_json=assessment.profile.model_dump(mode="json"),
        capability_probe_json=assessment.evidence.model_dump(mode="json"),
        capability_probe_hash=assessment.profile.probe_hash,
        capability_observed_at=assessment.profile.observed_at,
    )

    assert entry.enabled is None or entry.enabled is True
    assert entry.is_default is None or entry.is_default is False
    assert entry.capability_probe_hash == assessment.profile.probe_hash
    assert "provider_protocol" not in ModelCatalogEntry.__table__.columns
    assert "supports_tools" not in ModelCatalogEntry.__table__.columns
    assert ModelCatalogEntry.__table__.columns["capability_probe_hash"].nullable is False
    assert ModelCatalogEntry.__table__.columns["capability_observed_at"].nullable is False
    assert entry.config_version is None or entry.config_version == 1


def test_pricing_policy_contract() -> None:
    assert PricingPolicy.__tablename__ == "pricing_policies"
    assert PricingPolicyKind.GLOBAL_CREDIT.value == "global_credit"
    assert PricingPolicyKind.MODEL_USAGE.value == "model_usage"
    assert PricingPolicyKind.MISSION.value == "mission"
    assert PricingPolicyKind.TOOL.value == "tool"
    assert PricingPolicyKind.SANDBOX.value == "sandbox"

    index_names = {idx.name for idx in PricingPolicy.__table__.indexes}
    assert "ix_pricing_policies_kind_enabled" in index_names

    policy = PricingPolicy(
        policy_key="standard-model",
        policy_kind=PricingPolicyKind.MODEL_USAGE,
        name="Standard model policy",
        config_json={"credits_per_1k_weighted_tokens": 6},
    )

    assert policy.enabled is None or policy.enabled is True
    assert policy.version is None or policy.version == 1


def test_credit_reservation_contract() -> None:
    assert CreditReservation.__tablename__ == "credit_reservations"
    assert CreditReservationScope.MISSION.value == "mission"
    assert CreditReservationScope.SANDBOX_OPERATION.value == "sandbox_operation"
    assert CreditReservationScope.THREAD_TURN.value == "thread_turn"
    assert CreditReservationStatus.RESERVED.value == "reserved"
    assert CreditReservationStatus.SETTLED.value == "settled"
    assert CreditReservationStatus.RELEASED.value == "released"
    assert CreditReservationStatus.EXPIRED.value == "expired"

    index_names = {idx.name for idx in CreditReservation.__table__.indexes}
    assert "ix_credit_reservations_user_status" in index_names
    assert "ix_credit_reservations_mission" in index_names

    reservation = CreditReservation(
        user_id="user-1",
        scope=CreditReservationScope.MISSION,
        reserved_credits=500,
        idempotency_key="mission:mission-1",
    )

    assert reservation.status is None or reservation.status == CreditReservationStatus.RESERVED
    assert reservation.settled_credits is None or reservation.settled_credits == 0
    assert reservation.reserved_credits == 500


def test_user_tracks_reserved_credits() -> None:
    assert "reserved_credits" in User.__table__.columns

    user = User(
        email="researcher@example.com",
        name="Researcher",
        hashed_password="x",
        credits=1000,
        reserved_credits=250,
    )

    assert user.credits == 1000
    assert user.reserved_credits == 250
