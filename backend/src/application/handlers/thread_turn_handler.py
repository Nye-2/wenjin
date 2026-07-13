"""Thread-turn application boundary for the single WorkspaceAgent."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator, Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig

from src.academic.services.artifact_service import ArtifactService
from src.academic.services.workspace_service import WorkspaceService
from src.agents.middlewares.mission_policy_hints import load_mission_policy_hints
from src.agents.workspace_agent.agent import WorkspaceAgent
from src.agents.workspace_agent.contracts import ActiveMissionContext, WorkspaceAgentContext
from src.application.errors import BadRequestError, NotFoundError, PaymentRequiredError
from src.application.results import (
    CompletedThreadTurn,
    GeneratedThreadReply,
    PreparedThreadTurn,
    ThreadTurnRequest,
)
from src.config import get_model_config
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.mission import (
    MissionCancelPayload,
    MissionRunPayload,
    MissionStatus,
)
from src.dataservice_client.provider import dataservice_client
from src.models import create_chat_model, route_chat_model
from src.models.router import InvalidRequestedModelError
from src.services import ThreadAccessError, ThreadService
from src.services.credit_service import CreditService
from src.services.mission_runtime_service import MissionRuntimeService, build_mission_runtime
from src.services.thread_billing import normalize_token_usage
from src.services.thread_events import publish_thread_updated, set_thread_status


@dataclass(frozen=True, slots=True)
class ThreadStreamDelta:
    kind: Literal["reasoning", "content", "tool_invocation", "tool_result"]
    text: str = ""
    data: dict[str, Any] | None = None


class _ReplyStreamRun:
    def __init__(
        self,
        iterator: AsyncIterator[ThreadStreamDelta],
        reply_future: asyncio.Future[GeneratedThreadReply],
    ) -> None:
        self._iterator = iterator
        self._reply_future = reply_future
        self._reply_future.add_done_callback(self._consume_exception)

    def __aiter__(self) -> AsyncIterator[ThreadStreamDelta]:
        return self._iterator

    async def wait_reply(self) -> GeneratedThreadReply:
        return await self._reply_future

    async def aclose(self) -> None:
        closer = getattr(self._iterator, "aclose", None)
        if callable(closer):
            result = closer()
            if inspect.isawaitable(result):
                await result
        if not self._reply_future.done():
            self._reply_future.cancel()

    @staticmethod
    def _consume_exception(future: asyncio.Future[Any]) -> None:
        if not future.cancelled():
            future.exception()


class _CompletedTurnStreamRun:
    def __init__(
        self,
        iterator: AsyncIterator[ThreadStreamDelta],
        completed_future: asyncio.Future[CompletedThreadTurn],
    ) -> None:
        self._iterator = iterator
        self._completed_future = completed_future
        self._completed_future.add_done_callback(self._consume_exception)

    def __aiter__(self) -> AsyncIterator[ThreadStreamDelta]:
        return self._iterator

    async def wait_completed(self) -> CompletedThreadTurn:
        return await self._completed_future

    async def aclose(self) -> None:
        closer = getattr(self._iterator, "aclose", None)
        if callable(closer):
            result = closer()
            if inspect.isawaitable(result):
                await result
        if not self._completed_future.done():
            self._completed_future.cancel()

    @staticmethod
    def _consume_exception(future: asyncio.Future[Any]) -> None:
        if not future.cancelled():
            future.exception()


class _LazyMissionPort:
    """Build the durable runtime only when a structured mutation is executed."""

    def __init__(self, dataservice: AsyncDataServiceClient) -> None:
        self._dataservice = dataservice

    async def _service(self) -> MissionRuntimeService:
        from src.review_commit_runtime.composition import build_review_commit_runtime

        runtime = await build_mission_runtime(self._dataservice)
        return MissionRuntimeService(
            runtime,
            dataservice=self._dataservice,
            review_commit=build_review_commit_runtime(self._dataservice),
        )

    async def start(self, request):
        return await (await self._service()).start(request)

    async def steer(self, mission_id: str, **kwargs):
        return await (await self._service()).steer(mission_id, **kwargs)

    async def review(self, mission_id: str, **kwargs):
        return await (await self._service()).review(mission_id, **kwargs)

    async def request_commit(self, mission_id: str, **kwargs):
        return await (await self._service()).request_commit(mission_id, **kwargs)


def build_thread_runtime_config(
    request: ThreadTurnRequest,
    thread: Any,
    *,
    actor_id: str,
    workspace_id: str | None,
    user_message_id: str | None = None,
) -> RunnableConfig:
    """Build chat-only request context without durable mission lifecycle fields."""
    return {
        "configurable": {
            "thread_id": str(thread.id),
            "user_id": actor_id,
            "workspace_id": workspace_id,
            "user_message_id": user_message_id,
            "requested_model": request.model,
            "reasoning_effort": request.reasoning_effort or "xhigh",
        }
    }


def build_thread_initial_state(
    *,
    conversation_messages: list[dict[str, Any]] | None,
    workspace_id: str | None,
    thread_id: str,
    user_id: str,
    **_: Any,
) -> dict[str, Any]:
    return {
        "messages": list(conversation_messages or []),
        "workspace_id": workspace_id,
        "thread_id": thread_id,
        "user_id": user_id,
    }


async def _workspace_type(
    workspace_service: WorkspaceService | None,
    workspace_id: str,
) -> str:
    service = workspace_service or WorkspaceService()
    workspace = await service.get(workspace_id)
    if workspace is None:
        raise NotFoundError("Workspace not found")
    return str(getattr(workspace, "workspace_type", None) or getattr(workspace, "type", "")).strip()


def _profile_hash(model_id: str) -> str:
    config = get_model_config(model_id)
    profile = getattr(config, "capability_profile", None)
    probe_hash = str(getattr(profile, "probe_hash", "") or "").strip()
    if not probe_hash:
        raise BadRequestError(f"Model '{model_id}' has no verified capability profile")
    return probe_hash


def _active_context(mission: MissionRunPayload | None) -> ActiveMissionContext | None:
    if mission is None:
        return None
    pending = mission.snapshot_json.get("pending_request")
    request_id = str(pending.get("request_id") or "") if isinstance(pending, dict) else ""
    return ActiveMissionContext(
        mission_id=mission.mission_id,
        title=mission.title,
        objective=mission.objective,
        status=mission.status.value,
        active_stage_id=mission.active_stage_id,
        pending_request_id=request_id or None,
        pending_review_count=mission.pending_review_count,
        evidence_count=mission.evidence_count,
        artifact_count=mission.artifact_count,
    )


async def _foreground_mission(
    dataservice: AsyncDataServiceClient,
    *,
    workspace_id: str,
    thread_id: str,
    user_id: str,
) -> MissionRunPayload | None:
    return await dataservice.missions.get_foreground_for_thread(
        workspace_id=workspace_id,
        thread_id=thread_id,
        user_id=user_id,
    )


def _reply_blocks(text: str, *, mission_id: str | None) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [{"kind": "text", "content": text}]
    if mission_id:
        blocks.insert(
            0,
            {
                "kind": "status_line",
                "label": "研究任务已开始",
                "run_id": mission_id,
                "tone": "info",
            },
        )
    return blocks


async def generate_thread_response(
    request: ThreadTurnRequest,
    thread: Any,
    *,
    actor_id: str,
    user_message_id: str | None = None,
    workspace_service: WorkspaceService | None = None,
    conversation_messages: list[dict[str, Any]] | None = None,
    **_: Any,
) -> GeneratedThreadReply:
    workspace_id = str(thread.workspace_id or request.workspace_id or "").strip()
    if not workspace_id:
        raise BadRequestError("WorkspaceAgent requires a workspace-bound thread")
    if not user_message_id:
        raise BadRequestError("WorkspaceAgent requires the persisted user message id")
    workspace_type = await _workspace_type(workspace_service, workspace_id)
    model_id = route_chat_model(
        requested_model=request.model,
        thread_model=thread.model,
        require_tools=True,
        require_vision=bool(request.attachments),
    )
    effort = str(request.reasoning_effort or "xhigh").strip().lower()
    if effort not in {"low", "medium", "high", "xhigh"}:
        raise BadRequestError("Unsupported reasoning effort")
    model = create_chat_model(model_id, reasoning_effort=effort)

    async with dataservice_client() as dataservice:
        active = await _foreground_mission(
            dataservice,
            workspace_id=workspace_id,
            thread_id=str(thread.id),
            user_id=actor_id,
        )
        context = WorkspaceAgentContext(
            workspace_id=workspace_id,
            workspace_type=workspace_type,
            thread_id=str(thread.id),
            user_id=actor_id,
            user_message_id=user_message_id,
            user_message=request.message,
            model_id=model_id,
            reasoning_effort=effort,
            model_capability_profile_hash=_profile_hash(model_id),
            conversation=tuple(conversation_messages or ()),
            policy_hints=await load_mission_policy_hints(dataservice, workspace_type),
            active_mission=_active_context(active),
        )
        reply = await WorkspaceAgent(model=model, missions=_LazyMissionPort(dataservice)).run(context)

    usage = dict(reply.metadata.get("usage") or {})
    usage.update({"model_name": model_id, "source": "workspace_agent"})
    metadata = {**reply.metadata, "usage": usage, "agent_action": reply.action.action}
    if reply.mission_id:
        metadata["mission_id"] = reply.mission_id
    return GeneratedThreadReply(
        content=reply.text,
        blocks=_reply_blocks(reply.text, mission_id=reply.mission_id),
        metadata=metadata,
    )


def stream_thread_response(*args: Any, **kwargs: Any) -> _ReplyStreamRun:
    future: asyncio.Future[GeneratedThreadReply] = asyncio.get_running_loop().create_future()

    async def iterator() -> AsyncIterator[ThreadStreamDelta]:
        try:
            reply = await generate_thread_response(*args, **kwargs)
            yield ThreadStreamDelta(kind="content", text=reply.content)
            future.set_result(reply)
        except BaseException as exc:
            if not future.done():
                future.set_exception(exc)
            raise

    return _ReplyStreamRun(iterator(), future)


class ThreadTurnHandler:
    def __init__(
        self,
        *,
        thread_service: ThreadService,
        workspace_service: WorkspaceService | None = None,
        index_service: Any | None = None,
        artifact_service: ArtifactService | None = None,
        reference_service: Any | None = None,
    ) -> None:
        self.thread_service = thread_service
        self.workspace_service = workspace_service
        self.index_service = index_service
        self.artifact_service = artifact_service
        self.reference_service = reference_service

    async def prepare_turn(self, request: ThreadTurnRequest, *, actor_id: str) -> PreparedThreadTurn:
        thread = await self._get_or_create_owned_thread(request, actor_id=actor_id)
        await ensure_thread_turn_budget(actor_id)
        metadata = dict(request.metadata or {})
        if request.attachments:
            metadata["attachments"] = [asdict(item) for item in request.attachments]
        message = await self.thread_service.add_message(
            thread,
            role="user",
            content=request.message,
            metadata=metadata or None,
        )
        await set_thread_status(thread.workspace_id, thread.id, status="running", skill=thread.skill, skill_name=None)
        message_id = str(message.get("id") or "") if isinstance(message, Mapping) else ""
        return PreparedThreadTurn(request=request, thread=thread, user_message_id=message_id or None)

    async def preflight_stream_turn(self, request: ThreadTurnRequest, *, actor_id: str) -> None:
        try:
            self.thread_service.resolve_requested_model(request.model)
        except InvalidRequestedModelError as exc:
            raise BadRequestError(str(exc)) from exc
        if request.thread_id:
            await self._get_or_create_owned_thread(request, actor_id=actor_id)

    async def run_turn(self, request: ThreadTurnRequest, *, actor_id: str) -> CompletedThreadTurn:
        return await self.complete_turn(await self.prepare_turn(request, actor_id=actor_id), actor_id=actor_id)

    async def complete_turn(self, prepared: PreparedThreadTurn, *, actor_id: str) -> CompletedThreadTurn:
        try:
            messages = await self.thread_service.list_thread_messages(prepared.thread)
            reply = await generate_thread_response(
                prepared.request,
                prepared.thread,
                actor_id=actor_id,
                user_message_id=prepared.user_message_id,
                workspace_service=self.workspace_service,
                conversation_messages=messages,
            )
            return await self._finalize(prepared, actor_id=actor_id, reply=reply)
        except BaseException:
            await self._fail(prepared.thread)
            raise

    def stream_turn(self, prepared: PreparedThreadTurn, *, actor_id: str) -> _CompletedTurnStreamRun:
        future: asyncio.Future[CompletedThreadTurn] = asyncio.get_running_loop().create_future()

        async def iterator() -> AsyncIterator[ThreadStreamDelta]:
            stream = None
            try:
                messages = await self.thread_service.list_thread_messages(prepared.thread)
                stream = stream_thread_response(
                    prepared.request,
                    prepared.thread,
                    actor_id=actor_id,
                    user_message_id=prepared.user_message_id,
                    workspace_service=self.workspace_service,
                    conversation_messages=messages,
                )
                async for delta in stream:
                    yield delta
                completed = await self._finalize(
                    prepared,
                    actor_id=actor_id,
                    reply=await stream.wait_reply(),
                )
                future.set_result(completed)
            except BaseException as exc:
                await self._fail(prepared.thread)
                if not future.done():
                    future.set_exception(exc)
                raise

        return _CompletedTurnStreamRun(iterator(), future)

    async def _finalize(
        self,
        prepared: PreparedThreadTurn,
        *,
        actor_id: str,
        reply: GeneratedThreadReply,
    ) -> CompletedThreadTurn:
        usage = normalize_token_usage(reply.metadata.get("usage"))
        if usage is not None:
            billing = await CreditService().consume_for_thread_usage(
                user_id=actor_id,
                token_usage=usage,
                model_name=reply.metadata.get("usage", {}).get("model_name"),
                workspace_id=prepared.thread.workspace_id,
                thread_id=prepared.thread.id,
                metadata={
                    "source": "workspace_agent",
                    "user_message_id": prepared.user_message_id,
                    "idempotency_key": f"thread_token_billing:{prepared.user_message_id}",
                },
            )
            reply.metadata["billing"] = billing.as_metadata()
        assistant = await self.thread_service.add_message(
            prepared.thread,
            role="assistant",
            content=reply.content,
            blocks=reply.blocks,
            metadata=reply.metadata,
        )
        await self.thread_service.set_title_if_empty(prepared.thread, prepared.request.message)
        await publish_thread_updated(prepared.thread)
        await set_thread_status(prepared.thread.workspace_id, prepared.thread.id, status="completed", skill=prepared.thread.skill, skill_name=None)
        return CompletedThreadTurn(thread=prepared.thread, assistant_message=dict(assistant), reply=reply)

    async def _get_or_create_owned_thread(self, request: ThreadTurnRequest, *, actor_id: str):
        try:
            thread = await self.thread_service.get_or_create_thread(
                thread_id=request.thread_id,
                user_id=actor_id,
                workspace_id=request.workspace_id,
                model=request.model,
                skill=request.skill,
                skill_explicit=request.skill_explicit,
            )
        except ThreadAccessError as exc:
            raise NotFoundError("Thread not found") from exc
        except InvalidRequestedModelError as exc:
            raise BadRequestError(str(exc)) from exc
        if request.workspace_id and thread.workspace_id and request.workspace_id != thread.workspace_id:
            raise BadRequestError("Thread does not belong to the requested workspace")
        return thread

    async def handle_run_interruption(self, prepared: PreparedThreadTurn, *, rollback: bool) -> None:
        if rollback:
            if not await self._cancel_started_mission(prepared):
                await self._fail(prepared.thread)
                return
            messages = await self.thread_service.list_thread_messages(prepared.thread)
            await self.thread_service.rollback_last_user_message(
                prepared.thread,
                expected_content=prepared.request.message,
                source_messages=messages,
            )
        await self._fail(prepared.thread)

    @staticmethod
    async def _cancel_started_mission(prepared: PreparedThreadTurn) -> bool:
        if not prepared.user_message_id or not prepared.thread.workspace_id:
            return True
        key = f"mission:{prepared.thread.id}:{prepared.user_message_id}"
        async with dataservice_client() as client:
            mission = await client.missions.get_by_idempotency_key(
                workspace_id=prepared.thread.workspace_id,
                key=key,
            )
            if mission is None:
                return True
            if mission.status in {
                MissionStatus.COMPLETED,
                MissionStatus.FAILED,
                MissionStatus.CANCELLED,
            }:
                return False
            await client.missions.cancel(
                mission.mission_id,
                MissionCancelPayload(
                    request_id=f"chat-rollback:{prepared.user_message_id}",
                    reason="Initiating chat turn was rolled back",
                ),
            )
        return True

    @staticmethod
    async def _fail(thread: Any) -> None:
        await set_thread_status(thread.workspace_id, thread.id, status="failed", skill=thread.skill, skill_name=None)


async def ensure_thread_turn_budget(actor_id: str) -> None:
    if await CreditService().can_start_thread_turn(actor_id):
        return
    raise PaymentRequiredError("主线对话积分额度不足，请先补充积分后继续。")
