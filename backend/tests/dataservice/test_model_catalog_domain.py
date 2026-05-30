"""Tests for DataService model catalog domain behavior."""

from __future__ import annotations

import base64

import pytest

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


def _test_key() -> str:
    return "base64:" + base64.urlsafe_b64encode(b"0" * 32).decode("ascii")


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
