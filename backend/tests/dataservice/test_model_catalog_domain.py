"""Tests for DataService model catalog domain behavior."""

from __future__ import annotations

import base64
from types import SimpleNamespace
from typing import Any

import pytest

from src.database.models.model_catalog import ModelCategory, ModelHealthStatus
from src.database.models.pricing_policy import PricingPolicyKind
from src.dataservice.common.errors import DataServiceConflictError, DataServiceValidationError
from src.dataservice.domains.model_catalog.security import (
    ModelApiKeyCipher,
    ModelCatalogSecurityError,
    api_key_last4,
    decrypt_api_key,
    encrypt_api_key,
    load_model_secret_key,
    redact_api_key,
    validate_model_base_url,
)
from src.dataservice.domains.model_catalog.service import DataServiceModelCatalogService
from src.models.capability_profile import (
    GenerationAPI,
    gpt56_release_assessment,
    unverified_capability_assessment,
)


class _FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.flush_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def flush(self) -> None:
        self.flush_count += 1


class _FakeModelCatalogRepository:
    def __init__(self) -> None:
        self.rows: dict[str, SimpleNamespace] = {}

    async def create_model(self, values: dict[str, Any]) -> SimpleNamespace:
        row = SimpleNamespace(
            id=f"row-{len(self.rows) + 1}",
            created_at=None,
            updated_at=None,
            last_tested_at=None,
            last_test_error=None,
            **values,
        )
        self.rows[row.model_id] = row
        return row

    async def get_model(self, model_id: str) -> SimpleNamespace | None:
        return self.rows.get(model_id)

    async def list_models(
        self,
        *,
        category: str | None = None,
        enabled_only: bool = False,
    ) -> list[SimpleNamespace]:
        rows = list(self.rows.values())
        if category is not None:
            rows = [row for row in rows if _enum_value(row.category) == category]
        if enabled_only:
            rows = [row for row in rows if row.enabled]
        return rows

    async def unset_default_models(self, *, category: str, except_model_id: str | None = None) -> None:
        for row in self.rows.values():
            if _enum_value(row.category) == category and row.model_id != except_model_id:
                row.is_default = False


class _FakePricingPolicyRepository:
    def __init__(self) -> None:
        self.rows: dict[str, SimpleNamespace] = {
            "model-standard": SimpleNamespace(
                id="policy-row-1",
                policy_key="model-standard",
                policy_kind=PricingPolicyKind.MODEL_USAGE,
                enabled=True,
            ),
            "model-disabled": SimpleNamespace(
                id="policy-row-2",
                policy_key="model-disabled",
                policy_kind=PricingPolicyKind.MODEL_USAGE,
                enabled=False,
            ),
            "sandbox-standard": SimpleNamespace(
                id="policy-row-3",
                policy_key="sandbox-standard",
                policy_kind=PricingPolicyKind.SANDBOX,
                enabled=True,
            ),
        }

    async def get_policy(self, policy_id_or_key: str) -> SimpleNamespace | None:
        return self.rows.get(policy_id_or_key)


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _test_key() -> str:
    return "base64:" + base64.urlsafe_b64encode(b"0" * 32).decode("ascii")


def _model_catalog_service() -> tuple[DataServiceModelCatalogService, _FakeModelCatalogRepository, _FakeSession]:
    session = _FakeSession()
    service = DataServiceModelCatalogService(
        session,  # type: ignore[arg-type]
        master_key=b"0" * 32,
        autocommit=True,
    )
    repository = _FakeModelCatalogRepository()
    service.repository = repository  # type: ignore[assignment]
    service.pricing_repository = _FakePricingPolicyRepository()  # type: ignore[assignment]
    return service, repository, session


def _model_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model_id": "deepseek-v3",
        "display_name": "DeepSeek V3",
        "generation_api": "chat_completions",
        "provider_name": "QnAIGC",
        "category": "llm",
        "model_name": "deepseek/deepseek-v3",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-live-1234abcd",
        "enabled": True,
        "is_default": True,
        "pricing_policy_id": "model-standard",
        "default_headers": {"X-Provider": "qnaigc"},
    }
    payload.update(overrides)
    return payload


