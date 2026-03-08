"""Framework Designer Skill for generating paper abstracts and outlines.

This skill analyzes research ideas and literature context to generate:
- Compelling abstracts
- Detailed paper outlines following IMRaD structure
- Section headings with key points
"""

import logging
import uuid

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.thread_state import AcademicArtifact, ThreadState
from src.config.llm_config import get_gen_models
from src.models.factory import create_chat_model
from src.skills.base import BaseSkill, SkillInput, SkillOutput

logger = logging.getLogger(__name__)


# Default outline structure following IMRaD format
DEFAULT_OUTLINE_STRUCTURE = """
1. Introduction
   1.1 Background and Motivation
   1.2 Problem Statement
   1.3 Research Objectives and Contributions
2. Related Work
   2.1 Theoretical Background
   2.2 Existing Approaches
   2.3 Research Gap
3. Methodology
   3.1 Overview
   3.2 Problem Formulation
   3.3 Proposed Approach
   3.4 Algorithm/Model Details
4. Experiments
   4.1 Experimental Setup
   4.2 Datasets and Evaluation Metrics
   4.3 Results and Analysis
   4.4 Ablation Studies
5. Discussion
   5.1 Key Findings
   5.2 Limitations
   5.3 Future Work
6. Conclusion
"""

ABSTRACT_GENERATION_PROMPT = """You are an expert academic writer. Generate a compelling abstract for a research paper based on the following information.

Research Idea:
{research_idea}

{literature_context}

Requirements:
1. The abstract should be 150-250 words
2. Include: background, problem statement, methodology, key contributions, and results/implications
3. Use clear, academic language
4. Make it compelling and informative
5. Do not include citations in the abstract

Generate the abstract:"""

OUTLINE_GENERATION_PROMPT = """You are an expert academic paper architect. Generate a detailed paper outline based on the following information.

Research Idea:
{research_idea}

Abstract:
{abstract}

{literature_context}

Requirements:
1. Follow the IMRaD structure (Introduction, Methods, Results, Discussion)
2. Each section should have 2-4 subsections
3. For each section and subsection, provide:
   - A clear heading
   - 2-4 key points to be covered
4. The outline should be detailed enough to guide the writing process
5. Adapt the structure based on the specific research type (theoretical, empirical, review, etc.)

Use this format for each section:
## Section Number. Section Title
Key points:
- Point 1
- Point 2
- Point 3

### Subsection Number.Subsection Title
Key points:
- Point 1
- Point 2

Generate the detailed outline:"""


