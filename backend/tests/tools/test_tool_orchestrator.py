from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field

from src.tools.orchestrator import (
    MalformedToolArgumentsError,
    ResearchToolOutcome,
    SideEffectClass,
    SourceReference,
    ToolCallerKind,
    ToolCatalog,
    ToolDispatchError,
    ToolErrorType,
    ToolGuardDecision,
    ToolHandlerResult,
    ToolInvocationContext,
    ToolKind,
    ToolOperation,
    ToolOperationInProgressError,
    ToolOrchestrator,
    ToolOutcomeStatus,
    ToolPolicy,
    ToolReference,
    UnknownToolError,
    VerificationStatus,
    build_tool_registration,
)


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int = Field(gt=0)


class _NestedSpec(BaseModel):
    value: int = Field(gt=0)


class _NestedBrief(BaseModel):
    figure_spec: _NestedSpec


class _NestedInput(BaseModel):
    brief: _NestedBrief


class _Journal:
    def __init__(self) -> None:
        self.terminals: dict[str, ResearchToolOutcome] = {}
        self.started: list[ToolOperation] = []
        self.started_keys: set[str] = set()

    async def load_terminal(self, operation: ToolOperation):
        return self.terminals.get(operation.operation_key)

    async def claim_started(self, operation: ToolOperation) -> bool:
        if operation.operation_key in self.started_keys:
            return False
        self.started_keys.add(operation.operation_key)
        self.started.append(operation)
        return True

    async def record_terminal(
        self,
        operation: ToolOperation,
        outcome: ResearchToolOutcome,
    ) -> bool:
        self.terminals.setdefault(operation.operation_key, outcome)
        return True


class _Fence:
    async def assert_current(self, operation: ToolOperation) -> None:
        assert operation.lease_epoch == 7


class _Guard:
    async def preflight(self, **kwargs: Any) -> ToolGuardDecision:
        return ToolGuardDecision(allowed=True)


def _context() -> ToolInvocationContext:
    return ToolInvocationContext(
        mission_id="mission-1",
        workspace_id="workspace-1",
        command_id="command-1",
        stage_id="stage-1",
        caller_id="agent-1",
        caller_kind=ToolCallerKind.WORKSPACE_AGENT,
        lease_epoch=7,
        model_id="gpt-5.6-sol",
        input_refs=("mission-item:source-1",),
    )


def _policy(tool_id: str) -> ToolPolicy:
    return ToolPolicy(
        policy_ref="policy:1",
        allowed_tool_ids=(tool_id,),
        allowed_network_profiles=("none",),
        max_attempts=2,
    )


def _orchestrator(
    handler,
    *,
    side_effect=SideEffectClass.NONE,
    default_timeout_seconds: float = 60,
    payload_limit_bytes: int = 262_144,
    provenance_requirements: tuple[str, ...] = (),
    guard=None,
):
    registration = build_tool_registration(
        tool_id="test.read",
        tool_version="1.0.0",
        kind=ToolKind.READ,
        input_model=_Input,
        handler=handler,
        side_effect_class=side_effect,
        allowed_callers=(ToolCallerKind.WORKSPACE_AGENT,),
        default_timeout_seconds=default_timeout_seconds,
        payload_limit_bytes=payload_limit_bytes,
        provenance_requirements=provenance_requirements,
    )
    journal = _Journal()
    catalog = ToolCatalog([registration]).freeze()
    return (
        ToolOrchestrator(
            catalog=catalog,
            journal=journal,
            lease_fence=_Fence(),
            guard=guard or _Guard(),
            sleep=_no_sleep,
        ),
        journal,
    )


async def _no_sleep(_seconds: float) -> None:
    return None


@pytest.mark.asyncio
async def test_unknown_tool_fails_explicitly() -> None:
    async def handler(_operation, _arguments):
        raise AssertionError("handler must not run")

    orchestrator, _journal = _orchestrator(handler)

    with pytest.raises(UnknownToolError, match="unknown tool"):
        await orchestrator.invoke(
            "missing.tool",
            {"value": 1},
            context=_context(),
            policy=_policy("missing.tool"),
        )


@pytest.mark.asyncio
async def test_malformed_arguments_never_reach_handler() -> None:
    async def handler(_operation, _arguments):
        raise AssertionError("handler must not run")

    orchestrator, journal = _orchestrator(handler)

    with pytest.raises(
        MalformedToolArgumentsError,
        match=r"value:greater_than.*<extra>:extra_forbidden",
    ) as captured:
        await orchestrator.invoke(
            "test.read",
            {"value": 0, "private-client-key": True},
            context=_context(),
            policy=_policy("test.read"),
        )
    assert "private-client-key" not in str(captured.value)
    assert journal.started == []