def test_model_api_key_cipher_round_trips_with_authenticated_context() -> None:
    cipher = ModelApiKeyCipher(_test_key())

    token = cipher.encrypt("sk-live-secret", aad="model:deepseek-v3")

    assert token.startswith("v1:")
    assert token != "sk-live-secret"
    assert cipher.decrypt(token, aad="model:deepseek-v3") == "sk-live-secret"


def test_model_api_key_cipher_rejects_different_authenticated_context() -> None:
    cipher = ModelApiKeyCipher(_test_key())
    token = cipher.encrypt("sk-live-secret", aad="model:deepseek-v3")

    with pytest.raises(ModelCatalogSecurityError, match="decrypt"):
        cipher.decrypt(token, aad="model:qwen-max")


def test_model_api_key_function_helpers_bind_ciphertext_to_model_id() -> None:
    master_key = load_model_secret_key(env={"MODEL_SECRET_KEY": _test_key()})

    token = encrypt_api_key("sk-live-secret", model_id="deepseek-v3", master_key=master_key)

    assert decrypt_api_key(token, model_id="deepseek-v3", master_key=master_key) == "sk-live-secret"
    with pytest.raises(ModelCatalogSecurityError, match="decrypt"):
        decrypt_api_key(token, model_id="qwen-max", master_key=master_key)


def test_load_model_secret_key_prefers_file(tmp_path, monkeypatch) -> None:
    key_file = tmp_path / "model-secret.key"
    key_file.write_text(_test_key(), encoding="utf-8")
    monkeypatch.setenv("MODEL_SECRET_KEY_FILE", str(key_file))
    monkeypatch.setenv("MODEL_SECRET_KEY", "this-env-value-is-long-enough-but-not-used")

    assert load_model_secret_key() == b"0" * 32


def test_load_model_secret_key_rejects_missing_or_short_key() -> None:
    with pytest.raises(ModelCatalogSecurityError, match="MODEL_SECRET_KEY"):
        load_model_secret_key(env={})
    with pytest.raises(ModelCatalogSecurityError, match="32 bytes"):
        load_model_secret_key(env={"MODEL_SECRET_KEY": "short"})


def test_load_model_secret_key_rejects_all_zero_placeholder() -> None:
    placeholder = "base64:" + base64.urlsafe_b64encode(bytes(32)).decode("ascii")

    with pytest.raises(ModelCatalogSecurityError, match="all-zero placeholder"):
        load_model_secret_key(env={"MODEL_SECRET_KEY": placeholder})


def test_redact_api_key_keeps_only_tail() -> None:
    assert api_key_last4("sk-live-1234abcd") == "abcd"
    assert redact_api_key("abcd") == "sk-****abcd"
    assert redact_api_key(None) is None


@pytest.mark.parametrize(
    "url",
    [
        "http://api.example.com/v1",
        "https://localhost:8000/v1",
        "https://127.0.0.1/v1",
        "https://10.0.0.12/v1",
        "https://172.16.0.3/v1",
        "https://192.168.1.2/v1",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/v1",
    ],
)
def test_validate_model_base_url_rejects_insecure_or_private_production_targets(url: str) -> None:
    with pytest.raises(ModelCatalogSecurityError):
        validate_model_base_url(url)


def test_validate_model_base_url_accepts_public_https_url_and_normalizes_trailing_slash() -> None:
    assert validate_model_base_url("https://api.example.com/v1/") == "https://api.example.com/v1"


def test_validate_model_base_url_can_allow_local_development_targets_explicitly() -> None:
    assert (
        validate_model_base_url(
            "http://localhost:8000/v1/",
            allow_private_network=True,
            require_https=False,
        )
        == "http://localhost:8000/v1"
    )


