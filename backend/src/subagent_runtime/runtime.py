"""Bounded in-slice SubagentRuntime with isolated child contexts."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Protocol

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from src.contracts.model_usage import ModelCallTerminalOutcome, ModelUsageReceipt
from src.models.provider_errors import is_rate_limit_error, is_transient_model_error
from src.subagent_runtime.contracts import (
    SubagentAction,
    SubagentActionCheckpoint,
    SubagentBatchResult,
    SubagentJobResult,
    SubagentJobSpec,
    SubagentModelOutputError,
    SubagentModelTurn,
    SubagentModelUsageError,
    SubagentStatus,
    SubagentStep,
    SubagentStopReason,
    SubagentToolRequest,
    SubagentToolResult,
)

logger = logging.getLogger(__name__)

_FINAL_SYNTHESIS_INSTRUCTION = (
    "Final synthesis turn: do not request another tool. Complete from the loaded "
    "context and tool results, or stop honestly with the best valid partial result."
)


class SubagentModelAdmissionDeferred(TimeoutError):
    """The slice cannot safely contain a new receipt-bearing model call."""


class SubagentModelPort(Protocol):
    async def next_action(
        self,
        job: SubagentJobSpec,
        steps: tuple[SubagentStep, ...],
        tool_results: tuple[SubagentToolResult, ...],
    ) -> SubagentModelTurn: ...


class SubagentToolPort(Protocol):
    async def execute(self, request: SubagentToolRequest) -> SubagentToolResult: ...


class SubagentLedgerPort(Protocol):
    async def command_pending(self, job: SubagentJobSpec) -> bool: ...

    async def record_progress(
        self,
        job: SubagentJobSpec,
        *,
        phase: str,
        summary: str,
        payload_json: dict[str, object] | None = None,
    ) -> None: ...

    async def record_model_usage(
        self,
        job: SubagentJobSpec,
        *,
        turn: int,
        attempt: int,
        model_call_id: str,
        usage_receipt: ModelUsageReceipt,
    ) -> None: ...

    async def record_model_call_started(
        self,
        job: SubagentJobSpec,
        *,
        turn: int,
        attempt: int,
        model_call_id: str,
    ) -> None: ...

    async def record_model_call_terminal(
        self,
        job: SubagentJobSpec,
        *,
        turn: int,
        attempt: int,
        model_call_id: str,
        outcome: ModelCallTerminalOutcome,
        error_type: str | None,
        detail: str,
    ) -> None: ...

    async def record_model_usage_with_action(
        self,
        job: SubagentJobSpec,
        *,
        turn: int,
        attempt: int,
        model_call_id: str,
        usage_receipt: ModelUsageReceipt,
        action: SubagentAction,
    ) -> None: ...

    async def load_action_checkpoints(
        self,
        job: SubagentJobSpec,
    ) -> tuple[SubagentActionCheckpoint, ...]: ...


def _require_subagent_model_usage(
    receipt: object,
    *,
    model_id: str,
) -> ModelUsageReceipt:
    if (
        not isinstance(receipt, ModelUsageReceipt)
        or receipt.model_id != model_id
        or receipt.usage.total_tokens <= 0
    ):
        raise SubagentModelUsageError(
            "Subagent provider response requires matching non-zero usage"
        )
    return receipt


def _nonreceipt_model_call_outcome(
    exc: BaseException,
) -> ModelCallTerminalOutcome:
    if getattr(exc, "usage_not_incurred", False) is not True:
        return ModelCallTerminalOutcome.UNRESOLVED
    raw_outcome = str(getattr(exc, "model_call_terminal_outcome", "failed"))
    if raw_outcome == ModelCallTerminalOutcome.CANCELLED.value:
        return ModelCallTerminalOutcome.CANCELLED
    return ModelCallTerminalOutcome.FAILED


class SubagentRuntime:
    """Runs child model loops inside one bounded parent operation; no detached ownership."""

    def __init__(
        self,
        *,
        model: SubagentModelPort,
        tools: SubagentToolPort,
        ledger: SubagentLedgerPort,
        max_concurrency: int = 4,
        max_jobs_per_batch: int = 8,
        monotonic_clock: Callable[[], float] = monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        max_transient_model_retries: int = 2,
        model_call_timeout_seconds: float = 0.0,
        model_call_completion_margin_seconds: float = 0.0,
    ) -> None:
        if (
            max_concurrency < 1
            or max_jobs_per_batch < 1
            or max_transient_model_retries < 0
            or model_call_timeout_seconds < 0
            or model_call_completion_margin_seconds < 0
        ):
            raise ValueError("subagent concurrency and batch limits must be positive")
        self.model = model
        self.tools = tools
        self.ledger = ledger
        self.max_concurrency = max_concurrency
        self.max_jobs_per_batch = max_jobs_per_batch
        self.monotonic_clock = monotonic_clock
        self.sleep = sleep
        self.max_transient_model_retries = max_transient_model_retries
        self.model_call_timeout_seconds = model_call_timeout_seconds
        self.model_call_completion_margin_seconds = model_call_completion_margin_seconds
        self._active: dict[str, asyncio.Task[SubagentJobResult]] = {}
        self._active_waiters: dict[str, int] = {}
        self._terminal: dict[str, SubagentJobResult] = {}
        self._job_fingerprints: dict[str, str] = {}
        self._registry_lock = asyncio.Lock()

    async def run_batch(
        self,
        jobs: tuple[SubagentJobSpec, ...],
        *,
        deadline_monotonic: float,
    ) -> SubagentBatchResult:
        if not jobs or len(jobs) > self.max_jobs_per_batch:
            raise ValueError("subagent batch size is outside the configured limit")
        job_ids = [job.job_id for job in jobs]
        if len(job_ids) != len(set(job_ids)):
            raise ValueError("subagent batch contains duplicate job_id")
        operation_ids = {job.operation_id for job in jobs}
        if len(operation_ids) != 1:
            raise ValueError("all jobs in a batch must share the parent operation_id")

        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def bounded(job: SubagentJobSpec) -> SubagentJobResult:
            async with semaphore:
                return await self._run_stable(job, deadline_monotonic=deadline_monotonic)

        tasks = [
            asyncio.create_task(bounded(job), name=f"subagent-batch:{job.job_id}")
            for job in jobs
        ]
        try:
            results = await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        return SubagentBatchResult(operation_id=jobs[0].operation_id, results=tuple(results))

    async def _run_stable(
        self,
        job: SubagentJobSpec,
        *,
        deadline_monotonic: float,
    ) -> SubagentJobResult:
        fingerprint = subagent_job_fingerprint(job)
        async with self._registry_lock:
            prior_fingerprint = self._job_fingerprints.get(job.job_id)
            if prior_fingerprint is not None and prior_fingerprint != fingerprint:
                raise RuntimeError("subagent job_id was reused with a different semantic request")
            self._job_fingerprints[job.job_id] = fingerprint
            terminal = self._terminal.get(job.job_id)
            if terminal is not None:
                return terminal
            active = self._active.get(job.job_id)
            if active is None:
                active = asyncio.create_task(
                    self._run_job(job, deadline_monotonic=deadline_monotonic),
                    name=f"subagent:{job.job_id}",
                )
                self._active[job.job_id] = active
            self._active_waiters[job.job_id] = (
                self._active_waiters.get(job.job_id, 0) + 1
            )
        cancelled = False
        try:
            result = await asyncio.shield(active)
            async with self._registry_lock:
                self._remember_terminal_result_locked(job.job_id, result)
            return result
        except asyncio.CancelledError:
            cancelled = True
            raise
        finally:
            reap_orphan: asyncio.Task[SubagentJobResult] | None = None
            async with self._registry_lock:
                waiter_count = self._active_waiters.get(job.job_id, 0) - 1
                if waiter_count > 0:
                    self._active_waiters[job.job_id] = waiter_count
                else:
                    self._active_waiters.pop(job.job_id, None)
                if active.done():
                    if not active.cancelled():
                        try:
                            completed_result = active.result()
                        except BaseException:
                            pass
                        else:
                            self._remember_terminal_result_locked(
                                job.job_id,
                                completed_result,
                            )
                    if self._active.get(job.job_id) is active:
                        self._active.pop(job.job_id, None)
                elif cancelled and waiter_count <= 0:
                    active.cancel()
                    if self._active.get(job.job_id) is active:
                        self._active.pop(job.job_id, None)
                    reap_orphan = active
            if reap_orphan is not None:
                await asyncio.gather(reap_orphan, return_exceptions=True)

    def _remember_terminal_result_locked(
        self,
        job_id: str,
        result: SubagentJobResult,
    ) -> None:
        prior = self._terminal.get(job_id)
        if prior is not None and prior.result_sha256 != result.result_sha256:
            raise RuntimeError(
                "duplicate subagent job produced a divergent terminal result"
            )
        self._terminal[job_id] = result

    async def _run_job(
        self,
        job: SubagentJobSpec,
        *,
        deadline_monotonic: float,
    ) -> SubagentJobResult:
        await self.ledger.record_progress(
            job,
            phase="running",
            summary=f"{job.display_name} started",
            payload_json={"role_label": job.role_label},
        )
        steps: list[SubagentStep] = []
        tool_results: list[SubagentToolResult] = []
        tool_steps_used = 0
        successful_tool_requests: set[str] = set()
        published_milestones: set[tuple[str, str]] = set()
        partial: dict[str, object] = {}
        checkpoint_loader = getattr(self.ledger, "load_action_checkpoints", None)
        checkpoints = (
            await checkpoint_loader(job)
            if checkpoint_loader is not None
            else ()
        )
        checkpoints_by_turn = {item.turn: item for item in checkpoints}
        base_context_bytes = len(
            json.dumps(
                job.model_dump(mode="json", exclude={"budget"}),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        hydrated_context_bytes = 0
        for context_read in job.context_reads:
            if await self._command_pending(job):
                return await self._command_interrupted_result(
                    job,
                    partial=partial,
                    turns=0,
                    tools=tool_steps_used,
                    tool_results=tuple(tool_results),
                )
            if tool_steps_used >= job.budget.max_tool_steps:
                return await self._terminal_result(
                    job,
                    status=SubagentStatus.FAILED,
                    stop_reason=SubagentStopReason.TOOL_UNAVAILABLE,
                    summary="所选材料超过本次成员可读取的工具预算",
                    result_json={},
                    turns=0,
                    tools=tool_steps_used,
                    tool_results=tuple(tool_results),
                )
            if self.monotonic_clock() >= deadline_monotonic:
                return await self._terminal_result(
                    job,
                    status=SubagentStatus.TIMED_OUT,
                    stop_reason=SubagentStopReason.DEADLINE_REACHED,
                    summary="研究成员在读取所选材料时到达本次协作时限",
                    result_json={},
                    turns=0,
                    tools=tool_steps_used,
                    tool_results=tuple(tool_results),
                )
            request_fingerprint = _tool_request_fingerprint(
                context_read.tool_name,
                context_read.arguments,
            )
            steps.append(
                SubagentStep(
                    turn=1,
                    kind="tool",
                    summary=f"Load selected context: {context_read.ref}",
                    tool_name=context_read.tool_name,
                )
            )
            try:
                tool_result = await self.tools.execute(
                    SubagentToolRequest(
                        job_id=job.job_id,
                        operation_id=job.operation_id,
                        mission_id=job.mission_id,
                        workspace_id=job.workspace_id,
                        lease_owner=job.lease_owner,
                        lease_epoch=job.lease_epoch,
                        stage_id=job.stage_id,
                        tool_name=context_read.tool_name,
                        arguments=context_read.arguments,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "Subagent selected-context read failed job=%s tool=%s error=%s",
                    job.job_id,
                    context_read.tool_name,
                    type(exc).__name__,
                    exc_info=True,
                )
                tool_result = SubagentToolResult(
                    status="failed",
                    summary="Selected context could not be loaded",
                    error_type=type(exc).__name__,
                )
            tool_results.append(tool_result)
            tool_steps_used += 1
            hydrated_context_bytes += len(
                json.dumps(
                    tool_result.model_dump(mode="json"),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            if (
                base_context_bytes + hydrated_context_bytes
                > job.budget.max_context_bytes
            ):
                return await self._terminal_result(
                    job,
                    status=SubagentStatus.FAILED,
                    stop_reason=SubagentStopReason.TOKEN_CAPPED,
                    summary="所选材料内容超过本次成员的上下文预算",
                    result_json={},
                    turns=0,
                    tools=tool_steps_used,
                    tool_results=tuple(tool_results),
                )
            if tool_result.status == "completed":
                successful_tool_requests.add(request_fingerprint)
            steps.append(
                SubagentStep(
                    turn=1,
                    kind="tool_result",
                    summary=tool_result.summary,
                    tool_name=context_read.tool_name,
                    payload_ref=tool_result.payload_ref,
                )
            )
            await self.ledger.record_progress(
                job,
                phase="progress",
                summary=tool_result.summary,
                payload_json={
                    "tool_name": context_read.tool_name,
                    "selected_ref": context_read.ref,
                    "status": tool_result.status,
                    "context_hydration": True,
                    "error_type": tool_result.error_type,
                    "recoverable": tool_result.recoverable,
                    "evidence_refs": list(tool_result.evidence_refs),
                    "artifact_refs": list(tool_result.artifact_refs),
                },
            )
        for turn in range(1, job.budget.max_turns + 1):
            if await self._command_pending(job):
                return await self._command_interrupted_result(
                    job,
                    partial=partial,
                    turns=turn - 1,
                    tools=tool_steps_used,
                    tool_results=tuple(tool_results),
                )
            if self.monotonic_clock() >= deadline_monotonic:
                return await self._terminal_result(
                    job,
                    status=SubagentStatus.TIMED_OUT,
                    stop_reason=(SubagentStopReason.PARTIAL_RESULT_AVAILABLE if partial else SubagentStopReason.DEADLINE_REACHED),
                    summary="研究成员到达本次协作时限",
                    result_json=partial,
                    turns=turn - 1,
                    tools=tool_steps_used,
                    tool_results=tuple(tool_results),
                )
            finalization_only = (
                turn == job.budget.max_turns
                or tool_steps_used >= job.budget.max_tool_steps
            )
            model_steps = tuple(steps)
            if finalization_only:
                model_steps = (
                    *model_steps,
                    SubagentStep(
                        turn=turn,
                        kind="progress",
                        summary=_FINAL_SYNTHESIS_INSTRUCTION,
                    ),
                )
            try:
                checkpoint = checkpoints_by_turn.get(turn)
                if checkpoint is not None:
                    action = checkpoint.action
                else:
                    model_turn = await self._next_model_action_with_retry(
                        job,
                        turn=turn,
                        steps=model_steps,
                        tool_results=tuple(tool_results),
                        deadline_monotonic=deadline_monotonic,
                    )
                    action = model_turn.action
                if await self._command_pending(job):
                    if action.partial_result_json:
                        partial = dict(action.partial_result_json)
                    return await self._command_interrupted_result(
                        job,
                        partial=partial,
                        turns=turn,
                        tools=tool_steps_used,
                        tool_results=tuple(tool_results),
                    )
            except SubagentModelAdmissionDeferred:
                return await self._terminal_result(
                    job,
                    status=(SubagentStatus.COMPLETED if partial else SubagentStatus.TIMED_OUT),
                    stop_reason=(
                        SubagentStopReason.PARTIAL_RESULT_AVAILABLE
                        if partial
                        else SubagentStopReason.DEADLINE_REACHED
                    ),
                    summary="剩余协作时间不足以安全完成下一次模型分析，已保留当前进度",
                    result_json=partial,
                    turns=turn - 1,
                    tools=tool_steps_used,
                    tool_results=tuple(tool_results),
                )
            except SubagentModelOutputError as exc:
                retry_summary = f"Structured worker response was invalid; retrying within the bounded turn budget. Repair requirement: {exc}"
                steps.append(
                    SubagentStep(
                        turn=turn,
                        kind="progress",
                        summary=retry_summary,
                    )
                )
                await self.ledger.record_progress(
                    job,
                    phase="progress",
                    summary="Structured worker response was invalid; retrying within the bounded turn budget",
                    payload_json={
                        "status": "model_output_retry",
                        "diagnostic": str(exc)[:500],
                    },
                )
                if turn < job.budget.max_turns:
                    continue
                return await self._terminal_result(
                    job,
                    status=SubagentStatus.FAILED,
                    stop_reason=SubagentStopReason.MALFORMED_MODEL_OUTPUT,
                    summary="结构化结果多次未通过校验，已保留可用进度",
                    result_json=partial,
                    turns=turn,
                    tools=tool_steps_used,
                    warnings=(type(exc).__name__,),
                    tool_results=tuple(tool_results),
                )
            except Exception as exc:
                return await self._terminal_result(
                    job,
                    status=SubagentStatus.FAILED,
                    stop_reason=SubagentStopReason.MODEL_ERROR,
                    summary="Subagent model step failed",
                    result_json=partial,
                    turns=turn - 1,
                    tools=tool_steps_used,
                    warnings=(type(exc).__name__,),
                    tool_results=tuple(tool_results),
                )

            if action.partial_result_json:
                partial = dict(action.partial_result_json)
            if action.kind == "progress":
                if finalization_only:
                    return await self._terminal_result(
                        job,
                        status=(
                            SubagentStatus.COMPLETED
                            if partial
                            else SubagentStatus.FAILED
                        ),
                        stop_reason=SubagentStopReason.LOOP_CAPPED,
                        summary="阶段进展已保存，但本轮已没有足够步骤完成最终汇总",
                        result_json=partial,
                        turns=turn,
                        tools=tool_steps_used,
                        tool_results=tuple(tool_results),
                    )
                progress_kind = action.progress_kind or "checkpoint"
                milestone_key = (progress_kind, action.summary.strip())
                if milestone_key not in published_milestones:
                    published_milestones.add(milestone_key)
                    steps.append(
                        SubagentStep(
                            turn=turn,
                            kind="progress",
                            summary=action.summary,
                        )
                    )
                    await self.ledger.record_progress(
                        job,
                        phase="progress",
                        summary=action.summary,
                        payload_json={
                            "status": "milestone",
                            "progress_kind": progress_kind,
                        },
                    )
                else:
                    steps.append(
                        SubagentStep(
                            turn=turn,
                            kind="progress",
                            summary=(
                                "重复阶段进展未再次发布；请继续实质工作或完成任务"
                            ),
                        )
                    )
                continue
            if action.kind == "complete":
                schema_errors = _validate_output_contract(action.result_json, job.output_schema)
                if schema_errors:
                    await self.ledger.record_progress(
                        job,
                        phase="progress",
                        summary="Worker result did not satisfy its output contract; retrying within the bounded turn budget",
                        payload_json={
                            "status": "output_contract_retry",
                            "diagnostic": schema_errors[:10],
                        },
                    )
                    if turn < job.budget.max_turns:
                        steps.append(
                            SubagentStep(
                                turn=turn,
                                kind="progress",
                                summary=(
                                    "Pinned output contract validation failed; repair the result: "
                                    + "; ".join(schema_errors[:5])
                                ),
                            )
                        )
                        continue
                    return await self._terminal_result(
                        job,
                        status=SubagentStatus.FAILED,
                        stop_reason=SubagentStopReason.MALFORMED_MODEL_OUTPUT,
                        summary="Subagent result did not satisfy its pinned output contract",
                        result_json={"validation_errors": schema_errors[:20]},
                        turns=turn,
                        tools=tool_steps_used,
                        tool_results=tuple(tool_results),
                    )
                reference_errors = _validate_receipt_backed_result_refs(
                    action.result_json,
                    tool_results,
                )
                if reference_errors:
                    retry_summary = (
                        "Structured worker result cited references that were not returned by its tools; "
                        "reuse only exact receipt refs. " + "; ".join(reference_errors[:5])
                    )
                    steps.append(
                        SubagentStep(
                            turn=turn,
                            kind="progress",
                            summary=retry_summary,
                        )
                    )
                    await self.ledger.record_progress(
                        job,
                        phase="progress",
                        summary="Worker result contained unverified references; retrying within the bounded turn budget",
                        payload_json={
                            "status": "reference_retry",
                            "diagnostic": reference_errors[:10],
                        },
                    )
                    if turn < job.budget.max_turns:
                        continue
                    return await self._terminal_result(
                        job,
                        status=SubagentStatus.FAILED,
                        stop_reason=SubagentStopReason.MALFORMED_MODEL_OUTPUT,
                        summary="Subagent result cited references that were not returned by its tools",
                        result_json={"validation_errors": reference_errors[:20]},
                        turns=turn,
                        tools=tool_steps_used,
                        tool_results=tuple(tool_results),
                    )
                return await self._terminal_result(
                    job,
                    status=SubagentStatus.COMPLETED,
                    stop_reason=SubagentStopReason.NORMAL,
                    summary=_completed_result_summary(action),
                    result_json=action.result_json,
                    turns=turn,
                    tools=tool_steps_used,
                    tool_results=tuple(tool_results),
                )
            if action.kind == "stop":
                reason = action.stop_reason or SubagentStopReason.LOOP_CAPPED
                status = SubagentStatus.COMPLETED if partial else SubagentStatus.FAILED
                return await self._terminal_result(
                    job,
                    status=status,
                    stop_reason=reason,
                    summary=action.summary,
                    result_json=partial,
                    turns=turn,
                    tools=tool_steps_used,
                    tool_results=tuple(tool_results),
                )

            if self.monotonic_clock() >= deadline_monotonic:
                return await self._terminal_result(
                    job,
                    status=(
                        SubagentStatus.COMPLETED
                        if partial
                        else SubagentStatus.TIMED_OUT
                    ),
                    stop_reason=(
                        SubagentStopReason.PARTIAL_RESULT_AVAILABLE
                        if partial
                        else SubagentStopReason.DEADLINE_REACHED
                    ),
                    summary="模型分析已完成，但本轮剩余时间不足以安全启动工具",
                    result_json=partial,
                    turns=turn,
                    tools=tool_steps_used,
                    tool_results=tuple(tool_results),
                )

            tool_name = action.tool_name or ""
            if tool_name not in job.allowed_tools:
                return await self._terminal_result(
                    job,
                    status=SubagentStatus.FAILED,
                    stop_reason=SubagentStopReason.PERMISSION_DENIED,
                    summary=f"Subagent requested a tool outside its allowlist: {tool_name}",
                    result_json=partial,
                    turns=turn,
                    tools=tool_steps_used,
                    tool_results=tuple(tool_results),
                )
            request_fingerprint = _tool_request_fingerprint(tool_name, action.arguments)
            if request_fingerprint in successful_tool_requests:
                duplicate_summary = "Duplicate successful tool request skipped; reuse the prior result and complete or stop"
                steps.append(
                    SubagentStep(
                        turn=turn,
                        kind="progress",
                        summary=duplicate_summary,
                        tool_name=tool_name,
                    )
                )
                await self.ledger.record_progress(
                    job,
                    phase="progress",
                    summary=duplicate_summary,
                    payload_json={"tool_name": tool_name, "status": "duplicate_skipped"},
                )
                continue
            if finalization_only:
                return await self._terminal_result(
                    job,
                    status=SubagentStatus.COMPLETED if partial else SubagentStatus.FAILED,
                    stop_reason=SubagentStopReason.LOOP_CAPPED,
                    summary="Worker used its final synthesis turn without producing a complete result",
                    result_json=partial,
                    turns=turn,
                    tools=tool_steps_used,
                    tool_results=tuple(tool_results),
                )
            steps.append(SubagentStep(turn=turn, kind="tool", summary=action.summary, tool_name=tool_name))
            if await self._command_pending(job):
                return await self._command_interrupted_result(
                    job,
                    partial=partial,
                    turns=turn,
                    tools=tool_steps_used,
                    tool_results=tuple(tool_results),
                )
            try:
                tool_result = await self.tools.execute(
                    SubagentToolRequest(
                        job_id=job.job_id,
                        operation_id=job.operation_id,
                        mission_id=job.mission_id,
                        workspace_id=job.workspace_id,
                        lease_owner=job.lease_owner,
                        lease_epoch=job.lease_epoch,
                        stage_id=job.stage_id,
                        tool_name=tool_name,
                        arguments=action.arguments,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "Subagent tool failed before a typed result job=%s tool=%s error=%s",
                    job.job_id,
                    tool_name,
                    type(exc).__name__,
                    exc_info=True,
                )
                tool_result = SubagentToolResult(
                    status="failed",
                    summary="Tool invocation failed before producing a typed result",
                    error_type=type(exc).__name__,
                )
            tool_results.append(tool_result)
            tool_steps_used += 1
            if tool_result.status == "completed":
                successful_tool_requests.add(request_fingerprint)
            steps.append(
                SubagentStep(
                    turn=turn,
                    kind="tool_result",
                    summary=tool_result.summary,
                    tool_name=tool_name,
                    payload_ref=tool_result.payload_ref,
                )
            )
            await self.ledger.record_progress(
                job,
                phase="progress",
                summary=tool_result.summary,
                payload_json={
                    "tool_name": tool_name,
                    "status": tool_result.status,
                    "error_type": tool_result.error_type,
                    "recoverable": tool_result.recoverable,
                    "evidence_refs": list(tool_result.evidence_refs),
                    "artifact_refs": list(tool_result.artifact_refs),
                },
            )

        return await self._terminal_result(
            job,
            status=SubagentStatus.COMPLETED if partial else SubagentStatus.FAILED,
            stop_reason=SubagentStopReason.TURN_CAPPED,
            summary="达到本轮分析步数上限，已保留可用进度",
            result_json=partial,
            turns=job.budget.max_turns,
            tools=tool_steps_used,
            tool_results=tuple(tool_results),
        )

    async def _next_model_action_with_retry(
        self,
        job: SubagentJobSpec,
        *,
        turn: int,
        steps: tuple[SubagentStep, ...],
        tool_results: tuple[SubagentToolResult, ...],
        deadline_monotonic: float,
    ) -> SubagentModelTurn:
        transient_attempt = 0
        while True:
            remaining = deadline_monotonic - self.monotonic_clock()
            required = (
                self.model_call_timeout_seconds
                + self.model_call_completion_margin_seconds
            )
            if required > 0 and remaining < required:
                raise SubagentModelAdmissionDeferred(
                    "insufficient slice time for a receipt-bearing subagent model call"
                )
            attempt = transient_attempt + 1
            model_call_id = subagent_model_call_id(
                job,
                turn=turn,
                attempt=attempt,
            )
            await self.ledger.record_model_call_started(
                job,
                turn=turn,
                attempt=attempt,
                model_call_id=model_call_id,
            )
            try:
                model_turn = await self.model.next_action(job, steps, tool_results)
            except asyncio.CancelledError as exc:
                try:
                    await asyncio.shield(
                        self.ledger.record_model_call_terminal(
                            job,
                            turn=turn,
                            attempt=attempt,
                            model_call_id=model_call_id,
                            outcome=ModelCallTerminalOutcome.UNRESOLVED,
                            error_type=type(exc).__name__,
                            detail=(
                                "Subagent model call was cancelled before usage "
                                "could be confirmed"
                            ),
                        )
                    )
                finally:
                    raise
            except SubagentModelOutputError as exc:
                try:
                    usage_receipt = _require_subagent_model_usage(
                        exc.usage_receipt,
                        model_id=job.model_id,
                    )
                except SubagentModelUsageError as usage_exc:
                    await self.ledger.record_model_call_terminal(
                        job,
                        turn=turn,
                        attempt=attempt,
                        model_call_id=model_call_id,
                        outcome=ModelCallTerminalOutcome.UNRESOLVED,
                        error_type=type(usage_exc).__name__,
                        detail=str(usage_exc),
                    )
                    raise
                await self.ledger.record_model_usage(
                    job,
                    turn=turn,
                    attempt=attempt,
                    model_call_id=model_call_id,
                    usage_receipt=usage_receipt,
                )
                raise
            except Exception as exc:
                terminal_outcome = _nonreceipt_model_call_outcome(exc)
                await self.ledger.record_model_call_terminal(
                    job,
                    turn=turn,
                    attempt=attempt,
                    model_call_id=model_call_id,
                    outcome=terminal_outcome,
                    error_type=type(exc).__name__,
                    detail=str(exc)[:1000] or type(exc).__name__,
                )
                if terminal_outcome is ModelCallTerminalOutcome.UNRESOLVED:
                    raise SubagentModelUsageError(
                        "Subagent model usage could not be confirmed"
                    ) from exc
                if not is_transient_model_error(exc) or transient_attempt >= self.max_transient_model_retries:
                    raise
                transient_attempt += 1
                delay = _transient_model_retry_delay(
                    exc,
                    job_id=job.job_id,
                    attempt=transient_attempt,
                )
                if self.monotonic_clock() + delay >= deadline_monotonic:
                    raise
                await self.ledger.record_progress(
                    job,
                    phase="progress",
                    summary="Model service is busy; preserving worker context and retrying",
                    payload_json={
                        "status": "transient_model_retry",
                        "attempt": transient_attempt,
                        "retry_after_seconds": delay,
                        "error_type": type(exc).__name__,
                    },
                )
                await self.sleep(delay)
                continue
            try:
                usage_receipt = _require_subagent_model_usage(
                    getattr(model_turn, "usage_receipt", None),
                    model_id=job.model_id,
                )
            except SubagentModelUsageError as exc:
                await self.ledger.record_model_call_terminal(
                    job,
                    turn=turn,
                    attempt=attempt,
                    model_call_id=model_call_id,
                    outcome=ModelCallTerminalOutcome.UNRESOLVED,
                    error_type=type(exc).__name__,
                    detail=str(exc),
                )
                raise
            atomic_recorder = getattr(
                self.ledger,
                "record_model_usage_with_action",
                None,
            )
            if atomic_recorder is not None:
                await atomic_recorder(
                    job,
                    turn=turn,
                    attempt=attempt,
                    model_call_id=model_call_id,
                    usage_receipt=usage_receipt,
                    action=model_turn.action,
                )
            else:
                await self.ledger.record_model_usage(
                    job,
                    turn=turn,
                    attempt=attempt,
                    model_call_id=model_call_id,
                    usage_receipt=usage_receipt,
                )
            return model_turn

    async def _terminal_result(
        self,
        job: SubagentJobSpec,
        *,
        status: SubagentStatus,
        stop_reason: SubagentStopReason,
        summary: str,
        result_json: dict[str, object],
        turns: int,
        tools: int,
        warnings: tuple[str, ...] = (),
        tool_results: tuple[SubagentToolResult, ...] = (),
    ) -> SubagentJobResult:
        tool_failure_warnings = tuple(
            dict.fromkeys(
                f"tool_failure:{item.error_type or 'typed_failure'}"
                for item in tool_results
                if item.status == "failed"
            )
        )
        warnings = (*warnings, *tool_failure_warnings)
        encoded = json.dumps(result_json, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        result_oversized = len(encoded) > job.budget.max_result_bytes
        if result_oversized:
            result_json = {
                "validation_errors": [
                    "result exceeded the pinned durable inline byte budget"
                ]
            }
            encoded = json.dumps(result_json, sort_keys=True).encode()
            warnings = (*warnings, "result_exceeded_inline_budget")
            stop_reason = SubagentStopReason.TOKEN_CAPPED
            status = SubagentStatus.FAILED
        partial_result_available = False
        if (
            result_json
            and stop_reason is not SubagentStopReason.NORMAL
            and not result_oversized
        ):
            partial_schema_errors = _validate_output_contract(result_json, job.output_schema)
            partial_reference_errors = _validate_receipt_backed_result_refs(
                result_json,
                list(tool_results),
            )
            partial_result_available = not (
                partial_schema_errors or partial_reference_errors
            )
            if partial_schema_errors:
                warnings = (*warnings, "partial_result_contract_invalid")
            if partial_reference_errors:
                warnings = (*warnings, "partial_result_refs_unverified")
        if status is SubagentStatus.COMPLETED and stop_reason is not SubagentStopReason.NORMAL:
            if not partial_result_available:
                status = SubagentStatus.FAILED
        result = SubagentJobResult(
            job_id=job.job_id,
            operation_id=job.operation_id,
            display_name=job.display_name,
            role_label=job.role_label,
            status=status,
            stop_reason=stop_reason,
            result_brief=summary,
            result_json=result_json,
            result_sha256=hashlib.sha256(encoded).hexdigest(),
            evidence_refs=tuple(dict.fromkeys(ref for item in tool_results for ref in item.evidence_refs)),
            artifact_refs=tuple(dict.fromkeys(ref for item in tool_results for ref in item.artifact_refs)),
            warnings=warnings,
            turns_used=turns,
            tool_steps_used=tools,
            partial_result_available=partial_result_available,
        )
        await self.ledger.record_progress(
            job,
            phase="terminal",
            summary=summary,
            payload_json={
                "status": status.value,
                "stop_reason": stop_reason.value,
                "result_sha256": result.result_sha256,
                "job_fingerprint": subagent_job_fingerprint(job),
                "frozen_budget": job.budget.model_dump(mode="json"),
                "result": result.model_dump(mode="json"),
            },
        )
        return result

    async def _command_pending(self, job: SubagentJobSpec) -> bool:
        checker = getattr(self.ledger, "command_pending", None)
        if checker is None:
            return False
        return bool(await checker(job))

    async def _command_interrupted_result(
        self,
        job: SubagentJobSpec,
        *,
        partial: dict[str, object],
        turns: int,
        tools: int,
        tool_results: tuple[SubagentToolResult, ...],
    ) -> SubagentJobResult:
        return await self._terminal_result(
            job,
            status=SubagentStatus.CANCELLED,
            stop_reason=SubagentStopReason.CANCELLED,
            summary="收到新的研究要求，成员已在安全边界停止当前工作",
            result_json=partial,
            turns=turns,
            tools=tools,
            tool_results=tool_results,
        )

    async def cancel_all(self) -> None:
        async with self._registry_lock:
            tasks = tuple(self._active.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        async with self._registry_lock:
            for job_id, task in tuple(self._active.items()):
                if task.done():
                    self._active.pop(job_id, None)


def _tool_request_fingerprint(tool_name: str, arguments: dict[str, object]) -> str:
    encoded = json.dumps(
        {"tool_name": tool_name, "arguments": arguments},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=repr,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def subagent_model_call_id(
    job: SubagentJobSpec,
    *,
    turn: int,
    attempt: int,
) -> str:
    identity = f"{job.job_id}:{job.lease_epoch}:{turn}:{attempt}"
    digest = hashlib.sha256(identity.encode()).hexdigest()
    return f"model-call:subagent:{digest}"


def _transient_model_retry_delay(
    exc: BaseException,
    *,
    job_id: str,
    attempt: int,
) -> float:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    raw_retry_after = headers.get("retry-after") if headers is not None else None
    try:
        provider_delay = float(raw_retry_after) if raw_retry_after is not None else 0.0
    except (TypeError, ValueError):
        provider_delay = 0.0
    jitter = int(hashlib.sha256(job_id.encode()).hexdigest()[:2], 16) % 5
    if is_rate_limit_error(exc):
        return min(max(provider_delay, 45.0 if attempt == 1 else 60.0) + jitter, 90.0)
    return min(max(provider_delay, float(2**attempt)) + jitter, 20.0)


def _completed_result_summary(action: SubagentAction) -> str:
    structured_summary = action.result_json.get("summary")
    if isinstance(structured_summary, str) and structured_summary.strip():
        return structured_summary.strip()[:4_000]
    return action.summary


def _validate_output_contract(value: object, schema: dict[str, object]) -> list[str]:
    if not schema:
        return []
    try:
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
    except SchemaError as exc:
        return [f"pinned output contract is invalid: {exc.message}"]
    errors: list[str] = []
    for error in sorted(
        validator.iter_errors(value),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    ):
        path = "$" + "".join(
            f"[{part}]" if isinstance(part, int) else f".{part}"
            for part in error.absolute_path
        )
        errors.append(f"{path}: {error.message}")
    return errors


def _validate_receipt_backed_result_refs(
    value: object,
    tool_results: list[SubagentToolResult],
) -> list[str]:
    allowed_by_field = {
        "evidence_refs": {
            ref for result in tool_results for ref in result.evidence_refs
        },
        "artifact_refs": {
            ref for result in tool_results for ref in result.artifact_refs
        },
    }
    errors: list[str] = []

    def visit(node: object, *, path: str) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                child_path = f"{path}.{key}"
                if key in allowed_by_field:
                    if not isinstance(child, list):
                        errors.append(f"{child_path} must be an array of receipt refs")
                        continue
                    for index, ref in enumerate(child):
                        if not isinstance(ref, str):
                            errors.append(
                                f"{child_path}[{index}] must be a string receipt ref"
                            )
                        elif ref not in allowed_by_field[key]:
                            errors.append(f"{child_path}[{index}] is not backed by a tool receipt")
                    continue
                visit(child, path=child_path)
        elif isinstance(node, list):
            for index, child in enumerate(node):
                visit(child, path=f"{path}[{index}]")

    visit(value, path="$")
    return errors


def subagent_job_fingerprint(job: SubagentJobSpec) -> str:
    semantic = job.model_dump(
        mode="json",
        exclude={"lease_owner", "lease_epoch"},
    )
    encoded = json.dumps(
        semantic,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "SubagentLedgerPort",
    "SubagentModelPort",
    "SubagentRuntime",
    "SubagentToolPort",
    "subagent_job_fingerprint",
    "subagent_model_call_id",
]