@pytest.mark.asyncio
async def test_malformed_arguments_report_safe_nested_schema_path() -> None:
    async def handler(_operation, _arguments):
        raise AssertionError("handler must not run")

    registration = build_tool_registration(
        tool_id="test.nested",
        tool_version="1.0.0",
        kind=ToolKind.READ,
        input_model=_NestedInput,
        handler=handler,
        side_effect_class=SideEffectClass.NONE,
        allowed_callers=(ToolCallerKind.WORKSPACE_AGENT,),
        required_permissions=("read",),
    )
    journal = _Journal()
    orchestrator = ToolOrchestrator(
        catalog=ToolCatalog([registration]).freeze(),
        journal=journal,
        lease_fence=_Fence(),
        guard=_Guard(),
        sleep=_no_sleep,
    )

    with pytest.raises(
        MalformedToolArgumentsError,
        match=r"brief\.figure_spec\.value:greater_than",
    ):
        await orchestrator.invoke(
            "test.nested",
            {"brief": {"figure_spec": {"value": 0}}},
            context=_context(),
            policy=_policy("test.nested"),
        )


@pytest.mark.asyncio
async def test_duplicate_delivery_reuses_stable_terminal_receipt() -> None:
    calls = 0

    async def handler(_operation, arguments):
        nonlocal calls
        calls += 1
        return ToolHandlerResult(
            status=ToolOutcomeStatus.SUCCESS,
            summary=f"value={arguments.value}",
            verification_status=VerificationStatus.VERIFIED,
        )

    orchestrator, journal = _orchestrator(handler)
    first = await orchestrator.invoke(
        "test.read",
        {"value": 4},
        context=_context(),
        policy=_policy("test.read"),
    )
    second = await orchestrator.invoke(
        "test.read",
        {"value": 4},
        context=_context(),
        policy=_policy("test.read"),
    )

    assert calls == 1
    assert first == second
    assert first.operation_id.startswith("op_")
    assert first.input_refs == ("mission-item:source-1",)
    assert len(journal.started[0].descriptor_schema_hash) == 64
    assert len(journal.started) == 1


@pytest.mark.asyncio
async def test_retryable_read_failure_reuses_operation_identity() -> None:
    attempts: list[ToolOperation] = []

    async def handler(operation, _arguments):
        attempts.append(operation)
        if len(attempts) == 1:
            raise ToolDispatchError(
                ToolErrorType.RATE_LIMITED,
                "Search is temporarily limited.",
                recoverable_by_model=True,
            )
        return ToolHandlerResult(
            status=ToolOutcomeStatus.SUCCESS,
            summary="ok",
            verification_status=VerificationStatus.VERIFIED,
        )

    orchestrator, _journal = _orchestrator(handler)
    outcome = await orchestrator.invoke(
        "test.read",
        {"value": 9},
        context=_context(),
        policy=_policy("test.read"),
    )

    assert outcome.status is ToolOutcomeStatus.SUCCESS
    assert [item.attempt for item in attempts] == [1, 2]
    assert len({item.operation_id for item in attempts}) == 1


@pytest.mark.asyncio
async def test_long_retry_after_returns_control_without_inline_retry() -> None:
    calls = 0

    async def handler(_operation, _arguments):
        nonlocal calls
        calls += 1
        raise ToolDispatchError(
            ToolErrorType.RATE_LIMITED,
            "Search is temporarily limited.",
            recoverable_by_model=True,
            retry_after_seconds=30,
        )

    orchestrator, _journal = _orchestrator(handler)
    outcome = await orchestrator.invoke(
        "test.read",
        {"value": 9},
        context=_context(),
        policy=_policy("test.read"),
    )

    assert calls == 1
    assert outcome.error_type is ToolErrorType.RATE_LIMITED
    assert outcome.retry_after_seconds == 30


@pytest.mark.asyncio
async def test_concurrent_duplicate_without_terminal_does_not_dispatch_twice() -> None:
    calls = 0

    async def handler(_operation, _arguments):
        nonlocal calls
        calls += 1
        return ToolHandlerResult(
            status=ToolOutcomeStatus.SUCCESS,
            summary="ok",
            verification_status=VerificationStatus.VERIFIED,
        )

    orchestrator, journal = _orchestrator(handler)
    context = _context()
    policy = _policy("test.read")
    first = await orchestrator.invoke(
        "test.read",
        {"value": 3},
        context=context,
        policy=policy,
    )
    journal.terminals.clear()

    with pytest.raises(ToolOperationInProgressError, match="already in progress"):
        await orchestrator.invoke(
            "test.read",
            {"value": 3},
            context=context,
            policy=policy,
        )

    assert first.status is ToolOutcomeStatus.SUCCESS
    assert calls == 1


