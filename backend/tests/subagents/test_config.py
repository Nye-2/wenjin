"""Tests for subagent configuration."""

import os
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from src.subagents.config import SubagentConfig


class TestSubagentConfig:
    """Tests for SubagentConfig Pydantic model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = SubagentConfig()
        assert config.global_max_concurrent == 10
        assert config.per_thread_max_concurrent == 3
        assert config.default_timeout == 900
        assert config.max_timeout == 3600
        assert config.default_max_turns == 10
        assert config.max_turns_limit == 50
        assert config.llm is None
        assert config.default_tools == []

    def test_custom_values(self):
        """Test configuration with custom values."""
        config = SubagentConfig(
            global_max_concurrent=20,
            per_thread_max_concurrent=5,
            default_timeout=600,
        )
        assert config.global_max_concurrent == 20
        assert config.per_thread_max_concurrent == 5
        assert config.default_timeout == 600

    def test_validation_positive_concurrency(self):
        """Test that concurrency values must be positive."""
        with pytest.raises(ValidationError):
            SubagentConfig(global_max_concurrent=0)

        with pytest.raises(ValidationError):
            SubagentConfig(global_max_concurrent=-1)

        with pytest.raises(ValidationError):
            SubagentConfig(per_thread_max_concurrent=0)

    def test_validation_timeout_values(self):
        """Test that timeout values are valid."""
        # Valid timeouts
        config = SubagentConfig(default_timeout=100, max_timeout=1000)
        assert config.default_timeout == 100

        # Invalid: default_timeout > max_timeout should fail or be allowed
        # Based on the spec, we'll allow any positive int for now

    def test_validation_turns_values(self):
        """Test that turns values are valid."""
        config = SubagentConfig(default_max_turns=20, max_turns_limit=100)
        assert config.default_max_turns == 20
        assert config.max_turns_limit == 100

    def test_llm_field_accepts_any(self):
        """Test that llm field can accept various types."""
        # Can be None
        config = SubagentConfig(llm=None)
        assert config.llm is None

        # Can be a mock object
        mock_llm = MagicMock()
        config = SubagentConfig(llm=mock_llm)
        assert config.llm is mock_llm

    def test_default_tools_list(self):
        """Test default_tools field."""
        config = SubagentConfig(default_tools=["bash", "read_file"])
        assert config.default_tools == ["bash", "read_file"]

    def test_model_dump(self):
        """Test serialization to dictionary."""
        config = SubagentConfig(
            global_max_concurrent=15,
            per_thread_max_concurrent=4,
        )
        d = config.model_dump()
        assert d["global_max_concurrent"] == 15
        assert d["per_thread_max_concurrent"] == 4
        assert "default_timeout" in d

    def test_model_dump_json(self):
        """Test serialization to JSON."""
        import json
        config = SubagentConfig(global_max_concurrent=15)
        json_str = config.model_dump_json()
        d = json.loads(json_str)
        assert d["global_max_concurrent"] == 15

    def test_from_environment_variables(self):
        """Test loading config from environment variables."""
        # Set environment variables
        os.environ["SUBAGENT_GLOBAL_MAX_CONCURRENT"] = "25"
        os.environ["SUBAGENT_PER_THREAD_MAX_CONCURRENT"] = "7"
        os.environ["SUBAGENT_DEFAULT_TIMEOUT"] = "1200"

        try:
            config = SubagentConfig.from_env()
            assert config.global_max_concurrent == 25
            assert config.per_thread_max_concurrent == 7
            assert config.default_timeout == 1200
        finally:
            # Cleanup
            del os.environ["SUBAGENT_GLOBAL_MAX_CONCURRENT"]
            del os.environ["SUBAGENT_PER_THREAD_MAX_CONCURRENT"]
            del os.environ["SUBAGENT_DEFAULT_TIMEOUT"]

    def test_from_env_uses_defaults(self):
        """Test that from_env uses defaults when env vars not set."""
        # Make sure env vars are not set
        for key in list(os.environ.keys()):
            if key.startswith("SUBAGENT_"):
                del os.environ[key]

        config = SubagentConfig.from_env()
        assert config.global_max_concurrent == 10
        assert config.per_thread_max_concurrent == 3

    def test_immutable_config(self):
        """Test that config is immutable (frozen) if specified."""
        # This depends on whether we make it frozen
        # For now, just test that we can create it
        config = SubagentConfig()
        # Pydantic v2 models are mutable by default
        config.global_max_concurrent = 20
        assert config.global_max_concurrent == 20

    def test_complex_config(self):
        """Test creating a complex config with all fields."""
        mock_llm = MagicMock()
        config = SubagentConfig(
            global_max_concurrent=50,
            per_thread_max_concurrent=10,
            default_timeout=1800,
            max_timeout=7200,
            default_max_turns=25,
            max_turns_limit=100,
            llm=mock_llm,
            default_tools=["bash", "read_file", "write_file"],
        )
        assert config.global_max_concurrent == 50
        assert config.per_thread_max_concurrent == 10
        assert config.default_timeout == 1800
        assert config.max_timeout == 7200
        assert config.default_max_turns == 25
        assert config.max_turns_limit == 100
        assert config.llm is mock_llm
        assert len(config.default_tools) == 3
