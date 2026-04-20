"""Tests for lazy MCP bootstrap in langgraph entry."""

from unittest.mock import MagicMock, patch


def test_module_import_does_not_call_activate_mcp():
    """Importing langgraph_entry should NOT trigger MCP activate."""
    with patch("src.mcp.activate_mcp_runtime") as mock_activate:
        import src.agents.lead_agent.langgraph_entry as entry_module
        # Reset module state
        entry_module._bootstrapped = False
        # The import itself should not have called activate
        mock_activate.assert_not_called()


def test_ensure_bootstrapped_calls_activate_once():
    """_ensure_bootstrapped should call activate_mcp_runtime exactly once."""
    import src.agents.lead_agent.langgraph_entry as entry_module
    entry_module._bootstrapped = False

    with patch.object(entry_module, "activate_mcp_runtime"), \
         patch.object(entry_module, "get_extensions_config", return_value={}), \
         patch.object(entry_module, "asyncio") as mock_asyncio:
        # Simulate no running loop (RuntimeError on get_running_loop)
        mock_asyncio.get_running_loop.side_effect = RuntimeError
        mock_asyncio.run = MagicMock()

        entry_module._ensure_bootstrapped()
        entry_module._ensure_bootstrapped()  # Second call should be no-op

        mock_asyncio.run.assert_called_once()


def test_make_lead_agent_graph_triggers_bootstrap():
    """make_lead_agent_graph should call _ensure_bootstrapped."""
    import src.agents.lead_agent.langgraph_entry as entry_module

    with patch.object(entry_module, "_ensure_bootstrapped") as mock_boot, \
         patch.object(entry_module, "make_lead_agent"):
        entry_module.make_lead_agent_graph({"configurable": {}})
        mock_boot.assert_called_once()
