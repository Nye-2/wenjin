"""Deterministic eval helpers for Wenjin research-task harness outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from src.agents.contracts.task_report import TaskReport
from src.sandbox.workspace_layout import WORKSPACE_HARNESS_INTERNAL_VIRTUAL_ROOT

ResearchSurface = Literal[
    "literature",
    "experiment",
    "writing",
    "workflow_trace",
    "citation_strength",
    "experiment_interpretation",
    "paper_relevance",
    "statistical_robustness",
    "writing_semantic_preservation",
]
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
    "incomplete",
    "missing",
    "missing_metadata",
    "missing_source",
    "needs_replacement",
    "not_ready",
    "replace",
    "unsupported",
}
_UNTRUSTED_CITATION_AUDIT_SEVERITIES = {"blocking", "critical", "high"}
_STRONG_CITATION_AUDIT_STATUSES = {
    "accepted",
    "grounded",
    "ready",
    "supported",
    "verified",
}
_STRONG_CITATION_AUDIT_RISKS = {
    "grounded",
    "low",
    "verified",
}
_WEAK_CITATION_AUDIT_STATUSES = {
    "partial",
    "uncertain",
    "weak",
}
_WEAK_CITATION_AUDIT_RISKS = {
    "medium",
    "partial",
    "uncertain",
    "weak",
}
_REJECTED_CITATION_AUDIT_STATUSES = {
    "blocked",
    "contradicted",
    "fabricated",
    "incomplete",
    "missing",
    "missing_metadata",
    "missing_source",
    "needs_replacement",
    "not_ready",
    "replace",
    "unsupported",
}


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
        "workflow_trace": _evaluate_workflow_trace,
        "citation_strength": _evaluate_citation_strength,
        "experiment_interpretation": _evaluate_experiment_interpretation,
        "paper_relevance": _evaluate_paper_relevance,
        "statistical_robustness": _evaluate_statistical_robustness,
        "writing_semantic_preservation": _evaluate_writing_semantic_preservation,
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


def _evaluate_citation_strength(
    report: TaskReport,
    node_events: list[dict[str, Any]],
) -> tuple[bool, dict[str, Any], str]:
    del report
    evidence = _citation_strength_evidence(node_events)
    if evidence["strong_count"] > 0:
        return True, evidence, ""
    return (
        False,
        evidence,
        "No strong citation/source audit evidence was produced.",
    )


def _evaluate_paper_relevance(
    report: TaskReport,
    node_events: list[dict[str, Any]],
) -> tuple[bool, dict[str, Any], str]:
    del report
    evidence = _paper_relevance_evidence(node_events)
    if evidence["aligned_count"] > 0 and evidence["off_topic_count"] == 0 and evidence["aligned_refs"]:
        return True, evidence, ""
    return (
        False,
        evidence,
        "No topic-aligned paper relevance evidence was produced.",
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


def _evaluate_experiment_interpretation(
    report: TaskReport,
    node_events: list[dict[str, Any]],
) -> tuple[bool, dict[str, Any], str]:
    del report
    evidence = _experiment_interpretation_evidence(node_events)
    has_core_interpretation = (
        evidence["interpretation_count"] > 0
        and evidence["method_summary_count"] > 0
        and bool(evidence["metric_names"])
        and evidence["verified_result_count"] > 0
        and evidence["limitation_count"] > 0
        and bool(evidence["artifact_paths"])
        and bool(evidence["dataset_paths"])
    )
    has_reproducibility_alignment = bool(
        set(evidence["artifact_paths"]) & set(evidence["reproducibility_artifact_paths"])
    ) and bool(
        set(evidence["dataset_paths"]) & set(evidence["reproducibility_dataset_paths"])
    )
    if has_core_interpretation and has_reproducibility_alignment:
        return True, evidence, ""
    return (
        False,
        evidence,
        "No experiment interpretation with method, metric, result, limitation, artifact, and dataset evidence was produced.",
    )


def _evaluate_statistical_robustness(
    report: TaskReport,
    node_events: list[dict[str, Any]],
) -> tuple[bool, dict[str, Any], str]:
    del report
    evidence = _statistical_robustness_evidence(node_events)
    has_core_statistics = (
        evidence["check_count"] > 0
        and evidence["method_count"] > 0
        and bool(evidence["metric_names"])
        and evidence["sample_size_count"] > 0
        and evidence["robustness_check_count"] > 0
        and evidence["passed_robustness_check_count"] > 0
        and evidence["critical_failed_robustness_check_count"] == 0
        and evidence["limitation_count"] > 0
        and bool(evidence["artifact_paths"])
        and bool(evidence["dataset_paths"])
    )
    has_reproducibility_alignment = bool(
        set(evidence["artifact_paths"]) & set(evidence["reproducibility_artifact_paths"])
    ) and bool(
        set(evidence["dataset_paths"]) & set(evidence["reproducibility_dataset_paths"])
    )
    if has_core_statistics and has_reproducibility_alignment:
        return True, evidence, ""
    return (
        False,
        evidence,
        (
            "No statistical robustness evidence with method, sample size, metrics, "
            "passed checks, limitations, artifact, and dataset alignment was produced."
        ),
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


def _evaluate_writing_semantic_preservation(
    report: TaskReport,
    node_events: list[dict[str, Any]],
) -> tuple[bool, dict[str, Any], str]:
    del node_events
    evidence = _writing_semantic_preservation_evidence(report)
    passed = (
        evidence["review_item_count"] > 0
        and evidence["checked_item_count"] == evidence["review_item_count"]
        and evidence["missing_semantic_contract_count"] == 0
        and evidence["high_risk_count"] == 0
        and evidence["claim_preservation_fail_count"] == 0
        and evidence["citation_preservation_fail_count"] == 0
        and evidence["equation_preservation_fail_count"] == 0
        and evidence["table_preservation_fail_count"] == 0
    )
    if passed:
        return True, evidence, ""
    return (
        False,
        evidence,
        "No low-risk Prism semantic preservation contract was produced for writing review.",
    )


def _evaluate_workflow_trace(
    report: TaskReport,
    node_events: list[dict[str, Any]],
) -> tuple[bool, dict[str, Any], str]:
    del report
    evidence = _workflow_trace_evidence(node_events)
    if evidence["member_count"] > 0 and evidence["completed_tool_count"] > 0:
        return True, evidence, ""
    return (
        False,
        evidence,
        "No member execution transcript with completed tool activity was produced.",
    )


def _workflow_trace_evidence(node_events: list[dict[str, Any]]) -> dict[str, Any]:
    member_count = 0
    tool_call_count = 0
    completed_tool_count = 0
    failed_tool_count = 0
    generated_artifact_count = 0
    duration_ms = 0
    credits_charged = 0.0
    tool_names: list[str] = []
    changed_paths: list[str] = []
    sandbox_job_ids: list[str] = []
    sandbox_environment_ids: list[str] = []
    scratch_refs: list[str] = []
    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for transcript in _member_execution_transcripts(node_events):
        member_count += 1
        tool_call_count += _int_value(transcript.get("tool_call_count"))
        completed_tool_count += _int_value(transcript.get("completed_tool_count"))
        failed_tool_count += _int_value(transcript.get("failed_tool_count"))
        generated_artifact_count += _int_value(transcript.get("generated_artifact_count"))
        duration_ms += _int_value(transcript.get("duration_ms"))
        for name in _string_list(transcript.get("tool_names")):
            _append_unique(tool_names, name)
        for path in (_workspace_path(path) for path in _string_list(transcript.get("changed_paths"))):
            _append_unique(changed_paths, path)
        for job_id in _string_list(transcript.get("sandbox_job_ids")):
            _append_unique(sandbox_job_ids, job_id)
        for environment_id in _string_list(transcript.get("sandbox_environment_ids")):
            _append_unique(sandbox_environment_ids, environment_id)
        for ref in (_workspace_task_scratch_ref(ref) for ref in _string_list(transcript.get("scratch_refs"))):
            _append_unique(scratch_refs, ref)
        raw_usage = _dict_value(transcript.get("usage"))
        for key in usage:
            usage[key] += _int_value(raw_usage.get(key))
        billing = _dict_value(transcript.get("billing"))
        credits_charged += _number_value(billing.get("credits_charged"))
    return {
        "member_count": member_count,
        "tool_call_count": tool_call_count,
        "completed_tool_count": completed_tool_count,
        "failed_tool_count": failed_tool_count,
        "tool_names": tool_names[:50],
        "changed_paths": changed_paths[:50],
        "sandbox_job_ids": sandbox_job_ids[:50],
        "sandbox_environment_ids": sandbox_environment_ids[:50],
        "scratch_refs": scratch_refs[:50],
        "generated_artifact_count": generated_artifact_count,
        "usage": usage,
        "billing": {"credits_charged": _json_number(credits_charged)},
        "duration_ms": duration_ms,
    }


def _experiment_interpretation_evidence(node_events: list[dict[str, Any]]) -> dict[str, Any]:
    interpretation_count = 0
    method_summary_count = 0
    verified_result_count = 0
    limitation_count = 0
    metric_names: list[str] = []
    artifact_paths: list[str] = []
    dataset_paths: list[str] = []
    for summary in _experiment_interpretation_summaries(node_events):
        interpretation_count += _int_value(summary.get("interpretation_count"))
        summary_method_count = _int_value(summary.get("method_summary_count"))
        if summary_method_count == 0:
            summary_method_count = len(_string_list(summary.get("method_summaries")))
        method_summary_count += summary_method_count
        verified_result_count += _int_value(summary.get("verified_result_count"))
        summary_limitation_count = _int_value(summary.get("limitation_count"))
        if summary_limitation_count == 0:
            summary_limitation_count = len(_string_list(summary.get("limitations")))
        limitation_count += summary_limitation_count
        for metric_name in _string_list(summary.get("metric_names")):
            _append_unique(metric_names, metric_name)
        for path in (_workspace_artifact_path(path) for path in _string_list(summary.get("artifact_paths"))):
            _append_unique(artifact_paths, path)
        for path in _workspace_dataset_paths(summary.get("dataset_paths")):
            _append_unique(dataset_paths, path)

    reproducibility_summaries = _reproducibility_summaries(node_events)
    reproducibility_artifact_paths = _unique(_summary_paths(reproducibility_summaries, "artifact_paths"))
    reproducibility_dataset_paths = _unique(_summary_paths(reproducibility_summaries, "dataset_paths"))
    return {
        "interpretation_count": interpretation_count,
        "method_summary_count": method_summary_count,
        "metric_names": metric_names[:50],
        "verified_result_count": verified_result_count,
        "limitation_count": limitation_count,
        "artifact_paths": artifact_paths[:50],
        "dataset_paths": dataset_paths[:50],
        "reproducibility_artifact_paths": reproducibility_artifact_paths[:50],
        "reproducibility_dataset_paths": reproducibility_dataset_paths[:50],
    }


def _experiment_interpretation_summaries(node_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for event in node_events:
        harness = _harness_metadata(event)
        summary = harness.get("experiment_interpretation_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
    return summaries[:20]


def _statistical_robustness_evidence(node_events: list[dict[str, Any]]) -> dict[str, Any]:
    check_count = 0
    method_count = 0
    sample_size_count = 0
    robustness_check_count = 0
    passed_robustness_check_count = 0
    failed_robustness_check_count = 0
    critical_failed_robustness_check_count = 0
    limitation_count = 0
    metric_names: list[str] = []
    sample_sizes: list[int] = []
    artifact_paths: list[str] = []
    dataset_paths: list[str] = []
    failed_robustness_checks: list[str] = []
    for summary in _statistical_robustness_summaries(node_events):
        check_count += _int_value(summary.get("check_count"))
        method_count += _int_value(summary.get("method_count"))
        sample_size_count += _int_value(summary.get("sample_size_count"))
        robustness_check_count += _int_value(summary.get("robustness_check_count"))
        passed_robustness_check_count += _int_value(summary.get("passed_robustness_check_count"))
        failed_robustness_check_count += _int_value(summary.get("failed_robustness_check_count"))
        critical_failed_robustness_check_count += _int_value(
            summary.get("critical_failed_robustness_check_count")
        )
        limitation_count += _int_value(summary.get("limitation_count"))
        for metric_name in _string_list(summary.get("metric_names")):
            _append_unique(metric_names, metric_name)
        for sample_size in (_int_value(value) for value in _string_list(summary.get("sample_sizes"))):
            if sample_size and sample_size not in sample_sizes:
                sample_sizes.append(sample_size)
        for path in (_workspace_artifact_path(path) for path in _string_list(summary.get("artifact_paths"))):
            _append_unique(artifact_paths, path)
        for path in _workspace_dataset_paths(summary.get("dataset_paths")):
            _append_unique(dataset_paths, path)
        for name in _string_list(summary.get("failed_robustness_checks")):
            _append_unique(failed_robustness_checks, name)

    if sample_size_count == 0:
        sample_size_count = len(sample_sizes)
    reproducibility_summaries = _reproducibility_summaries(node_events)
    reproducibility_artifact_paths = _unique(_summary_paths(reproducibility_summaries, "artifact_paths"))
    reproducibility_dataset_paths = _unique(_summary_paths(reproducibility_summaries, "dataset_paths"))
    return {
        "check_count": check_count,
        "method_count": method_count,
        "metric_names": metric_names[:50],
        "sample_size_count": sample_size_count,
        "sample_sizes": sample_sizes[:20],
        "robustness_check_count": robustness_check_count,
        "passed_robustness_check_count": passed_robustness_check_count,
        "failed_robustness_check_count": failed_robustness_check_count,
        "critical_failed_robustness_check_count": critical_failed_robustness_check_count,
        "limitation_count": limitation_count,
        "artifact_paths": artifact_paths[:50],
        "dataset_paths": dataset_paths[:50],
        "reproducibility_artifact_paths": reproducibility_artifact_paths[:50],
        "reproducibility_dataset_paths": reproducibility_dataset_paths[:50],
        "failed_robustness_checks": failed_robustness_checks[:20],
    }


def _statistical_robustness_summaries(node_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for event in node_events:
        harness = _harness_metadata(event)
        summary = harness.get("statistical_robustness_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
    return summaries[:20]


def _writing_semantic_preservation_evidence(report: TaskReport) -> dict[str, Any]:
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
        content_contract = _prism_content_contract(item)
        semantic_contract = _prism_semantic_contract(item)
        failed_flags: list[str] = []
        if not content_contract or not _prism_change_is_structurally_reviewable(item):
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


def _member_execution_transcripts(node_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    transcripts: list[dict[str, Any]] = []
    for event in node_events:
        harness = _harness_metadata(event)
        transcript = harness.get("member_execution_transcript")
        if isinstance(transcript, dict):
            transcripts.append(transcript)
    return transcripts


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


def _prism_semantic_contract(item: dict[str, Any]) -> dict[str, Any]:
    preview = item.get("preview") if isinstance(item.get("preview"), dict) else {}
    contract = preview.get("semantic_contract")
    return dict(contract) if isinstance(contract, dict) else {}


def _citation_audit_refs(node_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for finding in _citation_source_findings(node_events):
        ref = _citation_audit_ref(finding)
        if ref:
            refs.append(ref)
    return _dedupe_citation_refs(refs)[:50]


def _citation_strength_evidence(node_events: list[dict[str, Any]]) -> dict[str, Any]:
    strong_refs: list[dict[str, str]] = []
    weak_refs: list[dict[str, str]] = []
    rejected_refs: list[dict[str, str]] = []
    for finding in _citation_source_findings(node_events):
        ref = _citation_strength_ref(finding)
        if not ref:
            continue
        if _citation_strength_ref_is_rejected(ref):
            _append_unique_dict(rejected_refs, ref)
            continue
        if _citation_strength_ref_is_strong(ref):
            _append_unique_dict(strong_refs, ref)
            continue
        if _citation_strength_ref_is_weak(ref):
            _append_unique_dict(weak_refs, ref)
    return {
        "strong_refs": strong_refs[:50],
        "weak_refs": weak_refs[:50],
        "rejected_refs": rejected_refs[:50],
        "strong_count": len(strong_refs),
        "weak_count": len(weak_refs),
        "rejected_count": len(rejected_refs),
    }


def _paper_relevance_evidence(node_events: list[dict[str, Any]]) -> dict[str, Any]:
    aligned_refs: list[dict[str, str]] = []
    weak_refs: list[dict[str, str]] = []
    off_topic_refs: list[dict[str, str]] = []
    aligned_count = 0
    weak_count = 0
    off_topic_count = 0
    for summary in _paper_relevance_summaries(node_events):
        summary_aligned_refs = _paper_relevance_refs(summary.get("aligned_refs"))
        summary_weak_refs = _paper_relevance_refs(summary.get("weak_refs"))
        summary_off_topic_refs = _paper_relevance_refs(summary.get("off_topic_refs"))
        aligned_count += _int_value(summary.get("aligned_count")) or len(summary_aligned_refs)
        weak_count += _int_value(summary.get("weak_count")) or len(summary_weak_refs)
        off_topic_count += _int_value(summary.get("off_topic_count")) or len(summary_off_topic_refs)
        for ref in summary_aligned_refs:
            _append_unique_dict(aligned_refs, ref)
        for ref in summary_weak_refs:
            _append_unique_dict(weak_refs, ref)
        for ref in summary_off_topic_refs:
            _append_unique_dict(off_topic_refs, ref)
    return {
        "aligned_count": aligned_count,
        "weak_count": weak_count,
        "off_topic_count": off_topic_count,
        "aligned_refs": aligned_refs[:50],
        "weak_refs": weak_refs[:50],
        "off_topic_refs": off_topic_refs[:50],
    }


def _paper_relevance_summaries(node_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for event in node_events:
        harness = _harness_metadata(event)
        summary = harness.get("paper_relevance_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
    return summaries[:20]


def _paper_relevance_refs(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    refs: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        source_id = _clean_text(item.get("source_id"))
        citation_key = _clean_text(item.get("citation_key"))
        if not source_id and not citation_key:
            continue
        ref = {
            "source_id": source_id,
            "citation_key": citation_key,
            "reason": _clean_text(item.get("reason"))[:300],
        }
        refs.append({key: value for key, value in ref.items() if value})
    return refs


def _citation_source_findings(node_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for event in node_events:
        harness = _harness_metadata(event)
        findings.extend(
            _citation_source_findings_from_value(
                harness.get("citation_source_audit")
            )
        )
        findings.extend(_team_quality_gate_citation_findings(event))
    return findings


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
    risk = _clean_text(finding.get("risk")).lower()
    severity = _clean_text(finding.get("severity")).lower()
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


def _citation_strength_ref(finding: dict[str, Any]) -> dict[str, str] | None:
    source_id = _clean_text(finding.get("source_id"))
    citation_key = _clean_text(finding.get("citation_key"))
    if not source_id and not citation_key:
        return None
    ref = {
        "source_id": source_id,
        "citation_key": citation_key,
        "status": _clean_text(finding.get("status")).lower(),
        "risk": _clean_text(finding.get("risk")).lower(),
        "severity": _clean_text(finding.get("severity")).lower(),
    }
    return {key: value for key, value in ref.items() if value}


def _citation_strength_ref_is_rejected(ref: dict[str, str]) -> bool:
    return (
        ref.get("status") in _REJECTED_CITATION_AUDIT_STATUSES
        or ref.get("risk") in _UNTRUSTED_CITATION_AUDIT_RISKS
        or ref.get("severity") in _UNTRUSTED_CITATION_AUDIT_SEVERITIES
    )


def _citation_strength_ref_is_strong(ref: dict[str, str]) -> bool:
    if _citation_strength_ref_has_weak_signal(ref):
        return False
    return (
        ref.get("status") in _STRONG_CITATION_AUDIT_STATUSES
        or ref.get("risk") in _STRONG_CITATION_AUDIT_RISKS
    ) and not _citation_strength_ref_is_rejected(ref)


def _citation_strength_ref_is_weak(ref: dict[str, str]) -> bool:
    return _citation_strength_ref_has_weak_signal(ref) or bool(
        ref.get("source_id") or ref.get("citation_key")
    )


def _citation_strength_ref_has_weak_signal(ref: dict[str, str]) -> bool:
    return (
        ref.get("status") in _WEAK_CITATION_AUDIT_STATUSES
        or ref.get("risk") in _WEAK_CITATION_AUDIT_RISKS
    )


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
        if path.startswith(f"{WORKSPACE_HARNESS_INTERNAL_VIRTUAL_ROOT}/"):
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


def _workspace_task_scratch_ref(value: Any) -> str:
    path = _workspace_path(value)
    if not path.startswith("/workspace/tmp/tasks/"):
        return ""
    if path.startswith(f"{WORKSPACE_HARNESS_INTERNAL_VIRTUAL_ROOT}/"):
        return ""
    parts = path.removeprefix("/workspace/tmp/tasks/").split("/")
    if len(parts) < 2 or any(part in {"", ".", ".."} for part in parts):
        return ""
    return path


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


def _append_unique(values: list[str], value: str) -> None:
    text = _clean_text(value)
    if text and text not in values:
        values.append(text)


def _append_unique_dict(values: list[dict[str, str]], value: dict[str, str]) -> None:
    if value not in values:
        values.append(value)


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _number_value(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        parsed = float(value)
    else:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.0
    return parsed if parsed > 0 else 0.0


def _json_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else ""
