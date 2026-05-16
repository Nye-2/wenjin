"""Tests for CreditGrantRuleService — focus on config validation and rule logic."""

import pytest

from src.database import CreditGrantRuleType
from src.services.credit_grant_rule_service import (
    CreditGrantRuleService,
    _validated_config,
    RegistrationConfig,
    ReferralConfig,
    PeriodicConfig,
)


# ============ Config validation tests (sync, no DB needed) ============


def test_registration_config_accepts_empty():
    config = _validated_config(CreditGrantRuleType.REGISTRATION_BONUS, {})
    assert config == {}


def test_registration_config_rejects_extra_fields():
    with pytest.raises(ValueError, match="config invalid"):
        _validated_config(CreditGrantRuleType.REGISTRATION_BONUS, {"unexpected": True})


def test_referral_config_defaults_trigger():
    config = _validated_config(CreditGrantRuleType.REFERRAL_REFERRER, {})
    assert config["trigger"] == "on_first_task"


def test_referral_config_accepts_on_signup():
    config = _validated_config(CreditGrantRuleType.REFERRAL_REFERRER, {"trigger": "on_signup"})
    assert config["trigger"] == "on_signup"


def test_periodic_config_requires_cron():
    with pytest.raises(ValueError, match="cron"):
        _validated_config(CreditGrantRuleType.PERIODIC, {})


def test_periodic_config_rejects_invalid_cron():
    with pytest.raises(ValueError, match="cron"):
        _validated_config(CreditGrantRuleType.PERIODIC, {"cron": "not a cron"})


def test_periodic_config_accepts_valid_cron():
    config = _validated_config(CreditGrantRuleType.PERIODIC, {"cron": "0 0 * * 1"})
    assert config["cron"] == "0 0 * * 1"


def test_periodic_config_with_target_filter():
    config = _validated_config(CreditGrantRuleType.PERIODIC, {
        "cron": "0 0 * * *",
        "target_filter": {"active_within_days": 30, "role": "user"},
    })
    assert config["target_filter"]["active_within_days"] == 30
    assert config["target_filter"]["role"] == "user"


def test_referred_config_forces_on_signup():
    config = _validated_config(CreditGrantRuleType.REFERRAL_REFERRED, {})
    assert config["trigger"] == "on_signup"


def test_referred_config_rejects_non_signup():
    with pytest.raises(ValueError, match="config invalid"):
        _validated_config(CreditGrantRuleType.REFERRAL_REFERRED, {"trigger": "on_first_task"})
