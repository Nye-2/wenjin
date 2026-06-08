"""LangChain adapter for Wenjin harness tools."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from langchain_core.tools import StructuredTool
from langgraph.errors import GraphBubbleUp
from pydantic import BaseModel, Field

from src.agents.lead_agent.v2.sandbox_runtime_session import SandboxRuntimeSession
from src.subagents.v2.base import SubagentContext

from .args_summary import summarize_tool_args
from .builtins import default_harness_tool_registry
from .business_tools import BUSINESS_TOOL_NAMES, build_business_langchain_tools
from .contracts import HarnessPolicy, HarnessRunContext, HarnessToolResult
from .events import publish_harness_event
from .loop_guard import HarnessLoopGuard
from .policy import CANONICAL_TOOL_ALIASES, resolve_harness_policy
from .sandbox_execution_tools import SandboxExecutionTools
from .sandbox_tools import SandboxFileTools
from .scheduler import default_workspace_tool_scheduler


class ReadFileInput(BaseModel):
    path: str
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    max_chars: int | None = Field(default=None, ge=1)


class ListDirInput(BaseModel):
    path: str = "/workspace"
    max_depth: int = Field(default=1, ge=1, le=3)


class GlobInput(BaseModel):
    pattern: str
    max_matches: int | None = Field(default=None, ge=1, le=200)


class GrepInput(BaseModel):
    pattern: str
    glob: str = "**/*"
    max_matches: int | None = Field(default=None, ge=1, le=200)
    literal: bool = False


class WriteFileInput(BaseModel):
    path: str
    content: str


class StrReplaceInput(BaseModel):
    path: str
    old: str
    new: str


class RunPythonInput(BaseModel):
    script: str
    script_name: str = "analysis.py"
    dependency_hints: list[str] | str | None = None


ToolHandler = Callable[..., Awaitable[str]]


def build_harness_run_context(ctx: SubagentContext) -> HarnessRunContext:
    """Translate current SubagentContext into the harness context contract."""

    invocation = ctx.invocation if isinstance(ctx.invocation, dict) else {}
    skill = _skill_snapshot(ctx.skill)
    return HarnessRunContext(
        workspace_id=ctx.workspace_id,
        user_id=str((ctx.inputs or {}).get("user_id") or ""),
        execution_id=ctx.execution_id,
        node_id=str(invocation.get("id") or (ctx.inputs or {}).get("node_id") or "react"),
        invocation_id=str(invocation.get("id") or "react"),
        workspace_type=str((ctx.inputs or {}).get("workspace_type") or ""),
        capability_id=str((ctx.inputs or {}).get("capability_id") or ""),
        capability_policy=dict(ctx.capability_policy or {}),
        agent_template=dict(invocation),
        skill=skill,
        context_bundle=dict(ctx.workspace_data or {}),
        requested_tools=tuple(ctx.tools or ()),
        publish_event=ctx.publish_event,
    )


def build_langchain_tools(ctx: SubagentContext, tool_names: list[str]) -> list[StructuredTool]:
    """Build LangChain-compatible tools from canonical harness tool names."""

    requested = [_canonical_tool_name(name) for name in tool_names if str(name).strip()]
    business_requested = [name for name in requested if name in BUSINESS_TOOL_NAMES]
    harness_requested = [name for name in requested if name not in BUSINESS_TOOL_NAMES]

    tools: list[StructuredTool] = []
    if business_requested:
        tools.extend(build_business_langchain_tools(ctx, business_requested))
    if not harness_requested:
        return tools

    harness_ctx = build_harness_run_context(ctx)
    policy = resolve_harness_policy(harness_ctx)
    forbidden = [name for name in harness_requested if name not in policy.allowed_tools]
    if forbidden:
        raise RuntimeError(f"React tools were requested but forbidden by harness policy: {', '.join(forbidden)}")
    registry = default_harness_tool_registry()
    specs = registry.resolve(harness_requested)
    for spec in specs:
        tool_definition = TOOL_DEFINITIONS.get(spec.name)
        if tool_definition is None:
            continue
        args_schema, handler = tool_definition
        tools.append(
            _structured_tool(
                spec.name,
                spec.description,
                args_schema,
                _recorded_coroutine(spec.name, harness_ctx, policy, handler),
                harness_ctx,
            )
        )
    return tools


def _structured_tool(
    canonical_name: str,
    description: str,
    args_schema: type[BaseModel],
    coroutine,
    ctx: HarnessRunContext,
):
    return StructuredTool.from_function(
        coroutine=coroutine,
        name=_langchain_tool_name(canonical_name),
        description=f"{description} Canonical tool: {canonical_name}.",
        args_schema=args_schema,
        handle_validation_error=_validation_error_handler(canonical_name, ctx),
    )


def _recorded_coroutine(
    canonical_name: str,
    ctx: HarnessRunContext,
    policy: HarnessPolicy,
    handler: ToolHandler,
) -> Callable[..., Awaitable[str]]:
    async def _coroutine(**kwargs) -> str:
        return await _invoke_recorded(
            canonical_name,
            ctx,
            policy,
            kwargs,
            lambda: handler(ctx, policy, **kwargs),
        )

    return _coroutine


def _langchain_tool_name(canonical_name: str) -> str:
    return canonical_name.replace(".", "_")


def _canonical_tool_name(name: str) -> str:
    text = str(name).strip()
    return CANONICAL_TOOL_ALIASES.get(text, text)


async def _invoke_recorded(
    canonical_name: str,
    ctx: HarnessRunContext,
    policy: HarnessPolicy,
    args: dict[str, Any],
    operation,
) -> str:
    records = ctx.context_bundle.get("_harness_tool_records")
    args_summary = summarize_tool_args(args)
    loop_guard = _loop_guard(ctx, policy)
    loop_decision = loop_guard.record(canonical_name, args_summary)
    if not loop_decision.allowed:
        error = loop_decision.stop_reason or "tool_loop_hard_stop"
        if isinstance(records, list):
            records.append(
                {
                    "name": canonical_name,
                    "status": "failed",
                    "args": args_summary,
                    "error": error,
                }
            )
        await publish_harness_event(
            ctx,
            "tool_call.failed",
            visibility="debug_only",
            sequence_kind="tool",
            payload={"name": canonical_name, "args": args_summary, "error": error},
        )
        raise RuntimeError(f"repeated tool call stopped by harness loop guard: {error}")
    if loop_decision.should_warn and loop_decision.count == loop_guard.warn_threshold:
        await publish_harness_event(
            ctx,
            "loop_warning",
            visibility="team_visible",
            sequence_kind="loop",
            payload={
                "name": canonical_name,
                "args": args_summary,
                "repeat_count": loop_decision.count,
                "warn_threshold": loop_guard.warn_threshold,
            },
        )
    await publish_harness_event(
        ctx,
        "tool_call.started",
        visibility="debug_only",
        sequence_kind="tool",
        payload={
            "name": canonical_name,
            "args": args_summary,
            "loop_warning": loop_decision.should_warn,
            "repeat_count": loop_decision.count,
        },
    )
    try:
        result = await operation()
    except GraphBubbleUp:
        raise
    except Exception as exc:
        result = _format_tool_error_result(canonical_name, args_summary, exc)
        metadata = _tool_result_metadata(result)
        if isinstance(records, list):
            records.append(
                {
                    "name": canonical_name,
                    "status": "failed",
                    "args": args_summary,
                    "result_preview": result[:500],
                    "error": metadata.get("recoverable_error") or _format_exception_error(exc),
                    "metadata": metadata,
                }
            )
        await publish_harness_event(
            ctx,
            "tool_call.failed",
            visibility="debug_only",
            sequence_kind="tool",
            payload={
                "name": canonical_name,
                "args": args_summary,
                "result_preview": result[:500],
                "error": metadata.get("recoverable_error") or _format_exception_error(exc),
                **metadata,
            },
        )
        return result
    if isinstance(records, list):
        records.append(_completed_tool_record(canonical_name, args_summary, result))
    metadata = _tool_result_metadata(result)
    if metadata.get("externalized") and metadata.get("output_refs"):
        await publish_harness_event(
            ctx,
            "output_externalized",
            visibility="debug_only",
            sequence_kind="budget",
            payload={
                "name": canonical_name,
                "args": args_summary,
                "result_preview": result[:500],
                **metadata,
            },
        )
    if metadata.get("file_changes"):
        await publish_harness_event(
            ctx,
            "file_change",
            visibility="debug_only",
            sequence_kind="file_change",
            payload={
                "name": canonical_name,
                "args": args_summary,
                "result_preview": result[:500],
                "file_changes": metadata["file_changes"],
            },
        )
    await publish_harness_event(
        ctx,
        "tool_call.completed",
        visibility="debug_only",
        sequence_kind="tool",
        payload={
            "name": canonical_name,
            "args": args_summary,
            "result_preview": result[:500],
            **metadata,
        },
    )
    return result


def _loop_guard(ctx: HarnessRunContext, policy: HarnessPolicy) -> HarnessLoopGuard:
    guard = ctx.context_bundle.get("_harness_loop_guard")
    if isinstance(guard, HarnessLoopGuard):
        return guard
    hard_limit = max(1, int(policy.max_tool_calls or 1))
    warn_threshold = min(3, hard_limit)
    guard = HarnessLoopGuard(warn_threshold=warn_threshold, hard_limit=hard_limit)
    ctx.context_bundle["_harness_loop_guard"] = guard
    return guard


async def _read_file(ctx: HarnessRunContext, policy: HarnessPolicy, **kwargs) -> str:
    return _format_tool_result(await _with_file_tools(ctx, policy, "read_file", kwargs))


async def _list_dir(ctx: HarnessRunContext, policy: HarnessPolicy, **kwargs) -> str:
    return _format_tool_result(await _with_file_tools(ctx, policy, "list_dir", kwargs))


async def _glob(ctx: HarnessRunContext, policy: HarnessPolicy, **kwargs) -> str:
    return _format_tool_result(await _with_file_tools(ctx, policy, "glob", kwargs))


async def _grep(ctx: HarnessRunContext, policy: HarnessPolicy, **kwargs) -> str:
    return _format_tool_result(await _with_file_tools(ctx, policy, "grep", kwargs))


async def _write_file(ctx: HarnessRunContext, policy: HarnessPolicy, **kwargs) -> str:
    return _format_tool_result(await _with_file_tools(ctx, policy, "write_file", kwargs))


async def _str_replace(ctx: HarnessRunContext, policy: HarnessPolicy, **kwargs) -> str:
    return _format_tool_result(await _with_file_tools(ctx, policy, "str_replace", kwargs))


async def _run_python(ctx: HarnessRunContext, policy: HarnessPolicy, **kwargs) -> str:
    result = await SandboxExecutionTools(
        context=ctx,
        policy=policy,
        scheduler=default_workspace_tool_scheduler,
    ).run_python(**kwargs)
    return _format_tool_result(result)


TOOL_DEFINITIONS: dict[str, tuple[type[BaseModel], ToolHandler]] = {
    "sandbox.read_file": (ReadFileInput, _read_file),
    "sandbox.list_dir": (ListDirInput, _list_dir),
    "sandbox.glob": (GlobInput, _glob),
    "sandbox.grep": (GrepInput, _grep),
    "sandbox.write_file": (WriteFileInput, _write_file),
    "sandbox.str_replace": (StrReplaceInput, _str_replace),
    "sandbox.run_python": (RunPythonInput, _run_python),
}


async def _with_file_tools(
    ctx: HarnessRunContext,
    policy: HarnessPolicy,
    method_name: str,
    kwargs: dict[str, Any],
) -> HarnessToolResult:
    async def _run() -> HarnessToolResult:
        injected = ctx.context_bundle.get("_harness_sandbox")
        if injected is not None:
            return await getattr(SandboxFileTools(sandbox=injected, context=ctx, policy=policy), method_name)(**kwargs)

        session = SandboxRuntimeSession()
        runtime_ctx = await session.build_context(
            workspace_id=ctx.workspace_id,
            sandbox_policy=dict(ctx.capability_policy.get("sandbox_policy") or {}),
        )
        sandbox = await runtime_ctx.provider.acquire(runtime_ctx.sandbox_key)
        try:
            return await getattr(SandboxFileTools(sandbox=sandbox, context=ctx, policy=policy), method_name)(**kwargs)
        finally:
            with suppress(Exception):
                await runtime_ctx.provider.release(sandbox)

    return await default_workspace_tool_scheduler.run(ctx.workspace_id, _run)


def _format_tool_result(result: HarnessToolResult) -> str:
    payload = {
        "preview": result.preview_text,
        "payload": result.structured_payload,
        "truncated": result.truncated,
        "externalized": result.externalized,
        "output_refs": list(result.output_refs),
    }
    if result.file_change is not None:
        payload["file_change"] = result.file_change
    if result.error:
        payload["error"] = result.error
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _format_tool_error_result(canonical_name: str, args_summary: dict[str, Any], exc: Exception) -> str:
    error = _format_exception_error(exc)
    payload = {
        "preview": f"Tool {canonical_name} failed: {error}",
        "payload": {
            "tool": canonical_name,
            "args": args_summary,
            "error_code": "tool_error",
            "exception_type": exc.__class__.__name__,
        },
        "truncated": False,
        "externalized": False,
        "output_refs": [],
        "error": error,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _validation_error_handler(canonical_name: str, ctx: HarnessRunContext) -> Callable[[Exception], str]:
    def _handle(exc: Exception) -> str:
        validation = _validation_error_summary(exc)
        result = _format_tool_validation_error_result(canonical_name, exc, validation)
        metadata = _tool_result_metadata(result)
        records = ctx.context_bundle.get("_harness_tool_records")
        if isinstance(records, list):
            records.append(
                {
                    "name": canonical_name,
                    "status": "failed",
                    "args": {"validation": validation},
                    "result_preview": result[:500],
                    "error": metadata.get("recoverable_error") or _format_exception_error(exc),
                    "metadata": metadata,
                }
            )
        _schedule_validation_error_event(
            canonical_name=canonical_name,
            ctx=ctx,
            result=result,
            metadata=metadata,
            validation=validation,
        )
        return result

    return _handle


def _format_tool_validation_error_result(
    canonical_name: str,
    exc: Exception,
    validation: dict[str, Any],
) -> str:
    error = f"{exc.__class__.__name__}: tool input validation failed"
    payload = {
        "preview": f"Tool {canonical_name} input validation failed.",
        "payload": {
            "tool": canonical_name,
            "error_code": "tool_input_validation",
            "exception_type": exc.__class__.__name__,
            "validation": validation,
            "recoverable": True,
        },
        "truncated": False,
        "externalized": False,
        "output_refs": [],
        "error": error,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _schedule_validation_error_event(
    *,
    canonical_name: str,
    ctx: HarnessRunContext,
    result: str,
    metadata: dict[str, Any],
    validation: dict[str, Any],
) -> None:
    if ctx.publish_event is None:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(
        publish_harness_event(
            ctx,
            "tool_call.failed",
            visibility="debug_only",
            sequence_kind="tool",
            payload={
                "name": canonical_name,
                "args": {"validation": validation},
                "result_preview": result[:500],
                "error": metadata.get("recoverable_error") or "tool input validation failed",
                **metadata,
                "validation": validation,
            },
        )
    )


def _validation_error_summary(exc: Exception) -> dict[str, Any]:
    raw_errors = []
    errors_method = getattr(exc, "errors", None)
    if callable(errors_method):
        with suppress(Exception):
            raw_errors = errors_method()
    if not isinstance(raw_errors, list):
        raw_errors = []

    errors: list[dict[str, Any]] = []
    for item in raw_errors[:5]:
        if not isinstance(item, dict):
            continue
        loc = item.get("loc")
        if isinstance(loc, tuple):
            safe_loc = [str(part) for part in loc]
        elif isinstance(loc, list):
            safe_loc = [str(part) for part in loc]
        elif loc is None:
            safe_loc = []
        else:
            safe_loc = [str(loc)]
        errors.append(
            {
                "loc": safe_loc,
                "msg": str(item.get("msg") or "Invalid tool input"),
                "type": str(item.get("type") or "validation_error"),
            }
        )
    return {
        "error_count": len(raw_errors) if raw_errors else 1,
        "errors": errors,
    }


def _format_exception_error(exc: Exception) -> str:
    detail = str(exc).strip() or exc.__class__.__name__
    if len(detail) > 500:
        detail = f"{detail[:497]}..."
    return f"{exc.__class__.__name__}: {detail}"


def _completed_tool_record(canonical_name: str, args_summary: dict[str, Any], result: str) -> dict[str, Any]:
    record = {
        "name": canonical_name,
        "status": "completed",
        "args": args_summary,
        "result_preview": result[:500],
    }
    record.update(_tool_result_metadata(result))
    return record


def _tool_result_metadata(result: str) -> dict[str, Any]:
    try:
        payload = json.loads(result)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}

    metadata: dict[str, Any] = {}
    output_refs = payload.get("output_refs")
    if isinstance(output_refs, list):
        refs = [str(ref) for ref in output_refs if str(ref).strip()]
        if refs:
            metadata["output_refs"] = refs

    for key in ("truncated", "externalized"):
        value = payload.get(key)
        if isinstance(value, bool) and value:
            metadata[key] = value
    error = payload.get("error")
    if isinstance(error, str) and error.strip():
        metadata["recoverable_error"] = error.strip()
        structured_payload = payload.get("payload")
        if isinstance(structured_payload, dict):
            error_code = structured_payload.get("error_code")
            if isinstance(error_code, str) and error_code.strip():
                metadata["error_code"] = error_code.strip()
    generated_artifacts = _generated_artifact_metadata(payload)
    if generated_artifacts:
        metadata["generated_artifacts"] = generated_artifacts
    command_audit = _command_audit_metadata(payload)
    if command_audit:
        metadata.update(command_audit)
    run_python_metadata = _run_python_metadata(payload)
    if run_python_metadata:
        metadata.update(run_python_metadata)
    file_changes = _file_change_metadata(payload)
    if file_changes:
        metadata["file_changes"] = file_changes
    return metadata


def _command_audit_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    structured_payload = payload.get("payload")
    if not isinstance(structured_payload, dict):
        return {}
    metadata: dict[str, Any] = {}
    command_audit = structured_payload.get("command_audit")
    if isinstance(command_audit, dict):
        metadata["command_audit"] = dict(command_audit)
    install_command_audits = structured_payload.get("install_command_audits")
    if isinstance(install_command_audits, list):
        audits = [dict(item) for item in install_command_audits if isinstance(item, dict)]
        if audits:
            metadata["install_command_audits"] = audits
    return metadata


def _run_python_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    structured_payload = payload.get("payload")
    if not isinstance(structured_payload, dict):
        return {}
    metadata: dict[str, Any] = {}
    execution_manifest = structured_payload.get("execution_manifest")
    if isinstance(execution_manifest, dict):
        metadata["execution_manifest"] = dict(execution_manifest)
    reproducibility_manifest = structured_payload.get("reproducibility_manifest")
    if isinstance(reproducibility_manifest, dict):
        metadata["reproducibility_manifest"] = dict(reproducibility_manifest)
    failure_classification = structured_payload.get("failure_classification")
    if isinstance(failure_classification, dict):
        metadata["failure_classification"] = dict(failure_classification)
    return metadata


def _file_change_metadata(payload: dict[str, Any]) -> list[dict[str, Any]]:
    file_change = payload.get("file_change")
    if not isinstance(file_change, dict):
        return []
    path = str(file_change.get("path") or "").strip()
    if not path:
        return []
    return [dict(file_change)]


def _generated_artifact_metadata(payload: dict[str, Any]) -> list[dict[str, Any]]:
    structured_payload = payload.get("payload")
    if not isinstance(structured_payload, dict):
        return []
    artifacts = structured_payload.get("generated_artifacts")
    if not isinstance(artifacts, list):
        return []
    sandbox_job_id = str(structured_payload.get("sandbox_job_id") or "").strip()
    sandbox_environment_id = str(structured_payload.get("sandbox_environment_id") or "").strip()
    enriched: list[dict[str, Any]] = []
    for artifact in artifacts[:50]:
        if not isinstance(artifact, dict) or not str(artifact.get("path") or "").strip():
            continue
        candidate = dict(artifact)
        if sandbox_job_id:
            candidate.setdefault("sandbox_job_id", sandbox_job_id)
        if sandbox_environment_id:
            candidate.setdefault("sandbox_environment_id", sandbox_environment_id)
        enriched.append(candidate)
    return enriched


def _skill_snapshot(skill: Any | None) -> dict[str, Any]:
    if skill is None:
        return {}
    if isinstance(skill, dict):
        return dict(skill)
    snapshot: dict[str, Any] = {}
    for attr in ("id", "name", "display_name", "allowed_tools"):
        value = getattr(skill, attr, None)
        if value is not None:
            snapshot[attr] = value
    config = getattr(skill, "config", None)
    if isinstance(config, dict):
        snapshot["config"] = dict(config)
    skill_json = getattr(skill, "skill_json", None)
    if isinstance(skill_json, dict):
        snapshot["skill_json"] = dict(skill_json)
    return snapshot
