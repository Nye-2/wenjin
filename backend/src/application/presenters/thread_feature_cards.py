"""Structured response builders for thread feature orchestration cards."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypedDict

from src.application.presenters.thread_feature_presenters import (
    feature_follow_up_prompt as _feature_follow_up_prompt,
)
from src.application.presenters.thread_feature_presenters import (
    feature_title as _feature_title,
)
from src.application.presenters.thread_feature_presenters import (
    summarize_feature_result as _feature_result_summary,
)
from src.application.results import GeneratedThreadReply
from src.task.workspace_feature_params import coerce_workspace_feature_params

type _NextStepAction = Literal[
    "trigger_feature",
    "continue_thread",
    "open_feature",
    "rerun_from_artifact",
]


class _NextStepItem(TypedDict):
    label: str
    feature_id: str
    action: _NextStepAction


def _sanitize_orchestration_params(params: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        str(key): value
        for key, value in dict(params or {}).items()
        if not str(key).startswith("__")
    }


def _build_task_block(
    *,
    feature_id: str,
    task_id: str,
    execution_session_id: str | None = None,
    message: str,
    warning: str | None = None,
) -> dict[str, Any]:
    return {
        "type": "task",
        "title": _feature_title(feature_id),
        "data": {
            "feature_id": feature_id,
            "task_id": task_id,
            "execution_session_id": execution_session_id,
            "status": "pending",
            "message": message,
            "warning": warning,
        },
    }


def _build_warning_block(
    *,
    title: str,
    detail: str,
    code: str | None = None,
    feature_id: str | None = None,
) -> dict[str, Any]:
    return {
        "type": "warning",
        "title": title,
        "data": {
            "code": code,
            "feature_id": feature_id,
            "detail": detail,
        },
    }


def _build_next_step_item(
    *,
    label: str,
    feature_id: str,
    action: _NextStepAction,
) -> _NextStepItem:
    return {
        "label": label,
        "feature_id": feature_id,
        "action": action,
    }


def _build_next_steps_block(items: list[_NextStepItem]) -> dict[str, Any]:
    return {
        "type": "next_steps",
        "title": "建议下一步",
        "data": {"items": items},
    }


def _build_result_block(
    *,
    title: str,
    summary: str,
    feature_id: str | None = None,
) -> dict[str, Any]:
    return {
        "type": "result",
        "title": title,
        "data": {
            "feature_id": feature_id,
            "summary": summary,
        },
    }


def _build_continue_thread_step(
    feature_id: str,
    *,
    label: str,
) -> _NextStepItem:
    return _build_next_step_item(
        label=label,
        feature_id=feature_id,
        action="continue_thread",
    )


def _build_open_feature_step(
    feature_id: str,
    *,
    label: str,
) -> _NextStepItem:
    return _build_next_step_item(
        label=label,
        feature_id=feature_id,
        action="open_feature",
    )


def _build_rerun_from_artifact_step(
    feature_id: str,
    *,
    label: str,
) -> _NextStepItem:
    return _build_next_step_item(
        label=label,
        feature_id=feature_id,
        action="rerun_from_artifact",
    )


def build_missing_response(
    *,
    feature_id: str,
    message: str,
    missing_feature_id: str | None = None,
    execution_session_id: str | None = None,
    params: Mapping[str, Any] | None = None,
    missing_fields: list[str] | None = None,
) -> GeneratedThreadReply:
    resolved_params = _sanitize_orchestration_params(params)
    normalized_missing_fields = [str(field) for field in (missing_fields or []) if str(field).strip()]
    next_steps: list[_NextStepItem] = []
    if missing_feature_id:
        next_steps.append(
            _build_next_step_item(
                label=f"先执行 {_feature_title(missing_feature_id)}",
                feature_id=missing_feature_id,
                action="trigger_feature",
            )
        )
    next_steps.append(
        _build_continue_thread_step(
            feature_id,
            label="直接回复补充信息",
        )
    )
    return GeneratedThreadReply(
        content=message,
        blocks=[
            _build_warning_block(
                title=f"{_feature_title(feature_id)} 还缺少必要信息",
                detail=message,
                feature_id=feature_id,
                code="missing_params",
            ),
            _build_next_steps_block(next_steps),
        ],
        metadata={
            "orchestration": {
                "mode": "feature_execution",
                "feature_id": feature_id,
                "status": "awaiting_user_input",
                "execution_session_id": execution_session_id,
                "params": resolved_params,
                "missing_fields": normalized_missing_fields,
            }
        },
    )


def build_execution_success_response(
    *,
    feature_id: str,
    task_id: str,
    execution_session_id: str | None,
    message: str,
    params: Mapping[str, Any] | None,
) -> GeneratedThreadReply:
    resolved_params = _sanitize_orchestration_params(params)
    return GeneratedThreadReply(
        content=f"已为你启动「{_feature_title(feature_id)}」任务，接下来会在当前 workspace 中继续推进。",
        blocks=[
            _build_task_block(
                feature_id=feature_id,
                task_id=task_id,
                execution_session_id=execution_session_id,
                message=message,
            ),
            _build_next_steps_block(
                [
                    _build_continue_thread_step(
                        feature_id,
                        label="继续在线程中补充要求",
                    ),
                    _build_open_feature_step(
                        feature_id,
                        label="打开对应模块查看运行态",
                    ),
                    _build_rerun_from_artifact_step(
                        feature_id,
                        label="基于最近 artifact 再次执行",
                    ),
                ]
            ),
        ],
        metadata={
            "orchestration": {
                "mode": "feature_execution",
                "feature_id": feature_id,
                "status": "pending",
                "task_id": task_id,
                "execution_session_id": execution_session_id,
                "params": resolved_params,
            }
        },
    )


def build_execution_warning_response(
    *,
    feature_id: str,
    execution_session_id: str | None,
    execution: Any,
    params: Mapping[str, Any] | None,
) -> GeneratedThreadReply:
    resolved_params = _sanitize_orchestration_params(params)
    warning_code = getattr(execution, "code", None) or getattr(execution, "warning", None)
    detail = getattr(execution, "context", None) or getattr(execution, "detail", None) or {}
    warning_text = str(getattr(execution, "message", "") or "当前无法直接执行该模块。")
    if str(warning_code or "").strip().lower() == "missing_params":
        missing_fields = (
            [str(item) for item in detail.get("missing_fields", []) if str(item).strip()]
            if isinstance(detail, Mapping)
            else []
        )
        return build_missing_response(
            feature_id=feature_id,
            message=warning_text,
            execution_session_id=execution_session_id,
            params=resolved_params,
            missing_fields=missing_fields,
        )

    next_steps = [
        _build_open_feature_step(
            "literature_management" if warning_code == "literature_insufficient" else feature_id,
            label="查看推荐补救步骤",
        ),
        _build_continue_thread_step(
            feature_id,
            label="继续补充约束后再执行",
        ),
    ]
    if warning_code == "literature_insufficient":
        current = detail.get("current", 0)
        recommended = detail.get("recommended", 0)
        warning_text = (
            f"当前文献储备不足（{current}/{recommended}），"
            "建议先补齐文献再继续写作。"
        )

    return GeneratedThreadReply(
        content=warning_text,
        blocks=[
            _build_warning_block(
                title=f"{_feature_title(feature_id)} 暂未启动",
                detail=warning_text,
                feature_id=feature_id,
                code=str(warning_code) if warning_code else None,
            ),
            _build_next_steps_block(next_steps),
        ],
        metadata={
            "orchestration": {
                "mode": "feature_execution",
                "feature_id": feature_id,
                "status": "warning",
                "execution_session_id": execution_session_id,
                "warning": warning_code,
                "detail": detail,
                "params": resolved_params,
            }
        },
    )


def build_thread_result_card(
    *,
    title: str,
    summary: str,
    feature_id: str | None = None,
) -> GeneratedThreadReply:
    """Helper for tooling surfaces that need a simple structured reply."""
    return GeneratedThreadReply(
        content=summary,
        blocks=[_build_result_block(title=title, summary=summary, feature_id=feature_id)],
        metadata={"orchestration": {"mode": "info", "feature_id": feature_id}},
    )


def build_feature_task_completion_card(
    *,
    feature_id: str,
    task_id: str,
    execution_session_id: str | None = None,
    payload: Mapping[str, Any] | None,
    result: Mapping[str, Any] | None,
) -> GeneratedThreadReply:
    """Build a structured assistant card for async feature completion."""
    data = (
        result.get("data")
        if isinstance(result, Mapping) and isinstance(result.get("data"), Mapping)
        else {}
    )
    artifacts = (
        result.get("artifacts")
        if isinstance(result, Mapping) and isinstance(result.get("artifacts"), list)
        else []
    )
    summary = _feature_result_summary(feature_id, data, artifacts)
    params = _sanitize_orchestration_params(coerce_workspace_feature_params(payload))
    follow_up_prompt = _feature_follow_up_prompt(feature_id)
    blocks = [
        _build_result_block(
            title=f"{_feature_title(feature_id)} 已完成",
            summary=summary,
            feature_id=feature_id,
        ),
    ]
    if follow_up_prompt:
        blocks.append(
            _build_result_block(
                title="建议下一轮继续",
                summary=follow_up_prompt,
                feature_id=feature_id,
            )
        )
    blocks.append(
        _build_next_steps_block(
            [
                _build_open_feature_step(
                    feature_id,
                    label="直接打开模块",
                ),
                _build_continue_thread_step(
                    feature_id,
                    label="继续追问结果",
                ),
                _build_rerun_from_artifact_step(
                    feature_id,
                    label="基于 artifact 再执行",
                ),
            ]
        )
    )

    return GeneratedThreadReply(
        content=summary,
        blocks=blocks,
        metadata={
            "orchestration": {
                "mode": "feature_execution",
                "feature_id": feature_id,
                "status": "completed",
                "task_id": task_id,
                "execution_session_id": execution_session_id,
                "params": params,
                "artifacts": artifacts,
                "suggested_follow_up": follow_up_prompt,
            }
        },
    )


def build_feature_task_failure_card(
    *,
    feature_id: str,
    task_id: str,
    execution_session_id: str | None = None,
    payload: Mapping[str, Any] | None,
    error: str | None,
) -> GeneratedThreadReply:
    """Build a structured assistant card for async feature failure."""
    detail = str(error or "任务执行失败，请稍后重试。").strip()
    params = _sanitize_orchestration_params(coerce_workspace_feature_params(payload))
    summary = f"{_feature_title(feature_id)} 执行失败。{detail}"

    return GeneratedThreadReply(
        content=summary,
        blocks=[
            _build_warning_block(
                title=f"{_feature_title(feature_id)} 执行失败",
                detail=detail,
                code="task_failed",
                feature_id=feature_id,
            ),
            _build_next_steps_block(
                [
                    _build_open_feature_step(
                        feature_id,
                        label="打开模块排查",
                    ),
                    _build_continue_thread_step(
                        feature_id,
                        label="继续追问原因",
                    ),
                    _build_rerun_from_artifact_step(
                        feature_id,
                        label="重新基于 artifact 执行",
                    ),
                ]
            ),
        ],
        metadata={
            "orchestration": {
                "mode": "feature_execution",
                "feature_id": feature_id,
                "status": "failed",
                "task_id": task_id,
                "execution_session_id": execution_session_id,
                "params": params,
                "error": detail,
            }
        },
    )
