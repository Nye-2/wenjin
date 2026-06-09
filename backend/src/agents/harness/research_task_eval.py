"""Deterministic eval helpers for Wenjin research-task harness outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from src.agents.contracts.task_report import TaskReport

ResearchSurface = Literal["literature", "experiment", "writing"]
EvalStatus = Literal["pass", "fail"]

_VERIFIED_LITERATURE_LEVELS = {
    "external_verified",
    "indexed_fulltext",
    "uploaded_fulltext",
}
_UNTRUSTED_CITATION_AUDIT_RISKS = {
    "blocked",
    "contradicted",
    "fabricated",
    "missing",
    "missing_source",
    "unsupported",
}
_UNTRUSTED_CITATION_AUDIT_SEVERITIES = {"blocking", "critical", "high"}


@dataclass(slots=True)
class ResearchTaskEvidenceEval:
    """Compact deterministic audit for a research workflow result."""

    status: EvalStatus
    coverage: dict[str, EvalStatus]
    findings: list[dict[str, Any]] = field(default_factory=list)
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)


def evaluate_research_task_evidence(
    report: TaskReport,
    *,
    node_events: list[dict[str, Any]] | None = None,
    required_surfaces: tuple[ResearchSurface, ...] = ("literature", "experiment", "writing"),
) -> ResearchTaskEvidenceEval:
    """Evaluate whether a research task produced reviewable, grounded evidence.

    This is intentionally deterministic and model-free. It does not judge prose
    quality; it verifies that the harness produced the evidence surfaces needed
    for later human/model quality review.
    """

    node_events = node_events or []
    coverage: dict[str, EvalStatus] = {}
    findings: list[dict[str, Any]] = []
    evidence: dict[str, dict[str, Any]] = {}

    checks = {
        "literature": _evaluate_literature,
        "experiment": _evaluate_experiment,
        "writing": _evaluate_writing,
    }
    for surface in required_surfaces:
        passed, surface_evidence, message = checks[surface](report, node_events)
        coverage[surface] = "pass" if passed else "fail"
        evidence[surface] = surface_evidence
        if not passed:
            findings.append(
                {
                    "surface": surface,
                    "severity": "high",
                    "message": message,
                }
            )

    status: EvalStatus = "pass" if all(value == "pass" for value in coverage.values()) else "fail"
    return ResearchTaskEvidenceEval(
        status=status,
        coverage=coverage,
        findings=findings,
        evidence=evidence,
    )


def _evaluate_literature(
    report: TaskReport,
    node_events: list[dict[str, Any]],
) -> tuple[bool, dict[str, Any], str]:
    verified_outputs: list[dict[str, Any]] = []
    for output in report.outputs:
        if output.kind != "library_item":
            continue
        data = output.data
        evidence_level = str(data.evidence_level or "").strip()
        has_external_identity = bool(str(data.doi or data.url or data.external_id or "").strip())
        if evidence_level in _VERIFIED_LITERATURE_LEVELS or (
            has_external_identity and str(data.source or "").strip()
        ):
            verified_outputs.append(
                {
                    "output_id": output.id,
                    "title": data.title,
                    "source": data.source,
                    "external_id": data.external_id,
                    "evidence_level": evidence_level,
                }
            )

    audit_refs = _citation_audit_refs(node_events)
    evidence = {
        "verified_library_outputs": verified_outputs,
        "citation_audit_refs": audit_refs,
    }
    if verified_outputs or audit_refs:
        return True, evidence, ""
    return (
        False,
        evidence,
        "No verified literature output or citation/source audit refs were produced.",
    )


def _evaluate_experiment(
    report: TaskReport,
    node_events: list[dict[str, Any]],
) -> tuple[bool, dict[str, Any], str]:
    review_artifacts: list[dict[str, Any]] = []
    artifact_paths: list[str] = []
    for item in report.review_items:
        if not isinstance(item, dict) or item.get("kind") != "sandbox_artifact":
            continue
        reproducibility = item.get("reproducibility")
        if not isinstance(reproducibility, dict):
            continue
        source_script = _workspace_script_path(reproducibility.get("source_script"))
        dataset_paths = _workspace_dataset_paths(reproducibility.get("dataset_paths"))
        content_hash = _clean_text(reproducibility.get("content_hash"))
        target = item.get("target") if isinstance(item.get("target"), dict) else {}
        artifact_path = _workspace_artifact_path(target.get("path"))
        if source_script and dataset_paths and content_hash and artifact_path:
            review_artifacts.append(
                {
                    "review_item_id": str(item.get("id") or ""),
                    "source_script": source_script,
                    "dataset_paths": dataset_paths,
                    "artifact_path": artifact_path,
                    "content_hash": content_hash,
                }
            )
            artifact_paths.append(artifact_path)

    summaries = _reproducibility_summaries(node_events)
    evidence = {
        "review_artifacts": review_artifacts,
        "reproducibility_summaries": summaries,
        "artifact_paths": _unique([*artifact_paths, *_summary_paths(summaries, "artifact_paths")]),
    }
    if review_artifacts and summaries:
        return True, evidence, ""
    return (
        False,
        evidence,
        "No reviewable sandbox artifact with source script, dataset paths, content hash, and node reproducibility summary was produced.",
    )


def _evaluate_writing(
    report: TaskReport,
    node_events: list[dict[str, Any]],
) -> tuple[bool, dict[str, Any], str]:
    del node_events
    prism_changes: list[dict[str, Any]] = []
    documents: list[dict[str, Any]] = []
    for item in report.review_items:
        if not isinstance(item, dict) or item.get("kind") != "prism_file_change":
            continue
        target = item.get("target") if isinstance(item.get("target"), dict) else {}
        file_path = _clean_text(target.get("file_path"))
        logical_key = _clean_text(target.get("logical_key"))
        if file_path and logical_key and _prism_change_is_structurally_reviewable(item):
            prism_changes.append(
                {
                    "review_item_id": str(item.get("id") or ""),
                    "logical_key": logical_key,
                    "file_path": file_path,
                    "content_contract": _prism_content_contract(item),
                }
            )

    for output in report.outputs:
        if output.kind != "document":
            continue
        data = output.data
        has_content = bool(str(data.content or data.storage_path or "").strip())
        if has_content:
            documents.append(
                {
                    "output_id": output.id,
                    "name": data.name,
                    "doc_kind": data.doc_kind,
                }
            )

    evidence = {
        "prism_file_changes": prism_changes,
        "document_outputs": documents,
    }
    if prism_changes or documents:
        return True, evidence, ""
    return (
        False,
        evidence,
        "No structurally reviewable Prism file-change or document output was produced for writing review.",
    )


def _prism_change_is_structurally_reviewable(item: dict[str, Any]) -> bool:
    target = item.get("target") if isinstance(item.get("target"), dict) else {}
    file_path = _clean_text(target.get("file_path"))
    logical_key = _clean_text(target.get("logical_key"))
    if not file_path.lower().endswith(".tex"):
        return bool(file_path and logical_key)
    contract = _prism_content_contract(item)
    if not contract:
        return False
    if contract.get("balanced_braces") is not True:
        return False
    latex_shape = _clean_text(contract.get("latex_shape"))
    if file_path == "main.tex" or logical_key == "project:main":
        return latex_shape == "document"
    return latex_shape in {"document", "fragment"}


def _prism_content_contract(item: dict[str, Any]) -> dict[str, Any]:
    preview = item.get("preview") if isinstance(item.get("preview"), dict) else {}
    contract = preview.get("content_contract")
    return dict(contract) if isinstance(contract, dict) else {}


def _citation_audit_refs(node_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for event in node_events:
        harness = _harness_metadata(event)
        for finding in _citation_source_findings_from_value(
            harness.get("citation_source_audit")
        ):
            ref = _citation_audit_ref(finding)
            if ref:
                refs.append(ref)
        for finding in _team_quality_gate_citation_findings(event):
            ref = _citation_audit_ref(finding)
            if ref:
                refs.append(ref)
    return _dedupe_citation_refs(refs)[:50]


def _citation_source_findings_from_value(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _team_quality_gate_citation_findings(event: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for gate in _team_quality_gates(event):
        raw_findings = gate.get("findings")
        if not isinstance(raw_findings, list):
            continue
        for gate_finding in raw_findings:
            if not isinstance(gate_finding, dict):
                continue
            findings.extend(
                _citation_source_findings_from_value(
                    gate_finding.get("citation_source_audit")
                )
            )
    return findings


def _team_quality_gates(event: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        event.get("quality_gates"),
        _dict_value(event.get("runtime_state")).get("quality_gates"),
        _dict_value(event.get("runtime_state_json")).get("quality_gates"),
        _dict_value(_dict_value(event.get("node_metadata")).get("runtime_state")).get("quality_gates"),
    ]
    gates: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, list):
            continue
        gates.extend(item for item in candidate if isinstance(item, dict))
    return gates


def _citation_audit_ref(finding: dict[str, Any]) -> dict[str, str] | None:
    source_id = _clean_text(finding.get("source_id"))
    citation_key = _clean_text(finding.get("citation_key"))
    risk = _clean_text(finding.get("risk"))
    severity = _clean_text(finding.get("severity"))
    if risk in _UNTRUSTED_CITATION_AUDIT_RISKS:
        return None
    if severity in _UNTRUSTED_CITATION_AUDIT_SEVERITIES:
        return None
    if source_id or citation_key:
        return {
            "source_id": source_id,
            "citation_key": citation_key,
            "risk": risk,
        }
    return None


def _dedupe_citation_refs(refs: list[dict[str, str]]) -> list[dict[str, str]]:
    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for ref in refs:
        key = (
            ref.get("source_id", ""),
            ref.get("citation_key", ""),
            ref.get("risk", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(ref)
    return unique


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _reproducibility_summaries(node_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for event in node_events:
        harness = _harness_metadata(event)
        summary = harness.get("reproducibility_summary")
        if not isinstance(summary, dict):
            continue
        script_paths = [
            path
            for path in (_workspace_script_path(path) for path in _string_list(summary.get("script_paths")))
            if path
        ]
        dataset_paths = _workspace_dataset_paths(summary.get("dataset_paths"))
        artifact_paths = [
            path
            for path in (_workspace_artifact_path(path) for path in _string_list(summary.get("artifact_paths")))
            if path
        ]
        if script_paths and dataset_paths and artifact_paths:
            summaries.append(
                {
                    "script_paths": script_paths,
                    "dataset_paths": dataset_paths,
                    "artifact_paths": artifact_paths,
                }
            )
    return summaries[:20]


def _harness_metadata(event: dict[str, Any]) -> dict[str, Any]:
    node_metadata = event.get("node_metadata")
    if not isinstance(node_metadata, dict):
        return {}
    harness = node_metadata.get("harness")
    return dict(harness) if isinstance(harness, dict) else {}


def _summary_paths(summaries: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    for summary in summaries:
        values.extend(_string_list(summary.get(key)))
    return values


def _workspace_script_path(value: Any) -> str:
    path = _workspace_path(value)
    if not path.startswith("/workspace/scripts/") or not path.endswith(".py"):
        return ""
    return path


def _workspace_dataset_paths(value: Any) -> list[str]:
    return [
        path
        for path in (_workspace_path(item) for item in _string_list(value))
        if path.startswith("/workspace/datasets/")
    ][:50]


def _workspace_artifact_path(value: Any) -> str:
    path = _workspace_path(value)
    if path.startswith("/workspace/outputs/") or path.startswith("/workspace/reports/"):
        if path.startswith("/workspace/outputs/harness/"):
            return ""
        return path
    return ""


def _workspace_path(value: Any) -> str:
    text = _clean_text(value)
    if not text or not text.startswith("/workspace/"):
        return ""
    if "/../" in text or text.endswith("/..") or "\x00" in text:
        return ""
    if (
        text.startswith("/workspace/.")
        or "/.env" in text
        or text.endswith(".pem")
        or text.endswith(".key")
    ):
        return ""
    return text


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, list | tuple | set | frozenset):
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


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else ""
