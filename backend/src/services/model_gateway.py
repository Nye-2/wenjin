"""Model gateway — routes chat completions to Anthropic or OpenAI."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from src.services.audit_service import AuditService
from src.services.quota_service import QuotaExceeded, QuotaService

logger = logging.getLogger(__name__)

# Cost per 1M tokens (input / output)
_COST_TABLE: dict[str, tuple[float, float]] = {
    "claude": (3.0, 15.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
}


@dataclass
class CompletionResult:
    """Result of a chat completion call."""

    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    for prefix, (inp, out) in _COST_TABLE.items():
        if model.startswith(prefix):
            return (input_tokens * inp + output_tokens * out) / 1_000_000
    # Fallback: assume $1/1M tokens
    return (input_tokens + output_tokens) / 1_000_000


class ModelGateway:
    """Routes completion requests to the appropriate LLM provider.

    Handles quota enforcement, retries on transient errors, and audit logging.
    """

    def __init__(
        self,
        *,
        anthropic,
        openai,
        audit: AuditService,
        quota: QuotaService,
    ) -> None:
        self.anthropic = anthropic
        self.openai = openai
        self.audit = audit
        self.quota = quota

    async def chat_completion(
        self,
        *,
        messages: list[dict],
        model: str,
        workspace_id: str,
        user_id: str,
        execution_id: str | None = None,
        max_tokens: int = 4096,
        **kwargs,
    ) -> CompletionResult:
        # 1. Quota check
        can_proceed = await self.quota.check(user_id, kind="tokens_daily", amount=max_tokens)
        if not can_proceed:
            raise QuotaExceeded(f"Daily token quota exceeded for user {user_id}")

        # 2. Route + retry
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                if model.startswith("claude"):
                    return await self._call_anthropic(
                        messages=messages, model=model, max_tokens=max_tokens,
                        workspace_id=workspace_id, user_id=user_id, **kwargs,
                    )
                else:
                    return await self._call_openai(
                        messages=messages, model=model, max_tokens=max_tokens,
                        workspace_id=workspace_id, user_id=user_id, **kwargs,
                    )
            except Exception as exc:
                last_exc = exc
                if attempt < 2:
                    wait = 2 ** attempt
                    logger.warning(
                        "Attempt %d failed for model %s: %s; retrying in %ds",
                        attempt + 1, model, exc, wait,
                    )
                    await asyncio.sleep(wait)

        # All retries exhausted
        raise last_exc  # type: ignore[misc]

    async def _call_anthropic(self, *, messages, model, max_tokens, workspace_id, user_id, **kwargs) -> CompletionResult:
        # Convert messages: Anthropic expects system as separate param
        system_msg = None
        api_messages = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                api_messages.append(m)

        create_kwargs: dict = {
            "model": model,
            "messages": api_messages,
            "max_tokens": max_tokens,
        }
        if system_msg:
            create_kwargs["system"] = system_msg

        response = await self.anthropic.messages.create(**create_kwargs)

        text = response.content[0].text if response.content else ""
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = _estimate_cost(model, input_tokens, output_tokens)

        # 4. Consume quota + audit
        await self.quota.consume(user_id=user_id, kind="tokens_daily", amount=input_tokens + output_tokens)
        await self.audit.log(
            "model.completion",
            workspace_id=workspace_id,
            user_id=user_id,
            target_type="model",
            target_id=model,
            payload={"input_tokens": input_tokens, "output_tokens": output_tokens, "cost_usd": cost},
        )

        return CompletionResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            model=model,
        )

    async def _call_openai(self, *, messages, model, max_tokens, workspace_id, user_id, **kwargs) -> CompletionResult:
        response = await self.openai.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
        )

        choice = response.choices[0]
        text = choice.message.content or ""
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        cost = _estimate_cost(model, input_tokens, output_tokens)

        # 4. Consume quota + audit
        await self.quota.consume(user_id=user_id, kind="tokens_daily", amount=input_tokens + output_tokens)
        await self.audit.log(
            "model.completion",
            workspace_id=workspace_id,
            user_id=user_id,
            target_type="model",
            target_id=model,
            payload={"input_tokens": input_tokens, "output_tokens": output_tokens, "cost_usd": cost},
        )

        return CompletionResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            model=model,
        )
