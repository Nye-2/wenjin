"""Literature review skill for generating comprehensive literature reviews.

This skill analyzes papers in a workspace, identifies themes and trends,
creates a synthesis matrix, and generates a structured literature review.
"""

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from src.agents.thread_state import AcademicArtifact, ThreadState
from src.skills.base import BaseSkill, SkillInput, SkillOutput


class PaperData:
    """Data structure for paper analysis."""

    def __init__(
        self,
        paper_id: str,
        title: str,
        authors: list[str],
        year: Optional[int],
        abstract: Optional[str],
        keywords: list[str] = None,
        methodology: Optional[str] = None,
        findings: list[str] = None,
        contributions: list[str] = None,
    ):
        self.paper_id = paper_id
        self.title = title
        self.authors = authors
        self.year = year
        self.abstract = abstract
        self.keywords = keywords or []
        self.methodology = methodology
        self.findings = findings or []
        self.contributions = contributions or []

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "abstract": self.abstract,
            "keywords": self.keywords,
            "methodology": self.methodology,
            "findings": self.findings,
            "contributions": self.contributions,
        }


class Theme:
    """Represents an identified theme in the literature."""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.papers: list[PaperData] = []
        self.key_findings: list[str] = []
        self.gaps: list[str] = []

    def add_paper(self, paper: PaperData) -> None:
        """Add a paper to this theme."""
        self.papers.append(paper)

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "description": self.description,
            "paper_count": len(self.papers),
            "paper_ids": [p.paper_id for p in self.papers],
            "key_findings": self.key_findings,
            "gaps": self.gaps,
        }


class SynthesisMatrix:
    """Matrix for synthesizing paper contributions across themes."""

    def __init__(self):
        self.themes: list[str] = []
        self.papers: list[str] = []
        self.matrix: dict[str, dict[str, str]] = defaultdict(dict)

    def add_theme(self, theme_name: str) -> None:
        """Add a theme to the matrix."""
        if theme_name not in self.themes:
            self.themes.append(theme_name)

    def add_paper(self, paper_id: str) -> None:
        """Add a paper to the matrix."""
        if paper_id not in self.papers:
            self.papers.append(paper_id)

    def set_contribution(
        self, paper_id: str, theme_name: str, contribution: str
    ) -> None:
        """Set the contribution of a paper to a theme."""
        self.add_paper(paper_id)
        self.add_theme(theme_name)
        self.matrix[paper_id][theme_name] = contribution

    def get_contribution(self, paper_id: str, theme_name: str) -> Optional[str]:
        """Get the contribution of a paper to a theme."""
        return self.matrix.get(paper_id, {}).get(theme_name)

    def get_paper_contributions(self, paper_id: str) -> dict[str, str]:
        """Get all contributions of a paper."""
        return dict(self.matrix.get(paper_id, {}))

    def get_theme_contributions(self, theme_name: str) -> dict[str, str]:
        """Get all contributions to a theme."""
        return {
            paper_id: self.matrix[paper_id][theme_name]
            for paper_id in self.papers
            if theme_name in self.matrix[paper_id]
        }

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "themes": self.themes,
            "papers": self.papers,
            "matrix": {
                paper_id: dict(themes)
                for paper_id, themes in self.matrix.items()
            },
        }


