"""Prism writing evidence builders for deterministic research-task eval."""

from __future__ import annotations

from typing import Any

from src.agents.contracts.task_report import TaskReport
from src.services.prism_review_contracts import is_valid_academic_style_delta_contract


def writing_semantic_preservation_evidence(report: TaskReport) -> dict[str, Any]:
    review_item_count = 0
    checked_item_count = 0
    missing_semantic_contract_count = 0
    high_risk_count = 0
    claim_preservation_fail_count = 0
    citation_preservation_fail_count = 0
    equation_preservation_fail_count = 0
    table_preservation_fail_count = 0
    risky_items: list[dict[str, Any]] = []
    for item in report.review_items:
        if not isinstance(item, dict) or item.get("kind") != "prism_file_change":
            continue
        review_item_count += 1
        target = item.get("target") if isinstance(item.get("target"), dict) else {}
        review_item_id = _clean_text(item.get("id"))
        file_path = _clean_text(target.get("file_path"))
        content_contract = prism_content_contract(item)
        semantic_contract = _prism_semantic_contract(item)
        failed_flags: list[str] = []
        if not content_contract or not prism_change_is_structurally_reviewable(item):
            failed_flags.append("structure")
        if not semantic_contract:
            missing_semantic_contract_count += 1
            failed_flags.append("semantic_contract")
            _append_risky_prism_item(
                risky_items,
                review_item_id=review_item_id,
                file_path=file_path,
                risk="high",
                failed_flags=failed_flags,
            )
            continue
        checked_item_count += 1
        risk = _clean_text(semantic_contract.get("risk")).lower() or "medium"
        if risk == "high":
            high_risk_count += 1
        if semantic_contract.get("preserves_claims") is not True:
            claim_preservation_fail_count += 1
            failed_flags.append("claims")
        if semantic_contract.get("preserves_citations") is not True:
            citation_preservation_fail_count += 1
            failed_flags.append("citations")
        if (
            semantic_contract.get("has_equations") is True
            and semantic_contract.get("preserves_equations") is not True
        ):
            equation_preservation_fail_count += 1
            failed_flags.append("equations")
        if (
            semantic_contract.get("has_tables") is True
            and semantic_contract.get("preserves_tables") is not True
        ):
            table_preservation_fail_count += 1
            failed_flags.append("tables")
        if risk == "high" or failed_flags:
            _append_risky_prism_item(
                risky_items,
                review_item_id=review_item_id,
                file_path=file_path,
                risk=risk,
                failed_flags=failed_flags,
            )
    return {
        "review_item_count": review_item_count,
        "checked_item_count": checked_item_count,
        "missing_semantic_contract_count": missing_semantic_contract_count,
        "high_risk_count": high_risk_count,
        "claim_preservation_fail_count": claim_preservation_fail_count,
        "citation_preservation_fail_count": citation_preservation_fail_count,
        "equation_preservation_fail_count": equation_preservation_fail_count,
        "table_preservation_fail_count": table_preservation_fail_count,
        "risky_items": risky_items[:20],
    }


def writing_academic_style_evidence(report: TaskReport) -> dict[str, Any]:
    review_item_count = 0
    checked_item_count = 0
    missing_style_contract_count = 0
    delta_checked_count = 0
    high_risk_count = 0
    low_score_count = 0
    anti_pattern_count = 0
    improvement_fail_count = 0
    min_score: int | None = None
    style_items: list[dict[str, Any]] = []
    for item in report.review_items:
        if not isinstance(item, dict) or item.get("kind") != "prism_file_change":
            continue
        review_item_count += 1
        target = item.get("target") if isinstance(item.get("target"), dict) else {}
        review_item_id = _clean_text(item.get("id"))
        file_path = _clean_text(target.get("file_path"))
        contract = _prism_academic_style_contract(item)
        if not contract:
            missing_style_contract_count += 1
            continue
        checked_item_count += 1
        risk = _clean_text(contract.get("risk")).lower() or "medium"
        score = min(_int_value(contract.get("academic_style_score")), 5)
        signals = _string_list(contract.get("signals"))[:10]
        anti_patterns = _string_list(contract.get("anti_patterns"))[:10]
        style_delta = _prism_academic_style_delta_contract(contract)
        if risk == "high":
            high_risk_count += 1
        if score < 3:
            low_score_count += 1
        anti_pattern_count += len(anti_patterns)
        if style_delta:
            delta_checked_count += 1
            if not is_valid_academic_style_delta_contract(style_delta, pending_score=score):
                improvement_fail_count += 1
        min_score = score if min_score is None else min(min_score, score)
        style_item = {
            "review_item_id": review_item_id,
            "file_path": file_path,
            "risk": risk,
            "academic_style_score": score,
            "signals": signals,
            "anti_patterns": anti_patterns,
        }
        if style_delta:
            style_item["style_delta"] = style_delta
        style_items.append(style_item)
    return {
        "review_item_count": review_item_count,
        "checked_item_count": checked_item_count,
        "missing_style_contract_count": missing_style_contract_count,
        "delta_checked_count": delta_checked_count,
        "high_risk_count": high_risk_count,
        "low_score_count": low_score_count,
        "anti_pattern_count": anti_pattern_count,
        "improvement_fail_count": improvement_fail_count,
        "min_academic_style_score": min_score or 0,
        "style_items": style_items[:20],
    }


def prism_change_is_structurally_reviewable(item: dict[str, Any]) -> bool:
    target = item.get("target") if isinstance(item.get("target"), dict) else {}
    file_path = _clean_text(target.get("file_path"))
    logical_key = _clean_text(target.get("logical_key"))
    if not file_path.lower().endswith(".tex"):
        return bool(file_path and logical_key)
    contract = prism_content_contract(item)
    if not contract:
        return False
    if contract.get("balanced_braces") is not True:
        return False
    latex_shape = _clean_text(contract.get("latex_shape"))
    if file_path == "main.tex" or logical_key == "project:main":
        return latex_shape == "document"
    return latex_shape in {"document", "fragment"}


def _append_risky_prism_item(
    values: list[dict[str, Any]],
    *,
    review_item_id: str,
    file_path: str,
    risk: str,
    failed_flags: list[str],
) -> None:
    values.append(
        {
            "review_item_id": review_item_id,
            "file_path": file_path,
            "risk": risk or "medium",
            "failed_flags": failed_flags,
        }
    )


def prism_content_contract(item: dict[str, Any]) -> dict[str, Any]:
    preview = item.get("preview") if isinstance(item.get("preview"), dict) else {}
    contract = preview.get("content_contract")
    return dict(contract) if isinstance(contract, dict) else {}


def _prism_semantic_contract(item: dict[str, Any]) -> dict[str, Any]:
    preview = item.get("preview") if isinstance(item.get("preview"), dict) else {}
    contract = preview.get("semantic_contract")
    return dict(contract) if isinstance(contract, dict) else {}


def _prism_academic_style_contract(item: dict[str, Any]) -> dict[str, Any]:
    preview = item.get("preview") if isinstance(item.get("preview"), dict) else {}
    contract = preview.get("academic_style_contract")
    return dict(contract) if isinstance(contract, dict) else {}


def _prism_academic_style_delta_contract(contract: dict[str, Any]) -> dict[str, Any]:
    delta = contract.get("style_delta")
    return dict(delta) if isinstance(delta, dict) else {}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, list | tuple | set):
        raw = list(value)
    else:
        return []
    return _unique([text for item in raw for text in (_clean_text(item),) if text])


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value)
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except ValueError:
            return 0
    return 0


def _clean_text(value: Any) -> str:
    return str(value or "").strip()
