"""Tests for FullpaperWriterSkill.

This module tests:
- Skill initialization and attributes
- Input validation
- Section writing
- Citation extraction
- Paper combination
- Artifact creation
- Async execution
"""


import pytest

from src.agents.thread_state import ThreadState
from src.skills.base import BaseSkill, SkillInput, SkillOutput
from src.skills.implementations.fullpaper_writer import (
    PAPER_SECTIONS,
    SECTION_PROMPTS,
    ACADEMIC_WRITING_ORDER,
    SECTION_DEPENDENCIES,
    FullpaperWriterSkill,
    FullpaperWriterSkillV2,
    MockLLMService,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def skill() -> FullpaperWriterSkill:
    """Create a FullpaperWriterSkill instance for testing."""
    return FullpaperWriterSkill()


@pytest.fixture
def mock_llm_service() -> MockLLMService:
    """Create a MockLLMService instance for testing."""
    return MockLLMService()


@pytest.fixture
def basic_framework_outline() -> dict:
    """Create a basic framework outline for testing."""
    return {
        "id": "outline-001",
        "title": "Deep Learning for Natural Language Processing",
        "topic": "Applying transformer models to NLP tasks",
        "sections": {
            "introduction": "Focus on recent advances in transformers",
            "methodology": "Include details about fine-tuning",
        },
    }


@pytest.fixture
def skill_input(basic_framework_outline: dict) -> SkillInput:
    """Create a default SkillInput with framework outline."""
    return SkillInput(
        workspace_id="test-workspace",
        user_query="Write a paper about NLP",
        context={"framework_outline": basic_framework_outline},
    )


@pytest.fixture
def skill_input_with_literature(basic_framework_outline: dict) -> SkillInput:
    """Create SkillInput with literature context."""
    return SkillInput(
        workspace_id="test-workspace",
        user_query="Write a paper about NLP",
        context={
            "framework_outline": basic_framework_outline,
            "literature_context": "Key papers: Vaswani et al. (2017), Devlin et al. (2019)",
        },
    )


@pytest.fixture
def thread_state() -> ThreadState:
    """Create a default ThreadState for testing."""
    return ThreadState(
        messages=[],
        workspace_id="test-workspace",
    )


@pytest.fixture
def thread_state_with_cited_papers() -> ThreadState:
    """Create ThreadState with existing cited papers."""
    return ThreadState(
        messages=[],
        workspace_id="test-workspace",
        cited_papers=["Brown et al. (2020)", "Radford et al. (2021)"],
    )


# ============================================================================
# Test Skill Attributes
# ============================================================================


class TestFullpaperWriterSkillAttributes:
    """Tests for skill class attributes."""

    def test_skill_name(self, skill: FullpaperWriterSkill):
        """Test skill has correct name."""
        assert skill.name == "fullpaper-writer"

    def test_skill_description(self, skill: FullpaperWriterSkill):
        """Test skill has description."""
        assert "complete academic papers" in skill.description.lower()

    def test_skill_version(self, skill: FullpaperWriterSkill):
        """Test skill has version."""
        # Version 2.0.0 for academic writing order
        assert skill.version == "2.0.0"

    def test_skill_is_base_skill_subclass(self, skill: FullpaperWriterSkill):
        """Test skill inherits from BaseSkill."""
        assert isinstance(skill, BaseSkill)

    def test_paper_sections_constant(self):
        """Test PAPER_SECTIONS contains expected sections."""
        expected = [
            "introduction",
            "related_work",
            "methodology",
            "experiments",
            "discussion",
            "conclusion",
        ]
        assert PAPER_SECTIONS == expected

    def test_section_prompts_constant(self):
        """Test SECTION_PROMPTS has prompts for all sections."""
        for section in PAPER_SECTIONS:
            assert section in SECTION_PROMPTS
            assert len(SECTION_PROMPTS[section]) > 100


# ============================================================================
# Test Input Validation
# ============================================================================


class TestFullpaperWriterSkillValidation:
    """Tests for input validation."""

    def test_validate_input_missing_framework_outline(self, skill: FullpaperWriterSkill):
        """Test validation fails without framework_outline."""
        input_data = SkillInput(
            workspace_id="ws",
            user_query="query",
            context={},
        )
        error = skill.validate_input(input_data)
        assert error is not None
        assert "framework_outline" in error

    def test_validate_input_with_framework_outline(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
    ):
        """Test validation passes with framework_outline."""
        error = skill.validate_input(skill_input)
        assert error is None

    def test_validate_input_missing_workspace(self, skill: FullpaperWriterSkill):
        """Test validation fails without workspace_id."""
        input_data = SkillInput(
            workspace_id="",
            user_query="query",
            context={"framework_outline": {"topic": "test"}},
        )
        error = skill.validate_input(input_data)
        assert error == "workspace_id is required"

    def test_validate_input_empty_query(self, skill: FullpaperWriterSkill):
        """Test validation fails with empty query."""
        input_data = SkillInput(
            workspace_id="ws",
            user_query="",
            context={"framework_outline": {"topic": "test"}},
        )
        error = skill.validate_input(input_data)
        assert error == "user_query cannot be empty"


# ============================================================================
# Test Literature Context
# ============================================================================


class TestLiteratureContext:
    """Tests for literature context handling."""

    def test_get_literature_context_from_state(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
    ):
        """Test getting literature context from state."""
        state = ThreadState(messages=[], workspace_id="ws", literature_context="Test literature context")

        context = skill._get_literature_context(skill_input, state)
        assert "Test literature context" in context

    def test_get_literature_context_from_input(
        self,
        skill: FullpaperWriterSkill,
        skill_input_with_literature: SkillInput,
    ):
        """Test getting literature context from input context."""
        state = ThreadState(messages=[], workspace_id="ws")
        context = skill._get_literature_context(skill_input_with_literature, state)
        assert "Vaswani" in context

    def test_get_literature_context_includes_cited_papers(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
        thread_state_with_cited_papers: ThreadState,
    ):
        """Test literature context includes cited papers."""
        context = skill._get_literature_context(skill_input, thread_state_with_cited_papers)
        assert "Brown et al. (2020)" in context
        assert "Radford et al. (2021)" in context

    def test_get_literature_context_default(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test default literature context when none provided."""
        context = skill._get_literature_context(skill_input, thread_state)
        assert "No specific literature context" in context


# ============================================================================
# Test Citation Extraction
# ============================================================================


class TestCitationExtraction:
    """Tests for citation extraction from text."""

    def test_extract_single_citation(self, skill: FullpaperWriterSkill):
        """Test extracting a single citation."""
        text = "Previous work (Vaswani et al. (2017)) showed promising results."
        citations = skill._extract_citations(text)
        assert "Vaswani et al. (2017)" in citations

    def test_extract_multiple_citations(self, skill: FullpaperWriterSkill):
        """Test extracting multiple citations."""
        text = """
        Deep learning (LeCun et al., 2015) has transformed AI.
        Transformers (Vaswani et al., 2017) revolutionized NLP.
        BERT (Devlin et al., 2019) improved language understanding.
        """
        citations = skill._extract_citations(text)
        assert len(citations) >= 3
        assert "LeCun et al. (2015)" in citations
        assert "Vaswani et al. (2017)" in citations
        assert "Devlin et al. (2019)" in citations

    def test_extract_citation_single_author(self, skill: FullpaperWriterSkill):
        """Test extracting citation with single author."""
        text = "According to Brown (2020), few-shot learning is effective."
        citations = skill._extract_citations(text)
        assert "Brown (2020)" in citations

    def test_extract_no_citations(self, skill: FullpaperWriterSkill):
        """Test text with no citations."""
        text = "This is plain text without any citations."
        citations = skill._extract_citations(text)
        assert len(citations) == 0


# ============================================================================
# Test Section Combination
# ============================================================================


class TestSectionCombination:
    """Tests for combining sections into a paper."""

    def test_combine_sections_basic(self, skill: FullpaperWriterSkill):
        """Test basic section combination."""
        sections = {
            "introduction": "## 1. Introduction\n\nContent here.",
            "conclusion": "## 6. Conclusion\n\nFinal thoughts.",
        }
        outline = {"title": "Test Paper"}

        paper = skill._combine_sections(sections, "Test Topic", outline)

        assert "# Test Paper" in paper
        assert "Introduction" in paper
        assert "Conclusion" in paper

    def test_combine_sections_with_title(self, skill: FullpaperWriterSkill):
        """Test combination with custom title."""
        sections = {"introduction": "Intro content"}
        outline = {"title": "Custom Title: A Study"}

        paper = skill._combine_sections(sections, "Test Topic", outline)

        assert "# Custom Title: A Study" in paper

    def test_combine_sections_with_abstract(self, skill: FullpaperWriterSkill):
        """Test combination includes abstract from outline."""
        sections = {"introduction": "Intro content"}
        outline = {
            "title": "Test Paper",
            "abstract": "This is the abstract of the paper.",
        }

        paper = skill._combine_sections(sections, "Test Topic", outline)

        assert "Abstract" in paper
        assert "This is the abstract" in paper

    def test_combine_sections_order(self, skill: FullpaperWriterSkill):
        """Test sections appear in correct order."""
        sections = {
            "conclusion": "## 6. Conclusion",
            "introduction": "## 1. Introduction",
            "methodology": "## 3. Methodology",
        }
        outline = {}

        paper = skill._combine_sections(sections, "Topic", outline)

        intro_idx = paper.find("Introduction")
        method_idx = paper.find("Methodology")
        concl_idx = paper.find("Conclusion")

        assert intro_idx < method_idx < concl_idx


# ============================================================================
# Test Skill Execution
# ============================================================================


class TestSkillExecution:
    """Tests for skill execution."""

    def test_execute_returns_skill_output(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test execute returns SkillOutput."""
        output = skill.execute(skill_input, thread_state)
        assert isinstance(output, SkillOutput)

    def test_execute_success(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test execute is successful."""
        output = skill.execute(skill_input, thread_state)
        assert output.success is True

    def test_execute_creates_artifact(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test execute creates paper_draft artifact."""
        output = skill.execute(skill_input, thread_state)
        assert len(output.artifacts) == 1
        assert output.artifacts[0].type == "paper_draft"

    def test_execute_artifact_has_correct_workspace(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test artifact has correct workspace_id."""
        output = skill.execute(skill_input, thread_state)
        assert output.artifacts[0].workspace_id == "test-workspace"

    def test_execute_artifact_created_by_skill(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test artifact has created_by_skill set."""
        output = skill.execute(skill_input, thread_state)
        # Accept either the old or new skill name for backward compatibility
        assert output.artifacts[0].created_by_skill in ["fullpaper-writer", "fullpaper-writer-v2"]

    def test_execute_generates_all_sections(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test execute generates all sections."""
        output = skill.execute(skill_input, thread_state)
        artifact_content = output.artifacts[0].content

        assert "sections" in artifact_content
        # V2 generates sections in ACADEMIC_WRITING_ORDER which includes abstract
        for section in ACADEMIC_WRITING_ORDER:
            assert section in artifact_content["sections"]

    def test_execute_metadata(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test execute returns correct metadata."""
        output = skill.execute(skill_input, thread_state)

        assert "sections_generated" in output.metadata
        assert len(output.metadata["sections_generated"]) == len(PAPER_SECTIONS)
        assert "word_count" in output.metadata

    def test_execute_content_not_empty(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test execute returns non-empty content."""
        output = skill.execute(skill_input, thread_state)
        assert len(output.content) > 0
        assert len(output.content.split()) > 100  # At least 100 words

    def test_execute_updates_cited_papers(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test execute updates cited_papers in state."""
        output = skill.execute(skill_input, thread_state)
        # Check that cited_papers was updated (mock LLM generates citations)
        # The artifact should have citations in its content
        artifact_citations = output.artifacts[0].content.get("citations", [])
        # Verify citations were extracted (mock content has comma-style citations)
        assert len(artifact_citations) > 0 or len(thread_state.get("cited_papers", [])) > 0


# ============================================================================
# Test Async Execution
# ============================================================================


class TestAsyncExecution:
    """Tests for async skill execution."""

    @pytest.mark.asyncio
    async def test_execute_async_returns_skill_output(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test async execute returns SkillOutput."""
        output = await skill.execute_async(skill_input, thread_state)
        assert isinstance(output, SkillOutput)

    @pytest.mark.asyncio
    async def test_execute_async_success(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test async execute is successful."""
        output = await skill.execute_async(skill_input, thread_state)
        assert output.success is True

    @pytest.mark.asyncio
    async def test_execute_async_creates_artifact(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test async execute creates artifact."""
        output = await skill.execute_async(skill_input, thread_state)
        assert len(output.artifacts) == 1


# ============================================================================
# Test MockLLMService
# ============================================================================


class TestMockLLMService:
    """Tests for MockLLMService."""

    def test_mock_llm_service_creation(self, mock_llm_service: MockLLMService):
        """Test MockLLMService can be created."""
        assert mock_llm_service is not None

    @pytest.mark.asyncio
    async def test_generate_returns_string(self, mock_llm_service: MockLLMService):
        """Test generate returns a string."""
        result = await mock_llm_service.generate("Test prompt")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_generate_introduction(self, mock_llm_service: MockLLMService):
        """Test generate returns introduction content."""
        prompt = "Write an Introduction section..."
        result = await mock_llm_service.generate(prompt)
        assert "Introduction" in result

    @pytest.mark.asyncio
    async def test_generate_related_work(self, mock_llm_service: MockLLMService):
        """Test generate returns related work content."""
        prompt = "Write a Related Work section..."
        result = await mock_llm_service.generate(prompt)
        assert "Related Work" in result

    @pytest.mark.asyncio
    async def test_generate_methodology(self, mock_llm_service: MockLLMService):
        """Test generate returns methodology content."""
        prompt = "Write a Methodology section..."
        result = await mock_llm_service.generate(prompt)
        assert "Methodology" in result

    @pytest.mark.asyncio
    async def test_generate_experiments(self, mock_llm_service: MockLLMService):
        """Test generate returns experiments content."""
        prompt = "Write an Experiments section..."
        result = await mock_llm_service.generate(prompt)
        assert "Experiments" in result

    @pytest.mark.asyncio
    async def test_generate_discussion(self, mock_llm_service: MockLLMService):
        """Test generate returns discussion content."""
        prompt = "Write a Discussion section..."
        result = await mock_llm_service.generate(prompt)
        assert "Discussion" in result

    @pytest.mark.asyncio
    async def test_generate_conclusion(self, mock_llm_service: MockLLMService):
        """Test generate returns conclusion content."""
        prompt = "Write a Conclusion section..."
        result = await mock_llm_service.generate(prompt)
        assert "Conclusion" in result

    @pytest.mark.asyncio
    async def test_generate_includes_citations(self, mock_llm_service: MockLLMService):
        """Test generated content includes citations."""
        prompt = "Write an Introduction section..."
        result = await mock_llm_service.generate(prompt)
        # Check for citation pattern
        assert "(" in result and ")" in result


# ============================================================================
# Test Section Writing
# ============================================================================


class TestSectionWriting:
    """Tests for individual section writing."""

    def test_write_section_introduction(
        self,
        skill: FullpaperWriterSkill,
        basic_framework_outline: dict,
    ):
        """Test writing introduction section."""
        content = skill._write_section(
            section_name="introduction",
            topic="Machine Learning",
            outline=basic_framework_outline,
            literature_context="Test context",
        )
        assert len(content) > 0
        assert "Introduction" in content or "introduction" in content.lower()

    def test_write_section_with_guidance(
        self,
        skill: FullpaperWriterSkill,
        basic_framework_outline: dict,
    ):
        """Test section writing uses guidance from outline."""
        content = skill._write_section(
            section_name="introduction",
            topic="ML",
            outline=basic_framework_outline,
            literature_context="",
        )
        # Content should be generated
        assert len(content) > 0

    def test_write_section_unknown(
        self,
        skill: FullpaperWriterSkill,
        basic_framework_outline: dict,
    ):
        """Test writing unknown section returns default."""
        content = skill._write_section(
            section_name="unknown_section",
            topic="ML",
            outline=basic_framework_outline,
            literature_context="",
        )
        assert "unknown_section" in content.lower()


# ============================================================================
# Test Artifact Content
# ============================================================================


class TestArtifactContent:
    """Tests for artifact content structure."""

    def test_artifact_has_title(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test artifact has title."""
        output = skill.execute(skill_input, thread_state)
        content = output.artifacts[0].content
        assert "title" in content

    def test_artifact_has_topic(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test artifact has topic."""
        output = skill.execute(skill_input, thread_state)
        content = output.artifacts[0].content
        assert "topic" in content

    def test_artifact_has_full_paper(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test artifact has full_paper."""
        output = skill.execute(skill_input, thread_state)
        content = output.artifacts[0].content
        assert "full_paper" in content

    def test_artifact_has_citations(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test artifact has citations list."""
        output = skill.execute(skill_input, thread_state)
        content = output.artifacts[0].content
        assert "citations" in content
        assert isinstance(content["citations"], list)

    def test_artifact_has_word_count(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test artifact has word_count."""
        output = skill.execute(skill_input, thread_state)
        content = output.artifacts[0].content
        assert "word_count" in content
        assert content["word_count"] > 0

    def test_artifact_has_generated_at(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test artifact has generated_at timestamp."""
        output = skill.execute(skill_input, thread_state)
        content = output.artifacts[0].content
        assert "generated_at" in content


# ============================================================================
# Test Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_execute_with_empty_outline(
        self,
        skill: FullpaperWriterSkill,
        thread_state: ThreadState,
    ):
        """Test execute with minimal outline."""
        input_data = SkillInput(
            workspace_id="ws",
            user_query="Write about AI",
            context={"framework_outline": {}},
        )
        output = skill.execute(input_data, thread_state)
        assert output.success is True

    def test_execute_with_literature_in_context(
        self,
        skill: FullpaperWriterSkill,
        skill_input_with_literature: SkillInput,
        thread_state: ThreadState,
    ):
        """Test execute with literature context."""
        output = skill.execute(skill_input_with_literature, thread_state)
        assert output.success is True

    def test_skill_with_custom_llm_service(self):
        """Test skill initialization with custom LLM service."""
        custom_llm = MockLLMService()
        skill = FullpaperWriterSkill(llm_service=custom_llm)
        assert skill.llm_service is custom_llm

    def test_execute_merges_cited_papers(
        self,
        skill: FullpaperWriterSkill,
        skill_input: SkillInput,
        thread_state_with_cited_papers: ThreadState,
    ):
        """Test execute preserves existing cited papers."""
        existing_cited = list(thread_state_with_cited_papers["cited_papers"])
        skill.execute(skill_input, thread_state_with_cited_papers)

        # Existing citations should still be there
        for citation in existing_cited:
            assert citation in thread_state_with_cited_papers["cited_papers"]


# ============================================================================
# Test Skill with Executor
# ============================================================================


class TestSkillWithExecutor:
    """Tests for skill integration with SkillExecutor."""

    def test_skill_registration(self):
        """Test skill can be registered with executor."""
        from src.skills.executor import SkillExecutor

        executor = SkillExecutor()
        skill = FullpaperWriterSkill()
        executor.register_skill(skill)

        assert executor.has_skill("fullpaper-writer")

    def test_skill_execution_through_executor(
        self,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test skill execution through executor."""
        from src.skills.executor import SkillExecutor

        executor = SkillExecutor()
        skill = FullpaperWriterSkill()
        executor.register_skill(skill)

        output = executor.execute("fullpaper-writer", skill_input, thread_state)
        assert output.success is True
        assert len(output.artifacts) == 1

    def test_skill_validation_through_executor(self, thread_state: ThreadState):
        """Test validation through executor."""
        from src.skills.executor import (
            SkillExecutor,
            SkillValidationError,
        )

        executor = SkillExecutor()
        skill = FullpaperWriterSkill()
        executor.register_skill(skill)

        input_data = SkillInput(
            workspace_id="ws",
            user_query="query",
            context={},  # Missing framework_outline
        )

        with pytest.raises(SkillValidationError):
            executor.execute("fullpaper-writer", input_data, thread_state)


# ============================================================================
# Test Academic Writing Order (V2)
# ============================================================================


class TestFullPaperWriterAcademicOrder:
    """Tests for academic writing order in FullPaperWriterSkillV2."""

    def test_academic_writing_order_constant(self):
        """Sections should be written in academic order."""
        assert ACADEMIC_WRITING_ORDER[0] == "methodology"
        assert ACADEMIC_WRITING_ORDER[-1] == "abstract"
        # Experiments and related_work should come after methodology
        assert "experiments" in ACADEMIC_WRITING_ORDER
        assert "related_work" in ACADEMIC_WRITING_ORDER
        # Introduction before conclusion
        assert ACADEMIC_WRITING_ORDER.index("introduction") < ACADEMIC_WRITING_ORDER.index("conclusion")

    def test_section_dependencies_constant(self):
        """Section dependencies should be properly defined."""
        # Methodology has no dependencies
        assert SECTION_DEPENDENCIES["methodology"] == []
        # Experiments depends on methodology
        assert "methodology" in SECTION_DEPENDENCIES["experiments"]
        # Related work depends on methodology
        assert "methodology" in SECTION_DEPENDENCIES["related_work"]
        # Introduction depends on multiple sections
        assert "methodology" in SECTION_DEPENDENCIES["introduction"]
        assert "experiments" in SECTION_DEPENDENCIES["introduction"]
        assert "related_work" in SECTION_DEPENDENCIES["introduction"]
        # Conclusion depends on introduction
        assert "introduction" in SECTION_DEPENDENCIES["conclusion"]
        # Abstract depends on introduction and conclusion
        assert "introduction" in SECTION_DEPENDENCIES["abstract"]
        assert "conclusion" in SECTION_DEPENDENCIES["abstract"]

    def test_parallel_sections_identified(self):
        """Should identify which sections can be written in parallel."""
        skill = FullpaperWriterSkillV2()
        parallel_groups = skill._get_parallel_groups()
        # Experiments and related_work should be in a parallel group together
        parallel_pair = {"experiments", "related_work"}
        found = any(parallel_pair.issubset(group) for group in parallel_groups)
        assert found, f"Expected parallel group with experiments and related_work, got {parallel_groups}"

    def test_injects_prev_chapters(self):
        """Dependent sections should receive previous chapters."""
        skill = FullpaperWriterSkillV2()
        prev_chapters = {"methodology": "Methodology content..."}
        context = skill._prepare_section_context("experiments", prev_chapters, "Test topic", {}, "No literature context")
        assert "prev_chapters" in context
        assert context["prev_chapters"]["methodology"] == "Methodology content..."

    def test_injects_prev_chapters_for_introduction(self):
        """Introduction should receive all its dependencies."""
        skill = FullpaperWriterSkillV2()
        prev_chapters = {
            "methodology": "Methodology content...",
            "experiments": "Experiments content...",
            "related_work": "Related work content...",
        }
        context = skill._prepare_section_context("introduction", prev_chapters, "Test topic", {}, "No literature context")
        assert "prev_chapters" in context
        assert len(context["prev_chapters"]) == 3

    def test_format_terminology_with_glossary(self):
        """Should format terminology glossary correctly."""
        skill = FullpaperWriterSkillV2()
        terminology_glossary = {
            "LLM": "Large Language Model",
            "NLP": "Natural Language Processing",
        }
        formatted = skill._format_terminology(terminology_glossary)
        assert "LLM" in formatted
        assert "Large Language Model" in formatted

    def test_format_terminology_without_glossary(self):
        """Should handle missing terminology glossary."""
        skill = FullpaperWriterSkillV2()
        formatted = skill._format_terminology(None)
        assert formatted == "" or "No specific terminology" in formatted

    def test_v2_skill_execution(
        self,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test V2 skill executes successfully."""
        skill = FullpaperWriterSkillV2()
        output = skill.execute(skill_input, thread_state)
        assert output.success is True
        assert len(output.artifacts) == 1

    def test_v2_respects_dependencies(
        self,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test V2 respects section dependencies in execution."""
        skill = FullpaperWriterSkillV2()
        output = skill.execute(skill_input, thread_state)
        sections = output.artifacts[0].content.get("sections", {})
        # All expected sections should be generated
        for section in ACADEMIC_WRITING_ORDER:
            assert section in sections, f"Section {section} not found in output"

    def test_backward_compatibility_alias(self):
        """FullpaperWriterSkill should work as alias for V2."""
        # Both should be the same class or V2 should be aliased
        assert FullpaperWriterSkill == FullpaperWriterSkillV2 or issubclass(FullpaperWriterSkill, FullpaperWriterSkillV2.__class__)


class TestAcademicOrderIntegration:
    """Integration tests for academic writing order."""

    @pytest.fixture
    def v2_skill(self) -> FullpaperWriterSkillV2:
        """Create a FullpaperWriterSkillV2 instance for testing."""
        return FullpaperWriterSkillV2()

    @pytest.fixture
    def framework_with_terminology(self) -> dict:
        """Create a framework outline with terminology glossary."""
        return {
            "id": "outline-002",
            "title": "Advanced NLP Techniques",
            "topic": "State-of-the-art NLP methods",
            "sections": {
                "introduction": "Focus on transformer advances",
                "methodology": "Include fine-tuning details",
            },
            "terminology_glossary": {
                "Transformer": "Neural network architecture using self-attention",
                "BERT": "Bidirectional Encoder Representations from Transformers",
            },
        }

    def test_v2_with_terminology_glossary(
        self,
        v2_skill: FullpaperWriterSkillV2,
        framework_with_terminology: dict,
        thread_state: ThreadState,
    ):
        """Test V2 handles terminology glossary from framework."""
        skill_input = SkillInput(
            workspace_id="test-workspace",
            user_query="Write about NLP",
            context={"framework_outline": framework_with_terminology},
        )
        output = v2_skill.execute(skill_input, thread_state)
        assert output.success is True

    def test_v2_async_execution(
        self,
        v2_skill: FullpaperWriterSkillV2,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test V2 async execution respects dependencies."""
        import asyncio
        output = asyncio.run(v2_skill.execute_async(skill_input, thread_state))
        assert output.success is True
        assert len(output.artifacts) == 1

    def test_v2_generates_abstract_last(
        self,
        v2_skill: FullpaperWriterSkillV2,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test that abstract is generated last."""
        # Track the order of section generation
        generated_order = []
        original_write = v2_skill._write_section

        def track_write(section_name, *args, **kwargs):
            generated_order.append(section_name)
            return original_write(section_name, *args, **kwargs)

        v2_skill._write_section = track_write
        v2_skill.execute(skill_input, thread_state)

        # Abstract should be the last section generated
        assert generated_order[-1] == "abstract"

    def test_v2_citation_tracking(
        self,
        v2_skill: FullpaperWriterSkillV2,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test V2 properly tracks citations across sections."""
        output = v2_skill.execute(skill_input, thread_state)
        citations = output.artifacts[0].content.get("citations", [])
        assert isinstance(citations, list)
