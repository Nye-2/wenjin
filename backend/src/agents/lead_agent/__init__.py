"""Lead agent package initialization."""

from .agent import apply_prompt_template, get_available_tools, make_lead_agent

__all__ = ["make_lead_agent", "apply_prompt_template", "get_available_tools"]
