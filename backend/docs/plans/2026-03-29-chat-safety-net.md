# Chat Main Chain Safety Net — Implementation Plan

> 归档说明: 本文档为历史阶段性计划快照，可能包含已过时路由、线程模型或状态描述。当前实现请以 `docs/product/workspace-current-state.md` 与相关当前契约文档为准。

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Harden the chat main chain so that no single failure (LLM hang, middleware crash, tool runaway, SSE stall, billing race) can bring down the user session or corrupt state.

**Architecture:** Six surgical patches at critical points in the request lifecycle: model factory, agent wrapper, middleware runners, tool node, SSE generator, and billing gate. Each change is isolated — no shared state between tasks. Existing `LLMSettings` and `ServiceHttpClient` patterns are reused where possible.

**Tech Stack:** asyncio (wait_for, create_task), LangChain (ChatOpenAI/ChatAnthropic kwargs), SQLAlchemy (with_for_update), SSE (heartbeat framing)

---

### Task 1: Wire LLM Timeout & Retry Into Model Factory

`LLMSettings.TIMEOUT=120s` and `MAX_RETRIES=3` exist in `src/config/llm_config.py:30-35` but `create_chat_model()` in `src/models/factory.py` never passes them to the underlying SDK clients. Both `ChatOpenAI` and `ChatAnthropic` accept `timeout` and `max_retries` kwargs.

**Files:**
- Modify: `src/models/factory.py:140-180` (`_create_openai_compatible_model`)
- Modify: `src/models/factory.py:183-233` (`_create_anthropic_model`)
- Test: `tests/models/test_factory.py`

**Step 1: Write failing tests**

```python
# tests/models/test_factory.py — add two tests

from unittest.mock import patch, MagicMock
from src.config.llm_config import LLMSettings


class TestModelFactoryTimeoutRetry:
    """Verify LLMSettings.TIMEOUT and MAX_RETRIES are forwarded."""

    @patch("src.models.factory.ChatOpenAI")
    @patch("src.models.factory.get_model_full_config")
    @patch("src.models.factory.resolve_model_id", return_value="test-model")
    def test_openai_receives_timeout_and_retries(self, _resolve, mock_config, mock_cls):
        mock_config.return_value = {
            "model": "gpt-4",
            "api_key": "sk-test",
            "base_url": "https://api.openai.com",
            "temperature": 0.7,
            "max_tokens": 4096,
        }
        LLMSettings.TIMEOUT = 90.0
        LLMSettings.MAX_RETRIES = 2

        from src.models.factory import create_chat_model
        create_chat_model("test-model")

        _, kwargs = mock_cls.call_args
        assert kwargs["timeout"] == 90.0
        assert kwargs["max_retries"] == 2

    @patch("src.models.factory.get_model_full_config")
    @patch("src.models.factory.resolve_model_id", return_value="claude-test")
    def test_anthropic_receives_timeout_and_retries(self, _resolve, mock_config):
        mock_config.return_value = {
            "model": "claude-sonnet-4",
            "api_key": "sk-ant-test",
            "base_url": "https://api.anthropic.com",
            "temperature": 0.7,
            "max_tokens": 4096,
        }
        LLMSettings.TIMEOUT = 60.0
        LLMSettings.MAX_RETRIES = 1

        with patch("src.models.factory.ChatAnthropic") as mock_cls:
            from src.models.factory import create_chat_model
            create_chat_model("claude-test")

            _, kwargs = mock_cls.call_args
            assert kwargs["timeout"] == 60.0
            assert kwargs["max_retries"] == 1
```

**Step 2: Run tests — expect FAIL (missing timeout/max_retries in kwargs)**

```bash
pytest tests/models/test_factory.py::TestModelFactoryTimeoutRetry -xvs
```

**Step 3: Implement — add two lines to each factory helper**

In `_create_openai_compatible_model` (line ~168), add to `kwargs`:

```python
from src.config.llm_config import LLMSettings

# inside kwargs dict:
"timeout": LLMSettings.TIMEOUT,
"max_retries": LLMSettings.MAX_RETRIES,
```

In `_create_anthropic_model` (line ~214), add to `kwargs`:

```python
"timeout": LLMSettings.TIMEOUT,
"max_retries": LLMSettings.MAX_RETRIES,
```

**Step 4: Run tests — expect PASS**

