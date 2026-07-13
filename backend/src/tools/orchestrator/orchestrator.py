"""Policy-checked, idempotent tool dispatch for Mission Runtime."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from src.tools.orchestrator.catalog import ToolCatalog, ToolRegistration
from src.tools.orchestrator.contracts import (
    ProviderToolCall,
    ResearchToolOutcome,
    SideEffectClass,
    ToolDescriptor,
    ToolErrorType,
    ToolGuardDecision,
    ToolHandlerResult,
    ToolInvocationContext,
    ToolOperation,
    ToolOutcomeStatus,
    ToolPolicy,
    VerificationStatus,
    utc_now,
)
from src.tools.orchestrator.errors import (
    MalformedToolArgumentsError,
    StaleToolLeaseError,
    ToolDispatchError,
    ToolOperationInProgressError,
)
from src.tools.orchestrator.frames import parse_chat_completions_tool_calls
from src.tools.orchestrator.redaction import redact_tool_value

_MAX_INLINE_RETRY_DELAY_SECONDS = 2.0


class OperationJournal(Protocol):
    """MissionItem-backed operation journal supplied by MissionRuntime."""

    async def load_terminal(self, operation: ToolOperation) -> ResearchToolOutcome | None: ...

    async def claim_started(self, operation: ToolOperation) -> bool: ...

    async def record_terminal(
        self,
        operation: ToolOperation,
        outcome: ResearchToolOutcome,
    ) -> bool: ...


class ToolLeaseFence(Protocol):
    async def assert_current(self, operation: ToolOperation) -> None: ...


class ToolExecutionGuard(Protocol):
    async def preflight(
        self,
        *,
        descriptor: ToolDescriptor,
        operation: ToolOperation,
        arguments: BaseModel,
        policy: ToolPolicy,
    ) -> ToolGuardDecision: ...


class ToolOrchestrator:
    """The only dispatch boundary for model-facing and internal tool calls."""

    def __init__(
        self,
        *,
        catalog: ToolCatalog,
        journal: OperationJournal,
        lease_fence: ToolLeaseFence,
        guard: ToolExecutionGuard,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not catalog.frozen:
            raise ValueError("ToolOrchestrator requires a frozen ToolCatalog")
        self.catalog = catalog
        self.journal = journal
        self.lease_fence = lease_fence
        self.guard = guard
        self._sleep = sleep

    async def invoke_provider_response(
        self,
        response: dict[str, Any],
        *,
        context: ToolInvocationContext,
        policy: ToolPolicy,
    ) -> tuple[ResearchToolOutcome, ...]:
        calls = parse_chat_completions_tool_calls(response)
        for call in calls:
            registration = self.catalog.require(call.tool_id)
            _validate_arguments(registration, call.arguments)
        outcomes: list[ResearchToolOutcome] = []
        for call in calls:
            outcomes.append(
                await self.invoke_provider_call(
                    call,
                    context=context,
                    policy=policy,
                )
            )
        return tuple(outcomes)

    async def invoke_provider_call(
        self,
        call: ProviderToolCall,
        *,
        context: ToolInvocationContext,
        policy: ToolPolicy,
    ) -> ResearchToolOutcome:
        return await self.invoke(
            call.tool_id,
            call.arguments,
            context=context,
            policy=policy,
        )

    async def invoke(
        self,
        tool_id: str,
        arguments: dict[str, Any],
        *,
        context: ToolInvocationContext,
        policy: ToolPolicy,
    ) -> ResearchToolOutcome:
        registration = self.catalog.require(tool_id)
        parsed_arguments = _validate_arguments(registration, arguments)
        operation = _build_operation(
            registration=registration,
            arguments=parsed_arguments,
            context=context,
            policy=policy,
            attempt=1,
        )

        existing = await self.journal.load_terminal(operation)
        if existing is not None:
            return existing

        await self.lease_fence.assert_current(operation)
        claimed = await self.journal.claim_started(operation)
        if not claimed:
            existing = await self.journal.load_terminal(operation)
            if existing is not None:
                return existing
            raise ToolOperationInProgressError(f"tool operation is already in progress: {operation.operation_id}")

        preflight = _catalog_preflight(
            registration=registration,
            context=context,
            policy=policy,
        )
        if preflight is None:
            try:
                preflight = await self.guard.preflight(
                    descriptor=registration.descriptor,
                    operation=operation,
                    arguments=parsed_arguments,
                    policy=policy,
                )
            except StaleToolLeaseError:
                raise
            except ToolDispatchError as exc:
                outcome = _error_outcome(
                    operation,
                    exc.error_type,
                    exc.user_safe_summary,
                    recoverable_by_model=exc.recoverable_by_model,
                    retry_after_seconds=exc.retry_after_seconds,
                )
                await self._record_terminal(operation, outcome)
                return outcome
            except Exception:
                outcome = _error_outcome(
                    operation,
                    ToolErrorType.INTERNAL_ERROR,
                    "Tool permission and budget checks could not be completed.",
                )
                await self._record_terminal(operation, outcome)
                return outcome
        if not preflight.allowed:
            outcome = _error_outcome(
                operation,
                preflight.error_type or ToolErrorType.POLICY_FORBIDDEN,
                preflight.user_safe_summary or "Tool use is not allowed in this mission.",
            )
            await self._record_terminal(operation, outcome)
            return outcome

        max_attempts = _max_attempts(registration, policy)
        timeout_seconds = min(
            registration.descriptor.default_timeout_seconds,
            policy.max_timeout_seconds,
        )
        last_failure: ToolDispatchError | None = None

        for attempt in range(1, max_attempts + 1):
            current_operation = operation.model_copy(update={"attempt": attempt})
            await self.lease_fence.assert_current(current_operation)
            try:
                handler_result = await asyncio.wait_for(
                    registration.handler(current_operation, parsed_arguments),
                    timeout=timeout_seconds,
                )
                await self.lease_fence.assert_current(current_operation)
                outcome = _success_outcome(
                    registration,
                    current_operation,
                    handler_result,
                )
                await self._record_terminal(current_operation, outcome)
                return outcome
            except StaleToolLeaseError:
                raise
            except TimeoutError:
                if registration.descriptor.side_effect_class is SideEffectClass.NON_IDEMPOTENT:
                    last_failure = ToolDispatchError(
                        ToolErrorType.RECEIPT_UNKNOWN,
                        "The operation receipt is unknown and will not be retried automatically.",
                    )
                else:
                    last_failure = ToolDispatchError(
                        ToolErrorType.TIMEOUT,
                        "The tool did not finish within its time budget.",
                        recoverable_by_model=True,
                    )
            except ToolDispatchError as exc:
                last_failure = exc
            except (ValidationError, ValueError) as exc:
                last_failure = ToolDispatchError(
                    ToolErrorType.UNSAFE_OUTPUT,
                    "The tool returned data that did not satisfy its output contract.",
                )
                last_failure.__cause__ = exc
            except Exception as exc:
                last_failure = ToolDispatchError(
                    ToolErrorType.INTERNAL_ERROR,
                    "The tool could not complete this operation.",
                )
                last_failure.__cause__ = exc

            if not _should_retry(
                registration=registration,
                failure=last_failure,
                attempt=attempt,
                max_attempts=max_attempts,
            ):
                break
            await self._sleep(_retry_delay(last_failure, attempt=attempt))

        failure = last_failure or ToolDispatchError(
            ToolErrorType.INTERNAL_ERROR,
            "The tool could not complete this operation.",
        )
        outcome = _error_outcome(
            operation.model_copy(update={"attempt": max_attempts}),
            failure.error_type,
            failure.user_safe_summary,
            recoverable_by_model=failure.recoverable_by_model,
            retry_after_seconds=failure.retry_after_seconds,
        )
        await self._record_terminal(operation, outcome)
        return outcome

    async def _record_terminal(
        self,
        operation: ToolOperation,
        outcome: ResearchToolOutcome,
    ) -> None:
        await self.lease_fence.assert_current(operation)
        accepted = await self.journal.record_terminal(operation, outcome)
        if not accepted:
            raise StaleToolLeaseError(f"terminal tool receipt rejected for operation {operation.operation_id}")


def _catalog_preflight(
    *,
    registration: ToolRegistration,
    context: ToolInvocationContext,
    policy: ToolPolicy,
) -> ToolGuardDecision | None:
    descriptor = registration.descriptor
    if not policy.allows_tool(descriptor.tool_id):
        return ToolGuardDecision(
            allowed=False,
            error_type=ToolErrorType.POLICY_FORBIDDEN,
            user_safe_summary="This tool is outside the current mission policy.",
        )
    if context.caller_kind not in descriptor.allowed_callers:
        return ToolGuardDecision(
            allowed=False,
            error_type=ToolErrorType.PERMISSION_DENIED,
            user_safe_summary="This agent is not allowed to use the requested tool.",
        )
    if not set(descriptor.required_permissions).issubset(policy.granted_permissions):
        return ToolGuardDecision(
            allowed=False,
            error_type=ToolErrorType.PERMISSION_DENIED,
            user_safe_summary="This tool requires permission that has not been granted.",
        )
    if descriptor.network_profile not in policy.allowed_network_profiles:
        return ToolGuardDecision(
            allowed=False,
            error_type=ToolErrorType.POLICY_FORBIDDEN,
            user_safe_summary="The requested network access is not allowed for this mission.",
        )
    return None


def _validate_arguments(
    registration: ToolRegistration,
    arguments: dict[str, Any],
) -> BaseModel:
    if not isinstance(arguments, dict):
        raise MalformedToolArgumentsError("tool arguments must be an object")
    try:
        return registration.input_model.model_validate(arguments)
    except ValidationError as exc:
        raise MalformedToolArgumentsError(f"tool arguments do not satisfy {registration.descriptor.tool_id}") from exc


def _build_operation(
    *,
    registration: ToolRegistration,
    arguments: BaseModel,
    context: ToolInvocationContext,
    policy: ToolPolicy,
    attempt: int,
) -> ToolOperation:
    args_payload = arguments.model_dump(mode="json")
    args_hash = _stable_hash(args_payload)
    operation_key = _stable_hash(
        {
            "mission_id": context.mission_id,
            "command_id": context.command_id,
            "stage_id": context.stage_id,
            "caller_id": context.caller_id,
            "model_id": context.model_id,
            "input_refs": context.input_refs,
            "tool_id": registration.descriptor.tool_id,
            "tool_version": registration.descriptor.tool_version,
            "descriptor_schema_hash": registration.descriptor.schema_hash,
            "args_hash": args_hash,
            "policy_ref": policy.policy_ref,
        }
    )
    return ToolOperation(
        mission_id=context.mission_id,
        operation_id=f"op_{operation_key[:32]}",
        operation_key=operation_key,
        command_id=context.command_id,
        stage_id=context.stage_id,
        caller_id=context.caller_id,
        caller_kind=context.caller_kind,
        model_id=context.model_id,
        input_refs=context.input_refs,
        tool_id=registration.descriptor.tool_id,
        tool_version=registration.descriptor.tool_version,
        descriptor_schema_hash=registration.descriptor.schema_hash,
        args_hash=args_hash,
        policy_snapshot_ref=policy.policy_ref,
        lease_epoch=context.lease_epoch,
        attempt=attempt,
    )


def _max_attempts(registration: ToolRegistration, policy: ToolPolicy) -> int:
    if registration.descriptor.side_effect_class is SideEffectClass.NON_IDEMPOTENT:
        return 1
    return policy.max_attempts


def _should_retry(
    *,
    registration: ToolRegistration,
    failure: ToolDispatchError,
    attempt: int,
    max_attempts: int,
) -> bool:
    if attempt >= max_attempts:
        return False
    if registration.descriptor.side_effect_class is SideEffectClass.NON_IDEMPOTENT:
        return False
    if failure.retry_after_seconds is not None and failure.retry_after_seconds > _MAX_INLINE_RETRY_DELAY_SECONDS:
        return False
    return failure.recoverable_by_model and failure.error_type in {
        ToolErrorType.RATE_LIMITED,
        ToolErrorType.TIMEOUT,
        ToolErrorType.TOOL_UNAVAILABLE,
    }


def _retry_delay(failure: ToolDispatchError, *, attempt: int) -> float:
    if failure.retry_after_seconds is not None:
        return failure.retry_after_seconds
    return min(0.1 * (2 ** (attempt - 1)), 1.0)


def _success_outcome(
    registration: ToolRegistration,
    operation: ToolOperation,
    result: ToolHandlerResult,
) -> ResearchToolOutcome:
    redacted_value = redact_tool_value(result.model_dump(mode="json"))
    payload_size = len(
        json.dumps(
            redacted_value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    if payload_size > registration.descriptor.payload_limit_bytes:
        raise ToolDispatchError(
            ToolErrorType.UNSAFE_OUTPUT,
            "The tool output exceeded its bounded result contract and must be externalized.",
        )
    redacted = ToolHandlerResult.model_validate(redacted_value)
    _enforce_provenance_requirements(
        descriptor=registration.descriptor,
        operation=operation,
        result=redacted,
    )
    return ResearchToolOutcome(
        operation_id=operation.operation_id,
        operation_key=operation.operation_key,
        producer=operation.caller_id,
        tool_id=operation.tool_id,
        tool_version=operation.tool_version,
        status=redacted.status,
        error_type=redacted.error_type,
        observed_at=utc_now(),
        input_refs=operation.input_refs,
        summary=redacted.summary[:2000],
        evidence_refs=redacted.evidence_refs,
        source_refs=redacted.source_refs,
        artifact_refs=redacted.artifact_refs,
        confidence=redacted.confidence,
        risk_level=redacted.risk_level,
        verification_status=redacted.verification_status,
        recommended_next_action=redacted.recommended_next_action,
        payload_ref=redacted.payload_ref,
        redaction_applied=True,
        recoverable_by_model=redacted.recoverable_by_model,
        retry_after_seconds=redacted.retry_after_seconds,
    )


def _enforce_provenance_requirements(
    *,
    descriptor: ToolDescriptor,
    operation: ToolOperation,
    result: ToolHandlerResult,
) -> None:
    if result.verification_status not in {
        VerificationStatus.VERIFIED,
        VerificationStatus.PROVIDER_RECEIPT,
    }:
        return

    predicates = {
        "workspace_scope": bool(operation.mission_id),
        "mission_receipt": bool(operation.operation_id and operation.operation_key),
        "mission_permission": bool(operation.policy_snapshot_ref),
        "verification_ref": any(
            bool(ref.metadata.get("verification_ref"))
            for ref in (*result.evidence_refs, *result.artifact_refs)
        ),
        "sandbox_receipt": bool(
            operation.tool_id.startswith("sandbox.")
            and operation.operation_id
            and operation.operation_key
        ),
        "evidence_refs": bool(result.evidence_refs),
        "source_refs": bool(result.source_refs)
        or any(bool(ref.metadata.get("source_refs")) for ref in result.artifact_refs),
        "artifact_refs": bool(result.artifact_refs),
        "visual_manifest": any(
            ref.kind == "academic_visual_candidate"
            and isinstance(ref.metadata.get("candidate"), dict)
            and isinstance(ref.metadata.get("manifest"), dict)
            and ref.metadata["manifest"].get("schema")
            == "wenjin.figure_generation.artifact.v2"
            and bool(ref.metadata["candidate"].get("review_preview_ref"))
            and bool(ref.metadata["candidate"].get("preview_hash"))
            for ref in result.artifact_refs
        ),
        "provider_web_search_call": any(
            ref.kind == "provider_search_receipt"
            and bool(ref.metadata.get("response_id"))
            and bool(ref.metadata.get("search_call_ids"))
            for ref in result.evidence_refs
        ),
        "provider_url_citations": bool(result.source_refs)
        and all(
            bool(ref.canonical_url and ref.supported_claim_refs)
            for ref in result.source_refs
        ),
        "provider_source_metadata": bool(result.source_refs)
        and all(bool(ref.source_id and ref.title and ref.observed_at) for ref in result.source_refs),
    }
    missing = tuple(
        requirement
        for requirement in descriptor.provenance_requirements
        if not predicates.get(requirement, False)
    )
    if missing:
        raise ToolDispatchError(
            ToolErrorType.PROVENANCE_MISSING,
            "The tool result did not include all provenance required for verification.",
        )


def _error_outcome(
    operation: ToolOperation,
    error_type: ToolErrorType,
    summary: str,
    *,
    recoverable_by_model: bool = False,
    retry_after_seconds: float | None = None,
) -> ResearchToolOutcome:
    safe_summary = str(redact_tool_value(summary, max_text_chars=500))
    return ResearchToolOutcome(
        operation_id=operation.operation_id,
        operation_key=operation.operation_key,
        producer=operation.caller_id,
        tool_id=operation.tool_id,
        tool_version=operation.tool_version,
        status=ToolOutcomeStatus.ERROR,
        error_type=error_type,
        observed_at=utc_now(),
        input_refs=operation.input_refs,
        summary=safe_summary,
        verification_status="rejected",
        recommended_next_action=_recommended_action(error_type),
        redaction_applied=True,
        recoverable_by_model=recoverable_by_model,
        retry_after_seconds=retry_after_seconds,
    )


def _recommended_action(error_type: ToolErrorType) -> str:
    actions = {
        ToolErrorType.CAPABILITY_UNVERIFIED: "Use a model endpoint with a current capability probe.",
        ToolErrorType.PROVENANCE_MISSING: "Collect a provider search receipt and citation metadata.",
        ToolErrorType.PERMISSION_DENIED: "Request the required permission before retrying.",
        ToolErrorType.POLICY_FORBIDDEN: "Revise the mission plan to use an allowed tool.",
        ToolErrorType.TIMEOUT: "Retry within the remaining mission budget or narrow the request.",
        ToolErrorType.RECEIPT_UNKNOWN: "Check the operation receipt before any retry.",
    }
    return actions.get(error_type, "Replan the current step or ask the user for guidance.")


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "OperationJournal",
    "ToolExecutionGuard",
    "ToolLeaseFence",
    "ToolOrchestrator",
]
