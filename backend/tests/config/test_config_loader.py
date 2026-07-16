"""Tests for unified config.yaml loader."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from src.config.config_loader import (
    AppConfig,
    load_config,
)


class TestConfigLoader:
    def _write_config(self, tmp: Path, data: dict) -> Path:
        p = tmp / "config.yaml"
        p.write_text(yaml.dump(data))
        return p

    def test_load_minimal_config(self, tmp_path):
        cfg_path = self._write_config(tmp_path, {
            "memory": {"enabled": True},
        })
        config = load_config(str(cfg_path))
        assert isinstance(config, AppConfig)
        assert config.memory.enabled is True

    def test_wenjin_config_path_selects_config(self, tmp_path, monkeypatch):
        cfg_path = self._write_config(tmp_path, {"memory": {"enabled": True}})
        monkeypatch.setenv("WENJIN_CONFIG_PATH", str(cfg_path))

        config = load_config()

        assert config.memory.enabled is True

    def test_fixed_subagent_config_is_rejected(self, tmp_path):
        cfg_path = self._write_config(tmp_path, {
            "subagents": {"enabled": True, "max_concurrent": 4, "types": {
                "scout": {"description": "Literature search", "allowed_tools": ["research.search_web"], "max_turns": 10},
            }},
        })
        with pytest.raises(ValidationError):
            load_config(str(cfg_path))

    def test_memory_config(self, tmp_path):
        cfg_path = self._write_config(tmp_path, {
            "memory": {"enabled": True, "injection_enabled": True, "debounce_seconds": 30},
        })
        config = load_config(str(cfg_path))
        assert config.memory.enabled is True
        assert config.memory.debounce_seconds == 30

    def test_defaults(self, tmp_path):
        cfg_path = self._write_config(tmp_path, {})
        config = load_config(str(cfg_path))
        assert config.memory.enabled is False
        assert not hasattr(config, "sandbox")
        assert config.billing.thread.enabled is True
        assert config.billing.thread.free_tokens == 100000
        assert config.billing.thread.tokens_per_credit == 10000
        assert config.billing.thread.max_overdraft_credits == 100
        assert config.billing.mission.enabled is True
        assert config.billing.mission.free_tokens == 0
        assert config.billing.mission.tokens_per_credit == 10000
        assert config.billing.mission.max_overdraft_credits == 100
        assert config.billing.sandbox.enabled is True
        assert config.billing.sandbox.run_python_credits == 1
        assert config.billing.sandbox.max_overdraft_credits == 100

    def test_load_billing_config(self, tmp_path):
        cfg_path = self._write_config(tmp_path, {
            "billing": {
                "thread": {
                    "enabled": False,
                    "free_tokens": 2048,
                    "tokens_per_credit": 512,
                    "max_overdraft_credits": 10,
                },
                "mission": {
                    "enabled": True,
                    "free_tokens": 128,
                    "tokens_per_credit": 256,
                    "max_overdraft_credits": 20,
                },
                "sandbox": {
                    "enabled": True,
                    "run_python_credits": 3,
                    "max_overdraft_credits": 30,
                }
            },
        })
        config = load_config(str(cfg_path))
        assert config.billing.thread.enabled is False
        assert config.billing.thread.free_tokens == 2048
        assert config.billing.thread.tokens_per_credit == 512
        assert config.billing.thread.max_overdraft_credits == 10
        assert config.billing.mission.enabled is True
        assert config.billing.mission.free_tokens == 128
        assert config.billing.mission.tokens_per_credit == 256
        assert config.billing.mission.max_overdraft_credits == 20
        assert config.billing.sandbox.enabled is True
        assert config.billing.sandbox.run_python_credits == 3
        assert config.billing.sandbox.max_overdraft_credits == 30
