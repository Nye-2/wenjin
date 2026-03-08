"""Comprehensive tests for the skill execution framework.

This module tests:
- SkillInput and SkillOutput Pydantic models
- BaseSkill abstract class
- SkillExecutor registration and execution
- Error handling and validation
"""

import pytest

from src.agents.thread_state import AcademicArtifact, ThreadState
from src.skills.base import BaseSkill, SkillInput, SkillOutput
from src.skills.executor import (
    SkillExecutionError,
    SkillExecutor,
    SkillNotFoundError,
    SkillValidationError,
)

# ============================================================================
# Concrete skill implementations for testing
# ============================================================================


class MockSkill(BaseSkill):
    """A simple mock skill for testing."""

    name = "mock-skill"
    description = "A mock skill for testing"
    version = "1.0.0"

    def execute(self, input: SkillInput, state: ThreadState) -> SkillOutput:
        """Execute the mock skill."""
        return SkillOutput(
            success=True,
            content=f"Processed: {input.user_query}",
            metadata={"workspace_id": input.workspace_id},
        )


class SkillWithArtifacts(BaseSkill):
    """A skill that produces artifacts."""

    name = "artifact-skill"
    description = "A skill that produces artifacts"
    version = "2.0.0"

    def execute(self, input: SkillInput, state: ThreadState) -> SkillOutput:
        """Execute and produce artifacts."""
        artifact = AcademicArtifact(
            id="artifact-1",
            workspace_id=input.workspace_id,
            type="research_idea",
            content={"title": "Test Idea", "query": input.user_query},
            created_by_skill=self.name,
        )
        return SkillOutput(
            success=True,
            content="Created research idea",
            artifacts=[artifact],
        )


class SkillWithValidation(BaseSkill):
    """A skill with custom validation."""

    name = "validated-skill"
    description = "A skill with custom validation"
    version = "1.0.0"

    def validate_input(self, input: SkillInput) -> str | None:
        """Custom validation requiring a special context key."""
        if "required_key" not in input.context:
            return "context must contain 'required_key'"
        return None

    def execute(self, input: SkillInput, state: ThreadState) -> SkillOutput:
        """Execute the skill."""
        return SkillOutput(success=True, content="Validated and processed")


class FailingSkill(BaseSkill):
    """A skill that always fails."""

    name = "failing-skill"
    description = "A skill that always fails"
    version = "1.0.0"

    def execute(self, input: SkillInput, state: ThreadState) -> SkillOutput:
        """Execute and fail."""
        return SkillOutput(
            success=False,
            content="",
            error_message="This skill always fails",
        )


class ExceptionSkill(BaseSkill):
    """A skill that raises an exception."""

    name = "exception-skill"
    description = "A skill that raises an exception"
    version = "1.0.0"

    def execute(self, input: SkillInput, state: ThreadState) -> SkillOutput:
        """Execute and raise."""
        raise ValueError("Something went wrong!")


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def executor() -> SkillExecutor:
    """Create a fresh SkillExecutor for each test."""
    return SkillExecutor()


@pytest.fixture
def skill_input() -> SkillInput:
    """Create a default SkillInput for testing."""
    return SkillInput(
        workspace_id="test-workspace",
        user_query="Test query",
        context={"key": "value"},
    )


@pytest.fixture
def thread_state() -> ThreadState:
    """Create a default ThreadState for testing."""
    return ThreadState(
        messages=[],
        workspace_id="test-workspace",
    )


# ============================================================================
# SkillInput Tests
# ============================================================================


class TestSkillInput:
    """Tests for SkillInput model."""

    def test_skill_input_creation_with_required_fields(self):
        """Test creating SkillInput with required fields."""
        input_data = SkillInput(
            workspace_id="ws-123",
            user_query="What is machine learning?",
        )
        assert input_data.workspace_id == "ws-123"
        assert input_data.user_query == "What is machine learning?"
        assert input_data.context == {}

    def test_skill_input_with_context(self):
        """Test creating SkillInput with context."""
        input_data = SkillInput(
            workspace_id="ws-456",
            user_query="Research topic",
            context={"discipline": "computer_science", "papers": ["p1", "p2"]},
        )
        assert input_data.context["discipline"] == "computer_science"
        assert len(input_data.context["papers"]) == 2

    def test_skill_input_context_default_empty_dict(self):
        """Test that context defaults to empty dict."""
        input_data = SkillInput(workspace_id="ws", user_query="query")
        assert input_data.context == {}
        assert isinstance(input_data.context, dict)

    def test_skill_input_validation_missing_workspace(self):
        """Test that workspace_id is required."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            SkillInput(user_query="query")

    def test_skill_input_validation_missing_query(self):
        """Test that user_query is required."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            SkillInput(workspace_id="ws")


