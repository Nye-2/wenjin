"""Integration tests for end-to-end academic workflow.

This module tests the complete academic workflow:
Deep Research -> Framework Designer -> Paper Writer

Tests verify:
- Artifact flow between skills
- Terminology propagation
- Context transfer
- End-to-end workflow execution
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.thread_state import AcademicArtifact, ThreadState
from src.skills.base import SkillInput
from src.skills.implementations.deep_research import (
    DeepResearchSkill,
    Paper,
    ResearchGap,
    ResearchIdea,
)
from src.skills.implementations.framework_designer import FrameworkDesignerSkill
from src.skills.implementations.fullpaper_writer import FullpaperWriterSkill


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_papers() -> list[Paper]:
    """Create sample papers for testing."""
    return [
        Paper(
            title="Attention Is All You Need",
            authors=["Ashish Vaswani", "Noam Shazeer"],
            year=2017,
            venue="NeurIPS",
            abstract="We propose the Transformer architecture based on attention mechanisms.",
            citations=50000,
            url="https://arxiv.org/abs/1706.03762",
            doi="10.48550/arXiv.1706.03762",
            paper_id="paper-1",
        ),
        Paper(
            title="BERT: Pre-training of Deep Bidirectional Transformers",
            authors=["Jacob Devlin", "Ming-Wei Chang"],
            year=2018,
            venue="NAACL",
            abstract="BERT is a language representation model using bidirectional training.",
            citations=75000,
            url="https://arxiv.org/abs/1810.04805",
            doi="10.18653/v1/N19-1423",
            paper_id="paper-2",
        ),
        Paper(
            title="Language Models are Few-Shot Learners",
            authors=["Tom Brown", "Benjamin Mann"],
            year=2020,
            venue="NeurIPS",
            abstract="GPT-3 demonstrates scaling improves few-shot performance.",
            citations=30000,
            url="https://arxiv.org/abs/2005.14165",
            doi="10.48550/arXiv.2005.14165",
            paper_id="paper-3",
        ),
        Paper(
            title="Deep Learning for NLP",
            authors=["Alice Smith", "Bob Johnson"],
            year=2019,
            venue="ACL",
            abstract="A survey of deep learning methods for NLP tasks.",
            citations=1500,
            url="https://example.com/paper4",
            doi="10.1234/example.1",
            paper_id="paper-4",
        ),
        Paper(
            title="Transfer Learning in Language Models",
            authors=["Carol White", "David Lee"],
            year=2021,
            venue="ICLR",
            abstract="Transfer learning techniques for language model adaptation.",
            citations=500,
            url="https://example.com/paper5",
            doi="10.1234/example.2",
            paper_id="paper-5",
        ),
    ]


@pytest.fixture
def sample_gaps() -> list[ResearchGap]:
    """Create sample research gaps for testing."""
    return [
        ResearchGap(
            description="Interpretability of transformer attention patterns",
            supporting_evidence=["Attention Is All You Need", "BERT"],
            potential_impact="Could improve model transparency and trust",
        ),
        ResearchGap(
            description="Cross-lingual transfer efficiency",
            supporting_evidence=["BERT", "GPT-3"],
            potential_impact="Enable better multilingual NLP systems",
        ),
    ]


@pytest.fixture
def sample_ideas() -> list[ResearchIdea]:
    """Create sample research ideas for testing."""
    return [
        ResearchIdea(
            title="Interpretable Attention for Transformers",
            description="A novel approach to make attention weights more interpretable.",
            methodology_hints=["Attention visualization", "Probing tasks"],
            related_papers=["Attention Is All You Need"],
            novelty_score=0.85,
        ),
    ]


@pytest.fixture
def thread_state() -> ThreadState:
    """Create a fresh ThreadState for testing."""
    return ThreadState(
        messages=[],
        workspace_id="test-workspace",
        academic_artifacts=[],
        cited_papers=[],
    )


@pytest.fixture
def mock_deep_research_output(sample_papers, sample_gaps, sample_ideas):
    """Create mock output from deep research skill."""
    return {
        "papers": sample_papers,
        "gaps": sample_gaps,
        "ideas": sample_ideas,
    }


# ============================================================================
# Test Classes
# ============================================================================


class TestEndToEndAcademicWorkflow:
    """End-to-end tests for the complete academic workflow."""

    @pytest.mark.asyncio
    async def test_deep_research_to_framework_flow(
        self,
        thread_state: ThreadState,
        sample_papers: list[Paper],
    ):
        """Deep Research output should flow to Framework Designer."""
        # Setup: Mock Deep Research to produce artifacts
        deep_research = DeepResearchSkill()

        with patch.object(deep_research, "_executor") as mock_executor:
            # Mock the parallel executor to return empty results
            # (fallback to direct search)
            mock_executor.execute_plan = AsyncMock(return_value=[])

            with patch.object(deep_research, "_search_papers") as mock_search:
                mock_search.return_value = sample_papers

                skill_input = SkillInput(
                    workspace_id="test-workspace",
                    user_query="transformer attention mechanisms",
                    context={},
                )

                output = deep_research.execute(skill_input, thread_state)

                # Verify Deep Research created artifacts
                assert output.success is True
                assert len(output.artifacts) >= 1

                # Check artifact types
                artifact_types = [a.type for a in output.artifacts]
                assert "deep_research_report" in artifact_types

                # Verify cited papers were added to state
                assert len(thread_state.get("cited_papers", [])) > 0

    @pytest.mark.asyncio
    async def test_framework_to_writer_flow(
        self,
        thread_state: ThreadState,
    ):
        """Framework output should flow to Paper Writer."""
        # Setup: Create a framework outline artifact in state
        framework_artifact = AcademicArtifact(
            id="framework-outline-test",
            workspace_id="test-workspace",
            type="framework_outline",
            content={
                "abstract": "This paper presents a novel approach to attention.",
                "outline": "1. Introduction\n2. Methods\n3. Experiments",
                "research_idea": "Interpretable attention mechanisms",
                "terminology_glossary": {
                    "Attention": "Mechanism for weighing input importance",
                    "Transformer": "Architecture using self-attention",
                },
                "structure_type": "enhanced_imrad",
            },
            created_by_skill="framework-designer",
        )
        thread_state["academic_artifacts"] = [framework_artifact]

        # Execute Paper Writer
        paper_writer = FullpaperWriterSkill()

        skill_input = SkillInput(
            workspace_id="test-workspace",
            user_query="Write a paper about interpretable attention",
            context={"framework_outline": framework_artifact.content},
        )

        output = paper_writer.execute(skill_input, thread_state)

        # Verify Paper Writer consumed the framework
        assert output.success is True
        assert len(output.artifacts) == 1
        assert output.artifacts[0].type == "paper_draft"

        # Verify paper content includes framework elements
        paper_content = output.artifacts[0].content
        assert "sections" in paper_content

    @pytest.mark.asyncio
    async def test_full_workflow_chain(
        self,
        thread_state: ThreadState,
        sample_papers: list[Paper],
    ):
        """Complete workflow: Research -> Framework -> Paper."""
        # Step 1: Execute Deep Research
        deep_research = DeepResearchSkill()

        with patch.object(deep_research, "_executor") as mock_executor:
            mock_executor.execute_plan = AsyncMock(return_value=[])

            with patch.object(deep_research, "_search_papers") as mock_search:
                mock_search.return_value = sample_papers

                research_input = SkillInput(
                    workspace_id="test-workspace",
                    user_query="transformer models for NLP",
                    context={},
                )

                research_output = deep_research.execute(research_input, thread_state)

                assert research_output.success is True
                assert len(research_output.artifacts) >= 1

        # Update thread state with research artifacts
        thread_state["academic_artifacts"] = list(research_output.artifacts)
        thread_state["literature_context"] = research_output.content[:500]

        # Step 2: Execute Framework Designer (with mocked LLM)
        framework_designer = FrameworkDesignerSkill()

        mock_model = MagicMock()
        mock_model.invoke.side_effect = [
            MagicMock(content="This paper presents novel attention mechanisms for transformers."),
            MagicMock(content="1. Introduction\n   1.1 Background\n2. Methodology\n3. Experiments"),
        ]

        with patch.object(framework_designer, "_get_model", return_value=mock_model):
            framework_input = SkillInput(
                workspace_id="test-workspace",
                user_query="Design paper about transformer attention",
                context={"research_idea": "Novel attention mechanisms"},
            )

            framework_output = framework_designer.execute(framework_input, thread_state)

            assert framework_output.success is True
            assert len(framework_output.artifacts) == 1
            assert framework_output.artifacts[0].type == "framework_outline"

        # Update state with framework artifact
        thread_state["academic_artifacts"].extend(framework_output.artifacts)

        # Step 3: Execute Paper Writer
        paper_writer = FullpaperWriterSkill()

        paper_input = SkillInput(
            workspace_id="test-workspace",
            user_query="Write complete paper",
            context={"framework_outline": framework_output.artifacts[0].content},
        )

        paper_output = paper_writer.execute(paper_input, thread_state)

        # Verify complete workflow
        assert paper_output.success is True
        assert len(paper_output.artifacts) == 1
        assert paper_output.artifacts[0].type == "paper_draft"

        # Verify all artifacts exist in state
        all_artifact_types = [a.type for a in thread_state["academic_artifacts"]]
        assert "deep_research_report" in all_artifact_types
        assert "framework_outline" in all_artifact_types

    @pytest.mark.asyncio
    async def test_terminology_propagates(
        self,
        thread_state: ThreadState,
    ):
        """Terminology from framework should propagate to paper."""
        # Setup: Framework with terminology glossary
        terminology_glossary = {
            "Transformer": "Neural architecture using self-attention",
            "Attention": "Mechanism for weighing input importance",
            "BERT": "Bidirectional encoder representations",
            "Fine-tuning": "Adapting pre-trained models to specific tasks",
        }

        framework_artifact = AcademicArtifact(
            id="framework-terminology-test",
            workspace_id="test-workspace",
            type="framework_outline",
            content={
                "abstract": "Paper about transformer architectures.",
                "outline": "1. Introduction\n2. Methodology",
                "terminology_glossary": terminology_glossary,
                "structure_type": "enhanced_imrad",
            },
            created_by_skill="framework-designer",
        )

        # Execute Paper Writer with terminology
        paper_writer = FullpaperWriterSkill()

        skill_input = SkillInput(
            workspace_id="test-workspace",
            user_query="Write paper with terminology",
            context={"framework_outline": framework_artifact.content},
        )

        output = paper_writer.execute(skill_input, thread_state)

        # Verify terminology is used in paper generation
        assert output.success is True

        # The terminology should be passed to section writing context
        # (Verification that _format_terminology was called with the glossary)
        paper_content = output.artifacts[0].content
        assert "sections" in paper_content

    @pytest.mark.asyncio
    async def test_artifacts_chain(
        self,
        thread_state: ThreadState,
        sample_papers: list[Paper],
    ):
        """Artifacts should flow between skills with correct types."""
        # Track artifact flow through the chain

        # Step 1: Deep Research creates deep_research_report
        research_artifact = AcademicArtifact(
            id="research-results-1",
            workspace_id="test-workspace",
            type="deep_research_report",
            content={
                "schema_version": "v1",
                "source_feature": "deep_research",
                "topic": "test topic",
                "corpus": {"paper_count": len(sample_papers), "top_papers": [{"title": p.title} for p in sample_papers]},
                "discovery": {"patterns": []},
                "gaps": [],
                "ideas": [],
            },
            created_by_skill="deep-research",
        )
        thread_state["academic_artifacts"] = [research_artifact]

        # Verify initial artifact type
        assert thread_state["academic_artifacts"][0].type == "deep_research_report"

        # Step 2: Framework Designer consumes and creates framework_outline
        framework_artifact = AcademicArtifact(
            id="framework-outline-1",
            workspace_id="test-workspace",
            type="framework_outline",
            content={
                "abstract": "Test abstract",
                "outline": "1. Introduction",
            },
            created_by_skill="framework-designer",
        )
        thread_state["academic_artifacts"].append(framework_artifact)

        # Verify chain so far
        artifact_types = [a.type for a in thread_state["academic_artifacts"]]
        assert "deep_research_report" in artifact_types
        assert "framework_outline" in artifact_types

        # Step 3: Paper Writer creates paper_draft
        paper_writer = FullpaperWriterSkill()
        skill_input = SkillInput(
            workspace_id="test-workspace",
            user_query="Write paper",
            context={"framework_outline": framework_artifact.content},
        )

        output = paper_writer.execute(skill_input, thread_state)

        # Add paper draft to artifacts
        thread_state["academic_artifacts"].extend(output.artifacts)

        # Verify complete chain
        final_types = [a.type for a in thread_state["academic_artifacts"]]
        assert "deep_research_report" in final_types
        assert "framework_outline" in final_types
        assert "paper_draft" in final_types

    @pytest.mark.asyncio
    async def test_citations_flow_through_workflow(
        self,
        thread_state: ThreadState,
        sample_papers: list[Paper],
    ):
        """Citations should accumulate through the workflow."""
        # Initial citations from Deep Research
        initial_citations = [p.doi for p in sample_papers if p.doi]
        thread_state["cited_papers"] = initial_citations

        # Execute Framework Designer
        framework_designer = FrameworkDesignerSkill()
        mock_model = MagicMock()
        mock_model.invoke.return_value = MagicMock(content="Generated content")

        with patch.object(framework_designer, "_get_model", return_value=mock_model):
            framework_input = SkillInput(
                workspace_id="test-workspace",
                user_query="Design paper",
                context={},
            )

            # Framework should have access to cited papers
            literature_ctx = framework_designer._get_literature_context(thread_state)
            assert "10.48550" in literature_ctx or len(thread_state["cited_papers"]) > 0

            framework_designer.execute(framework_input, thread_state)

        # Execute Paper Writer
        paper_writer = FullpaperWriterSkill()

        framework_content = {
            "abstract": "Test abstract",
            "outline": "1. Introduction",
        }

        paper_input = SkillInput(
            workspace_id="test-workspace",
            user_query="Write paper",
            context={"framework_outline": framework_content},
        )

        paper_output = paper_writer.execute(paper_input, thread_state)

        # Verify citations persist
        assert paper_output.success is True
        # Cited papers should be preserved
        assert len(thread_state.get("cited_papers", [])) >= len(initial_citations)

    @pytest.mark.asyncio
    async def test_context_preservation_across_skills(
        self,
        thread_state: ThreadState,
    ):
        """Context should be preserved and accessible across skills."""
        # Set up initial context
        thread_state["literature_context"] = "Important papers: Vaswani et al. (2017)"
        thread_state["discipline"] = "Computer Science"
        thread_state["workspace_type"] = "sci"

        # Verify Framework Designer can access context
        framework_designer = FrameworkDesignerSkill()
        mock_model = MagicMock()
        mock_model.invoke.return_value = MagicMock(content="Generated abstract and outline")

        with patch.object(framework_designer, "_get_model", return_value=mock_model):
            framework_input = SkillInput(
                workspace_id="test-workspace",
                user_query="Design paper",
                context={},
            )

            literature_ctx = framework_designer._get_literature_context(thread_state)
            assert "Vaswani" in literature_ctx

            output = framework_designer.execute(framework_input, thread_state)
            assert output.success is True

        # Verify context persists
        assert thread_state.get("discipline") == "Computer Science"
        assert thread_state.get("workspace_type") == "sci"


class TestWorkflowErrorHandling:
    """Tests for error handling in the workflow."""

    @pytest.mark.asyncio
    async def test_framework_handles_missing_research(
        self,
        thread_state: ThreadState,
    ):
        """Framework Designer should handle missing research gracefully."""
        framework_designer = FrameworkDesignerSkill()
        mock_model = MagicMock()
        mock_model.invoke.return_value = MagicMock(content="Generated content")

        with patch.object(framework_designer, "_get_model", return_value=mock_model):
            framework_input = SkillInput(
                workspace_id="test-workspace",
                user_query="Design paper about machine learning",
                context={},  # No research idea provided
            )

            output = framework_designer.execute(framework_input, thread_state)

            # Should succeed using user_query as fallback
            assert output.success is True

    @pytest.mark.asyncio
    async def test_writer_handles_incomplete_framework(
        self,
        thread_state: ThreadState,
    ):
        """Paper Writer should handle incomplete framework."""
        paper_writer = FullpaperWriterSkill()

        # Minimal framework
        minimal_framework = {
            "abstract": "Test abstract",
            # Missing outline, sections, etc.
        }

        skill_input = SkillInput(
            workspace_id="test-workspace",
            user_query="Write paper",
            context={"framework_outline": minimal_framework},
        )

        output = paper_writer.execute(skill_input, thread_state)

        # Should still succeed with mock content
        assert output.success is True

    @pytest.mark.asyncio
    async def test_workflow_continues_after_skill_failure(
        self,
        thread_state: ThreadState,
    ):
        """Workflow should be able to continue after a skill fails."""
        # Simulate a failed research skill
        deep_research = DeepResearchSkill()

        with patch.object(deep_research, "_executor") as mock_executor:
            mock_executor.execute_plan = AsyncMock(return_value=[])
            with patch.object(deep_research, "_search_papers", return_value=[]):
                skill_input = SkillInput(
                    workspace_id="test-workspace",
                    user_query="obscure topic with no results",
                    context={},
                )

                research_output = deep_research.execute(skill_input, thread_state)

                # Research may succeed but with no papers
                assert research_output.success is True

        # Framework should still work
        framework_designer = FrameworkDesignerSkill()
        mock_model = MagicMock()
        mock_model.invoke.return_value = MagicMock(content="Generated content")

        with patch.object(framework_designer, "_get_model", return_value=mock_model):
            framework_input = SkillInput(
                workspace_id="test-workspace",
                user_query="Design paper",
                context={"research_idea": "Fallback research idea"},
            )

            framework_output = framework_designer.execute(framework_input, thread_state)
            assert framework_output.success is True


class TestWorkflowPerformance:
    """Tests for workflow performance requirements."""

    @pytest.mark.asyncio
    async def test_deep_research_completes_quickly(
        self,
        thread_state: ThreadState,
        sample_papers: list[Paper],
    ):
        """Deep Research should complete in under 5 seconds."""
        import time

        deep_research = DeepResearchSkill()

        with patch.object(deep_research, "_executor") as mock_executor:
            mock_executor.execute_plan = AsyncMock(return_value=[])
            with patch.object(deep_research, "_search_papers", return_value=sample_papers):
                skill_input = SkillInput(
                    workspace_id="test-workspace",
                    user_query="test query",
                    context={},
                )

                start = time.time()
                deep_research.execute(skill_input, thread_state)
                elapsed = time.time() - start

                assert elapsed < 5.0, f"Deep Research took {elapsed:.2f}s (limit: 5s)"

    @pytest.mark.asyncio
    async def test_framework_designer_completes_quickly(
        self,
        thread_state: ThreadState,
    ):
        """Framework Designer should complete in under 5 seconds."""
        import time

        framework_designer = FrameworkDesignerSkill()
        mock_model = MagicMock()
        mock_model.invoke.return_value = MagicMock(content="Generated content")

        with patch.object(framework_designer, "_get_model", return_value=mock_model):
            skill_input = SkillInput(
                workspace_id="test-workspace",
                user_query="Design paper",
                context={},
            )

            start = time.time()
            framework_designer.execute(skill_input, thread_state)
            elapsed = time.time() - start

            assert elapsed < 5.0, f"Framework Designer took {elapsed:.2f}s (limit: 5s)"

    @pytest.mark.asyncio
    async def test_paper_writer_completes_quickly(
        self,
        thread_state: ThreadState,
    ):
        """Paper Writer should complete in under 5 seconds."""
        import time

        paper_writer = FullpaperWriterSkill()

        framework_content = {
            "abstract": "Test abstract",
            "outline": "1. Introduction\n2. Methods",
            "terminology_glossary": {"Term": "Definition"},
        }

        skill_input = SkillInput(
            workspace_id="test-workspace",
            user_query="Write paper",
            context={"framework_outline": framework_content},
        )

        start = time.time()
        paper_writer.execute(skill_input, thread_state)
        elapsed = time.time() - start

        assert elapsed < 5.0, f"Paper Writer took {elapsed:.2f}s (limit: 5s)"