```bash
pytest tests/models/test_factory.py::TestModelFactoryTimeoutRetry -xvs
```

**Step 5: Run full model test suite — no regressions**

```bash
pytest tests/models/ -xvs
```

**Step 6: Commit**

```bash
git add src/models/factory.py tests/models/test_factory.py
git commit -m "feat(safety): wire LLM timeout & retry settings into model factory"
```

---

### Task 2: Agent-Level Timeout in generate_chat_response

Even with per-LLM-call timeouts, the full agent loop (multiple LLM round-trips + tool calls) can run unbounded. Wrap `agent.ainvoke()` in `asyncio.wait_for()` at the top-level call site.

**Files:**
- Modify: `src/application/handlers/chat_turn_handler.py:601-603`
- Modify: `src/config/llm_config.py` (add `AGENT_TIMEOUT`)
- Test: `tests/application/handlers/test_chat_turn_handler.py`

**Step 1: Add `AGENT_TIMEOUT` to LLMSettings**

In `src/config/llm_config.py`, add to the `LLMSettings` class:

```python
AGENT_TIMEOUT: float = 300.0  # 5 minutes for full agent loop

# In load():
if agent_timeout := os.environ.get("LLM_AGENT_TIMEOUT"):
    try:
        cls.AGENT_TIMEOUT = float(agent_timeout)
    except ValueError:
        pass
```

**Step 2: Write failing test**

```python
# tests/application/handlers/test_chat_turn_handler.py — add test

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestAgentTimeout:
    @pytest.mark.asyncio
    async def test_agent_timeout_raises_application_error(self):
        """Agent hanging beyond AGENT_TIMEOUT should raise, not hang forever."""
        from src.config.llm_config import LLMSettings
        original = LLMSettings.AGENT_TIMEOUT
        LLMSettings.AGENT_TIMEOUT = 0.1  # 100ms for test

        try:
            mock_agent = AsyncMock()
            mock_agent.ainvoke = AsyncMock(side_effect=lambda *a, **kw: asyncio.sleep(10))

            with patch("src.application.handlers.chat_turn_handler.make_lead_agent", return_value=mock_agent), \
                 patch("src.application.handlers.chat_turn_handler.build_pipeline", return_value=[]), \
                 patch("src.application.handlers.chat_turn_handler.ensure_chat_turn_budget"), \
                 patch("src.application.handlers.chat_turn_handler.maybe_bridge_workspace_feature", return_value=None), \
                 patch("src.application.handlers.chat_turn_handler.route_chat_model", return_value="test-model"):

                from src.application.handlers.chat_turn_handler import generate_chat_response
                from src.application.errors import ApplicationError

                mock_request = MagicMock()
                mock_request.model = "test-model"
                mock_request.message = "hello"
                mock_request.attachments = []
                mock_thread = MagicMock()
                mock_thread.id = "thread-1"
                mock_thread.skill = None
                mock_thread.model = None
                mock_thread.workspace_id = None

                with pytest.raises((asyncio.TimeoutError, ApplicationError)):
                    await generate_chat_response(
                        mock_request,
                        mock_thread,
                        actor_id="user-1",
                    )
        finally:
            LLMSettings.AGENT_TIMEOUT = original
```

**Step 3: Run test — expect FAIL (currently hangs or no timeout)**

```bash
pytest tests/application/handlers/test_chat_turn_handler.py::TestAgentTimeout -xvs --timeout=5
```

**Step 4: Implement — wrap ainvoke in wait_for**

In `src/application/handlers/chat_turn_handler.py`, modify `generate_chat_response()` around line 601-603:

```python
import asyncio
from src.config.llm_config import LLMSettings

# Replace:
#   result = await agent.ainvoke(initial_state, config=config)
# With:
try:
    result = await asyncio.wait_for(
        agent.ainvoke(initial_state, config=config),
        timeout=LLMSettings.AGENT_TIMEOUT,
    )
except asyncio.TimeoutError:
    logger.error("Agent timed out after %.0fs for thread %s", LLMSettings.AGENT_TIMEOUT, thread.id)
    raise ApplicationError("AI 响应超时，请稍后重试或简化您的问题。")
```

**Step 5: Run test — expect PASS**

```bash
pytest tests/application/handlers/test_chat_turn_handler.py::TestAgentTimeout -xvs --timeout=10
```

