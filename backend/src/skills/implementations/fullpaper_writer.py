"""Fullpaper Writer Skill for writing complete academic papers section by section.

This skill generates complete academic papers by:
1. Reading the framework outline from thread state
2. Getting literature context for citations
3. Writing each section using LLM
4. Incorporating citations in proper format
5. Producing a paper_draft artifact
"""

import asyncio
from datetime import UTC, datetime

from src.agents.thread_state import AcademicArtifact, ThreadState
from src.skills.base import BaseSkill, SkillInput, SkillOutput

# Standard academic paper sections in order
PAPER_SECTIONS = [
    "introduction",
    "related_work",
    "methodology",
    "experiments",
    "discussion",
    "conclusion",
]

# Section-specific prompts for LLM
SECTION_PROMPTS = {
    "introduction": """Write an Introduction section for an academic paper.

Topic: {topic}
Framework outline: {outline}
Literature context: {literature_context}

Requirements:
- Provide background and motivation for the research
- Clearly state the research problem
- Present research objectives and questions
- Outline the paper's contribution
- Include relevant citations using Author (Year) format
- Target length: 500-1000 words
- Maintain formal academic tone
""",

    "related_work": """Write a Related Work section for an academic paper.

Topic: {topic}
Framework outline: {outline}
Literature context: {literature_context}

Requirements:
- Survey relevant prior work organized by themes
- Compare and contrast different approaches
- Identify gaps in existing literature
- Position this work relative to prior research
- Include citations using Author (Year) format
- Target length: 800-1500 words
- Maintain formal academic tone
""",

    "methodology": """Write a Methodology section for an academic paper.

Topic: {topic}
Framework outline: {outline}
Literature context: {literature_context}

Requirements:
- Describe the research approach and design
- Explain data collection methods
- Detail analysis techniques
- Justify methodological choices
- Include citations for established methods
- Target length: 800-1500 words
- Maintain formal academic tone
""",

    "experiments": """Write an Experiments section for an academic paper.

Topic: {topic}
Framework outline: {outline}
Literature context: {literature_context}

Requirements:
- Describe experimental setup
- Detail datasets and evaluation metrics
- Present results with appropriate detail
- Include comparisons to baselines if applicable
- Reference any tools or resources used
- Target length: 800-1500 words
- Maintain formal academic tone
""",

    "discussion": """Write a Discussion section for an academic paper.

Topic: {topic}
Framework outline: {outline}
Literature context: {literature_context}

Requirements:
- Interpret the results and their implications
- Discuss how findings relate to research questions
- Address limitations of the study
- Compare with prior work where relevant
- Include citations using Author (Year) format
- Target length: 500-1000 words
- Maintain formal academic tone
""",

    "conclusion": """Write a Conclusion section for an academic paper.

Topic: {topic}
Framework outline: {outline}
Literature context: {literature_context}

Requirements:
- Summarize key findings
- Restate contributions
- Discuss broader implications
- Suggest directions for future work
- Keep concise and impactful
- Target length: 300-500 words
- Maintain formal academic tone
""",
}


class MockLLMService:
    """Mock LLM service for testing purposes.

    In production, this would be replaced with actual LLM API calls.
    """

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate text using mock LLM.

        Args:
            prompt: The prompt to generate from
            **kwargs: Additional generation parameters

        Returns:
            Generated text
        """
        # Simulate async generation
        await asyncio.sleep(0.01)

        # Return mock content based on section type detection
        if "Introduction" in prompt:
            return self._generate_introduction(prompt)
        elif "Related Work" in prompt:
            return self._generate_related_work(prompt)
        elif "Methodology" in prompt:
            return self._generate_methodology(prompt)
        elif "Experiments" in prompt:
            return self._generate_experiments(prompt)
        elif "Discussion" in prompt:
            return self._generate_discussion(prompt)
        elif "Conclusion" in prompt:
            return self._generate_conclusion(prompt)
        else:
            return "Generated content for the requested section."

    def _generate_introduction(self, prompt: str) -> str:
        """Generate mock introduction."""
        return """## 1. Introduction

The rapid advancement of artificial intelligence has transformed numerous domains of scientific research and practical applications. In recent years, deep learning approaches have demonstrated remarkable capabilities in handling complex tasks that were previously considered challenging for computational systems (LeCun et al., 2015).

