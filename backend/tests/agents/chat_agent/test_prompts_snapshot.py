"""Snapshot every prompt that ships to the LLM.

Updates require explicit reviewer approval of snapshot diff:
  uv run pytest tests/agents/lead_agent/test_prompts_snapshot.py --snapshot-update
"""
from src.agents.chat_agent.prompts import system as system_prompts


def test_lead_agent_system_prompt_sci(snapshot):
    rendered = system_prompts.render("sci")
    assert rendered == snapshot


def test_lead_agent_system_prompt_thesis(snapshot):
    rendered = system_prompts.render("thesis")
    assert rendered == snapshot


def test_system_prompt_mentions_block_kinds():
    rendered = system_prompts.render("sci")
    for kind in ("text", "status_line", "question_card", "result_card"):
        assert kind in rendered


def test_system_prompt_mentions_no_blacklist_tokens():
    from src.agents.chat_agent.prompts.jargon import BLACKLIST
    rendered = system_prompts.render("sci")
    # The prompt may mention blacklist tokens *as negative examples* explicitly
    # framed as "do not say". Forbid raw appearance in the body otherwise.
    body = rendered.split("# 反例")[0] if "# 反例" in rendered else rendered
    for token in BLACKLIST:
        assert token not in body, f"token {token!r} appears in prompt body"

from src.agents.chat_agent.prompts import skills as skill_prompts


def test_skill_paper_analyst_prompt(snapshot):
    rendered = skill_prompts.render("paper-analyst")
    assert rendered == snapshot


def test_skill_framework_designer_prompt(snapshot):
    rendered = skill_prompts.render("framework-designer")
    assert rendered == snapshot


def test_skill_unknown_returns_empty():
    assert skill_prompts.render("nonexistent") == ""
