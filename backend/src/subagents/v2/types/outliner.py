"""Outliner subagent — V1 stub that generates a 3-section outline for a topic."""

from ..base import SubagentBase, SubagentContext, SubagentResult
from ..registry import subagent


@subagent("outliner")
class Outliner(SubagentBase):
    """Generates a structured outline for a research topic.

    Required inputs:
        topic (str): The research topic to outline.

    Output shape::

        {
            "outline": [
                {"section": str, "subsections": [str]},
                ...
            ]
        }

    V1 stub: returns 3 sections with templated subsection names.
    """

    allowed_tools = []

    async def run(self, ctx: SubagentContext) -> SubagentResult:
        topic = ctx.inputs.get("topic")
        if not topic:
            raise ValueError("outliner requires 'topic' in inputs")

        outline = [
            {
                "section": f"Introduction to {topic}",
                "subsections": [
                    "Background and Motivation",
                    f"Scope and Definitions of {topic}",
                    "Research Questions",
                ],
            },
            {
                "section": f"Literature Review: {topic}",
                "subsections": [
                    "Foundational Contributions",
                    "Recent Advances",
                    "Identified Gaps",
                ],
            },
            {
                "section": f"Conclusions and Future Directions for {topic}",
                "subsections": [
                    "Summary of Findings",
                    "Limitations",
                    "Recommendations for Future Work",
                ],
            },
        ]

        return SubagentResult(
            output={"outline": outline},
            tool_calls=[],
            token_usage={"input": 0, "output": 0},
        )
