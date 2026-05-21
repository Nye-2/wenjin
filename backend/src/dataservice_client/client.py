"""Async HTTP client for DataService."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from src.config import dataservice_settings
from src.dataservice_client.contracts.asset import (
    WorkspaceAssetCreatePayload,
    WorkspaceAssetDownloadPayload,
    WorkspaceAssetPayload,
    WorkspaceAssetUpdatePayload,
)
from src.dataservice_client.contracts.catalog import (
    CapabilityDefinitionPayload,
    CapabilitySkillPayload,
)
from src.dataservice_client.contracts.conversation import (
    ConversationMessageCreatePayload,
    ConversationMessagePayload,
    ConversationMessagesRebuildPayload,
)
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
)
from src.dataservice_client.contracts.prism import (
    PrismFileVersionCreatePayload,
    PrismFileVersionPayload,
    PrismPrimaryProjectPayload,
    PrismProjectPayload,
    PrismSurfacePayload,
)
from src.dataservice_client.contracts.provenance import (
    ProvenanceLinkCreatePayload,
    ProvenanceLinkPayload,
)
from src.dataservice_client.contracts.review import (
    ReviewBatchCreatePayload,
    ReviewBatchDetailPayload,
    ReviewBatchPayload,
    ReviewItemDecisionPayload,
    ReviewItemDeletePayload,
    ReviewItemPatchPayload,
    ReviewItemPayload,
    ReviewItemTransitionPayload,
)
from src.dataservice_client.contracts.rooms import (
    DecisionPayload,
    DecisionSetPayload,
    MemoryFactCreatePayload,
    MemoryFactPayload,
    RoomCandidateApplyPayload,
    RoomCandidatePayload,
    WorkspaceTaskCreatePayload,
    WorkspaceTaskPayload,
    WorkspaceTaskUpdatePayload,
)
from src.dataservice_client.contracts.sandbox import (
    SandboxArtifactCreatePayload,
    SandboxArtifactPayload,
    SandboxEnvironmentCreatePayload,
    SandboxEnvironmentPayload,
    SandboxEnvironmentUpdatePayload,
    SandboxJobCreatePayload,
    SandboxJobPayload,
    SandboxJobUpdatePayload,
)
from src.dataservice_client.contracts.source import (
    SourceBibliographyCreatePayload,
    SourceBibliographyPayload,
    SourceCitationUsageCreatePayload,
    SourceCitationUsagePayload,
    SourceCreatePayload,
    SourcePayload,
)
from src.dataservice_client.contracts.workspace import (
    WorkspaceCreatePayload,
    WorkspacePayload,
    WorkspaceUpdatePayload,
)
from src.dataservice_client.errors import DataServiceClientError


class AsyncDataServiceClient:
    """Small typed client used by gateway, worker, and agent runtime code."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        internal_token: str | None = None,
        timeout_seconds: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or dataservice_settings.url).rstrip("/")
        self.internal_token = internal_token if internal_token is not None else dataservice_settings.internal_token
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout_seconds or dataservice_settings.timeout_seconds,
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AsyncDataServiceClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.close()

    async def livez(self) -> dict[str, Any]:
        return await self._request("GET", "/livez", authenticated=False)

    async def readyz(self) -> dict[str, Any]:
        return await self._request("GET", "/readyz", authenticated=False)

    async def append_conversation_message(
        self,
        thread_id: str,
        command: ConversationMessageCreatePayload,
    ) -> ConversationMessagePayload | None:
        payload = await self._request(
            "POST",
            f"/internal/v1/conversations/{thread_id}/messages",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return ConversationMessagePayload.model_validate(data) if data is not None else None

    async def rebuild_conversation_messages(
        self,
        thread_id: str,
        command: ConversationMessagesRebuildPayload,
    ) -> list[ConversationMessagePayload]:
        payload = await self._request(
            "PUT",
            f"/internal/v1/conversations/{thread_id}/messages",
            json=command.model_dump(mode="json"),
        )
        return [ConversationMessagePayload.model_validate(item) for item in payload["data"]]

    async def list_conversation_messages(self, thread_id: str) -> list[ConversationMessagePayload]:
        payload = await self._request("GET", f"/internal/v1/conversations/{thread_id}/messages")
        return [ConversationMessagePayload.model_validate(item) for item in payload["data"]]

    async def list_catalog_capabilities(
        self,
        *,
        workspace_type: str | None = None,
        enabled_only: bool = False,
    ) -> list[CapabilityDefinitionPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/catalog/capabilities",
            params={"workspace_type": workspace_type, "enabled_only": enabled_only},
        )
        return [CapabilityDefinitionPayload.model_validate(item) for item in payload["data"]]

    async def get_catalog_capability(
        self,
        *,
        workspace_type: str,
        capability_id: str,
        enabled_only: bool = False,
    ) -> CapabilityDefinitionPayload | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/catalog/capabilities/{workspace_type}/{capability_id}",
            params={"enabled_only": enabled_only},
        )
        data = payload.get("data")
        return CapabilityDefinitionPayload.model_validate(data) if data is not None else None

    async def list_catalog_skills(self, *, enabled_only: bool = False) -> list[CapabilitySkillPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/catalog/skills",
            params={"enabled_only": enabled_only},
        )
        return [CapabilitySkillPayload.model_validate(item) for item in payload["data"]]

    async def get_catalog_skill(
        self,
        skill_id: str,
        *,
        enabled_only: bool = False,
    ) -> CapabilitySkillPayload | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/catalog/skills/{skill_id}",
            params={"enabled_only": enabled_only},
        )
        data = payload.get("data")
        return CapabilitySkillPayload.model_validate(data) if data is not None else None

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

    async def create_review_batch(self, command: ReviewBatchCreatePayload) -> ReviewBatchDetailPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/review/batches",
            json=command.model_dump(mode="json"),
        )
        return ReviewBatchDetailPayload.model_validate(payload["data"])

    async def list_review_batches(
        self,
        *,
        workspace_id: str | None = None,
        execution_id: str | None = None,
        status: list[str] | None = None,
        limit: int = 50,
    ) -> list[ReviewBatchPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/review/batches",
            params={
                "workspace_id": workspace_id,
                "execution_id": execution_id,
                "status": status,
                "limit": limit,
            },
        )
        return [ReviewBatchPayload.model_validate(item) for item in payload["data"]]

    async def get_review_batch(self, batch_id: str) -> ReviewBatchDetailPayload | None:
        payload = await self._request("GET", f"/internal/v1/review/batches/{batch_id}")
        data = payload.get("data")
        return ReviewBatchDetailPayload.model_validate(data) if data is not None else None

    async def get_review_item(self, item_id: str) -> ReviewItemPayload | None:
        payload = await self._request("GET", f"/internal/v1/review/items/{item_id}")
        data = payload.get("data")
        return ReviewItemPayload.model_validate(data) if data is not None else None

    async def list_review_items(
        self,
        *,
        workspace_id: str | None = None,
        execution_id: str | None = None,
        target_domain: str | None = None,
        target_kind: str | None = None,
        status: list[str] | None = None,
        limit: int = 50,
    ) -> list[ReviewItemPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/review/items",
            params={
                "workspace_id": workspace_id,
                "execution_id": execution_id,
                "target_domain": target_domain,
                "target_kind": target_kind,
                "status": status,
                "limit": limit,
            },
        )
        return [ReviewItemPayload.model_validate(item) for item in payload["data"]]

    async def patch_review_item(
        self,
        item_id: str,
        command: ReviewItemPatchPayload,
    ) -> ReviewItemPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/review/items/{item_id}",
            json=command.model_dump(mode="json", exclude_none=True),
        )
        data = payload.get("data")
        return ReviewItemPayload.model_validate(data) if data is not None else None

    async def set_review_item_decision(
        self,
        item_id: str,
        command: ReviewItemDecisionPayload,
    ) -> ReviewItemPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/review/items/{item_id}/decision",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return ReviewItemPayload.model_validate(data) if data is not None else None

    async def transition_review_item(
        self,
        item_id: str,
        command: ReviewItemTransitionPayload,
    ) -> ReviewItemPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/review/items/{item_id}/transition",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return ReviewItemPayload.model_validate(data) if data is not None else None

    async def delete_review_item(
        self,
        item_id: str,
        command: ReviewItemDeletePayload,
    ) -> bool:
        payload = await self._request(
            "DELETE",
            f"/internal/v1/review/items/{item_id}",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data") or {}
        return bool(data.get("deleted"))

    async def register_asset(self, command: WorkspaceAssetCreatePayload) -> WorkspaceAssetPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/assets",
            json=command.model_dump(mode="json"),
        )
        return WorkspaceAssetPayload.model_validate(payload["data"])

    async def list_assets(
        self,
        *,
        workspace_id: str,
        asset_kind: str | None = None,
        source_kind: str | None = None,
        source_id: str | None = None,
        include_deleted: bool = False,
        limit: int = 50,
    ) -> list[WorkspaceAssetPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/assets",
            params={
                "workspace_id": workspace_id,
                "asset_kind": asset_kind,
                "source_kind": source_kind,
                "source_id": source_id,
                "include_deleted": include_deleted,
                "limit": limit,
            },
        )
        return [WorkspaceAssetPayload.model_validate(item) for item in payload["data"]]

    async def get_asset(
        self,
        asset_id: str,
        *,
        include_deleted: bool = False,
    ) -> WorkspaceAssetPayload | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/assets/{asset_id}",
            params={"include_deleted": include_deleted},
        )
        data = payload.get("data")
        return WorkspaceAssetPayload.model_validate(data) if data is not None else None

    async def update_asset(
        self,
        asset_id: str,
        command: WorkspaceAssetUpdatePayload,
    ) -> WorkspaceAssetPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/assets/{asset_id}",
            json=command.model_dump(mode="json", exclude_unset=True),
        )
        data = payload.get("data")
        return WorkspaceAssetPayload.model_validate(data) if data is not None else None

    async def delete_asset(self, asset_id: str) -> WorkspaceAssetPayload | None:
        payload = await self._request("DELETE", f"/internal/v1/assets/{asset_id}")
        data = payload.get("data")
        return WorkspaceAssetPayload.model_validate(data) if data is not None else None

    async def resolve_asset_download(self, asset_id: str) -> WorkspaceAssetDownloadPayload | None:
        payload = await self._request("GET", f"/internal/v1/assets/{asset_id}/download")
        data = payload.get("data")
        return WorkspaceAssetDownloadPayload.model_validate(data) if data is not None else None

    async def ensure_prism_primary_project(
        self,
        workspace_id: str,
        command: PrismPrimaryProjectPayload,
    ) -> PrismSurfacePayload:
        payload = await self._request(
            "PUT",
            f"/internal/v1/prism/workspaces/{workspace_id}/primary",
            json=command.model_dump(mode="json"),
        )
        return PrismSurfacePayload.model_validate(payload["data"])

    async def get_prism_primary_project(self, workspace_id: str) -> PrismProjectPayload | None:
        payload = await self._request("GET", f"/internal/v1/prism/workspaces/{workspace_id}/primary")
        data = payload.get("data")
        return PrismProjectPayload.model_validate(data) if data is not None else None

    async def get_prism_surface(self, workspace_id: str) -> PrismSurfacePayload | None:
        payload = await self._request("GET", f"/internal/v1/prism/workspaces/{workspace_id}/surface")
        data = payload.get("data")
        return PrismSurfacePayload.model_validate(data) if data is not None else None

    async def append_prism_file_version(
        self,
        file_id: str,
        command: PrismFileVersionCreatePayload,
    ) -> PrismFileVersionPayload | None:
        payload = await self._request(
            "POST",
            f"/internal/v1/prism/files/{file_id}/versions",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return PrismFileVersionPayload.model_validate(data) if data is not None else None

    async def create_source(self, command: SourceCreatePayload) -> SourcePayload:
        payload = await self._request(
            "POST",
            "/internal/v1/sources",
            json=command.model_dump(mode="json"),
        )
        return SourcePayload.model_validate(payload["data"])

    async def list_sources(
        self,
        *,
        workspace_id: str,
        library_status: str | None = None,
        include_deleted: bool = False,
        limit: int = 50,
    ) -> list[SourcePayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/sources",
            params={
                "workspace_id": workspace_id,
                "library_status": library_status,
                "include_deleted": include_deleted,
                "limit": limit,
            },
        )
        return [SourcePayload.model_validate(item) for item in payload["data"]]

    async def count_sources(
        self,
        *,
        workspace_id: str,
        library_status: str | None = None,
        include_deleted: bool = False,
        include_excluded: bool = False,
    ) -> int:
        payload = await self._request(
            "GET",
            "/internal/v1/sources/count",
            params={
                "workspace_id": workspace_id,
                "library_status": library_status,
                "include_deleted": include_deleted,
                "include_excluded": include_excluded,
            },
        )
        return int(payload["data"]["count"])

    async def get_source_library_outline(self, *, workspace_id: str) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET",
            "/internal/v1/sources/library-outline",
            params={"workspace_id": workspace_id},
        )
        return list(payload["data"])

    async def get_source_toc_summary(self, *, workspace_id: str) -> str:
        payload = await self._request(
            "GET",
            "/internal/v1/sources/toc-summary",
            params={"workspace_id": workspace_id},
        )
        return str(payload["data"].get("summary") or "")

    async def search_source_text_units(
        self,
        *,
        workspace_id: str,
        query: str,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET",
            "/internal/v1/sources/text-units/search",
            params={"workspace_id": workspace_id, "query": query, "limit": limit},
        )
        return list(payload["data"])

    async def get_source_section_by_path(
        self,
        *,
        source_id: str,
        workspace_id: str,
        section_path: str,
    ) -> dict[str, Any] | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/sources/{source_id}/sections/by-path",
            params={"workspace_id": workspace_id, "section_path": section_path},
        )
        data = payload.get("data")
        return dict(data) if isinstance(data, dict) else None

    async def get_source_section_by_title(
        self,
        *,
        source_id: str,
        workspace_id: str,
        section_title: str,
    ) -> dict[str, Any] | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/sources/{source_id}/sections/by-title",
            params={"workspace_id": workspace_id, "section_title": section_title},
        )
        data = payload.get("data")
        return dict(data) if isinstance(data, dict) else None

    async def get_source(self, source_id: str) -> SourcePayload | None:
        payload = await self._request("GET", f"/internal/v1/sources/{source_id}")
        data = payload.get("data")
        return SourcePayload.model_validate(data) if data is not None else None

    async def build_source_bibliography(
        self,
        command: SourceBibliographyCreatePayload,
    ) -> SourceBibliographyPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/sources/bibliography",
            json=command.model_dump(mode="json"),
        )
        return SourceBibliographyPayload.model_validate(payload["data"])

    async def record_source_citation_usage(
        self,
        command: SourceCitationUsageCreatePayload,
    ) -> SourceCitationUsagePayload:
        payload = await self._request(
            "POST",
            "/internal/v1/sources/citation-usage",
            json=command.model_dump(mode="json"),
        )
        return SourceCitationUsagePayload.model_validate(payload["data"])

    async def create_provenance_link(
        self,
        command: ProvenanceLinkCreatePayload,
    ) -> ProvenanceLinkPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/provenance/links",
            json=command.model_dump(mode="json"),
        )
        return ProvenanceLinkPayload.model_validate(payload["data"])

    async def list_provenance_links(
        self,
        *,
        workspace_id: str,
        source_id: str | None = None,
        target_domain: str | None = None,
        target_kind: str | None = None,
        target_id: str | None = None,
        review_item_id: str | None = None,
        relation_kind: str | None = None,
        limit: int = 50,
    ) -> list[ProvenanceLinkPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/provenance/links",
            params={
                "workspace_id": workspace_id,
                "source_id": source_id,
                "target_domain": target_domain,
                "target_kind": target_kind,
                "target_id": target_id,
                "review_item_id": review_item_id,
                "relation_kind": relation_kind,
                "limit": limit,
            },
        )
        return [ProvenanceLinkPayload.model_validate(item) for item in payload["data"]]

    async def delete_provenance_links(
        self,
        *,
        workspace_id: str,
        source_id: str | None = None,
        target_domain: str | None = None,
        target_kind: str | None = None,
        target_id: str | None = None,
        review_item_id: str | None = None,
        relation_kind: str | None = None,
    ) -> int:
        payload = await self._request(
            "DELETE",
            "/internal/v1/provenance/links",
            params={
                "workspace_id": workspace_id,
                "source_id": source_id,
                "target_domain": target_domain,
                "target_kind": target_kind,
                "target_id": target_id,
                "review_item_id": review_item_id,
                "relation_kind": relation_kind,
            },
        )
        data = payload.get("data") or {}
        return int(data.get("deleted") or 0)

    async def create_sandbox_environment(
        self,
        command: SandboxEnvironmentCreatePayload,
    ) -> SandboxEnvironmentPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/sandbox/environments",
            json=command.model_dump(mode="json"),
        )
        return SandboxEnvironmentPayload.model_validate(payload["data"])

    async def get_or_create_sandbox_environment(
        self,
        workspace_id: str,
        command: SandboxEnvironmentCreatePayload,
    ) -> SandboxEnvironmentPayload:
        payload = await self._request(
            "PUT",
            f"/internal/v1/sandbox/workspaces/{workspace_id}/environment",
            json=command.model_dump(mode="json"),
        )
        return SandboxEnvironmentPayload.model_validate(payload["data"])

    async def list_sandbox_environments(
        self,
        *,
        workspace_id: str,
        state: str | None = None,
        limit: int = 50,
    ) -> list[SandboxEnvironmentPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/sandbox/environments",
            params={"workspace_id": workspace_id, "state": state, "limit": limit},
        )
        return [SandboxEnvironmentPayload.model_validate(item) for item in payload["data"]]

    async def get_sandbox_environment(self, environment_id: str) -> SandboxEnvironmentPayload | None:
        payload = await self._request("GET", f"/internal/v1/sandbox/environments/{environment_id}")
        data = payload.get("data")
        return SandboxEnvironmentPayload.model_validate(data) if data is not None else None

    async def update_sandbox_environment(
        self,
        environment_id: str,
        command: SandboxEnvironmentUpdatePayload,
    ) -> SandboxEnvironmentPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/sandbox/environments/{environment_id}",
            json=command.model_dump(mode="json", exclude_unset=True),
        )
        data = payload.get("data")
        return SandboxEnvironmentPayload.model_validate(data) if data is not None else None

    async def create_sandbox_job(self, command: SandboxJobCreatePayload) -> SandboxJobPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/sandbox/jobs",
            json=command.model_dump(mode="json"),
        )
        return SandboxJobPayload.model_validate(payload["data"])

    async def update_sandbox_job(
        self,
        job_id: str,
        command: SandboxJobUpdatePayload,
    ) -> SandboxJobPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/sandbox/jobs/{job_id}",
            json=command.model_dump(mode="json", exclude_unset=True),
        )
        data = payload.get("data")
        return SandboxJobPayload.model_validate(data) if data is not None else None

    async def list_sandbox_jobs(
        self,
        *,
        workspace_id: str,
        sandbox_environment_id: str | None = None,
        execution_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[SandboxJobPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/sandbox/jobs",
            params={
                "workspace_id": workspace_id,
                "sandbox_environment_id": sandbox_environment_id,
                "execution_id": execution_id,
                "status": status,
                "limit": limit,
            },
        )
        return [SandboxJobPayload.model_validate(item) for item in payload["data"]]

    async def register_sandbox_artifact(
        self,
        command: SandboxArtifactCreatePayload,
    ) -> SandboxArtifactPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/sandbox/artifacts",
            json=command.model_dump(mode="json"),
        )
        return SandboxArtifactPayload.model_validate(payload["data"])

    async def list_sandbox_artifacts(
        self,
        *,
        workspace_id: str,
        sandbox_job_id: str | None = None,
        materialization_status: str | None = None,
        limit: int = 50,
    ) -> list[SandboxArtifactPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/sandbox/artifacts",
            params={
                "workspace_id": workspace_id,
                "sandbox_job_id": sandbox_job_id,
                "materialization_status": materialization_status,
                "limit": limit,
            },
        )
        return [SandboxArtifactPayload.model_validate(item) for item in payload["data"]]

    async def list_room_decisions(self, workspace_id: str) -> dict[str, str]:
        payload = await self._request("GET", f"/internal/v1/rooms/workspaces/{workspace_id}/decisions")
        return dict(payload["data"])

    async def set_room_decision(self, command: DecisionSetPayload) -> DecisionPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/rooms/decisions",
            json=command.model_dump(mode="json"),
        )
        return DecisionPayload.model_validate(payload["data"])

    async def delete_room_decision(self, decision_id: str) -> bool:
        payload = await self._request("DELETE", f"/internal/v1/rooms/decisions/{decision_id}")
        data = payload.get("data")
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    async def list_room_memory_facts(
        self,
        *,
        workspace_id: str,
        limit: int = 15,
        category: str | None = None,
    ) -> list[MemoryFactPayload]:
        payload = await self._request(
            "GET",
            f"/internal/v1/rooms/workspaces/{workspace_id}/memory",
            params={"limit": limit, "category": category},
        )
        return [MemoryFactPayload.model_validate(item) for item in payload["data"]]

    async def add_room_memory_facts(
        self,
        commands: list[MemoryFactCreatePayload],
    ) -> list[MemoryFactPayload]:
        payload = await self._request(
            "POST",
            "/internal/v1/rooms/memory",
            json=[command.model_dump(mode="json") for command in commands],
        )
        return [MemoryFactPayload.model_validate(item) for item in payload["data"]]

    async def delete_room_memory_fact(self, *, workspace_id: str, fact_id: str) -> bool:
        payload = await self._request("DELETE", f"/internal/v1/rooms/workspaces/{workspace_id}/memory/{fact_id}")
        data = payload.get("data")
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    async def list_room_tasks(
        self,
        *,
        workspace_id: str,
        status: str | None = None,
    ) -> list[WorkspaceTaskPayload]:
        payload = await self._request(
            "GET",
            f"/internal/v1/rooms/workspaces/{workspace_id}/tasks",
            params={"status": status},
        )
        return [WorkspaceTaskPayload.model_validate(item) for item in payload["data"]]

    async def create_room_task(self, command: WorkspaceTaskCreatePayload) -> WorkspaceTaskPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/rooms/tasks",
            json=command.model_dump(mode="json"),
        )
        return WorkspaceTaskPayload.model_validate(payload["data"])

    async def update_room_task(
        self,
        *,
        workspace_id: str,
        task_id: str,
        command: WorkspaceTaskUpdatePayload,
    ) -> WorkspaceTaskPayload | None:
        payload = await self._request(
            "PUT",
            f"/internal/v1/rooms/workspaces/{workspace_id}/tasks/{task_id}",
            json=command.model_dump(mode="json", exclude_unset=True),
        )
        data = payload.get("data")
        return WorkspaceTaskPayload.model_validate(data) if data is not None else None

    async def delete_room_task(self, *, workspace_id: str, task_id: str) -> bool:
        payload = await self._request("DELETE", f"/internal/v1/rooms/workspaces/{workspace_id}/tasks/{task_id}")
        data = payload.get("data")
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    async def stage_and_apply_room_candidates(
        self,
        *,
        workspace_id: str,
        execution_id: str,
        candidates: list[RoomCandidatePayload],
    ) -> RoomCandidateApplyPayload:
        payload = await self._request(
            "POST",
            f"/internal/v1/rooms/workspaces/{workspace_id}/candidate-apply",
            params={"execution_id": execution_id},
            json=[candidate.model_dump(mode="json") for candidate in candidates],
        )
        return RoomCandidateApplyPayload.model_validate(payload["data"])

    async def create_workspace(self, command: WorkspaceCreatePayload) -> WorkspacePayload:
        payload = await self._request(
            "POST",
            "/internal/v1/workspaces",
            json=command.model_dump(mode="json"),
        )
        return WorkspacePayload.model_validate(payload["data"])

    async def list_workspaces(self, *, member_user_id: str) -> list[WorkspacePayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/workspaces",
            params={"member_user_id": member_user_id},
        )
        return [WorkspacePayload.model_validate(item) for item in payload["data"]]

    async def get_workspace(self, workspace_id: str) -> WorkspacePayload | None:
        payload = await self._request("GET", f"/internal/v1/workspaces/{workspace_id}")
        data = payload.get("data")
        return WorkspacePayload.model_validate(data) if data is not None else None

    async def update_workspace(
        self,
        workspace_id: str,
        command: WorkspaceUpdatePayload,
    ) -> WorkspacePayload | None:
        payload = await self._request(
            "PUT",
            f"/internal/v1/workspaces/{workspace_id}",
            json=command.model_dump(mode="json", exclude_unset=True),
        )
        data = payload.get("data")
        return WorkspacePayload.model_validate(data) if data is not None else None

    async def delete_workspace(self, workspace_id: str) -> bool:
        payload = await self._request("DELETE", f"/internal/v1/workspaces/{workspace_id}")
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    async def _request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        headers = dict(kwargs.pop("headers", {}) or {})
        if authenticated:
            headers["X-Wenjin-Internal-Token"] = self.internal_token
        response = await self._client.request(method, path, headers=headers, **kwargs)
        if response.status_code >= 400:
            raise DataServiceClientError.from_response(response)
        payload = response.json()
        if not isinstance(payload, dict):
            raise DataServiceClientError(f"DataService returned non-object payload from {path}")
        return payload
