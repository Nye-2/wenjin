"""Clusterer subagent — V1 stub that groups papers into thematic clusters."""

from ..base import SubagentBase, SubagentContext, SubagentResult
from ..registry import subagent


@subagent("clusterer")
class Clusterer(SubagentBase):
    """Groups a list of papers into thematic clusters.

    Required inputs:
        papers (list[dict]): List of paper dicts, each with at minimum an 'id' or 'title'.
            Each paper may have a 'year' field used to bucket into clusters.

    Output shape::

        {
            "clusters": [
                {"theme": str, "paper_ids": [str]},
                ...
            ]
        }

    V1 stub: buckets papers into 1-2 year-based clusters.
        - Papers with year < 2022 → "Foundational Works"
        - Papers with year >= 2022 → "Recent Advances"
        - Papers without a year → appended to whichever cluster is non-empty, or "Uncategorised"
    """

    allowed_tools = []

    async def run(self, ctx: SubagentContext) -> SubagentResult:
        papers = ctx.inputs.get("papers")
        if papers is None:
            raise ValueError("clusterer requires 'papers' in inputs")
        if not isinstance(papers, list):
            raise ValueError("clusterer: 'papers' must be a list")

        foundational: list[str] = []
        recent: list[str] = []
        uncategorised: list[str] = []

        for i, paper in enumerate(papers):
            paper_id = str(paper.get("id", paper.get("title", f"paper_{i}")))
            year = paper.get("year")
            if year is None:
                uncategorised.append(paper_id)
            elif int(year) < 2022:
                foundational.append(paper_id)
            else:
                recent.append(paper_id)

        # If uncategorised papers exist, merge them into whichever cluster has items,
        # or keep them separate if both clusters are empty.
        if uncategorised:
            if recent:
                recent.extend(uncategorised)
            elif foundational:
                foundational.extend(uncategorised)
            # else: will appear as separate cluster below

        clusters = []
        if foundational:
            clusters.append({"theme": "Foundational Works", "paper_ids": foundational})
        if recent:
            clusters.append({"theme": "Recent Advances", "paper_ids": recent})
        if uncategorised and not foundational and not recent:
            clusters.append({"theme": "Uncategorised", "paper_ids": uncategorised})

        # Always produce at least one cluster
        if not clusters:
            clusters.append({"theme": "All Papers", "paper_ids": []})

        return SubagentResult(
            output={"clusters": clusters},
            tool_calls=[],
            token_usage={"input": 0, "output": 0},
        )