# ============================================================================
# SkillOutput Tests
# ============================================================================


class TestSkillOutput:
    """Tests for SkillOutput model."""

    def test_skill_output_defaults(self):
        """Test SkillOutput default values."""
        output = SkillOutput()
        assert output.success is True
        assert output.content == ""
        assert output.artifacts == []
        assert output.metadata == {}
        assert output.error_message is None

    def test_skill_output_with_content(self):
        """Test SkillOutput with content."""
        output = SkillOutput(success=True, content="Result content")
        assert output.content == "Result content"

    def test_skill_output_with_artifacts(self):
        """Test SkillOutput with artifacts."""
        artifact = AcademicArtifact(
            id="a1",
            workspace_id="ws",
            type="idea",
            content={"title": "Test"},
        )
        output = SkillOutput(artifacts=[artifact])
        assert len(output.artifacts) == 1
        assert output.artifacts[0].id == "a1"

    def test_skill_output_with_error(self):
        """Test SkillOutput with error."""
        output = SkillOutput(
            success=False,
            error_message="Something went wrong",
        )
        assert output.success is False
        assert output.error_message == "Something went wrong"

    def test_skill_output_with_metadata(self):
        """Test SkillOutput with metadata."""
        output = SkillOutput(
            metadata={
                "tokens_used": 1500,
                "model": "gpt-4",
            }
        )
        assert output.metadata["tokens_used"] == 1500


# ============================================================================
# BaseSkill Tests
# ============================================================================


class TestBaseSkill:
    """Tests for BaseSkill class."""

    def test_skill_repr(self):
        """Test skill string representation."""
        skill = MockSkill()
        repr_str = repr(skill)
        assert "MockSkill" in repr_str
        assert "mock-skill" in repr_str
        assert "1.0.0" in repr_str

    def test_skill_default_validation_valid_input(self, skill_input):
        """Test default validation with valid input."""
        skill = MockSkill()
        result = skill.validate_input(skill_input)
        assert result is None

    def test_skill_default_validation_missing_workspace(self):
        """Test default validation with missing workspace_id."""
        skill = MockSkill()
        input_data = SkillInput(workspace_id="", user_query="query")
        result = skill.validate_input(input_data)
        assert result == "workspace_id is required"

    def test_skill_default_validation_empty_query(self):
        """Test default validation with empty query."""
        skill = MockSkill()
        input_data = SkillInput(workspace_id="ws", user_query="")
        result = skill.validate_input(input_data)
        assert result == "user_query cannot be empty"

    def test_skill_default_validation_whitespace_query(self):
        """Test default validation with whitespace-only query."""
        skill = MockSkill()
        input_data = SkillInput(workspace_id="ws", user_query="   ")
        result = skill.validate_input(input_data)
        assert result == "user_query cannot be empty"

    def test_skill_custom_validation(self):
        """Test custom validation in skill."""
        skill = SkillWithValidation()

        # Without required key
        input_data = SkillInput(
            workspace_id="ws",
            user_query="query",
            context={},
        )
        result = skill.validate_input(input_data)
        assert result == "context must contain 'required_key'"

        # With required key
        input_data.context["required_key"] = "value"
        result = skill.validate_input(input_data)
        assert result is None


# ============================================================================
# SkillExecutor Registration Tests
# ============================================================================


class TestSkillExecutorRegistration:
    """Tests for skill registration."""

    def test_register_skill(self, executor: SkillExecutor):
        """Test registering a skill."""
        skill = MockSkill()
        executor.register_skill(skill)
        assert executor.has_skill("mock-skill")

    def test_register_multiple_skills(self, executor: SkillExecutor):
        """Test registering multiple skills."""
        executor.register_skill(MockSkill())
        executor.register_skill(SkillWithArtifacts())
        assert len(executor) == 2
        assert "mock-skill" in executor
        assert "artifact-skill" in executor

    def test_register_skill_replaces_existing(self, executor: SkillExecutor):
        """Test that registering overwrites existing skill."""

        class SkillV1(BaseSkill):
            name = "test-skill"
            description = "Version 1"
            version = "1.0.0"

            def execute(self, input, state):
                return SkillOutput(content="v1")

        class SkillV2(BaseSkill):
            name = "test-skill"
            description = "Version 2"
            version = "2.0.0"

            def execute(self, input, state):
                return SkillOutput(content="v2")

        executor.register_skill(SkillV1())
        executor.register_skill(SkillV2())

        skill = executor.get_skill("test-skill")
        assert skill is not None
        assert skill.version == "2.0.0"

    def test_register_non_skill_raises(self, executor: SkillExecutor):
        """Test that registering non-BaseSkill raises TypeError."""
        with pytest.raises(TypeError) as exc_info:
            executor.register_skill("not a skill")  # type: ignore
        assert "Expected BaseSkill instance" in str(exc_info.value)

    def test_unregister_skill(self, executor: SkillExecutor):
        """Test unregistering a skill."""
        executor.register_skill(MockSkill())
        assert executor.unregister_skill("mock-skill") is True
        assert not executor.has_skill("mock-skill")

    def test_unregister_nonexistent_skill(self, executor: SkillExecutor):
        """Test unregistering a skill that doesn't exist."""
        assert executor.unregister_skill("nonexistent") is False

    def test_clear_skills(self, executor: SkillExecutor):
        """Test clearing all skills."""
        executor.register_skill(MockSkill())
        executor.register_skill(SkillWithArtifacts())
        assert len(executor) == 2
        executor.clear()
        assert len(executor) == 0


