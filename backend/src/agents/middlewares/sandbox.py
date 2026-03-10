"""SandboxMiddleware - manages SandboxProvider lifecycle.

Acquires sandbox from provider in before_model and stores sandbox_id in state.
If sandbox already exists in state, skips acquisition.
"""

from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState
from src.sandbox import SandboxProvider


class SandboxMiddleware(Middleware):
    """Middleware that acquires sandbox from provider.

    Lifecycle Management:
    - Acquires sandbox in before_model if not already present
    - Stores sandbox_id in state.sandbox
    - Sandbox is reused across multiple turns within the same thread
    - Cleanup happens at application shutdown via SandboxProvider
    """

    def __init__(self, provider: SandboxProvider):
        """Initialize sandbox middleware.

        Args:
            provider: SandboxProvider instance for acquiring sandboxes.
        """
        self._provider = provider

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Acquire sandbox if not already present.

        Args:
            state: Current thread state.
            config: Runtime configuration with thread_id.

        Returns:
            Dict with sandbox info, or empty dict if sandbox exists.
        """
        # Skip if sandbox already exists
        existing = state.get("sandbox")
        if existing and existing.get("sandbox_id"):
            return {}

        # Get thread_id from config
        thread_id = config.get("configurable", {}).get("thread_id", "default")

        # Acquire sandbox from provider
        sandbox = await self._provider.acquire(thread_id)

        return {
            "sandbox": {
                "sandbox_id": sandbox.sandbox_id,
            }
        }

    async def after_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """No-op after model.

        Args:
            state: Current thread state.
            config: Runtime configuration.

        Returns:
            Empty dict (no state changes).
        """
        return {}
