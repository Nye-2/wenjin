"""Thread-turn application boundary for the single WorkspaceAgent."""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from src.academic.services.artifact_service import ArtifactService
from src.academic.services.workspace_service import WorkspaceService
from src.agents.workspace_agent.agent import WorkspaceAgent
from src.agents.workspace_agent.contracts import (
    ActiveMissionContext,
    ContinuationMissionContext,
    SteerMissionAction,
    WorkspaceAgentContext,
)
from src.application.errors import BadRequestError, NotFoundError, PaymentRequiredError
from src.application.results import (
    CompletedThreadTurn,
    GeneratedThreadReply,
    PreparedThreadTurn,
    ThreadTurnAttachment,
    ThreadTurnRequest,
)
from src.config import get_model_config
from src.contracts.billing import ThreadTurnBillingStatus
from src.contracts.model_usage import ModelUsage
from src.contracts.prism_context import PrismContextRef
from src.contracts.reasoning import (
    DEFAULT_REASONING_EFFORT,
    normalize_reasoning_effort,
)
from src.contracts.review_policy import ReviewMode
from src.dataservice_client import AsyncDataServiceClient, DataServiceClientError
from src.dataservice_client.contracts.mission import (
    MissionRunPayload,
    MissionStatus,
)
from src.dataservice_client.provider import dataservice_client
from src.models import create_chat_model, route_chat_model
from src.models.router import InvalidRequestedModelError
from src.services import ThreadAccessError, ThreadService
from src.services.mission_inputs import MissionInputService
from src.services.mission_policy_hints import load_mission_policy_hints
from src.services.mission_runtime_service import MissionRuntimeService, build_mission_runtime
from src.services.thread_events import publish_thread_updated, set_thread_status
from src.services.thread_turn_billing_gateway import (
    ThreadTurnBillingGateway,
    message_payload_to_bridge,
)
from src.services.workspace_uploads import is_image_upload

