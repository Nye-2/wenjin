"""WebSearcher subagent — V1 stub that returns fake web results for a query."""

from ..base import SubagentBase, SubagentContext, SubagentResult
from ..registry import subagent


@subagent("web_searcher")
class WebSearcher(SubagentBase):
    """Searches the web for information matching a query.

    Required inputs:
        query (str): The search query.

    Output shape::

        {
            "results": [
                {"title": str, "url": str, "snippet": str},
                ...
            ]
        }

    V1 stub: returns 3 fake results derived from the query string.
    """

    allowed_tools = ["web_search", "fetch_url"]

    async def run(self, ctx: SubagentContext) -> SubagentResult:
        query = ctx.inputs.get("query")
        if not query:
            raise ValueError("web_searcher requires 'query' in inputs")

        results = [
            {
                "title": f"{query} — Overview and Introduction",
                "url": f"https://example.com/stub/overview",
                "snippet": f"A comprehensive overview of {query}, covering key concepts and applications.",
            },
            {
                "title": f"Latest Developments in {query}",
                "url": f"https://example.com/stub/latest",
                "snippet": f"Recent news and research breakthroughs related to {query}.",
            },
            {
                "title": f"{query}: Practical Guide",
                "url": f"https://example.com/stub/guide",
                "snippet": f"Step-by-step practical guide for working with {query} in real-world settings.",
            },
        ]

        return SubagentResult(
            output={"results": results},
            tool_calls=[],
            token_usage={"input": 0, "output": 0},
        )
