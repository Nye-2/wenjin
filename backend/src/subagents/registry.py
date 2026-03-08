"""Subagent registry for managing subagent configurations."""

from dataclasses import dataclass, field


@dataclass
class SubagentConfig:
    """Configuration for a subagent type."""
    name: str
    description: str
    system_prompt: str
    allowed_tools: tuple = field(default_factory=tuple)
    max_turns: int = 10


# Academic subagent configurations
SCOUT_PROMPT = """You are Scout, a literature exploration agent.

Your mission is to discover and gather relevant academic papers:
1. Search for papers related to the research topic using semantic_scholar_search
2. Track citation chains to find influential works
3. Identify related papers through semantic similarity
4. Summarize key findings from discovered papers

Available tools:
- semantic_scholar_search: Search academic papers
- rag_retrieve: Search papers in current workspace

Always cite your sources and provide paper identifiers for tracking."""


WRITER_PROMPT = """You are Writer, an academic writing agent.

Your mission is to produce high-quality academic writing:
1. Follow the specified citation style (APA, IEEE, etc.)
2. Use academic language appropriate to the discipline
3. Structure content according to academic conventions
4. Ensure all claims are properly cited

Available tools:
- rag_retrieve: Search for relevant literature to cite
- read_file: Read existing drafts or outlines
- write_file: Write content to files

Always maintain academic integrity and proper attribution."""


SYNTHESIZER_PROMPT = """You are Synthesizer, a knowledge synthesis agent.

Your mission is to synthesize information from multiple sources:
1. Analyze patterns across papers
2. Identify research gaps and opportunities
3. Generate novel insights from existing literature
4. Create coherent summaries and syntheses

Available tools:
- rag_retrieve: Search literature for information
- read_file: Read existing artifacts

Focus on generating actionable insights and identifying connections."""


ANALYST_PROMPT = """You are Analyst, a data analysis agent.

Your mission is to perform data analysis and experimental design:
1. Design experimental methodologies
2. Analyze data patterns
3. Perform statistical analysis
4. Create visualizations and charts

Available tools:
- bash: Run analysis scripts
- read_file: Read data files
- write_file: Save analysis results

Ensure rigor and reproducibility in all analyses."""


# Default subagent configurations
DEFAULT_SUBAGENTS = {
    "scout": SubagentConfig(
        name="Scout",
        description="Literature exploration agent for discovering academic papers",
        system_prompt=SCOUT_PROMPT,
        allowed_tools=(
            "semantic_scholar_search",
            "rag_retrieve",
        ),
        max_turns=10,
    ),
    "writer": SubagentConfig(
        name="Writer",
        description="Academic writing agent for producing high-quality content",
        system_prompt=WRITER_PROMPT,
        allowed_tools=(
            "rag_retrieve",
            "read_file",
            "write_file",
        ),
        max_turns=15,
    ),
    "synthesizer": SubagentConfig(
        name="Synthesizer",
        description="Knowledge synthesis agent for generating insights",
        system_prompt=SYNTHESIZER_PROMPT,
        allowed_tools=(
            "rag_retrieve",
            "read_file",
        ),
        max_turns=10,
    ),
    "analyst": SubagentConfig(
        name="Analyst",
        description="Data analysis agent for experiments and statistics",
        system_prompt=ANALYST_PROMPT,
        allowed_tools=(
            "bash",
            "read_file",
            "write_file",
        ),
        max_turns=10,
    ),
}


class SubagentRegistry:
    """Registry for subagent configurations."""

    def __init__(self):
        """Initialize registry with default subagents."""
        self._subagents = dict(DEFAULT_SUBAGENTS)

    def get(self, subagent_type: str) -> SubagentConfig | None:
        """Get subagent configuration by type.

        Args:
            subagent_type: Type identifier (e.g., 'scout', 'writer')

        Returns:
            SubagentConfig if found, None otherwise
        """
        return self._subagents.get(subagent_type)

    def list_all(self) -> list[SubagentConfig]:
        """List all registered subagents.

        Returns:
            List of SubagentConfig objects
        """
        return list(self._subagents.values())

    def register(self, config: SubagentConfig) -> None:
        """Register a new subagent configuration.

        Args:
            config: SubagentConfig to register
        """
        key = config.name.lower()
        self._subagents[key] = config

    def unregister(self, subagent_type: str) -> bool:
        """Unregister a subagent.

        Args:
            subagent_type: Type to unregister

        Returns:
            True if unregistered, False if not found
        """
        if subagent_type in self._subagents:
            del self._subagents[subagent_type]
            return True
        return False


# Global registry instance
registry = SubagentRegistry()
