"""Guardrail middleware for safety and policy enforcement.

Validates user inputs and model outputs against safety policies,
preventing harmful, illegal, or policy-violating content from
entering the system.
"""

import logging
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from src.agents.thread_state import ThreadState

from .base import Middleware

logger = logging.getLogger(__name__)


class GuardrailMiddleware(Middleware):
    """Safety guardrail middleware.

    Checks user messages against content safety policies before they reach
    the model. Can be configured with custom policy checks.
    """

    # Simple heuristic patterns for initial implementation
    BLOCKED_PATTERNS = [
        "ignore previous instructions",
        "disregard all prior",
        "forget your training",
        "ignore your system prompt",
        "jailbreak",
        "DAN mode",
    ]

    def __init__(self, *, blocked_patterns: list[str] | None = None) -> None:
        self.blocked_patterns = blocked_patterns or self.BLOCKED_PATTERNS

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Check user messages against safety policies.

        Args:
            state: Current thread state
            config: Runtime configuration

        Returns:
            Empty dict if safe, or raises GuardrailViolation
        """
        messages = getattr(state, "messages", [])
        for msg in messages:
            if isinstance(msg, HumanMessage):
                content = str(msg.content or "").lower()
                for pattern in self.blocked_patterns:
                    if pattern.lower() in content:
                        logger.warning(
                            "Guardrail triggered: pattern='%s' thread=%s",
                            pattern,
                            getattr(state, "thread_id", "unknown"),
                        )
                        raise GuardrailViolation(
                            f"Content violates safety policy: blocked pattern detected."
                        )
        return {}

    async def after_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Optional: check model output for policy violations."""
        return {}


class GuardrailViolation(RuntimeError):
    """Raised when content violates a safety guardrail policy."""
