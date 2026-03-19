"""Tests for execution base interfaces."""

import pytest

from src.execution.base import ExecutionProvider, ExecutionService


class TestExecutionServiceInterface:
    """Tests for ExecutionService abstract interface."""

    def test_cannot_instantiate_abstract_class(self):
        """Should not be able to instantiate abstract class."""
        with pytest.raises(TypeError):
            ExecutionService()

    def test_subclass_must_implement_execute(self):
        """Subclass must implement execute method."""
        class IncompleteService(ExecutionService):
            pass

        with pytest.raises(TypeError):
            IncompleteService()


class TestExecutionProviderInterface:
    """Tests for ExecutionProvider abstract interface."""

    def test_cannot_instantiate_abstract_class(self):
        """Should not be able to instantiate abstract class."""
        with pytest.raises(TypeError):
            ExecutionProvider()

    def test_subclass_must_implement_required_methods(self):
        """Subclass must implement all required methods."""
        class IncompleteProvider(ExecutionProvider):
            @property
            def execution_type(self) -> str:
                return "test"

        with pytest.raises(TypeError):
            IncompleteProvider()
