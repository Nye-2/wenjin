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
    "open_prism",
    "preview_prism_changes",
    "open_artifact",
    "rerun_feature",
    "resume_execution",
    "import_references",
]


class _NextStepItem(TypedDict):
    label: str
    feature_id: str
    action: _NextStepAction
    params: dict[str, Any]


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
    params: Mapping[str, Any] | None = None,
) -> _NextStepItem:
    return {
        "label": label,
        "feature_id": feature_id,
        "action": action,
        "params": _sanitize_orchestration_params(params),
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


def _build_task_result_block(
    *,
    feature_id: str,
    execution_session_id: str | None,
    summary: str,
    destinations: list[dict[str, Any]] | None = None,
    prism: dict[str, Any] | None = None,
    trust: dict[str, Any] | None = None,
    reference_import: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": "task_result",
        "title": f"{_feature_title(feature_id)} 已完成",
        "data": {
            "feature_id": feature_id,
            "execution_session_id": execution_session_id,
            "summary": summary,
            "destinations": destinations or [],
            "prism": prism,
            "trust": trust,
            "reference_import": reference_import,
        },
    }


def _build_prism_status_block(
    *,
    project_id: str,
    project_name: str | None = None,
    main_file: str | None = None,
    pending_file_changes: int = 0,
    applied_file_changes: int = 0,
    compile_status: str | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    return {
        "type": "prism_status",
        "title": "主稿状态",
        "data": {
            "project_id": project_id,
            "project_name": project_name or "Untitled Paper",
            "main_file": main_file or "main.tex",
            "pending_file_changes": pending_file_changes,
            "applied_file_changes": applied_file_changes,
            "compile_status": compile_status or "not_compiled",
            "url": url,
        },
    }


def _build_task_failure_block(
    *,
    feature_id: str,
    execution_session_id: str | None,
    task_id: str | None,
    failed_phase: str | None,
    error_summary: str,
    completed: list[str] | None = None,
    not_applied: bool = True,
    prism_affected: bool = False,
    recovery_actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "type": "task_failure",
        "title": f"{_feature_title(feature_id)} 执行失败",
        "data": {
            "feature_id": feature_id,
            "execution_session_id": execution_session_id,
            "task_id": task_id,
            "failed_phase": failed_phase,
            "error_summary": error_summary,
            "completed": completed or [],
            "not_applied": not_applied,
            "prism_affected": prism_affected,
            "recovery_actions": recovery_actions or [],
        },
    }


def _build_missing_input_block(
    *,
    feature_id: str,
    execution_session_id: str | None,
    message: str,
    missing_fields: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "type": "missing_input",
        "title": f"{_feature_title(feature_id)} 还缺少必要信息",
        "data": {
            "feature_id": feature_id,
            "execution_session_id": execution_session_id,
            "message": message,
            "missing_fields": missing_fields or [],
            "resume_policy": "reply_in_chat",
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
    missing_fields_structured: list[dict[str, Any]] = [
        {"field": field, "label": field}
        for field in normalized_missing_fields
    ]

    return GeneratedThreadReply(
        content=message,
        blocks=[
            _build_missing_input_block(
                feature_id=feature_id,
                execution_session_id=execution_session_id,
                message=message,
                missing_fields=missing_fields_structured,
            ),
            # Keep warning block for backward compatibility
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


def build_feature_proposal_response(
    *,
    feature_id: str,
    feature_name: str,
    skill_id: str | None,
    params: Mapping[str, Any] | None,
    reason: str,
    confidence: float,
) -> GeneratedThreadReply:
    """Build the canonical chat-side proposal for a feature launch."""
    resolved_params = _sanitize_orchestration_params(params)
    route_params = {
        **resolved_params,
        **({"skill": skill_id} if skill_id else {}),
    }
    title = f"建议启动「{feature_name or _feature_title(feature_id)}」"
    content = (
        f"{title}。我会先复用当前工作区、线程上下文和已有产物；"
        "如果执行前仍缺关键信息，会在当前执行会话里继续追问。"
    )
    return GeneratedThreadReply(
        content=content,
        blocks=[
            {
                "type": "feature_proposal",
                "title": title,
                "data": {
                    "feature_id": feature_id,
                    "feature_name": feature_name,
                    "skill_id": skill_id,
                    "params": resolved_params,
                    "reason": reason,
                    "confidence": confidence,
                    "start_policy": "explicit_user_action",
                },
            },
            _build_next_steps_block(
                [
                    _build_next_step_item(
                        label=f"启动{feature_name or _feature_title(feature_id)}",
                        feature_id=feature_id,
                        action="trigger_feature",
                        params=route_params,
                    ),
                    _build_continue_thread_step(
                        feature_id,
                        label="先继续补充要求",
                    ),
                ]
            ),
        ],
        metadata={
            "orchestration": {
                "mode": "feature_proposal",
                "feature_id": feature_id,
                "skill_id": skill_id,
                "status": "proposed",
                "params": resolved_params,
                "confidence": confidence,
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


def _extract_prism_from_result(
    data: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Extract prism projection fields from feature result data."""
    latex_project_id = data.get("latex_project_id") if isinstance(data, Mapping) else None
    if not latex_project_id or not str(latex_project_id).strip():
        return None
    return {
        "project_id": str(latex_project_id).strip(),
        "project_name": str(data.get("project_name") or "Untitled Paper").strip(),
        "main_file": str(data.get("main_file") or "main.tex").strip(),
        "url": str(data.get("prism_url") or f"/latex/{latex_project_id}").strip(),
        "pending_file_changes": int(data.get("pending_file_changes", 0)) if isinstance(data.get("pending_file_changes"), int | float) else 0,
        "applied_file_changes": int(data.get("applied_file_changes", 0)) if isinstance(data.get("applied_file_changes"), int | float) else 0,
        "compile_status": str(data.get("compile_status") or "not_compiled").strip(),
    }


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_literature_evidence_from_result(
    data: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Extract Semantic Scholar evidence fields for result trust display."""
    if str(data.get("source") or "").strip() != "semantic_scholar":
        return None

    verified_papers = data.get("verified_papers")
    if not isinstance(verified_papers, list):
        verified_papers = []
    unverified_leads = data.get("unverified_leads")
    if not isinstance(unverified_leads, list):
        unverified_leads = []
    retrieval = data.get("retrieval")
    retrieval_info = retrieval if isinstance(retrieval, Mapping) else {}

    preview: list[dict[str, Any]] = []
    for raw in verified_papers[:5]:
        if not isinstance(raw, Mapping):
            continue
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        preview.append(
            {
                "title": title,
                "year": _safe_int(raw.get("year")),
                "venue": str(raw.get("venue") or "").strip() or None,
                "doi": str(raw.get("doi") or "").strip() or None,
                "url": str(raw.get("url") or "").strip() or None,
                "external_id": str(raw.get("external_id") or "").strip() or None,
                "citations_count": _safe_int(
                    raw.get("citations_count")
                    or raw.get("citation_count")
                    or raw.get("citations")
                ),
            }
        )

    verified_at = str(retrieval_info.get("verified_at") or "").strip()
    if not verified_at:
        for raw in verified_papers:
            if isinstance(raw, Mapping):
                verified_at = str(raw.get("verified_at") or "").strip()
                if verified_at:
                    break

    return {
        "evidence_source": "Semantic Scholar",
        "evidence_source_id": "semantic_scholar",
        "verified_papers_count": len([item for item in verified_papers if isinstance(item, Mapping)]),
        "unverified_leads_count": len([item for item in unverified_leads if isinstance(item, Mapping)]),
        "retrieval_status": str(retrieval_info.get("status") or "unknown").strip(),
        "retrieval_query": str(retrieval_info.get("query") or data.get("query") or "").strip(),
        "verified_at": verified_at or None,
        "verified_papers_preview": preview,
    }


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

    # Build destinations from artifacts and prism
    destinations: list[dict[str, Any]] = []
    for artifact in artifacts:
        if isinstance(artifact, Mapping):
            title = str(artifact.get("title") or "").strip()
            artifact_id = str(artifact.get("id") or "").strip()
            if title:
                destinations.append({
                    "kind": "artifact",
                    "label": title,
                    "id": artifact_id,
                })

    # Extract prism info
    prism_info = _extract_prism_from_result(data)
    if prism_info:
        destinations.append({
            "kind": "prism",
            "label": "WenjinPrism 主稿",
            "project_id": prism_info["project_id"],
        })
    if feature_id == "literature_search" and isinstance(data.get("reference_import"), Mapping):
        imported_count = int(data["reference_import"].get("imported") or 0)
        if imported_count > 0:
            destinations.append({
                "kind": "references",
                "label": f"参考库已同步 {imported_count} 条 Semantic Scholar 文献",
            })

    trust: dict[str, Any] = {
        "used_context_count": int(data.get("used_context_count", 0)) if isinstance(data.get("used_context_count"), int | float) else 0,
        "unverified_items": int(data.get("unverified_items", 0)) if isinstance(data.get("unverified_items"), int | float) else 0,
        "citation_status": str(data.get("citation_status") or "needs_review").strip(),
        "will_not_overwrite_prism": True,
    }
    literature_evidence = _extract_literature_evidence_from_result(data)
    if literature_evidence:
        trust.update(literature_evidence)

    reference_import: dict[str, Any] | None = None

    blocks: list[dict[str, Any]] = [
        _build_task_result_block(
            feature_id=feature_id,
            execution_session_id=execution_session_id,
            summary=summary,
            destinations=destinations,
            prism=prism_info,
            trust=trust,
            reference_import=reference_import,
        ),
    ]

    if prism_info:
        blocks.append(
            _build_prism_status_block(
                project_id=prism_info["project_id"],
                project_name=prism_info.get("project_name"),
                main_file=prism_info.get("main_file"),
                pending_file_changes=prism_info.get("pending_file_changes", 0),
                applied_file_changes=prism_info.get("applied_file_changes", 0),
                compile_status=prism_info.get("compile_status"),
                url=prism_info.get("url"),
            )
        )

    if follow_up_prompt:
        blocks.append(
            _build_result_block(
                title="建议下一轮继续",
                summary=follow_up_prompt,
                feature_id=feature_id,
            )
        )

    # Build next steps with destination-specific actions when available.
    next_step_items: list[_NextStepItem] = [
        _build_continue_thread_step(
            feature_id,
            label="继续追问结果",
        ),
        _build_rerun_from_artifact_step(
            feature_id,
            label="基于 artifact 再执行",
        ),
    ]
    if reference_import:
        next_step_items.insert(
            0,
            _build_next_step_item(
                label="同步到参考库",
                feature_id=feature_id,
                action="import_references",
                params=reference_import,
            ),
        )

    if prism_info:
        pending_file_changes = int(prism_info.get("pending_file_changes") or 0)
        if pending_file_changes > 0:
            next_step_items.insert(
                0,
                _build_next_step_item(
                    label=f"预览待确认修改（{pending_file_changes}）",
                    feature_id=feature_id,
                    action="preview_prism_changes",
                    params={
                        "project_id": prism_info["project_id"],
                        "url": prism_info.get("url"),
                    },
                ),
            )
        next_step_items.insert(
            1 if pending_file_changes > 0 else 0,
            _build_next_step_item(
                label="打开 WenjinPrism",
                feature_id=feature_id,
                action="open_prism",
                params={
                    "project_id": prism_info["project_id"],
                    "url": prism_info.get("url"),
                },
            ),
        )
    else:
        next_step_items.insert(
            1 if reference_import else 0,
            _build_open_feature_step(
                feature_id,
                label="直接打开模块",
            ),
        )

    blocks.append(_build_next_steps_block(next_step_items))

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
    failed_phase: str | None = None,
    completed: list[str] | None = None,
    prism_affected: bool = False,
) -> GeneratedThreadReply:
    """Build a structured assistant card for async feature failure."""
    detail = str(error or "任务执行失败，请稍后重试。").strip()
    params = _sanitize_orchestration_params(coerce_workspace_feature_params(payload))
    summary = f"{_feature_title(feature_id)} 执行失败。{detail}"

    recovery_actions: list[dict[str, Any]] = [
        {"label": "基于已完成结果继续", "action": "resume_execution"},
        {"label": "继续补充后重试", "action": "continue_thread"},
    ]

    blocks: list[dict[str, Any]] = [
        _build_task_failure_block(
            feature_id=feature_id,
            execution_session_id=execution_session_id,
            task_id=task_id,
            failed_phase=failed_phase,
            error_summary=detail,
            completed=completed,
            not_applied=True,
            prism_affected=prism_affected,
            recovery_actions=recovery_actions,
        ),
        # Keep warning block for backward compatibility with older frontends
        _build_warning_block(
            title=f"{_feature_title(feature_id)} 执行失败",
            detail=detail,
            code="task_failed",
            feature_id=feature_id,
        ),
        _build_next_steps_block(
            [
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
    ]

    return GeneratedThreadReply(
        content=summary,
        blocks=blocks,
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
