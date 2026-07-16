"""Bounded in-slice SubagentRuntime with isolated child contexts."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Protocol

from src.models.provider_errors import is_rate_limit_error, is_transient_model_error
from src.subagent_runtime.contracts import (
    SubagentAction,
    SubagentBatchResult,
    SubagentJobResult,
    SubagentJobSpec,
    SubagentModelOutputError,
    SubagentStatus,
    SubagentStep,
    SubagentStopReason,
    SubagentToolRequest,
    SubagentToolResult,
)


class SubagentModelPort(Protocol):
    async def next_action(
        self,
        job: SubagentJobSpec,
        steps: tuple[SubagentStep, ...],
        tool_results: tuple[SubagentToolResult, ...],
    ) -> SubagentAction: ...


class SubagentToolPort(Protocol):
    async def execute(self, request: SubagentToolRequest) -> SubagentToolResult: ...


class SubagentLedgerPort(Protocol):
    async def record_progress(
        self,
        job: SubagentJobSpec,
        *,
        phase: str,
        summary: str,
        payload_json: dict[str, object] | None = None,
    ) -> None: ...


class SubagentRuntime:
    """Runs child model loops inside one parent slice; no detached ownership."""

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
    ) -> None:
        if max_concurrency < 1 or max_jobs_per_batch < 1 or max_transient_model_retries < 0:
            raise ValueError("subagent concurrency and batch limits must be positive")
        self.model = model
        self.tools = tools
        self.ledger = ledger
        self.max_concurrency = max_concurrency
        self.max_jobs_per_batch = max_jobs_per_batch
        self.monotonic_clock = monotonic_clock
        self.sleep = sleep
        self.max_transient_model_retries = max_transient_model_retries
        self._active: dict[str, asyncio.Task[SubagentJobResult]] = {}
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

        results = await asyncio.gather(*(bounded(job) for job in jobs))
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
        try:
            result = await asyncio.shield(active)
        except asyncio.CancelledError:
            active.cancel()
            await asyncio.gather(active, return_exceptions=True)
            raise
        finally:
            if active.done():
                async with self._registry_lock:
                    self._active.pop(job.job_id, None)
        async with self._registry_lock:
            prior = self._terminal.get(job.job_id)
            if prior is not None and prior.result_sha256 != result.result_sha256:
                raise RuntimeError("duplicate subagent job produced a divergent terminal result")
            self._terminal[job.job_id] = result
        return result

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
        successful_tool_requests: set[str] = set()
        partial: dict[str, object] = {}
        for context_read in job.context_reads:
            if self.monotonic_clock() >= deadline_monotonic:
                return await self._terminal_result(
                    job,
                    status=SubagentStatus.TIMED_OUT,
                    stop_reason=SubagentStopReason.DEADLINE_REACHED,
                    summary="Subagent reached the parent slice deadline while loading selected context",
                    result_json={},
                    turns=0,
                    tools=len(tool_results),
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
                tool_result = SubagentToolResult(
                    status="failed",
                    summary="Selected context could not be loaded",
                    error_type=type(exc).__name__,
                )
            tool_results.append(tool_result)
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
                    "evidence_refs": list(tool_result.evidence_refs),
                    "artifact_refs": list(tool_result.artifact_refs),
                },
            )
        for turn in range(1, job.budget.max_turns + 1):
            if self.monotonic_clock() >= deadline_monotonic:
                return await self._terminal_result(
                    job,
                    status=SubagentStatus.TIMED_OUT,
                    stop_reason=(SubagentStopReason.PARTIAL_RESULT_AVAILABLE if partial else SubagentStopReason.DEADLINE_REACHED),
                    summary="Subagent reached the parent slice deadline",
                    result_json=partial,
                    turns=turn - 1,
                    tools=len(tool_results),
                    tool_results=tuple(tool_results),
                )
            try:
                action = await self._next_model_action_with_retry(
                    job,
                    steps=tuple(steps),
                    tool_results=tuple(tool_results),
                    deadline_monotonic=deadline_monotonic,
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
                    summary="Subagent exhausted its retries for structured model output",
                    result_json=partial,
                    turns=turn,
                    tools=len(tool_results),
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
                    tools=len(tool_results),
                    warnings=(type(exc).__name__,),
                    tool_results=tuple(tool_results),
                )

            if action.partial_result_json:
                partial = dict(action.partial_result_json)
            if action.kind == "complete":
                schema_errors = _validate_output_contract(action.result_json, job.output_schema)
                if schema_errors:
                    return await self._terminal_result(
                        job,
                        status=SubagentStatus.FAILED,
                        stop_reason=SubagentStopReason.MALFORMED_MODEL_OUTPUT,
                        summary="Subagent result did not satisfy its pinned output contract",
                        result_json={"validation_errors": schema_errors[:20]},
                        turns=turn,
                        tools=len(tool_results),
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
                        tools=len(tool_results),
                        tool_results=tuple(tool_results),
                    )
                return await self._terminal_result(
                    job,
                    status=SubagentStatus.COMPLETED,
                    stop_reason=SubagentStopReason.NORMAL,
                    summary=_completed_result_summary(action),
                    result_json=action.result_json,
                    turns=turn,
                    tools=len(tool_results),
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
                    tools=len(tool_results),
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
                    tools=len(tool_results),
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
            if len(tool_results) >= job.budget.max_tool_steps:
                return await self._terminal_result(
                    job,
                    status=SubagentStatus.COMPLETED if partial else SubagentStatus.FAILED,
                    stop_reason=SubagentStopReason.LOOP_CAPPED,
                    summary="Subagent exhausted its tool-step budget",
                    result_json=partial,
                    turns=turn,
                    tools=len(tool_results),
                    tool_results=tuple(tool_results),
                )
            steps.append(SubagentStep(turn=turn, kind="tool", summary=action.summary, tool_name=tool_name))
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
                tool_result = SubagentToolResult(
                    status="failed",
                    summary="Tool invocation failed before producing a typed result",
                    error_type=type(exc).__name__,
                )
            tool_results.append(tool_result)
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
                    "evidence_refs": list(tool_result.evidence_refs),
                    "artifact_refs": list(tool_result.artifact_refs),
                },
            )

        return await self._terminal_result(
            job,
            status=SubagentStatus.COMPLETED if partial else SubagentStatus.FAILED,
            stop_reason=SubagentStopReason.TURN_CAPPED,
            summary="Subagent exhausted its model-turn budget",
            result_json=partial,
            turns=job.budget.max_turns,
            tools=len(tool_results),
            tool_results=tuple(tool_results),
        )

    async def _next_model_action_with_retry(
        self,
        job: SubagentJobSpec,
        *,
        steps: tuple[SubagentStep, ...],
        tool_results: tuple[SubagentToolResult, ...],
        deadline_monotonic: float,
    ) -> SubagentAction:
        transient_attempt = 0
        while True:
            try:
                return await self.model.next_action(job, steps, tool_results)
            except Exception as exc:
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
        encoded = json.dumps(result_json, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(encoded) > min(job.budget.max_result_bytes, 48 * 1024):
            result_json = {"externalization_required": True}
            encoded = json.dumps(result_json, sort_keys=True).encode()
            warnings = (*warnings, "result_exceeded_inline_budget")
            if stop_reason is SubagentStopReason.NORMAL:
                stop_reason = SubagentStopReason.TOKEN_CAPPED
        partial_result_available = False
        if result_json and stop_reason is not SubagentStopReason.NORMAL:
            partial_schema_errors = _validate_output_contract(result_json, job.output_schema)
            partial_result_available = not partial_schema_errors
            if partial_schema_errors:
                warnings = (*warnings, "partial_result_contract_invalid")
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
                "result": result.model_dump(mode="json"),
            },
        )
        return result

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
    errors: list[str] = []
    _validate_schema_node(value, schema, path="$", errors=errors)
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
                if key in allowed_by_field and isinstance(child, list):
                    for index, ref in enumerate(child):
                        if (
                            isinstance(ref, str)
                            and ref not in allowed_by_field[key]
                        ):
                            errors.append(f"{child_path}[{index}] is not backed by a tool receipt")
                    continue
                visit(child, path=child_path)
        elif isinstance(node, list):
            for index, child in enumerate(node):
                visit(child, path=f"{path}[{index}]")

    visit(value, path="$")
    return errors


def _validate_schema_node(
    value: object,
    schema: dict[str, object],
    *,
    path: str,
    errors: list[str],
) -> None:
    expected = schema.get("type")
    type_matches = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }
    if isinstance(expected, str) and expected in type_matches and not type_matches[expected]:
        errors.append(f"{path} must be {expected}")
        return
    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        errors.append(f"{path} is not an allowed value")
    if isinstance(value, dict):
        required = schema.get("required")
        if isinstance(required, list):
            for key in required:
                if isinstance(key, str) and key not in value:
                    errors.append(f"{path}.{key} is required")
        properties = schema.get("properties")
        if isinstance(properties, dict):
            for key, child_schema in properties.items():
                if key in value and isinstance(child_schema, dict):
                    _validate_schema_node(value[key], child_schema, path=f"{path}.{key}", errors=errors)
    if isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_schema_node(item, item_schema, path=f"{path}[{index}]", errors=errors)


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
]
