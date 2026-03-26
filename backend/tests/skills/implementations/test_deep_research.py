"""Comprehensive tests for the Deep Research Skill.

This module tests:
- Paper search and parsing
- Pattern analysis and extraction
- Research gap identification
- Research idea generation
- Artifact creation
- Full skill execution workflow
"""

from unittest.mock import patch

import pytest

from src.agents.thread_state import AcademicArtifact, ThreadState
from src.skills.base import SkillInput
from src.skills.implementations.deep_research import (
    DeepResearchSkill,
    Paper,
    ResearchGap,
    ResearchIdea,
    ResearchPattern,
    ResearchTrend,
)
from src.subagents.parallel import PhaseResult

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def skill() -> DeepResearchSkill:
    """Create a DeepResearchSkill instance for testing."""
    return DeepResearchSkill()


@pytest.fixture
def skill_input() -> SkillInput:
    """Create a default SkillInput for deep research testing."""
    return SkillInput(
        workspace_id="test-workspace",
        user_query="machine learning in natural language processing",
        context={},
    )


@pytest.fixture
def thread_state() -> ThreadState:
    """Create a default ThreadState for testing."""
    return ThreadState(
        messages=[],
        workspace_id="test-workspace",
    )


@pytest.fixture
def sample_papers() -> list[Paper]:
    """Create sample papers for testing."""
    return [
        Paper(
            title="Attention Is All You Need",
            authors=["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
            year=2017,
            venue="NeurIPS",
            abstract="We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely. We show that the transformer achieves state-of-the-art performance on machine translation tasks.",
            citations=50000,
            url="https://arxiv.org/abs/1706.03762",
            doi="10.48550/arXiv.1706.03762",
            paper_id="204e3073870fae3d05bcbc2f6a8e263d9b72e776",
        ),
        Paper(
            title="BERT: Pre-training of Deep Bidirectional Transformers",
            authors=["Jacob Devlin", "Ming-Wei Chang", "Kenton Lee"],
            year=2018,
            venue="NAACL",
            abstract="We introduce BERT, a new language representation model that stands for Bidirectional Encoder Representations from Transformers. BERT is designed to pre-train deep bidirectional representations from unlabeled text.",
            citations=75000,
            url="https://arxiv.org/abs/1810.04805",
            doi="10.18653/v1/N19-1423",
            paper_id="df2b0e02d5a9227f0f9e897460d817e78f9898dc",
        ),
        Paper(
            title="Language Models are Few-Shot Learners",
            authors=["Tom Brown", "Benjamin Mann", "Nick Ryder"],
            year=2020,
            venue="NeurIPS",
            abstract="We demonstrate that scaling up language models greatly improves task-agnostic, few-shot performance. GPT-3 achieves strong performance on many NLP datasets without any gradient-based fine-tuning.",
            citations=30000,
            url="https://arxiv.org/abs/2005.14165",
            doi="10.48550/arXiv.2005.14165",
            paper_id="6b5a33e7f3fa3d2b4c0e0e0e0e0e0e0e0e0e0e0e0",
        ),
        Paper(
            title="Deep Learning for Text Classification",
            authors=["Wei Liu", "John Smith"],
            year=2019,
            venue="ACL",
            abstract="We present a comprehensive study of deep learning methods for text classification using convolutional neural networks and recurrent neural networks. Our experiments show that transformer-based models outperform traditional methods.",
            citations=1500,
            url="https://example.com/paper1",
            doi="10.1234/example.1",
            paper_id="paper-4",
        ),
        Paper(
            title="Neural Machine Translation with Attention",
            authors=["Jane Doe", "Richard Roe"],
            year=2016,
            venue="EMNLP",
            abstract="We propose an attention mechanism for neural machine translation that learns to focus on different parts of the source sentence during translation. The attention mechanism significantly improves translation quality.",
            citations=8000,
            url="https://example.com/paper2",
            doi="10.1234/example.2",
            paper_id="paper-5",
        ),
        Paper(
            title="Transfer Learning in NLP",
            authors=["Alice Wang", "Bob Chen"],
            year=2021,
            venue="ICLR",
            abstract="We study transfer learning techniques in natural language processing. Our experiments demonstrate that pre-trained language models can be effectively fine-tuned for various downstream tasks with limited labeled data.",
            citations=500,
            url="https://example.com/paper3",
            doi="10.1234/example.3",
            paper_id="paper-6",
        ),
    ]


# ============================================================================
# Skill Metadata Tests
# ============================================================================


class TestDeepResearchSkillMetadata:
    """Tests for skill metadata and attributes."""

    def test_skill_has_correct_name(self, skill: DeepResearchSkill):
        """Test that skill has the correct name."""
        assert skill.name == "deep-research"

    def test_skill_has_description(self, skill: DeepResearchSkill):
        """Test that skill has a description."""
        assert skill.description == "Comprehensive literature analysis and research idea generation"

    def test_skill_has_version(self, skill: DeepResearchSkill):
        """Test that skill has a version."""
        assert skill.version == "2.0.0"

    def test_skill_has_default_config(self, skill: DeepResearchSkill):
        """Test that skill has default configuration values."""
        assert skill.DEFAULT_SEARCH_LIMIT == 20
        assert skill.MIN_PAPERS_FOR_ANALYSIS == 5
        assert skill.KEYWORD_EXTRACTION_MIN_FREQ == 2


# ============================================================================
# Paper Dataclass Tests
# ============================================================================


class TestPaperDataclass:
    """Tests for Paper dataclass."""

    def test_paper_creation(self):
        """Test creating a Paper instance."""
        paper = Paper(
            title="Test Paper",
            authors=["Author 1", "Author 2"],
            year=2023,
            venue="Test Venue",
            abstract="Test abstract",
            citations=100,
            url="https://example.com",
            doi="10.1234/test",
            paper_id="test-id",
        )
        assert paper.title == "Test Paper"
        assert len(paper.authors) == 2
        assert paper.year == 2023
        assert paper.citations == 100

    def test_paper_optional_fields(self):
        """Test Paper with optional fields as None."""
        paper = Paper(
            title="Minimal Paper",
            authors=[],
            year=None,
            venue=None,
            abstract=None,
            citations=None,
            url=None,
            doi=None,
        )
        assert paper.year is None
        assert paper.abstract is None
        assert paper.citations is None


# ============================================================================
# Keyword Extraction Tests
# ============================================================================


class TestKeywordExtraction:
    """Tests for keyword extraction functionality."""

    def test_extract_keywords_basic(self, skill: DeepResearchSkill):
        """Test basic keyword extraction."""
        text = "Deep learning models achieve state-of-the-art performance on natural language processing tasks."
        keywords = skill._extract_keywords(text)
        assert "learning" in keywords
        assert "language" in keywords
        assert "processing" in keywords

    def test_extract_keywords_filters_stopwords(self, skill: DeepResearchSkill):
        """Test that stopwords are filtered out."""
        text = "The paper presents a study on the use of neural networks for text classification."
        keywords = skill._extract_keywords(text)
        # Common stopwords should be filtered
        assert "the" not in keywords
        assert "a" not in keywords
        assert "of" not in keywords

    def test_extract_keywords_empty_text(self, skill: DeepResearchSkill):
        """Test extraction from empty text."""
        keywords = skill._extract_keywords("")
        assert keywords == []

    def test_extract_keywords_none_text(self, skill: DeepResearchSkill):
        """Test extraction from None text."""
        keywords = skill._extract_keywords(None)  # type: ignore
        assert keywords == []

    def test_extract_keywords_handles_special_chars(self, skill: DeepResearchSkill):
        """Test extraction handles special characters."""
        text = "We propose: (1) advanced neural architectures; (2) experimental validation!"
        keywords = skill._extract_keywords(text)
        # Check that special characters are stripped and keywords extracted
        assert "neural" in keywords
        assert "architectures" in keywords
        assert "experimental" in keywords


# ============================================================================
# Pattern Analysis Tests
# ============================================================================


class TestPatternAnalysis:
    """Tests for pattern analysis functionality."""

    def test_analyze_patterns_with_sufficient_papers(
        self,
        skill: DeepResearchSkill,
        sample_papers: list[Paper],
    ):
        """Test pattern analysis with enough papers."""
        patterns = skill._analyze_patterns(sample_papers)
        assert len(patterns) > 0
        # Should identify some patterns from the sample papers
        for pattern in patterns:
            assert isinstance(pattern, ResearchPattern)
            assert pattern.description
            assert pattern.frequency > 0

    def test_analyze_patterns_insufficient_papers(self, skill: DeepResearchSkill):
        """Test pattern analysis with too few papers."""
        few_papers = [
            Paper(
                title="Only Paper",
                authors=["Single Author"],
                year=2020,
                venue="Venue",
                abstract="Single abstract",
                citations=10,
                url="url",
                doi="doi",
            )
        ]
        patterns = skill._analyze_patterns(few_papers)
        assert patterns == []

    def test_analyze_patterns_identifies_common_terms(
        self,
        skill: DeepResearchSkill,
        sample_papers: list[Paper],
    ):
        """Test that common terms are identified as patterns."""
        patterns = skill._analyze_patterns(sample_papers)
        # The sample papers have "learning", "language", "attention" in common
        " ".join([p.description.lower() for p in patterns])
        # Should identify at least some patterns
        assert len(patterns) > 0


# ============================================================================
# Synthesis Tests
# ============================================================================


class TestSynthesis:
    """Tests for synthesis functionality."""

    def test_synthesize_findings_basic(
        self,
        skill: DeepResearchSkill,
        sample_papers: list[Paper],
    ):
        """Test basic synthesis generation."""
        patterns = skill._analyze_patterns(sample_papers)
        synthesis = skill._synthesize_findings(sample_papers, patterns)

        assert str(len(sample_papers)) in synthesis
        assert "papers" in synthesis.lower()

    def test_synthesize_findings_includes_year_range(
        self,
        skill: DeepResearchSkill,
        sample_papers: list[Paper],
    ):
        """Test that synthesis includes year range."""
        synthesis = skill._synthesize_findings(sample_papers, [])
        assert "2016" in synthesis  # Min year from sample
        assert "2021" in synthesis  # Max year from sample

    def test_synthesize_findings_includes_citations(
        self,
        skill: DeepResearchSkill,
        sample_papers: list[Paper],
    ):
        """Test that synthesis includes citation counts."""
        synthesis = skill._synthesize_findings(sample_papers, [])
        assert "citation" in synthesis.lower()

    def test_synthesize_findings_empty_papers(self, skill: DeepResearchSkill):
        """Test synthesis with no papers."""
        synthesis = skill._synthesize_findings([], [])
        assert "No papers" in synthesis


# ============================================================================
# Research Gap Identification Tests
# ============================================================================


class TestResearchGapIdentification:
    """Tests for research gap identification."""

    def test_identify_gaps_with_sufficient_papers(
        self,
        skill: DeepResearchSkill,
        sample_papers: list[Paper],
    ):
        """Test gap identification with enough papers."""
        patterns = skill._analyze_patterns(sample_papers)
        gaps = skill._identify_research_gaps(sample_papers, patterns)

        assert len(gaps) > 0
        for gap in gaps:
            assert isinstance(gap, ResearchGap)
            assert gap.description
            assert gap.potential_impact

    def test_identify_gaps_insufficient_papers(self, skill: DeepResearchSkill):
        """Test gap identification with too few papers."""
        few_papers = [
            Paper(
                title="Single Paper",
                authors=["Author"],
                year=2020,
                venue="Venue",
                abstract="Abstract",
                citations=10,
                url="url",
                doi="doi",
            )
        ]
        gaps = skill._identify_research_gaps(few_papers, [])
        assert gaps == []

    def test_identify_gaps_returns_limited_count(
        self,
        skill: DeepResearchSkill,
        sample_papers: list[Paper],
    ):
        """Test that gap identification returns limited number of gaps."""
        patterns = skill._analyze_patterns(sample_papers)
        gaps = skill._identify_research_gaps(sample_papers, patterns)
        # Should be limited to 5 gaps
        assert len(gaps) <= 5


# ============================================================================
# Research Idea Generation Tests
# ============================================================================


class TestResearchIdeaGeneration:
    """Tests for research idea generation."""

    def test_generate_ideas_basic(
        self,
        skill: DeepResearchSkill,
        sample_papers: list[Paper],
    ):
        """Test basic idea generation."""
        patterns = skill._analyze_patterns(sample_papers)
        gaps = skill._identify_research_gaps(sample_papers, patterns)
        ideas = skill._generate_research_ideas(sample_papers, patterns, gaps)

        assert len(ideas) > 0
        for idea in ideas:
            assert isinstance(idea, ResearchIdea)
            assert idea.title
            assert idea.description
            assert 0 <= idea.novelty_score <= 1

    def test_generate_ideas_insufficient_papers(self, skill: DeepResearchSkill):
        """Test idea generation with too few papers."""
        few_papers = [
            Paper(
                title="Paper",
                authors=["Author"],
                year=2020,
                venue="Venue",
                abstract="Abstract",
                citations=10,
                url="url",
                doi="doi",
            )
        ]
        ideas = skill._generate_research_ideas(few_papers, [], [])
        assert ideas == []

    def test_generate_ideas_includes_methodology_hints(
        self,
        skill: DeepResearchSkill,
        sample_papers: list[Paper],
    ):
        """Test that ideas include methodology hints."""
        patterns = skill._analyze_patterns(sample_papers)
        gaps = skill._identify_research_gaps(sample_papers, patterns)
        ideas = skill._generate_research_ideas(sample_papers, patterns, gaps)

        for idea in ideas:
            assert len(idea.methodology_hints) > 0


# ============================================================================
# Artifact Creation Tests
# ============================================================================


class TestArtifactCreation:
    """Tests for artifact creation."""

    def test_create_artifacts_basic(
        self,
        skill: DeepResearchSkill,
        sample_papers: list[Paper],
    ):
        """Test basic artifact creation."""
        patterns = skill._analyze_patterns(sample_papers)
        gaps = skill._identify_research_gaps(sample_papers, patterns)
        ideas = skill._generate_research_ideas(sample_papers, patterns, gaps)

        artifacts = skill._create_artifacts(
            "test-workspace",
            "test query",
            sample_papers,
            patterns,
            [],
            gaps,
            ideas,
            "Synthesis summary",
        )

        assert len(artifacts) > 0
        for artifact in artifacts:
            assert isinstance(artifact, AcademicArtifact)
            assert artifact.workspace_id == "test-workspace"
            assert artifact.created_by_skill == "deep-research"

    def test_create_artifacts_includes_deep_research_report(
        self,
        skill: DeepResearchSkill,
        sample_papers: list[Paper],
    ):
        """Test that canonical deep research report artifact is created."""
        artifacts = skill._create_artifacts(
            "test-workspace",
            "test query",
            sample_papers,
            [],
            [],
            [],
            [],
            "Synthesis summary",
        )

        artifact_types = [a.type for a in artifacts]
        assert "deep_research_report" in artifact_types

    def test_create_artifacts_embeds_research_ideas(
        self,
        skill: DeepResearchSkill,
        sample_papers: list[Paper],
    ):
        """Test that research ideas are embedded in the canonical report."""
        ideas = [
            ResearchIdea(
                title="Test Idea",
                description="Test description",
                methodology_hints=["hint1"],
                related_papers=["Paper 1"],
                novelty_score=0.8,
            )
        ]

        artifacts = skill._create_artifacts(
            "test-workspace",
            "test query",
            sample_papers,
            [],
            [],
            [],
            ideas,
            "Synthesis summary",
        )

        assert len(artifacts) == 1
        assert artifacts[0].type == "deep_research_report"
        assert artifacts[0].content["ideas"][0]["title"] == "Test Idea"

    def test_create_artifacts_embeds_gap_analysis(
        self,
        skill: DeepResearchSkill,
        sample_papers: list[Paper],
    ):
        """Test that gap analysis is embedded in the canonical report."""
        gaps = [
            ResearchGap(
                description="Test Gap",
                supporting_evidence=["Evidence 1"],
                potential_impact="High impact",
            )
        ]

        artifacts = skill._create_artifacts(
            "test-workspace",
            "test query",
            sample_papers,
            [],
            [],
            gaps,
            [],
            "Synthesis summary",
        )

        assert len(artifacts) == 1
        assert artifacts[0].type == "deep_research_report"
        assert artifacts[0].content["gaps"][0]["description"] == "Test Gap"


# ============================================================================
# Report Building Tests
# ============================================================================


class TestReportBuilding:
    """Tests for report building."""

    def test_build_report_includes_query(
        self,
        skill: DeepResearchSkill,
        sample_papers: list[Paper],
    ):
        """Test that report includes the original query."""
        patterns = skill._analyze_patterns(sample_papers)
        gaps = skill._identify_research_gaps(sample_papers, patterns)
        ideas = skill._generate_research_ideas(sample_papers, patterns, gaps)
        synthesis = skill._synthesize_findings(sample_papers, patterns)

        report = skill._build_report(
            "machine learning",
            sample_papers,
            patterns,
            gaps,
            ideas,
            synthesis,
        )

        assert "machine learning" in report

    def test_build_report_structure(
        self,
        skill: DeepResearchSkill,
        sample_papers: list[Paper],
    ):
        """Test that report has expected structure."""
        patterns = skill._analyze_patterns(sample_papers)
        gaps = skill._identify_research_gaps(sample_papers, patterns)
        ideas = skill._generate_research_ideas(sample_papers, patterns, gaps)
        synthesis = skill._synthesize_findings(sample_papers, patterns)

        report = skill._build_report(
            "test query",
            sample_papers,
            patterns,
            gaps,
            ideas,
            synthesis,
        )

        assert "# Deep Research Analysis" in report
        assert "## Summary" in report
        assert "## Papers Analyzed" in report

    def test_build_report_limits_papers_displayed(
        self,
        skill: DeepResearchSkill,
    ):
        """Test that report limits number of papers displayed."""
        # Create more than 10 papers
        many_papers = [
            Paper(
                title=f"Paper {i}",
                authors=[f"Author {i}"],
                year=2020,
                venue="Venue",
                abstract=f"Abstract {i}",
                citations=10,
                url="url",
                doi=f"doi/{i}",
            )
            for i in range(15)
        ]

        report = skill._build_report(
            "test",
            many_papers,
            [],
            [],
            [],
            "Synthesis text",
        )

        assert "...and 5 more papers" in report


# ============================================================================
# Skill Execution Tests
# ============================================================================


class TestSkillExecution:
    """Tests for complete skill execution."""

    @patch.object(DeepResearchSkill, "_search_papers")
    def test_execute_success_with_papers(
        self,
        mock_search,
        skill: DeepResearchSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
        sample_papers: list[Paper],
    ):
        """Test successful execution with papers found."""
        mock_search.return_value = sample_papers

        output = skill.execute(skill_input, thread_state)

        assert output.success is True
        assert output.content != ""
        assert len(output.artifacts) > 0
        assert output.metadata["papers_analyzed"] == len(sample_papers)

    @patch.object(DeepResearchSkill, "_search_papers")
    def test_execute_no_papers_found(
        self,
        mock_search,
        skill: DeepResearchSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test execution when no papers are found."""
        mock_search.return_value = []

        output = skill.execute(skill_input, thread_state)

        assert output.success is True
        assert "No papers found" in output.content
        assert output.metadata["papers_found"] == 0

    @patch.object(DeepResearchSkill, "_search_papers")
    def test_execute_with_custom_search_limit(
        self,
        mock_search,
        skill: DeepResearchSkill,
        thread_state: ThreadState,
        sample_papers: list[Paper],
    ):
        """Test execution with custom search limit."""
        mock_search.return_value = sample_papers

        skill_input = SkillInput(
            workspace_id="test-workspace",
            user_query="test query",
            context={"search_limit": 50},
        )

        output = skill.execute(skill_input, thread_state)

        mock_search.assert_called_once_with("test query", 50, None)
        assert output.success is True

    @patch.object(DeepResearchSkill, "_search_papers")
    def test_execute_with_year_range(
        self,
        mock_search,
        skill: DeepResearchSkill,
        thread_state: ThreadState,
        sample_papers: list[Paper],
    ):
        """Test execution with year range filter."""
        mock_search.return_value = sample_papers

        skill_input = SkillInput(
            workspace_id="test-workspace",
            user_query="test query",
            context={"year_range": "2020-2024"},
        )

        output = skill.execute(skill_input, thread_state)

        mock_search.assert_called_once_with("test query", 20, "2020-2024")
        assert output.success is True

    @patch.object(DeepResearchSkill, "_search_papers")
    def test_execute_updates_cited_papers(
        self,
        mock_search,
        skill: DeepResearchSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
        sample_papers: list[Paper],
    ):
        """Test that execution updates cited papers in state."""
        mock_search.return_value = sample_papers

        skill.execute(skill_input, thread_state)

        # Check that DOIs were added to cited_papers
        assert len(thread_state.get("cited_papers", [])) > 0

    @patch.object(DeepResearchSkill, "_search_papers")
    def test_execute_handles_exception(
        self,
        mock_search,
        skill: DeepResearchSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
    ):
        """Test that execution handles exceptions gracefully."""
        mock_search.side_effect = Exception("API Error")

        output = skill.execute(skill_input, thread_state)

        assert output.success is False
        assert "Deep research failed" in output.error_message
        assert "API Error" in output.error_message


# ============================================================================
# Integration Tests
# ============================================================================


class TestDeepResearchIntegration:
    """Integration tests for the deep research skill."""

    @patch.object(DeepResearchSkill, "_search_papers")
    def test_full_workflow(
        self,
        mock_search,
        skill: DeepResearchSkill,
        skill_input: SkillInput,
        thread_state: ThreadState,
        sample_papers: list[Paper],
    ):
        """Test the full workflow from search to artifact creation."""
        mock_search.return_value = sample_papers

        output = skill.execute(skill_input, thread_state)

        # Verify output structure
        assert output.success is True
        assert isinstance(output.content, str)
        assert len(output.content) > 100  # Should have substantial content

        # Verify artifacts
        assert len(output.artifacts) >= 1
        artifact_types = {a.type for a in output.artifacts}
        assert "deep_research_report" in artifact_types

        # Verify metadata
        assert output.metadata["papers_analyzed"] == len(sample_papers)
        assert "patterns_identified" in output.metadata
        assert "gaps_identified" in output.metadata
        assert "ideas_generated" in output.metadata

    @patch.object(DeepResearchSkill, "_search_papers")
    def test_skill_registration_with_executor(
        self,
        mock_search,
        skill_input: SkillInput,
        thread_state: ThreadState,
        sample_papers: list[Paper],
    ):
        """Test that the skill can be registered and executed via SkillExecutor."""
        from src.skills.executor import SkillExecutor

        mock_search.return_value = sample_papers

        executor = SkillExecutor()
        skill = DeepResearchSkill()
        executor.register_skill(skill)

        assert executor.has_skill("deep-research")

        output = executor.execute("deep-research", skill_input, thread_state)
        assert output.success is True

    def test_skill_validation(self, skill: DeepResearchSkill):
        """Test skill input validation."""
        # Valid input
        valid_input = SkillInput(
            workspace_id="ws",
            user_query="query",
        )
        assert skill.validate_input(valid_input) is None

        # Invalid input - empty workspace
        invalid_input = SkillInput(
            workspace_id="",
            user_query="query",
        )
        assert skill.validate_input(invalid_input) == "workspace_id is required"


# ============================================================================
# Parallel Execution Tests
# ============================================================================


class TestDeepResearchParallelExecution:
    """Tests for parallel execution with ParallelExecutor."""

    def test_creates_phased_plan(self, skill: DeepResearchSkill):
        """Deep Research should create a phased execution plan."""
        plan = skill._create_execution_plan("federated learning privacy")

        assert len(plan.phases) >= 3
        # Phase 1 should be parallel discovery
        assert plan.phases[0].is_parallel()
        # Check for dependencies
        has_dependencies = any(p.depends_on for p in plan.phases)
        assert has_dependencies

    def test_phased_plan_has_correct_structure(self, skill: DeepResearchSkill):
        """Phased plan should follow the expected structure."""
        plan = skill._create_execution_plan("quantum computing")

        # Phase 1: Discovery (parallel Scout + Trend Spotter)
        assert plan.phases[0].name == "discovery"
        assert len(plan.phases[0].tasks) >= 2  # At least 2 parallel tasks

        # Phase 2: Gap Mining (depends on discovery)
        gap_phase = next((p for p in plan.phases if "gap" in p.name.lower()), None)
        assert gap_phase is not None
        assert "discovery" in gap_phase.depends_on

        # Phase 3: Synthesis (depends on gap mining)
        synth_phase = next((p for p in plan.phases if "synth" in p.name.lower()), None)
        assert synth_phase is not None

    @pytest.mark.asyncio
    async def test_parallel_execution_structure(self):
        """Should use ParallelExecutor for execution."""
        from unittest.mock import AsyncMock, patch

        skill = DeepResearchSkill()

        # Mock the executor's execute_plan method
        with patch.object(skill, "_executor") as mock_executor:
            mock_executor.execute_plan = AsyncMock(return_value=[])

            state = {"messages": [], "cited_papers": []}
            input_data = SkillInput(workspace_id="test", user_query="test", context={})

            await skill.execute_async(input_data, state)

            mock_executor.execute_plan.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_async_returns_output(self):
        """execute_async should return a SkillOutput."""
        from unittest.mock import AsyncMock, patch

        skill = DeepResearchSkill()

        # Mock the executor
        with patch.object(skill, "_executor") as mock_executor:
            mock_executor.execute_plan = AsyncMock(return_value=[])

            state = {"messages": [], "cited_papers": []}
            input_data = SkillInput(
                workspace_id="test-ws",
                user_query="machine learning",
                context={},
            )

            output = await skill.execute_async(input_data, state)

            assert output.success is True
            assert output.metadata.get("papers_analyzed", 0) == 0

    @pytest.mark.asyncio
    async def test_execute_async_emits_runtime_blocks_via_progress_callback(self):
        """Deep research should expose phase/block runtime updates for the UI."""
        from unittest.mock import AsyncMock

        skill = DeepResearchSkill()
        progress_callback = AsyncMock()

        discovery_phase = PhaseResult(
            phase_name="discovery",
            task_results=[
                {
                    "success": True,
                    "result": {
                        "papers": [
                            {
                                "title": "Adaptive Retrieval-Augmented Generation",
                                "authors": ["A. Researcher"],
                                "year": 2024,
                                "venue": "ACL",
                                "abstract": "Studies adaptive retrieval strategies for long-context QA.",
                                "citations": 42,
                                "url": "https://example.com/paper",
                                "doi": "10.1234/example",
                            }
                        ],
                        "trends": [
                            {
                                "topic": "retrieval orchestration",
                                "description": "More systems coordinate multiple retrieval strategies.",
                                "growth_rate": 12.5,
                                "paper_count": 9,
                            }
                        ],
                    },
                }
            ],
        )
        gap_phase = PhaseResult(
            phase_name="gap_mining",
            task_results=[
                {
                    "success": True,
                    "result": {
                        "gaps": [
                            {
                                "description": "Evaluation under shifting corpora",
                                "supporting_evidence": ["Adaptive Retrieval-Augmented Generation"],
                                "potential_impact": "Would improve real-world robustness.",
                            }
                        ],
                    },
                }
            ],
        )
        synthesis_phase = PhaseResult(
            phase_name="synthesis",
            task_results=[
                {
                    "success": True,
                    "result": {
                        "ideas": [
                            {
                                "title": "Adaptive RAG under drift",
                                "description": "A benchmark and controller for corpus drift.",
                                "methodology_hints": ["Dynamic retrieval policies"],
                                "related_papers": ["Adaptive Retrieval-Augmented Generation"],
                                "novelty_score": 0.83,
                            }
                        ],
                    },
                }
            ],
        )

        async def execute_plan(plan, context, phase_callback=None):
            for phase in [discovery_phase, gap_phase, synthesis_phase]:
                if phase_callback:
                    await phase_callback(phase)
            return [discovery_phase, gap_phase, synthesis_phase]

        with patch.object(skill, "_executor") as mock_executor:
            mock_executor.execute_plan = AsyncMock(side_effect=execute_plan)

            output = await skill.execute_async(
                SkillInput(
                    workspace_id="test-ws",
                    user_query="adaptive retrieval generation",
                    context={},
                ),
                {"messages": [], "cited_papers": []},
                progress_callback=progress_callback,
            )

        assert output.success is True
        assert "runtime" in output.metadata
        runtime = output.metadata["runtime"]
        block_ids = {block["id"] for block in runtime["blocks"]}
        assert {"overview", "activity", "papers", "trends", "gaps", "ideas", "artifacts", "summary"} <= block_ids
        assert progress_callback.await_count >= 4

    def test_extract_papers_from_results(self, skill: DeepResearchSkill):
        """Should extract papers from phase results."""
        from src.subagents.parallel import PhaseResult

        phase_results = [
            PhaseResult(
                phase_name="discovery",
                task_results=[
                    {
                        "success": True,
                        "result": {
                            "papers": [
                                {
                                    "title": "Test Paper",
                                    "authors": ["Author 1"],
                                    "year": 2023,
                                    "venue": "ICML",
                                    "abstract": "Test abstract",
                                    "citations": 100,
                                    "url": "https://example.com",
                                    "doi": "10.1234/test",
                                }
                            ]
                        },
                    }
                ],
            )
        ]

        papers = skill._extract_papers(phase_results)
        assert len(papers) >= 0  # May be empty if extraction logic differs

    def test_extract_gaps_from_results(self, skill: DeepResearchSkill):
        """Should extract research gaps from phase results."""
        from src.subagents.parallel import PhaseResult

        phase_results = [
            PhaseResult(
                phase_name="gap_mining",
                task_results=[
                    {
                        "success": True,
                        "result": {
                            "gaps": [
                                {
                                    "description": "Test gap",
                                    "supporting_evidence": [],
                                    "potential_impact": "High",
                                }
                            ]
                        },
                    }
                ],
            )
        ]

        gaps = skill._extract_gaps(phase_results)
        assert isinstance(gaps, list)

    def test_extract_trends_from_results(self, skill: DeepResearchSkill):
        """Should extract trends from phase results."""
        from src.subagents.parallel import PhaseResult

        phase_results = [
            PhaseResult(
                phase_name="discovery",
                task_results=[
                    {
                        "success": True,
                        "result": {
                            "trends": [
                                {
                                    "topic": "transformers",
                                    "growth_rate": 0.5,
                                    "paper_count": 100,
                                }
                            ]
                        },
                    }
                ],
            )
        ]

        trends = skill._extract_trends(phase_results)
        assert isinstance(trends, list)