@pytest.mark.asyncio
async def test_model_selection_is_part_of_operation_identity() -> None:
    async def handler(_operation, _arguments):
        return ToolHandlerResult(
            status=ToolOutcomeStatus.SUCCESS,
            summary="ok",
            verification_status=VerificationStatus.VERIFIED,
        )

    orchestrator, _journal = _orchestrator(handler)
    first = await orchestrator.invoke(
        "test.read",
        {"value": 1},
        context=_context(),
        policy=_policy("test.read"),
    )
    second_context = _context().model_copy(update={"model_id": "gpt-5.6-sol-review"})
    second = await orchestrator.invoke(
        "test.read",
        {"value": 1},
        context=second_context,
        policy=_policy("test.read"),
    )

    assert first.operation_key != second.operation_key


@pytest.mark.asyncio
async def test_assistant_prose_is_not_parsed_as_a_tool_call() -> None:
    async def handler(_operation, _arguments):
        raise AssertionError("handler must not run")

    orchestrator, _journal = _orchestrator(handler)
    response = {"choices": [{"message": {"content": '<tool_call name="test.read">{"value": 1}</tool_call>'}}]}

    with pytest.raises(MalformedToolArgumentsError, match="no structured tool call"):
        await orchestrator.invoke_provider_response(
            response,
            context=_context(),
            policy=_policy("test.read"),
        )


@pytest.mark.asyncio
async def test_provider_batch_is_fully_validated_before_any_dispatch() -> None:
    calls = 0

    async def handler(_operation, _arguments):
        nonlocal calls
        calls += 1
        return ToolHandlerResult(
            status=ToolOutcomeStatus.SUCCESS,
            summary="ok",
            verification_status=VerificationStatus.VERIFIED,
        )

    orchestrator, _journal = _orchestrator(handler)
    response = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "test.read",
                                "arguments": '{"value": 1}',
                            },
                        },
                        {
                            "id": "call_2",
                            "type": "function",
                            "function": {
                                "name": "missing.tool",
                                "arguments": '{"value": 1}',
                            },
                        },
                    ]
                }
            }
        ]
    }

    with pytest.raises(UnknownToolError, match="missing.tool"):
        await orchestrator.invoke_provider_response(
            response,
            context=_context(),
            policy=_policy("test.read"),
        )

    assert calls == 0


@pytest.mark.asyncio
async def test_non_idempotent_timeout_is_receipt_unknown_and_not_retried() -> None:
    calls = 0

    async def handler(_operation, _arguments):
        nonlocal calls
        calls += 1
        import asyncio

        await asyncio.sleep(0.05)
        raise AssertionError("wait_for should cancel the handler")

    orchestrator, _journal = _orchestrator(
        handler,
        side_effect=SideEffectClass.NON_IDEMPOTENT,
        default_timeout_seconds=0.001,
    )
    outcome = await orchestrator.invoke(
        "test.read",
        {"value": 1},
        context=_context(),
        policy=_policy("test.read"),
    )

    assert calls == 1
    assert outcome.status is ToolOutcomeStatus.ERROR
    assert outcome.error_type is ToolErrorType.RECEIPT_UNKNOWN
    assert outcome.recoverable_by_model is False


@pytest.mark.asyncio
async def test_policy_can_only_narrow_catalog_availability() -> None:
    async def handler(_operation, _arguments):
        raise AssertionError("handler must not run")

    orchestrator, journal = _orchestrator(handler)
    outcome = await orchestrator.invoke(
        "test.read",
        {"value": 1},
        context=_context(),
        policy=ToolPolicy(
            policy_ref="policy:deny",
            allowed_tool_ids=(),
            allowed_network_profiles=("none",),
        ),
    )

    assert outcome.error_type is ToolErrorType.POLICY_FORBIDDEN
    assert len(journal.started) == 1


@pytest.mark.asyncio
async def test_guard_failure_is_terminal_and_never_reaches_handler() -> None:
    class FailingGuard:
        async def preflight(self, **_kwargs):
            raise RuntimeError("internal budget backend detail")

    async def handler(_operation, _arguments):
        raise AssertionError("handler must not run")

    orchestrator, journal = _orchestrator(handler, guard=FailingGuard())
    outcome = await orchestrator.invoke(
        "test.read",
        {"value": 1},
        context=_context(),
        policy=_policy("test.read"),
    )

    assert outcome.error_type is ToolErrorType.INTERNAL_ERROR
    assert "budget backend detail" not in outcome.summary
    assert outcome.operation_key in journal.terminals