Despite these advances, significant challenges remain in developing robust and interpretable models that can generalize effectively across diverse scenarios. The research community has increasingly focused on addressing these limitations through novel architectural innovations and training methodologies (Vaswani et al., 2017).

This paper presents a comprehensive framework for addressing these challenges. Our primary contributions include:

1. A novel approach that combines the strengths of multiple paradigms
2. Extensive experimental validation across diverse benchmarks
3. Detailed analysis of the factors influencing performance

The remainder of this paper is organized as follows: Section 2 reviews related work, Section 3 describes our methodology, Section 4 presents experimental results, Section 5 discusses implications, and Section 6 concludes with future directions.
"""

    def _generate_related_work(self, prompt: str) -> str:
        """Generate mock related work."""
        return """## 2. Related Work

### 2.1 Foundation Models

The development of large-scale foundation models has fundamentally changed the landscape of machine learning research. These models, trained on vast amounts of data, have shown impressive capabilities in transfer learning and few-shot learning scenarios (Brown et al., 2020).

Early work in this area focused on transformer-based architectures that leveraged attention mechanisms for capturing long-range dependencies (Vaswani et al., 2017). Subsequent research has expanded these approaches to multimodal settings (Radford et al., 2021).

### 2.2 Domain-Specific Applications

In domain-specific contexts, researchers have adapted general-purpose models to address particular challenges. Fine-tuning approaches have proven effective for specialized tasks (Devlin et al., 2019). More recent work has explored parameter-efficient methods that reduce computational requirements while maintaining performance.

### 2.3 Evaluation Methodologies

The evaluation of AI systems has evolved significantly, with researchers proposing various metrics and benchmarks. Standardized evaluation protocols enable meaningful comparisons across approaches (Wang et al., 2019).
"""

    def _generate_methodology(self, prompt: str) -> str:
        """Generate mock methodology."""
        return """## 3. Methodology

### 3.1 Problem Formulation

We formalize our problem as follows. Given an input distribution D over samples x, our objective is to learn a mapping function f that minimizes the expected loss:

L(f) = E_{x~D}[l(f(x), y)]

where l denotes the task-specific loss function and y represents the ground truth label.

### 3.2 Model Architecture

Our architecture consists of three main components:

1. **Encoder Module**: Processes the input through a series of transformer layers
2. **Fusion Layer**: Combines representations from multiple modalities
3. **Decoder Module**: Generates the final output

The encoder employs multi-head self-attention with relative positional encodings, following established practices (Shaw et al., 2018).

### 3.3 Training Procedure

We train our model using a two-stage approach:

**Stage 1 - Pre-training**: The model is trained on a large unlabeled corpus using self-supervised objectives.

**Stage 2 - Fine-tuning**: The pre-trained model is adapted to the target task using labeled data.

We use AdamW optimizer with learning rate 1e-4 and batch size 32.
"""

    def _generate_experiments(self, prompt: str) -> str:
        """Generate mock experiments."""
        return """## 4. Experiments

### 4.1 Experimental Setup

We evaluate our approach on three benchmark datasets:

- **Dataset A**: Contains 10,000 samples for classification
- **Dataset B**: Multi-modal benchmark with 5,000 examples
- **Dataset C**: Large-scale evaluation with 50,000 instances

All experiments were conducted on NVIDIA A100 GPUs with 40GB memory. We report mean and standard deviation over 5 random seeds.

### 4.2 Baselines

We compare against the following baselines:

- **Baseline 1**: Standard transformer approach (Vaswani et al., 2017)
- **Baseline 2**: Fine-tuned language model (Devlin et al., 2019)
- **Baseline 3**: State-of-the-art domain-specific method

### 4.3 Results

Table 1 shows the main results:

| Method | Dataset A | Dataset B | Dataset C |
|--------|-----------|-----------|-----------|
| Baseline 1 | 78.3 | 72.1 | 81.5 |
| Baseline 2 | 82.1 | 76.4 | 84.2 |
| Baseline 3 | 84.5 | 78.9 | 86.1 |
| **Ours** | **87.2** | **81.3** | **89.0** |

Our method achieves consistent improvements across all datasets, with an average gain of 3.2 percentage points over the strongest baseline.

### 4.4 Ablation Study

We conduct ablation studies to understand the contribution of each component. Removing the fusion layer results in a 2.1% drop in performance, demonstrating its importance.
"""

    def _generate_discussion(self, prompt: str) -> str:
        """Generate mock discussion."""
        return """## 5. Discussion

