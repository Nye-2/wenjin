"""LaTeX adapter metadata helpers for Prism."""

from __future__ import annotations

from typing import Any


def build_latex_adapter_metadata(
    *,
    latex_project_id: str,
    main_file: str = "main.tex",
    file_order: dict[str, list[str]] | None = None,
    llm_config: dict[str, Any] | None = None,
    template_id: str | None = None,
) -> dict[str, Any]:
    """Build canonical LaTeX project fields for Prism adapter metadata."""

    metadata = {}
    if isinstance(llm_config, dict):
        raw_metadata = llm_config.get("metadata")
        if isinstance(raw_metadata, dict):
            metadata.update(raw_metadata)
    return {
        "latex_project_id": latex_project_id,
        "main_file": main_file,
        "template_id": template_id,
        "file_order": dict(file_order or {}),
        "source_metadata": metadata,
    }