_MISSION_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
_EXPLICIT_MISSION_REFERENCE_RE = re.compile(
    rf"(?ix)(?:"
    rf"(?:续接|继续|重试)\s*(?:父)?任务|"
    rf"父任务|任务\s*(?:id|编号)|"
    rf"mission\s*(?:id|run)?|/missions?/"
    rf")\s*[:：#=/]?\s*(?P<mission_id>{_MISSION_UUID})"
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ThreadStreamDelta:
    kind: Literal["content"]
    text: str = ""


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


async def _workspace_agent_settings(
    workspace_service: WorkspaceService | None,
    workspace_id: str,
) -> tuple[str, ReviewMode]:
    service = workspace_service or WorkspaceService()
    workspace = await service.get(workspace_id)
    if workspace is None:
        raise NotFoundError("Workspace not found")
    workspace_type = str(getattr(workspace, "workspace_type", None) or getattr(workspace, "type", "")).strip()
    settings = getattr(workspace, "settings_json", None)
    raw_review_mode = settings.get("review_mode") if isinstance(settings, dict) else None
    return workspace_type, ReviewMode(
        raw_review_mode or ReviewMode.BALANCED_DEFAULT.value
    )


def _attachments_require_vision(attachments: tuple[ThreadTurnAttachment, ...]) -> bool:
    return any(is_image_upload(item.name, item.content_type) for item in attachments)


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


def _continuation_context(
    mission: MissionRunPayload | None,
) -> ContinuationMissionContext | None:
    if mission is None or mission.status not in {
        MissionStatus.COMPLETED,
        MissionStatus.FAILED,
        MissionStatus.CANCELLED,
    }:
        return None
    policy_id = str(mission.mission_policy_id or "").strip()
    if not policy_id:
        return None
    raw_acceptance = mission.snapshot_json.get("stage_acceptance")
    passed_stage_ids = tuple(
        sorted(
            str(stage_id)
            for stage_id, result in (
                raw_acceptance.items()
                if isinstance(raw_acceptance, dict)
                else ()
            )
            if isinstance(result, dict) and result.get("result") == "pass"
        )
    )
    raw_inputs = mission.snapshot_json.get("mission_inputs")
    pinned_input_refs = tuple(
        dict.fromkeys(
            str(item.get("input_ref") or "").strip()
            for item in (raw_inputs if isinstance(raw_inputs, list) else ())
            if isinstance(item, dict)
            and str(item.get("input_ref") or "").startswith("mission-input:")
        )
    )
    raw_error = mission.snapshot_json.get("last_error")
    terminal_summary = (
        str(raw_error.get("summary") or "").strip()[:1000]
        if isinstance(raw_error, dict)
        else ""
    )
    return ContinuationMissionContext(
        mission_id=mission.mission_id,
        title=mission.title[:60],
        objective=mission.objective[:4000],
        status=mission.status.value,
        mission_policy_id=policy_id,
        passed_stage_ids=passed_stage_ids,
        pinned_input_refs=pinned_input_refs,
        evidence_count=mission.evidence_count,
        artifact_count=mission.artifact_count,
        terminal_summary=terminal_summary or None,
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


async def _latest_mission(
    dataservice: AsyncDataServiceClient,
    *,
    workspace_id: str,
    thread_id: str,
    user_id: str,
) -> MissionRunPayload | None:
    return await dataservice.missions.get_latest_for_thread(
        workspace_id=workspace_id,
        thread_id=thread_id,
        user_id=user_id,
    )


def _explicit_mission_ids(message: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            match.group("mission_id").lower()
            for match in _EXPLICIT_MISSION_REFERENCE_RE.finditer(message)
        )
    )


async def _resolve_continuation_target(
    dataservice: AsyncDataServiceClient,
    *,
    message: str,
    workspace_id: str,
    thread_id: str,
    user_id: str,
    focused_mission_id: str | None = None,
) -> MissionRunPayload | None:
    explicit_ids = _explicit_mission_ids(message)
    requested_id = str(focused_mission_id or "").strip().lower()
    if requested_id:
        if not re.fullmatch(_MISSION_UUID, requested_id):
            raise BadRequestError("指定的研究任务编号无效")
        if explicit_ids and explicit_ids != (requested_id,):
            raise BadRequestError("消息与界面指定了不同的研究任务")
        explicit_ids = (requested_id,)
    if len(explicit_ids) > 1:
        raise BadRequestError("一次只能指定一个需要续接的研究任务")
    if not explicit_ids:
        return await _latest_mission(
            dataservice,
            workspace_id=workspace_id,
            thread_id=thread_id,
            user_id=user_id,
        )

    mission = await dataservice.missions.get(explicit_ids[0])
    if (
        mission is None
        or mission.workspace_id != workspace_id
        or mission.thread_id != thread_id
        or mission.user_id != user_id
        or mission.status
        not in {
            MissionStatus.COMPLETED,
            MissionStatus.FAILED,
            MissionStatus.CANCELLED,
        }
        or not mission.mission_policy_id
    ):
        raise BadRequestError("指定的研究任务在当前工作区中不可续接")
    return mission


def _focused_mission_id(metadata: Mapping[str, Any] | None) -> str | None:
    if not isinstance(metadata, Mapping):
        return None
    value = metadata.get("focused_mission_id")
    return str(value).strip() if isinstance(value, str) and value.strip() else None


def _validate_active_mission_target(
    active: MissionRunPayload,
    *,
    message: str,
    focused_mission_id: str | None,
) -> None:
    explicit_ids = _explicit_mission_ids(message)
    focused_id = str(focused_mission_id or "").strip().lower()
    if focused_id and not re.fullmatch(_MISSION_UUID, focused_id):
        raise BadRequestError("指定的研究任务编号无效")
    if len(explicit_ids) > 1:
        raise BadRequestError("一次只能指定一个研究任务")
    if focused_id and explicit_ids and explicit_ids != (focused_id,):
        raise BadRequestError("消息与界面指定了不同的研究任务")
    target_id = explicit_ids[0] if explicit_ids else focused_id
    if target_id and target_id != active.mission_id.lower():
        raise BadRequestError("当前对话已有另一个进行中的研究任务，请先切回该任务或结束它")


def _prism_context_ref(
    metadata: Mapping[str, Any] | None,
    *,
    workspace_id: str,
) -> PrismContextRef | None:
    if not isinstance(metadata, Mapping):
        return None
    raw = metadata.get("prism_context_ref")
    if raw is None:
        return None
    try:
        context = PrismContextRef.model_validate(raw)
    except ValidationError as exc:
        raise BadRequestError("写作台选区定位已失效，请重新选择") from exc
    if context.workspace_id != workspace_id:
        raise BadRequestError("写作台选区不属于当前工作区")
    return context


def _reply_blocks(
    text: str,
    *,
    mission_id: str | None,
    agent_action: str,
    steer_kind: str | None = None,
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [{"kind": "text", "content": text}]
    if mission_id:
        if agent_action == "steer_mission":
            label = {
                "cancel": "研究任务已取消",
                "pause": "暂停请求已提交",
            }.get(steer_kind, "研究要求已更新")
        else:
            label = {
                "start_mission": "研究任务已开始",
                "propose_review": "确认决定已记录",
                "request_commit": "保存请求已提交",
            }.get(agent_action, "研究任务已更新")
        blocks.insert(
            0,
            {
                "kind": "status_line",
                "label": label,
                "run_id": mission_id,
                "tone": "info",
                "action": agent_action,
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
    mission_input_service: MissionInputService | None = None,
    on_text_delta: Callable[[str], Awaitable[None]] | None = None,
    **_: Any,
) -> GeneratedThreadReply:
    workspace_id = str(thread.workspace_id or request.workspace_id or "").strip()
    if not workspace_id:
        raise BadRequestError("WorkspaceAgent requires a workspace-bound thread")
    if not user_message_id:
        raise BadRequestError("WorkspaceAgent requires the persisted user message id")
    workspace_type, review_mode = await _workspace_agent_settings(workspace_service, workspace_id)
    model_id = route_chat_model(
        requested_model=request.model,
        thread_model=thread.model,
        require_tools=True,
        require_vision=_attachments_require_vision(request.attachments),
    )
    try:
        effort = normalize_reasoning_effort(
            request.reasoning_effort,
            default=DEFAULT_REASONING_EFFORT,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    assert effort is not None
    model = create_chat_model(model_id, reasoning_effort=effort)
    input_context = await asyncio.to_thread(
        (mission_input_service or MissionInputService()).collect_from_messages,
        conversation_messages or (),
        workspace_id=workspace_id,
        thread_id=str(thread.id),
    )

    async with dataservice_client() as dataservice:
        focused_mission_id = _focused_mission_id(request.metadata)
        active = await _foreground_mission(
            dataservice,
            workspace_id=workspace_id,
            thread_id=str(thread.id),
            user_id=actor_id,
        )
        continuation_target = None
        if active is not None:
            _validate_active_mission_target(
                active,
                message=request.message,
                focused_mission_id=focused_mission_id,
            )
        else:
            continuation_target = await _resolve_continuation_target(
                dataservice,
                message=request.message,
                focused_mission_id=focused_mission_id,
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
            reasoning_effort=effort.value,
            model_capability_profile_hash=_profile_hash(model_id),
            review_mode=review_mode,
            conversation=tuple(conversation_messages or ()),
            mission_inputs=input_context.manifests,
            attachment_contexts=input_context.contexts,
            policy_hints=await load_mission_policy_hints(dataservice, workspace_type),
            active_mission=_active_context(active),
            continuation_target=_continuation_context(continuation_target),
            prism_context_ref=_prism_context_ref(
                request.metadata,
                workspace_id=workspace_id,
            ),
        )
        reply = await WorkspaceAgent(model=model, missions=_LazyMissionPort(dataservice)).run(
            context,
            on_text_delta=on_text_delta,
        )

    usage = dict(reply.metadata.get("usage") or {})
    usage.update({"model_name": model_id, "source": "workspace_agent"})
    metadata = {**reply.metadata, "usage": usage, "agent_action": reply.action.action}
    if reply.mission_id:
        metadata["mission_id"] = reply.mission_id
    return GeneratedThreadReply(
        content=reply.text,
        blocks=_reply_blocks(
            reply.text,
            mission_id=reply.mission_id,
            agent_action=reply.action.action,
            steer_kind=(
                reply.action.input_kind.value
                if isinstance(reply.action, SteerMissionAction)
                else None
            ),
        ),
        metadata=metadata,
    )


def stream_thread_response(*args: Any, **kwargs: Any) -> _ReplyStreamRun:
    finished = object()
    queue: asyncio.Queue[str | object] = asyncio.Queue()

    async def emit_text(delta: str) -> None:
        await queue.put(delta)

    async def produce() -> GeneratedThreadReply:
        try:
            return await generate_thread_response(
                *args,
                **kwargs,
                on_text_delta=emit_text,
            )
        finally:
            queue.put_nowait(finished)

    future = asyncio.create_task(produce())

    async def iterator() -> AsyncIterator[ThreadStreamDelta]:
        while True:
            item = await queue.get()
            if item is finished:
                break
            yield ThreadStreamDelta(kind="content", text=str(item))
        await future

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
        mission_input_service: MissionInputService | None = None,
        billing_gateway: ThreadTurnBillingGateway | None = None,
    ) -> None:
        self.thread_service = thread_service
        self.workspace_service = workspace_service
        self.index_service = index_service
        self.artifact_service = artifact_service
        self.reference_service = reference_service
        self.mission_input_service = mission_input_service or MissionInputService()
        self.billing_gateway = billing_gateway or ThreadTurnBillingGateway()

    async def prepare_turn(self, request: ThreadTurnRequest, *, actor_id: str) -> PreparedThreadTurn:
        thread = await self._get_or_create_owned_thread(request, actor_id=actor_id)
        metadata = dict(request.metadata or {})
        if request.attachments:
            metadata["attachments"] = [asdict(item) for item in request.attachments]
            workspace_id = str(thread.workspace_id or request.workspace_id or "").strip()
            if not workspace_id:
                raise BadRequestError("Attachments require a workspace-bound thread")
            prepared_inputs = await asyncio.to_thread(
                self.mission_input_service.prepare,
                workspace_id=workspace_id,
                thread_id=str(thread.id),
                attachments=request.attachments,
            )
            metadata["mission_inputs"] = [item.model_dump(mode="json") for item in prepared_inputs.manifests]
            metadata["attachment_contexts"] = [
                item.model_dump(
                    mode="json",
                    exclude={"excerpt", "current_message"},
                    exclude_none=True,
                )
                for item in prepared_inputs.contexts
            ]
        idempotency_key = str(request.turn_idempotency_key or "").strip()
        if not idempotency_key:
            raise BadRequestError("Chat turn requires a stable request identity")
        authorization_task = asyncio.create_task(
            self._authorize_turn(
                thread=thread,
                content=request.message,
                metadata=metadata or None,
                idempotency_key=idempotency_key,
            )
        )
        pending_cancellation: asyncio.CancelledError | None = None
        try:
            while True:
                try:
                    authorization = await asyncio.shield(authorization_task)
                    break
                except asyncio.CancelledError as exc:
                    pending_cancellation = pending_cancellation or exc
                    if authorization_task.cancelled():
                        raise
                    if authorization_task.done():
                        authorization = authorization_task.result()
                        break
        except DataServiceClientError as exc:
            if pending_cancellation is not None:
                raise pending_cancellation from exc
            if exc.status_code == 402:
                raise PaymentRequiredError(
                    "主线对话积分额度不足，请先补充积分后继续。"
                ) from exc
            raise
        prepared = PreparedThreadTurn(
            request=request,
            thread=thread,
            billing_authorization_id=authorization.billing.id,
        )
        if pending_cancellation is not None:
            await self._fail(
                prepared,
                actor_id=actor_id,
                reason="chat turn authorization cancelled",
            )
            raise pending_cancellation
        try:
            user_message_id = (
                authorization.user_message.id
                if authorization.user_message is not None
                else authorization.billing.user_message_id
            )
            replayed_assistant = (
                message_payload_to_bridge(authorization.assistant_message)
                if authorization.assistant_message is not None
                else None
            )
            if (
                authorization.billing.status == ThreadTurnBillingStatus.AUTHORIZED
                and not user_message_id
            ):
                raise RuntimeError("Active chat-turn authorization has no user message")
            if (
                authorization.billing.status == ThreadTurnBillingStatus.SETTLED
                and replayed_assistant is None
            ):
                raise RuntimeError(
                    "Settled chat-turn authorization has no assistant message"
                )
            prepared = PreparedThreadTurn(
                request=request,
                thread=thread,
                user_message_id=user_message_id,
                billing_authorization_id=authorization.billing.id,
                replayed_assistant_message=replayed_assistant,
            )
            await set_thread_status(thread.workspace_id, thread.id, status="running")
            return prepared
        except BaseException:
            await self._fail(
                prepared,
                actor_id=actor_id,
                reason="chat turn preparation failed",
            )
            raise

    async def _authorize_turn(
        self,
        *,
        thread: Any,
        content: str,
        metadata: dict[str, Any] | None,
        idempotency_key: str,
    ) -> Any:
        try:
            return await self.billing_gateway.authorize(
                thread=thread,
                content=content,
                metadata=metadata,
                idempotency_key=idempotency_key,
            )
        except DataServiceClientError as exc:
            if exc.status_code is not None and exc.status_code < 500:
                raise
            logger.warning(
                "Retrying chat-turn authorization %s after DataService failure",
                idempotency_key,
                exc_info=True,
            )
        except Exception:
            logger.warning(
                "Retrying chat-turn authorization %s after transport failure",
                idempotency_key,
                exc_info=True,
            )
        try:
            return await self.billing_gateway.authorize(
                thread=thread,
                content=content,
                metadata=metadata,
                idempotency_key=idempotency_key,
            )
        except DataServiceClientError as exc:
            if exc.status_code is not None and exc.status_code < 500:
                raise
            await self._release_lost_authorization(
                thread=thread,
                idempotency_key=idempotency_key,
            )
            raise
        except Exception:
            await self._release_lost_authorization(
                thread=thread,
                idempotency_key=idempotency_key,
            )
            raise

    async def _release_lost_authorization(
        self,
        *,
        thread: Any,
        idempotency_key: str,
    ) -> None:
        try:
            await self.billing_gateway.release_by_idempotency_key(
                idempotency_key=idempotency_key,
                user_id=str(thread.user_id),
                reason="authorization response unavailable after retry",
            )
        except (Exception, asyncio.CancelledError):
            logger.exception(
                "Failed to compensate chat-turn authorization %s",
                idempotency_key,
            )

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
            if prepared.replayed_assistant_message is not None:
                return await self._complete_replay(prepared)
            messages = await self.thread_service.list_thread_messages(prepared.thread)
            reply = await generate_thread_response(
                prepared.request,
                prepared.thread,
                actor_id=actor_id,
                user_message_id=prepared.user_message_id,
                workspace_service=self.workspace_service,
                conversation_messages=messages,
                mission_input_service=self.mission_input_service,
            )
            return await self._finalize(prepared, actor_id=actor_id, reply=reply)
        except BaseException:
            await self._fail(prepared, actor_id=actor_id, reason="chat turn failed")
            raise

    def stream_turn(self, prepared: PreparedThreadTurn, *, actor_id: str) -> _CompletedTurnStreamRun:
        future: asyncio.Future[CompletedThreadTurn] = asyncio.get_running_loop().create_future()

        async def iterator() -> AsyncIterator[ThreadStreamDelta]:
            stream = None
            try:
                if prepared.replayed_assistant_message is not None:
                    content = str(prepared.replayed_assistant_message.get("content") or "")
                    if content:
                        yield ThreadStreamDelta(kind="content", text=content)
                    future.set_result(await self._complete_replay(prepared))
                    return
                messages = await self.thread_service.list_thread_messages(prepared.thread)
                stream = stream_thread_response(
                    prepared.request,
                    prepared.thread,
                    actor_id=actor_id,
                    user_message_id=prepared.user_message_id,
                    workspace_service=self.workspace_service,
                    conversation_messages=messages,
                    mission_input_service=self.mission_input_service,
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
                await self._fail(prepared, actor_id=actor_id, reason="chat turn failed")
                if not future.done():
                    future.set_exception(exc)
                raise
            finally:
                if stream is not None:
                    await stream.aclose()

        return _CompletedTurnStreamRun(iterator(), future)

    async def _finalize(
        self,
        prepared: PreparedThreadTurn,
        *,
        actor_id: str,
        reply: GeneratedThreadReply,
    ) -> CompletedThreadTurn:
        if not prepared.billing_authorization_id:
            raise RuntimeError("Thread turn is missing its billing authorization")
        usage = ModelUsage.from_provider_metadata(reply.metadata.get("usage"))
        if usage is None:
            raise RuntimeError(
                "WorkspaceAgent completed without a verifiable model-usage receipt"
            )
        completion = await self.billing_gateway.complete(
            thread=prepared.thread,
            billing_id=prepared.billing_authorization_id,
            content=reply.content,
            blocks=reply.blocks,
            metadata=reply.metadata,
            usage=usage,
        )
        reply.metadata["billing"] = dict(completion.billing_metadata)
        assistant = message_payload_to_bridge(completion.assistant_message)
        await self.thread_service.set_title_if_empty(prepared.thread, prepared.request.message)
        await publish_thread_updated(prepared.thread)
        await set_thread_status(
            prepared.thread.workspace_id,
            prepared.thread.id,
            status="completed",
        )
        return CompletedThreadTurn(thread=prepared.thread, assistant_message=dict(assistant), reply=reply)

    async def _complete_replay(
        self,
        prepared: PreparedThreadTurn,
    ) -> CompletedThreadTurn:
        assistant = dict(prepared.replayed_assistant_message or {})
        reply = GeneratedThreadReply(
            content=str(assistant.get("content") or ""),
            blocks=[
                dict(item)
                for item in assistant.get("blocks", [])
                if isinstance(item, Mapping)
            ],
            metadata=(
                dict(assistant.get("metadata") or {})
                if isinstance(assistant.get("metadata"), Mapping)
                else {}
            ),
        )
        await set_thread_status(
            prepared.thread.workspace_id,
            prepared.thread.id,
            status="completed",
        )
        return CompletedThreadTurn(
            thread=prepared.thread,
            assistant_message=assistant,
            reply=reply,
        )

    async def _get_or_create_owned_thread(self, request: ThreadTurnRequest, *, actor_id: str):
        try:
            thread = await self.thread_service.get_or_create_thread(
                thread_id=request.thread_id,
                user_id=actor_id,
                workspace_id=request.workspace_id,
                model=request.model,
            )
        except ThreadAccessError as exc:
            raise NotFoundError("Thread not found") from exc
        except InvalidRequestedModelError as exc:
            raise BadRequestError(str(exc)) from exc
        if request.workspace_id and thread.workspace_id and request.workspace_id != thread.workspace_id:
            raise BadRequestError("Thread does not belong to the requested workspace")
        return thread

    async def handle_run_interruption(self, prepared: PreparedThreadTurn, *, rollback: bool) -> None:
        if not prepared.billing_authorization_id:
            await self._set_failed_status(prepared)
            return
        authorization_closed = False
        if rollback:
            try:
                started_mission_exists = await self._started_mission_exists(prepared)
            except (Exception, asyncio.CancelledError):
                logger.exception(
                    "Failed to inspect Mission state while interrupting chat turn %s",
                    prepared.billing_authorization_id,
                )
                started_mission_exists = True
            if not started_mission_exists:
                try:
                    await self.billing_gateway.rollback(
                        thread=prepared.thread,
                        billing_id=prepared.billing_authorization_id,
                        user_id=str(prepared.thread.user_id),
                        reason="chat turn interrupted with rollback",
                    )
                    authorization_closed = True
                except (Exception, asyncio.CancelledError):
                    logger.exception(
                        "Failed to roll back interrupted chat-turn authorization %s",
                        prepared.billing_authorization_id,
                    )
        if not authorization_closed:
            await self._release_authorization(
                prepared,
                user_id=str(prepared.thread.user_id),
                reason="chat turn interrupted",
            )
        await self._set_failed_status(prepared)

    async def handle_run_failure(
        self,
        prepared: PreparedThreadTurn,
        *,
        actor_id: str,
        reason: str,
    ) -> None:
        """Close an authorization when the outer transport fails."""
        await self._fail(prepared, actor_id=actor_id, reason=reason)

    @staticmethod
    async def _started_mission_exists(prepared: PreparedThreadTurn) -> bool:
        if not prepared.user_message_id or not prepared.thread.workspace_id:
            return False
        key = f"mission:{prepared.thread.id}:{prepared.user_message_id}"
        async with dataservice_client() as client:
            mission = await client.missions.get_by_idempotency_key(
                workspace_id=prepared.thread.workspace_id,
                key=key,
            )
            return mission is not None

    async def _fail(
        self,
        prepared: PreparedThreadTurn,
        *,
        actor_id: str,
        reason: str,
    ) -> None:
        await self._release_authorization(
            prepared,
            user_id=actor_id,
            reason=reason,
        )
        await self._set_failed_status(prepared)

    async def _release_authorization(
        self,
        prepared: PreparedThreadTurn,
        *,
        user_id: str,
        reason: str,
    ) -> None:
        if not prepared.billing_authorization_id:
            return
        try:
            await self.billing_gateway.release(
                billing_id=prepared.billing_authorization_id,
                user_id=user_id,
                reason=reason,
            )
        except (Exception, asyncio.CancelledError):
            logger.exception(
                "Failed to release chat-turn authorization %s",
                prepared.billing_authorization_id,
            )

    @staticmethod
    async def _set_failed_status(prepared: PreparedThreadTurn) -> None:
        try:
            await set_thread_status(
                prepared.thread.workspace_id,
                prepared.thread.id,
                status="failed",
            )
        except (Exception, asyncio.CancelledError):
            logger.exception(
                "Failed to mark thread %s after chat-turn failure",
                prepared.thread.id,
            )
