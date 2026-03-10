"""Tests for TodoListMiddleware."""

import pytest

from src.agents.middlewares.todo_list import TodoListMiddleware
from src.agents.thread_state import ThreadState


@pytest.fixture
def middleware() -> TodoListMiddleware:
    """Create a TodoListMiddleware instance for testing."""
    return TodoListMiddleware()


@pytest.fixture
def initial_state() -> ThreadState:
    """Create an initial state for testing."""
    return {
        "messages": [],
        "todos": None,
    }


@pytest.fixture
def plan_mode_config() -> dict:
    """Create a config with plan_mode enabled."""
    return {"configurable": {"is_plan_mode": True}}


@pytest.fixture
def normal_config() -> dict:
    """Create a config with plan_mode disabled."""
    return {"configurable": {"is_plan_mode": False}}


class TestTodoListMiddleware:
    """Test cases for TodoListMiddleware."""

    @pytest.mark.asyncio
    async def test_before_model_injects_todos_in_plan_mode(
        self,
        middleware: TodoListMiddleware,
        initial_state: ThreadState,
        plan_mode_config: dict,
    ) -> None:
        """Verify that before_model injects todos when plan_mode is enabled."""
        # Arrange - set up some todos
        todos = [
            {"id": "1", "task": "First task", "completed": False},
            {"id": "2", "task": "Second task", "completed": True},
        ]
        middleware.update_todos(todos)

        # Act
        result = await middleware.before_model(initial_state, plan_mode_config)

        # Assert
        assert result is not None
        assert "todos" in result
        assert result["todos"] == todos

    @pytest.mark.asyncio
    async def test_before_model_skips_in_normal_mode(
        self,
        middleware: TodoListMiddleware,
        initial_state: ThreadState,
        normal_config: dict,
    ) -> None:
        """Verify that before_model skips injection when plan_mode is disabled."""
        # Arrange - set up some todos
        todos = [{"id": "1", "task": "Test task", "completed": False}]
        middleware.update_todos(todos)

        # Act
        result = await middleware.before_model(initial_state, normal_config)

        # Assert
        assert result == {}

    @pytest.mark.asyncio
    async def test_after_model_returns_empty(
        self,
        middleware: TodoListMiddleware,
        initial_state: ThreadState,
        plan_mode_config: dict,
    ) -> None:
        """Verify that after_model returns empty dict."""
        # Act
        result = await middleware.after_model(initial_state, plan_mode_config)

        # Assert
        assert result == {}

    def test_update_todos(self, middleware: TodoListMiddleware) -> None:
        """Verify that update_todos correctly stores the todo list."""
        # Arrange
        todos = [
            {"id": "1", "task": "Task 1", "completed": False},
            {"id": "2", "task": "Task 2", "completed": True},
            {"id": "3", "task": "Task 3", "completed": False},
        ]

        # Act
        middleware.update_todos(todos)

        # Assert
        assert middleware.todos == todos

    def test_get_next_todo(self, middleware: TodoListMiddleware) -> None:
        """Verify that get_next_todo returns the first incomplete todo."""
        # Arrange
        todos = [
            {"id": "1", "task": "Completed task", "completed": True},
            {"id": "2", "task": "Next pending task", "completed": False},
            {"id": "3", "task": "Another pending task", "completed": False},
        ]
        middleware.update_todos(todos)

        # Act
        next_todo = middleware.get_next_todo()

        # Assert
        assert next_todo is not None
        assert next_todo["id"] == "2"
        assert next_todo["task"] == "Next pending task"
        assert next_todo["completed"] is False

    def test_get_next_todo_all_completed(self, middleware: TodoListMiddleware) -> None:
        """Verify that get_next_todo returns None when all todos are completed."""
        # Arrange
        todos = [
            {"id": "1", "task": "Task 1", "completed": True},
            {"id": "2", "task": "Task 2", "completed": True},
        ]
        middleware.update_todos(todos)

        # Act
        next_todo = middleware.get_next_todo()

        # Assert
        assert next_todo is None

    def test_get_next_todo_empty_list(self, middleware: TodoListMiddleware) -> None:
        """Verify that get_next_todo returns None when todo list is empty."""
        # Arrange
        middleware.update_todos([])

        # Act
        next_todo = middleware.get_next_todo()

        # Assert
        assert next_todo is None
