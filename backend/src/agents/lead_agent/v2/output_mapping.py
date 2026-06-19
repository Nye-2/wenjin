"""OutputMappingResolver — transforms subagent outputs into typed ResultOutput objects."""
from __future__ import annotations

import logging
import re
from typing import Any

from src.agents.contracts.task_report import (
    DecisionData,
    DecisionOutput,
    DocumentData,
    DocumentOutput,
    LibraryItemData,
    LibraryItemOutput,
    MemoryFactData,
    MemoryFactOutput,
    ResultOutput,
    ReviewPacket,
    ReviewPacketCompletionStatus,
    ReviewPacketItem,
    TaskData,
    TaskOutput,
)
from src.contracts.team_expert import ExpertReportV1

logger = logging.getLogger(__name__)


def _dot_get(obj: Any, path: str) -> Any:
    """Resolve a dot-separated path against a dict. Returns None on any failure."""
    if obj is None:
        return None
    current = obj
    for key in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current


def _resolve_value(expr: str, output: dict, item: dict | None = None) -> Any:
    """Resolve a template expression or return a literal string.

    Supports pure templates (entire string is {{...}}), interpolated strings
    (containing one or more {{...}} segments mixed with literals), and plain
    literal strings.
    """
    if not isinstance(expr, str):
        return expr

    # Pure template — return the resolved value directly (preserves type)
    if expr.startswith("{{") and expr.endswith("}}") and expr.count("{{") == 1:
        path = expr[2:-2].strip()
        if path.startswith("output."):
            return _dot_get(output, path[7:])
        if path.startswith("item."):
            return _dot_get(item, path[5:])
        return None

    # Interpolated string — replace all {{...}} segments
    if "{{" in expr:
        def _replace(m: re.Match) -> str:
            path = m.group(1).strip()
            if path.startswith("output."):
                val = _dot_get(output, path[7:])
            elif path.startswith("item."):
                val = _dot_get(item, path[5:])
            else:
                val = None
            return str(val) if val is not None else ""
        return re.sub(r"\{\{(.+?)\}\}", _replace, expr)

    return expr


def resolve_output_mapping_value(
    expr: str,
    output: dict,
    item: dict | None = None,
) -> Any:
    """Resolve an output mapping expression for runtime consumers."""
    return _resolve_value(expr, output, item)


_KIND_TO_DATA_MODEL = {
    "library_item": ("library_item", LibraryItemData, LibraryItemOutput),
    "document": ("document", DocumentData, DocumentOutput),
    "memory_fact": ("memory_fact", MemoryFactData, MemoryFactOutput),
    "decision": ("decision", DecisionData, DecisionOutput),
    "task": ("task", TaskData, TaskOutput),
}

_KIND_PREVIEW_TEMPLATE = {
    "library_item": lambda d: f"{d.title} — {', '.join(d.authors[:3])}" + (f", {d.year}" if d.year else ""),
    "document": lambda d: f"{d.name} ({d.mime_type or 'text/markdown'})",
    "memory_fact": lambda d: (d.content[:80] + "...") if len(d.content) > 80 else d.content,
    "decision": lambda d: f"{d.key}: {d.value}",
    "task": lambda d: d.title,
}


class OutputMappingResolver:
    """Resolves output mapping declarations from capability YAML against node_results."""

    def resolve(self, graph_template: dict, node_results: dict) -> list[ResultOutput]:
        outputs: list[ResultOutput] = []
        for phase in graph_template.get("phases", []):
            for task in phase.get("tasks", []):
                task_name = task["name"]
                for decl in task.get("outputs", []):
                    outputs.extend(self._resolve_declaration(task_name, decl, node_results))
        return outputs

    def _resolve_declaration(
        self, task_name: str, decl: dict, node_results: dict,
    ) -> list[ResultOutput]:
        kind = decl["kind"]
        if kind == "prism_file_change":
            return []
        if kind not in _KIND_TO_DATA_MODEL:
            logger.warning("Unknown output kind '%s' in task '%s'", kind, task_name)
            return []

        kind_str, data_model, output_model = _KIND_TO_DATA_MODEL[kind]
        mapping = decl.get("mapping", {})
        default_checked = decl.get("default_checked", True)
        iterate_on = decl.get("iterate_on")

        nr = node_results.get(task_name)
        if not isinstance(nr, dict):
            return []
        output = nr.get("output")
        if not isinstance(output, dict):
            return []

        if iterate_on:
            return self._resolve_iterated(
                task_name, kind, kind_str, iterate_on, mapping, output, data_model, output_model, default_checked,
            )
        return self._resolve_single(
            task_name, kind, kind_str, mapping, output, None, data_model, output_model, default_checked, 0,
        )

    def _resolve_iterated(
        self, task_name: str, kind: str, kind_str: str, iterate_on: str, mapping: dict,
        output: dict, data_model: type, output_model: type, default_checked: bool,
    ) -> list[ResultOutput]:
        path = iterate_on
        if path.startswith("output."):
            path = path[7:]
        array = _dot_get(output, path)
        if not isinstance(array, list):
            return []

        results: list[ResultOutput] = []
        for i, item in enumerate(array):
            if not isinstance(item, dict):
                continue
            resolved = self._resolve_single(
                task_name, kind, kind_str, mapping, output, item, data_model, output_model, default_checked, i,
            )
            results.extend(resolved)
        return results

    def _resolve_single(
        self, task_name: str, kind: str, kind_str: str, mapping: dict,
        output: dict, item: dict | None, data_model: type, output_model: type,
        default_checked: bool, index: int,
    ) -> list[ResultOutput]:
        resolved_fields: dict[str, Any] = {}
        for field_name, expr in mapping.items():
            value = _resolve_value(expr, output, item)
            if value is not None:
                resolved_fields[field_name] = value

        try:
            data = data_model(**resolved_fields)
        except Exception:
            logger.warning(
                "Failed to construct %s data for task '%s' with fields %s",
                kind, task_name, list(resolved_fields.keys()),
                exc_info=True,
            )
            return []

        preview_fn = _KIND_PREVIEW_TEMPLATE.get(kind)
        preview = preview_fn(data) if preview_fn else str(data)

        output_id = f"{task_name}-{kind}-{index}"
        return [output_model(
            id=output_id,
            kind=kind_str,
            preview=preview,
            default_checked=default_checked,
            data=data,
        )]