@pytest.mark.asyncio
async def test_handler_value_error_is_not_mislabeled_as_unsafe_output() -> None:
    async def handler(_operation, _arguments):
        raise ValueError("runtime input mapping is inconsistent")

    orchestrator, journal = _orchestrator(handler)
    outcome = await orchestrator.invoke(
        "test.read",
        {"value": 1},
        context=_context(),
        policy=_policy("test.read"),
    )

    assert outcome.error_type is ToolErrorType.INTERNAL_ERROR
    assert "output contract" not in outcome.summary
    assert outcome.operation_key in journal.terminals


@pytest.mark.asyncio
async def test_outcome_redacts_secrets_before_journaling() -> None:
    async def handler(_operation, _arguments):
        return ToolHandlerResult(
            status=ToolOutcomeStatus.SUCCESS,
            summary="provider token=sk-super-secret-value",
            verification_status=VerificationStatus.VERIFIED,
        )

    orchestrator, journal = _orchestrator(handler)
    outcome = await orchestrator.invoke(
        "test.read",
        {"value": 1},
        context=_context(),
        policy=_policy("test.read"),
    )

    assert "sk-super-secret-value" not in outcome.summary
    assert journal.terminals[outcome.operation_key].redaction_applied is True


@pytest.mark.asyncio
async def test_oversized_result_must_be_externalized() -> None:
    async def handler(_operation, _arguments):
        return ToolHandlerResult(
            status=ToolOutcomeStatus.SUCCESS,
            summary="x" * 4000,
            verification_status=VerificationStatus.VERIFIED,
        )

    orchestrator, _journal = _orchestrator(
        handler,
        payload_limit_bytes=1024,
    )
    outcome = await orchestrator.invoke(
        "test.read",
        {"value": 1},
        context=_context(),
        policy=_policy("test.read"),
    )

    assert outcome.status is ToolOutcomeStatus.ERROR
    assert outcome.error_type is ToolErrorType.UNSAFE_OUTPUT
    assert "externalized" in outcome.summary


