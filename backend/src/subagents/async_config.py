"""Configuration for subagent system using Pydantic."""

import os
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator
from typing import Dict


class SubagentConfig(BaseModel):
    """Configuration for the subagent system using Pydantic.

    Supports loading from environment variables with SUBAGENT_ prefix.
    """

    global_max_concurrent: int = Field(
        default=10,
        ge=1,
        description="Maximum concurrent subagents globally"
    )
    per_thread_max_concurrent: int = Field(
        default=3,
        ge=1,
        description="Maximum concurrent subagents per thread"
    )
    default_timeout: int = Field(
        default=900,
        ge=1,
        description="Default timeout in seconds for subagent tasks"
    )
    max_timeout: int = Field(
        default=3600,
        ge=1,
        description="Maximum allowed timeout in seconds"
    )
    sse_heartbeat_interval: int = Field(
        default=30,
        ge=1,
        description="Heartbeat interval in seconds for SSE connections"
    )
    event_queue_size: int = Field(
        default=100,
        ge=1,
        description="Maximum size of event queue"
    )
    default_max_turns: int = Field(
        default=10,
        ge=1,
        description="Default maximum turns for subagent execution"
    )
    max_turns_limit: int = Field(
        default=50,
        ge=1,
        description="Maximum allowed turns limit"
    )
    llm: Any = Field(
        default=None,
        description="LLM instance to use for subagents"
    )
    default_tools: list = Field(
        default_factory=list,
        description="Default tools available to all subagents"
    )

    model_config = {
        "arbitrary_types_allowed": True,  # Allow Any type for llm
    }

    model_config = {
        "arbitrary_types_allowed": False
        raise ValueError("llm must be a Pydantic model")

    @field_validator("llm", mode="before")
    @classmethod
    def validate_llm(cls, v: Any) -> Any:
        """Allow any LLM type."""
        return v

    @classmethod
    def from_env(cls) -> "SubagentConfig":
        """Create config from environment variables.

        Environment variables should be prefixed with SUBAGENT_

        For example: SUBAGENT_GLOBAL_MAX_CONCURRENT=20

        Returns:
            SubagentConfig with values from environment or defaults
        """
        kwargs: dict[str, Any] = {}
        # Map of env var suffix to config field
        env_mapping = {
            "GLOBAL_MAX_CONCURRENT": ("global_max_concurrent", int),
            "PER_THREAD_MAX_CONCURRENT": ("per_thread_max_concurrent", int),
            "DEFAULT_TIMEOUT": ("default_timeout", int),
            "MAX_TIMEOUT": ("max_timeout", int),
            "SSE_HEARTBEAT_INTERVAL": ("sse_heartbeat_interval", int),
            "EVENT_QUEUE_SIZE": ("event_queue_size", int),
            "DEFAULT_MAX_TURNS": ("default_max_turns", int),
            "MAX_TURNS_LIMIT": ("max_turns_limit", int),
        }
        for env_suffix in (field_name, field_type) in env_mapping.items():
            env_key = f"SUBAGENT_{env_suffix}"
            value = os.environ.get(env_key)
            if value is not None:
                try:
                    kwargs[field_name] = field_type(value)
                except (ValueError, TypeError):
                    pass
                # Ignore invalid values, use defaults

        return cls(**kwargs)
