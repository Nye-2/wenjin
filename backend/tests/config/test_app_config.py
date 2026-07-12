"""Tests for environment-backed application settings."""

import pytest

from src.config.app_config import AppConfig, JWTSettings


def test_app_config_accepts_environment_names_in_debug_env(monkeypatch) -> None:
    monkeypatch.setenv("DEBUG", "release")
    assert AppConfig().debug is False

    monkeypatch.setenv("DEBUG", "prod")
    assert AppConfig().debug is False

    monkeypatch.setenv("DEBUG", "dev")
    assert AppConfig().debug is True


def test_app_config_preserves_standard_boolean_debug_values(monkeypatch) -> None:
    monkeypatch.setenv("DEBUG", "true")
    assert AppConfig().debug is True

    monkeypatch.setenv("DEBUG", "false")
    assert AppConfig().debug is False


def test_e2e_test_hooks_are_opt_in_even_in_development(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("E2E_TEST_HOOKS_ENABLED", raising=False)

    assert AppConfig().e2e_test_hooks_enabled is False

    monkeypatch.setenv("E2E_TEST_HOOKS_ENABLED", "true")
    assert AppConfig().e2e_test_hooks_enabled is True


def test_production_rejects_placeholder_jwt_secret(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        JWTSettings(secret_key="change-me-in-production")


def test_production_accepts_strong_jwt_secret(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")

    settings = JWTSettings(secret_key="a-secure-production-signing-secret-that-is-long-enough")

    assert settings.secret_key.startswith("a-secure")
