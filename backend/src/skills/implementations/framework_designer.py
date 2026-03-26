"""Framework Designer Skill for generating paper abstracts and outlines.

This skill analyzes research ideas and literature context to generate:
- Compelling abstracts
- Detailed paper outlines following IMRaD structure
- Section headings with key points
- Terminology glossary and chapter dependencies
"""

import logging
import re
import uuid
from typing import Any

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
    """Enhanced skill for generating paper frameworks with Memory injection.

    This implementation extends the framework generation flow with:
    - Memory context injection (research context, writing preferences)
    - Enhanced framework structure with terminology glossary
    - Chapter dependencies for optimal writing order

    Attributes:
        name: Unique identifier for the skill.
        description: Human-readable description.
        version: Version string.
        model_id: ID of the LLM model to use for generation.
    """

    name = "framework-designer"
    description = "Generate paper abstracts and detailed outlines with memory context injection"
    version = "2.0.0"

    def __init__(
        self,
        model_id: str | None = None,
    ):
        """Initialize the Enhanced Framework Designer Skill.

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

    def _prepare_memory_context_from_prompt(self, memory_prompt: str) -> dict[str, Any]:
        """Convert prompt-form memory into the structured context used by the skill."""
        context: dict[str, Any] = {
            "research_context": {"summary": ""},
            "writing_preferences": {"summary": ""},
            "tool_preferences": {"summary": ""},
            "top_facts": [],
        }

        section = None
        for raw_line in memory_prompt.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("<") or line.startswith("</"):
                continue
            if line.endswith(":"):
                section = line[:-1]
                continue
            if not line.startswith("- "):
                continue

            content = re.sub(r"\s*\(置信度:\s*[\d.]+\)\s*$", "", line[2:]).strip()
            if not content:
                continue

            context["top_facts"].append({"content": content, "confidence": 0.8})
            if section == "研究上下文" and not context["research_context"]["summary"]:
                context["research_context"]["summary"] = content
            elif section == "用户偏好" and not context["writing_preferences"]["summary"]:
                context["writing_preferences"]["summary"] = content
            elif section == "行为习惯" and not context["tool_preferences"]["summary"]:
                context["tool_preferences"]["summary"] = content

        return context

    def _prepare_memory_context(self, state: ThreadState | None = None) -> dict[str, Any]:
        """Prepare memory context for injection into prompts.

        Extracts research context, writing preferences, and other
        relevant user data from canonical prompt-form state memory.

        Returns:
            Dictionary containing memory context for prompt injection.
        """
        if state is not None:
            raw_memory = state.get("memory_context")
            if isinstance(raw_memory, dict):
                return raw_memory
            prompt_memory = str(raw_memory or "").strip()
            if prompt_memory:
                return self._prepare_memory_context_from_prompt(prompt_memory)
        return {
            "research_context": {"summary": ""},
            "writing_preferences": {"summary": ""},
            "tool_preferences": {"summary": ""},
            "top_facts": [],
        }

    def _format_memory_for_prompt(self, memory_context: dict) -> str:
        """Format memory context for inclusion in prompts.

        Args:
            memory_context: The memory context dictionary.

        Returns:
            Formatted string for prompt injection.
        """
        parts = []

        research_ctx = memory_context.get("research_context", {})
        if research_ctx.get("summary"):
            parts.append(f"Research Context: {research_ctx['summary']}")

        writing_prefs = memory_context.get("writing_preferences", {})
        if writing_prefs.get("summary"):
            parts.append(f"Writing Preferences: {writing_prefs['summary']}")

        top_facts = memory_context.get("top_facts", [])
        if top_facts:
            facts_str = ", ".join(f.get("content", "") for f in top_facts[:3])
            parts.append(f"Key Facts: {facts_str}")

        return "\n".join(parts) if parts else ""

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

        # Check state academic_artifacts for research_idea type
        for artifact in state.get("academic_artifacts", []):
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
        context = state.get("literature_context", "")
        if context:
            return f"Relevant Literature Context:\n{context}"

        # Check for cited papers
        cited = state.get("cited_papers", [])
        if cited:
            return f"Related Papers: {', '.join(cited[:10])}"

        return ""

    def _create_enhanced_framework(
        self,
        outline: dict,
        topic: str,
    ) -> dict[str, Any]:
        """Create enhanced framework with terminology glossary and dependencies.

        Args:
            outline: The basic outline structure (abstract, sections).
            topic: The research topic for glossary generation.

        Returns:
            Enhanced framework dictionary with additional metadata.
        """
        # Generate terminology glossary (5-10 key terms)
        terminology_glossary = self._generate_terminology_glossary(topic, outline)

        # Generate chapter dependencies for writing order
        chapter_dependencies = self._generate_chapter_dependencies(outline)

        return {
            "abstract": outline.get("abstract", ""),
            "sections": outline.get("sections", {}),
            "terminology_glossary": terminology_glossary,
            "chapter_dependencies": chapter_dependencies,
            "structure_type": "enhanced_imrad",
        }

    def _generate_terminology_glossary(self, topic: str, outline: dict) -> dict[str, str]:
        """Generate a terminology glossary based on topic and outline.

        Args:
            topic: The research topic.
            outline: The outline structure.

        Returns:
            Dictionary of term -> definition pairs.
        """
        # Extract key terms from topic
        terms = {}

        # Common academic terms with definitions based on context
        topic_lower = topic.lower()

        if "machine learning" in topic_lower or "ml" in topic_lower:
            terms["Machine Learning"] = "A subset of AI enabling systems to learn from data"
            terms["Training Data"] = "Dataset used to train the model parameters"
            terms["Model"] = "Mathematical representation learned from data"

        if "neural" in topic_lower or "deep learning" in topic_lower:
            terms["Neural Network"] = "Computational model inspired by biological neurons"
            terms["Deep Learning"] = "Neural networks with multiple hidden layers"
            terms["Backpropagation"] = "Algorithm for computing gradients in neural networks"

        if "attention" in topic_lower or "transformer" in topic_lower:
            terms["Attention Mechanism"] = "Component that weighs input importance dynamically"
            terms["Transformer"] = "Architecture using self-attention for sequence processing"
            terms["Self-Attention"] = "Attention mechanism relating positions within a sequence"

        # Add general academic terms if we don't have enough
        general_terms = {
            "Methodology": "Systematic approach to conducting research",
            "Hypothesis": "Testable prediction about the research question",
            "Evaluation Metrics": "Quantitative measures to assess performance",
            "Baseline": "Reference method for comparison in experiments",
            "Ablation Study": "Analysis of component contribution to overall performance",
        }

        for term, definition in general_terms.items():
            if len(terms) < 10 and term not in terms:
                terms[term] = definition

        return terms

    def _generate_chapter_dependencies(self, outline: dict) -> dict[str, list[str]]:
        """Generate chapter dependencies for optimal writing order.

        Args:
            outline: The outline structure.

        Returns:
            Dictionary mapping chapter to its dependencies.
        """
        sections = outline.get("sections", {})

        # Default IMRaD dependencies
        dependencies = {
            "Abstract": ["Conclusion", "Results"],  # Write abstract last
            "Introduction": [],  # Can start here
            "Related Work": ["Introduction"],
            "Methodology": ["Related Work", "Introduction"],
            "Experiments": ["Methodology"],
            "Results": ["Experiments", "Methodology"],
            "Discussion": ["Results", "Experiments"],
            "Conclusion": ["Results", "Discussion"],
        }

        # If outline has custom sections, derive dependencies
        if sections:
            section_titles = []
            for section_key, section_data in sections.items():
                if isinstance(section_data, dict):
                    title = section_data.get("title", str(section_key))
                    section_titles.append(title)

            # Build dependencies based on section order
            custom_deps = {}
            for i, title in enumerate(section_titles):
                # Each section depends on previous ones
                custom_deps[title] = section_titles[:i] if i > 0 else []
            if custom_deps:
                dependencies = custom_deps

        return dependencies

    def _generate_abstract(
        self,
        research_idea: str,
        literature_context: str,
        model: BaseChatModel,
        memory_context: dict | None = None,
    ) -> str:
        """Generate an abstract using the LLM with memory context.

        Args:
            research_idea: The research idea text.
            literature_context: Context from literature review.
            model: The LLM model instance.
            memory_context: Optional memory context for personalization.

        Returns:
            Generated abstract text.
        """
        # Build prompt with memory context
        memory_str = ""
        if memory_context:
            memory_str = self._format_memory_for_prompt(memory_context)

        memory_section = f"\nUser Context from Memory:\n{memory_str}\n" if memory_str else ""

        prompt = ABSTRACT_GENERATION_PROMPT.format(
            research_idea=research_idea,
            literature_context=literature_context,
        )

        # Add memory context if available
        if memory_section:
            prompt = prompt.replace(
                "Requirements:",
                f"{memory_section}Requirements:",
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
        memory_context: dict | None = None,
    ) -> str:
        """Generate a detailed outline using the LLM with memory context.

        Args:
            research_idea: The research idea text.
            abstract: The generated abstract.
            literature_context: Context from literature review.
            model: The LLM model instance.
            memory_context: Optional memory context for personalization.

        Returns:
            Generated outline text.
        """
        # Build prompt with memory context
        memory_str = ""
        if memory_context:
            memory_str = self._format_memory_for_prompt(memory_context)

        memory_section = f"\nUser Context from Memory:\n{memory_str}\n" if memory_str else ""

        prompt = OUTLINE_GENERATION_PROMPT.format(
            research_idea=research_idea,
            abstract=abstract,
            literature_context=literature_context,
        )

        # Add memory context if available
        if memory_section:
            prompt = prompt.replace(
                "Requirements:",
                f"{memory_section}Requirements:",
            )

        messages = [
            SystemMessage(content="You are an expert academic paper architect specializing in research paper outlines."),
            HumanMessage(content=prompt),
        ]

        response = model.invoke(messages)
        return response.content.strip()

    def _parse_outline_to_dict(self, outline_text: str) -> dict:
        """Parse outline text into structured dictionary.

        Args:
            outline_text: The raw outline text.

        Returns:
            Structured dictionary of sections.
        """
        sections = {}
        current_section = None
        current_points = []

        for line in outline_text.split("\n"):
            line = line.strip()
            if line.startswith("##") or (line and line[0].isdigit() and "." in line):
                # Save previous section
                if current_section:
                    sections[current_section] = {"points": current_points}
                # Start new section
                current_section = line.lstrip("#").strip()
                current_points = []
            elif line.startswith("-") and current_section:
                current_points.append(line.lstrip("-").strip())

        # Save last section
        if current_section:
            sections[current_section] = {"points": current_points}

        return sections

    def _create_artifact(
        self,
        workspace_id: str,
        abstract: str,
        outline: str,
        research_idea: str,
        enhanced_framework: dict | None = None,
    ) -> AcademicArtifact:
        """Create the enhanced framework outline artifact.

        Args:
            workspace_id: The workspace ID.
            abstract: The generated abstract.
            outline: The generated outline.
            research_idea: The original research idea.
            enhanced_framework: Optional enhanced framework with glossary and dependencies.

        Returns:
            The created artifact.
        """
        content = {
            "abstract": abstract,
            "outline": outline,
            "research_idea": research_idea,
            "structure_type": "enhanced_imrad",
        }

        # Add enhanced framework data if available
        if enhanced_framework:
            content["terminology_glossary"] = enhanced_framework.get("terminology_glossary", {})
            content["chapter_dependencies"] = enhanced_framework.get("chapter_dependencies", {})

        return AcademicArtifact(
            id=f"framework-outline-{uuid.uuid4().hex[:8]}",
            workspace_id=workspace_id,
            type="framework_outline",
            content=content,
            created_by_skill=self.name,
        )

    def execute(self, input: SkillInput, state: ThreadState) -> SkillOutput:
        """Execute the enhanced framework designer skill.

        This method:
        1. Extracts the research idea from artifacts or input context
        2. Prepares memory context (research context, writing preferences)
        3. Gets literature context if available
        4. Generates a compelling abstract with memory context
        5. Generates a detailed paper outline with memory context
        6. Creates an enhanced framework with terminology glossary
        7. Creates a framework_outline artifact with all metadata

        Args:
            input: The skill input containing workspace_id, user_query, and context.
            state: The current thread state for context and artifact storage.

        Returns:
            SkillOutput containing the abstract, outline, and created artifact.
        """
        try:
            # Get the LLM model
            model = self._get_model()

            # Prepare memory context
            memory_context = self._prepare_memory_context(state)
            logger.info("Framework Designer: Memory context prepared")

            # Extract research idea
            research_idea = self._get_research_idea(state, input)
            logger.info("Framework Designer: Processing research idea (length: %d)", len(research_idea))

            # Get literature context
            literature_context = self._get_literature_context(state)

            # Generate abstract with memory context
            logger.info("Framework Designer: Generating abstract with memory context...")
            abstract = self._generate_abstract(research_idea, literature_context, model, memory_context)

            # Generate outline with memory context
            logger.info("Framework Designer: Generating outline with memory context...")
            outline = self._generate_outline(research_idea, abstract, literature_context, model, memory_context)

            # Parse outline and create enhanced framework
            outline_dict = self._parse_outline_to_dict(outline)
            outline_dict["abstract"] = abstract

            enhanced_framework = self._create_enhanced_framework(outline_dict, research_idea)
            logger.info(
                "Framework Designer: Enhanced framework created with %d glossary terms",
                len(enhanced_framework.get("terminology_glossary", {})),
            )

            # Create artifact with enhanced structure
            artifact = self._create_artifact(
                workspace_id=input.workspace_id,
                abstract=abstract,
                outline=outline,
                research_idea=research_idea,
                enhanced_framework=enhanced_framework,
            )

            # Format output content
            glossary_section = ""
            if enhanced_framework.get("terminology_glossary"):
                glossary_items = [
                    f"- **{term}**: {definition}"
                    for term, definition in enhanced_framework["terminology_glossary"].items()
                ]
                glossary_section = f"\n## Terminology Glossary\n\n" + "\n".join(glossary_items) + "\n"

            content = f"""## Abstract

{abstract}

## Paper Outline

{outline}
{glossary_section}"""

            logger.info("Framework Designer: Successfully generated enhanced framework outline")

            return SkillOutput(
                success=True,
                content=content,
                artifacts=[artifact],
                metadata={
                    "abstract_word_count": len(abstract.split()),
                    "outline_sections": outline.count("##"),
                    "glossary_terms": len(enhanced_framework.get("terminology_glossary", {})),
                    "has_memory_context": bool(memory_context.get("research_context", {}).get("summary")),
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