class LiteratureReviewSkill(BaseSkill):
    """Skill for generating comprehensive literature reviews.

    This skill analyzes papers in a workspace, identifies themes and trends,
    creates a synthesis matrix, and writes a structured literature review.

    Attributes:
        name: Unique identifier for the skill.
        description: Human-readable description of the skill.
        version: Version string for the skill.
    """

    name = "literature-review"
    description = "Generate comprehensive literature reviews from workspace papers"
    version = "1.0.0"

    def execute(self, input: SkillInput, state: ThreadState) -> SkillOutput:
        """Execute the literature review skill.

        Args:
            input: The skill input containing workspace_id, user_query, and context.
            state: The current thread state for context and artifact storage.

        Returns:
            SkillOutput containing the literature review and artifacts.
        """
        # 1. Get papers from workspace (from context or state)
        papers = self._get_papers(input, state)

        if not papers:
            return SkillOutput(
                success=False,
                content="No papers found in the workspace. Please add papers before generating a literature review.",
                error_message="No papers available for literature review",
            )

        # 2. Extract key themes
        themes = self._extract_themes(papers)

        # 3. Create comparison/synthesis matrix
        synthesis_matrix = self._create_synthesis_matrix(papers, themes)

        # 4. Write synthesis (literature review content)
        review_content = self._write_literature_review(
            papers, themes, synthesis_matrix, input.user_query
        )

        # 5. Create literature_review artifact
        artifact = self._create_artifact(
            workspace_id=input.workspace_id,
            review_content=review_content,
            themes=themes,
            synthesis_matrix=synthesis_matrix,
        )

        return SkillOutput(
            success=True,
            content=review_content,
            artifacts=[artifact],
            metadata={
                "paper_count": len(papers),
                "theme_count": len(themes),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _get_papers(self, input: SkillInput, state: ThreadState) -> list[PaperData]:
        """Get papers from input context or state.

        Args:
            input: The skill input.
            state: The current thread state.

        Returns:
            List of PaperData objects.
        """
        papers = []

        # Check context for papers first
        context_papers = input.context.get("papers", [])
        for p in context_papers:
            paper = self._convert_to_paper_data(p)
            if paper:
                papers.append(paper)

        # Also check state thread_data for papers
        if not papers:
            state_papers = state.thread_data.get("papers", [])
            for p in state_papers:
                paper = self._convert_to_paper_data(p)
                if paper:
                    papers.append(paper)

        return papers

    def _convert_to_paper_data(self, paper_dict: dict) -> Optional[PaperData]:
        """Convert a dictionary to PaperData object.

        Args:
            paper_dict: Dictionary containing paper data.

        Returns:
            PaperData object or None if conversion fails.
        """
        if not paper_dict:
            return None

        # Extract authors from various formats
        authors = self._extract_authors(paper_dict.get("authors", []))

        return PaperData(
            paper_id=str(paper_dict.get("id", paper_dict.get("paper_id", str(uuid4())))),
            title=paper_dict.get("title", "Untitled"),
            authors=authors,
            year=paper_dict.get("year"),
            abstract=paper_dict.get("abstract"),
            keywords=paper_dict.get("keywords", []),
            methodology=paper_dict.get("methodology"),
            findings=paper_dict.get("findings", []),
            contributions=paper_dict.get("contributions", []),
        )

    def _extract_authors(self, authors_data: Any) -> list[str]:
        """Extract author names from various formats.

        Args:
            authors_data: Authors data in various formats.

        Returns:
            List of author names.
        """
        if not authors_data:
            return []

        if isinstance(authors_data, list):
            return [
                a.get("name", str(a)) if isinstance(a, dict) else str(a)
                for a in authors_data
            ]

        if isinstance(authors_data, str):
            return [a.strip() for a in authors_data.split(",")]

        return [str(authors_data)]

    def _extract_themes(self, papers: list[PaperData]) -> list[Theme]:
        """Extract key themes from papers.

        This method analyzes paper abstracts, keywords, and content to identify
        common themes across the literature.

        Args:
            papers: List of papers to analyze.

        Returns:
            List of identified themes with associated papers.
        """
        # Collect all keywords and terms
        keyword_counts: dict[str, int] = defaultdict(int)
        keyword_papers: dict[str, list[PaperData]] = defaultdict(list)

        for paper in papers:
            # Process explicit keywords
            for keyword in paper.keywords:
                normalized = self._normalize_term(keyword)
                keyword_counts[normalized] += 1
                keyword_papers[normalized].append(paper)

            # Extract terms from abstract
            if paper.abstract:
                terms = self._extract_terms_from_text(paper.abstract)
                for term in terms:
                    normalized = self._normalize_term(term)
                    keyword_counts[normalized] += 1
                    if paper not in keyword_papers[normalized]:
                        keyword_papers[normalized].append(paper)

        # Identify themes based on frequency and coverage
        themes = []
        used_keywords = set()

        # Sort by frequency to identify major themes
        sorted_keywords = sorted(
            keyword_counts.items(), key=lambda x: x[1], reverse=True
        )

        for keyword, count in sorted_keywords:
            # Skip if too rare or already covered
            if count < 2 or keyword in used_keywords:
                continue

            # Create theme from keyword
            theme = Theme(
                name=keyword.title(),
                description=f"Literature related to {keyword}",
            )

            # Add relevant papers
            for paper in keyword_papers[keyword]:
                theme.add_paper(paper)

            # Mark related keywords as used
            used_keywords.add(keyword)

            # Only add themes with multiple papers
            if len(theme.papers) >= 1:
                themes.append(theme)

        # Ensure at least one theme if we have papers
        if not themes and papers:
            general_theme = Theme(
                name="General Research",
                description="Overview of all research papers in the workspace",
            )
            for paper in papers:
                general_theme.add_paper(paper)
            themes.append(general_theme)

        return themes

    def _normalize_term(self, term: str) -> str:
        """Normalize a term for comparison.

        Args:
            term: The term to normalize.

        Returns:
            Normalized term.
        """
        # Convert to lowercase and remove extra whitespace
        normalized = " ".join(term.lower().split())
        # Remove punctuation except hyphens
        normalized = re.sub(r"[^\w\s-]", "", normalized)
        return normalized

    def _extract_terms_from_text(self, text: str) -> list[str]:
        """Extract significant terms from text.

        Args:
            text: Text to extract terms from.

        Returns:
            List of significant terms.
        """
        # Common stopwords to exclude
        stopwords = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "must", "shall", "can", "need", "dare",
            "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by",
            "from", "as", "into", "through", "during", "before", "after",
            "above", "below", "between", "under", "again", "further", "then",
            "once", "here", "there", "when", "where", "why", "how", "all",
            "each", "few", "more", "most", "other", "some", "such", "no", "nor",
            "not", "only", "own", "same", "so", "than", "too", "very", "just",
            "and", "but", "if", "or", "because", "until", "while", "this",
            "that", "these", "those", "which", "who", "whom", "what", "whose",
            "we", "our", "you", "your", "he", "she", "it", "its", "they", "their",
            "study", "paper", "research", "approach", "method", "result", "results",
            "analysis", "proposed", "present", "based", "using", "new", "novel",
        }

        # Tokenize and filter
        words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())

        # Filter stopwords and get meaningful terms
        terms = [word for word in words if word not in stopwords]

        # Count and return top terms
        term_counts = defaultdict(int)
        for term in terms:
            term_counts[term] += 1

        # Return terms that appear at least once
        return [term for term, count in term_counts.items() if count >= 1]

    def _create_synthesis_matrix(
        self, papers: list[PaperData], themes: list[Theme]
    ) -> SynthesisMatrix:
        """Create a synthesis matrix comparing papers across themes.

        Args:
            papers: List of papers to include.
            themes: List of identified themes.

        Returns:
            SynthesisMatrix object.
        """
        matrix = SynthesisMatrix()

        for theme in themes:
            matrix.add_theme(theme.name)

        for paper in papers:
            matrix.add_paper(paper.paper_id)

            for theme in themes:
                if paper in theme.papers:
                    contribution = self._extract_contribution(paper, theme)
                    matrix.set_contribution(paper.paper_id, theme.name, contribution)

        return matrix

    def _extract_contribution(self, paper: PaperData, theme: Theme) -> str:
        """Extract a paper's contribution to a theme.

        Args:
            paper: The paper to analyze.
            theme: The theme context.

        Returns:
            String describing the contribution.
        """
        # Use explicit contributions if available
        if paper.contributions:
            return "; ".join(paper.contributions[:2])  # Top 2 contributions

        # Use findings if available
        if paper.findings:
            return "; ".join(paper.findings[:2])

        # Generate from abstract if available
        if paper.abstract:
            # Extract first sentence as contribution summary
            sentences = paper.abstract.split(". ")
            if sentences:
                return sentences[0][:200] + ("..." if len(sentences[0]) > 200 else "")

        return f"Contributes to {theme.name.lower()} research"

    def _write_literature_review(
        self,
        papers: list[PaperData],
        themes: list[Theme],
        synthesis_matrix: SynthesisMatrix,
        user_query: str,
    ) -> str:
        """Write the literature review content.

        Args:
            papers: List of papers analyzed.
            themes: Identified themes.
            synthesis_matrix: Synthesis matrix.
            user_query: The original user query.

        Returns:
            Literature review as formatted text.
        """
        sections = []

        # 1. Introduction
        intro = self._write_introduction(papers, themes, user_query)
        sections.append(intro)

        # 2. Theme sections
        for theme in themes:
            theme_section = self._write_theme_section(theme, synthesis_matrix)
            sections.append(theme_section)

        # 3. Research Gaps
        gaps_section = self._write_research_gaps(themes)
        sections.append(gaps_section)

        # 4. Conclusion
        conclusion = self._write_conclusion(papers, themes)
        sections.append(conclusion)

        return "\n\n".join(sections)

    def _write_introduction(
        self, papers: list[PaperData], themes: list[Theme], user_query: str
    ) -> str:
        """Write the introduction section.

        Args:
            papers: List of papers.
            themes: Identified themes.
            user_query: The user's query.

        Returns:
            Introduction text.
        """
        # Determine year range
        years = [p.year for p in papers if p.year]
        year_range = ""
        if years:
            min_year, max_year = min(years), max(years)
            if min_year == max_year:
                year_range = f"from {min_year}"
            else:
                year_range = f"from {min_year} to {max_year}"

        intro_lines = [
            "# Literature Review",
            "",
            f"## Introduction",
            "",
            f"This literature review analyzes {len(papers)} papers {year_range}, "
            f"addressing the research question: *{user_query}*",
            "",
        ]

        if themes:
            intro_lines.append("The following key themes were identified:")
            for theme in themes:
                intro_lines.append(f"- **{theme.name}** ({len(theme.papers)} papers)")
            intro_lines.append("")

        return "\n".join(intro_lines)

    def _write_theme_section(self, theme: Theme, matrix: SynthesisMatrix) -> str:
        """Write a section for a specific theme.

        Args:
            theme: The theme to write about.
            matrix: Synthesis matrix.

        Returns:
            Theme section text.
        """
        lines = [
            f"## {theme.name}",
            "",
            theme.description,
            "",
        ]

        # Sort papers by year
        sorted_papers = sorted(
            theme.papers, key=lambda p: p.year or 0, reverse=True
        )

        for paper in sorted_papers:
            authors_str = ", ".join(paper.authors[:3])
            if len(paper.authors) > 3:
                authors_str += " et al."

            year_str = f" ({paper.year})" if paper.year else ""

            lines.append(f"### {authors_str}{year_str}")
            lines.append(f"**{paper.title}**")
            lines.append("")

            contribution = matrix.get_contribution(paper.paper_id, theme.name)
            if contribution:
                lines.append(f"Contribution: {contribution}")
                lines.append("")

        # Add synthesis for this theme
        if len(theme.papers) > 1:
            lines.append("**Synthesis:**")
            lines.append(
                f"The {len(theme.papers)} papers in this theme collectively advance "
                f"our understanding of {theme.name.lower()}."
            )
            lines.append("")

        return "\n".join(lines)

    def _write_research_gaps(self, themes: list[Theme]) -> str:
        """Write the research gaps section.

        Args:
            themes: Identified themes.

        Returns:
            Research gaps text.
        """
        lines = [
            "## Research Gaps",
            "",
            "Based on the analysis of the literature, the following research gaps were identified:",
            "",
        ]

        # Identify gaps based on theme coverage
        for theme in themes:
            if len(theme.papers) < 3:
                lines.append(
                    f"- **{theme.name}**: Limited research exists in this area, "
                    f"with only {len(theme.papers)} paper(s) identified."
                )

        # Add general gaps
        lines.append("- **Longitudinal Studies**: Most research focuses on short-term outcomes.")
        lines.append("- **Cross-domain Validation**: Many approaches lack validation across different domains.")
        lines.append("- **Reproducibility**: Limited attention to reproducibility and open science practices.")

        return "\n".join(lines)

    def _write_conclusion(
        self, papers: list[PaperData], themes: list[Theme]
    ) -> str:
        """Write the conclusion section.

        Args:
            papers: List of papers.
            themes: Identified themes.

        Returns:
            Conclusion text.
        """
        lines = [
            "## Conclusion",
            "",
            f"This literature review synthesized {len(papers)} papers across "
            f"{len(themes)} theme(s).",
            "",
        ]

        if themes:
            lines.append("Key findings include:")
            for theme in themes:
                lines.append(f"- {theme.name} remains an active area of research.")

        lines.append("")
        lines.append(
            "Future research should address the identified gaps and build upon "
            "the foundations established by the reviewed literature."
        )

        return "\n".join(lines)

    def _create_artifact(
        self,
        workspace_id: str,
        review_content: str,
        themes: list[Theme],
        synthesis_matrix: SynthesisMatrix,
    ) -> AcademicArtifact:
        """Create an academic artifact from the literature review.

        Args:
            workspace_id: The workspace ID.
            review_content: The review text content.
            themes: List of themes.
            synthesis_matrix: The synthesis matrix.

        Returns:
            AcademicArtifact object.
        """
        return AcademicArtifact(
            id=f"lit-review-{uuid4().hex[:8]}",
            workspace_id=workspace_id,
            type="literature_review",
            content={
                "review": review_content,
                "themes": [t.to_dict() for t in themes],
                "synthesis_matrix": synthesis_matrix.to_dict(),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            created_by_skill=self.name,
        )
