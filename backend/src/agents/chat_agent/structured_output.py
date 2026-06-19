"""LLM structured-output wrapper with JSON-failure degradation (spec §5.5).

Not a fallback for compat — a fallback for LLM non-determinism.
Spec mandates this exists.
"""
import logging
from typing import Any

from src.agents.chat_agent.blocks import AgentMessage, TextBlock
from src.config.app_config import get_settings

logger = logging.getLogger(__name__)

# Prometheus counter is wired in src.observability.metrics; provide a default
# no-op so unit tests can patch this name without importing prom.
def record_parse_failure() -> None:
    logger.warning("agent_block_json_parse_failure")


async def parse_with_fallback(llm: Any, prompt: str, *, run_id: str) -> AgentMessage:
    """Run `with_structured_output(AgentMessage)`; on failure, degrade to TextBlock.

    Args:
        llm: LangChain chat model instance.
        prompt: Composed prompt text or message list.
        run_id: Current run id; used to attach to a degraded TextBlock context.

    Returns:
        A valid AgentMessage. Never raises on parse error.
    """
    # Plan 3 T2 — dev-only short-circuit: if a Playwright test has queued a
    # scripted AgentMessage via /__test__/llm/queue, return it instead of
    # calling the real LLM. Disabled in production.
    settings = get_settings()
    if settings.e2e_test_hooks_enabled and settings.environment.lower() != "production":
        try:
            from src.gateway.routers.dev_test_hooks import pop_next
            queued = pop_next()
            if queued is not None:
                return queued
        except ImportError:
            pass

    try:
        structured = llm.with_structured_output(AgentMessage)
        result = await structured.ainvoke(prompt)
        return result
    except Exception as exc:  # noqa: BLE001 — fallback for ANY model parse failure
        record_parse_failure()
        logger.exception("structured_output_failed run_id=%s err=%s", run_id, exc)
        # prompt already contains the text from the first LLM call — wrap it
        # directly instead of making another LLM call that generates new content.
        raw = str(prompt) if prompt else ""
        return AgentMessage(blocks=[TextBlock(content=raw)])
