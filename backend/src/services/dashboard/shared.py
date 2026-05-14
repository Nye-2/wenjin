"""Shared helpers for dashboard module status builders."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import func, select

from src.database import Artifact, ExecutionRecord


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
        stmt = (
            select(func.count())
            .where(Artifact.workspace_id == workspace_id)
            .where(Artifact.type == artifact_type)
        )
        normalized_creator_skills = [
            skill_id.strip()
            for skill_id in (created_by_skills or ())
            if isinstance(skill_id, str) and skill_id.strip()
        ]
        if normalized_creator_skills:
            stmt = stmt.where(Artifact.created_by_skill.in_(normalized_creator_skills))
        elif created_by_skill:
            stmt = stmt.where(Artifact.created_by_skill == created_by_skill)
        result = await self.db.execute(stmt)
        return int(result.scalar() or 0)

    async def _get_latest_artifact(
        self,
        workspace_id: str,
        artifact_type: str,
        *,
        created_by_skill: str | None = None,
        created_by_skills: Sequence[str] | None = None,
    ) -> Artifact | None:
        stmt = (
            select(Artifact)
            .where(Artifact.workspace_id == workspace_id)
            .where(Artifact.type == artifact_type)
            .order_by(Artifact.created_at.desc())
            .limit(1)
        )
        normalized_creator_skills = [
            skill_id.strip()
            for skill_id in (created_by_skills or ())
            if isinstance(skill_id, str) and skill_id.strip()
        ]
        if normalized_creator_skills:
            stmt = stmt.where(Artifact.created_by_skill.in_(normalized_creator_skills))
        elif created_by_skill:
            stmt = stmt.where(Artifact.created_by_skill == created_by_skill)
        result = await self.db.execute(stmt)
        return cast(Artifact | None, result.scalar_one_or_none())

    async def _count_running_feature_executions(
        self,
        workspace_id: str,
        feature_id: str,
    ) -> int:
        result = await self.db.execute(
            select(func.count())
            .where(ExecutionRecord.workspace_id == workspace_id)
            .where(ExecutionRecord.feature_id == feature_id)
            .where(ExecutionRecord.execution_type == "feature")
            .where(ExecutionRecord.status.in_(["pending", "running", "awaiting_user_input"]))
        )
        return int(result.scalar() or 0)

    async def _get_latest_feature_execution_status(
        self,
        workspace_id: str,
        feature_id: str,
    ) -> str | None:
        result = await self.db.execute(
            select(ExecutionRecord.status)
            .where(ExecutionRecord.workspace_id == workspace_id)
            .where(ExecutionRecord.feature_id == feature_id)
            .where(ExecutionRecord.execution_type == "feature")
            .order_by(ExecutionRecord.created_at.desc())
            .limit(1)
        )
        return cast(str | None, result.scalar_one_or_none())

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