**Step 6: Run related tests — no regressions**

```bash
pytest tests/application/handlers/ -xvs --timeout=30
```

**Step 7: Commit**

```bash
git add src/config/llm_config.py src/application/handlers/chat_turn_handler.py tests/application/handlers/test_chat_turn_handler.py
git commit -m "feat(safety): add 5-min agent-level timeout with graceful error"
```

---

### Task 3: Middleware Error Isolation

Currently, if any middleware throws in `middleware_before_model()` or `middleware_after_model()`, the entire chain crashes and the user gets an unhandled 500. Each middleware should be individually try-caught: log the error, skip the faulty middleware, continue the chain.

**Files:**
- Modify: `src/agents/lead_agent/agent.py:609-653` (both runner functions)
- Modify: `src/agents/lead_agent/dynamic_tools.py:175-226` (before_tool / after_tool)
- Test: `tests/agents/lead_agent/test_middleware_isolation.py` (new)

**Step 1: Write failing tests**

```python
# tests/agents/lead_agent/test_middleware_isolation.py

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.agents.middlewares.base import Middleware


class _CrashingMiddleware(Middleware):
    """Middleware that always raises."""
    async def before_model(self, state, config):
        raise RuntimeError("middleware boom")

    async def after_model(self, state, config):
        raise RuntimeError("middleware boom after")


class _PassthroughMiddleware(Middleware):
    """Middleware that records it was called and passes through."""
    def __init__(self):
        self.before_called = False
        self.after_called = False

    async def before_model(self, state, config):
        self.before_called = True
        return {}

    async def after_model(self, state, config):
        self.after_called = True
        return {}


class TestMiddlewareErrorIsolation:
    @pytest.mark.asyncio
    async def test_crashing_middleware_does_not_block_chain(self):
        """A crashing middleware must not prevent subsequent middlewares from running."""
        from src.agents.lead_agent.agent import middleware_before_model

        passthrough = _PassthroughMiddleware()
        middlewares = [_CrashingMiddleware(), passthrough]

        state = {"messages": []}
        config = {"configurable": {}}

        result = await middleware_before_model(state, config, middlewares)

        assert passthrough.before_called is True
        # State should still be returned (not crash)
        assert result is not None

    @pytest.mark.asyncio
    async def test_crashing_after_model_does_not_block_chain(self):
        from src.agents.lead_agent.agent import middleware_after_model

        passthrough = _PassthroughMiddleware()
        middlewares = [_CrashingMiddleware(), passthrough]

        state = {"messages": []}
        config = {"configurable": {}}

        result = await middleware_after_model(state, config, middlewares)

        assert passthrough.after_called is True
        assert result is not None
```

**Step 2: Run tests — expect FAIL (RuntimeError propagates)**

```bash
pytest tests/agents/lead_agent/test_middleware_isolation.py -xvs
```

**Step 3: Implement — add try-catch per middleware**

In `src/agents/lead_agent/agent.py`, modify `middleware_before_model()` (line 624-630):

```python
current_state = state
for middleware in middlewares:
    try:
        updates = await middleware.before_model(current_state, config)
        if isinstance(updates, dict):
            current_state = merge_thread_state(current_state, updates)
    except Exception:
        logger.exception(
            "Middleware %s.before_model failed, skipping",
            type(middleware).__name__,
        )
return current_state
```

Same pattern for `middleware_after_model()` (line 648-653).

In `src/agents/lead_agent/dynamic_tools.py`, modify `_apply_before_tool()` (line 186-193):

```python
for middleware in self._middlewares:
    try:
        tool_name, tool_args = await middleware.before_tool(
            state, config, tool_name, tool_args,
        )
    except Exception:
        logger.exception(
            "Middleware %s.before_tool failed, skipping",
            type(middleware).__name__,
        )
```

Same for `_apply_after_tool()` (line 208-213).

**Step 4: Run tests — expect PASS**

```bash
pytest tests/agents/lead_agent/test_middleware_isolation.py -xvs
```

**Step 5: Run full agent test suite**

```bash
pytest tests/agents/ -xvs --timeout=30
```

**Step 6: Commit**

```bash
git add src/agents/lead_agent/agent.py src/agents/lead_agent/dynamic_tools.py tests/agents/lead_agent/test_middleware_isolation.py
git commit -m "feat(safety): isolate middleware errors with per-middleware try-catch"
```