@pytest.mark.asyncio
async def test_payload_limit_uses_actual_utf8_wire_size() -> None:
    content = "科研证据" * 100

    async def handler(_operation, _arguments):
        return ToolHandlerResult(
            status=ToolOutcomeStatus.SUCCESS,
            summary="Read UTF-8 content.",
            evidence_refs=(
                ToolReference(
                    ref_id="document:utf8",
                    kind="workspace_document_text",
                    metadata={"content": content},
                ),
            ),
        )

    actual_size = len(
        json.dumps(
            ToolHandlerResult(
                status=ToolOutcomeStatus.SUCCESS,
                summary="Read UTF-8 content.",
                evidence_refs=(
                    ToolReference(
                        ref_id="document:utf8",
                        kind="workspace_document_text",
                        metadata={"content": content},
                    ),
                ),
            ).model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    escaped_size = len(
        json.dumps(
            {"content": content},
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    assert escaped_size > actual_size
    orchestrator, _journal = _orchestrator(
        handler,
        payload_limit_bytes=actual_size,
    )

    outcome = await orchestrator.invoke(
        "test.read",
        {"value": 1},
        context=_context(),
        policy=_policy("test.read"),
    )

    assert outcome.status is ToolOutcomeStatus.SUCCESS


@pytest.mark.asyncio
async def test_redaction_preserves_bounded_reference_content_and_truncation_contract() -> None:
    content = "正文" * 1500 + "完整结尾"

    async def handler(_operation, _arguments):
        return ToolHandlerResult(
            status=ToolOutcomeStatus.SUCCESS,
            summary=f"Read {len(content)} characters.",
            evidence_refs=(
                ToolReference(
                    ref_id="document:one",
                    kind="workspace_document_text",
                    metadata={
                        "content": content,
                        "offset": 0,
                        "truncated": False,
                    },
                ),
            ),
            verification_status=VerificationStatus.VERIFIED,
        )

    orchestrator, _journal = _orchestrator(handler)
    outcome = await orchestrator.invoke(
        "test.read",
        {"value": 1},
        context=_context(),
        policy=_policy("test.read"),
    )

    metadata = outcome.evidence_refs[0].metadata
    assert metadata["content"] == content
    assert metadata["content"].endswith("完整结尾")
    assert metadata["truncated"] is False


@pytest.mark.asyncio
async def test_receipted_source_result_is_json_normalized_before_journaling() -> None:
    async def handler(_operation, _arguments):
        return ToolHandlerResult(
            status=ToolOutcomeStatus.SUCCESS,
            summary="One source returned.",
            source_refs=(
                SourceReference(
                    source_id="web:source-1",
                    canonical_url="https://example.edu/source-1",
                    title="Source 1",
                    observed_at=datetime.now(UTC),
                    verification_status=VerificationStatus.PROVIDER_RECEIPT,
                ),
            ),
            verification_status=VerificationStatus.PROVIDER_RECEIPT,
        )

    orchestrator, _journal = _orchestrator(handler)
    outcome = await orchestrator.invoke(
        "test.read",
        {"value": 1},
        context=_context(),
        policy=_policy("test.read"),
    )

    assert outcome.status is ToolOutcomeStatus.SUCCESS
    assert outcome.source_refs[0].canonical_url == "https://example.edu/source-1"


@pytest.mark.asyncio
async def test_verified_result_missing_descriptor_provenance_is_typed_failure() -> None:
    async def handler(_operation, _arguments):
        return ToolHandlerResult(
            status=ToolOutcomeStatus.SUCCESS,
            summary="Claimed verified without evidence.",
            verification_status=VerificationStatus.VERIFIED,
        )

    orchestrator, journal = _orchestrator(
        handler,
        provenance_requirements=("evidence_refs",),
    )
    outcome = await orchestrator.invoke(
        "test.read",
        {"value": 1},
        context=_context(),
        policy=_policy("test.read"),
    )

    assert outcome.status is ToolOutcomeStatus.ERROR
    assert outcome.error_type is ToolErrorType.PROVENANCE_MISSING
    assert outcome.verification_status is VerificationStatus.REJECTED
    assert journal.terminals[outcome.operation_key] == outcome


@pytest.mark.asyncio
async def test_verified_result_satisfying_descriptor_provenance_remains_verified() -> None:
    async def handler(_operation, _arguments):
        return ToolHandlerResult(
            status=ToolOutcomeStatus.SUCCESS,
            summary="Evidence attached.",
            evidence_refs=(
                ToolReference(ref_id="evidence:1", kind="test_evidence"),
            ),
            verification_status=VerificationStatus.VERIFIED,
        )

    orchestrator, _journal = _orchestrator(
        handler,
        provenance_requirements=("workspace_scope", "mission_receipt", "evidence_refs"),
    )
    outcome = await orchestrator.invoke(
        "test.read",
        {"value": 1},
        context=_context(),
        policy=_policy("test.read"),
    )

    assert outcome.status is ToolOutcomeStatus.SUCCESS
    assert outcome.verification_status is VerificationStatus.VERIFIED


@pytest.mark.asyncio
async def test_verified_academic_visual_requires_typed_v2_manifest() -> None:
    async def handler(_operation, _arguments):
        return ToolHandlerResult(
            status=ToolOutcomeStatus.SUCCESS,
            summary="Visual candidate attached.",
            artifact_refs=(
                ToolReference(
                    ref_id="academic-visual:1",
                    kind="academic_visual_candidate",
                    metadata={
                        "candidate": {
                            "review_preview_ref": "mpv1_abcdefghijklmnopqrstuvwxyzABCDEF",
                            "preview_hash": "a" * 64,
                        },
                        "manifest": {"schema": "wenjin.figure_generation.artifact.v2"},
                    },
                ),
            ),
            verification_status=VerificationStatus.VERIFIED,
        )

    orchestrator, _journal = _orchestrator(
        handler,
        provenance_requirements=("visual_manifest",),
    )
    outcome = await orchestrator.invoke(
        "test.read",
        {"value": 1},
        context=_context(),
        policy=_policy("test.read"),
    )

    assert outcome.status is ToolOutcomeStatus.SUCCESS
    assert outcome.verification_status is VerificationStatus.VERIFIED


@pytest.mark.asyncio
async def test_unknown_provenance_requirement_fails_closed() -> None:
    async def handler(_operation, _arguments):
        return ToolHandlerResult(
            status=ToolOutcomeStatus.SUCCESS,
            summary="Unknown provenance vocabulary.",
            verification_status=VerificationStatus.VERIFIED,
        )

    orchestrator, _journal = _orchestrator(
        handler,
        provenance_requirements=("unknown_receipt_kind",),
    )
    outcome = await orchestrator.invoke(
        "test.read",
        {"value": 1},
        context=_context(),
        policy=_policy("test.read"),
    )

    assert outcome.error_type is ToolErrorType.PROVENANCE_MISSING
