"""Workspace feature param helpers.

New task payloads must keep business params exclusively under ``payload["params"]``.
The mirrored key list below exists only to recover params from legacy persisted
tasks that were created before the canonical nested contract was enforced.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

LEGACY_WORKSPACE_PARAM_KEYS: tuple[str, ...] = (
    "action",
    "topic",
    "query",
    "paper_id",
    "paper_title",
    "paper_abstract",
    "section_type",
    "target_words",
    "discipline",
    "abstract",
    "keywords",
    "ipc_codes",
    "time_range",
    "industry_scope",
    "objective",
    "description",
    "type",
    "fig_type",
    "chapter_title",
    "chapter_index",
    "proposal_type",
    "period_months",
    "manuscript_excerpt",
    "innovation_description",
    "technical_field",
    "application_scenario",
    "implementation_method",
    "project_name",
    "software_name",
    "version",
    "applicant_name",
    "completion_date",
    "highlights",
    "target_platforms",
    "source_modules",
    "core_modules",
    "deployment_architecture",
    "database_middleware",
    "interface_protocols",
    "deep_research_artifact_ids",
    "report_type",
    "section",
    "template",
    "compiler",
    "bibliography_style",
    "context_artifact_ids",
    "source_artifact_id",
)


def coerce_workspace_feature_params(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Recover canonical workspace feature params from new or legacy payload shapes."""
    if not isinstance(payload, Mapping):
        return {}

    params = payload.get("params")
    if isinstance(params, Mapping):
        return dict(params)

    fallback: dict[str, Any] = {}
    for key in LEGACY_WORKSPACE_PARAM_KEYS:
        value = payload.get(key)
        if value is not None:
            fallback[key] = value
    return fallback
