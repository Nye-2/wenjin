"""Shared helpers for staging Prism file-change review items."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from src.agents.lead_agent.v2.output_mapping import resolve_output_mapping_value
from src.dataservice_client.contracts.prism_review import PrismFileChangeUpsertPayload
from src.services.prism_file_content import normalize_prism_file_change_content


def ensure_latex_bibliography_call(content: str) -> str:
    """Ensure a complete LaTeX manuscript points at Prism's Library BibTeX file."""
    if "\\bibliography{" in content or "\\printbibliography" in content:
        return content
    insertion = "\n\\bibliographystyle{plain}\n\\bibliography{refs}\n"
    if "\\end{document}" in content:
        return content.replace("\\end{document}", f"{insertion}\\end{{document}}", 1)
    return f"{content.rstrip()}\n{insertion}\n"


def build_prism_file_change_command(
    decl: dict[str, Any],
    output: dict[str, Any],
    *,
    workspace_id: str,
    latex_project_id: str,
    task_name: str,
    execution_id: str,
    default_path: str,
    require_bibliography: bool = False,
) -> PrismFileChangeUpsertPayload | None:
    mapping = decl.get("mapping") if isinstance(decl.get("mapping"), dict) else {}
    path_value = resolve_output_mapping_value(
        str(mapping.get("path") or default_path),
        output,
    )
    path = str(path_value or default_path).strip() or default_path
    content_format_value = (
        resolve_output_mapping_value(str(mapping["content_format"]), output)
        if "content_format" in mapping
        else None
    )
    content_format = (
        str(content_format_value).strip()
        if content_format_value is not None and str(content_format_value).strip()
        else None
    )
    pending_content = resolve_output_mapping_value(
        str(
            mapping.get("pending_content")
            or mapping.get("content")
            or "{{output.text}}"
        ),
        output,
    )
    if not isinstance(pending_content, str) or not pending_content.strip():
        return None
    pending_content = normalize_prism_file_change_content(
        pending_content,
        path=path,
        content_format=content_format,
    )
    if path == "main.tex" and require_bibliography:
        pending_content = ensure_latex_bibliography_call(pending_content)
    logical_key_value = resolve_output_mapping_value(
        str(mapping.get("logical_key") or f"project:{path}"),
        output,
    )
    logical_key = str(logical_key_value or f"project:{path}").strip()
    reason_value = resolve_output_mapping_value(
        str(mapping.get("reason") or "feature_proposal"),
        output,
    )
    reason = str(reason_value or "feature_proposal").strip() or "feature_proposal"
    current_hash_value = (
        resolve_output_mapping_value(str(mapping["current_hash"]), output)
        if "current_hash" in mapping
        else None
    )
    current_hash = (
        str(current_hash_value).strip()
        if current_hash_value is not None and str(current_hash_value).strip()
        else None
    )

    return PrismFileChangeUpsertPayload(
        workspace_id=workspace_id,
        latex_project_id=latex_project_id,
        logical_key=logical_key,
        path=path,
        reason=reason,
        pending_content=pending_content,
        pending_hash=sha256(pending_content.encode("utf-8")).hexdigest(),
        current_hash=current_hash,
        source_execution_id=execution_id,
        source_task_id=task_name,
    )