@pytest.mark.asyncio
async def test_create_model_encrypts_key_and_returns_redacted_record() -> None:
    service, repository, session = _model_catalog_service()

    record = await service.create_model(_model_payload(), admin_id="admin-1")

    stored = repository.rows["deepseek-v3"]
    assert record.model_id == "deepseek-v3"
    assert record.api_key_redacted == "sk-****abcd"
    assert "api_key" not in record.model_dump(mode="json")
    assert stored.encrypted_api_key.startswith("v1:")
    assert stored.encrypted_api_key != "sk-live-1234abcd"
    assert stored.api_key_last4 == "abcd"
    assert stored.created_by_admin_id == "admin-1"
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_removed_capability_switches_are_rejected() -> None:
    service, _repository, _session = _model_catalog_service()

    with pytest.raises(DataServiceValidationError, match="unsupported model catalog fields"):
        await service.create_model(_model_payload(supports_tools=True))


@pytest.mark.asyncio
async def test_endpoint_change_invalidates_capability_assessment() -> None:
    service, _repository, _session = _model_catalog_service()
    created = await service.create_model(_model_payload())

    updated = await service.update_model(
        "deepseek-v3",
        {"base_url": "https://changed.example.com/v1"},
    )

    assert updated is not None
    assert updated.capability_profile.protocol_conformance is False
    assert updated.capability_probe_hash != created.capability_probe_hash
    assert updated.health_status == "unknown"


@pytest.mark.asyncio
async def test_probe_assessment_must_match_exact_current_endpoint() -> None:
    service, _repository, _session = _model_catalog_service()
    await service.create_model(
        _model_payload(
            model_id="gpt-5.6-sol",
            display_name="GPT-5.6 Sol",
            model_name="gpt-5.6-sol",
            provider_name="OpenAI",
            base_url="https://api.nainai.love/v1",
        )
    )
    assessment = gpt56_release_assessment("gpt-5.6-sol")

    record = await service.update_capability_assessment(
        "gpt-5.6-sol",
        profile=assessment.profile,
        evidence=assessment.evidence,
    )

    assert record is not None
    assert record.health_status == "healthy"
    assert record.capability_profile.has_strict_tools() is True

    await service.update_model(
        "gpt-5.6-sol",
        {"base_url": "https://changed.example.com/v1"},
    )
    with pytest.raises(DataServiceValidationError, match="does not match"):
        await service.update_capability_assessment(
            "gpt-5.6-sol",
            profile=assessment.profile,
            evidence=assessment.evidence,
        )


@pytest.mark.asyncio
async def test_probe_assessment_rejects_profile_from_different_evidence() -> None:
    service, _repository, _session = _model_catalog_service()
    await service.create_model(
        _model_payload(
            model_id="gpt-5.6-sol",
            display_name="GPT-5.6 Sol",
            model_name="gpt-5.6-sol",
            provider_name="OpenAI",
            base_url="https://api.nainai.love/v1",
        )
    )
    verified = gpt56_release_assessment("gpt-5.6-sol")
    unverified = unverified_capability_assessment(
        model_id="gpt-5.6-sol",
        model_name="gpt-5.6-sol",
        base_url="https://api.nainai.love/v1",
        generation_api=GenerationAPI.CHAT_COMPLETIONS,
    )

    with pytest.raises(DataServiceValidationError, match="not derived"):
        await service.update_capability_assessment(
            "gpt-5.6-sol",
            profile=verified.profile,
            evidence=unverified.evidence,
        )


@pytest.mark.asyncio
async def test_enabled_model_requires_enabled_model_usage_pricing_policy() -> None:
    service, _repository, _session = _model_catalog_service()

    with pytest.raises(DataServiceValidationError, match="enabled model requires enabled model_usage pricing policy"):
        await service.create_model(_model_payload(pricing_policy_id=None))

    with pytest.raises(DataServiceValidationError, match="enabled model requires enabled model_usage pricing policy"):
        await service.create_model(_model_payload(model_id="bad-kind", pricing_policy_id="sandbox-standard"))

    with pytest.raises(DataServiceValidationError, match="enabled model requires enabled model_usage pricing policy"):
        await service.create_model(_model_payload(model_id="disabled-policy", pricing_policy_id="model-disabled"))


