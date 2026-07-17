"""Policy-checked, idempotent tool dispatch for Mission Runtime."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from time import monotonic
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
_PREFLIGHT_BUDGET_SECONDS = 5.0
_TERMINAL_RECEIPT_MARGIN_SECONDS = 5.0


class OperationJournal(Protocol):
    """MissionItem-backed operation journal supplied by MissionRuntime."""

    async def load_terminal(self, operation: ToolOperation) -> ResearchToolOutcome | None: ...

    async def claim_started(self, operation: ToolOperation) -> str | None: ...

    async def record_terminal(
        self,
        operation: ToolOperation,
        outcome: ResearchToolOutcome,
        *,
        claim_token: str,
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
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        if not catalog.frozen:
            raise ValueError("ToolOrchestrator requires a frozen ToolCatalog")
        self.catalog = catalog
        self.journal = journal
        self.lease_fence = lease_fence
        self.guard = guard
        self._sleep = sleep
        self._monotonic = monotonic_clock

    def required_budget_seconds(self, tool_id: str, policy: ToolPolicy) -> float:
        registration = self.catalog.require(tool_id)
        timeout_seconds, max_attempts = _execution_parameters(registration, policy)
        return _required_budget_seconds(
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
        )

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
        operation = await _build_operation(
            registration=registration,
            arguments=parsed_arguments,
            context=context,
            policy=policy,
            attempt=1,
        )

        existing = await self.journal.load_terminal(operation)
        if existing is not None:
            return existing

        preflight = _catalog_preflight(
            registration=registration,
            context=context,
            policy=policy,
        )
        if preflight is None:
            timeout_seconds, max_attempts = _execution_parameters(
                registration,
                policy,
            )
            required_budget = _required_budget_seconds(
                timeout_seconds=timeout_seconds,
                max_attempts=max_attempts,
            )
            if context.deadline_monotonic - self._monotonic() < required_budget:
                raise ToolDispatchError(
                    ToolErrorType.TIMEOUT,
                    "The current Mission slice cannot cover this tool's pinned attempt boundary.",
                    recoverable_by_model=True,
                )

        await self.lease_fence.assert_current(operation)
        claim_token = await self.journal.claim_started(operation)
        if claim_token is None:
            existing = await self.journal.load_terminal(operation)
            if existing is not None:
                return existing
            raise ToolOperationInProgressError(f"tool operation is already in progress: {operation.operation_id}")

        if preflight is None:
            try:
                preflight = await asyncio.wait_for(
                    self.guard.preflight(
                        descriptor=registration.descriptor,
                        operation=operation,
                        arguments=parsed_arguments,
                        policy=policy,
                    ),
                    timeout=_PREFLIGHT_BUDGET_SECONDS,
                )
            except asyncio.CancelledError:
                await self._record_cancelled_terminal(
                    operation,
                    claim_token=claim_token,
                )
                raise
            except StaleToolLeaseError:
                raise
            except TimeoutError:
                outcome = _error_outcome(
                    operation,
                    ToolErrorType.TIMEOUT,
                    "Tool permission and budget checks exceeded their pinned budget.",
                    recoverable_by_model=True,
                )
                await self._record_terminal(
                    operation,
                    outcome,
                    claim_token=claim_token,
                )
                return outcome
            except ToolDispatchError as exc:
                outcome = _error_outcome(
                    operation,
                    exc.error_type,
                    exc.user_safe_summary,
                    recoverable_by_model=exc.recoverable_by_model,
                    retry_after_seconds=exc.retry_after_seconds,
                )
                await self._record_terminal(operation, outcome, claim_token=claim_token)
                return outcome
            except Exception:
                outcome = _error_outcome(
                    operation,
                    ToolErrorType.INTERNAL_ERROR,
                    "Tool permission and budget checks could not be completed.",
                )
                await self._record_terminal(operation, outcome, claim_token=claim_token)
                return outcome
        if not preflight.allowed:
            outcome = _error_outcome(
                operation,
                preflight.error_type or ToolErrorType.POLICY_FORBIDDEN,
                preflight.user_safe_summary or "Tool use is not allowed in this mission.",
            )
            await self._record_terminal(operation, outcome, claim_token=claim_token)
            return outcome

        last_failure: ToolDispatchError | None = None

        for attempt in range(1, max_attempts + 1):
            current_operation = operation.model_copy(update={"attempt": attempt})
            try:
                await self.lease_fence.assert_current(current_operation)
                attempt_timeout = min(
                    timeout_seconds,
                    max(
                        0.0,
                        context.deadline_monotonic
                        - self._monotonic()
                        - _TERMINAL_RECEIPT_MARGIN_SECONDS,
                    ),
                )
                if attempt_timeout <= 0:
                    raise TimeoutError
                handler_result = await asyncio.wait_for(
                    registration.handler(current_operation, parsed_arguments),
                    timeout=attempt_timeout,
                )
                await self.lease_fence.assert_current(current_operation)
            except asyncio.CancelledError:
                await self._record_cancelled_terminal(
                    current_operation,
                    claim_token=claim_token,
                )
                raise
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
                    ToolErrorType.INTERNAL_ERROR,
                    "The tool runtime could not complete its typed operation.",
                )
                last_failure.__cause__ = exc
            except Exception as exc:
                last_failure = ToolDispatchError(
                    ToolErrorType.INTERNAL_ERROR,
                    "The tool could not complete this operation.",
                )
                last_failure.__cause__ = exc
            else:
                try:
                    outcome = _success_outcome(
                        registration,
                        current_operation,
                        handler_result,
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
                else:
                    await self._record_terminal(
                        current_operation,
                        outcome,
                        claim_token=claim_token,
                    )
                    return outcome

            if not _should_retry(
                registration=registration,
                failure=last_failure,
                attempt=attempt,
                max_attempts=max_attempts,
            ):
                break
            retry_delay = _retry_delay(last_failure, attempt=attempt)
            if (
                self._monotonic()
                + retry_delay
                + timeout_seconds * (max_attempts - attempt)
                + _TERMINAL_RECEIPT_MARGIN_SECONDS
                > context.deadline_monotonic
            ):
                last_failure = ToolDispatchError(
                    ToolErrorType.TIMEOUT,
                    "The Mission slice cannot cover another pinned tool attempt.",
                    recoverable_by_model=True,
                )
                break
            try:
                await self._sleep(retry_delay)
            except asyncio.CancelledError:
                await self._record_cancelled_terminal(
                    current_operation,
                    claim_token=claim_token,
                )
                raise

        failure = last_failure or ToolDispatchError(
            ToolErrorType.INTERNAL_ERROR,
            "The tool could not complete this operation.",
        )
        terminal_operation = operation.model_copy(update={"attempt": max_attempts})
        outcome = _error_outcome(
            terminal_operation,
            failure.error_type,
            failure.user_safe_summary,
            recoverable_by_model=failure.recoverable_by_model,
            retry_after_seconds=failure.retry_after_seconds,
        )
        await self._record_terminal(
            terminal_operation,
            outcome,
            claim_token=claim_token,
        )
        return outcome

    async def _record_terminal(
        self,
        operation: ToolOperation,
        outcome: ResearchToolOutcome,
        *,
        claim_token: str,
    ) -> None:
        task = asyncio.create_task(
            self._record_terminal_unshielded(
                operation,
                outcome,
                claim_token=claim_token,
            )
        )
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    async def _record_terminal_unshielded(
        self,
        operation: ToolOperation,
        outcome: ResearchToolOutcome,
        *,
        claim_token: str,
    ) -> None:
        await self.lease_fence.assert_current(operation)
        accepted = await self.journal.record_terminal(
            operation,
            outcome,
            claim_token=claim_token,
        )
        if not accepted:
            raise StaleToolLeaseError(f"terminal tool receipt rejected for operation {operation.operation_id}")

    async def _record_cancelled_terminal(
        self,
        operation: ToolOperation,
        *,
        claim_token: str,
    ) -> None:
        existing = await self.journal.load_terminal(operation)
        if existing is not None:
            return
        await self._record_terminal(
            operation,
            _error_outcome(
                operation,
                ToolErrorType.CANCELLED,
                "The tool operation was cancelled before it completed.",
            ),
            claim_token=claim_token,
        )


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
        issues = [
            _safe_validation_issue(registration.input_model, issue)
            for issue in exc.errors(include_input=False)[:12]
        ]
        detail = ", ".join(issues) or "schema_validation_failed"
        raise MalformedToolArgumentsError(
            "tool arguments do not satisfy "
            f"{registration.descriptor.tool_id} ({detail})"
        ) from exc


def _safe_validation_issue(
    input_model: type[BaseModel],
    issue: dict[str, Any],
) -> str:
    issue_type = str(issue.get("type") or "schema_validation_failed")
    location = tuple(issue.get("loc") or ())
    first = location[0] if location else None
    if issue_type == "extra_forbidden":
        field = "<extra>"
    elif isinstance(first, str) and first in input_model.model_fields:
        allowed_fields = _schema_property_names(
            input_model.model_json_schema(mode="validation")
        )
        path: list[str] = []
        for segment in location[:6]:
            if isinstance(segment, int):
                if path:
                    path[-1] += "[]"
                continue
            if not isinstance(segment, str) or segment not in allowed_fields:
                break
            path.append(segment)
        field = ".".join(path) or first
    else:
        field = "<root>"
    return f"{field}:{issue_type}"


def _schema_property_names(schema: object) -> set[str]:
    if isinstance(schema, list):
        return set().union(*(_schema_property_names(value) for value in schema))
    if not isinstance(schema, dict):
        return set()
    names: set[str] = set()
    properties = schema.get("properties")
    if isinstance(properties, dict):
        names.update(str(name) for name in properties)
    for value in schema.values():
        names.update(_schema_property_names(value))
    return names


async def _build_operation(
    *,
    registration: ToolRegistration,
    arguments: BaseModel,
    context: ToolInvocationContext,
    policy: ToolPolicy,
    attempt: int,
) -> ToolOperation:
    args_payload = arguments.model_dump(mode="json")
    args_hash = _stable_hash(args_payload)
    descriptor_hash = _stable_hash(
        registration.descriptor.model_dump(mode="json")
    )
    semantic_identity_hash: str | None = None
    if registration.semantic_identity_builder is not None:
        semantic_identity = await registration.semantic_identity_builder(
            arguments,
            context,
        )
        semantic_payload = (
            semantic_identity.model_dump(mode="json", by_alias=True)
            if isinstance(semantic_identity, BaseModel)
            else semantic_identity
        )
        semantic_identity_hash = _stable_hash(semantic_payload)
        operation_key_payload = {
            "mission_id": context.mission_id,
            "stage_id": context.stage_id,
            "tool_id": registration.descriptor.tool_id,
            "tool_version": registration.descriptor.tool_version,
            "descriptor_schema_hash": registration.descriptor.schema_hash,
            "descriptor_hash": descriptor_hash,
            "semantic_identity_hash": semantic_identity_hash,
            "policy_ref": policy.policy_ref,
        }
    else:
        operation_key_payload = {
            "mission_id": context.mission_id,
            "command_id": context.command_id,
            "stage_id": context.stage_id,
            "caller_id": context.caller_id,
            "model_id": context.model_id,
            "input_refs": context.input_refs,
            "permission_grant_ref": context.permission_grant_ref,
            "tool_id": registration.descriptor.tool_id,
            "tool_version": registration.descriptor.tool_version,
            "descriptor_schema_hash": registration.descriptor.schema_hash,
            "descriptor_hash": descriptor_hash,
            "args_hash": args_hash,
            "policy_ref": policy.policy_ref,
        }
    operation_key = _stable_hash(operation_key_payload)
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
        permission_grant_ref=context.permission_grant_ref,
        tool_id=registration.descriptor.tool_id,
        tool_version=registration.descriptor.tool_version,
        descriptor_schema_hash=registration.descriptor.schema_hash,
        args_hash=args_hash,
        semantic_identity_hash=semantic_identity_hash,
        policy_snapshot_ref=policy.policy_ref,
        lease_epoch=context.lease_epoch,
        attempt=attempt,
    )


def _execution_parameters(
    registration: ToolRegistration,
    policy: ToolPolicy,
) -> tuple[float, int]:
    descriptor = registration.descriptor
    limit = policy.execution_limit(descriptor.tool_id)
    if limit.descriptor_schema_hash != descriptor.schema_hash:
        raise ToolDispatchError(
            ToolErrorType.POLICY_FORBIDDEN,
            "The pinned tool policy no longer matches the frozen catalog descriptor.",
        )
    if limit.descriptor_hash != _stable_hash(
        descriptor.model_dump(mode="json")
    ):
        raise ToolDispatchError(
            ToolErrorType.POLICY_FORBIDDEN,
            "The pinned tool policy no longer matches the frozen catalog descriptor.",
        )
    if limit.timeout_seconds != descriptor.timeout_seconds:
        raise ToolDispatchError(
            ToolErrorType.POLICY_FORBIDDEN,
            "The pinned tool timeout no longer matches the frozen catalog descriptor.",
        )
    if limit.max_attempts != descriptor.max_attempts:
        raise ToolDispatchError(
            ToolErrorType.POLICY_FORBIDDEN,
            "The pinned tool attempt limit no longer matches the frozen catalog descriptor.",
        )
    return limit.timeout_seconds, limit.max_attempts


def _required_budget_seconds(
    *,
    timeout_seconds: float,
    max_attempts: int,
) -> float:
    retry_budget = _MAX_INLINE_RETRY_DELAY_SECONDS * max(0, max_attempts - 1)
    return (
        _PREFLIGHT_BUDGET_SECONDS
        + timeout_seconds * max_attempts
        + retry_budget
        + _TERMINAL_RECEIPT_MARGIN_SECONDS
    )


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
            ensure_ascii=False,
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
        "mission_permission": bool(operation.permission_grant_ref),
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
        ToolErrorType.EXECUTION_FAILED: (
            "Inspect the bounded execution output, revise the computation, and use a new operation id."
        ),
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