### 5.1 Analysis of Results

The experimental results demonstrate the effectiveness of our proposed approach. The consistent improvements across diverse datasets suggest that our method captures generalizable patterns rather than dataset-specific artifacts.

Our approach shows particularly strong performance on Dataset C, which contains the most diverse samples. This indicates robust generalization capabilities, addressing a key challenge identified in prior work (Brown et al., 2020).

### 5.2 Comparison with Prior Work

Compared to existing approaches, our method offers several advantages:

1. **Improved Performance**: The 3.2% average improvement is substantial for these benchmarks
2. **Parameter Efficiency**: Our model achieves better results with 20% fewer parameters
3. **Training Stability**: Lower variance across random seeds indicates more stable training

### 5.3 Limitations

Despite the promising results, several limitations should be acknowledged:

- The computational requirements for pre-training remain substantial
- Performance on out-of-distribution samples requires further investigation
- The approach assumes access to labeled data for fine-tuning

### 5.4 Broader Implications

The findings have implications for both research and practical applications. The improved efficiency could enable deployment in resource-constrained settings.
"""

    def _generate_conclusion(self, prompt: str) -> str:
        """Generate mock conclusion."""
        return """## 6. Conclusion

This paper presented a novel approach for addressing key challenges in AI research. Our main contributions include a new architectural framework, comprehensive experimental validation, and detailed analysis of factors influencing performance.

The experimental results demonstrate consistent improvements across multiple benchmarks, with an average gain of 3.2 percentage points over state-of-the-art baselines. The ablation studies confirm the importance of each proposed component.

Future work will focus on extending the approach to additional domains and investigating methods for further reducing computational requirements. We believe this work opens promising directions for developing more robust and efficient AI systems.

## References

Brown, T., et al. (2020). Language Models are Few-Shot Learners. NeurIPS.

Devlin, J., et al. (2019). BERT: Pre-training of Deep Bidirectional Transformers. NAACL.

LeCun, Y., et al. (2015). Deep Learning. Nature.

Radford, A., et al. (2021). Learning Transferable Visual Models. ICML.

Shaw, P., et al. (2018). Self-Attention with Relative Position Representations. NAACL.

Vaswani, A., et al. (2017). Attention Is All You Need. NeurIPS.

