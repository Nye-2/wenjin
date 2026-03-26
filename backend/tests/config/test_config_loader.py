"""Tests for unified config.yaml loader."""

from pathlib import Path

import yaml

from src.config.config_loader import (
    AppConfig,
    ModelConfig,
    load_config,
)


class TestConfigLoader:
    def _write_config(self, tmp: Path, data: dict) -> Path:
        p = tmp / "config.yaml"
        p.write_text(yaml.dump(data))
        return p

    def test_load_minimal_config(self, tmp_path):
        cfg_path = self._write_config(tmp_path, {
            "models": [{"name": "test", "use": "langchain_openai:ChatOpenAI", "model": "gpt-4o", "api_key": "sk-test"}],
        })
        config = load_config(str(cfg_path))
        assert isinstance(config, AppConfig)
        assert len(config.models) == 1
        assert config.models[0].name == "test"

    def test_env_var_resolution(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TEST_API_KEY", "resolved-key")
        cfg_path = self._write_config(tmp_path, {
            "models": [{"name": "test", "use": "langchain_openai:ChatOpenAI", "model": "gpt-4o", "api_key": "$TEST_API_KEY"}],
        })
        config = load_config(str(cfg_path))
        assert config.models[0].api_key == "resolved-key"

    def test_subagent_types(self, tmp_path):
        cfg_path = self._write_config(tmp_path, {
            "models": [],
            "subagents": {"enabled": True, "max_concurrent": 4, "types": {
                "scout": {"description": "Literature search", "allowed_tools": ["web_search"], "max_turns": 10},
            }},
        })
        config = load_config(str(cfg_path))
        assert config.subagents.enabled is True
        assert "scout" in config.subagents.types
        assert config.subagents.types["scout"].max_turns == 10

    def test_memory_config(self, tmp_path):
        cfg_path = self._write_config(tmp_path, {
            "models": [],
            "memory": {"enabled": True, "injection_enabled": True, "debounce_seconds": 30},
        })
        config = load_config(str(cfg_path))
        assert config.memory.enabled is True
        assert config.memory.debounce_seconds == 30

    def test_defaults(self, tmp_path):
        cfg_path = self._write_config(tmp_path, {"models": []})
        config = load_config(str(cfg_path))
        assert config.subagents.enabled is False
        assert config.memory.enabled is False
        assert config.sandbox is None
        assert config.billing.chat.enabled is True
        assert config.billing.chat.free_tokens == 100000
        assert config.billing.chat.tokens_per_credit == 10000

    def test_load_chat_billing_config(self, tmp_path):
        cfg_path = self._write_config(tmp_path, {
            "models": [],
            "billing": {
                "chat": {
                    "enabled": False,
                    "free_tokens": 2048,
                    "tokens_per_credit": 512,
                }
            },
        })
        config = load_config(str(cfg_path))
        assert config.billing.chat.enabled is False
        assert config.billing.chat.free_tokens == 2048
        assert config.billing.chat.tokens_per_credit == 512


class TestModelConfig:
    def test_model_config_fields(self):
        mc = ModelConfig(name="test", use="langchain_openai:ChatOpenAI", model="gpt-4o", api_key="sk-test")
        assert mc.name == "test"
        assert mc.supports_thinking is False  # default
        assert mc.supports_vision is False    # default
        assert mc.tags == []                  # default