# ============================================================================
# SkillExecutor Lookup Tests
# ============================================================================


class TestSkillExecutorLookup:
    """Tests for skill lookup methods."""

    def test_get_skill(self, executor: SkillExecutor):
        """Test getting a skill by name."""
        skill = MockSkill()
        executor.register_skill(skill)
        retrieved = executor.get_skill("mock-skill")
        assert retrieved is skill

    def test_get_nonexistent_skill(self, executor: SkillExecutor):
        """Test getting a skill that doesn't exist."""
        assert executor.get_skill("nonexistent") is None

    def test_list_skills_empty(self, executor: SkillExecutor):
        """Test listing skills when empty."""
        assert executor.list_skills() == []

    def test_list_skills_sorted(self, executor: SkillExecutor):
        """Test that list_skills returns sorted list."""
        executor.register_skill(SkillWithArtifacts())  # artifact-skill
        executor.register_skill(FailingSkill())  # failing-skill
        executor.register_skill(MockSkill())  # mock-skill
        skills = executor.list_skills()
        assert skills == ["artifact-skill", "failing-skill", "mock-skill"]

    def test_has_skill(self, executor: SkillExecutor):
        """Test has_skill method."""
        executor.register_skill(MockSkill())
        assert executor.has_skill("mock-skill") is True
        assert executor.has_skill("other-skill") is False

    def test_contains_operator(self, executor: SkillExecutor):
        """Test 'in' operator for skill lookup."""
        executor.register_skill(MockSkill())
        assert "mock-skill" in executor
        assert "other-skill" not in executor

    def test_len_operator(self, executor: SkillExecutor):
        """Test len() for executor."""
        assert len(executor) == 0
        executor.register_skill(MockSkill())
        assert len(executor) == 1


# ============================================================================
# SkillExecutor Execution Tests
# ============================================================================


