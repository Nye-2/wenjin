"""Reference Library navigation tools for workspace-scoped retrieval."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.database import get_db_session
from src.dataservice.provenance_api import ProvenanceDataService, ProvenanceLinkCreateCommand
from src.dataservice.source_api import SourceDataService

logger = logging.getLogger(__name__)


class ListReferenceLibraryInput(BaseModel):
    """Input for listing workspace Reference Library outline."""

    workspace_id: str | None = Field(
        default=None,
        description="Runtime-injected workspace id; leave empty when calling as an agent.",
    )


class SearchReferenceTextUnitsInput(BaseModel):
    """Input for searching indexed text units inside a workspace Reference Library."""

    workspace_id: str | None = Field(
        default=None,
        description="Runtime-injected workspace id; leave empty when calling as an agent.",
    )
    query: str = Field(description="Search query for section title/content")
    limit: int = Field(default=8, ge=1, le=20, description="Maximum matches")


class ReadReferenceOutlineNodeInput(BaseModel):
    """Input for reading one reference section."""

    reference_id: str = Field(description="Reference id")
    section_path: str | None = Field(
        default=None,
        description="Section path such as 1 or 2.3.1",
    )
    section_title: str | None = Field(
        default=None,
        description="Section title fuzzy match when path is unknown",
    )
    workspace_id: str | None = Field(
        default=None,
        description="Runtime-injected workspace id; leave empty when calling as an agent.",
    )


def _runtime_workspace_id(config: RunnableConfig | None) -> str | None:
    configurable = config.get("configurable", {}) if isinstance(config, Mapping) else {}
    if not isinstance(configurable, Mapping):
        return None
    workspace_id = str(configurable.get("workspace_id") or "").strip()
    return workspace_id or None


def _runtime_value(config: RunnableConfig | None, key: str) -> str | None:
    configurable = config.get("configurable", {}) if isinstance(config, Mapping) else {}
    if not isinstance(configurable, Mapping):
        return None
    value = str(configurable.get(key) or "").strip()
    return value or None


def _resolve_workspace_scope(
    workspace_id: str | None,
    config: RunnableConfig | None,
) -> tuple[str | None, dict[str, Any] | None]:
    """Resolve workspace scope with runtime identity as the authority."""
    requested_workspace_id = str(workspace_id or "").strip() or None
    runtime_workspace_id = _runtime_workspace_id(config)
    if runtime_workspace_id is None:
        return None, {
            "error": "runtime_context_missing",
            "message": "Reference Library tools require a runtime workspace scope.",
        }
    if requested_workspace_id and requested_workspace_id != runtime_workspace_id:
        return None, {
            "error": "workspace_scope_violation",
            "message": "Reference Library tools are workspace-scoped and cannot read a different workspace.",
            "runtime_workspace_id": runtime_workspace_id,
            "requested_workspace_id": requested_workspace_id,
        }
    return runtime_workspace_id, None


async def _record_reference_access(
    *,
    db: Any,
    workspace_id: str,
    reference_id: str,
    section: dict[str, Any],
    config: RunnableConfig | None,
) -> None:
    """Best-effort evidence-access audit for outline/page navigation."""
    try:
        raw_units = section.get("units")
        units = raw_units if isinstance(raw_units, list) else []
        first_unit = next((item for item in units if isinstance(item, dict)), {})
        await ProvenanceDataService(db).create_link(
            ProvenanceLinkCreateCommand(
                workspace_id=workspace_id,
                source_id=reference_id,
                target_domain="agent_tool",
                target_kind="source_section_access",
                target_id=str(section.get("node_id") or "").strip() or None,
                target_ref_json={
                    "section_path": section.get("section_path"),
                    "outline_node_id": str(section.get("node_id") or "").strip() or None,
                    "text_unit_id": str(first_unit.get("id") or "").strip() or None,
                    "skill_id": _runtime_value(config, "skill_id"),
                },
                relation_kind="used_as_context",
                claim_text=str(section.get("title") or "").strip() or None,
                generated_text=str(section.get("content") or "")[:4000],
                execution_id=_runtime_value(config, "execution_id"),
                metadata_json={
                    "task_id": _runtime_value(config, "task_id"),
                    "artifact_id": _runtime_value(config, "artifact_id"),
                    "accepted_status": "pending",
                },
            )
        )
    except Exception:
        logger.debug(
            "Failed to record Reference Library access for workspace=%s reference=%s",
            workspace_id,
            reference_id,
            exc_info=True,
        )


@tool("list_reference_library", args_schema=ListReferenceLibraryInput)
async def list_reference_library_tool(
    workspace_id: str | None = None,
    config: RunnableConfig = None,  # type: ignore[assignment]
) -> str:
    """List outline summary for all references in a workspace."""
    resolved_workspace_id, error = _resolve_workspace_scope(workspace_id, config)
    if error is not None:
        return json.dumps(error, ensure_ascii=False)
    assert resolved_workspace_id is not None
    async with get_db_session() as db:
        summary = await SourceDataService(db, autocommit=False).get_workspace_toc_summary(
            resolved_workspace_id
        )
    return summary or "该工作区暂无可用参考文献目录。"


@tool("search_reference_text_units", args_schema=SearchReferenceTextUnitsInput)
async def search_reference_text_units_tool(
    query: str,
    limit: int = 8,
    workspace_id: str | None = None,
    config: RunnableConfig = None,  # type: ignore[assignment]
) -> str:
    """Search reference sections by title/content in one workspace."""
    resolved_workspace_id, error = _resolve_workspace_scope(workspace_id, config)
    if error is not None:
        return json.dumps(error, ensure_ascii=False)
    assert resolved_workspace_id is not None
    async with get_db_session() as db:
        records = await SourceDataService(db, autocommit=False).search_workspace_sections(
            resolved_workspace_id,
            query,
            limit=limit,
        )
    return json.dumps(
        {
            "workspace_id": resolved_workspace_id,
            "query": query,
            "count": len(records),
            "results": records,
        },
        ensure_ascii=False,
    )


@tool(
    "read_reference_outline_node",
    args_schema=ReadReferenceOutlineNodeInput,
)
async def read_reference_outline_node_tool(
    reference_id: str,
    section_path: str | None = None,
    section_title: str | None = None,
    workspace_id: str | None = None,
    config: RunnableConfig = None,  # type: ignore[assignment]
) -> str:
    """Read one reference section by section_path or section_title."""
    resolved_workspace_id, error = _resolve_workspace_scope(workspace_id, config)
    if error is not None:
        if error.get("error") == "workspace_scope_violation":
            return json.dumps(error, ensure_ascii=False)
        return "缺少 workspace runtime context，无法读取参考文献。"
    normalized_path = str(section_path or "").strip()
    normalized_title = str(section_title or "").strip()
    if not normalized_path and not normalized_title:
        return "请至少提供 section_path 或 section_title。"

    async with get_db_session() as db:
        source_service = SourceDataService(db, autocommit=False)
        if normalized_path:
            section = await source_service.get_source_section(
                source_id=reference_id,
                section_path=normalized_path,
                workspace_id=resolved_workspace_id,
            )
        else:
            section = await source_service.get_source_section_by_title(
                source_id=reference_id,
                section_title=normalized_title,
                workspace_id=resolved_workspace_id,
            )
        if section:
            await _record_reference_access(
                db=db,
                workspace_id=cast(str, resolved_workspace_id),
                reference_id=reference_id,
                section=section,
                config=config,
            )

    if not section:
        return "未找到对应章节。"

    title = str(section.get("title") or normalized_path or normalized_title)
    content = str(section.get("content") or "")
    if not content.strip():
        return f"章节《{title}》暂无可读取内容。"
    return f"## {title}\n\n{content}"
