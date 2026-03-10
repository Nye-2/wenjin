"""Sandbox provider abstract base class."""

from abc import ABC, abstractmethod
from typing import Optional

from src.sandbox.base import Sandbox


class SandboxProvider(ABC):
    """Abstract base class for sandbox providers.

    A provider manages the lifecycle of sandbox instances:
    - Acquire: Create or get a sandbox for a thread
    - Get: Retrieve an existing sandbox
    - Release: Release sandbox resources
    """

    @abstractmethod
    async def acquire(self, thread_id: str) -> Sandbox:
        """Acquire a sandbox for a thread.

        Args:
            thread_id: Thread identifier.

        Returns:
            Sandbox instance for the thread.
        """
        pass

    @abstractmethod
    def get(self, sandbox_id: str) -> Optional[Sandbox]:
        """Get existing sandbox by ID.

        Args:
            sandbox_id: Sandbox identifier.

        Returns:
            Sandbox instance or None if not found.
        """
        pass

    @abstractmethod
    async def release(self, sandbox: Sandbox) -> None:
        """Release sandbox resources.

        Args:
            sandbox: Sandbox instance to release.
        """
        pass
