"""Summarization middleware for token limit management."""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


@dataclass(frozen=True, slots=True)
class SummarizationSettings:
    """Resolved summarization settings shared by transient and durable compaction."""

    enabled: bool = False
    trigger_tokens: int = 80000
    keep_messages: int = 10
    model_name: str | None = None


def _parse_config_count(value: Any, *, default: int) -> int:
    try:
        raw = str(value or "").strip()
        parsed = int(raw.split(":", 1)[1] if ":" in raw else raw)
    except (TypeError, ValueError, IndexError):
        return default
    return parsed if parsed > 0 else default


def resolve_summarization_settings(config: Any) -> SummarizationSettings:
    """Normalize app summarization config into one SSOT shape."""
    model_name = getattr(config, "model_name", None)
    normalized_model = str(model_name).strip() if model_name else None
    return SummarizationSettings(
        enabled=bool(getattr(config, "enabled", False)),
        trigger_tokens=_parse_config_count(
            getattr(config, "trigger", "tokens:80000"),
            default=80000,
        ),
        keep_messages=_parse_config_count(
            getattr(config, "keep", "messages:10"),
            default=10,
        ),
        model_name=normalized_model or None,
    )


@lru_cache(maxsize=32)
def _resolve_token_encoder(model_name: str | None):
    """Resolve tokenizer encoder for a model, with stable fallback."""
    try:
        import tiktoken

        normalized_model = str(model_name or "").strip()
        if normalized_model:
            try:
                return tiktoken.encoding_for_model(normalized_model)
            except Exception:
                pass
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


class SummarizationMiddleware(Middleware):
    """Summarizes conversation history when approaching token limits.

    This middleware monitors token usage and triggers summarization
    when the conversation exceeds the configured threshold.
    """

    def __init__(
        self,
        trigger_tokens: int = 80000,
        keep_messages: int = 10,
        model_name: str | None = None,
    ):
        """Initialize summarization middleware.

        Args:
            trigger_tokens: Token count threshold to trigger summarization
            keep_messages: Number of recent messages to keep after summarization
            model_name: Model to use for summarization (defaults to fast model)
        """
        self._trigger_tokens = trigger_tokens
        self._keep_messages = keep_messages
        self._model_name = model_name

    @classmethod
    def from_settings(cls, settings: SummarizationSettings) -> "SummarizationMiddleware":
        """Build middleware from normalized app settings."""
        return cls(
            trigger_tokens=settings.trigger_tokens,
            keep_messages=settings.keep_messages,
            model_name=settings.model_name,
        )

    def count_tokens(self, messages: list[Any], *, model_name: str | None = None) -> int:
        """Public token-counting entrypoint for compaction callers."""
        return self._count_tokens(messages, model_name=model_name)

    async def summarize_messages(self, messages: list[Any]) -> str | None:
        """Public summarization entrypoint for compaction callers."""
        return await self._summarize(messages)

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Check token count and summarize if needed."""
        messages = state.get("messages", [])
        if not messages:
            return {}

        configurable = config.get("configurable", {})
        runtime_model_name = (
            str(configurable.get("model_name")).strip()
            if isinstance(configurable, dict) and configurable.get("model_name")
            else None
        )
        token_count = self._count_tokens(messages, model_name=runtime_model_name)
        if token_count < self._trigger_tokens:
            return {}
        if len(messages) <= self._keep_messages:
            return {}

        # Perform summarization
        summary = await self._summarize(messages[: -self._keep_messages])
        if not summary:
            return {}

        # Replace old messages with summary
        kept_messages = messages[-self._keep_messages :]
        summary_message = SystemMessage(
            content=f"<conversation_summary>\n{summary}\n</conversation_summary>"
        )

        return {"messages": [summary_message] + kept_messages}

    async def after_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """No-op after model."""
        return {}

    def _count_tokens(self, messages: list[Any], *, model_name: str | None = None) -> int:
        """Estimate prompt token count, preferring model tokenizer when available."""
        encoder = _resolve_token_encoder(model_name)
        if encoder is not None:
            total_tokens = 2  # reply priming / formatting overhead
            for msg in messages:
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                total_tokens += 4 + len(encoder.encode(content))
            return total_tokens

        # Fallback heuristic if tokenizer is unavailable.
        total_bytes = 6
        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            total_bytes += 12 + len(content.encode("utf-8"))
        return total_bytes // 3

    async def _summarize(self, messages: list[Any]) -> str | None:
        """Generate a summary of the messages."""
        try:
            from src.models.factory import create_chat_model
            from src.models.router import route_model

            model_id = route_model(
                requested_model=self._model_name,
                preferred_categories=("llm",),
                allowed_categories=("llm",),
                require_tools=False,
            )
            model = create_chat_model(model_id)
        except Exception:
            return None

        formatted: list[str] = []
        for msg in messages:
            role = "User" if isinstance(msg, HumanMessage) else "Assistant"
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            formatted.append(f"{role}: {content}")

        chunks = self._chunk_formatted_messages(formatted)
        if not chunks:
            return None

        chunk_summaries: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            prompt = f"""Summarize conversation chunk {index}/{len(chunks)} for Wenjin's chat-side continuation state.

Preserve:
- User goals, constraints, decisions, and unresolved questions
- Workspace type, selected skill/feature intent, Compute launch/resume context, and active artifact references
- Important research topics, writing requirements, citation/style preferences, and evidence gaps
- Concrete next actions already agreed

Conversation:
{chunk}

Do not preserve:
- Repetitive greetings, filler, transient UI chatter, or low-value tool logs
- Secrets, credentials, or exact long pasted source material unless necessary as a brief reference

Summary:"""
            summary = await self._invoke_summary_model(model, prompt)
            if summary:
                chunk_summaries.append(summary)

        if not chunk_summaries:
            return None
        if len(chunk_summaries) == 1:
            return chunk_summaries[0]

        combine_prompt = f"""Merge these chronological conversation summaries into one compact continuation summary for Wenjin.
Preserve decisions, constraints, unresolved questions, user preferences, active Compute/feature context, artifact references, and important facts.
Keep chronology only where it affects the next response. Separate confirmed facts from pending assumptions when needed.

Chunk summaries:
{chr(10).join(f"{idx}. {summary}" for idx, summary in enumerate(chunk_summaries, start=1))}

Merged summary:"""
        merged = await self._invoke_summary_model(model, combine_prompt)
        return merged or "\n".join(chunk_summaries)

    async def _invoke_summary_model(self, model: Any, prompt: str) -> str | None:
        try:
            response = await model.ainvoke(prompt)
            return response.content if hasattr(response, "content") else str(response)
        except Exception:
            return None

    def _chunk_formatted_messages(
        self,
        formatted_messages: list[str],
        *,
        max_chunk_tokens: int = 12000,
    ) -> list[str]:
        """Split all old messages into summarization chunks instead of dropping history."""
        chunks: list[str] = []
        current: list[str] = []
        current_tokens = 0
        for item in formatted_messages:
            item_tokens = self._count_text_tokens(item)
            if current and current_tokens + item_tokens > max_chunk_tokens:
                chunks.append("\n".join(current))
                current = []
                current_tokens = 0
            current.append(item)
            current_tokens += item_tokens
        if current:
            chunks.append("\n".join(current))
        return chunks

    def _count_text_tokens(self, text: str) -> int:
        encoder = _resolve_token_encoder(self._model_name)
        if encoder is not None:
            return len(encoder.encode(text))
        return max(1, len(text.encode("utf-8")) // 3)
