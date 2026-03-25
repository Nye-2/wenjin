"""Dashboard status builders for SCI workspaces."""

from __future__ import annotations

from typing import Any

from src.artifacts.types import ArtifactType


class DashboardSciStatusMixin:
    """Feature status builders for SCI workspace modules."""

    db: Any

    async def _get_literature_search_status(self, workspace_id: str) -> dict[str, Any]:
        results_count = await self._count_artifacts(
            workspace_id,
            ArtifactType.LITERATURE_SEARCH_RESULTS.value,
        )
        running_count = await self._count_running_workspace_feature_tasks(
            workspace_id,
            "literature_search",
        )
        latest_task_status = await self._get_latest_workspace_feature_task_status(
            workspace_id,
            "literature_search",
        )

        status = await self._status_from_count_and_running(
            count=results_count,
            running_count=running_count,
            latest_task_status=latest_task_status,
        )

        return {
            "id": "literature_search",
            "status": status,
            "summary": {
                "results_count": results_count,
                "last_task_status": latest_task_status,
            },
        }

    async def _get_paper_analysis_status(self, workspace_id: str) -> dict[str, Any]:
        analysis_count = await self._count_artifacts(
            workspace_id,
            ArtifactType.PAPER_ANALYSIS.value,
        )
        running_count = await self._count_running_workspace_feature_tasks(
            workspace_id,
            "paper_analysis",
        )
        latest_task_status = await self._get_latest_workspace_feature_task_status(
            workspace_id,
            "paper_analysis",
        )

        status = await self._status_from_count_and_running(
            count=analysis_count,
            running_count=running_count,
            latest_task_status=latest_task_status,
        )

        return {
            "id": "paper_analysis",
            "status": status,
            "summary": {
                "analysis_count": analysis_count,
            },
        }

    async def _get_writing_status(self, workspace_id: str) -> dict[str, Any]:
        draft_count = await self._count_artifacts(
            workspace_id,
            ArtifactType.PAPER_DRAFT.value,
            created_by_skill="sci.writing",
        )
        running_count = await self._count_running_workspace_feature_tasks(
            workspace_id,
            "writing",
        )
        latest_task_status = await self._get_latest_workspace_feature_task_status(
            workspace_id,
            "writing",
        )
        status = await self._status_from_count_and_running(
            count=draft_count,
            running_count=running_count,
            latest_task_status=latest_task_status,
        )

        return {
            "id": "writing",
            "status": status,
            "summary": {
                "drafts_count": draft_count,
            },
        }

    async def _get_literature_review_status(self, workspace_id: str) -> dict[str, Any]:
        review_count = await self._count_artifacts(
            workspace_id,
            ArtifactType.LITERATURE_REVIEW.value,
            created_by_skill="sci.literature_review",
        )
        latest_artifact = await self._get_latest_artifact(
            workspace_id,
            ArtifactType.LITERATURE_REVIEW.value,
            created_by_skill="sci.literature_review",
        )
        running_count = await self._count_running_workspace_feature_tasks(
            workspace_id,
            "literature_review",
        )
        latest_task_status = await self._get_latest_workspace_feature_task_status(
            workspace_id,
            "literature_review",
        )
        status = await self._status_from_count_and_running(
            count=review_count,
            running_count=running_count,
            latest_task_status=latest_task_status,
        )
        content = (
            latest_artifact.content
            if latest_artifact and isinstance(latest_artifact.content, dict)
            else {}
        )
        sections = content.get("sections")
        research_gaps = content.get("research_gaps")
        key_papers = content.get("key_papers")
        return {
            "id": "literature_review",
            "status": status,
            "summary": {
                "count": review_count,
                "sections_count": len(sections) if isinstance(sections, list) else 0,
                "gaps_count": len(research_gaps) if isinstance(research_gaps, list) else 0,
                "key_papers_count": len(key_papers) if isinstance(key_papers, list) else 0,
            },
        }

    async def _get_framework_outline_status(self, workspace_id: str) -> dict[str, Any]:
        outline_count = await self._count_artifacts(
            workspace_id,
            ArtifactType.FRAMEWORK_OUTLINE.value,
            created_by_skill="sci.framework_outline",
        )
        latest_artifact = await self._get_latest_artifact(
            workspace_id,
            ArtifactType.FRAMEWORK_OUTLINE.value,
            created_by_skill="sci.framework_outline",
        )
        running_count = await self._count_running_workspace_feature_tasks(
            workspace_id,
            "framework_outline",
        )
        latest_task_status = await self._get_latest_workspace_feature_task_status(
            workspace_id,
            "framework_outline",
        )
        status = await self._status_from_count_and_running(
            count=outline_count,
            running_count=running_count,
            latest_task_status=latest_task_status,
        )
        content = (
            latest_artifact.content
            if latest_artifact and isinstance(latest_artifact.content, dict)
            else {}
        )
        sections = content.get("sections")
        keywords = content.get("keywords")
        return {
            "id": "framework_outline",
            "status": status,
            "summary": {
                "count": outline_count,
                "sections_count": len(sections) if isinstance(sections, list) else 0,
                "keywords_count": len(keywords) if isinstance(keywords, list) else 0,
            },
        }

    async def _get_peer_review_status(self, workspace_id: str) -> dict[str, Any]:
        review_count = await self._count_artifacts(
            workspace_id,
            ArtifactType.REVIEW.value,
            created_by_skill="sci.peer_review",
        )
        latest_artifact = await self._get_latest_artifact(
            workspace_id,
            ArtifactType.REVIEW.value,
            created_by_skill="sci.peer_review",
        )
        running_count = await self._count_running_workspace_feature_tasks(
            workspace_id,
            "peer_review",
        )
        latest_task_status = await self._get_latest_workspace_feature_task_status(
            workspace_id,
            "peer_review",
        )
        status = await self._status_from_count_and_running(
            count=review_count,
            running_count=running_count,
            latest_task_status=latest_task_status,
        )
        content = (
            latest_artifact.content
            if latest_artifact and isinstance(latest_artifact.content, dict)
            else {}
        )
        revision_actions = content.get("revision_actions")
        score = content.get("score")
        return {
            "id": "peer_review",
            "status": status,
            "summary": {
                "count": review_count,
                "revision_actions_count": (
                    len(revision_actions) if isinstance(revision_actions, list) else 0
                ),
                "score": float(score) if isinstance(score, (int, float)) else None,
            },
        }

    async def _get_journal_recommend_status(self, workspace_id: str) -> dict[str, Any]:
        summary_count = await self._count_artifacts(
            workspace_id,
            ArtifactType.SUMMARY.value,
            created_by_skill="sci.journal_recommend",
        )
        latest_artifact = await self._get_latest_artifact(
            workspace_id,
            ArtifactType.SUMMARY.value,
            created_by_skill="sci.journal_recommend",
        )
        running_count = await self._count_running_workspace_feature_tasks(
            workspace_id,
            "journal_recommend",
        )
        latest_task_status = await self._get_latest_workspace_feature_task_status(
            workspace_id,
            "journal_recommend",
        )
        status = await self._status_from_count_and_running(
            count=summary_count,
            running_count=running_count,
            latest_task_status=latest_task_status,
        )
        content = (
            latest_artifact.content
            if latest_artifact and isinstance(latest_artifact.content, dict)
            else {}
        )
        journals = content.get("journals")
        return {
            "id": "journal_recommend",
            "status": status,
            "summary": {
                "count": summary_count,
                "journals_count": len(journals) if isinstance(journals, list) else 0,
            },
        }