class TestSkillExecutorExecution:
    """Tests for skill execution."""

    def test_execute_skill_success(
        self,
        executor: SkillExecutor,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test successful skill execution."""
        executor.register_skill(MockSkill())
        output = executor.execute("mock-skill", skill_input, thread_state)
        assert output.success is True
        assert "Processed: Test query" == output.content
        assert output.metadata["workspace_id"] == "test-workspace"

    def test_execute_skill_with_artifacts(
        self,
        executor: SkillExecutor,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test skill that produces artifacts."""
        executor.register_skill(SkillWithArtifacts())
        output = executor.execute("artifact-skill", skill_input, thread_state)
        assert output.success is True
        assert len(output.artifacts) == 1
        assert output.artifacts[0].type == "research_idea"

    def test_execute_skill_not_found(
        self,
        executor: SkillExecutor,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test executing non-existent skill raises SkillNotFoundError."""
        with pytest.raises(SkillNotFoundError) as exc_info:
            executor.execute("nonexistent", skill_input, thread_state)
        assert exc_info.value.skill_name == "nonexistent"

    def test_execute_skill_validation_error(
        self,
        executor: SkillExecutor,
        thread_state: ThreadState,
    ):
        """Test validation error is raised properly."""
        executor.register_skill(SkillWithValidation())
        input_data = SkillInput(
            workspace_id="ws",
            user_query="query",
            context={},  # Missing required_key
        )
        with pytest.raises(SkillValidationError) as exc_info:
            executor.execute("validated-skill", input_data, thread_state)
        assert exc_info.value.skill_name == "validated-skill"
        assert "required_key" in exc_info.value.error_message

    def test_execute_skill_with_exception(
        self,
        executor: SkillExecutor,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test skill that raises exception."""
        executor.register_skill(ExceptionSkill())
        with pytest.raises(SkillExecutionError) as exc_info:
            executor.execute("exception-skill", skill_input, thread_state)
        assert exc_info.value.skill_name == "exception-skill"
        assert isinstance(exc_info.value.original_error, ValueError)

    def test_execute_skill_returns_failure(
        self,
        executor: SkillExecutor,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test skill that returns failure output."""
        executor.register_skill(FailingSkill())
        output = executor.execute("failing-skill", skill_input, thread_state)
        assert output.success is False
        assert output.error_message == "This skill always fails"


# ============================================================================
# SkillExecutor Info Tests
# ============================================================================


class TestSkillExecutorInfo:
    """Tests for skill info methods."""

    def test_get_skill_info(self, executor: SkillExecutor):
        """Test getting skill info."""
        executor.register_skill(MockSkill())
        info = executor.get_skill_info("mock-skill")
        assert info is not None
        assert info["name"] == "mock-skill"
        assert info["description"] == "A mock skill for testing"
        assert info["version"] == "1.0.0"

    def test_get_nonexistent_skill_info(self, executor: SkillExecutor):
        """Test getting info for non-existent skill."""
        info = executor.get_skill_info("nonexistent")
        assert info is None

    def test_get_all_skills_info(self, executor: SkillExecutor):
        """Test getting info for all skills."""
        executor.register_skill(MockSkill())
        executor.register_skill(SkillWithArtifacts())
        all_info = executor.get_all_skills_info()
        assert len(all_info) == 2

        names = [info["name"] for info in all_info]
        assert "mock-skill" in names
        assert "artifact-skill" in names


# ============================================================================
# Integration Tests
# ============================================================================


class TestSkillFrameworkIntegration:
    """Integration tests for the skill framework."""

    def test_full_skill_workflow(
        self,
        executor: SkillExecutor,
        thread_state: ThreadState,
    ):
        """Test complete workflow from registration to execution."""
        # Register multiple skills
        executor.register_skill(MockSkill())
        executor.register_skill(SkillWithArtifacts())
        executor.register_skill(SkillWithValidation())

        # List registered skills
        skills = executor.list_skills()
        assert len(skills) == 3

        # Execute a skill
        input_data = SkillInput(
            workspace_id="integration-ws",
            user_query="Integration test query",
            context={"required_key": "value"},
        )

        output = executor.execute("validated-skill", input_data, thread_state)
        assert output.success is True

        # Get skill info
        info = executor.get_skill_info("mock-skill")
        assert info is not None
        assert info["name"] == "mock-skill"

    def test_skill_with_state_artifacts(
        self,
        executor: SkillExecutor,
        thread_state: ThreadState,
    ):
        """Test that skills can access thread state."""
        executor.register_skill(SkillWithArtifacts())

        input_data = SkillInput(
            workspace_id="state-test-ws",
            user_query="Create artifact",
        )

        output = executor.execute("artifact-skill", input_data, thread_state)
        assert output.success is True
        assert len(output.artifacts) == 1

        # Verify artifact has correct workspace_id from input
        artifact = output.artifacts[0]
        assert artifact.workspace_id == "state-test-ws"
        assert artifact.created_by_skill == "artifact-skill"


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_skill_with_empty_context(self, thread_state: ThreadState):
        """Test skill with empty context dictionary."""
        skill = MockSkill()
        input_data = SkillInput(
            workspace_id="ws",
            user_query="query",
            context={},
        )
        output = skill.execute(input_data, thread_state)
        assert output.success is True

    def test_skill_with_large_context(self, thread_state: ThreadState):
        """Test skill with large context data."""
        skill = MockSkill()
        large_context = {f"key_{i}": f"value_{i}" * 100 for i in range(100)}
        input_data = SkillInput(
            workspace_id="ws",
            user_query="query",
            context=large_context,
        )
        output = skill.execute(input_data, thread_state)
        assert output.success is True

    def test_skill_with_unicode_query(self, thread_state: ThreadState):
        """Test skill with unicode characters in query."""
        skill = MockSkill()
        input_data = SkillInput(
            workspace_id="ws",
            user_query="研究课题：机器学习在自然语言处理中的应用",
            context={},
        )
        output = skill.execute(input_data, thread_state)
        assert output.success is True
        assert "机器学习" in output.content

    def test_skill_with_special_characters_in_workspace_id(self, thread_state: ThreadState):
        """Test skill with special characters in workspace_id."""
        skill = MockSkill()
        input_data = SkillInput(
            workspace_id="ws-with-special_chars.123",
            user_query="query",
        )
        output = skill.execute(input_data, thread_state)
        assert output.success is True
