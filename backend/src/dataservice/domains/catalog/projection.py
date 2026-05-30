"""Catalog projection helpers."""

from __future__ import annotations

from typing import Any

from src.database.models.agent_template import AgentTemplate
from src.database.models.capability_skill import CapabilitySkill
from src.dataservice.domains.catalog.contracts import (
    AdminLogRecord,
    AgentTemplateRecord,
    CapabilityDefinitionRecord,
    CapabilitySkillRecord,
)
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
    if not isinstance(skill_json, dict) or len(skill_json) == 0:
        skill_id = getattr(skill, "id", "<unknown>")
        raise ValueError(
            f"Capability skill {skill_id} is missing canonical skill_json"
        )
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
        skill_json=dict(skill_json),
        checksum=getattr(skill, "checksum", None),
        source_path=getattr(skill, "source_path", None),
    )


def agent_template_to_record(template: AgentTemplate) -> AgentTemplateRecord:
    """Project a canonical agent template row."""
    return AgentTemplateRecord(
        id=template.id,
        schema_version=str(template.schema_version or "agent_template.v1"),
        enabled=bool(template.enabled),
        display_role=template.display_role,
        category=template.category,
        description=template.description or "",
        persona_prompt=template.persona_prompt or "",
        default_skills=list(template.default_skills or []),
        tool_affinity=dict(template.tool_affinity or {}),
        risk_profile=dict(template.risk_profile or {}),
        output_contracts=list(template.output_contracts or []),
        quality_expectations=list(template.quality_expectations or []),
        runtime_defaults=dict(template.runtime_defaults or {}),
        template_json=dict(template.template_json or {}),
        checksum=template.checksum,
        source_path=template.source_path,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


def admin_log_to_record(
    log: Any,
    *,
    admin_email: str | None = None,
    admin_name: str | None = None,
    target_email: str | None = None,
    target_name: str | None = None,
) -> AdminLogRecord:
    """Project an admin log row plus optional joined user metadata."""
    action = getattr(log, "action", "")
    action_value = action.value if hasattr(action, "value") else str(action)
    target_user_id = getattr(log, "target_user_id", None)
    return AdminLogRecord(
        id=str(log.id) if getattr(log, "id", None) is not None else None,
        action=action_value,
        target_type=str(getattr(log, "target_type", None) or "user"),
        target_user_id=target_user_id,
        details=dict(getattr(log, "details", None) or {}),
        ip_address=getattr(log, "ip_address", None),
        created_at=getattr(log, "created_at", None),
        admin={
            "id": str(getattr(log, "admin_id", "")),
            "email": admin_email,
            "name": admin_name,
        },
        target_user=(
            {
                "id": str(target_user_id),
                "email": target_email,
                "name": target_name,
            }
            if target_user_id
            else None
        ),
    )