def review_packet_from_expert_reports(
    *,
    execution_id: str,
    capability_id: str,
    title: str,
    reports: list[ExpertReportV1],
    completion_status: str,
) -> ReviewPacket:
    """Map expert reports into the semantic Review Packet contract."""

    normalized_status = _review_packet_completion_status(completion_status)
    items: list[ReviewPacketItem] = []
    for report_index, report in enumerate(reports):
        artifact_refs = [
            f"artifact:{artifact.path}"
            for artifact in report.artifacts
            if artifact.reviewable
        ]
        evidence_refs = [
            f"{evidence.source_type}:{evidence.source_id}"
            for evidence in report.evidence
            if evidence.source_id
        ]
        claim_refs = [
            claim.claim_id
            for claim in report.claims
            if claim.support_level in {"verified", "supported", "plausible"}
        ]
        if report.summary or artifact_refs or claim_refs:
            items.append(
                ReviewPacketItem(
                    item_id=f"{_safe_id(report.expert_id)}-{report_index}-summary",
                    kind="document" if artifact_refs else "memory",
                    title=_review_packet_title_for_report(report),
                    summary=report.summary,
                    preview={"format": "markdown", "excerpt": report.summary[:500]},
                    source={"expert_id": report.expert_id, "skill_id": report.skill_id},
                    claim_refs=claim_refs,
                    evidence_refs=evidence_refs,
                    artifact_refs=artifact_refs,
                    quality_surfaces=list(report.quality_gates_checked),
                    risk=_risk_from_report(report),
                    default_checked=normalized_status == "complete" and not _report_has_unsupported_claims(report),
                    can_commit=True,
                    provenance={"execution_id": execution_id, "expert_id": report.expert_id},
                )
            )
        unsupported_claims = [
            claim for claim in report.claims if claim.support_level in {"weak", "unsupported"}
        ]
        for claim in unsupported_claims:
            items.append(
                ReviewPacketItem(
                    item_id=f"{_safe_id(report.expert_id)}-{_safe_id(claim.claim_id)}-warning",
                    kind="warning",
                    title="弱证据或未支持论断",
                    summary=claim.text,
                    preview={"format": "text", "excerpt": claim.text},
                    source={"expert_id": report.expert_id, "skill_id": report.skill_id},
                    claim_refs=[claim.claim_id],
                    evidence_refs=list(claim.evidence_ids),
                    quality_surfaces=list(report.quality_gates_checked),
                    risk={
                        "level": "high",
                        "reasons": claim.limitations or ["claim is not sufficiently supported"],
                    },
                    default_checked=False,
                    can_commit=False,
                    provenance={"execution_id": execution_id, "expert_id": report.expert_id},
                )
            )
    return ReviewPacket(
        packet_id=f"{execution_id}-review-packet",
        execution_id=execution_id,
        capability_id=capability_id,
        title=title,
        summary=_review_packet_summary(items),
        completion_status=normalized_status,
        items=items,
    )


def _review_packet_completion_status(value: str) -> ReviewPacketCompletionStatus:
    if value == "completed":
        return "complete"
    if value == "failed_partial":
        return "partial"
    if value in {"complete", "partial", "failed", "cancelled"}:
        return value  # type: ignore[return-value]
    return "partial"


def _review_packet_title_for_report(report: ExpertReportV1) -> str:
    if report.artifacts:
        return f"{report.skill_id} 产物"
    return f"{report.skill_id} 摘要"


def _report_has_unsupported_claims(report: ExpertReportV1) -> bool:
    return any(claim.support_level in {"weak", "unsupported"} for claim in report.claims)


def _risk_from_report(report: ExpertReportV1) -> dict[str, Any]:
    if _report_has_unsupported_claims(report):
        return {"level": "high", "reasons": ["contains weak or unsupported claims"]}
    if report.uncertainties:
        return {"level": "medium", "reasons": list(report.uncertainties[:5])}
    return {"level": "low", "reasons": []}


def _review_packet_summary(items: list[ReviewPacketItem]) -> str:
    committable = sum(1 for item in items if item.can_commit)
    blocked = len(items) - committable
    if blocked:
        return f"{committable} 项可保存，{blocked} 项需要确认。"
    return f"{committable} 项待确认成果。"


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value or "").strip()) or "item"
