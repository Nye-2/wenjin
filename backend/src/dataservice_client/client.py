"""Async HTTP client for DataService."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from src.config import dataservice_settings
from src.dataservice_client.contracts.account import (
    AccountAdminStatsPayload,
    AccountRefreshTokenPayload,
    AccountUserCreatePayload,
    AccountUserGrowthPayload,
    AccountUserListPayload,
    AccountUserPayload,
    AccountUserRolePayload,
    AccountUserStatusPayload,
)
from src.dataservice_client.contracts.asset import (
    LegacyArtifactCreatePayload,
    LegacyArtifactPayload,
    LegacyArtifactUpdatePayload,
    WorkspaceAssetCreatePayload,
    WorkspaceAssetDownloadPayload,
    WorkspaceAssetPayload,
    WorkspaceAssetUpdatePayload,
)
from src.dataservice_client.contracts.audit import AuditLogCreatePayload, AuditLogPayload
from src.dataservice_client.contracts.catalog import (
    AdminLogCreatePayload as CatalogAdminLogCreatePayload,
)
from src.dataservice_client.contracts.catalog import (
    AdminLogPayload as CatalogAdminLogPayload,
)
from src.dataservice_client.contracts.catalog import (
    CapabilityDefinitionPayload,
    CapabilitySkillPayload,
    CatalogEnabledPayload,
    CatalogSeedLoadPayload,
    CatalogSeedLoadResultPayload,
    CatalogUpsertPayload,
)
from src.dataservice_client.contracts.conversation import (
    ConversationMessageCreatePayload,
    ConversationMessagePayload,
    ConversationMessagesRebuildPayload,
    ConversationThreadCreatePayload,
    ConversationThreadPayload,
    ConversationThreadUpdatePayload,
)
from src.dataservice_client.contracts.credit import (
    CreditAdminAdjustPayload,
    CreditAdminSummaryPayload,
    CreditConsumptionCreatePayload,
    CreditConsumptionStatsPayload,
    CreditGrantRuleCreatePayload,
    CreditGrantRulePayload,
    CreditGrantRuleUpdatePayload,
    CreditHistoryPayload,
    CreditPeriodicGrantProcessPayload,
    CreditPeriodicGrantSummaryPayload,
    CreditRedeemCodeCreatePayload,
    CreditRedeemCodePayload,
    CreditRedeemPayload,
    CreditReferralCreatePayload,
    CreditReferralPayload,
    CreditRefundPayload,
    CreditSummaryPayload,
    CreditTokenUsagePayload,
    CreditTransactionPayload,
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
    GenerationRecordCreatePayload,
    GenerationRecordPayload,
)
from src.dataservice_client.contracts.knowledge import (
    KnowledgeArchiveLowConfidencePayload,
    KnowledgeMemoryCreatePayload,
    KnowledgeMemoryPayload,
    KnowledgeMemoryUpdatePayload,
)
from src.dataservice_client.contracts.latex import (
    LatexCompileHistoryCreatePayload,
    LatexCompileHistoryPayload,
    LatexProjectAttachWorkspacePayload,
    LatexProjectCreatePayload,
    LatexProjectPayload,
    LatexProjectTouchPayload,
    LatexProjectUpdatePayload,
    LatexTemplatePayload,
)
from src.dataservice_client.contracts.prism import (
    PrismFileVersionCreatePayload,
    PrismFileVersionPayload,
    PrismPrimaryProjectPayload,
    PrismProjectPayload,
    PrismSurfacePayload,
)
from src.dataservice_client.contracts.prism_review import (
    PrismFileChangeAppliedPayload,
    PrismFileChangeClearPayload,
    PrismFileChangeRejectedPayload,
    PrismFileChangeUpsertPayload,
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
    SourceAssetUpdatePayload,
    SourceBibliographyCreatePayload,
    SourceBibliographyPayload,
    SourceBibliographySnapshotCreatePayload,
    SourceBibliographySnapshotPayload,
    SourceCitationUsageCreatePayload,
    SourceCitationUsagePayload,
    SourceCreatePayload,
    SourceExternalIdCreatePayload,
    SourceImportPayload,
    SourceImportResultPayload,
    SourcePayload,
    SourceUpdatePayload,
)
from src.dataservice_client.contracts.task import (
    TaskRecordCompletedPayload,
    TaskRecordCreateGuardedPayload,
    TaskRecordCreatePayload,
    TaskRecordPatchPayload,
    TaskRecordPayload,
    TaskRecordRuntimeStatePayload,
    TaskRecordStartedPayload,
)
from src.dataservice_client.contracts.template import (
    WorkspaceTemplateCreatePayload,
    WorkspaceTemplateDeactivatePayload,
    WorkspaceTemplatePayload,
)
from src.dataservice_client.contracts.workspace import (
    WorkspaceAdminStatsPayload,
    WorkspaceCreatePayload,
    WorkspacePayload,
    WorkspaceStatsPayload,
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

    async def create_audit_log(
        self,
        command: AuditLogCreatePayload,
    ) -> AuditLogPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/audit/logs",
            json=command.model_dump(mode="json"),
        )
        return AuditLogPayload.model_validate(payload["data"])

    async def query_audit_logs(
        self,
        *,
        workspace_id: str | None = None,
        user_id: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditLogPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/audit/logs",
            params={
                "workspace_id": workspace_id,
                "user_id": user_id,
                "since": since.isoformat() if since else None,
                "limit": limit,
            },
        )
        return [AuditLogPayload.model_validate(item) for item in payload["data"]]

    async def get_workspace_template(
        self,
        template_id: str,
    ) -> WorkspaceTemplatePayload | None:
        payload = await self._request("GET", f"/internal/v1/templates/{template_id}")
        data = payload.get("data")
        return WorkspaceTemplatePayload.model_validate(data) if data is not None else None

    async def get_active_workspace_template(
        self,
        workspace_id: str,
    ) -> WorkspaceTemplatePayload | None:
        payload = await self._request("GET", f"/internal/v1/templates/workspaces/{workspace_id}/active")
        data = payload.get("data")
        return WorkspaceTemplatePayload.model_validate(data) if data is not None else None

    async def list_workspace_templates(
        self,
        workspace_id: str,
    ) -> list[WorkspaceTemplatePayload]:
        payload = await self._request("GET", f"/internal/v1/templates/workspaces/{workspace_id}")
        return [WorkspaceTemplatePayload.model_validate(item) for item in payload["data"]]

    async def create_workspace_template(
        self,
        command: WorkspaceTemplateCreatePayload,
    ) -> WorkspaceTemplatePayload | None:
        payload = await self._request(
            "POST",
            "/internal/v1/templates",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return WorkspaceTemplatePayload.model_validate(data) if data is not None else None

    async def deactivate_active_workspace_templates(
        self,
        workspace_id: str,
        command: WorkspaceTemplateDeactivatePayload | None = None,
    ) -> bool:
        payload = await self._request(
            "POST",
            f"/internal/v1/templates/workspaces/{workspace_id}/deactivate-active",
            json=(command or WorkspaceTemplateDeactivatePayload()).model_dump(mode="json"),
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("deactivated")) if isinstance(data, dict) else False

    async def activate_workspace_template(
        self,
        *,
        workspace_id: str,
        template_id: str,
    ) -> WorkspaceTemplatePayload | None:
        payload = await self._request(
            "POST",
            f"/internal/v1/templates/workspaces/{workspace_id}/{template_id}/activate",
        )
        data = payload.get("data")
        return WorkspaceTemplatePayload.model_validate(data) if data is not None else None

    async def delete_workspace_template(
        self,
        template_id: str,
        *,
        workspace_id: str | None = None,
    ) -> bool:
        payload = await self._request(
            "DELETE",
            f"/internal/v1/templates/{template_id}",
            params={"workspace_id": workspace_id},
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    async def create_knowledge_memory(
        self,
        command: KnowledgeMemoryCreatePayload,
    ) -> KnowledgeMemoryPayload | None:
        payload = await self._request(
            "POST",
            "/internal/v1/knowledge",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return KnowledgeMemoryPayload.model_validate(data) if data is not None else None

    async def upsert_knowledge_memory(
        self,
        command: KnowledgeMemoryCreatePayload,
    ) -> KnowledgeMemoryPayload | None:
        payload = await self._request(
            "POST",
            "/internal/v1/knowledge/upsert",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return KnowledgeMemoryPayload.model_validate(data) if data is not None else None

    async def get_knowledge_memory(self, knowledge_id: str) -> KnowledgeMemoryPayload | None:
        payload = await self._request("GET", f"/internal/v1/knowledge/{knowledge_id}")
        data = payload.get("data")
        return KnowledgeMemoryPayload.model_validate(data) if data is not None else None

    async def list_user_knowledge_memory(
        self,
        *,
        user_id: str,
        category: str | None = None,
        min_confidence: float | None = None,
        active_only: bool = True,
    ) -> list[KnowledgeMemoryPayload]:
        payload = await self._request(
            "GET",
            f"/internal/v1/knowledge/users/{user_id}",
            params={
                "category": category,
                "min_confidence": min_confidence,
                "active_only": active_only,
            },
        )
        return [KnowledgeMemoryPayload.model_validate(item) for item in payload["data"]]

    async def list_active_knowledge_memory(
        self,
        *,
        user_id: str,
        workspace_context: str | None = None,
        include_global: bool = True,
        min_confidence: float = 0.5,
        limit: int = 20,
    ) -> list[KnowledgeMemoryPayload]:
        payload = await self._request(
            "GET",
            f"/internal/v1/knowledge/users/{user_id}/active",
            params={
                "workspace_context": workspace_context,
                "include_global": include_global,
                "min_confidence": min_confidence,
                "limit": limit,
            },
        )
        return [KnowledgeMemoryPayload.model_validate(item) for item in payload["data"]]

    async def update_knowledge_memory(
        self,
        knowledge_id: str,
        command: KnowledgeMemoryUpdatePayload,
    ) -> KnowledgeMemoryPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/knowledge/{knowledge_id}",
            json=command.model_dump(mode="json", exclude_unset=True),
        )
        data = payload.get("data")
        return KnowledgeMemoryPayload.model_validate(data) if data is not None else None

    async def deactivate_knowledge_memory(self, knowledge_id: str) -> bool:
        payload = await self._request("POST", f"/internal/v1/knowledge/{knowledge_id}/deactivate")
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("deactivated")) if isinstance(data, dict) else False

    async def delete_knowledge_memory(self, knowledge_id: str) -> bool:
        payload = await self._request("DELETE", f"/internal/v1/knowledge/{knowledge_id}")
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    async def archive_low_confidence_knowledge_memory(
        self,
        *,
        user_id: str,
        command: KnowledgeArchiveLowConfidencePayload | None = None,
    ) -> int:
        payload = await self._request(
            "POST",
            f"/internal/v1/knowledge/users/{user_id}/archive-low-confidence",
            json=(command or KnowledgeArchiveLowConfidencePayload()).model_dump(mode="json"),
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        return int(data.get("archived", 0)) if isinstance(data, dict) else 0

    async def count_active_knowledge_memory(
        self,
        *,
        user_id: str,
        workspace_context: str | None = None,
        include_global: bool | None = None,
    ) -> int:
        payload = await self._request(
            "GET",
            f"/internal/v1/knowledge/users/{user_id}/active-count",
            params={
                "workspace_context": workspace_context,
                "include_global": include_global,
            },
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        return int(data.get("count", 0)) if isinstance(data, dict) else 0

    async def list_latex_projects_by_user(
        self,
        *,
        user_id: str,
        include_trashed: bool = False,
    ) -> list[LatexProjectPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/latex/projects",
            params={"user_id": user_id, "include_trashed": include_trashed},
        )
        return [LatexProjectPayload.model_validate(item) for item in payload["data"]]

    async def get_latex_project(self, project_id: str) -> LatexProjectPayload | None:
        payload = await self._request("GET", f"/internal/v1/latex/projects/{project_id}")
        data = payload.get("data")
        return LatexProjectPayload.model_validate(data) if data is not None else None

    async def get_owned_latex_project(
        self,
        *,
        project_id: str,
        user_id: str,
    ) -> LatexProjectPayload | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/latex/projects/{project_id}/owned",
            params={"user_id": user_id},
        )
        data = payload.get("data")
        return LatexProjectPayload.model_validate(data) if data is not None else None

    async def get_workspace_primary_latex_project(
        self,
        *,
        workspace_id: str,
        owner_user_id: str,
        template: str | None = None,
    ) -> LatexProjectPayload | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/latex/workspaces/{workspace_id}/primary-project",
            params={"owner_user_id": owner_user_id, "template": template},
        )
        data = payload.get("data")
        return LatexProjectPayload.model_validate(data) if data is not None else None

    async def create_latex_project(
        self,
        command: LatexProjectCreatePayload,
    ) -> LatexProjectPayload | None:
        payload = await self._request(
            "POST",
            "/internal/v1/latex/projects",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return LatexProjectPayload.model_validate(data) if data is not None else None

    async def update_latex_project(
        self,
        project_id: str,
        command: LatexProjectUpdatePayload,
    ) -> LatexProjectPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/latex/projects/{project_id}",
            json=command.model_dump(mode="json", exclude_unset=True),
        )
        data = payload.get("data")
        return LatexProjectPayload.model_validate(data) if data is not None else None

    async def touch_latex_project(
        self,
        project_id: str,
        command: LatexProjectTouchPayload,
    ) -> LatexProjectPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/latex/projects/{project_id}/touch",
            json=command.model_dump(mode="json", exclude_unset=True),
        )
        data = payload.get("data")
        return LatexProjectPayload.model_validate(data) if data is not None else None

    async def attach_workspace_latex_project(
        self,
        project_id: str,
        command: LatexProjectAttachWorkspacePayload,
    ) -> LatexProjectPayload | None:
        payload = await self._request(
            "POST",
            f"/internal/v1/latex/projects/{project_id}/attach-workspace",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return LatexProjectPayload.model_validate(data) if data is not None else None

    async def soft_delete_latex_project(self, project_id: str) -> LatexProjectPayload | None:
        payload = await self._request("POST", f"/internal/v1/latex/projects/{project_id}/soft-delete")
        data = payload.get("data")
        return LatexProjectPayload.model_validate(data) if data is not None else None

    async def delete_latex_project(self, project_id: str) -> bool:
        payload = await self._request("DELETE", f"/internal/v1/latex/projects/{project_id}")
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    async def get_latex_template(self, template_id: str) -> LatexTemplatePayload | None:
        payload = await self._request("GET", f"/internal/v1/latex/templates/{template_id}")
        data = payload.get("data")
        return LatexTemplatePayload.model_validate(data) if data is not None else None

    async def ensure_default_latex_templates(self) -> bool:
        payload = await self._request("POST", "/internal/v1/latex/templates/ensure-defaults")
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("ensured")) if isinstance(data, dict) else False

    async def list_latex_templates(self) -> list[LatexTemplatePayload]:
        payload = await self._request("GET", "/internal/v1/latex/templates")
        return [LatexTemplatePayload.model_validate(item) for item in payload["data"]]

    async def record_latex_compile_history(
        self,
        command: LatexCompileHistoryCreatePayload,
    ) -> LatexCompileHistoryPayload | None:
        payload = await self._request(
            "POST",
            "/internal/v1/latex/compile-history",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return LatexCompileHistoryPayload.model_validate(data) if data is not None else None

    async def get_latex_compile_history(
        self,
        history_id: str,
    ) -> LatexCompileHistoryPayload | None:
        payload = await self._request("GET", f"/internal/v1/latex/compile-history/{history_id}")
        data = payload.get("data")
        return LatexCompileHistoryPayload.model_validate(data) if data is not None else None

    async def list_latex_compile_history(
        self,
        project_id: str,
    ) -> list[LatexCompileHistoryPayload]:
        payload = await self._request(
            "GET",
            f"/internal/v1/latex/projects/{project_id}/compile-history",
        )
        return [LatexCompileHistoryPayload.model_validate(item) for item in payload["data"]]

    async def delete_latex_compile_history(self, history_id: str) -> bool:
        payload = await self._request("DELETE", f"/internal/v1/latex/compile-history/{history_id}")
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    async def create_task_record(
        self,
        command: TaskRecordCreatePayload,
    ) -> TaskRecordPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/tasks",
            json=command.model_dump(mode="json"),
        )
        return TaskRecordPayload.model_validate(payload["data"])

    async def create_task_record_guarded(
        self,
        command: TaskRecordCreateGuardedPayload,
    ) -> tuple[TaskRecordPayload | None, int]:
        payload = await self._request(
            "POST",
            "/internal/v1/tasks/guarded",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data") or {}
        record = data.get("record")
        return (
            TaskRecordPayload.model_validate(record) if record is not None else None,
            int(data.get("active_count", 0)),
        )

    async def get_task_record(self, task_id: str) -> TaskRecordPayload | None:
        payload = await self._request("GET", f"/internal/v1/tasks/{task_id}")
        data = payload.get("data")
        return TaskRecordPayload.model_validate(data) if data is not None else None

    async def update_task_record(
        self,
        task_id: str,
        command: TaskRecordPatchPayload,
    ) -> TaskRecordPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/tasks/{task_id}",
            json=command.model_dump(mode="json", exclude_unset=True),
        )
        data = payload.get("data")
        return TaskRecordPayload.model_validate(data) if data is not None else None

    async def list_user_task_records(
        self,
        *,
        user_id: str,
        status: str | list[str] | None = None,
        task_type: str | None = None,
        limit: int = 20,
        workspace_id: str | None = None,
        feature_id: str | None = None,
        action: str | None = None,
    ) -> list[TaskRecordPayload]:
        payload = await self._request(
            "GET",
            f"/internal/v1/tasks/users/{user_id}",
            params={
                "status": status,
                "task_type": task_type,
                "limit": limit,
                "workspace_id": workspace_id,
                "feature_id": feature_id,
                "action": action,
            },
        )
        return [TaskRecordPayload.model_validate(item) for item in payload["data"]]

    async def count_active_task_records(
        self,
        *,
        user_id: str,
        active_statuses: list[str],
    ) -> int:
        payload = await self._request(
            "GET",
            f"/internal/v1/tasks/users/{user_id}/active-count",
            params={"active_statuses": active_statuses},
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        return int(data.get("count", 0)) if isinstance(data, dict) else 0

    async def mark_task_record_started(
        self,
        task_id: str,
        command: TaskRecordStartedPayload,
    ) -> TaskRecordPayload | None:
        payload = await self._request(
            "POST",
            f"/internal/v1/tasks/{task_id}/started",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return TaskRecordPayload.model_validate(data) if data is not None else None

    async def persist_task_record_runtime_state(
        self,
        task_id: str,
        command: TaskRecordRuntimeStatePayload,
    ) -> TaskRecordPayload | None:
        payload = await self._request(
            "POST",
            f"/internal/v1/tasks/{task_id}/runtime-state",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return TaskRecordPayload.model_validate(data) if data is not None else None

    async def mark_task_record_completed(
        self,
        task_id: str,
        command: TaskRecordCompletedPayload,
    ) -> TaskRecordPayload | None:
        payload = await self._request(
            "POST",
            f"/internal/v1/tasks/{task_id}/completed",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return TaskRecordPayload.model_validate(data) if data is not None else None

    async def find_prism_file_change(
        self,
        *,
        workspace_id: str,
        latex_project_id: str,
        logical_key: str,
        statuses: list[str] | None = None,
        limit: int = 1000,
    ) -> ReviewItemPayload | None:
        payload = await self._request(
            "GET",
            "/internal/v1/prism-review/file-changes/find",
            params={
                "workspace_id": workspace_id,
                "latex_project_id": latex_project_id,
                "logical_key": logical_key,
                "statuses": statuses,
                "limit": limit,
            },
        )
        data = payload.get("data")
        return ReviewItemPayload.model_validate(data) if data is not None else None

    async def upsert_pending_prism_file_change(
        self,
        command: PrismFileChangeUpsertPayload,
    ) -> ReviewItemPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/prism-review/file-changes/upsert",
            json=command.model_dump(mode="json"),
        )
        return ReviewItemPayload.model_validate(payload["data"])

    async def clear_pending_prism_file_change(
        self,
        command: PrismFileChangeClearPayload,
    ) -> bool:
        payload = await self._request(
            "POST",
            "/internal/v1/prism-review/file-changes/clear-pending",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    async def mark_prism_file_change_applied(
        self,
        item_id: str,
        command: PrismFileChangeAppliedPayload,
    ) -> ReviewItemPayload | None:
        payload = await self._request(
            "POST",
            f"/internal/v1/prism-review/items/{item_id}/applied",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return ReviewItemPayload.model_validate(data) if data is not None else None

    async def mark_prism_file_change_rejected(
        self,
        item_id: str,
        command: PrismFileChangeRejectedPayload,
    ) -> ReviewItemPayload | None:
        payload = await self._request(
            "POST",
            f"/internal/v1/prism-review/items/{item_id}/rejected",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return ReviewItemPayload.model_validate(data) if data is not None else None

    async def mark_prism_file_change_reverted(
        self,
        item_id: str,
    ) -> ReviewItemPayload | None:
        payload = await self._request("POST", f"/internal/v1/prism-review/items/{item_id}/reverted")
        data = payload.get("data")
        return ReviewItemPayload.model_validate(data) if data is not None else None

    async def create_account_user(
        self,
        command: AccountUserCreatePayload,
    ) -> AccountUserPayload | None:
        payload = await self._request(
            "POST",
            "/internal/v1/account/users",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return AccountUserPayload.model_validate(data) if data is not None else None

    async def get_account_user(self, user_id: str) -> AccountUserPayload | None:
        payload = await self._request("GET", f"/internal/v1/account/users/{user_id}")
        data = payload.get("data")
        return AccountUserPayload.model_validate(data) if data is not None else None

    async def get_account_auth_user(self, user_id: str) -> AccountUserPayload | None:
        payload = await self._request("GET", f"/internal/v1/account/users/{user_id}/auth")
        data = payload.get("data")
        return AccountUserPayload.model_validate(data) if data is not None else None

    async def get_account_auth_user_by_email(self, email: str) -> AccountUserPayload | None:
        payload = await self._request(
            "GET",
            "/internal/v1/account/users/by-email",
            params={"email": email},
        )
        data = payload.get("data")
        return AccountUserPayload.model_validate(data) if data is not None else None

    async def update_account_refresh_token(
        self,
        user_id: str,
        command: AccountRefreshTokenPayload,
    ) -> AccountUserPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/account/users/{user_id}/refresh-token",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return AccountUserPayload.model_validate(data) if data is not None else None

    async def update_account_last_login(self, user_id: str) -> AccountUserPayload | None:
        payload = await self._request("POST", f"/internal/v1/account/users/{user_id}/last-login")
        data = payload.get("data")
        return AccountUserPayload.model_validate(data) if data is not None else None

    async def get_account_admin_stats(self) -> AccountAdminStatsPayload:
        payload = await self._request("GET", "/internal/v1/account/admin-stats")
        return AccountAdminStatsPayload.model_validate(payload["data"])

    async def list_account_users(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
        is_active: bool | None = None,
        is_superuser: bool | None = None,
    ) -> AccountUserListPayload:
        payload = await self._request(
            "GET",
            "/internal/v1/account/users",
            params={
                "page": page,
                "page_size": page_size,
                "keyword": keyword,
                "is_active": is_active,
                "is_superuser": is_superuser,
            },
        )
        return AccountUserListPayload.model_validate(payload["data"])

    async def update_account_user_status(
        self,
        user_id: str,
        command: AccountUserStatusPayload,
    ) -> AccountUserPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/account/users/{user_id}/status",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return AccountUserPayload.model_validate(data) if data is not None else None

    async def update_account_user_role(
        self,
        user_id: str,
        command: AccountUserRolePayload,
    ) -> AccountUserPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/account/users/{user_id}/role",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return AccountUserPayload.model_validate(data) if data is not None else None

    async def aggregate_account_user_growth(
        self,
        *,
        since: datetime,
        granularity: str = "day",
    ) -> AccountUserGrowthPayload:
        payload = await self._request(
            "GET",
            "/internal/v1/account/growth",
            params={"since": since.isoformat(), "granularity": granularity},
        )
        return AccountUserGrowthPayload.model_validate(payload["data"])

    async def list_credit_grant_rules(self) -> list[CreditGrantRulePayload]:
        payload = await self._request("GET", "/internal/v1/credit/grant-rules")
        return [CreditGrantRulePayload.model_validate(item) for item in payload["data"]]

    async def get_credit_grant_rule(self, rule_id: str) -> CreditGrantRulePayload | None:
        payload = await self._request("GET", f"/internal/v1/credit/grant-rules/{rule_id}")
        data = payload.get("data")
        return CreditGrantRulePayload.model_validate(data) if data is not None else None

    async def get_active_credit_grant_rule(
        self,
        rule_type: str,
    ) -> CreditGrantRulePayload | None:
        payload = await self._request("GET", f"/internal/v1/credit/active-grant-rules/{rule_type}")
        data = payload.get("data")
        return CreditGrantRulePayload.model_validate(data) if data is not None else None

    async def create_credit_grant_rule(
        self,
        command: CreditGrantRuleCreatePayload,
    ) -> CreditGrantRulePayload | None:
        payload = await self._request(
            "POST",
            "/internal/v1/credit/grant-rules",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return CreditGrantRulePayload.model_validate(data) if data is not None else None

    async def update_credit_grant_rule(
        self,
        rule_id: str,
        command: CreditGrantRuleUpdatePayload,
    ) -> CreditGrantRulePayload | None:
        payload = await self._request(
            "PUT",
            f"/internal/v1/credit/grant-rules/{rule_id}",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return CreditGrantRulePayload.model_validate(data) if data is not None else None

    async def toggle_credit_grant_rule(self, rule_id: str) -> CreditGrantRulePayload | None:
        payload = await self._request("POST", f"/internal/v1/credit/grant-rules/{rule_id}/toggle")
        data = payload.get("data")
        return CreditGrantRulePayload.model_validate(data) if data is not None else None

    async def delete_credit_grant_rule(self, rule_id: str) -> bool:
        payload = await self._request("DELETE", f"/internal/v1/credit/grant-rules/{rule_id}")
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    async def apply_credit_registration_bonus(
        self,
        user_id: str,
    ) -> CreditTransactionPayload | None:
        payload = await self._request("POST", f"/internal/v1/credit/users/{user_id}/registration-bonus")
        data = payload.get("data")
        return CreditTransactionPayload.model_validate(data) if data is not None else None

    async def get_credit_balance(self, user_id: str) -> int | None:
        payload = await self._request("GET", f"/internal/v1/credit/users/{user_id}/balance")
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or data.get("balance") is None:
            return None
        return int(data["balance"])

    async def get_credit_summary(self, user_id: str) -> CreditSummaryPayload | None:
        payload = await self._request("GET", f"/internal/v1/credit/users/{user_id}/summary")
        data = payload.get("data")
        return CreditSummaryPayload.model_validate(data) if data is not None else None

    async def get_credit_consumed_tokens(
        self,
        *,
        user_id: str,
        consume_type: str,
        metadata_type: str | None = None,
    ) -> int:
        payload = await self._request(
            "GET",
            f"/internal/v1/credit/users/{user_id}/consumed-tokens",
            params={"consume_type": consume_type, "metadata_type": metadata_type},
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        return int(data.get("consumed_tokens", 0)) if isinstance(data, dict) else 0

    async def process_credit_periodic_grant_rules(
        self,
        command: CreditPeriodicGrantProcessPayload | None = None,
    ) -> CreditPeriodicGrantSummaryPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/credit/periodic-grants/process",
            json=(command or CreditPeriodicGrantProcessPayload()).model_dump(mode="json"),
        )
        return CreditPeriodicGrantSummaryPayload.model_validate(payload["data"])


    async def get_credit_history(
        self,
        *,
        user_id: str | None = None,
        transaction_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> CreditHistoryPayload:
        payload = await self._request(
            "GET",
            "/internal/v1/credit/history",
            params={
                "user_id": user_id,
                "transaction_type": transaction_type,
                "limit": limit,
                "offset": offset,
            },
        )
        return CreditHistoryPayload.model_validate(payload["data"])

    async def get_credit_admin_summary(self) -> CreditAdminSummaryPayload:
        payload = await self._request("GET", "/internal/v1/credit/admin-summary")
        return CreditAdminSummaryPayload.model_validate(payload["data"])

    async def get_credit_thread_token_usage(self) -> CreditTokenUsagePayload:
        payload = await self._request("GET", "/internal/v1/credit/thread-token-usage")
        return CreditTokenUsagePayload.model_validate(payload["data"])

    async def aggregate_credit_consumption_stats(
        self,
        *,
        since: datetime,
        granularity: str = "day",
    ) -> CreditConsumptionStatsPayload:
        payload = await self._request(
            "GET",
            "/internal/v1/credit/consumption-stats",
            params={"since": since.isoformat(), "granularity": granularity},
        )
        return CreditConsumptionStatsPayload.model_validate(payload["data"])

    async def record_credit_consumption(
        self,
        command: CreditConsumptionCreatePayload,
    ) -> tuple[CreditTransactionPayload | None, int]:
        payload = await self._request(
            "POST",
            "/internal/v1/credit/consume",
            json=command.model_dump(mode="json"),
        )
        data = payload["data"]
        transaction = data.get("transaction")
        return (
            CreditTransactionPayload.model_validate(transaction) if transaction else None,
            int(data.get("balance_before", 0)),
        )

    async def refund_credit_consumption(
        self,
        command: CreditRefundPayload,
    ) -> CreditTransactionPayload | None:
        payload = await self._request(
            "POST",
            "/internal/v1/credit/refund",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return CreditTransactionPayload.model_validate(data) if data is not None else None

    async def admin_adjust_credit(
        self,
        command: CreditAdminAdjustPayload,
    ) -> CreditTransactionPayload | None:
        payload = await self._request(
            "POST",
            "/internal/v1/credit/admin-adjust",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return CreditTransactionPayload.model_validate(data) if data is not None else None

    async def create_credit_redeem_code(
        self,
        command: CreditRedeemCodeCreatePayload,
    ) -> CreditRedeemCodePayload | None:
        payload = await self._request(
            "POST",
            "/internal/v1/credit/redeem-codes",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return CreditRedeemCodePayload.model_validate(data) if data is not None else None

    async def list_credit_redeem_codes(
        self,
        *,
        batch_id: str | None = None,
        enabled: bool | None = None,
        keyword: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CreditRedeemCodePayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/credit/redeem-codes",
            params={
                "batch_id": batch_id,
                "enabled": enabled,
                "keyword": keyword,
                "limit": limit,
                "offset": offset,
            },
        )
        return [CreditRedeemCodePayload.model_validate(item) for item in payload["data"]]

    async def disable_credit_redeem_code(
        self,
        code_id: str,
    ) -> CreditRedeemCodePayload | None:
        payload = await self._request("POST", f"/internal/v1/credit/redeem-codes/{code_id}/disable")
        data = payload.get("data")
        return CreditRedeemCodePayload.model_validate(data) if data is not None else None

    async def redeem_credit_code(
        self,
        command: CreditRedeemPayload,
    ) -> CreditTransactionPayload | None:
        payload = await self._request(
            "POST",
            "/internal/v1/credit/redeem",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return CreditTransactionPayload.model_validate(data) if data is not None else None

    async def record_credit_referral(
        self,
        command: CreditReferralCreatePayload,
    ) -> CreditReferralPayload | None:
        payload = await self._request(
            "POST",
            "/internal/v1/credit/referrals",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return CreditReferralPayload.model_validate(data) if data is not None else None

    async def get_credit_referral_by_referee(
        self,
        referee_user_id: str,
    ) -> CreditReferralPayload | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/credit/referrals/by-referee/{referee_user_id}",
        )
        data = payload.get("data")
        return CreditReferralPayload.model_validate(data) if data is not None else None

    async def apply_credit_referee_signup_bonus(
        self,
        referee_user_id: str,
    ) -> CreditTransactionPayload | None:
        payload = await self._request(
            "POST",
            f"/internal/v1/credit/referrals/{referee_user_id}/apply-referee-signup",
        )
        data = payload.get("data")
        return CreditTransactionPayload.model_validate(data) if data is not None else None

    async def apply_credit_referrer_first_task_bonus(
        self,
        referee_user_id: str,
    ) -> CreditTransactionPayload | None:
        payload = await self._request(
            "POST",
            f"/internal/v1/credit/referrals/{referee_user_id}/apply-referrer-first-task",
        )
        data = payload.get("data")
        return CreditTransactionPayload.model_validate(data) if data is not None else None

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

    async def create_conversation_thread(
        self,
        command: ConversationThreadCreatePayload,
    ) -> ConversationThreadPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/conversations/threads",
            json=command.model_dump(mode="json"),
        )
        return ConversationThreadPayload.model_validate(payload["data"])

    async def get_conversation_thread(self, thread_id: str) -> ConversationThreadPayload | None:
        payload = await self._request("GET", f"/internal/v1/conversations/threads/{thread_id}")
        data = payload.get("data")
        return ConversationThreadPayload.model_validate(data) if data is not None else None

    async def get_owned_conversation_thread(
        self,
        *,
        thread_id: str,
        user_id: str,
    ) -> ConversationThreadPayload | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/conversations/threads/{thread_id}/owned",
            params={"user_id": user_id},
        )
        data = payload.get("data")
        return ConversationThreadPayload.model_validate(data) if data is not None else None

    async def get_latest_workspace_conversation_thread(
        self,
        *,
        user_id: str,
        workspace_id: str,
    ) -> ConversationThreadPayload | None:
        payload = await self._request(
            "GET",
            "/internal/v1/conversations/workspace-threads/latest",
            params={"user_id": user_id, "workspace_id": workspace_id},
        )
        data = payload.get("data")
        return ConversationThreadPayload.model_validate(data) if data is not None else None

    async def list_workspace_conversation_thread_summaries(
        self,
        *,
        workspace_id: str,
        limit: int = 20,
    ) -> list[ConversationThreadPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/conversations/workspace-threads/summaries",
            params={"workspace_id": workspace_id, "limit": limit},
        )
        return [ConversationThreadPayload.model_validate(item) for item in payload["data"]]

    async def list_conversation_threads(
        self,
        *,
        user_id: str,
        workspace_id: str | None = None,
        limit: int = 20,
    ) -> list[ConversationThreadPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/conversations/threads",
            params={"user_id": user_id, "workspace_id": workspace_id, "limit": limit},
        )
        return [ConversationThreadPayload.model_validate(item) for item in payload["data"]]

    async def update_conversation_thread(
        self,
        thread_id: str,
        command: ConversationThreadUpdatePayload,
    ) -> ConversationThreadPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/conversations/threads/{thread_id}",
            json=command.model_dump(mode="json", exclude_unset=True),
        )
        data = payload.get("data")
        return ConversationThreadPayload.model_validate(data) if data is not None else None

    async def delete_conversation_thread(self, *, thread_id: str, user_id: str) -> bool:
        payload = await self._request(
            "DELETE",
            f"/internal/v1/conversations/threads/{thread_id}",
            params={"user_id": user_id},
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    async def lock_conversation_thread(self, thread_id: str) -> bool:
        payload = await self._request("POST", f"/internal/v1/conversations/threads/{thread_id}/lock")
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("locked")) if isinstance(data, dict) else False

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

    async def has_catalog_capabilities(self) -> bool:
        payload = await self._request("GET", "/internal/v1/catalog/capabilities/exists")
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("exists")) if isinstance(data, dict) else False

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

    async def upsert_catalog_capability(
        self,
        *,
        workspace_type: str,
        capability_id: str,
        command: CatalogUpsertPayload,
    ) -> CapabilityDefinitionPayload:
        payload = await self._request(
            "PUT",
            f"/internal/v1/catalog/capabilities/{workspace_type}/{capability_id}",
            json=command.model_dump(mode="json"),
        )
        return CapabilityDefinitionPayload.model_validate(payload["data"])

    async def delete_catalog_capability(
        self,
        *,
        workspace_type: str,
        capability_id: str,
    ) -> bool:
        payload = await self._request(
            "DELETE",
            f"/internal/v1/catalog/capabilities/{workspace_type}/{capability_id}",
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    async def set_catalog_capability_enabled(
        self,
        *,
        workspace_type: str,
        capability_id: str,
        command: CatalogEnabledPayload,
    ) -> CapabilityDefinitionPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/catalog/capabilities/{workspace_type}/{capability_id}/enabled",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return CapabilityDefinitionPayload.model_validate(data) if data is not None else None

    async def load_catalog_capability_seed_items(
        self,
        command: CatalogSeedLoadPayload,
    ) -> CatalogSeedLoadResultPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/catalog/capabilities/seed-load",
            json=command.model_dump(mode="json"),
        )
        return CatalogSeedLoadResultPayload.model_validate(payload["data"])

    async def list_catalog_skills(self, *, enabled_only: bool = False) -> list[CapabilitySkillPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/catalog/skills",
            params={"enabled_only": enabled_only},
        )
        return [CapabilitySkillPayload.model_validate(item) for item in payload["data"]]

    async def has_catalog_skills(self) -> bool:
        payload = await self._request("GET", "/internal/v1/catalog/skills/exists")
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("exists")) if isinstance(data, dict) else False

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

    async def upsert_catalog_skill(
        self,
        skill_id: str,
        command: CatalogUpsertPayload,
    ) -> CapabilitySkillPayload:
        payload = await self._request(
            "PUT",
            f"/internal/v1/catalog/skills/{skill_id}",
            json=command.model_dump(mode="json"),
        )
        return CapabilitySkillPayload.model_validate(payload["data"])

    async def delete_catalog_skill(self, skill_id: str) -> bool:
        payload = await self._request("DELETE", f"/internal/v1/catalog/skills/{skill_id}")
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    async def set_catalog_skill_enabled(
        self,
        skill_id: str,
        command: CatalogEnabledPayload,
    ) -> CapabilitySkillPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/catalog/skills/{skill_id}/enabled",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return CapabilitySkillPayload.model_validate(data) if data is not None else None

    async def load_catalog_skill_seed_items(
        self,
        command: CatalogSeedLoadPayload,
    ) -> CatalogSeedLoadResultPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/catalog/skills/seed-load",
            json=command.model_dump(mode="json"),
        )
        return CatalogSeedLoadResultPayload.model_validate(payload["data"])

    async def record_catalog_admin_log(
        self,
        command: CatalogAdminLogCreatePayload,
    ) -> CatalogAdminLogPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/catalog/admin-logs",
            json=command.model_dump(mode="json"),
        )
        return CatalogAdminLogPayload.model_validate(payload["data"])

    async def list_catalog_admin_logs(
        self,
        *,
        action: str | None = None,
        target_user_id: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[CatalogAdminLogPayload], int]:
        payload = await self._request(
            "GET",
            "/internal/v1/catalog/admin-logs",
            params={
                "action": action,
                "target_user_id": target_user_id,
                "offset": offset,
                "limit": limit,
            },
        )
        data = payload.get("data") or {}
        return (
            [CatalogAdminLogPayload.model_validate(item) for item in data.get("items", [])],
            int(data.get("total", 0)),
        )

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

    async def create_legacy_artifact(
        self,
        command: LegacyArtifactCreatePayload,
    ) -> LegacyArtifactPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/assets/legacy-artifacts",
            json=command.model_dump(mode="json"),
        )
        return LegacyArtifactPayload.model_validate(payload["data"])

    async def get_legacy_artifact(self, artifact_id: str) -> LegacyArtifactPayload | None:
        payload = await self._request("GET", f"/internal/v1/assets/legacy-artifacts/{artifact_id}")
        data = payload.get("data")
        return LegacyArtifactPayload.model_validate(data) if data is not None else None

    async def find_latest_legacy_artifact(
        self,
        *,
        workspace_id: str,
        artifact_type: str,
        title: str,
    ) -> LegacyArtifactPayload | None:
        payload = await self._request(
            "GET",
            "/internal/v1/assets/legacy-artifacts/latest",
            params={"workspace_id": workspace_id, "artifact_type": artifact_type, "title": title},
        )
        data = payload.get("data")
        return LegacyArtifactPayload.model_validate(data) if data is not None else None

    async def list_legacy_artifacts(
        self,
        *,
        workspace_id: str,
        artifact_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[LegacyArtifactPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/assets/legacy-artifacts",
            params={
                "workspace_id": workspace_id,
                "artifact_type": artifact_type,
                "status": status,
                "limit": limit,
                "offset": offset,
            },
        )
        return [LegacyArtifactPayload.model_validate(item) for item in payload["data"]]

    async def list_legacy_artifact_versions(
        self,
        *,
        workspace_id: str,
        artifact_type: str,
        title: str,
    ) -> list[LegacyArtifactPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/assets/legacy-artifacts/versions",
            params={"workspace_id": workspace_id, "artifact_type": artifact_type, "title": title},
        )
        return [LegacyArtifactPayload.model_validate(item) for item in payload["data"]]

    async def update_legacy_artifact(
        self,
        artifact_id: str,
        command: LegacyArtifactUpdatePayload,
    ) -> LegacyArtifactPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/assets/legacy-artifacts/{artifact_id}",
            json=command.model_dump(mode="json", exclude_unset=True),
        )
        data = payload.get("data")
        return LegacyArtifactPayload.model_validate(data) if data is not None else None

    async def delete_legacy_artifact(self, artifact_id: str) -> bool:
        payload = await self._request("DELETE", f"/internal/v1/assets/legacy-artifacts/{artifact_id}")
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    async def get_legacy_artifact_lineage(self, artifact_id: str) -> list[LegacyArtifactPayload]:
        payload = await self._request("GET", f"/internal/v1/assets/legacy-artifacts/{artifact_id}/lineage")
        return [LegacyArtifactPayload.model_validate(item) for item in payload["data"]]

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

    async def upsert_source(self, command: SourceCreatePayload) -> SourcePayload:
        payload = await self._request(
            "POST",
            "/internal/v1/sources/upsert",
            json=command.model_dump(mode="json"),
        )
        return SourcePayload.model_validate(payload["data"])

    async def import_source(self, command: SourceImportPayload) -> SourceImportResultPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/sources/import",
            json=command.model_dump(mode="json"),
        )
        return SourceImportResultPayload.model_validate(payload["data"])

    async def list_sources(
        self,
        *,
        workspace_id: str,
        library_status: str | None = None,
        source_kind: str | None = None,
        ingest_kind: str | None = None,
        query: str | None = None,
        include_deleted: bool = False,
        include_excluded: bool = True,
        offset: int = 0,
        limit: int = 50,
    ) -> list[SourcePayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/sources",
            params={
                "workspace_id": workspace_id,
                "library_status": library_status,
                "source_kind": source_kind,
                "ingest_kind": ingest_kind,
                "query": query,
                "include_deleted": include_deleted,
                "include_excluded": include_excluded,
                "offset": offset,
                "limit": limit,
            },
        )
        return [SourcePayload.model_validate(item) for item in payload["data"]]

    async def count_sources(
        self,
        *,
        workspace_id: str,
        library_status: str | None = None,
        source_kind: str | None = None,
        ingest_kind: str | None = None,
        query: str | None = None,
        fulltext_status: str | None = None,
        include_deleted: bool = False,
        include_excluded: bool = False,
    ) -> int:
        payload = await self._request(
            "GET",
            "/internal/v1/sources/count",
            params={
                "workspace_id": workspace_id,
                "library_status": library_status,
                "source_kind": source_kind,
                "ingest_kind": ingest_kind,
                "query": query,
                "fulltext_status": fulltext_status,
                "include_deleted": include_deleted,
                "include_excluded": include_excluded,
            },
        )
        return int(payload["data"]["count"])

    async def count_source_reference_summary(self, *, workspace_id: str) -> dict[str, int]:
        payload = await self._request(
            "GET",
            "/internal/v1/sources/count/reference-summary",
            params={"workspace_id": workspace_id},
        )
        return dict(payload["data"])

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

    async def get_workspace_toc_summary(self, workspace_id: str) -> str:
        return await self.get_source_toc_summary(workspace_id=workspace_id)

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

    async def get_source_detail(
        self,
        *,
        source_id: str,
        workspace_id: str,
    ) -> dict[str, Any] | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/sources/{source_id}/detail",
            params={"workspace_id": workspace_id},
        )
        data = payload.get("data")
        return dict(data) if isinstance(data, dict) else None

    async def upsert_source_external_ids(
        self,
        *,
        source_id: str,
        workspace_id: str,
        external_ids: list[SourceExternalIdCreatePayload],
    ) -> list[dict[str, Any]]:
        payload = await self._request(
            "POST",
            f"/internal/v1/sources/{source_id}/external-ids",
            params={"workspace_id": workspace_id},
            json=[item.model_dump(mode="json") for item in external_ids],
        )
        return list(payload["data"])

    async def list_source_external_ids(
        self,
        *,
        source_id: str,
        workspace_id: str,
    ) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET",
            f"/internal/v1/sources/{source_id}/external-ids",
            params={"workspace_id": workspace_id},
        )
        return list(payload["data"])

    async def get_source_asset(
        self,
        *,
        source_asset_id: str,
        workspace_id: str,
    ) -> dict[str, Any] | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/source-assets/{source_asset_id}",
            params={"workspace_id": workspace_id},
        )
        data = payload.get("data")
        return dict(data) if isinstance(data, dict) else None

    async def update_source_asset(
        self,
        *,
        source_asset_id: str,
        workspace_id: str,
        command: SourceAssetUpdatePayload,
    ) -> dict[str, Any] | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/source-assets/{source_asset_id}",
            params={"workspace_id": workspace_id},
            json=command.model_dump(mode="json", exclude_none=True),
        )
        data = payload.get("data")
        return dict(data) if isinstance(data, dict) else None

    async def update_source(
        self,
        *,
        source_id: str,
        workspace_id: str,
        command: SourceUpdatePayload,
    ) -> SourcePayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/sources/{source_id}",
            params={"workspace_id": workspace_id},
            json=command.model_dump(mode="json", exclude_none=True),
        )
        data = payload.get("data")
        return SourcePayload.model_validate(data) if data is not None else None

    async def delete_source(
        self,
        *,
        source_id: str,
        workspace_id: str,
    ) -> bool:
        payload = await self._request(
            "DELETE",
            f"/internal/v1/sources/{source_id}",
            params={"workspace_id": workspace_id},
        )
        return bool(payload["data"].get("deleted"))

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

    async def build_bibliography(
        self,
        command: SourceBibliographyCreatePayload,
    ) -> SourceBibliographyPayload:
        return await self.build_source_bibliography(command)

    async def create_source_bibliography_snapshot(
        self,
        command: SourceBibliographySnapshotCreatePayload,
    ) -> SourceBibliographySnapshotPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/sources/bibliography/snapshots",
            json=command.model_dump(mode="json"),
        )
        return SourceBibliographySnapshotPayload.model_validate(payload["data"])

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

    async def record_citation_usage(
        self,
        command: SourceCitationUsageCreatePayload,
    ) -> SourceCitationUsagePayload:
        return await self.record_source_citation_usage(command)

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

    async def get_workspace_stats_for_member(self, user_id: str) -> WorkspaceStatsPayload:
        payload = await self._request("GET", f"/internal/v1/workspaces/stats/member/{user_id}")
        return WorkspaceStatsPayload.model_validate(payload["data"])

    async def get_admin_workspace_stats(self) -> WorkspaceAdminStatsPayload:
        payload = await self._request("GET", "/internal/v1/workspaces/stats/admin")
        return WorkspaceAdminStatsPayload.model_validate(payload["data"])

    async def get_workspace(self, workspace_id: str) -> WorkspacePayload | None:
        payload = await self._request("GET", f"/internal/v1/workspaces/{workspace_id}")
        data = payload.get("data")
        return WorkspacePayload.model_validate(data) if data is not None else None

    async def workspace_has_active_membership(
        self,
        *,
        workspace_id: str,
        user_id: str,
    ) -> bool:
        payload = await self._request(
            "GET",
            f"/internal/v1/workspaces/{workspace_id}/members/{user_id}/active",
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("has_active_membership")) if isinstance(data, dict) else False

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
