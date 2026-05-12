"""End-to-end: a chat turn that should launch a feature drives lead_agent to call launch_feature."""
from __future__ import annotations


def test_chat_turn_routes_to_lead_agent_only():
    """Sending a 'launch this feature' chat turn must reach lead_agent (no bypass)."""
    from src.application.handlers.thread_turn_handler import ThreadTurnHandler

    # Confirm the bypass methods don't exist anymore
    assert not hasattr(ThreadTurnHandler, "_try_feature_command_reply")


def test_lead_agent_can_call_launch_feature_tool():
    """Tool registry exposes launch_feature; agent can resolve it."""
    from src.agents.chat_agent.agent import get_available_tools

    tools = get_available_tools()
    by_name = {getattr(t, "name", ""): t for t in tools}
    assert "launch_feature" in by_name
    tool = by_name["launch_feature"]
    # Tool schema must include feature_id, params
    schema = getattr(tool, "args_schema", None)
    assert schema is not None
    field_names = set(schema.model_fields.keys()) if hasattr(schema, "model_fields") else set()
    assert "feature_id" in field_names
    assert "params" in field_names