Wang, A., et al. (2019). GLUE: A Multi-Task Benchmark. ICLR.
"""


class FullpaperWriterSkill(BaseSkill):
    """Skill for writing complete academic papers section by section.

    This skill reads a framework outline from the thread state, incorporates
    literature context for citations, and generates each section of an academic
    paper in the standard order: Introduction, Related Work, Methodology,
    Experiments, Discussion, Conclusion.

    Attributes:
        name: Unique identifier for the skill.
        description: Human-readable description of the skill.
        version: Version string for the skill.
    """

    name = "fullpaper-writer"
    description = "Write complete academic papers section by section"
    version = "1.0.0"

    def __init__(self, llm_service: MockLLMService | None = None):
        """Initialize the FullpaperWriterSkill.

        Args:
            llm_service: Optional LLM service for text generation.
                        If not provided, uses MockLLMService.
        """
        self.llm_service = llm_service or MockLLMService()

    def validate_input(self, input: SkillInput) -> str | None:
        """Validate the input before execution.

        Checks for required context fields.

        Args:
            input: The skill input to validate.

        Returns:
            None if validation passes, or an error message string.
        """
        # First run base validation
        base_error = super().validate_input(input)
        if base_error:
            return base_error

        # Check for framework_outline in context
        if "framework_outline" not in input.context:
            return "context must contain 'framework_outline' for paper generation"

        return None

    def execute(self, input: SkillInput, state: ThreadState) -> SkillOutput:
        """Execute the skill to generate a complete academic paper.

        Args:
            input: The skill input containing workspace_id, user_query, and context.
            state: The current thread state for context and artifact storage.

        Returns:
            SkillOutput containing the generated paper and paper_draft artifact.
        """
        # Get framework outline from context
        framework_outline = input.context.get("framework_outline", {})

        # Get literature context from state or context
        literature_context = self._get_literature_context(input, state)

        # Get topic from framework outline or user query
        topic = framework_outline.get("topic", input.user_query)

        # Track citations
        citations = []

        # Write each section
        sections = {}
        for section_name in PAPER_SECTIONS:
            section_content = self._write_section(
                section_name=section_name,
                topic=topic,
                outline=framework_outline,
                literature_context=literature_context,
            )
            sections[section_name] = section_content

            # Extract citations from section
            section_citations = self._extract_citations(section_content)
            citations.extend(section_citations)

        # Deduplicate citations
        unique_citations = list(dict.fromkeys(citations))

        # Combine all sections into full paper
        full_paper = self._combine_sections(sections, topic, framework_outline)

        # Update state with cited papers
        if unique_citations:
            existing_cited = list(state.cited_papers)
            state.cited_papers = existing_cited + [
                c for c in unique_citations if c not in existing_cited
            ]

        # Create paper_draft artifact
        artifact = AcademicArtifact(
            id=f"paper-draft-{input.workspace_id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
            workspace_id=input.workspace_id,
            type="paper_draft",
            content={
                "title": framework_outline.get("title", f"Research Paper: {topic}"),
                "topic": topic,
                "sections": sections,
                "full_paper": full_paper,
                "citations": unique_citations,
                "framework_outline_id": framework_outline.get("id"),
                "generated_at": datetime.now(UTC).isoformat(),
                "word_count": len(full_paper.split()),
            },
            created_by_skill=self.name,
        )

        return SkillOutput(
            success=True,
            content=full_paper,
            artifacts=[artifact],
            metadata={
                "sections_generated": list(sections.keys()),
                "total_citations": len(unique_citations),
                "word_count": len(full_paper.split()),
            },
        )

    def _get_literature_context(self, input: SkillInput, state: ThreadState) -> str:
        """Get literature context from state or input context.

        Args:
            input: The skill input.
            state: The thread state.

        Returns:
            Literature context string.
        """
        # Try to get from state first
        lit_context = state.get_context("literature_context", "")

        # Fall back to input context
        if not lit_context and "literature_context" in input.context:
            lit_context = input.context["literature_context"]

        # Also include any cited papers
        if state.cited_papers:
            cited_context = f"Previously cited papers: {', '.join(state.cited_papers)}"
            if lit_context:
                lit_context = f"{lit_context}\n\n{cited_context}"
            else:
                lit_context = cited_context

        return lit_context or "No specific literature context provided."

    def _write_section(
        self,
        section_name: str,
        topic: str,
        outline: dict,
        literature_context: str,
    ) -> str:
        """Write a single section of the paper.

        Args:
            section_name: Name of the section to write.
            topic: The research topic.
            outline: Framework outline dictionary.
            literature_context: Literature context for citations.

        Returns:
            Generated section content.
        """
        # Get the prompt template for this section
        prompt_template = SECTION_PROMPTS.get(section_name, "")
        if not prompt_template:
            return f"## {section_name.replace('_', ' ').title()}\n\nContent for {section_name} section."

        # Format the prompt
        prompt = prompt_template.format(
            topic=topic,
            outline=str(outline),
            literature_context=literature_context,
        )

        # Get section-specific guidance from outline if available
        section_guidance = outline.get("sections", {}).get(section_name, {})
        if section_guidance:
            guidance_str = f"\n\nAdditional guidance: {section_guidance}"
            prompt = prompt + guidance_str

        # Generate content using LLM service
        # Note: Using synchronous wrapper for async in sync context
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, create task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.llm_service.generate(prompt)
                    )
                    content = future.result()
            else:
                content = loop.run_until_complete(self.llm_service.generate(prompt))
        except RuntimeError:
            content = asyncio.run(self.llm_service.generate(prompt))

        return content

    def _extract_citations(self, text: str) -> list[str]:
        """Extract citations from text in Author (Year) format.

        Handles multiple citation formats:
        - Author (Year)
        - (Author, Year)
        - (Author et al., Year)

        Args:
            text: Text to extract citations from.

        Returns:
            List of citation strings.
        """
        import re

        citations = []

        # Pattern 1: "Author (2023)" or "Author et al. (2023)"
        # Handles camelCase names like "LeCun"
        pattern1 = r'([A-Z][a-zA-Z]+(?:\s+et\s+al\.)?)\s*\((\d{4})\)'
        matches1 = re.findall(pattern1, text)
        for author, year in matches1:
            citation = f"{author} ({year})"
            citations.append(citation)

        # Pattern 2: "(Author, 2023)" or "(Author et al., 2023)"
        pattern2 = r'\(([A-Z][a-zA-Z]+(?:\s+et\s+al\.)?),\s*(\d{4})\)'
        matches2 = re.findall(pattern2, text)
        for author, year in matches2:
            citation = f"{author} ({year})"
            if citation not in citations:  # Avoid duplicates
                citations.append(citation)

        return citations

    def _combine_sections(
        self,
        sections: dict[str, str],
        topic: str,
        outline: dict,
    ) -> str:
        """Combine all sections into a complete paper.

        Args:
            sections: Dictionary of section name to content.
            topic: The research topic.
            outline: Framework outline dictionary.

        Returns:
            Complete paper as a single string.
        """
        title = outline.get("title", f"Research Paper: {topic}")

        # Build the paper
        paper_parts = [f"# {title}", ""]

        # Add abstract if available
        if "abstract" in outline:
            paper_parts.append("## Abstract")
            paper_parts.append(outline["abstract"])
            paper_parts.append("")

        # Add each section in order
        for section_name in PAPER_SECTIONS:
            if section_name in sections:
                paper_parts.append(sections[section_name])
                paper_parts.append("")

        return "\n".join(paper_parts)

    async def execute_async(
        self,
        input: SkillInput,
        state: ThreadState,
    ) -> SkillOutput:
        """Async version of execute for better integration.

        Args:
            input: The skill input.
            state: The thread state.

        Returns:
            SkillOutput containing the results.
        """
        # Get framework outline from context
        framework_outline = input.context.get("framework_outline", {})

        # Get literature context from state or context
        literature_context = self._get_literature_context(input, state)

        # Get topic from framework outline or user query
        topic = framework_outline.get("topic", input.user_query)

        # Track citations
        citations = []

        # Write each section asynchronously
        sections = {}
        for section_name in PAPER_SECTIONS:
            section_content = await self._write_section_async(
                section_name=section_name,
                topic=topic,
                outline=framework_outline,
                literature_context=literature_context,
            )
            sections[section_name] = section_content

            # Extract citations from section
            section_citations = self._extract_citations(section_content)
            citations.extend(section_citations)

        # Deduplicate citations
        unique_citations = list(dict.fromkeys(citations))

        # Combine all sections into full paper
        full_paper = self._combine_sections(sections, topic, framework_outline)

        # Update state with cited papers
        if unique_citations:
            existing_cited = list(state.cited_papers)
            state.cited_papers = existing_cited + [
                c for c in unique_citations if c not in existing_cited
            ]

        # Create paper_draft artifact
        artifact = AcademicArtifact(
            id=f"paper-draft-{input.workspace_id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
            workspace_id=input.workspace_id,
            type="paper_draft",
            content={
                "title": framework_outline.get("title", f"Research Paper: {topic}"),
                "topic": topic,
                "sections": sections,
                "full_paper": full_paper,
                "citations": unique_citations,
                "framework_outline_id": framework_outline.get("id"),
                "generated_at": datetime.now(UTC).isoformat(),
                "word_count": len(full_paper.split()),
            },
            created_by_skill=self.name,
        )

        return SkillOutput(
            success=True,
            content=full_paper,
            artifacts=[artifact],
            metadata={
                "sections_generated": list(sections.keys()),
                "total_citations": len(unique_citations),
                "word_count": len(full_paper.split()),
            },
        )

    async def _write_section_async(
        self,
        section_name: str,
        topic: str,
        outline: dict,
        literature_context: str,
    ) -> str:
        """Async version of _write_section.

        Args:
            section_name: Name of the section to write.
            topic: The research topic.
            outline: Framework outline dictionary.
            literature_context: Literature context for citations.

        Returns:
            Generated section content.
        """
        # Get the prompt template for this section
        prompt_template = SECTION_PROMPTS.get(section_name, "")
        if not prompt_template:
            return f"## {section_name.replace('_', ' ').title()}\n\nContent for {section_name} section."

        # Format the prompt
        prompt = prompt_template.format(
            topic=topic,
            outline=str(outline),
            literature_context=literature_context,
        )

        # Get section-specific guidance from outline if available
        section_guidance = outline.get("sections", {}).get(section_name, {})
        if section_guidance:
            guidance_str = f"\n\nAdditional guidance: {section_guidance}"
            prompt = prompt + guidance_str

        # Generate content using LLM service
        content = await self.llm_service.generate(prompt)

        return content
