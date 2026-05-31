"""Async HTTP client for DataService."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from src.config import dataservice_settings
from src.dataservice_client.catalog_client import CatalogDataServiceClientMixin
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
    WorkspaceArtifactCreatePayload,
    WorkspaceArtifactPayload,
    WorkspaceArtifactUpdatePayload,
    WorkspaceAssetCreatePayload,
    WorkspaceAssetDownloadPayload,
    WorkspaceAssetPayload,
    WorkspaceAssetUpdatePayload,
)
from src.dataservice_client.contracts.audit import AuditLogCreatePayload, AuditLogPayload
from src.dataservice_client.contracts.conversation import (
    ConversationMessageCreatePayload,
    ConversationMessagePayload,
    ConversationMessagesRebuildPayload,
    ConversationThreadCreatePayload,
    ConversationThreadPayload,
    ConversationThreadUpdatePayload,
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
    PrismProtectedScopePayload,
    PrismProtectedScopeUpsertPayload,
    PrismSurfacePayload,
)
from src.dataservice_client.contracts.prism_review import (
    PrismFileChangeAppliedPayload,
    PrismFileChangeClearPayload,
    PrismFileChangeRejectedPayload,
    PrismFileChangeUpsertPayload,
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
from src.dataservice_client.contracts.task import (
    TaskRecordCompletedPayload,
    TaskRecordCreateGuardedPayload,
    TaskRecordCreatePayload,
    TaskRecordPatchPayload,
    TaskRecordPayload,
    TaskRecordRuntimeStatePayload,
    TaskRecordStartedPayload,
)
from src.dataservice_client.credit_client import CreditDataServiceClientMixin
from src.dataservice_client.errors import DataServiceClientError
from src.dataservice_client.execution_client import ExecutionDataServiceClientMixin
from src.dataservice_client.model_catalog_client import ModelCatalogDataServiceClientMixin
from src.dataservice_client.pricing_client import PricingDataServiceClientMixin
from src.dataservice_client.sandbox_client import SandboxDataServiceClientMixin
from src.dataservice_client.source_client import SourceDataServiceClientMixin
from src.dataservice_client.workspace_client import WorkspaceDataServiceClientMixin


def _clean_request_params(params: Any) -> Any:
    """Remove absent query params before handing them to httpx.

    httpx serializes ``None`` query values as empty strings. DataService treats
    those empty strings as real filter values, so optional params must be
    stripped at the client boundary.
    """
    if not isinstance(params, dict):
        return params

    cleaned: dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, list):
            normalized = [item for item in value if item is not None]
            if not normalized:
                continue
            cleaned[key] = normalized
            continue
        cleaned[key] = value
    return cleaned


class AsyncDataServiceClient(
    ExecutionDataServiceClientMixin,
    SourceDataServiceClientMixin,
    CreditDataServiceClientMixin,
    CatalogDataServiceClientMixin,
    WorkspaceDataServiceClientMixin,
    ModelCatalogDataServiceClientMixin,
    PricingDataServiceClientMixin,
    SandboxDataServiceClientMixin,
):
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
            trust_env=False,
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

    async def get_latex_binding_integrity_report(
        self,
        *,
        user_id: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        payload = await self._request(
            "GET",
            "/internal/v1/latex/binding-integrity",
            params={"user_id": user_id},
        )
        data = payload.get("data") or {}
        return {
            "missing_primary": list(data.get("missing_primary") or []),
            "duplicate_primary": list(data.get("duplicate_primary") or []),
        }

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

    async def count_active_admins(self) -> int:
        payload = await self._request("GET", "/internal/v1/account/admins/active-count")
        return int(payload["data"]["count"])

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

    async def create_workspace_artifact(
        self,
        command: WorkspaceArtifactCreatePayload,
    ) -> WorkspaceArtifactPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/assets/artifacts",
            json=command.model_dump(mode="json"),
        )
        return WorkspaceArtifactPayload.model_validate(payload["data"])

    async def get_workspace_artifact(self, artifact_id: str) -> WorkspaceArtifactPayload | None:
        payload = await self._request("GET", f"/internal/v1/assets/artifacts/{artifact_id}")
        data = payload.get("data")
        return WorkspaceArtifactPayload.model_validate(data) if data is not None else None

    async def find_latest_workspace_artifact(
        self,
        *,
        workspace_id: str,
        artifact_type: str,
        title: str,
    ) -> WorkspaceArtifactPayload | None:
        payload = await self._request(
            "GET",
            "/internal/v1/assets/artifacts/latest",
            params={"workspace_id": workspace_id, "artifact_type": artifact_type, "title": title},
        )
        data = payload.get("data")
        return WorkspaceArtifactPayload.model_validate(data) if data is not None else None

    async def list_workspace_artifacts(
        self,
        *,
        workspace_id: str,
        artifact_type: str | None = None,
        artifact_types: list[str] | None = None,
        status: str | None = None,
        created_by_skill: str | None = None,
        created_by_skills: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkspaceArtifactPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/assets/artifacts",
            params={
                "workspace_id": workspace_id,
                "artifact_type": artifact_type,
                "artifact_types": artifact_types,
                "status": status,
                "created_by_skill": created_by_skill,
                "created_by_skills": created_by_skills,
                "limit": limit,
                "offset": offset,
            },
        )
        return [WorkspaceArtifactPayload.model_validate(item) for item in payload["data"]]

    async def count_workspace_artifacts(
        self,
        *,
        workspace_id: str | None = None,
        artifact_type: str | None = None,
        created_by_skill: str | None = None,
        created_by_skills: list[str] | None = None,
    ) -> int:
        payload = await self._request(
            "GET",
            "/internal/v1/assets/artifacts/count",
            params={
                "workspace_id": workspace_id,
                "artifact_type": artifact_type,
                "created_by_skill": created_by_skill,
                "created_by_skills": created_by_skills,
            },
        )
        return int(payload["data"]["count"])

    async def list_workspace_artifact_versions(
        self,
        *,
        workspace_id: str,
        artifact_type: str,
        title: str,
    ) -> list[WorkspaceArtifactPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/assets/artifacts/versions",
            params={"workspace_id": workspace_id, "artifact_type": artifact_type, "title": title},
        )
        return [WorkspaceArtifactPayload.model_validate(item) for item in payload["data"]]

    async def update_workspace_artifact(
        self,
        artifact_id: str,
        command: WorkspaceArtifactUpdatePayload,
    ) -> WorkspaceArtifactPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/assets/artifacts/{artifact_id}",
            json=command.model_dump(mode="json", exclude_unset=True),
        )
        data = payload.get("data")
        return WorkspaceArtifactPayload.model_validate(data) if data is not None else None

    async def delete_workspace_artifact(self, artifact_id: str) -> bool:
        payload = await self._request("DELETE", f"/internal/v1/assets/artifacts/{artifact_id}")
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    async def get_workspace_artifact_lineage(self, artifact_id: str) -> list[WorkspaceArtifactPayload]:
        payload = await self._request("GET", f"/internal/v1/assets/artifacts/{artifact_id}/lineage")
        return [WorkspaceArtifactPayload.model_validate(item) for item in payload["data"]]

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

    async def upsert_latex_prism_protected_scope(
        self,
        command: PrismProtectedScopeUpsertPayload,
    ) -> PrismProtectedScopePayload | None:
        payload = await self._request(
            "PUT",
            f"/internal/v1/prism/workspaces/{command.workspace_id}/latex-protected-scope",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return PrismProtectedScopePayload.model_validate(data) if data is not None else None

    async def list_prism_protected_scopes(
        self,
        project_id: str,
        *,
        limit: int = 200,
    ) -> list[PrismProtectedScopePayload]:
        payload = await self._request(
            "GET",
            f"/internal/v1/prism/projects/{project_id}/protected-scopes",
            params={"limit": limit},
        )
        return [PrismProtectedScopePayload.model_validate(item) for item in payload["data"]]

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
        if "params" in kwargs:
            kwargs["params"] = _clean_request_params(kwargs["params"])
        response = await self._client.request(method, path, headers=headers, **kwargs)
        if response.status_code >= 400:
            raise DataServiceClientError.from_response(response)
        payload = response.json()
        if not isinstance(payload, dict):
            raise DataServiceClientError(f"DataService returned non-object payload from {path}")
        return payload
