"""Resolve prism status from LatexProject.

This resolver encapsulates the logic that ComputeProjectionService previously
performed directly — querying LatexProject and computing prism status from
file_changes / compile state. By extracting it, ProjectionService remains a
pure formatter and does not make business-status decisions.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.latex_project import LatexProject


def _read_text(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _normalize_prism_file_changes(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _normalize_applied_prism_file_changes(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [dict(item) for item in value.values() if isinstance(item, dict)]
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _append_unique_text(values: list[str], value: Any) -> None:
    text = _read_text(value)
    if text and text not in values:
        values.append(text)


class LatexPrismStatusResolver:
    """Refresh prism projection dict with latest LatexProject state and computed status."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def refresh(
        self,
        prism: dict[str, Any],
        *,
        user_id: str,
    ) -> dict[str, Any]:
        """Query LatexProject for current file changes and recompute prism status.

        Returns the mutated *prism* dict for convenience.
        """
        project_id = _read_text(prism.get("project_id"))
        if project_id is None:
            return prism

        result = await self.db.execute(
            select(LatexProject).where(
                LatexProject.id == project_id,
                LatexProject.user_id == user_id,
            )
        )
        project = result.scalar_one_or_none()
        if project is None:
            return prism

        llm_config = (
            project.llm_config if isinstance(project.llm_config, dict) else {}
        )
        metadata = (
            llm_config.get("metadata")
            if isinstance(llm_config.get("metadata"), dict)
            else {}
        )
        current_file_changes = _normalize_prism_file_changes(
            metadata.get("file_changes")
        )
        current_applied_file_changes = _normalize_applied_prism_file_changes(
            metadata.get("applied_file_changes")
        )
        prism["file_changes"] = current_file_changes
        prism["applied_file_changes"] = current_applied_file_changes
        prism["main_file"] = str(
            project.main_file or prism.get("main_file") or "main.tex"
        )
        for change in current_file_changes:
            _append_unique_text(
                prism.setdefault("target_files", []), change.get("path")
            )
        for change in current_applied_file_changes:
            _append_unique_text(
                prism.setdefault("target_files", []), change.get("path")
            )

        compile_info = (
            prism.get("compile") if isinstance(prism.get("compile"), dict) else {}
        )
        status = "ready"
        if compile_info.get("status") == "failed" or compile_info.get("error"):
            status = "compile_failed"
        elif current_file_changes:
            status = "pending_changes"
        prism["status"] = status

        for item in prism.get("items", []):
            if (
                not isinstance(item, dict)
                or item.get("latex_project_id") != project_id
            ):
                continue
            item["file_changes"] = current_file_changes
            item["applied_file_changes"] = current_applied_file_changes
            item_status = "ready"
            item_compile = (
                item.get("compile") if isinstance(item.get("compile"), dict) else {}
            )
            if item_compile.get("status") == "failed" or item_compile.get("error"):
                item_status = "compile_failed"
            elif current_file_changes:
                item_status = "pending_changes"
            item["status"] = item_status

        return prism
