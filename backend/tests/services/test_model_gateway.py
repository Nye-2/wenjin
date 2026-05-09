"""Tests for ModelGateway using mocked LLM clients."""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.services.model_gateway import ModelGateway
from src.services.quota_service import QuotaExceeded


def _make_anthropic_response(text="Hello", input_tokens=100, output_tokens=50):
    return SimpleNamespace(
        content=[SimpleNamespace(text=text)],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def _make_openai_response(text="Hello", prompt_tokens=100, completion_tokens=50):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


@pytest.mark.asyncio
async def test_routes_to_anthropic():
    """Model 'claude-opus-4-7' routes to anthropic.messages.create."""
    anthropic = AsyncMock()
    anthropic.messages.create = AsyncMock(
        return_value=_make_anthropic_response("Hi from Claude", 120, 80)
    )
    openai = AsyncMock()
    audit = AsyncMock()
    quota = AsyncMock()
    quota.check = AsyncMock(return_value=True)
    quota.consume = AsyncMock()

    gw = ModelGateway(anthropic=anthropic, openai=openai, audit=audit, quota=quota)
    result = await gw.chat_completion(
        messages=[{"role": "user", "content": "Hello"}],
        model="claude-opus-4-7",
        workspace_id="ws-1",
        user_id="u-1",
    )

    assert result.text == "Hi from Claude"
    assert result.input_tokens == 120
    assert result.output_tokens == 80
    assert result.model == "claude-opus-4-7"
    anthropic.messages.create.assert_called_once()
    openai.chat.completions.create.assert_not_called()


@pytest.mark.asyncio
async def test_routes_to_openai():
    """Model 'gpt-4o' routes to openai.chat.completions.create."""
    anthropic = AsyncMock()
    openai = AsyncMock()
    openai.chat.completions.create = AsyncMock(
        return_value=_make_openai_response("Hi from GPT", 100, 60)
    )
    audit = AsyncMock()
    quota = AsyncMock()
    quota.check = AsyncMock(return_value=True)
    quota.consume = AsyncMock()

    gw = ModelGateway(anthropic=anthropic, openai=openai, audit=audit, quota=quota)
    result = await gw.chat_completion(
        messages=[{"role": "user", "content": "Hello"}],
        model="gpt-4o",
        workspace_id="ws-1",
        user_id="u-1",
    )

    assert result.text == "Hi from GPT"
    assert result.input_tokens == 100
    assert result.output_tokens == 60
    assert result.model == "gpt-4o"
    openai.chat.completions.create.assert_called_once()
    anthropic.messages.create.assert_not_called()


@pytest.mark.asyncio
async def test_raises_quota_exceeded():
    """QuotaExceeded is raised when quota.check returns False."""
    anthropic = AsyncMock()
    openai = AsyncMock()
    audit = AsyncMock()
    quota = AsyncMock()
    quota.check = AsyncMock(return_value=False)

    gw = ModelGateway(anthropic=anthropic, openai=openai, audit=audit, quota=quota)
    with pytest.raises(QuotaExceeded):
        await gw.chat_completion(
            messages=[{"role": "user", "content": "Hello"}],
            model="gpt-4o",
            workspace_id="ws-1",
            user_id="u-1",
        )


@pytest.mark.asyncio
async def test_does_not_retry_on_quota_exceeded():
    """QuotaExceeded raised inside _call_anthropic propagates immediately without retry."""
    import anthropic as anthropic_mod
    import openai as openai_mod
    from unittest.mock import call

    # quota.check passes (so we enter the retry loop), but consume raises QuotaExceeded
    anthropic_client = AsyncMock()
    anthropic_client.messages.create = AsyncMock(
        return_value=_make_anthropic_response("Hi", 100, 50)
    )
    openai_client = AsyncMock()
    audit = AsyncMock()
    quota = AsyncMock()
    quota.check = AsyncMock(return_value=True)
    quota.consume = AsyncMock(side_effect=QuotaExceeded("token limit hit mid-call"))

    gw = ModelGateway(
        anthropic=anthropic_client,
        openai=openai_client,
        audit=audit,
        quota=quota,
    )

    with pytest.raises(QuotaExceeded):
        await gw.chat_completion(
            messages=[{"role": "user", "content": "Hello"}],
            model="claude-opus-4-7",
            workspace_id="ws-1",
            user_id="u-1",
        )

    # The LLM was called exactly once — no retry occurred
    anthropic_client.messages.create.assert_called_once()
