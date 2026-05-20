"""Catalog projection helpers."""

from __future__ import annotations

from typing import Any

from src.database.models.capability_skill import CapabilitySkill
from src.dataservice.domains.catalog.contracts import CapabilityDefinitionRecord, CapabilitySkillRecord
from src.dataservice.domains.catalog.models import CapabilityDefinition


def capability_to_record(capability: CapabilityDefinition) -> CapabilityDefinitionRecord:
    """Project a canonical capability row."""
    return CapabilityDefinitionRecord(
        id=capability.id,
        workspace_type=str(getattr(capability, "workspace_type", None) or ""),
        schema_version=str(getattr(capability, "schema_version", None) or "capability.v2"),
        enabled=bool(getattr(capability, "enabled", True)),
        tier=str(getattr(capability, "tier", None) or "primary"),
        entry_surface=str(getattr(capability, "entry_surface", None) or "workbench"),
        display_name=capability.display_name,
        description=str(getattr(capability, "description", None) or ""),
        intent_description=str(getattr(capability, "intent_description", None) or ""),
        trigger_phrases=list(getattr(capability, "trigger_phrases", None) or []),
        required_decisions=list(getattr(capability, "required_decisions", None) or []),
        brief_schema=dict(getattr(capability, "brief_schema", None) or {}),
        graph_template=dict(getattr(capability, "graph_template", None) or {}),
        ui_meta=dict(getattr(capability, "ui_meta", None) or {}),
        runtime=dict(getattr(capability, "runtime", None) or {}),
        dashboard_meta=dict(getattr(capability, "dashboard_meta", None) or {}),
        definition_json=dict(getattr(capability, "definition_json", None) or {}),
        notes=getattr(capability, "notes", None),
        checksum=getattr(capability, "checksum", None),
        source_path=getattr(capability, "source_path", None),
        created_at=getattr(capability, "created_at", None),
        updated_at=getattr(capability, "updated_at", None),
    )


def skill_to_record(skill: CapabilitySkill) -> CapabilitySkillRecord:
    """Project a canonical skill row."""
    worker_type = str(getattr(skill, "worker_type", None) or skill.subagent_type)
    skill_json = getattr(skill, "skill_json", None)
    if not isinstance(skill_json, dict) or not skill_json:
        skill_json = _legacy_skill_json(skill, worker_type=worker_type)
    return CapabilitySkillRecord(
        id=skill.id,
        schema_version=str(getattr(skill, "schema_version", None) or "capability_skill.v2"),
        enabled=skill.enabled,
        display_name=skill.display_name,
        description=skill.description or "",
        worker_type=worker_type,
        subagent_type=skill.subagent_type,
        prompt=skill.prompt or "",
        allowed_tools=list(skill.allowed_tools or []),
        resources=list(skill.resources or []),
        config=dict(skill.config or {}),
        skill_json=skill_json,
        checksum=getattr(skill, "checksum", None),
        source_path=getattr(skill, "source_path", None),
    )


def _legacy_skill_json(skill: CapabilitySkill, *, worker_type: str) -> dict[str, Any]:
    return {
        "schema_version": "capability_skill.v2",
        "id": skill.id,
        "enabled": skill.enabled,
        "display_name": skill.display_name,
        "description": skill.description or "",
        "worker_type": worker_type,
        "subagent_type": skill.subagent_type,
        "prompt": skill.prompt or "",
        "allowed_tools": list(skill.allowed_tools or []),
        "resources": list(skill.resources or []),
        "config": dict(skill.config or {}),
    }
