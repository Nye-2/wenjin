"""Workspace-owned WenjinPrism lookup and projection service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.latex import LatexProjectAttachWorkspacePayload
from src.dataservice_client.contracts.prism import PrismPrimaryProjectPayload
from src.dataservice_client.provider import dataservice_client
from src.services.prism_review_projection import prism_review_item_projection
from src.services.workspace_activity_contracts import (
    build_prism_review_activity_item,
    serialize_activity_item,
)
from src.services.workspace_latex_projects import WorkspaceLatexProjectService

PRIMARY_MANUSCRIPT_ROLE = "primary_manuscript"
PENDING_REVIEW_STATUSES = ("pending", "accepted")
APPLIED_REVIEW_STATUSES = ("applied",)


def _metadata_from_project(project: Any) -> dict[str, Any]:
    llm_config = project.llm_config if isinstance(project.llm_config, dict) else {}
    metadata = llm_config.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def _build_latex_adapter_metadata(
    *,
    latex_project_id: str,
    main_file: str = "main.tex",
    file_order: dict[str, Any] | None = None,
    llm_config: dict[str, Any] | None = None,
    template_id: str | None = None,
) -> dict[str, Any]:
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
        "legacy_metadata": metadata,
    }


def _memory_payload(item: Any) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "workspace_id": str(item.workspace_id),
        "category": str(item.category),
        "content": str(item.content),
        "confidence": float(item.confidence or 0),
        "reference_count": int(item.reference_count or 0),
        "last_referenced_at": _isoformat(item.last_referenced_at),
        "created_at": _isoformat(item.created_at),
    }


def _run_history_payload(item: Any) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "workspace_id": str(item.workspace_id or ""),
        "execution_id": str(getattr(item, "execution_id", None) or item.id),
        "capability_id": str(item.capability_id or ""),
        "title": str(getattr(item, "title", None) or getattr(item, "display_name", None) or item.execution_type),
        "summary": str(getattr(item, "summary", None) or getattr(item, "result_summary", None) or ""),
        "status": str(item.status),
        "artifact_count": int(getattr(item, "artifact_count", None) or len(getattr(item, "artifact_ids", []) or [])),
        "duration_seconds": int(getattr(item, "duration_seconds", None) or 0),
        "created_at": _isoformat(item.created_at),
    }


def _json_object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _model_payload(item: Any) -> dict[str, Any]:
    dump = getattr(item, "model_dump", None)
    if callable(dump):
        return dump(mode="json")
    if isinstance(item, dict):
        return dict(item)
    return {
        key: value
        for key, value in vars(item).items()
        if not key.startswith("_")
    }


def _review_target_ref(item: Any) -> dict[str, Any]:
    return _json_object(item.target_ref_json)


def _review_payload(item: Any) -> dict[str, Any]:
    payload = _json_object(item.payload_json)
    preview = _json_object(item.preview_json)
    result = _json_object(item.result_json)
    merged = {**payload}
    for key in (
        "pending_content",
        "pending_hash",
        "current_hash",
        "previous_content",
        "previous_hash",
        "applied_hash",
        "revert_signature",
    ):
        if key in preview:
            merged[key] = preview[key]
        if key in result:
            merged[key] = result[key]
    return merged


def _review_file_change_payload(item: Any) -> dict[str, Any]:
    target_ref = _review_target_ref(item)
    payload = _review_payload(item)
    path = str(
        target_ref.get("file_path")
        or target_ref.get("path")
        or payload.get("path")
        or "",
    ).strip()
    logical_key = str(
        target_ref.get("logical_key")
        or payload.get("logical_key")
        or item.source_item_id
        or item.id
    )
    result = {
        "id": str(item.id),
        "logical_key": logical_key,
        "source_type": "review_batch",
        "source_execution_id": payload.get("source_execution_id"),
        "source_task_id": payload.get("source_task_id"),
        "target_kind": str(item.target_kind or ""),
        "path": path,
        "title": str(item.title or path or logical_key),
        "reason": str(item.summary or payload.get("reason") or ""),
        "status": str(item.status),
        "created_at": _isoformat(item.created_at),
        "updated_at": _isoformat(item.updated_at),
        "applied_at": _isoformat(item.applied_at),
    }
    for key, value in payload.items():
        if key not in result and value is not None:
            result[key] = value
    return result


def _prism_review_activity_payload(item: Any) -> dict[str, Any]:
    occurred_at = item.applied_at or item.updated_at or item.created_at
    target_ref = _review_target_ref(item)
    payload = _review_payload(item)
    logical_key = str(
        target_ref.get("logical_key")
        or payload.get("logical_key")
        or item.source_item_id
        or item.id
    )
    target_file_path = target_ref.get("file_path") or target_ref.get("path") or payload.get("path")
    return serialize_activity_item(
        build_prism_review_activity_item(
            review_item_id=str(item.id),
            workspace_id=str(item.workspace_id),
            latex_project_id=str(
                target_ref.get("latex_project_id") or target_ref.get("project_id") or ""
            ),
            logical_key=logical_key,
            title=item.title,
            summary=item.summary,
            status=item.status,
            source_execution_id=payload.get("source_execution_id"),
            source_task_id=payload.get("source_task_id"),
            target_kind=item.target_kind,
            target_file_path=str(target_file_path) if target_file_path else None,
            target_room=target_ref.get("room"),
            target_item_id=target_ref.get("item_id"),
            occurred_at=occurred_at,
            created_at=item.created_at,
            updated_at=item.updated_at,
            applied_at=item.applied_at,
        )
    )


def _recent_activity_sort_key(item: dict[str, Any]) -> str:
    return str(item.get("occurred_at") or item.get("created_at") or "")


def _review_item_launch_payload(item: dict[str, Any]) -> dict[str, Any]:
    target = item.get("target") if isinstance(item.get("target"), dict) else {}
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    return {
        "id": str(item.get("id") or ""),
        "logical_key": str(item.get("logical_key") or ""),
        "status": str(item.get("status") or ""),
        "title": str(item.get("title") or ""),
        "summary": item.get("summary"),
        "target_file_path": target.get("file_path"),
        "source_execution_id": source.get("execution_id"),
        "source_task_id": source.get("task_id"),
    }


def _source_link_launch_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "review_item_id": item.get("review_item_id"),
        "source_type": str(item.get("source_type") or ""),
        "source_id": str(item.get("source_id") or ""),
        "file_path": str(item.get("file_path") or ""),
        "section_key": item.get("section_key"),
        "citation_key": item.get("citation_key"),
        "usage": str(item.get("usage") or ""),
    }


def _provenance_source_link_payload(item: Any, *, latex_project_id: str) -> dict[str, Any]:
    target_ref = _json_object(getattr(item, "target_ref_json", None))
    metadata = _json_object(getattr(item, "metadata_json", None))
    logical_key = str(target_ref.get("logical_key") or metadata.get("section_key") or "")
    file_path = str(target_ref.get("file_path") or metadata.get("file_path") or "")
    return {
        "id": str(getattr(item, "id", "")),
        "workspace_id": str(getattr(item, "workspace_id", "")),
        "latex_project_id": latex_project_id,
        "review_item_id": getattr(item, "review_item_id", None),
        "source_type": "source",
        "source_id": str(getattr(item, "source_id", "") or ""),
        "file_path": file_path,
        "section_key": logical_key,
        "quote": getattr(item, "claim_text", None),
        "citation_key": getattr(item, "citation_key", None),
        "usage": str(getattr(item, "relation_kind", None) or metadata.get("usage") or ""),
        "created_at": _isoformat(getattr(item, "created_at", None)),
    }


def _protected_section_launch_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "file_path": str(item.get("file_path") or ""),
        "section_key": item.get("section_key"),
        "scope": str(item.get("scope") or ""),
        "reason": item.get("reason"),
    }


def _protected_scope_payload(item: Any, *, latex_project_id: str) -> dict[str, Any]:
    return {
        "id": str(getattr(item, "id", "")),
        "workspace_id": str(getattr(item, "workspace_id", "")),
        "latex_project_id": latex_project_id,
        "prism_project_id": str(getattr(item, "project_id", "")),
        "file_path": str(getattr(item, "file_path", "")),
        "section_key": str(getattr(item, "section_key", "") or ""),
        "scope": str(getattr(item, "scope", "")),
        "reason": getattr(item, "reason", None),
        "source": str(getattr(item, "source", "")),
        "updated_at": _isoformat(getattr(item, "updated_at", None)),
    }


def _build_launch_context(surface: dict[str, Any]) -> dict[str, Any]:
    review_items = [
        item
        for item in surface.get("review_items", [])
        if isinstance(item, dict) and item.get("status") in PENDING_REVIEW_STATUSES
    ]
    source_links = [
        item for item in surface.get("source_links", []) if isinstance(item, dict)
    ]
    protected_sections = [
        item
        for item in surface.get("protected_sections", [])
        if isinstance(item, dict)
    ]
    return {
        "workspace_id": str(surface.get("workspace_id") or ""),
        "latex_project_id": str(surface.get("latex_project_id") or ""),
        "url": str(surface.get("url") or ""),
        "main_file": surface.get("main_file"),
        "target_files": list(surface.get("target_files", []))[:20],
        "pending_review_items": [
            _review_item_launch_payload(item) for item in review_items[:20]
        ],
        "protected_sections": [
            _protected_section_launch_payload(item) for item in protected_sections[:20]
        ],
        "source_links": [
            _source_link_launch_payload(item) for item in source_links[:40]
        ],
        "review_summary": dict(surface.get("review_summary") or {}),
        "context_summary": dict(surface.get("context_summary") or {}),
    }


class WorkspacePrismService:
    """Resolve the canonical Prism manuscript bound to a workspace."""

    def __init__(
        self,
        db: AsyncSession | None = None,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self.db = db
        self._dataservice = dataservice
        self.bridge = WorkspaceLatexProjectService(db, dataservice=dataservice)

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[AsyncDataServiceClient]:
        if self._dataservice is not None:
            yield self._dataservice
            return
        async with dataservice_client() as client:
            yield client

    async def get_primary_project(
        self,
        workspace_id: str,
        *,
        user_id: str,
    ) -> Any | None:
        async with self._client() as client:
            project = await client.get_prism_primary_project(workspace_id)
        if project is None or project.adapter_kind != "latex" or not project.adapter_ref_id:
            return None
        latex_project = await self._get_latex_adapter_project(project.adapter_ref_id)
        if latex_project is None or str(latex_project.user_id) != str(user_id):
            return None
        return latex_project

    async def ensure_primary_project(
        self,
        workspace_id: str,
        *,
        user_id: str,
        project_name: str,
    ) -> Any:
        project = await self.get_primary_project(workspace_id, user_id=user_id)
        if project is None:
            project = await self.bridge.ensure_workspace_project(
                workspace_id=workspace_id,
                project_name=project_name,
            )
        async with self._client() as client:
            project = await client.attach_workspace_latex_project(
                str(project.id),
                command=LatexProjectAttachWorkspacePayload(workspace_id=workspace_id),
            ) or project
        await self._ensure_prism_surface_for_latex_project(
            workspace_id=workspace_id,
            project=project,
        )
        return project

    async def get_surface_projection(
        self,
        workspace_id: str,
        *,
        user_id: str,
    ) -> dict[str, Any]:
        async with self._client() as client:
            surface = await client.get_prism_surface(workspace_id)
        if surface is None:
            raise ValueError(f"Workspace Prism not found: {workspace_id}")
        if surface.project.adapter_kind != "latex" or not surface.project.adapter_ref_id:
            raise ValueError(f"Workspace Prism adapter not available: {workspace_id}")
        project = await self._get_latex_adapter_project(surface.project.adapter_ref_id)
        if project is None or str(project.user_id) != str(user_id):
            raise ValueError(f"Workspace Prism adapter project not found: {workspace_id}")

        metadata = _metadata_from_project(project)
        pending_items = await self._list_prism_review_items(
            workspace_id=workspace_id,
            latex_project_id=str(project.id),
            statuses=PENDING_REVIEW_STATUSES,
        )
        applied_items = await self._list_prism_review_items(
            workspace_id=workspace_id,
            latex_project_id=str(project.id),
            statuses=APPLIED_REVIEW_STATUSES,
        )
        file_changes = [_review_file_change_payload(item) for item in pending_items]
        applied_file_changes = [_review_file_change_payload(item) for item in applied_items]
        review_items = [
            prism_review_item_projection(item)
            for item in [*pending_items, *applied_items]
        ]
        source_links = await self._list_source_links(
            workspace_id=workspace_id,
            latex_project_id=str(project.id),
        )
        async with self._client() as client:
            protected_scopes = await client.list_prism_protected_scopes(str(surface.project.id))
        protected_sections = [
            _protected_scope_payload(item, latex_project_id=str(project.id))
            for item in protected_scopes
        ]
        decisions = await self._list_decisions(workspace_id)
        memory_preferences = await self._list_memory_preferences(workspace_id)
        recent_activity = await self._list_recent_activity(workspace_id)
        main_file = str(project.main_file or "main.tex")
        target_files: list[str] = []
        for prism_file in surface.files:
            path = str(prism_file.path or "").strip()
            if path and path not in target_files:
                target_files.append(path)
        if main_file not in target_files:
            target_files.insert(0, main_file)
        raw_section_map = metadata.get("section_map")
        section_paths = (
            raw_section_map.values() if isinstance(raw_section_map, dict) else []
        )
        for value in section_paths:
            text = str(value).strip() if value is not None else ""
            if text and text not in target_files:
                target_files.append(text)
        for change in [*file_changes, *applied_file_changes]:
            text = str(change.get("path") or "").strip()
            if text and text not in target_files:
                target_files.append(text)

        return {
            "workspace_id": workspace_id,
            "prism_project_id": surface.project.id,
            "prism_document_id": surface.documents[0].id if surface.documents else None,
            "prism_files": [_model_payload(file) for file in surface.files],
            "latex_project_id": str(project.id),
            "surface_role": getattr(project, "surface_role", None)
            or PRIMARY_MANUSCRIPT_ROLE,
            "url": f"/workspaces/{workspace_id}/prism",
            "main_file": main_file,
            "compile_status": None,
            "has_pending_changes": bool(file_changes),
            "target_files": target_files,
            "file_changes": file_changes,
            "applied_file_changes": applied_file_changes,
            "review_items": review_items,
            "source_links": source_links,
            "protected_sections": protected_sections,
            "decisions": decisions,
            "memory_preferences": memory_preferences,
            "recent_activity": recent_activity,
            "review_summary": {
                "pending_count": len(file_changes),
                "applied_count": len(applied_file_changes),
                "source_link_count": len(source_links),
                "protected_section_count": len(protected_sections),
            },
            "context_summary": {
                "decision_count": len(decisions),
                "memory_preference_count": len(memory_preferences),
                "recent_activity_count": len(recent_activity),
            },
        }

    async def _ensure_prism_surface_for_latex_project(
        self,
        *,
        workspace_id: str,
        project: Any,
    ) -> None:
        async with self._client() as client:
            await client.ensure_prism_primary_project(
                workspace_id,
                PrismPrimaryProjectPayload(
                    workspace_id=workspace_id,
                    title=str(project.name or "Workspace Manuscript"),
                    adapter_kind="latex",
                    adapter_ref_id=str(project.id),
                    main_file=str(project.main_file or "main.tex"),
                    adapter_metadata_json=_build_latex_adapter_metadata(
                        latex_project_id=str(project.id),
                        main_file=str(project.main_file or "main.tex"),
                        file_order=project.file_order if isinstance(project.file_order, dict) else {},
                        llm_config=project.llm_config if isinstance(project.llm_config, dict) else {},
                        template_id=project.template_id,
                    ),
                ),
            )

    async def _get_latex_adapter_project(self, project_id: str) -> Any | None:
        return await self.bridge.get_project_by_id(project_id)

    async def _list_prism_review_items(
        self,
        *,
        workspace_id: str,
        latex_project_id: str,
        statuses: tuple[str, ...],
        limit: int = 200,
    ) -> list[ReviewItemProjection]:
        async with self._client() as client:
            items = await client.list_review_items(
                workspace_id=workspace_id,
                target_domain="prism",
                target_kind="prism_file_change",
                status=list(statuses),
                limit=limit,
            )
        return [
            item
            for item in items
            if str(_review_target_ref(item).get("latex_project_id") or "") == latex_project_id
        ]

    async def _list_source_links(
        self,
        *,
        workspace_id: str,
        latex_project_id: str,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        async with self._client() as client:
            links = await client.list_provenance_links(
                workspace_id=workspace_id,
                target_domain="prism",
                target_kind="prism_file_change",
                relation_kind="cited",
                limit=limit,
            )
        return [
            _provenance_source_link_payload(item, latex_project_id=latex_project_id)
            for item in links
            if str(_json_object(item.target_ref_json).get("latex_project_id") or "")
            == latex_project_id
        ]

    async def get_launch_context_projection(
        self,
        workspace_id: str,
        *,
        user_id: str,
    ) -> dict[str, Any]:
        surface = await self.get_surface_projection(workspace_id, user_id=user_id)
        return _build_launch_context(surface)

    async def _list_decisions(self, workspace_id: str) -> list[dict[str, Any]]:
        async with self._client() as client:
            decisions = await client.list_room_decisions(workspace_id)
        return [_model_payload(item) for item in decisions[:5]]

    async def _list_memory_preferences(self, workspace_id: str) -> list[dict[str, Any]]:
        async with self._client() as client:
            facts = await client.list_room_memory_facts(workspace_id=workspace_id, limit=5)
        return [_memory_payload(item) for item in facts]

    async def _list_recent_activity(self, workspace_id: str) -> list[dict[str, Any]]:
        async with self._client() as client:
            run_history = await client.list_executions(workspace_id=workspace_id, limit=5)
            review_records = await client.list_review_items(
                workspace_id=workspace_id,
                target_domain="prism",
                limit=5,
            )
        run_history_items = [_run_history_payload(item) for item in run_history]
        review_items = [
            _prism_review_activity_payload(item)
            for item in review_records
        ]
        items = [*run_history_items, *review_items]
        items.sort(key=_recent_activity_sort_key, reverse=True)
        return items[:5]

    async def get_binding_integrity_report(
        self,
        *,
        user_id: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Report workspaces with missing or duplicate primary Prism projects."""

        async with self._client() as client:
            return await client.get_latex_binding_integrity_report(user_id=user_id)
