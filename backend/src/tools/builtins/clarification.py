"""Clarification tool for asking user questions."""

from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class ClarificationInput(BaseModel):
    """Input for ask_clarification tool."""
    question: str = Field(description="The question to ask the user")
    options: Optional[list[str]] = Field(default=None, description="Optional list of choices")


@tool(args_schema=ClarificationInput)
async def ask_clarification_tool(
    question: str,
    options: Optional[list[str]] = None,
) -> str:
    """Ask the user for clarification.

    Use this tool when you need more information from the user before proceeding.
    This will interrupt the current task and wait for user input.

    Args:
        question: The question to ask
        options: Optional list of predefined choices

    Returns:
        The question (actual user response comes through conversation)
    """
    # This tool is intercepted by ClarificationMiddleware
    # The actual implementation interrupts the agent
    if options:
        options_str = "\n".join(f"  - {opt}" for opt in options)
        return f"{question}\n\nOptions:\n{options_str}"
    return question
