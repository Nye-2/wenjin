"""CompactMiddleware — auto-compacts chat session when token usage hits threshold.

Spec §4.1.4: when total token estimate exceeds threshold * model_context_limit,
summarize old turns + extract facts/decisions + replace messages head with summary
+ keep last N.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import BaseMessage, SystemMessage

logger = logging.getLogger(__name__)


class CompactMiddleware:
    """Auto-compacts chat session when token usage hits threshold.

    Spec §4.1.4: when total token estimate exceeds threshold * model_context_limit,
    summarize old turns + extract facts/decisions + replace messages head.

    Args:
        threshold: Fraction of model_context_limit at which compaction triggers
            (default 0.8 → 80%).
        keep_last: Number of recent messages to preserve unchanged (default 8).
        model_context_limit: Model context window size in tokens (default 200_000).
        memory_service: MemoryService instance for persisting extracted facts.
        decisions_service: DecisionsService instance for persisting extracted decisions.
        compact_runner: Async callable ``(old_turns, workspace_type) → dict`` that
            returns ``{"summary": str, "facts": list[dict], "decisions": list[dict]}``.
    """

    def __init__(
        self,
        *,
        threshold: float = 0.8,
        keep_last: int = 8,
        model_context_limit: int = 200_000,
        memory_service: Any,
        decisions_service: Any,
        compact_runner: Any,
    ) -> None:
        self.threshold = threshold
        self.keep_last = keep_last
        self.model_context_limit = model_context_limit
        self.memory = memory_service
        self.decisions = decisions_service
        self.compact_runner = compact_runner

    async def before_model(self, state: dict, config: dict) -> dict:
        """Hook called before the LLM is invoked.

        If token estimate is above threshold, runs compaction and replaces the
        messages head with a summary SystemMessage.

        Args:
            state: LangGraph state dict containing "messages".
            config: LangGraph config dict; expects "configurable.workspace_id"
                and "configurable.workspace_type".

        Returns:
            Possibly-modified state dict.
        """
        msgs: list[BaseMessage] = state.get("messages", [])
        if not self._should_compact(msgs):
            return state

        old_turns = msgs[: -self.keep_last] if len(msgs) > self.keep_last else []
        if not old_turns:
            return state

        configurable = config.get("configurable", {})
        workspace_id: str = configurable.get("workspace_id", "")
        workspace_type: str = configurable.get("workspace_type", "thesis")

        try:
            compact_result = await self.compact_runner(old_turns, workspace_type)
        except Exception:
            logger.exception("compact_runner failed; skipping compaction this turn")
            return state

        # Best-effort: write facts to memory
        if compact_result.get("facts"):
            try:
                from src.services.rooms.memory_service import FactCreate

                facts = [FactCreate(**f) for f in compact_result["facts"]]
                await self.memory.add_facts(workspace_id, facts)
            except Exception:
                logger.exception("CompactMiddleware: failed to write memory facts")

        # Best-effort: write decisions
        for d in compact_result.get("decisions", []):
            try:
                await self.decisions.set(
                    workspace_id,
                    key=d["key"],
                    value=d["value"],
                    extracted_by="compact_agent",
                    confidence=d.get("confidence", 1.0),
                )
            except Exception:
                logger.exception(
                    "CompactMiddleware: failed to write decision %s", d.get("key")
                )

        summary_text: str = compact_result.get("summary", "")
        new_messages: list[BaseMessage] = [
            SystemMessage(content=summary_text),
            *msgs[-self.keep_last :],
        ]
        return {**state, "messages": new_messages}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _should_compact(self, msgs: list[BaseMessage]) -> bool:
        """Return True if estimated token count exceeds the threshold."""
        token_count = self._estimate_tokens(msgs)
        return token_count / self.model_context_limit >= self.threshold

    def _estimate_tokens(self, msgs: list[BaseMessage]) -> int:
        """Rough token estimate: total chars / 4."""
        return sum(len(str(m.content)) for m in msgs) // 4
