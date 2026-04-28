"""Shared runtime/bootstrap helpers for the global subagent manager."""

from __future__ import annotations

import logging

from src.subagents.config import SubagentConfig
from src.subagents.manager import GlobalSubagentManager

logger = logging.getLogger(__name__)


def build_default_manager_config() -> SubagentConfig:
    """Build the lazily initialized manager configuration."""
    config = SubagentConfig.from_env()

    try:
        from src.config import get_default_model_id
        from src.models.factory import create_chat_model

        config.llm = create_chat_model(get_default_model_id())
    except Exception as exc:
        logger.warning("Failed to initialize default subagent model: %s", exc)
        config.llm = None

    try:
        from src.agents.lead_agent.agent import get_available_tools

        config.default_tools = get_available_tools(
            include_execution=True,
        )
    except Exception as exc:
        logger.warning("Failed to initialize default subagent tools: %s", exc)
        config.default_tools = []

    return config


def get_manager() -> GlobalSubagentManager:
    """Get or initialize the process-wide subagent manager."""
    try:
        return GlobalSubagentManager.get_instance()
    except RuntimeError:
        try:
            return GlobalSubagentManager.initialize(build_default_manager_config())
        except RuntimeError:
            return GlobalSubagentManager.get_instance()
