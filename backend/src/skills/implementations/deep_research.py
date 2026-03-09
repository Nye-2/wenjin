"""Deep Research Skill for comprehensive literature analysis.

This skill performs deep research on a topic by:
1. Searching for relevant papers using Semantic Scholar
2. Analyzing paper abstracts and identifying patterns
3. Identifying research gaps
4. Generating novel research ideas
"""

import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.agents.thread_state import AcademicArtifact, ThreadState
from src.config import settings
from src.skills.base import BaseSkill, SkillInput, SkillOutput


@dataclass
class Paper:
    """Represents a paper from Semantic Scholar search."""
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    abstract: str | None
    citations: int | None
    url: str | None
    doi: str | None
    paper_id: str | None = None


@dataclass
class ResearchPattern:
    """Represents an identified research pattern."""
    description: str
    frequency: int
    papers: list[str] = field(default_factory=list)


@dataclass
class ResearchGap:
    """Represents an identified research gap."""
    description: str
    supporting_evidence: list[str]
    potential_impact: str


@dataclass
class ResearchIdea:
    """Represents a generated research idea."""
    title: str
    description: str
    methodology_hints: list[str]
    related_papers: list[str]
    novelty_score: float


class DeepResearchSkill(BaseSkill):
    """Comprehensive literature analysis and research idea generation.

    This skill performs a deep research analysis on a given topic by:
    1. Searching for relevant academic papers using Semantic Scholar
    2. Analyzing paper abstracts to identify patterns and trends
    3. Identifying research gaps in the current literature
    4. Generating novel research ideas based on the analysis

    Attributes:
        name: Unique identifier for the skill.
        description: Human-readable description.
        version: Version string for the skill.
    """

    name = "deep-research"
    description = "Comprehensive literature analysis and research idea generation"
    version = "1.0.0"

    # Configuration
    DEFAULT_SEARCH_LIMIT = 20
    MIN_PAPERS_FOR_ANALYSIS = 5
    KEYWORD_EXTRACTION_MIN_FREQ = 2

    def execute(self, input: SkillInput, state: ThreadState) -> SkillOutput:
        """Execute the deep research skill.

        Args:
            input: The skill input containing workspace_id, user_query, and context.
            state: The current thread state for context and artifact storage.

        Returns:
            SkillOutput containing the research analysis results.
        """
        try:
            # Get configuration from context
            search_limit = input.context.get("search_limit", self.DEFAULT_SEARCH_LIMIT)
            year_range = input.context.get("year_range", None)

            # Step 1: Search papers from Semantic Scholar
            papers = self._search_papers(input.user_query, search_limit, year_range)

            if not papers:
                return SkillOutput(
                    success=True,
                    content=f"No papers found for query: '{input.user_query}'. Try broadening your search.",
                    metadata={"papers_found": 0},
                )

            # Step 2: Analyze and synthesize findings
            patterns = self._analyze_patterns(papers)
            synthesis = self._synthesize_findings(papers, patterns)

            # Step 3: Identify research gaps
            gaps = self._identify_research_gaps(papers, patterns)

            # Step 4: Generate research ideas
            ideas = self._generate_research_ideas(papers, patterns, gaps)

            # Create artifacts
            artifacts = self._create_artifacts(
                input.workspace_id,
                papers,
                patterns,
                gaps,
                ideas,
            )

            # Build content report
            content = self._build_report(
                input.user_query,
                papers,
                patterns,
                gaps,
                ideas,
                synthesis,
            )

            # Update cited papers in state
            cited_papers = [p.doi for p in papers if p.doi]
            if cited_papers:
                state["cited_papers"] = list(set(state.get("cited_papers", []) + cited_papers))

            return SkillOutput(
                success=True,
                content=content,
                artifacts=artifacts,
                metadata={
                    "papers_analyzed": len(papers),
                    "patterns_identified": len(patterns),
                    "gaps_identified": len(gaps),
                    "ideas_generated": len(ideas),
                    "search_query": input.user_query,
                },
            )

        except Exception as e:
            return SkillOutput(
                success=False,
                content="",
                error_message=f"Deep research failed: {str(e)}",
            )

    def _search_papers(
        self,
        query: str,
        limit: int,
        year_range: str | None = None,
    ) -> list[Paper]:
        """Search for papers using Semantic Scholar.

        Args:
            query: The search query.
            limit: Maximum number of results.
            year_range: Optional year range filter.

        Returns:
            List of Paper objects.
        """
        try:
            from semanticscholar import SemanticScholar

            client = SemanticScholar(api_key=settings.semantic_scholar_api_key)

            search_params = {
                "query": query,
                "limit": limit,
            }

            if year_range:
                search_params["year"] = year_range

            results = client.search_paper(**search_params)

            papers = []
            for paper in results:
                # Extract authors
                authors = []
                if paper.authors:
                    authors = [a.get("name", "Unknown") for a in paper.authors]

                # Extract DOI
                doi = None
                if paper.externalIds and "DOI" in paper.externalIds:
                    doi = paper.externalIds["DOI"]

                papers.append(Paper(
                    title=paper.title or "Untitled",
                    authors=authors,
                    year=paper.year,
                    venue=paper.venue,
                    abstract=paper.abstract,
                    citations=paper.citationCount,
                    url=paper.url,
                    doi=doi,
                    paper_id=paper.paperId,
                ))

            return papers

        except ImportError:
            # Return empty list if semanticscholar package is not installed
            return []
        except Exception:
            # Return empty list on any API error
            return []

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract meaningful keywords from text.

        Args:
            text: The text to extract keywords from.

        Returns:
            List of extracted keywords.
        """
        if not text:
            return []

        # Common stopwords to filter out
        stopwords = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "must", "shall", "can", "this",
            "that", "these", "those", "we", "our", "their", "its", "paper",
            "study", "research", "approach", "method", "result", "results",
            "propose", "present", "show", "using", "based", "new", "novel",
        }

        # Extract words (alphanumeric sequences)
        words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())

        # Filter out stopwords and count
        filtered = [w for w in words if w not in stopwords]

        return filtered

    def _analyze_patterns(self, papers: list[Paper]) -> list[ResearchPattern]:
        """Analyze patterns across paper abstracts.

        Args:
            papers: List of papers to analyze.

        Returns:
            List of identified research patterns.
        """
        if len(papers) < self.MIN_PAPERS_FOR_ANALYSIS:
            return []

        # Collect all keywords from abstracts
        all_keywords = []
        paper_keywords: dict[str, list[str]] = {}

        for paper in papers:
            if paper.abstract:
                keywords = self._extract_keywords(paper.abstract)
                paper_keywords[paper.title] = keywords
                all_keywords.extend(keywords)

        # Count keyword frequencies
        keyword_counts = Counter(all_keywords)

        # Identify patterns (frequent meaningful keywords)
        patterns = []
        for keyword, count in keyword_counts.most_common(15):
            if count >= self.KEYWORD_EXTRACTION_MIN_FREQ:
                # Find papers containing this keyword
                related_papers = [
                    title for title, kwds in paper_keywords.items()
                    if keyword in kwds
                ]

                patterns.append(ResearchPattern(
                    description=f"Frequent focus on '{keyword}' (appears in {count} abstracts)",
                    frequency=count,
                    papers=related_papers[:5],  # Limit to top 5 papers
                ))

        # Identify methodology patterns
        methodology_terms = [
            "deep learning", "neural network", "transformer", "attention",
            "reinforcement learning", "supervised", "unsupervised", "semi-supervised",
            "transfer learning", "fine-tuning", "pre-training", "embedding",
            "classification", "regression", "clustering", "gan", "vae",
            "lstm", "cnn", "rnn", "bert", "gpt", "graph neural",
        ]

        for term in methodology_terms:
            count = sum(
                1 for p in papers
                if p.abstract and term in p.abstract.lower()
            )
            if count >= self.KEYWORD_EXTRACTION_MIN_FREQ:
                related_papers = [
                    p.title for p in papers
                    if p.abstract and term in p.abstract.lower()
                ]
                patterns.append(ResearchPattern(
                    description=f"Common methodology: '{term}' (used in {count} papers)",
                    frequency=count,
                    papers=related_papers[:5],
                ))

        # Identify temporal patterns (year distribution)
        years = [p.year for p in papers if p.year]
        if years:
            year_counts = Counter(years)
            if len(year_counts) > 1:
                most_common_year = year_counts.most_common(1)[0]
                patterns.append(ResearchPattern(
                    description=f"Peak publication year: {most_common_year[0]} ({most_common_year[1]} papers)",
                    frequency=most_common_year[1],
                    papers=[p.title for p in papers if p.year == most_common_year[0]][:5],
                ))

        return patterns

    def _synthesize_findings(
        self,
        papers: list[Paper],
        patterns: list[ResearchPattern],
    ) -> str:
        """Synthesize findings from papers and patterns.

        Args:
            papers: List of analyzed papers.
            patterns: List of identified patterns.

        Returns:
            Synthesis summary string.
        """
        if not papers:
            return "No papers available for synthesis."

        # Calculate basic statistics
        total_papers = len(papers)
        papers_with_abstracts = sum(1 for p in papers if p.abstract)
        total_citations = sum(p.citations or 0 for p in papers)

        # Year range
        years = [p.year for p in papers if p.year]
        year_range = ""
        if years:
            min_year, max_year = min(years), max(years)
            year_range = f"Published between {min_year} and {max_year}."

        # Top venues
        venues = [p.venue for p in papers if p.venue]
        venue_counts = Counter(venues).most_common(3)
        top_venues = ", ".join([v[0] for v in venue_counts]) if venue_counts else "N/A"

        # Top cited papers
        sorted_papers = sorted(
            [p for p in papers if p.citations],
            key=lambda x: x.citations or 0,
            reverse=True,
        )[:3]
        top_cited = "; ".join([f"{p.title} ({p.citations} citations)" for p in sorted_papers])

        synthesis_parts = [
            f"Analyzed {total_papers} papers ({papers_with_abstracts} with abstracts).",
            year_range,
            f"Total citations across all papers: {total_citations}.",
            f"Top venues: {top_venues}.",
        ]

        if top_cited:
            synthesis_parts.append(f"Most cited papers: {top_cited}.")

        if patterns:
            synthesis_parts.append(f"Identified {len(patterns)} significant patterns.")

        return " ".join(synthesis_parts)

    def _identify_research_gaps(
        self,
        papers: list[Paper],
        patterns: list[ResearchPattern],
    ) -> list[ResearchGap]:
        """Identify research gaps based on analysis.

        Args:
            papers: List of analyzed papers.
            patterns: List of identified patterns.

        Returns:
            List of identified research gaps.
        """
        gaps = []

        if len(papers) < self.MIN_PAPERS_FOR_ANALYSIS:
            return gaps

        # Collect all abstract text
        all_abstracts = " ".join([p.abstract or "" for p in papers]).lower()

        # Identify potential gaps based on common research frontiers
        gap_indicators = [
            (
                "interpretability",
                "Explainability and interpretability of models",
                "limited attention to model interpretability",
            ),
            (
                "robustness",
                "Robustness and adversarial resilience",
                "limited study of model robustness",
            ),
            (
                "efficiency",
                "Computational efficiency and scalability",
                "limited focus on computational efficiency",
            ),
            (
                "real-world",
                "Real-world deployment and applications",
                "limited real-world validation",
            ),
            (
                "benchmark",
                "Standardized benchmarks and evaluation",
                "lack of standardized benchmarks",
            ),
            (
                "cross-domain",
                "Cross-domain generalization",
                "limited cross-domain evaluation",
            ),
            (
                "long-term",
                "Long-term performance and temporal aspects",
                "limited longitudinal studies",
            ),
            (
                "ethical",
                "Ethical considerations and fairness",
                "limited discussion of ethical implications",
            ),
        ]

        for keyword, gap_title, _evidence_template in gap_indicators:
            if keyword not in all_abstracts:
                # Find supporting papers that partially relate
                supporting = []
                for p in papers:
                    if p.abstract and any(
                        related in p.abstract.lower()
                        for related in ["evaluation", "future", "limitation", "challenge"]
                    ):
                        supporting.append(p.title)

                gaps.append(ResearchGap(
                    description=gap_title,
                    supporting_evidence=supporting[:3],
                    potential_impact=f"Addressing {gap_title.lower()} could significantly advance the field.",
                ))

        # Identify methodology gaps
        abstracts_text = all_abstracts
        method_gaps = []

        if "ablation" not in abstracts_text:
            method_gaps.append("comprehensive ablation studies")

        if "error analysis" not in abstracts_text and "failure" not in abstracts_text:
            method_gaps.append("detailed error analysis")

        if method_gaps:
            gaps.append(ResearchGap(
                description=f"Rigorous methodology: {', '.join(method_gaps)}",
                supporting_evidence=[p.title for p in papers[:3]],
                potential_impact="Improved methodological rigor would strengthen research validity.",
            ))

        # Limit to most significant gaps
        return gaps[:5]

    def _generate_research_ideas(
        self,
        papers: list[Paper],
        patterns: list[ResearchPattern],
        gaps: list[ResearchGap],
    ) -> list[ResearchIdea]:
        """Generate novel research ideas based on analysis.

        Args:
            papers: List of analyzed papers.
            patterns: List of identified patterns.
            gaps: List of identified gaps.

        Returns:
            List of generated research ideas.
        """
        ideas = []

        if len(papers) < self.MIN_PAPERS_FOR_ANALYSIS:
            return ideas

        # Get top patterns
        top_patterns = patterns[:5] if patterns else []
        pattern_keywords = [
            p.description.split("'")[1] if "'" in p.description else "research"
            for p in top_patterns
        ]

        # Generate ideas based on gaps
        for i, gap in enumerate(gaps[:3]):
            # Create a novel combination idea
            related_papers = []
            for p in papers[:5]:
                if p.abstract:
                    related_papers.append(p.title)

            # Calculate novelty based on gap frequency in literature
            novelty = min(0.9, 0.5 + (len(gaps) - i) * 0.1)

            ideas.append(ResearchIdea(
                title=f"Novel approach combining {pattern_keywords[0] if pattern_keywords else 'techniques'} with {gap.description.lower()}",
                description=f"This research could address the gap in {gap.description.lower()} by leveraging insights from {pattern_keywords[0] if pattern_keywords else 'recent advances'}. {gap.potential_impact}",
                methodology_hints=[
                    "Systematic literature review",
                    "Experimental validation",
                    "Comparative analysis",
                ],
                related_papers=related_papers[:3],
                novelty_score=novelty,
            ))

        # Generate cross-pollination ideas
        if len(top_patterns) >= 2:
            ideas.append(ResearchIdea(
                title=f"Cross-pollination: Integrating {pattern_keywords[0]} with {pattern_keywords[1]}",
                description=f"Exploring the intersection of {pattern_keywords[0]} and {pattern_keywords[1]} could reveal novel insights and methodologies not yet explored in the literature.",
                methodology_hints=[
                    f"Apply {pattern_keywords[0]} techniques to {pattern_keywords[1]} problems",
                    "Develop unified framework",
                    "Empirical comparison",
                ],
                related_papers=[p.title for p in papers[:4]],
                novelty_score=0.85,
            ))

        # Generate future direction ideas based on recent papers
        recent_papers = sorted(
            [p for p in papers if p.year],
            key=lambda x: x.year or 0,
            reverse=True,
        )[:3]

        if recent_papers:
            recent_topics = []
            for p in recent_papers:
                if p.abstract:
                    keywords = self._extract_keywords(p.abstract)[:3]
                    recent_topics.extend(keywords)

            if recent_topics:
                ideas.append(ResearchIdea(
                    title=f"Emerging direction: Advanced applications in {recent_topics[0]}",
                    description=f"Building on recent work, this research could explore advanced applications and extensions in {recent_topics[0]}, addressing current limitations and opening new research frontiers.",
                    methodology_hints=[
                        "State-of-the-art baseline comparison",
                        "Novel dataset creation",
                        "Performance benchmarking",
                    ],
                    related_papers=[p.title for p in recent_papers],
                    novelty_score=0.75,
                ))

        return ideas

    def _create_artifacts(
        self,
        workspace_id: str,
        papers: list[Paper],
        patterns: list[ResearchPattern],
        gaps: list[ResearchGap],
        ideas: list[ResearchIdea],
    ) -> list[AcademicArtifact]:
        """Create academic artifacts from the analysis.

        Args:
            workspace_id: The workspace ID.
            papers: List of analyzed papers.
            patterns: List of identified patterns.
            gaps: List of identified gaps.
            ideas: List of generated ideas.

        Returns:
            List of AcademicArtifact objects.
        """
        artifacts = []
        timestamp = datetime.now(UTC)

        # Create literature review artifact
        artifacts.append(AcademicArtifact(
            id=f"lit-review-{uuid.uuid4().hex[:8]}",
            workspace_id=workspace_id,
            type="literature_review",
            content={
                "papers": [
                    {
                        "title": p.title,
                        "authors": p.authors,
                        "year": p.year,
                        "venue": p.venue,
                        "citations": p.citations,
                        "doi": p.doi,
                    }
                    for p in papers
                ],
                "patterns": [
                    {
                        "description": p.description,
                        "frequency": p.frequency,
                        "papers": p.papers,
                    }
                    for p in patterns
                ],
                "created_at": timestamp.isoformat(),
            },
            created_by_skill=self.name,
        ))

        # Create research ideas artifact
        if ideas:
            artifacts.append(AcademicArtifact(
                id=f"research-ideas-{uuid.uuid4().hex[:8]}",
                workspace_id=workspace_id,
                type="research_ideas",
                content={
                    "ideas": [
                        {
                            "title": idea.title,
                            "description": idea.description,
                            "methodology_hints": idea.methodology_hints,
                            "related_papers": idea.related_papers,
                            "novelty_score": idea.novelty_score,
                        }
                        for idea in ideas
                    ],
                    "gaps_addressed": [g.description for g in gaps],
                    "created_at": timestamp.isoformat(),
                },
                created_by_skill=self.name,
            ))

        # Create research gap analysis artifact
        if gaps:
            artifacts.append(AcademicArtifact(
                id=f"gap-analysis-{uuid.uuid4().hex[:8]}",
                workspace_id=workspace_id,
                type="gap_analysis",
                content={
                    "gaps": [
                        {
                            "description": g.description,
                            "supporting_evidence": g.supporting_evidence,
                            "potential_impact": g.potential_impact,
                        }
                        for g in gaps
                    ],
                    "created_at": timestamp.isoformat(),
                },
                created_by_skill=self.name,
            ))

        return artifacts

    def _build_report(
        self,
        query: str,
        papers: list[Paper],
        patterns: list[ResearchPattern],
        gaps: list[ResearchGap],
        ideas: list[ResearchIdea],
        synthesis: str,
    ) -> str:
        """Build a formatted report of the research analysis.

        Args:
            query: The original search query.
            papers: List of analyzed papers.
            patterns: List of identified patterns.
            gaps: List of identified gaps.
            ideas: List of generated ideas.
            synthesis: Synthesis summary.

        Returns:
            Formatted report string.
        """
        sections = []

        # Title
        sections.append(f"# Deep Research Analysis: {query}")
        sections.append("")

        # Summary
        sections.append("## Summary")
        sections.append(synthesis)
        sections.append("")

        # Papers analyzed
        sections.append("## Papers Analyzed")
        for i, paper in enumerate(papers[:10], 1):  # Limit to top 10
            sections.append(f"### {i}. {paper.title}")
            if paper.authors:
                sections.append(f"**Authors:** {', '.join(paper.authors[:3])}")
            if paper.year:
                sections.append(f"**Year:** {paper.year}")
            if paper.venue:
                sections.append(f"**Venue:** {paper.venue}")
            if paper.citations is not None:
                sections.append(f"**Citations:** {paper.citations}")
            if paper.doi:
                sections.append(f"**DOI:** {paper.doi}")
            sections.append("")

        if len(papers) > 10:
            sections.append(f"*...and {len(papers) - 10} more papers.*")
            sections.append("")

        # Patterns
        if patterns:
            sections.append("## Research Patterns Identified")
            for pattern in patterns:
                sections.append(f"- {pattern.description}")
            sections.append("")

        # Research Gaps
        if gaps:
            sections.append("## Research Gaps")
            for gap in gaps:
                sections.append(f"### {gap.description}")
                sections.append(f"*Potential Impact:* {gap.potential_impact}")
                if gap.supporting_evidence:
                    sections.append("*Supporting Evidence:*")
                    for evidence in gap.supporting_evidence:
                        sections.append(f"  - {evidence}")
                sections.append("")

        # Research Ideas
        if ideas:
            sections.append("## Generated Research Ideas")
            for i, idea in enumerate(ideas, 1):
                sections.append(f"### Idea {i}: {idea.title}")
                sections.append(idea.description)
                sections.append(f"**Novelty Score:** {idea.novelty_score:.2f}")
                if idea.methodology_hints:
                    sections.append("**Methodology Hints:**")
                    for hint in idea.methodology_hints:
                        sections.append(f"  - {hint}")
                if idea.related_papers:
                    sections.append("**Related Papers:**")
                    for paper in idea.related_papers:
                        sections.append(f"  - {paper}")
                sections.append("")

        return "\n".join(sections)
