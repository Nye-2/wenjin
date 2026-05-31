"""Execution-domain methods for the DataService client."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.dataservice_client.contracts.execution import (
    ComputeSessionEnsurePayload,
    ComputeSessionPayload,
    ComputeSessionUpdatePayload,
    ExecutionCreatePayload,
    ExecutionEventCreatePayload,
    ExecutionEventPayload,
    ExecutionNodePatchPayload,
    ExecutionNodePayload,
    ExecutionNodeUpsertPayload,
    ExecutionPayload,
    ExecutionUpdatePayload,
    GenerationRecordCreatePayload,
    GenerationRecordPayload,
)


class ExecutionDataServiceClientMixin:
    """Typed DataService methods for execution, nodes, compute sessions, and usage."""

    async def _request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def create_execution(self, command: ExecutionCreatePayload) -> ExecutionPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/executions",
            json=command.model_dump(mode="json"),
        )
        return ExecutionPayload.model_validate(payload["data"])

    async def list_executions(
        self,
        *,
        user_id: str | None = None,
        workspace_id: str | None = None,
        thread_id: str | None = None,
        execution_type: str | None = None,
        status: list[str] | None = None,
        limit: int = 50,
    ) -> list[ExecutionPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/executions",
            params={
                "user_id": user_id,
                "workspace_id": workspace_id,
                "thread_id": thread_id,
                "execution_type": execution_type,
                "status": status,
                "limit": limit,
            },
        )
        return [ExecutionPayload.model_validate(item) for item in payload["data"]]

    async def get_execution(self, execution_id: str) -> ExecutionPayload | None:
        payload = await self._request("GET", f"/internal/v1/executions/{execution_id}")
        data = payload.get("data")
        return ExecutionPayload.model_validate(data) if data is not None else None

    async def update_execution(
        self,
        execution_id: str,
        command: ExecutionUpdatePayload,
    ) -> ExecutionPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/executions/{execution_id}",
            json=command.model_dump(mode="json", exclude_unset=True),
        )
        data = payload.get("data")
        return ExecutionPayload.model_validate(data) if data is not None else None

    async def count_active_execution_users(self, *, created_since: datetime) -> int:
        payload = await self._request(
            "GET",
            "/internal/v1/executions/analytics/active-users/count",
            params={"created_since": created_since.isoformat()},
        )
        return int(payload["data"]["count"])

    async def aggregate_execution_stats(
        self,
        *,
        created_since: datetime,
        granularity: str = "day",
    ) -> dict[str, Any]:
        payload = await self._request(
            "GET",
            "/internal/v1/executions/analytics/stats",
            params={"created_since": created_since.isoformat(), "granularity": granularity},
        )
        return dict(payload["data"])

    async def count_executions_by_status(self, *, user_id: str | None = None) -> dict[str, int]:
        payload = await self._request(
            "GET",
            "/internal/v1/executions/analytics/status-counts",
            params={"user_id": user_id},
        )
        return {str(key): int(value) for key, value in dict(payload["data"]).items()}

    async def count_executions(
        self,
        *,
        status: list[str] | None = None,
        created_since: datetime | None = None,
    ) -> int:
        payload = await self._request(
            "GET",
            "/internal/v1/executions/analytics/count",
            params={
                "status": status,
                "created_since": created_since.isoformat() if created_since else None,
            },
        )
        return int(payload["data"]["count"])

    async def count_executions_by_user_ids(self, user_ids: list[str]) -> dict[str, int]:
        payload = await self._request(
            "GET",
            "/internal/v1/executions/analytics/count-by-user",
            params={"user_id": user_ids},
        )
        return {str(key): int(value) for key, value in dict(payload["data"]).items()}

    async def count_running_feature_executions(
        self,
        *,
        workspace_id: str,
        capability_id: str,
    ) -> int:
        payload = await self._request(
            "GET",
            "/internal/v1/executions/features/running-count",
            params={"workspace_id": workspace_id, "capability_id": capability_id},
        )
        return int(payload["data"]["count"])

    async def get_latest_feature_execution_status(
        self,
        *,
        workspace_id: str,
        capability_id: str,
    ) -> str | None:
        payload = await self._request(
            "GET",
            "/internal/v1/executions/features/latest-status",
            params={"workspace_id": workspace_id, "capability_id": capability_id},
        )
        status = payload["data"].get("status")
        return str(status) if status is not None else None

    async def reconcile_interrupted_executions(self) -> int:
        payload = await self._request(
            "POST",
            "/internal/v1/executions/reconcile-interrupted",
        )
        return int(payload["data"]["reconciled"])

    async def ensure_compute_session(
        self,
        command: ComputeSessionEnsurePayload,
    ) -> tuple[ComputeSessionPayload, bool]:
        payload = await self._request(
            "POST",
            "/internal/v1/executions/compute-sessions/ensure",
            json=command.model_dump(mode="json"),
        )
        data = payload["data"]
        return ComputeSessionPayload.model_validate(data["session"]), bool(data["changed"])

    async def get_compute_session(self, compute_session_id: str) -> ComputeSessionPayload | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/executions/compute-sessions/{compute_session_id}",
        )
        data = payload.get("data")
        return ComputeSessionPayload.model_validate(data) if data is not None else None

    async def get_compute_session_by_execution(
        self,
        execution_id: str,
    ) -> ComputeSessionPayload | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/executions/compute-sessions/by-execution/{execution_id}",
        )
        data = payload.get("data")
        return ComputeSessionPayload.model_validate(data) if data is not None else None

    async def list_compute_sessions(
        self,
        *,
        workspace_id: str,
        user_id: str,
        limit: int = 20,
    ) -> list[ComputeSessionPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/executions/compute-sessions/list",
            params={"workspace_id": workspace_id, "user_id": user_id, "limit": limit},
        )
        return [ComputeSessionPayload.model_validate(item) for item in payload["data"]]

    async def update_compute_session(
        self,
        compute_session_id: str,
        command: ComputeSessionUpdatePayload,
    ) -> ComputeSessionPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/executions/compute-sessions/{compute_session_id}",
            json=command.model_dump(mode="json", exclude_unset=True),
        )
        data = payload.get("data")
        return ComputeSessionPayload.model_validate(data) if data is not None else None

    async def list_execution_nodes(self, execution_id: str) -> list[ExecutionNodePayload]:
        payload = await self._request("GET", f"/internal/v1/executions/{execution_id}/nodes")
        return [ExecutionNodePayload.model_validate(item) for item in payload["data"]]

    async def list_execution_nodes_by_execution_ids(
        self,
        execution_ids: list[str],
    ) -> list[ExecutionNodePayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/executions/nodes/batch",
            params={"execution_id": execution_ids},
        )
        return [ExecutionNodePayload.model_validate(item) for item in payload["data"]]

    async def get_execution_node(self, node_record_id: str) -> ExecutionNodePayload | None:
        payload = await self._request("GET", f"/internal/v1/executions/nodes/{node_record_id}")
        data = payload.get("data")
        return ExecutionNodePayload.model_validate(data) if data is not None else None

    async def find_execution_node(
        self,
        *,
        execution_id: str,
        node_id: str,
    ) -> ExecutionNodePayload | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/executions/{execution_id}/nodes/{node_id}",
        )
        data = payload.get("data")
        return ExecutionNodePayload.model_validate(data) if data is not None else None

    async def upsert_execution_node(
        self,
        execution_id: str,
        command: ExecutionNodeUpsertPayload,
    ) -> ExecutionNodePayload:
        payload = await self._request(
            "POST",
            f"/internal/v1/executions/{execution_id}/nodes",
            json=command.model_dump(mode="json", exclude_unset=True),
        )
        return ExecutionNodePayload.model_validate(payload["data"])

    async def update_execution_node(
        self,
        node_record_id: str,
        command: ExecutionNodePatchPayload,
    ) -> ExecutionNodePayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/executions/nodes/{node_record_id}",
            json=command.model_dump(mode="json", exclude_unset=True),
        )
        data = payload.get("data")
        return ExecutionNodePayload.model_validate(data) if data is not None else None

    async def append_execution_event(
        self,
        execution_id: str,
        command: ExecutionEventCreatePayload,
    ) -> ExecutionEventPayload:
        payload = await self._request(
            "POST",
            f"/internal/v1/executions/{execution_id}/events",
            json=command.model_dump(mode="json"),
        )
        return ExecutionEventPayload.model_validate(payload["data"])

    async def list_execution_events(self, execution_id: str) -> list[ExecutionEventPayload]:
        payload = await self._request("GET", f"/internal/v1/executions/{execution_id}/events")
        return [ExecutionEventPayload.model_validate(item) for item in payload["data"]]

    async def create_generation_record(
        self,
        command: GenerationRecordCreatePayload,
    ) -> GenerationRecordPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/executions/generation-records",
            json=command.model_dump(mode="json"),
        )
        return GenerationRecordPayload.model_validate(payload["data"])

    async def get_generation_record(self, record_id: str) -> GenerationRecordPayload | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/executions/generation-records/{record_id}",
        )
        data = payload.get("data")
        return GenerationRecordPayload.model_validate(data) if data is not None else None

    async def list_generation_records(
        self,
        *,
        workspace_id: str,
        skill_name: str | None = None,
        status: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[GenerationRecordPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/executions/generation-records",
            params={
                "workspace_id": workspace_id,
                "skill_name": skill_name,
                "status": status,
                "since": since.isoformat() if since else None,
                "limit": limit,
            },
        )
        return [GenerationRecordPayload.model_validate(item) for item in payload["data"]]

    async def list_generation_records_by_thread(
        self,
        thread_id: str,
    ) -> list[GenerationRecordPayload]:
        payload = await self._request(
            "GET",
            f"/internal/v1/executions/generation-records/by-thread/{thread_id}",
        )
        return [GenerationRecordPayload.model_validate(item) for item in payload["data"]]

    async def get_generation_usage_stats(
        self,
        *,
        workspace_id: str,
        since: datetime | None = None,
    ) -> dict[str, Any]:
        payload = await self._request(
            "GET",
            "/internal/v1/executions/generation-records/stats",
            params={
                "workspace_id": workspace_id,
                "since": since.isoformat() if since else None,
            },
        )
        return dict(payload["data"])

    async def cleanup_old_generation_records(
        self,
        *,
        days_old: int = 90,
        workspace_id: str | None = None,
    ) -> int:
        payload = await self._request(
            "POST",
            "/internal/v1/executions/generation-records/cleanup",
            json={"days_old": days_old, "workspace_id": workspace_id},
        )
        return int(payload["data"]["deleted"])
