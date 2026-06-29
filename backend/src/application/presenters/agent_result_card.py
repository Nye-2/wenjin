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
    "idea_to_thesis_manuscript": "Idea 到论文全文",
    "thesis_research_pack": "论文研究包",
    "thesis_empirical_analysis": "论文实证分析",
    "thesis_revision_pass": "论文修订",
    "thesis_defense_pack": "答辩材料包",
    "thesis_reference_curation": "参考文献整理",
    "research_question_to_paper": "SCI 论文主稿",
    "sci_literature_positioning": "SCI 文献定位",
    "sci_empirical_package": "SCI 实证包",
    "sci_revision_for_journal": "SCI 期刊修订",
    "journal_submission_strategy": "投稿策略",
    "response_to_reviewers": "审稿回复",
    "reproducibility_audit": "可复现性审计",
    "idea_to_proposal_package": "申报书整包",
    "proposal_background_pack": "申报背景包",
    "technical_route_package": "技术路线包",
    "feasibility_and_risk_review": "可行性与风险评审",
    "proposal_polish_for_review": "申报书送审润色",
    "software_copyright_application_pack": "软著申请包",
    "software_technical_manual": "软件技术说明书",
    "software_evidence_pack": "软著证据包",
    "software_architecture_diagrams": "软件架构图",
    "invention_to_patent_draft": "专利初稿",
    "prior_art_and_novelty_pack": "现有技术与新颖性包",
    "claims_strategy": "权利要求策略",
    "embodiment_and_drawings": "实施例与附图",
    "office_action_response": "审查意见答复",
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


def _review_items_from_result(result: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(result, Mapping):
        return []
    raw = result.get("review_items")
    if not isinstance(raw, list):
        task_report = result.get("task_report")
        raw = task_report.get("review_items") if isinstance(task_report, Mapping) else None
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


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

    if action_name in {"open_prism", "preview_prism_changes"}:
        if not workspace_id:
            return None
        if action_name == "preview_prism_changes":
            query: list[tuple[str, str]] = [("focus", "file_changes")]
            review_item_id = str(action.get("review_item_id") or "").strip()
            logical_key = str(action.get("logical_key") or "").strip()
            if review_item_id:
                query.append(("review_item_id", review_item_id))
            if logical_key:
                query.append(("logical_key", logical_key))
            return f"/workspaces/{workspace_id}/prism?{urlencode(query, doseq=True)}"
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
        artifact_kind = str(action.get("artifact_kind") or "").strip()
        title = str(action.get("title") or "").strip()
        artifact_id = str(action.get("artifact_id") or "").strip()
        file_id = str(action.get("file_id") or artifact_id).strip()
        if artifact_kind == "document":
            query: list[tuple[str, str]] = []
            if file_id:
                query.append(("file_id", file_id))
            suffix = urlencode(query, doseq=True)
            return f"/workspaces/{workspace_id}/prism?{suffix}" if suffix else f"/workspaces/{workspace_id}/prism"
        room = _artifact_room(artifact_kind)
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
        "review_items": _review_items_from_result(result),
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
