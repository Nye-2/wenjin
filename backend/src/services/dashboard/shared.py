"""Shared helpers for dashboard module status builders."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


class DashboardStatusSharedMixin:
    """Shared status helper methods reused by dashboard feature builders."""

    db: Any

    async def _count_artifacts(
        self,
        workspace_id: str,
        artifact_type: str,
        *,
        created_by_skill: str | None = None,
        created_by_skills: Sequence[str] | None = None,
    ) -> int:
        normalized_creator_skills = [
            skill_id.strip()
            for skill_id in (created_by_skills or ())
            if isinstance(skill_id, str) and skill_id.strip()
        ]
        async with self._client() as client:
            return await client.count_workspace_artifacts(
                workspace_id=workspace_id,
                artifact_type=artifact_type,
                created_by_skill=created_by_skill,
                created_by_skills=normalized_creator_skills or None,
            )

    async def _get_latest_artifact(
        self,
        workspace_id: str,
        artifact_type: str,
        *,
        created_by_skill: str | None = None,
        created_by_skills: Sequence[str] | None = None,
    ) -> Any | None:
        normalized_creator_skills = [
            skill_id.strip()
            for skill_id in (created_by_skills or ())
            if isinstance(skill_id, str) and skill_id.strip()
        ]
        async with self._client() as client:
            artifacts = await client.list_workspace_artifacts(
                workspace_id=workspace_id,
                artifact_type=artifact_type,
                created_by_skill=created_by_skill,
                created_by_skills=normalized_creator_skills or None,
                limit=1,
            )
        return artifacts[0] if artifacts else None

    async def _list_artifacts(
        self,
        workspace_id: str,
        *,
        artifact_types: Sequence[str],
        created_by_skills: Sequence[str] | None = None,
        limit: int = 50,
    ) -> list[Any]:
        normalized_artifact_types = [
            artifact_type.strip()
            for artifact_type in artifact_types
            if isinstance(artifact_type, str) and artifact_type.strip()
        ]
        normalized_creator_skills = [
            skill_id.strip()
            for skill_id in (created_by_skills or ())
            if isinstance(skill_id, str) and skill_id.strip()
        ]
        if not normalized_artifact_types:
            return []
        async with self._client() as client:
            return await client.list_workspace_artifacts(
                workspace_id=workspace_id,
                artifact_types=normalized_artifact_types,
                created_by_skills=normalized_creator_skills or None,
                limit=limit,
            )

    async def _count_running_feature_executions(
        self,
        workspace_id: str,
        feature_id: str,
    ) -> int:
        async with self._client() as client:
            return await client.count_running_feature_executions(
                workspace_id=workspace_id,
                capability_id=feature_id,
            )

    async def _get_latest_feature_execution_status(
        self,
        workspace_id: str,
        feature_id: str,
    ) -> str | None:
        async with self._client() as client:
            return await client.get_latest_feature_execution_status(
                workspace_id=workspace_id,
                capability_id=feature_id,
            )

    async def _status_from_count_and_running(
        self,
        *,
        count: int,
        running_count: int,
        latest_task_status: str | None = None,
    ) -> str:
        if running_count > 0:
            return "in_progress"
        if count > 0:
            return "completed"
        if latest_task_status == "failed":
            return "failed"
        return "not_started"
