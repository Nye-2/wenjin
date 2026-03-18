"""LangGraph entrypoints with strict signatures required by langgraph-api."""

from langchain_core.runnables import RunnableConfig

from src.agents.lead_agent.agent import make_lead_agent


def make_lead_agent_graph(config: RunnableConfig):
    """Create the lead agent graph with langgraph-api compatible signature."""
    return make_lead_agent(config)
