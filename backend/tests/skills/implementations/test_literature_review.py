"""Comprehensive tests for the LiteratureReviewSkill.

This module tests:
- PaperData data structure
- Theme data structure
- SynthesisMatrix functionality
- LiteratureReviewSkill execution
- Literature review generation
- Artifact creation
"""


import pytest

from src.agents.thread_state import ThreadState
from src.skills.base import SkillInput
from src.skills.implementations.literature_review import (
    LiteratureReviewSkill,
    PaperData,
    SynthesisMatrix,
    Theme,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def skill() -> LiteratureReviewSkill:
    """Create a LiteratureReviewSkill instance."""
    return LiteratureReviewSkill()


@pytest.fixture
def sample_paper() -> dict:
    """Create a sample paper dictionary."""
    return {
        "id": "paper-1",
        "title": "Deep Learning for Natural Language Processing",
        "authors": [
            {"name": "John Smith", "affiliation": "MIT"},
            {"name": "Jane Doe", "affiliation": "Stanford"},
        ],
        "year": 2023,
        "abstract": "This paper presents a novel approach to natural language processing using deep learning techniques. We demonstrate significant improvements in text classification and sentiment analysis tasks.",
        "keywords": ["deep learning", "NLP", "transformers"],
        "contributions": ["Novel architecture for NLP", "State-of-the-art results on benchmarks"],
    }


@pytest.fixture
def sample_papers() -> list[dict]:
    """Create a list of sample papers."""
    return [
        {
            "id": "paper-1",
            "title": "Deep Learning for Natural Language Processing",
            "authors": [{"name": "John Smith"}, {"name": "Jane Doe"}],
            "year": 2023,
            "abstract": "This paper presents deep learning techniques for NLP tasks including text classification and sentiment analysis using transformer architectures.",
            "keywords": ["deep learning", "NLP", "transformers"],
            "contributions": ["Novel architecture for NLP"],
        },
        {
            "id": "paper-2",
            "title": "Transformer Models in Computer Vision",
            "authors": [{"name": "Alice Brown"}],
            "year": 2022,
            "abstract": "We explore the application of transformer models to computer vision tasks, showing competitive results with convolutional neural networks.",
            "keywords": ["transformers", "computer vision", "deep learning"],
            "contributions": ["Vision transformer adaptation"],
        },
        {
            "id": "paper-3",
            "title": "Attention Mechanisms in Neural Networks",
            "authors": [{"name": "Bob Wilson"}, {"name": "Carol White"}],
            "year": 2021,
            "abstract": "A comprehensive study of attention mechanisms in neural networks, covering self-attention, cross-attention, and multi-head attention.",
            "keywords": ["attention", "neural networks", "transformers"],
        },
    ]


@pytest.fixture
def skill_input(sample_papers) -> SkillInput:
    """Create a SkillInput with sample papers."""
    return SkillInput(
        workspace_id="test-workspace",
        user_query="What are the recent advances in deep learning?",
        context={"papers": sample_papers},
    )


@pytest.fixture
def thread_state() -> ThreadState:
    """Create a ThreadState for testing."""
    return ThreadState(
        messages=[],
        workspace_id="test-workspace",
    )


# ============================================================================
# PaperData Tests
# ============================================================================


class TestPaperData:
    """Tests for the PaperData class."""

    def test_paper_data_creation_with_all_fields(self):
        """Test creating PaperData with all fields."""
        paper = PaperData(
            paper_id="test-1",
            title="Test Paper",
            authors=["Author One", "Author Two"],
            year=2023,
            abstract="Test abstract",
            keywords=["test", "paper"],
            methodology="experimental",
            findings=["finding 1"],
            contributions=["contribution 1"],
        )
        assert paper.paper_id == "test-1"
        assert paper.title == "Test Paper"
        assert len(paper.authors) == 2
        assert paper.year == 2023
        assert paper.abstract == "Test abstract"
        assert len(paper.keywords) == 2

    def test_paper_data_creation_with_minimal_fields(self):
        """Test creating PaperData with minimal fields."""
        paper = PaperData(
            paper_id="test-2",
            title="Minimal Paper",
            authors=[],
            year=None,
            abstract=None,
        )
        assert paper.paper_id == "test-2"
        assert paper.keywords == []
        assert paper.findings == []
        assert paper.contributions == []

    def test_paper_data_to_dict(self):
        """Test PaperData to_dict method."""
        paper = PaperData(
            paper_id="test-3",
            title="Dict Test",
            authors=["Author"],
            year=2022,
            abstract="Abstract",
        )
        result = paper.to_dict()
        assert isinstance(result, dict)
        assert result["paper_id"] == "test-3"
        assert result["title"] == "Dict Test"
        assert result["year"] == 2022


# ============================================================================
# Theme Tests
# ============================================================================


class TestTheme:
    """Tests for the Theme class."""

    def test_theme_creation(self):
        """Test creating a Theme."""
        theme = Theme(name="Test Theme", description="A test theme")
        assert theme.name == "Test Theme"
        assert theme.description == "A test theme"
        assert len(theme.papers) == 0

    def test_theme_add_paper(self):
        """Test adding papers to a theme."""
        theme = Theme(name="AI", description="AI research")
        paper = PaperData(
            paper_id="p1",
            title="AI Paper",
            authors=["Author"],
            year=2023,
            abstract=None,
        )
        theme.add_paper(paper)
        assert len(theme.papers) == 1
        assert theme.papers[0].paper_id == "p1"

    def test_theme_to_dict(self):
        """Test Theme to_dict method."""
        theme = Theme(name="ML", description="Machine Learning")
        paper = PaperData(
            paper_id="p1",
            title="ML Paper",
            authors=["Author"],
            year=2023,
            abstract=None,
        )
        theme.add_paper(paper)
        result = theme.to_dict()
        assert result["name"] == "ML"
        assert result["paper_count"] == 1
        assert "p1" in result["paper_ids"]


# ============================================================================
# SynthesisMatrix Tests
# ============================================================================


class TestSynthesisMatrix:
    """Tests for the SynthesisMatrix class."""

    def test_synthesis_matrix_creation(self):
        """Test creating a SynthesisMatrix."""
        matrix = SynthesisMatrix()
        assert len(matrix.themes) == 0
        assert len(matrix.papers) == 0

    def test_add_theme(self):
        """Test adding themes to matrix."""
        matrix = SynthesisMatrix()
        matrix.add_theme("Deep Learning")
        assert "Deep Learning" in matrix.themes

    def test_add_paper(self):
        """Test adding papers to matrix."""
        matrix = SynthesisMatrix()
        matrix.add_paper("paper-1")
        assert "paper-1" in matrix.papers

    def test_set_and_get_contribution(self):
        """Test setting and getting contributions."""
        matrix = SynthesisMatrix()
        matrix.set_contribution("paper-1", "NLP", "Novel NLP architecture")
        contribution = matrix.get_contribution("paper-1", "NLP")
        assert contribution == "Novel NLP architecture"

    def test_get_paper_contributions(self):
        """Test getting all contributions for a paper."""
        matrix = SynthesisMatrix()
        matrix.set_contribution("paper-1", "NLP", "NLP contribution")
        matrix.set_contribution("paper-1", "ML", "ML contribution")
        contributions = matrix.get_paper_contributions("paper-1")
        assert len(contributions) == 2
        assert contributions["NLP"] == "NLP contribution"

    def test_get_theme_contributions(self):
        """Test getting all contributions for a theme."""
        matrix = SynthesisMatrix()
        matrix.set_contribution("paper-1", "NLP", "Contribution 1")
        matrix.set_contribution("paper-2", "NLP", "Contribution 2")
        contributions = matrix.get_theme_contributions("NLP")
        assert len(contributions) == 2

    def test_synthesis_matrix_to_dict(self):
        """Test SynthesisMatrix to_dict method."""
        matrix = SynthesisMatrix()
        matrix.set_contribution("paper-1", "AI", "AI research")
        result = matrix.to_dict()
        assert isinstance(result, dict)
        assert "themes" in result
        assert "papers" in result
        assert "matrix" in result
        assert "AI" in result["themes"]


# ============================================================================
# LiteratureReviewSkill Tests
# ============================================================================


class TestLiteratureReviewSkillBasics:
    """Basic tests for LiteratureReviewSkill."""

    def test_skill_attributes(self, skill: LiteratureReviewSkill):
        """Test skill has correct attributes."""
        assert skill.name == "literature-review"
        assert "literature" in skill.description.lower()
        assert skill.version == "1.0.0"

    def test_skill_repr(self, skill: LiteratureReviewSkill):
        """Test skill string representation."""
        repr_str = repr(skill)
        assert "LiteratureReviewSkill" in repr_str
        assert "literature-review" in repr_str

    def test_skill_validation_valid_input(self, skill: LiteratureReviewSkill):
        """Test validation with valid input."""
        input_data = SkillInput(
            workspace_id="ws",
            user_query="query",
        )
        result = skill.validate_input(input_data)
        assert result is None

    def test_skill_validation_empty_workspace(self, skill: LiteratureReviewSkill):
        """Test validation with empty workspace."""
        input_data = SkillInput(workspace_id="", user_query="query")
        result = skill.validate_input(input_data)
        assert result == "workspace_id is required"


class TestLiteratureReviewSkillExecution:
    """Tests for skill execution."""

    def test_execute_with_papers(
        self,
        skill: LiteratureReviewSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test successful execution with papers."""
        output = skill.execute(skill_input, thread_state)
        assert output.success is True
        assert output.content != ""
        assert len(output.artifacts) == 1
        assert output.metadata["paper_count"] == 3

    def test_execute_without_papers(
        self,
        skill: LiteratureReviewSkill,
        thread_state: ThreadState,
    ):
        """Test execution without papers returns failure."""
        input_data = SkillInput(
            workspace_id="empty-workspace",
            user_query="What research exists?",
            context={},
        )
        output = skill.execute(input_data, thread_state)
        assert output.success is False
        assert "No papers" in output.error_message

    def test_execute_creates_artifact(
        self,
        skill: LiteratureReviewSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test that execution creates a literature review artifact."""
        output = skill.execute(skill_input, thread_state)
        artifact = output.artifacts[0]
        assert artifact.type == "literature_review"
        assert artifact.workspace_id == "test-workspace"
        assert artifact.created_by_skill == "literature-review"
        assert "review" in artifact.content

    def test_execute_metadata(
        self,
        skill: LiteratureReviewSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test execution produces correct metadata."""
        output = skill.execute(skill_input, thread_state)
        assert "paper_count" in output.metadata
        assert "theme_count" in output.metadata
        assert "generated_at" in output.metadata


class TestLiteratureReviewContent:
    """Tests for literature review content generation."""

    def test_review_has_introduction(
        self,
        skill: LiteratureReviewSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test that review contains introduction section."""
        output = skill.execute(skill_input, thread_state)
        assert "# Literature Review" in output.content
        assert "## Introduction" in output.content

    def test_review_has_themes(
        self,
        skill: LiteratureReviewSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test that review contains theme sections."""
        output = skill.execute(skill_input, thread_state)
        # Should have multiple theme sections (## headings)
        assert output.content.count("## ") >= 3  # Introduction, themes, gaps, conclusion

    def test_review_has_research_gaps(
        self,
        skill: LiteratureReviewSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test that review contains research gaps section."""
        output = skill.execute(skill_input, thread_state)
        assert "## Research Gaps" in output.content

    def test_review_has_conclusion(
        self,
        skill: LiteratureReviewSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test that review contains conclusion section."""
        output = skill.execute(skill_input, thread_state)
        assert "## Conclusion" in output.content

    def test_review_includes_paper_titles(
        self,
        skill: LiteratureReviewSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test that review includes paper titles."""
        output = skill.execute(skill_input, thread_state)
        assert "Deep Learning for Natural Language Processing" in output.content


class TestPaperDataExtraction:
    """Tests for paper data extraction."""

    def test_convert_to_paper_data_full(
        self, skill: LiteratureReviewSkill, sample_paper: dict
    ):
        """Test converting full paper dictionary."""
        paper = skill._convert_to_paper_data(sample_paper)
        assert paper is not None
        assert paper.title == "Deep Learning for Natural Language Processing"
        assert len(paper.authors) == 2
        assert paper.year == 2023

    def test_convert_to_paper_data_minimal(self, skill: LiteratureReviewSkill):
        """Test converting minimal paper dictionary."""
        minimal_paper = {"title": "Minimal Paper"}
        paper = skill._convert_to_paper_data(minimal_paper)
        assert paper is not None
        assert paper.title == "Minimal Paper"
        assert paper.authors == []

    def test_convert_to_paper_data_none(self, skill: LiteratureReviewSkill):
        """Test converting None returns None."""
        paper = skill._convert_to_paper_data(None)
        assert paper is None

    def test_extract_authors_from_list_of_dicts(
        self, skill: LiteratureReviewSkill
    ):
        """Test extracting authors from list of dicts."""
        authors = [{"name": "John"}, {"name": "Jane"}]
        result = skill._extract_authors(authors)
        assert result == ["John", "Jane"]

    def test_extract_authors_from_list_of_strings(
        self, skill: LiteratureReviewSkill
    ):
        """Test extracting authors from list of strings."""
        authors = ["John", "Jane"]
        result = skill._extract_authors(authors)
        assert result == ["John", "Jane"]

    def test_extract_authors_from_string(self, skill: LiteratureReviewSkill):
        """Test extracting authors from comma-separated string."""
        authors = "John, Jane, Bob"
        result = skill._extract_authors(authors)
        assert result == ["John", "Jane", "Bob"]


class TestThemeExtraction:
    """Tests for theme extraction."""

    def test_extract_themes_from_papers(
        self, skill: LiteratureReviewSkill, sample_papers: list[dict]
    ):
        """Test extracting themes from papers."""
        papers = [skill._convert_to_paper_data(p) for p in sample_papers]
        themes = skill._extract_themes(papers)
        assert len(themes) > 0

    def test_extract_themes_uses_keywords(
        self, skill: LiteratureReviewSkill, sample_papers: list[dict]
    ):
        """Test that theme extraction uses paper keywords."""
        papers = [skill._convert_to_paper_data(p) for p in sample_papers]
        themes = skill._extract_themes(papers)
        # Should find common themes like "transformers"
        theme_names = [t.name.lower() for t in themes]
        assert any("transformer" in name for name in theme_names)

    def test_normalize_term(self, skill: LiteratureReviewSkill):
        """Test term normalization."""
        result = skill._normalize_term("  Machine Learning  ")
        assert result == "machine learning"

    def test_extract_terms_from_text(self, skill: LiteratureReviewSkill):
        """Test extracting terms from text."""
        text = "Deep learning and neural networks are powerful machine learning techniques."
        terms = skill._extract_terms_from_text(text)
        assert isinstance(terms, list)
        assert "learning" in terms  # Should appear multiple times


class TestSynthesisMatrixCreation:
    """Tests for synthesis matrix creation."""

    def test_create_synthesis_matrix(
        self,
        skill: LiteratureReviewSkill,
        sample_papers: list[dict],
    ):
        """Test creating synthesis matrix."""
        papers = [skill._convert_to_paper_data(p) for p in sample_papers]
        themes = skill._extract_themes(papers)
        matrix = skill._create_synthesis_matrix(papers, themes)
        assert len(matrix.papers) == 3
        assert len(matrix.themes) > 0

    def test_extract_contribution_from_explicit(
        self, skill: LiteratureReviewSkill
    ):
        """Test extracting contribution from explicit contributions."""
        paper = PaperData(
            paper_id="p1",
            title="Test",
            authors=["Author"],
            year=2023,
            abstract=None,
            contributions=["Novel method", "Better accuracy"],
        )
        theme = Theme(name="Test Theme")
        contribution = skill._extract_contribution(paper, theme)
        assert "Novel method" in contribution

    def test_extract_contribution_from_findings(
        self, skill: LiteratureReviewSkill
    ):
        """Test extracting contribution from findings."""
        paper = PaperData(
            paper_id="p1",
            title="Test",
            authors=["Author"],
            year=2023,
            abstract=None,
            findings=["Found X", "Found Y"],
        )
        theme = Theme(name="Test Theme")
        contribution = skill._extract_contribution(paper, theme)
        assert "Found X" in contribution

    def test_extract_contribution_from_abstract(
        self, skill: LiteratureReviewSkill
    ):
        """Test extracting contribution from abstract."""
        paper = PaperData(
            paper_id="p1",
            title="Test",
            authors=["Author"],
            year=2023,
            abstract="This paper presents a novel approach to solving the problem. We demonstrate improvements.",
        )
        theme = Theme(name="Test Theme")
        contribution = skill._extract_contribution(paper, theme)
        assert len(contribution) > 0


class TestArtifactCreation:
    """Tests for artifact creation."""

    def test_create_artifact(
        self,
        skill: LiteratureReviewSkill,
        sample_papers: list[dict],
    ):
        """Test creating literature review artifact."""
        papers = [skill._convert_to_paper_data(p) for p in sample_papers]
        themes = skill._extract_themes(papers)
        matrix = skill._create_synthesis_matrix(papers, themes)

        artifact = skill._create_artifact(
            workspace_id="test-ws",
            review_content="Test review content",
            themes=themes,
            synthesis_matrix=matrix,
        )

        assert artifact.type == "literature_review"
        assert artifact.workspace_id == "test-ws"
        assert artifact.created_by_skill == "literature-review"
        assert "review" in artifact.content
        assert "themes" in artifact.content
        assert "synthesis_matrix" in artifact.content


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_paper_list(self, skill: LiteratureReviewSkill):
        """Test handling empty paper list."""
        themes = skill._extract_themes([])
        assert themes == []

    def test_paper_with_no_keywords(self, skill: LiteratureReviewSkill):
        """Test paper with no keywords uses abstract."""
        paper = PaperData(
            paper_id="p1",
            title="Test Paper",
            authors=["Author"],
            year=2023,
            abstract="This paper discusses machine learning and deep learning approaches.",
            keywords=[],
        )
        themes = skill._extract_themes([paper])
        assert len(themes) >= 1  # Should create at least one theme from abstract

    def test_paper_with_no_abstract(self, skill: LiteratureReviewSkill):
        """Test paper with no abstract."""
        paper = PaperData(
            paper_id="p1",
            title="Test Paper",
            authors=["Author"],
            year=2023,
            abstract=None,
            keywords=["test"],
        )
        themes = skill._extract_themes([paper])
        assert len(themes) >= 1

    def test_papers_from_thread_state(
        self,
        skill: LiteratureReviewSkill,
        sample_papers: list[dict],
    ):
        """Test getting papers from thread state."""
        state = ThreadState(
            messages=[],
            workspace_id="test-ws",
            thread_data={"papers": sample_papers},
        )

        input_data = SkillInput(
            workspace_id="test-ws",
            user_query="Query",
            context={},  # No papers in context
        )

        papers = skill._get_papers(input_data, state)
        assert len(papers) == 3

    def test_unicode_in_paper_title(self, skill: LiteratureReviewSkill):
        """Test handling unicode in paper titles."""
        paper = {
            "id": "p1",
            "title": "机器学习研究",  # Chinese characters
            "authors": ["作者"],
            "year": 2023,
            "abstract": "This paper discusses machine learning.",
        }
        paper_data = skill._convert_to_paper_data(paper)
        assert paper_data is not None
        assert paper_data.title == "机器学习研究"

    def test_long_abstract_truncation(self, skill: LiteratureReviewSkill):
        """Test that long abstracts are handled."""
        long_abstract = "A" * 500
        paper = PaperData(
            paper_id="p1",
            title="Test",
            authors=["Author"],
            year=2023,
            abstract=long_abstract,
        )
        theme = Theme(name="Test")
        contribution = skill._extract_contribution(paper, theme)
        assert len(contribution) <= 203  # 200 chars + "..."

    def test_many_authors_truncation(self, skill: LiteratureReviewSkill):
        """Test handling papers with many authors."""
        papers = [{
            "id": "p1",
            "title": "Multi-author Paper",
            "authors": [f"Author {i}" for i in range(10)],
            "year": 2023,
            "abstract": "Test abstract",
        }]
        input_data = SkillInput(
            workspace_id="ws",
            user_query="Query",
            context={"papers": papers},
        )
        state = ThreadState(messages=[], workspace_id="ws")
        output = skill.execute(input_data, state)
        # Should handle many authors gracefully
        assert output.success is True
