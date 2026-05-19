"""Build AgentBlock-conformant result_cards for async feature task completion / failure.

These are emitted by the Celery write-back path (src/task/tasks/base.py) — not by
lead_agent — but they conform to the same `AgentMessage` schema the frontend expects.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode

from src.application.results import GeneratedThreadReply
from src.services.workspace_activity_contracts import build_task_result_next_actions

_FEATURE_DISPLAY = {
    "paper_analysis": "论文分析",
    "literature_search": "文献检索",
    "literature_management": "文献管理",
    "literature_review": "文献综述",
    "framework_outline": "框架大纲",
    "writing": "章节写作",
    "thesis_writing": "学位论文写作",
    "peer_review": "同行评审",
    "journal_recommend": "期刊推荐",
    "figure_generation": "配图生成",
    "deep_research": "深度调研",
    "opening_research": "开题调研",
    "background_research": "背景调研",
    "experiment_design": "实验设计",
    "proposal_outline": "申报书大纲",
    "patent_outline": "专利大纲",
    "prior_art_search": "现有技术检索",
    "copyright_materials": "软著材料",
    "technical_description": "技术描述",
}

_FINDING_BULLETS = "①②③④⑤"


def _feature_title(feature_id: str) -> str:
    return _FEATURE_DISPLAY.get(feature_id, feature_id)


def _truncate(text: str, limit: int = 280) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _findings_from_data(data: Mapping[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    raw = data.get("findings") if isinstance(data, Mapping) else None
    if isinstance(raw, list):
        for i, entry in enumerate(raw[:5], start=1):
            text = ""
            if isinstance(entry, str):
                text = entry
            elif isinstance(entry, Mapping):
                text = str(entry.get("text") or entry.get("summary") or "")
            text = text.strip()
            if not text:
                continue
            items.append({"id": _FINDING_BULLETS[i - 1], "text": text})
    return items


def _links_from_artifacts(artifacts: list[Mapping[str, Any]]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for art in artifacts[:6]:
        if not isinstance(art, Mapping):
            continue
        title = str(art.get("title") or "").strip()
        href = str(art.get("url") or art.get("href") or "").strip()
        if not href or not title:
            continue
        links.append(
            {
                "icon": "file",
                "label": title,
                "href": href,
            }
        )
    return links


def _links_from_next_actions(
    *,
    feature_id: str,
    payload: Mapping[str, Any] | None,
    result: Mapping[str, Any] | None,
) -> list[dict[str, str]]:
    if not isinstance(payload, Mapping):
        payload_dict: dict[str, Any] = {}
    else:
        payload_dict = dict(payload)

    payload_dict.setdefault("feature_id", feature_id)
    actions = build_task_result_next_actions(
        payload=payload_dict,
        result=dict(result) if isinstance(result, Mapping) else None,
    )
    links: list[dict[str, str]] = []
    for action in actions:
        href = _action_href(action, payload_dict)
        label = str(action.get("label") or "").strip()
        if not href or not label:
            continue
        links.append(
            {
                "icon": "file" if action.get("action") == "open_artifact" else "sparkles",
                "label": label,
                "href": href,
            }
        )
    return links


def _action_href(action: Mapping[str, Any], payload: Mapping[str, Any]) -> str | None:
    action_name = str(action.get("action") or action.get("kind") or "").strip()
    workspace_id = str(payload.get("workspace_id") or "").strip()

    if workspace_id and action_name in {"open_prism", "preview_prism_changes"}:
        if action_name == "preview_prism_changes":
            return f"/workspaces/{workspace_id}/prism?focus=file_changes"
        return f"/workspaces/{workspace_id}/prism"

    explicit_href = str(action.get("url") or action.get("href") or "").strip()
    if explicit_href:
        return explicit_href

    if not workspace_id:
        return None

    if action_name == "rerun_from_artifact":
        feature_id = str(action.get("feature_id") or payload.get("feature_id") or "").strip()
        if not feature_id:
            return None
        query: list[tuple[str, str]] = [("feature", feature_id)]
        skill_id = str(action.get("skill_id") or "").strip()
        if skill_id:
            query.append(("skill", skill_id))
        for key, value in action.items():
            if key in {"action", "kind", "label", "feature_id", "skill_id"}:
                continue
            query.extend(_query_pairs(key, value))
        suffix = urlencode(query, doseq=True)
        return f"/workspaces/{workspace_id}?{suffix}" if suffix else f"/workspaces/{workspace_id}"

    if action_name == "open_artifact":
        room = _artifact_room(str(action.get("artifact_kind") or "").strip())
        title = str(action.get("title") or "").strip()
        artifact_id = str(action.get("artifact_id") or "").strip()
        if not room:
            return None
        query: list[tuple[str, str]] = [("room", room)]
        if artifact_id:
            query.append(("artifact_id", artifact_id))
        if title:
            query.append(("query", title))
        return f"/workspaces/{workspace_id}?{urlencode(query, doseq=True)}"

    return None


def _artifact_room(artifact_kind: str) -> str | None:
    if artifact_kind == "document":
        return "documents"
    if artifact_kind == "library_item":
        return "library"
    return None


def _query_pairs(key: str, value: Any) -> list[tuple[str, str]]:
    if value is None:
        return []
    if isinstance(value, list):
        pairs: list[tuple[str, str]] = []
        for item in value:
            if item is None:
                continue
            normalized = str(item).strip()
            if normalized:
                pairs.append((key, normalized))
        return pairs
    text = str(value).strip()
    return [(key, text)] if text else []


def build_completion_result_card(
    *,
    feature_id: str,
    task_id: str,
    run_id: str,
    execution_id: str | None,
    payload: Mapping[str, Any] | None,
    result: Mapping[str, Any] | None,
    duration_ms: int,
    subagents_count: int,
    tokens_total: int,
) -> GeneratedThreadReply:
    """Build a result_card for a successful feature task."""
    raw_data = result.get("data") if isinstance(result, Mapping) else None
    data: Mapping[str, Any] = raw_data if isinstance(raw_data, Mapping) else {}
    artifacts_raw = result.get("artifacts") if isinstance(result, Mapping) else None
    artifacts = [a for a in (artifacts_raw if isinstance(artifacts_raw, list) else []) if isinstance(a, Mapping)]

    raw_summary = str(data.get("summary") or "已完成。")
    summary = _truncate(raw_summary, 280)
    full_summary = raw_summary if len(raw_summary) > 280 else None
    title = f"{_feature_title(feature_id)} 已完成"
    findings = _findings_from_data(data)
    links = _links_from_next_actions(
        feature_id=feature_id,
        payload=payload,
        result=result,
    )
    if not links:
        links = _links_from_artifacts(artifacts)

    block = {
        "kind": "result_card",
        "run_id": run_id,
        "title": title,
        "tldr": summary,
        "full_summary": full_summary,
        "findings": findings,
        "recommend": None,
        "links": links,
        "feedback": {
            "question": "对结果是否满意？",
            "pills": [
                {"kind": "primary", "label": "深入展开 ①", "intent": "expand_finding_1"},
                {"kind": "normal", "label": "重新执行", "intent": "retry_run"},
                {"kind": "warn", "label": "结果不对", "intent": "result_invalid"},
            ],
            "allow_free_input": True,
        },
        "stats": {
            "duration_ms": int(duration_ms),
            "subagents": int(subagents_count),
            "tokens": int(tokens_total),
        },
    }

    return GeneratedThreadReply(content=summary, blocks=[block], metadata=None)


def build_failure_result_card(
    *,
    feature_id: str,
    task_id: str,
    run_id: str,
    execution_id: str | None,
    payload: Mapping[str, Any] | None,
    error: str | None,
    failed_phase: str | None,
    duration_ms: int,
    subagents_count: int,
    tokens_total: int,
) -> GeneratedThreadReply:
    """Build a result_card for a failed feature task."""
    detail = (error or "执行失败").strip()
    phase_text = f"（{failed_phase}）" if failed_phase else ""
    tldr = f"{_feature_title(feature_id)} 失败{phase_text}：{detail}"

    block = {
        "kind": "result_card",
        "run_id": run_id,
        "title": f"{_feature_title(feature_id)} 执行失败",
        "tldr": _truncate(tldr, 280),
        "findings": [],
        "recommend": None,
        "links": [],
        "feedback": {
            "question": "如何处理这次失败？",
            "pills": [
                {"kind": "primary", "label": "重试", "intent": "retry_run"},
                {"kind": "normal", "label": "调整参数后重试", "intent": "adjust_and_retry"},
                {"kind": "warn", "label": "放弃这一轮", "intent": "abandon_run"},
            ],
            "allow_free_input": True,
        },
        "stats": {
            "duration_ms": int(duration_ms),
            "subagents": int(subagents_count),
            "tokens": int(tokens_total),
        },
    }

    return GeneratedThreadReply(content=tldr, blocks=[block], metadata=None)
