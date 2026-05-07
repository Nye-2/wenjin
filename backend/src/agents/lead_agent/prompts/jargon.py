"""Black-list of tokens that must never appear in user-facing agent output.

Sourced from real bug reports (spec §1.1). Used both to:
1. Lint LLM responses post-parse (enforced in tests).
2. Negative examples in the system prompt itself.
"""
from src.agents.lead_agent.blocks import (
    AgentMessage,
    QuestionCardBlock,
    ResultCardBlock,
    StatusLineBlock,
    TextBlock,
)

BLACKLIST: tuple[str, ...] = (
    # Internal taxonomy tokens
    "message_feature_proposal",
    "意图置信度",
    # Self-narration phrases
    "我会先复用",
    "将进入",
    "识别依据",
    "执行链路",
    # Debug fields (turn count, node names — partial matches caught by callers)
)


def _strings_in_block(block) -> list[str]:
    if isinstance(block, TextBlock):
        return [block.content]
    if isinstance(block, StatusLineBlock):
        return [block.label]
    if isinstance(block, QuestionCardBlock):
        return [block.label, block.question, *(p.label for p in block.pills)]
    if isinstance(block, ResultCardBlock):
        return [
            block.title,
            block.tldr,
            *(f.text for f in block.findings),
            *((block.recommend.label, block.recommend.body) if block.recommend else ()),
            block.feedback.question,
            *(p.label for p in block.feedback.pills),
        ]
    return []


def assert_no_jargon(msg: AgentMessage) -> None:
    """Raise AssertionError naming the offending token if any blacklist hit found."""
    for block in msg.blocks:
        for s in _strings_in_block(block):
            for token in BLACKLIST:
                if token in s:
                    raise AssertionError(
                        f"jargon `{token}` leaked into agent output: {s!r}"
                    )
