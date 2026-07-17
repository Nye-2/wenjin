"""User dashboard aggregation service."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.mission import MissionStatus
from src.dataservice_client.provider import dataservice_client
from src.services.credit_service import CreditService

_RUNNING_MISSION_STATUSES = {
    MissionStatus.PLANNING,
    MissionStatus.RUNNING,
    MissionStatus.WAITING,
}
_TERMINAL_MISSION_STATUSES = {
    MissionStatus.COMPLETED,
    MissionStatus.FAILED,
    MissionStatus.CANCELLED,
}


class UserDashboardService:
    """Aggregate user-facing dashboard data."""

    def __init__(
        self,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ):
        self._dataservice = dataservice

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[AsyncDataServiceClient]:
        if self._dataservice is not None:
            yield self._dataservice
            return
        async with dataservice_client() as client:
            yield client

    async def get_dashboard(self, user_id: str) -> dict[str, Any]:
        """Build user dashboard payload."""
        async with self._client() as client:
            user = await client.get_account_user(user_id)
            pricing = await client.get_public_pricing_catalog()
        if user is None:
            raise ValueError("User not found")

        workspace_stats = await self._get_workspace_stats(user_id)
        task_stats, recent_tasks = await self._get_mission_stats(user_id)
        thread_credit_status = await self._get_thread_credit_status(
            user_id,
            credit_service=CreditService(dataservice=self._dataservice),
            current_balance=int(user.credits),
            default_model_id=next(
                (
                    model.model_id
                    for model in pricing.chat_models
                    if model.is_default
                ),
                pricing.chat_models[0].model_id if pricing.chat_models else None,
            ),
        )

        return {
            "profile": {
                "id": str(user.id),
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login": user.last_login.isoformat() if user.last_login else None,
            },
            "credits": {
                "balance": int(user.credits),
                "total_earned": int(user.total_credits_earned),
                "total_spent": int(user.total_credits_spent),
                "pricing": pricing.model_dump(mode="json"),
                "thread": thread_credit_status,
            },
            "workspaces": workspace_stats,
            "tasks": task_stats,
            "recent_tasks": recent_tasks,
            "updated_at": datetime.now(UTC).isoformat(),
        }

    async def get_public_pricing(self) -> dict[str, Any]:
        async with self._client() as client:
            pricing = await client.get_public_pricing_catalog()
        return pricing.model_dump(mode="json")

    async def _get_workspace_stats(self, user_id: str) -> dict[str, Any]:
        async with self._client() as client:
            stats = await client.get_workspace_stats_for_member(user_id)
        return {
            "total": stats.total,
            "by_type": stats.by_type,
            "created_last_7d": stats.created_last_7d,
        }

    async def _get_mission_stats(self, user_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        async with self._client() as client:
            summary = await client.missions.get_user_summary(user_id=user_id)

        counts = {status: 0 for status in MissionStatus}
        for raw_status, count in summary.status_counts.items():
            counts[MissionStatus(raw_status)] = count

        total = summary.total
        success = counts[MissionStatus.COMPLETED]
        terminal = sum(counts[status] for status in _TERMINAL_MISSION_STATUSES)
        completion_rate = float(round(success / terminal, 4)) if terminal else 0.0

        recent_tasks = [
            {
                "id": mission.mission_id,
                "task_type": mission.title,
                "status": mission.status.value,
                "progress": 100 if mission.status in _TERMINAL_MISSION_STATUSES else 0,
                "message": mission.objective,
                "created_at": mission.created_at.isoformat(),
                "completed_at": mission.completed_at.isoformat() if mission.completed_at else None,
            }
            for mission in summary.recent
        ]

        return (
            {
                "total": total,
                "success": success,
                "running": sum(counts[status] for status in _RUNNING_MISSION_STATUSES),
                "failed": counts[MissionStatus.FAILED],
                "pending": counts[MissionStatus.CREATED],
                "cancelled": counts[MissionStatus.CANCELLED],
                "completion_rate": completion_rate,
            },
            recent_tasks,
        )

    async def _get_thread_credit_status(
        self,
        user_id: str,
        *,
        credit_service: CreditService,
        current_balance: int,
        default_model_id: str | None,
    ) -> dict[str, Any]:
        """Build thread-specific credit status for dashboard display."""
        if default_model_id is None:
            raise ValueError("Default chat model pricing is unavailable")
        can_start_thread = await credit_service.preview_thread_turn_capacity(
            user_id,
            model_name=default_model_id,
        )

        return {
            "enabled": True,
            "can_start_thread": can_start_thread,
            "overdraft_credits": max(-current_balance, 0),
            "billing_unit": "credits",
            "pricing": "usage_based",
        }
