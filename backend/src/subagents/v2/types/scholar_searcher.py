"""ScholarSearcher subagent — V1 stub that returns fake papers for a given topic."""

from ..base import SubagentBase, SubagentContext, SubagentResult
from ..registry import subagent


@subagent("scholar_searcher")
class ScholarSearcher(SubagentBase):
    """Searches academic literature for papers matching a topic.

    Required inputs:
        topic (str): The research topic to search for.

    Output shape::

        {
            "papers": [
                {"title": str, "authors": [str], "year": int, "doi": str | None},
                ...
            ]
        }

    V1 stub: returns 3 fake papers derived from the topic string.
    """

    allowed_tools = ["scholar_search", "web_search"]

    async def run(self, ctx: SubagentContext) -> SubagentResult:
        topic = ctx.inputs.get("topic")
        if not topic:
            raise ValueError("scholar_searcher requires 'topic' in inputs")

        papers = [
            {
                "title": f"A Survey of {topic}: Foundations and Recent Advances",
                "authors": ["Smith, J.", "Lee, A.", "Wang, B."],
                "year": 2023,
                "doi": "10.1234/stub-doi-001",
            },
            {
                "title": f"Towards Scalable {topic}: Challenges and Opportunities",
                "authors": ["Johnson, R.", "Chen, X."],
                "year": 2022,
                "doi": "10.1234/stub-doi-002",
            },
            {
                "title": f"Empirical Evaluation of {topic} Methods",
                "authors": ["Patel, S.", "Kim, Y.", "Garcia, M."],
                "year": 2024,
                "doi": None,
            },
        ]

        return SubagentResult(
            output={"papers": papers},
            tool_calls=[],
            token_usage={"input": 0, "output": 0},
        )