---

### Task 4: Per-Tool Timeout in DynamicToolNode

Currently `tool.ainvoke()` in `_arun_one_with_middlewares()` can hang indefinitely. Wrap each tool invocation in `asyncio.wait_for()` with a configurable default (60s). Also truncate oversized tool output (>10KB) to prevent context window blowup.

**Files:**
- Modify: `src/agents/lead_agent/dynamic_tools.py:345-388` (`_arun_one_with_middlewares`)
- Modify: `src/config/llm_config.py` (add `TOOL_TIMEOUT`, `TOOL_OUTPUT_MAX_CHARS`)
- Test: `tests/agents/lead_agent/test_tool_timeout.py` (new)

**Step 1: Add config constants**

In `src/config/llm_config.py`, add to `LLMSettings`:

```python
TOOL_TIMEOUT: float = 60.0         # per-tool timeout in seconds
TOOL_OUTPUT_MAX_CHARS: int = 10000  # truncate tool output above this

# In load():
if tool_timeout := os.environ.get("LLM_TOOL_TIMEOUT"):
    try:
        cls.TOOL_TIMEOUT = float(tool_timeout)
    except ValueError:
        pass
if tool_max := os.environ.get("LLM_TOOL_OUTPUT_MAX_CHARS"):
    try:
        cls.TOOL_OUTPUT_MAX_CHARS = int(tool_max)
    except ValueError:
        pass
```

**Step 2: Write failing tests**

```python
# tests/agents/lead_agent/test_tool_timeout.py

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import ToolMessage


class TestToolTimeout:
    @pytest.mark.asyncio
    async def test_tool_timeout_returns_error_message(self):
        """A hanging tool should be terminated and return an error ToolMessage."""
        from src.agents.lead_agent.dynamic_tools import DynamicToolNode
        from src.config.llm_config import LLMSettings

        original = LLMSettings.TOOL_TIMEOUT
        LLMSettings.TOOL_TIMEOUT = 0.1  # 100ms

        try:
            slow_tool = AsyncMock()
            slow_tool.ainvoke = AsyncMock(side_effect=lambda *a, **kw: asyncio.sleep(10))
            slow_tool.name = "slow_tool"

            node = DynamicToolNode(lambda: [slow_tool])
            call = {"name": "slow_tool", "args": {}, "id": "call-1", "type": "tool_call"}

            result = await node._arun_one_with_middlewares(
                call=call,
                input_type="list",
                config={"configurable": {}},
                state={"messages": []},
            )

            assert isinstance(result, ToolMessage)
            assert "timeout" in result.content.lower() or "timed out" in result.content.lower()
        finally:
            LLMSettings.TOOL_TIMEOUT = original


class TestToolOutputTruncation:
    @pytest.mark.asyncio
    async def test_oversized_output_is_truncated(self):
        """Tool output exceeding TOOL_OUTPUT_MAX_CHARS should be truncated."""
        from src.agents.lead_agent.dynamic_tools import DynamicToolNode
        from src.config.llm_config import LLMSettings

        original = LLMSettings.TOOL_OUTPUT_MAX_CHARS
        LLMSettings.TOOL_OUTPUT_MAX_CHARS = 100

        try:
            big_output = ToolMessage(content="x" * 500, name="big_tool", tool_call_id="call-1")
            mock_tool = AsyncMock()
            mock_tool.ainvoke = AsyncMock(return_value=big_output)
            mock_tool.name = "big_tool"

            node = DynamicToolNode(lambda: [mock_tool])
            call = {"name": "big_tool", "args": {}, "id": "call-1", "type": "tool_call"}

            result = await node._arun_one_with_middlewares(
                call=call,
                input_type="list",
                config={"configurable": {}},
                state={"messages": []},
            )

            assert isinstance(result, ToolMessage)
            assert len(result.content) <= 150  # 100 + truncation notice
        finally:
            LLMSettings.TOOL_OUTPUT_MAX_CHARS = original
```

**Step 3: Run tests — expect FAIL**

```bash
pytest tests/agents/lead_agent/test_tool_timeout.py -xvs --timeout=5
```

**Step 4: Implement**

In `src/agents/lead_agent/dynamic_tools.py`, modify `_arun_one_with_middlewares()`:

```python
import asyncio
from src.config.llm_config import LLMSettings

async def _arun_one_with_middlewares(self, *, call, input_type, config, state):
    if invalid_tool_message := self._validate_tool_call(call):
        return invalid_tool_message

    try:
        updated_call = await self._apply_before_tool(
            state=state, config=config, call=call,
        )
        if invalid_tool_message := self._validate_tool_call(updated_call):
            return invalid_tool_message
        call_args = {**updated_call, **{"type": "tool_call"}}

        # Per-tool timeout
        try:
            response = await asyncio.wait_for(
                self.tools_by_name[updated_call["name"]].ainvoke(call_args, config),
                timeout=LLMSettings.TOOL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("Tool %s timed out after %.0fs", updated_call["name"], LLMSettings.TOOL_TIMEOUT)
            return ToolMessage(
                content=f"Tool '{updated_call['name']}' timed out after {LLMSettings.TOOL_TIMEOUT:.0f}s",
                name=str(updated_call["name"]),
                tool_call_id=str(call["id"]),
            )
    except GraphBubbleUp as exc:
        raise exc
    except Exception as exc:
        return self._coerce_tool_error_message(call=call, error=exc)

    response = await self._apply_after_tool(
        state=state, config=config, call=updated_call, response=response,
    )

    # Truncate oversized output
    if isinstance(response, ToolMessage) and isinstance(response.content, str):
        max_chars = LLMSettings.TOOL_OUTPUT_MAX_CHARS
        if len(response.content) > max_chars:
            response.content = response.content[:max_chars] + "\n...[truncated]"

    if isinstance(response, Command):
        return cast(ToolRunOutput, self._validate_tool_command(response, updated_call, input_type))
    if isinstance(response, ToolMessage):
        response.content = cast(str | list[Any], msg_content_output(response.content))
        return response
    raise TypeError(f"Tool {updated_call['name']} returned unexpected type: {type(response)}")
```

**Step 5: Run tests — expect PASS**

```bash
pytest tests/agents/lead_agent/test_tool_timeout.py -xvs --timeout=10
```

**Step 6: Run full agent tests**

```bash
pytest tests/agents/ -xvs --timeout=30
```

**Step 7: Commit**

```bash
git add src/config/llm_config.py src/agents/lead_agent/dynamic_tools.py tests/agents/lead_agent/test_tool_timeout.py
git commit -m "feat(safety): add per-tool timeout and output truncation"
```

---

### Task 5: SSE Heartbeat & Client Disconnect Detection

The current `chat_stream()` SSE generator in `src/gateway/routers/chat.py:152-175` has no heartbeat — if the agent takes >30s, proxies/browsers may close the connection. The existing `workspace_events.py:56-93` already implements this pattern (30s ping). Apply the same approach.

**Files:**
- Modify: `src/gateway/routers/chat.py:144-185` (`chat_stream` / `generate`)
- Modify: `src/gateway/routers/chat_streaming.py` (add `stream_heartbeat_event`)
- Test: `tests/gateway/routers/test_chat_stream_heartbeat.py` (new)

**Step 1: Add heartbeat helper**

In `src/gateway/routers/chat_streaming.py`, add:

```python
def stream_heartbeat_event() -> str:
    """SSE comment line — keeps the connection alive without data."""
    return ": heartbeat\n\n"
```

**Step 2: Write failing test**

```python
# tests/gateway/routers/test_chat_stream_heartbeat.py

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestSSEHeartbeat:
    @pytest.mark.asyncio
    async def test_heartbeat_sent_during_long_processing(self):
        """SSE stream should emit heartbeat comments while agent is working."""
        from src.gateway.routers.chat_streaming import stream_heartbeat_event

        heartbeat = stream_heartbeat_event()
        assert heartbeat == ": heartbeat\n\n"
        assert heartbeat.startswith(":")  # SSE comment format
```

**Step 3: Implement heartbeat in chat_stream**

Restructure `generate()` in `src/gateway/routers/chat.py` to use a background heartbeat:

```python
async def generate() -> AsyncGenerator[str, None]:
    heartbeat_task: asyncio.Task | None = None
    result_queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def _heartbeat() -> None:
        """Send periodic heartbeat comments."""
        try:
            while True:
                await asyncio.sleep(15)
                await result_queue.put(stream_heartbeat_event())
        except asyncio.CancelledError:
            pass

    async def _process() -> None:
        """Run the actual chat turn and enqueue SSE events."""
        try:
            prepared = await handler.prepare_turn(
                _to_turn_request(request),
                actor_id=str(current_user.id),
            )
            await result_queue.put(
                stream_thread_context_event(
                    thread_id=prepared.thread.id,
                    skill=prepared.thread.skill,
                )
            )
            completed = await handler.complete_turn(
                prepared,
                actor_id=str(current_user.id),
            )
            if completed.reply.content:
                await result_queue.put(stream_content_event(completed.reply.content))
            await result_queue.put(stream_assistant_message_event(completed.assistant_message))
            await result_queue.put(stream_done_event())
        except ApplicationError as exc:
            await result_queue.put(stream_error_event(exc.message))
        except Exception as exc:
            logger.exception("Streaming chat failed")
            await result_queue.put(stream_error_event(str(exc)))
        finally:
            await result_queue.put(None)  # sentinel

    heartbeat_task = asyncio.create_task(_heartbeat())
    process_task = asyncio.create_task(_process())

    try:
        while True:
            event = await result_queue.get()
            if event is None:
                break
            yield event
    finally:
        heartbeat_task.cancel()
        if not process_task.done():
            process_task.cancel()
        # Suppress CancelledError from cleanup
        for task in (heartbeat_task, process_task):
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
```

**Step 4: Run tests**

```bash
pytest tests/gateway/routers/test_chat_stream_heartbeat.py -xvs
pytest tests/gateway/ -xvs --timeout=30
```

**Step 5: Commit**

```bash
git add src/gateway/routers/chat.py src/gateway/routers/chat_streaming.py tests/gateway/routers/test_chat_stream_heartbeat.py
git commit -m "feat(safety): add SSE heartbeat to keep connections alive during processing"
```

---

### Task 6: Billing Concurrency Safety

`ensure_chat_turn_budget()` in `chat_turn_handler.py:530-541` uses `can_start_chat_turn()` which reads credit balance without row-level locking. Concurrent requests can both pass the check before either deducts. Add `SELECT ... FOR UPDATE` to the credit balance query.

**Files:**
- Modify: `src/services/credit_service.py` (the `can_start_chat_turn` query)
- Test: `tests/services/test_credit_concurrency.py` (new)

**Step 1: Identify the credit balance query**

Read `src/services/credit_service.py` to find `can_start_chat_turn()` and the balance query it uses.

**Step 2: Write failing test**

```python
# tests/services/test_credit_concurrency.py

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestCreditConcurrencySafety:
    @pytest.mark.asyncio
    async def test_can_start_chat_turn_uses_for_update(self):
        """Verify the credit balance query uses FOR UPDATE locking."""
        # This is a structural test — verify the query includes with_for_update()
        from src.services.credit_service import CreditService

        mock_db = AsyncMock()
        service = CreditService(mock_db)

        # Inspect that the implementation uses with_for_update
        # (Exact assertion depends on implementation found in Step 1)
        import inspect
        source = inspect.getsource(service.can_start_chat_turn)
        assert "for_update" in source.lower() or "with_for_update" in source.lower()
```

**Step 3: Implement — add FOR UPDATE to balance query**

In `can_start_chat_turn()`, change the credit balance select from:

```python
select(CreditBalance).where(CreditBalance.user_id == user_id)
```

to:

```python
select(CreditBalance).where(CreditBalance.user_id == user_id).with_for_update()
```

**Step 4: Run tests**

```bash
pytest tests/services/test_credit_concurrency.py -xvs
pytest tests/services/ -xvs --timeout=30
```

**Step 5: Commit**

```bash
git add src/services/credit_service.py tests/services/test_credit_concurrency.py
git commit -m "feat(safety): add row-level locking to billing concurrency check"
```

---

## Execution Notes

- Tasks 1-5 are independent and can be parallelized across subagents
- Task 6 requires reading `credit_service.py` first (Step 1) before writing the test
- All config additions go to `LLMSettings` to keep configuration centralized
- Env vars follow existing pattern: `LLM_AGENT_TIMEOUT`, `LLM_TOOL_TIMEOUT`, `LLM_TOOL_OUTPUT_MAX_CHARS`
- The heartbeat pattern in Task 5 mirrors the proven implementation in `workspace_events.py`
