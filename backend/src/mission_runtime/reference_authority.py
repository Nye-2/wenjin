"""Receipt-backed evidence authority shared by the Mission agent and quality runtime."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.contracts.research_evidence import KNOWN_RESEARCH_SURFACES
from src.dataservice_client.contracts.mission import MissionItemPayload


@dataclass(frozen=True, slots=True)
class EvidenceAuthority:
    evidence_id: str
    stage_id: str | None
    kind: str
    title: str
    source_ref: str | None
    operation_id: str
    surfaces: frozenset[str]
    supported_claims: frozenset[str]


@dataclass(frozen=True, slots=True)
class CanonicalReferenceRead:
    ref: str
    tool_name: str
    arguments: dict[str, str]


_MISSION_INPUT_REF = re.compile(r"^mission-input:[0-9a-f]{64}$")
_PRISM_FILE_REF = re.compile(
    r"^prism-file:[A-Za-z0-9][A-Za-z0-9._:-]{0,2047}$"
)
_ARTIFACT_CANDIDATE_REF = re.compile(r"^artifact-candidate:[0-9a-f]{64}$")
_ACADEMIC_VISUAL_REF = re.compile(
    r"^academic-visual:[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$"
)
_SANDBOX_ARTIFACT_REF = re.compile(r"^sandbox-artifact:[0-9a-f]{64}$")
_READABLE_SANDBOX_MIME_PREFIXES = (
    "text/",
    "application/json",
    "application/xml",
    "application/x-yaml",
)
_ARTIFACT_CLAIM_LABEL = re.compile(
    r"(?<![A-Za-z0-9_])(?:C|D)[1-9][0-9]{0,2}(?![A-Za-z0-9_])"
)
_AI_DISCLOSURE_HEADING = re.compile(
    r"(?im)^#{1,6}[ \t]*(?:(?:AI|人工智能)[^\r\n]*(?:披露|声明)|"
    r"(?:披露|声明)[^\r\n]*(?:AI|人工智能))[^\r\n]*$"
)


def canonical_reference_read(ref: str) -> CanonicalReferenceRead | None:
    """Map a bounded canonical ref to its one authorized hydration tool shape."""
    if _MISSION_INPUT_REF.fullmatch(ref):
        return CanonicalReferenceRead(
            ref=ref,
            tool_name="workspace.read_input",
            arguments={"input_ref": ref},
        )
    if _PRISM_FILE_REF.fullmatch(ref):
        return CanonicalReferenceRead(
            ref=ref,
            tool_name="workspace.read_document",
            arguments={"document_ref": ref},
        )
    if _ARTIFACT_CANDIDATE_REF.fullmatch(ref) or _ACADEMIC_VISUAL_REF.fullmatch(ref):
        return CanonicalReferenceRead(
            ref=ref,
            tool_name="artifact.read_candidate",
            arguments={"candidate_ref": ref},
        )
    if _SANDBOX_ARTIFACT_REF.fullmatch(ref):
        return CanonicalReferenceRead(
            ref=ref,
            tool_name="sandbox.read_artifact",
            arguments={"artifact_ref": ref},
        )
    return None


def is_internal_candidate_reference(ref: str) -> bool:
    """Return whether a ref is an immutable candidate readable by the artifact tool."""

    read = canonical_reference_read(ref)
    return read is not None and read.tool_name == "artifact.read_candidate"


def canonical_reference_read_for_receipt(
    ref: str,
    *,
    kind: str,
    metadata: dict[str, object],
) -> CanonicalReferenceRead | None:
    """Return a reader only when the verified receipt can satisfy it."""

    read = canonical_reference_read(ref)
    if read is None:
        return None
    if read.tool_name == "artifact.read_candidate":
        expected_kind = (
            "academic_visual_candidate"
            if _ACADEMIC_VISUAL_REF.fullmatch(ref)
            else "artifact_candidate"
        )
        return read if kind == expected_kind else None
    if read.tool_name != "sandbox.read_artifact":
        return read
    if kind != "sandbox_artifact_manifest":
        return None
    mime_type = str(metadata.get("kind") or "")
    if not mime_type.startswith(_READABLE_SANDBOX_MIME_PREFIXES):
        return None
    size_bytes = metadata.get("size_bytes")
    if not isinstance(size_bytes, int) or size_bytes <= 0 or size_bytes > 16_777_216:
        return None
    return read


def evidence_authority_index(
    items: list[MissionItemPayload],
) -> dict[str, EvidenceAuthority]:
    """Return the only evidence refs and semantic surfaces quality may cite."""
    index: dict[str, EvidenceAuthority] = {}
    for item in sorted(items, key=lambda value: value.seq):
        if item.phase.value != "completed" or item.item_type not in {
            "evidence",
            "artifact",
            "output",
        }:
            continue
        payload = item.payload_json
        if payload.get("verified") is not True:
            continue
        evidence_id = str(payload.get("reference_id") or "").strip()
        kind = str(payload.get("kind") or "").strip()
        metadata = payload.get("metadata")
        if not evidence_id or not kind or not isinstance(metadata, dict):
            continue
        surfaces = allowed_evidence_surfaces(kind, metadata)
        if not surfaces:
            continue
        supported_claims = {
            str(value)
            for value in metadata.get("supported_claim_refs") or ()
            if str(value).strip()
        }
        if kind == "artifact_candidate":
            supported_claims.update(_artifact_candidate_aligned_claims(metadata))
        index[evidence_id] = EvidenceAuthority(
            evidence_id=evidence_id,
            stage_id=item.stage_id,
            kind=kind,
            title=str(payload.get("title") or item.summary or "")[:300],
            source_ref=str(payload.get("uri") or item.payload_ref or "").strip()
            or None,
            operation_id=str(
                payload.get("receipt_operation_key") or item.operation_id or ""
            ),
            surfaces=surfaces,
            supported_claims=frozenset(supported_claims),
        )
    return index


def allowed_evidence_surfaces(
    kind: str,
    metadata: dict[str, Any],
) -> frozenset[str]:
    """Resolve typed evidence surfaces once for prompt projection and enforcement."""
    explicit = frozenset(
        str(item)
        for item in metadata.get("surfaces") or ()
        if str(item) in KNOWN_RESEARCH_SURFACES
    )
    if kind == "artifact_candidate":
        surfaces = set(explicit)
        preview_text = str(metadata.get("preview_text") or "").strip()
        source_refs = {
            str(value)
            for value in metadata.get("source_refs") or ()
            if str(value).strip()
        }
        cited_source_refs = {ref for ref in source_refs if ref in preview_text}
        claims = _artifact_candidate_aligned_claims(metadata)
        if preview_text:
            surfaces.add("writing")
        if preview_text and claims and cited_source_refs:
            surfaces.add("claim_evidence_alignment")
        if _has_substantive_ai_disclosure(preview_text):
            surfaces.add("ai_use_disclosure")
        return frozenset(surfaces)
    if kind == "academic_visual_candidate":
        surfaces = set(explicit)
        candidate = metadata.get("candidate")
        if isinstance(candidate, dict):
            quality_receipt = candidate.get("quality_receipt")
            has_verified_pixels = (
                isinstance(quality_receipt, dict)
                and quality_receipt.get("decoded") is True
                and quality_receipt.get("nonblank") is True
            )
            if (
                has_verified_pixels
                and candidate.get("source_code_hash")
                and candidate.get("dataset_refs")
                and candidate.get("source_refs")
            ):
                surfaces.add("figure_data_consistency")
        return frozenset(surfaces)
    if kind == "web_source":
        surfaces = set(explicit) | {
            "literature",
            "citation_strength",
            "paper_relevance",
        }
        if metadata.get("supported_claim_refs"):
            surfaces.add("claim_evidence_alignment")
        return frozenset(surfaces)
    if explicit:
        return explicit
    if kind in {"sandbox_dataset_manifest", "sandbox_artifact_manifest"}:
        return frozenset(
            {
                "experiment",
                "experiment_interpretation",
                "statistical_robustness",
                "experiment_reproducibility",
                "figure_data_consistency",
            }
        )
    if kind in {"workspace_asset", "source_code", "document"}:
        return frozenset(
            {"source_provenance", "screenshot_provenance", "workflow_trace"}
        )
    if kind in {
        "mission_input_text",
        "workspace_asset_text",
        "source_code_listing",
    }:
        return frozenset({"source_provenance"})
    return frozenset()


def _artifact_candidate_aligned_claims(
    metadata: dict[str, Any],
) -> frozenset[str]:
    preview_text = str(metadata.get("preview_text") or "")
    source_refs = {
        str(value)
        for value in metadata.get("source_refs") or ()
        if str(value).strip()
    }
    if not preview_text or not source_refs:
        return frozenset()
    aligned: set[str] = set()
    for block in re.split(r"\r?\n[ \t]*\r?\n", preview_text):
        if any(ref in block for ref in source_refs):
            aligned.update(_ARTIFACT_CLAIM_LABEL.findall(block))
    return frozenset(aligned)


def _has_substantive_ai_disclosure(preview_text: str) -> bool:
    heading = _AI_DISCLOSURE_HEADING.search(preview_text)
    if heading is None:
        return False
    section = preview_text[heading.end() :]
    next_heading = re.search(r"(?m)^#{1,6}[ \t]+", section)
    body = section[: next_heading.start()] if next_heading is not None else section
    return len("".join(body.split())) >= 20


__all__ = [
    "CanonicalReferenceRead",
    "EvidenceAuthority",
    "allowed_evidence_surfaces",
    "canonical_reference_read",
    "canonical_reference_read_for_receipt",
    "evidence_authority_index",
    "is_internal_candidate_reference",
]
