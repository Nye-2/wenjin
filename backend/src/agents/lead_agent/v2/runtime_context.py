"""Workspace context assembly for Lead Agent runtime."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from src.agents.contracts.task_brief import TaskBrief
from src.dataservice_client.provider import dataservice_client
from src.sandbox.workspace_layout import (
    WORKSPACE_DATASETS_MANIFEST_VIRTUAL_PATH,
    WORKSPACE_ROOT,
    is_workspace_internal_path,
    is_workspace_protected_path,
    normalize_workspace_virtual_path,
)
from src.services.workspace_prism_service import WorkspacePrismService

logger = logging.getLogger(__name__)


class RuntimeContextAssembler:
    """Builds bounded workspace context bundles for lead-agent execution."""

    @staticmethod
    def needs_library_context(capability_policy: dict[str, Any]) -> bool:
        context_policy = capability_policy.get("context_policy")
        if isinstance(context_policy, dict):
            room_reads = context_policy.get("room_reads")
            if isinstance(room_reads, dict) and "library" in room_reads:
                return True
        return RuntimeContextAssembler.requires_citation_library_context(capability_policy)

    @staticmethod
    def requires_citation_library_context(capability_policy: dict[str, Any]) -> bool:
        citation_policy = capability_policy.get("citation_policy")
        if not isinstance(citation_policy, dict):
            return False
        return (
            citation_policy.get("source_scope") == "workspace_library"
            or bool(citation_policy.get("required_for_prism_manuscript"))
        )

    @staticmethod
    def context_requirements_from_brief(brief: TaskBrief) -> dict[str, bool]:
        params = brief.brief if isinstance(brief.brief, Mapping) else {}
        raw = params.get("context_requirements")
        if not isinstance(raw, Mapping):
            return {}
        return {
            "include_manuscript_context": bool(raw.get("include_manuscript_context")),
            "include_workspace_history": bool(raw.get("include_workspace_history")),
            "include_related_documents": bool(raw.get("include_related_documents")),
            "include_sandbox_artifacts": bool(raw.get("include_sandbox_artifacts")),
            "include_pending_review_summary": bool(raw.get("include_pending_review_summary")),
        }

    @classmethod
    def needs_workspace_context(
        cls,
        capability_policy: dict[str, Any],
        context_requirements: dict[str, bool],
    ) -> bool:
        if cls.requires_citation_library_context(capability_policy):
            return True
        if context_requirements:
            return any(
                context_requirements.get(key)
                for key in (
                    "include_workspace_history",
                    "include_related_documents",
                    "include_sandbox_artifacts",
                    "include_pending_review_summary",
                )
            )
        return cls.needs_library_context(capability_policy)

    async def load_workspace_data(
        self,
        workspace_id: str,
        *,
        capability_policy: dict[str, Any] | None = None,
        context_requirements: dict[str, bool] | None = None,
        user_id: str = "",
    ) -> dict[str, Any]:
        """Load lightweight room data that subagents can safely consume."""

        normalized_workspace_id = str(workspace_id or "").strip()
        if not normalized_workspace_id:
            return {}
        capability_policy = capability_policy or {}
        context_requirements = context_requirements or {}
        if context_requirements:
            include_library = (
                bool(context_requirements.get("include_related_documents"))
                or self.requires_citation_library_context(capability_policy)
            )
        else:
            include_library = self.needs_library_context(capability_policy)
        include_workspace_history = bool(context_requirements.get("include_workspace_history"))
        include_related_documents = bool(context_requirements.get("include_related_documents"))
        include_sandbox_artifacts = bool(context_requirements.get("include_sandbox_artifacts"))
        include_pending_review_summary = bool(context_requirements.get("include_pending_review_summary"))

        workspace_data: dict[str, Any] = {}
        try:
            async with dataservice_client() as client:
                if include_pending_review_summary and user_id:
                    try:
                        manuscript_context = await WorkspacePrismService(
                            dataservice=client,
                        ).get_launch_context_projection(
                            normalized_workspace_id,
                            user_id=user_id,
                        )
                    except Exception:
                        logger.warning("Failed to load Prism manuscript context", exc_info=True)
                    else:
                        if manuscript_context:
                            workspace_data["manuscript_context"] = manuscript_context

                if include_library or include_related_documents:
                    try:
                        (
                            sources,
                            dataset_provenance,
                        ) = await self.load_source_records_for_workspace_context(
                            client,
                            workspace_id=normalized_workspace_id,
                        )
                    except Exception:
                        logger.warning("Failed to load workspace source context", exc_info=True)
                        sources = []
                        dataset_provenance = []
                    source_context = self.build_source_context(sources)
                    workspace_data.update(source_context)
                    if dataset_provenance:
                        workspace_data.setdefault("workspace_file_summary", {})[
                            "dataset_provenance"
                        ] = dataset_provenance

                if include_workspace_history:
                    workspace_data["workspace_history"] = await self.load_workspace_history_context(
                        client,
                        normalized_workspace_id,
                    )

                if include_sandbox_artifacts:
                    workspace_data["sandbox_context"] = await self.load_sandbox_context(
                        client,
                        normalized_workspace_id,
                    )
        except Exception:
            logger.warning("Failed to load workspace context", exc_info=True)
        return workspace_data

    @classmethod
    async def load_source_records_for_workspace_context(
        cls,
        client: Any,
        *,
        workspace_id: str,
    ) -> tuple[list[Any], list[dict[str, Any]]]:
        page = await client.list_sources_page(
            workspace_id=workspace_id,
            offset=0,
            limit=40,
        )
        if isinstance(page, Mapping):
            items = page.get("items")
            sources = list(items) if isinstance(items, list) else []
            return sources, cls.dataset_provenance_from_embedded_source_assets(sources)
        return [], []

    @classmethod
    def build_source_context(cls, sources: list[Any]) -> dict[str, Any]:
        citable_sources: list[dict[str, Any]] = []
        related_documents: list[dict[str, Any]] = []
        for source in sources:
            if str(cls.source_field(source, "library_status") or "") == "excluded":
                continue
            citation_key = str(cls.source_field(source, "citation_key") or "").strip()
            abstract = str(cls.source_field(source, "abstract") or "").strip()
            document = {
                "id": str(cls.source_field(source, "id") or ""),
                "citation_key": citation_key,
                "title": str(cls.source_field(source, "title") or ""),
                "authors": list(cls.source_field(source, "authors_json") or [])[:12],
                "year": cls.source_field(source, "year"),
                "venue": cls.source_field(source, "venue"),
                "doi": cls.source_field(source, "doi"),
                "url": cls.source_field(source, "url"),
                "library_status": str(cls.source_field(source, "library_status") or ""),
                "evidence_level": str(cls.source_field(source, "evidence_level") or ""),
                "abstract_excerpt": abstract[:500],
            }
            related_documents.append(document)
            if not citation_key:
                continue
            citable_sources.append(document)

        context: dict[str, Any] = {}
        if related_documents:
            context["related_documents"] = related_documents[:30]

        if citable_sources:
            context["library_context"] = {
                "refs_bib_file": "refs.bib",
                "bibliography_command": "\\bibliography{refs}",
                "citation_command": "\\cite{citation_key}",
                "citation_keys": [
                    item["citation_key"] for item in citable_sources
                ],
                "citable_sources": citable_sources[:30],
                "instruction": (
                    "Use these Library sources as the citation source of truth. "
                    "When drafting LaTeX, cite only these citation_key values with "
                    "\\cite{...}; do not invent citation keys; include "
                    "\\bibliographystyle{plain} and \\bibliography{refs} before "
                    "\\end{document}."
                ),
            }
        return context

    @classmethod
    def dataset_provenance_from_embedded_source_assets(
        cls,
        sources: list[Any],
    ) -> list[dict[str, Any]]:
        dataset_refs: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for source in sources[:40]:
            if str(cls.source_field(source, "library_status") or "") == "excluded":
                continue
            assets = cls.source_field(source, "assets")
            if not isinstance(assets, list):
                continue
            for asset in assets:
                ref = cls.dataset_provenance_ref_from_source_asset(source, asset)
                if not ref:
                    continue
                path = str(ref.get("path") or "")
                if path in seen_paths:
                    continue
                seen_paths.add(path)
                dataset_refs.append(ref)
                if len(dataset_refs) >= 20:
                    return dataset_refs
        return dataset_refs

    @classmethod
    def dataset_provenance_ref_from_source_asset(
        cls,
        source: Any,
        asset: Any,
    ) -> dict[str, Any] | None:
        if not isinstance(asset, Mapping):
            return None
        path = cls.dataset_asset_workspace_path(asset)
        if path is None:
            return None
        metadata = asset.get("metadata") or asset.get("metadata_json")
        metadata = metadata if isinstance(metadata, Mapping) else {}
        ref: dict[str, Any] = {
            "path": path,
            "source_kind": "source_asset",
            "source_id": str(cls.source_field(source, "id") or ""),
            "name": str(asset.get("name") or PurePosixPath(path).name),
        }
        title = str(asset.get("title") or cls.source_field(source, "title") or "").strip()
        if title:
            ref["title"] = title[:500]
        abstract = str(cls.source_field(source, "abstract") or "").strip()
        if abstract:
            ref["description"] = abstract[:500]
        field_map = (
            ("asset_type", "format"),
            ("content_type", "mime_type"),
            ("mime_type", "mime_type"),
            ("file_size", "size_bytes"),
            ("size_bytes", "size_bytes"),
            ("file_hash", "content_hash"),
            ("content_hash", "content_hash"),
            ("created_at", "created_at"),
            ("updated_at", "updated_at"),
        )
        for source_key, target_key in field_map:
            value = asset.get(source_key)
            if value in (None, "", {}, []):
                continue
            ref.setdefault(target_key, value)
        for key in ("license", "preparation"):
            value = metadata.get(key)
            if value not in (None, "", {}, []):
                ref[key] = value
        return ref

    @staticmethod
    def dataset_asset_workspace_path(asset: Mapping[str, Any]) -> str | None:
        raw_path = asset.get("virtual_path") or asset.get("file_path") or asset.get("path")
        raw_text = str(raw_path or "").strip()
        if not raw_text:
            return None
        try:
            path = normalize_workspace_virtual_path(raw_text)
        except ValueError:
            return None
        if not path.startswith(f"{WORKSPACE_ROOT}/datasets/"):
            return None
        if (
            path == WORKSPACE_DATASETS_MANIFEST_VIRTUAL_PATH
            or path.endswith("/README.md")
            or path.endswith("/.gitkeep")
            or is_workspace_protected_path(path)
            or is_workspace_internal_path(path)
        ):
            return None
        return path

    @staticmethod
    def source_field(source: Any, key: str) -> Any:
        if isinstance(source, Mapping):
            if key == "authors_json":
                return source.get("authors_json") or source.get("authors")
            return source.get(key)
        return getattr(source, key, None)

    @staticmethod
    def iso_timestamp(value: Any) -> str | None:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return str(value.isoformat())
        return str(value)

    @staticmethod
    def compact_metadata(value: Any, *, limit: int = 8) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        result: dict[str, str] = {}
        for key, item in list(value.items())[:limit]:
            clean_key = str(key or "").strip()
            if not clean_key:
                continue
            if isinstance(item, str | int | float | bool) or item is None:
                clean_value = "" if item is None else str(item)
            else:
                clean_value = json.dumps(item, ensure_ascii=False, default=str)
            result[clean_key[:80]] = clean_value[:300]
        return result

    async def load_workspace_history_context(
        self,
        client: Any,
        workspace_id: str,
    ) -> dict[str, Any]:
        decisions: list[Any] = []
        memory_facts: list[Any] = []
        executions: list[Any] = []
        threads: list[Any] = []
        try:
            decisions = await client.list_room_decisions(workspace_id)
        except Exception:
            logger.warning("Failed to load workspace decisions context", exc_info=True)
        try:
            memory_facts = await client.list_room_memory_facts(workspace_id=workspace_id, limit=12)
        except Exception:
            logger.warning("Failed to load workspace memory context", exc_info=True)
        try:
            executions = await client.list_executions(workspace_id=workspace_id, limit=8)
        except Exception:
            logger.warning("Failed to load workspace execution context", exc_info=True)
        try:
            threads = await client.list_workspace_conversation_thread_summaries(
                workspace_id=workspace_id,
                limit=8,
            )
        except Exception:
            logger.warning("Failed to load workspace thread context", exc_info=True)

        return {
            "decisions": [
                {
                    "key": str(getattr(item, "key", "") or ""),
                    "value": str(getattr(item, "value", "") or "")[:500],
                    "confidence": getattr(item, "confidence", None),
                    "created_at": self.iso_timestamp(getattr(item, "created_at", None)),
                }
                for item in decisions[:20]
            ],
            "memory": [
                {
                    "category": str(getattr(item, "category", "") or ""),
                    "content": str(getattr(item, "content", "") or "")[:500],
                    "confidence": getattr(item, "confidence", None),
                    "reference_count": getattr(item, "reference_count", 0),
                }
                for item in memory_facts[:12]
            ],
            "recent_executions": [
                {
                    "id": str(getattr(item, "id", "") or ""),
                    "capability_id": getattr(item, "capability_id", None),
                    "display_name": getattr(item, "display_name", None),
                    "status": getattr(item, "status", None),
                    "summary": str(getattr(item, "result_summary", "") or "")[:700],
                    "created_at": self.iso_timestamp(getattr(item, "created_at", None)),
                    "completed_at": self.iso_timestamp(getattr(item, "completed_at", None)),
                }
                for item in executions[:8]
            ],
            "recent_threads": [
                {
                    "id": str(getattr(item, "id", "") or ""),
                    "title": getattr(item, "title", None),
                    "last_message_preview": str(
                        getattr(item, "last_message_preview", "") or "",
                    )[:500],
                    "updated_at": self.iso_timestamp(getattr(item, "updated_at", None)),
                }
                for item in threads[:8]
            ],
        }

    async def load_sandbox_context(self, client: Any, workspace_id: str) -> dict[str, Any]:
        environments: list[Any] = []
        jobs: list[Any] = []
        artifacts: list[Any] = []
        try:
            environments = await client.list_sandbox_environments(workspace_id=workspace_id, limit=3)
        except Exception:
            logger.warning("Failed to load sandbox environments context", exc_info=True)
        try:
            jobs = await client.list_sandbox_jobs(workspace_id=workspace_id, limit=8)
        except Exception:
            logger.warning("Failed to load sandbox jobs context", exc_info=True)
        try:
            artifacts = await client.list_sandbox_artifacts(workspace_id=workspace_id, limit=12)
        except Exception:
            logger.warning("Failed to load sandbox artifact context", exc_info=True)

        return {
            "environments": [
                {
                    "id": str(getattr(item, "id", "") or ""),
                    "sandbox_id": getattr(item, "sandbox_id", None),
                    "state": getattr(item, "state", None),
                    "workspace_path": getattr(item, "workspace_path", None),
                    "last_active_at": self.iso_timestamp(getattr(item, "last_active_at", None)),
                }
                for item in environments[:3]
            ],
            "recent_jobs": [
                {
                    "id": str(getattr(item, "id", "") or ""),
                    "operation": getattr(item, "operation", None),
                    "language": getattr(item, "language", None),
                    "runtime_image": getattr(item, "runtime_image", None),
                    "status": getattr(item, "status", None),
                    "error_text": str(getattr(item, "error_text", "") or "")[:500],
                    "started_at": self.iso_timestamp(getattr(item, "started_at", None)),
                    "finished_at": self.iso_timestamp(getattr(item, "finished_at", None)),
                }
                for item in jobs[:8]
            ],
            "artifacts": [
                {
                    "id": str(getattr(item, "id", "") or ""),
                    "artifact_kind": getattr(item, "artifact_kind", None),
                    "path": getattr(item, "path", None),
                    "mime_type": getattr(item, "mime_type", None),
                    "materialization_status": getattr(item, "materialization_status", None),
                    "metadata": self.compact_metadata(getattr(item, "metadata_json", {}) or {}),
                    "created_at": self.iso_timestamp(getattr(item, "created_at", None)),
                }
                for item in artifacts[:12]
            ],
        }