@pytest.mark.asyncio
async def test_disabled_model_can_be_saved_without_pricing_policy_until_enabled() -> None:
    service, _repository, _session = _model_catalog_service()

    record = await service.create_model(_model_payload(enabled=False, is_default=False, pricing_policy_id=None))

    assert record.enabled is False
    assert record.pricing_policy_id is None

    runtime = await service.get_runtime_model(record.model_id)
    assert runtime is not None
    assert runtime.model_id == record.model_id
    assert runtime.api_key == "sk-live-1234abcd"


@pytest.mark.asyncio
async def test_enabling_model_requires_pricing_policy() -> None:
    service, _repository, _session = _model_catalog_service()
    await service.create_model(_model_payload(enabled=False, is_default=False, pricing_policy_id=None))

    with pytest.raises(DataServiceValidationError, match="enabled model requires enabled model_usage pricing policy"):
        await service.update_model("deepseek-v3", {"enabled": True})

    record = await service.update_model("deepseek-v3", {"enabled": True, "pricing_policy_id": "model-standard"})

    assert record is not None
    assert record.enabled is True
    assert record.pricing_policy_id == "model-standard"


@pytest.mark.asyncio
async def test_admin_record_redacts_secret_default_headers() -> None:
    service, repository, _session = _model_catalog_service()

    record = await service.create_model(
        _model_payload(default_headers={"api-key": "tp-cvt-secret-token", "X-Provider": "qnaigc"})
    )

    stored = repository.rows["deepseek-v3"]
    assert stored.default_headers["api-key"] == "tp-cvt-secret-token"
    assert record.default_headers == {"api-key": "[redacted]", "X-Provider": "qnaigc"}


@pytest.mark.asyncio
async def test_runtime_models_decrypt_keys_only_for_internal_payload() -> None:
    service, _repository, _session = _model_catalog_service()
    await service.create_model(_model_payload())

    runtime_models = await service.list_runtime_models(category=ModelCategory.LLM)

    assert len(runtime_models) == 1
    runtime = runtime_models[0]
    assert runtime.model_id == "deepseek-v3"
    assert runtime.api_key == "sk-live-1234abcd"
    assert runtime.base_url == "https://api.example.com/v1"
    assert runtime.default_headers == {"X-Provider": "qnaigc"}


@pytest.mark.asyncio
async def test_image_model_category_is_supported() -> None:
    service, _repository, _session = _model_catalog_service()

    await service.create_model(
        _model_payload(
            model_id="image-gen",
            model_name="image-gen-v1",
            category="image",
            generation_api=None,
            is_default=False,
        )
    )

    runtime_models = await service.list_runtime_models(category=ModelCategory.IMAGE)

    assert len(runtime_models) == 1
    assert runtime_models[0].model_id == "image-gen"
    assert runtime_models[0].category == "image"


@pytest.mark.asyncio
async def test_default_model_must_be_enabled_on_create() -> None:
    service, _repository, _session = _model_catalog_service()

    with pytest.raises(DataServiceValidationError, match="default model must be enabled"):
        await service.create_model(_model_payload(enabled=False, is_default=True))


@pytest.mark.asyncio
async def test_setting_new_default_unsets_previous_default() -> None:
    service, repository, _session = _model_catalog_service()
    await service.create_model(_model_payload(model_id="deepseek-v3", is_default=True))
    await service.create_model(_model_payload(model_id="qwen-max", model_name="qwen-max", is_default=True))

    assert repository.rows["deepseek-v3"].is_default is False
    assert repository.rows["qwen-max"].is_default is True


@pytest.mark.asyncio
async def test_cannot_disable_only_enabled_default_model() -> None:
    service, _repository, _session = _model_catalog_service()
    await service.create_model(_model_payload())

    with pytest.raises(DataServiceConflictError, match="default"):
        await service.update_model("deepseek-v3", {"enabled": False})


@pytest.mark.asyncio
async def test_model_id_is_immutable_on_update() -> None:
    service, _repository, _session = _model_catalog_service()
    await service.create_model(_model_payload())

    with pytest.raises(DataServiceValidationError, match="model_id"):
        await service.update_model("deepseek-v3", {"model_id": "qwen-max"})