class FrameworkDesignerSkill(BaseSkill):
    """Skill for generating paper abstracts and detailed outlines.

    This skill analyzes research ideas and literature context to produce:
    - Compelling abstracts (150-250 words)
    - Detailed paper outlines following IMRaD structure
    - Section headings with key points for each section

    Attributes:
        name: Unique identifier for the skill.
        description: Human-readable description.
        version: Version string.
        model_id: ID of the LLM model to use for generation.
    """

    name = "framework-designer"
    description = "Generate paper abstracts and detailed outlines based on research ideas"
    version = "1.0.0"

    def __init__(self, model_id: str | None = None):
        """Initialize the Framework Designer Skill.

        Args:
            model_id: Optional model ID for the LLM. If not provided,
                     will use the default model from configuration.
        """
        self.model_id = model_id
        self._model: BaseChatModel | None = None

    def _get_model(self) -> BaseChatModel:
        """Get or create the LLM model instance.

        Returns:
            The chat model instance.

        Raises:
            ValueError: If model configuration is not found.
        """
        if self._model is None:
            if self.model_id:
                self._model = create_chat_model(self.model_id, temperature=0.7)
            else:
                # Get default model from configuration
                models = get_gen_models()
                if not models:
                    raise ValueError("No generation models configured")
                # Use the first available model
                self._model = create_chat_model(models[0].id, temperature=0.7)
        return self._model

    def _get_research_idea(self, state: ThreadState, input: SkillInput) -> str:
        """Extract research idea from state artifacts or input.

        Args:
            state: The thread state containing artifacts.
            input: The skill input with context.

        Returns:
            The research idea text.
        """
        # First check context for research idea
        if "research_idea" in input.context:
            idea = input.context["research_idea"]
            if isinstance(idea, dict):
                return idea.get("content", idea.get("description", str(idea)))
            return str(idea)

        # Check state artifacts for research_idea type
        for artifact in state.artifacts:
            if artifact.type == "research_idea":
                content = artifact.content
                if isinstance(content, dict):
                    return content.get("content", content.get("description", str(content)))
                return str(content)

        # Fall back to user query
        return input.user_query

    def _get_literature_context(self, state: ThreadState) -> str:
        """Extract literature context from state.

        Args:
            state: The thread state.

        Returns:
            Formatted literature context string.
        """
        context = state.get_context("literature_context", "")
        if context:
            return f"Relevant Literature Context:\n{context}"

        # Check for cited papers
        if state.cited_papers:
            return f"Related Papers: {', '.join(state.cited_papers[:10])}"

        return ""

    def _generate_abstract(
        self,
        research_idea: str,
        literature_context: str,
        model: BaseChatModel,
    ) -> str:
        """Generate an abstract using the LLM.

        Args:
            research_idea: The research idea text.
            literature_context: Context from literature review.
            model: The LLM model instance.

        Returns:
            Generated abstract text.
        """
        prompt = ABSTRACT_GENERATION_PROMPT.format(
            research_idea=research_idea,
            literature_context=literature_context,
        )

        messages = [
            SystemMessage(content="You are an expert academic writer specializing in research paper abstracts."),
            HumanMessage(content=prompt),
        ]

        response = model.invoke(messages)
        return response.content.strip()

    def _generate_outline(
        self,
        research_idea: str,
        abstract: str,
        literature_context: str,
        model: BaseChatModel,
    ) -> str:
        """Generate a detailed outline using the LLM.

        Args:
            research_idea: The research idea text.
            abstract: The generated abstract.
            literature_context: Context from literature review.
            model: The LLM model instance.

        Returns:
            Generated outline text.
        """
        prompt = OUTLINE_GENERATION_PROMPT.format(
            research_idea=research_idea,
            abstract=abstract,
            literature_context=literature_context,
        )

        messages = [
            SystemMessage(content="You are an expert academic paper architect specializing in research paper outlines."),
            HumanMessage(content=prompt),
        ]

        response = model.invoke(messages)
        return response.content.strip()

    def _create_artifact(
        self,
        workspace_id: str,
        abstract: str,
        outline: str,
        research_idea: str,
    ) -> AcademicArtifact:
        """Create the framework outline artifact.

        Args:
            workspace_id: The workspace ID.
            abstract: The generated abstract.
            outline: The generated outline.
            research_idea: The original research idea.

        Returns:
            The created artifact.
        """
        return AcademicArtifact(
            id=f"framework-outline-{uuid.uuid4().hex[:8]}",
            workspace_id=workspace_id,
            type="framework_outline",
            content={
                "abstract": abstract,
                "outline": outline,
                "research_idea": research_idea,
                "structure_type": "imrad",
            },
            created_by_skill=self.name,
        )

    def execute(self, input: SkillInput, state: ThreadState) -> SkillOutput:
        """Execute the framework designer skill.

        This method:
        1. Extracts the research idea from artifacts or input context
        2. Gets literature context if available
        3. Generates a compelling abstract
        4. Generates a detailed paper outline
        5. Creates a framework_outline artifact

        Args:
            input: The skill input containing workspace_id, user_query, and context.
            state: The current thread state for context and artifact storage.

        Returns:
            SkillOutput containing the abstract, outline, and created artifact.
        """
        try:
            # Get the LLM model
            model = self._get_model()

            # Extract research idea
            research_idea = self._get_research_idea(state, input)
            logger.info("Framework Designer: Processing research idea (length: %d)", len(research_idea))

            # Get literature context
            literature_context = self._get_literature_context(state)

            # Generate abstract
            logger.info("Framework Designer: Generating abstract...")
            abstract = self._generate_abstract(research_idea, literature_context, model)

            # Generate outline
            logger.info("Framework Designer: Generating outline...")
            outline = self._generate_outline(research_idea, abstract, literature_context, model)

            # Create artifact
            artifact = self._create_artifact(
                workspace_id=input.workspace_id,
                abstract=abstract,
                outline=outline,
                research_idea=research_idea,
            )

            # Format output content
            content = f"""## Abstract

{abstract}

## Paper Outline

{outline}
"""

            logger.info("Framework Designer: Successfully generated framework outline")

            return SkillOutput(
                success=True,
                content=content,
                artifacts=[artifact],
                metadata={
                    "abstract_word_count": len(abstract.split()),
                    "outline_sections": outline.count("##"),
                    "model_used": self.model_id or "default",
                },
            )

        except ValueError as e:
            logger.error("Framework Designer configuration error: %s", e)
            return SkillOutput(
                success=False,
                content="",
                error_message=f"Configuration error: {str(e)}",
            )

        except Exception as e:
            logger.exception("Framework Designer execution failed")
            return SkillOutput(
                success=False,
                content="",
                error_message=f"Execution failed: {str(e)}",
            )

    def validate_input(self, input: SkillInput) -> str | None:
        """Validate the input before execution.

        Checks for:
        - Required workspace_id
        - Non-empty user_query or research_idea in context

        Args:
            input: The skill input to validate.

        Returns:
            None if validation passes, or an error message string.
        """
        # Check workspace_id
        if not input.workspace_id:
            return "workspace_id is required"

        # Allow empty query if research_idea is provided in context
        has_research_idea = "research_idea" in input.context

        # Check for empty or whitespace-only query
        if not input.user_query or not input.user_query.strip():
            if not has_research_idea:
                return "user_query cannot be empty"

        return None
