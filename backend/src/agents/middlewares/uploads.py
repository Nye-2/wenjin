"""Uploads middleware - injects uploaded file metadata into conversation."""

from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


class UploadsMiddleware(Middleware):
    """Tracks and injects uploaded files into the last HumanMessage."""

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        uploaded_files = state.get("uploaded_files")
        if not uploaded_files:
            return {}

        messages = list(state.get("messages", []))
        if not messages:
            return {}

        # Find last HumanMessage
        last_human_idx = None
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], HumanMessage):
                last_human_idx = i
                break

        if last_human_idx is None:
            return {}

        # Build file listing
        file_listing = "\n<uploaded_files>\n"
        for f in uploaded_files:
            name = f.get("name", "unknown")
            path = f.get("path", "")
            size = f.get("size", 0)
            file_listing += f"- {name} ({size} bytes): {path}\n"
        file_listing += "</uploaded_files>"

        # Prepend to last human message content
        original = messages[last_human_idx]
        content = original.content if isinstance(original.content, str) else str(original.content)
        if "<uploaded_files>" not in content:
            updated = HumanMessage(content=file_listing + "\n\n" + content)
            messages[last_human_idx] = updated
            return {"messages": messages}

        return {}