@pytest.mark.asyncio
async def test_category_is_immutable_on_update() -> None:
    service, _repository, _session = _model_catalog_service()
    await service.create_model(_model_payload())

    with pytest.raises(DataServiceValidationError, match="category"):
        await service.update_model("deepseek-v3", {"category": "image"})


@pytest.mark.asyncio
async def test_default_model_must_remain_enabled_on_update() -> None:
    service, _repository, _session = _model_catalog_service()
    await service.create_model(_model_payload())
    await service.create_model(_model_payload(model_id="qwen-max", model_name="qwen-max", is_default=False))

    with pytest.raises(DataServiceConflictError, match="default model must be enabled"):
        await service.update_model("deepseek-v3", {"enabled": False})


@pytest.mark.asyncio
async def test_default_model_cannot_be_unset_directly() -> None:
    service, _repository, _session = _model_catalog_service()
    await service.create_model(_model_payload())

    with pytest.raises(DataServiceConflictError, match="cannot be unset"):
        await service.update_model("deepseek-v3", {"is_default": False})


@pytest.mark.asyncio
async def test_disabled_model_cannot_be_made_default_on_update() -> None:
    service, _repository, _session = _model_catalog_service()
    await service.create_model(_model_payload())
    await service.create_model(
        _model_payload(
            model_id="qwen-max",
            model_name="qwen-max",
            enabled=False,
            is_default=False,
        )
    )

    with pytest.raises(DataServiceConflictError, match="default model must be enabled"):
        await service.update_model("qwen-max", {"is_default": True})


@pytest.mark.asyncio
async def test_update_without_api_key_preserves_existing_encrypted_key() -> None:
    service, repository, _session = _model_catalog_service()
    await service.create_model(_model_payload())
    encrypted_before = repository.rows["deepseek-v3"].encrypted_api_key

    record = await service.update_model("deepseek-v3", {"display_name": "DeepSeek V3.1"})

    assert record is not None
    assert record.display_name == "DeepSeek V3.1"
    assert repository.rows["deepseek-v3"].encrypted_api_key == encrypted_before
    assert repository.rows["deepseek-v3"].api_key_last4 == "abcd"


@pytest.mark.asyncio
async def test_update_can_clear_optional_runtime_fields() -> None:
    service, repository, _session = _model_catalog_service()
    await service.create_model(
        _model_payload(
            pricing_policy_id="model-standard",
            timeout_seconds=30,
            max_retries=2,
            default_headers={"X-Provider": "qnaigc"},
        )
    )

    record = await service.update_model(
        "deepseek-v3",
        {
            "timeout_seconds": None,
            "max_retries": None,
            "default_headers": None,
        },
    )

    assert record is not None
    row = repository.rows["deepseek-v3"]
    assert row.pricing_policy_id == "model-standard"
    assert row.timeout_seconds is None
    assert row.max_retries is None
    assert row.default_headers == {}
    assert record.default_headers == {}


@pytest.mark.asyncio
async def test_disabled_model_can_clear_pricing_policy() -> None:
    service, repository, _session = _model_catalog_service()
    await service.create_model(_model_payload(is_default=False, pricing_policy_id="model-standard"))

    record = await service.update_model("deepseek-v3", {"enabled": False, "pricing_policy_id": None})

    assert record is not None
    assert record.enabled is False
    assert repository.rows["deepseek-v3"].pricing_policy_id is None


@pytest.mark.asyncio
async def test_health_update_stores_redacted_error() -> None:
    service, repository, _session = _model_catalog_service()
    await service.create_model(_model_payload())

    record = await service.update_health(
        "deepseek-v3",
        status=ModelHealthStatus.FAILED,
        error_message="provider rejected sk-live-1234abcd and api-key=tp-cvt-secret-token",
    )

    assert record is not None
    assert repository.rows["deepseek-v3"].health_status == ModelHealthStatus.FAILED
    assert repository.rows["deepseek-v3"].last_test_error == "provider rejected sk-****abcd and [redacted]"
