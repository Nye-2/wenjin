"""DataService foundation tests."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src.database.base import Base
from src.dataservice.common.api import envelope_error, envelope_ok
from src.dataservice.common.idempotency import IdempotencyScope, make_request_hash, make_scope_hash
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.operations.models import (
    DataServiceIdempotencyKey,
    DataServiceMigrationReport,
    DataServiceOutboxEvent,
)
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.account import (
    AccountUserCreatePayload,
    AccountUserRolePayload,
    AccountUserStatusPayload,
)
from src.dataservice_client.contracts.audit import AuditLogCreatePayload
from src.dataservice_client.contracts.catalog import (
    AdminLogCreatePayload as CatalogAdminLogCreatePayload,
)
from src.dataservice_client.contracts.catalog import (
    CatalogEnabledPayload,
    CatalogSeedItemPayload,
    CatalogSeedLoadPayload,
    CatalogUpsertPayload,
)
from src.dataservice_client.contracts.conversation import (
    ConversationMessageCreatePayload,
    ConversationMessagesRebuildPayload,
    ConversationThreadCreatePayload,
    ConversationThreadUpdatePayload,
)
from src.dataservice_client.contracts.credit import (
    CreditAdminAdjustPayload,
    CreditConsumptionCreatePayload,
    CreditGrantRuleCreatePayload,
    CreditGrantRuleUpdatePayload,
    CreditRedeemCodeCreatePayload,
    CreditRedeemPayload,
    CreditReferralCreatePayload,
    CreditRefundPayload,
)
from src.dataservice_client.contracts.execution import (
    ComputeSessionEnsurePayload,
    ComputeSessionUpdatePayload,
    ExecutionNodePatchPayload,
    ExecutionNodeUpsertPayload,
)
from src.dataservice_client.contracts.knowledge import (
    KnowledgeArchiveLowConfidencePayload,
    KnowledgeMemoryCreatePayload,
    KnowledgeMemoryUpdatePayload,
)
from src.dataservice_client.contracts.latex import (
    LatexCompileHistoryCreatePayload,
    LatexProjectAttachWorkspacePayload,
    LatexProjectCreatePayload,
    LatexProjectTouchPayload,
    LatexProjectUpdatePayload,
)
from src.dataservice_client.contracts.prism_review import (
    PrismFileChangeAppliedPayload,
    PrismFileChangeClearPayload,
    PrismFileChangeRejectedPayload,
    PrismFileChangeUpsertPayload,
)
from src.dataservice_client.contracts.provenance import ProvenanceLinkCreatePayload
from src.dataservice_client.contracts.task import (
    TaskRecordCompletedPayload,
    TaskRecordCreateGuardedPayload,
    TaskRecordCreatePayload,
    TaskRecordPatchPayload,
    TaskRecordRuntimeStatePayload,
    TaskRecordStartedPayload,
)
from src.dataservice_client.contracts.template import (
    WorkspaceTemplateCreatePayload,
    WorkspaceTemplateDeactivatePayload,
)
from src.dataservice_client.contracts.workspace import WorkspaceCreatePayload, WorkspaceUpdatePayload


def test_operations_models_are_registered_on_shared_metadata() -> None:
    assert DataServiceIdempotencyKey.__tablename__ in Base.metadata.tables
    assert DataServiceOutboxEvent.__tablename__ in Base.metadata.tables
    assert DataServiceMigrationReport.__tablename__ in Base.metadata.tables


def test_response_envelope_contract() -> None:
    assert envelope_ok({"value": 1}, trace_id="trace-1") == {
        "status": "ok",
        "data": {"value": 1},
        "trace_id": "trace-1",
    }
    assert envelope_error(code="x", message="failed") == {
        "status": "error",
        "error": {"code": "x", "message": "failed"},
    }


def test_idempotency_hashes_are_stable_and_sensitive_to_scope() -> None:
    payload_a = {"b": 2, "a": 1}
    payload_b = {"a": 1, "b": 2}
    assert make_request_hash(payload_a) == make_request_hash(payload_b)

    base = IdempotencyScope(
        source_service="gateway",
        command_name="workspace.create",
        workspace_id="workspace-1",
        actor_user_id="user-1",
    )
    other_actor = base.model_copy(update={"actor_user_id": "user-2"})
    assert make_scope_hash(base) != make_scope_hash(other_actor)


def test_livez_endpoint_does_not_require_database() -> None:
    from src.dataservice_app.routers.health import router

    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get("/livez")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "dataservice"}


def test_internal_auth_uses_stable_error_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.dataservice.common.errors import DataServiceError
    from src.dataservice_app import auth as auth_module
    from src.dataservice_app.app import handle_dataservice_error

    monkeypatch.setattr(auth_module.dataservice_settings, "internal_token", "expected")

    app = FastAPI()
    app.add_exception_handler(DataServiceError, handle_dataservice_error)

    @app.get("/protected")
    async def protected(_: None = Depends(auth_module.require_internal_token)) -> dict[str, bool]:
        return {"ok": True}

    response = TestClient(app).get("/protected", headers={"X-Wenjin-Internal-Token": "wrong"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED_INTERNAL_CALL"


@pytest.mark.asyncio
async def test_uow_rolls_back_when_not_committed() -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.committed = False
            self.rolled_back = False
            self.closed = False
            self.added: list[Any] = []

        async def commit(self) -> None:
            self.committed = True

        async def rollback(self) -> None:
            self.rolled_back = True

        async def close(self) -> None:
            self.closed = True

        def add(self, value: Any) -> None:
            self.added.append(value)

    session = FakeSession()

    async with DataServiceUnitOfWork(session=session):  # type: ignore[arg-type]
        pass

    assert session.rolled_back is True
    assert session.committed is False
    assert session.closed is False


@pytest.mark.asyncio
async def test_dataservice_client_sends_internal_token() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Wenjin-Internal-Token"] == "secret"
        return httpx.Response(200, json={"status": "ok", "data": {"received": True}})

    transport = httpx.MockTransport(handler)
    async with AsyncDataServiceClient(
        base_url="http://dataservice",
        internal_token="secret",
        transport=transport,
    ) as client:
        result = await client._request("GET", "/protected")

    assert result == {"status": "ok", "data": {"received": True}}


@pytest.mark.asyncio
async def test_dataservice_client_workspace_contract_methods() -> None:
    seen: list[tuple[str, str, dict[str, Any] | None]] = []

    def workspace_payload(workspace_id: str = "workspace-1") -> dict[str, Any]:
        return {
            "id": workspace_id,
            "created_by_user_id": "user-1",
            "name": "Workspace",
            "workspace_type": "thesis",
            "settings_json": {"language": "zh"},
            "active_thread_id": None,
        }

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else None
        seen.append((request.method, request.url.path, body))
        if request.method == "POST":
            return httpx.Response(200, json={"status": "ok", "data": workspace_payload()})
        if request.method == "GET" and request.url.path == "/internal/v1/workspaces":
            return httpx.Response(200, json={"status": "ok", "data": [workspace_payload()]})
        if request.method == "GET" and request.url.path.endswith("/stats/member/user-1"):
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "data": {"total": 2, "by_type": {"thesis": 1}, "created_last_7d": 1},
                },
            )
        if request.method == "GET" and request.url.path.endswith("/stats/admin"):
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "data": {"total": 3, "by_type": {"sci": 2}, "users_with_workspaces": 2},
                },
            )
        if request.method == "GET" and request.url.path.endswith("/members/user-1/active"):
            return httpx.Response(
                200,
                json={"status": "ok", "data": {"has_active_membership": True}},
            )
        if request.method == "GET":
            return httpx.Response(200, json={"status": "ok", "data": workspace_payload("workspace-2")})
        if request.method == "PUT":
            payload = workspace_payload("workspace-2")
            payload["name"] = body["name"] if body else "Updated"
            return httpx.Response(200, json={"status": "ok", "data": payload})
        return httpx.Response(200, json={"status": "ok", "data": {"deleted": True}})

    transport = httpx.MockTransport(handler)
    async with AsyncDataServiceClient(
        base_url="http://dataservice",
        internal_token="secret",
        transport=transport,
    ) as client:
        created = await client.create_workspace(
            WorkspaceCreatePayload(
                created_by_user_id="user-1",
                name="Workspace",
                workspace_type="thesis",
                settings_json={"language": "zh"},
            )
        )
        listed = await client.list_workspaces(member_user_id="user-1")
        member_stats = await client.get_workspace_stats_for_member("user-1")
        admin_stats = await client.get_admin_workspace_stats()
        fetched = await client.get_workspace("workspace-2")
        has_membership = await client.workspace_has_active_membership(
            workspace_id="workspace-2",
            user_id="user-1",
        )
        updated = await client.update_workspace(
            "workspace-2",
            WorkspaceUpdatePayload(name="Updated"),
        )
        deleted = await client.delete_workspace("workspace-2")

    assert created.workspace_type == "thesis"
    assert listed[0].id == "workspace-1"
    assert member_stats.total == 2
    assert admin_stats.users_with_workspaces == 2
    assert fetched is not None
    assert fetched.id == "workspace-2"
    assert has_membership is True
    assert updated is not None
    assert updated.name == "Updated"
    assert deleted is True
    assert seen == [
        (
            "POST",
            "/internal/v1/workspaces",
            {
                "created_by_user_id": "user-1",
                "name": "Workspace",
                "workspace_type": "thesis",
                "discipline": None,
                "description": None,
                "settings_json": {"language": "zh"},
            },
        ),
        ("GET", "/internal/v1/workspaces", None),
        ("GET", "/internal/v1/workspaces/stats/member/user-1", None),
        ("GET", "/internal/v1/workspaces/stats/admin", None),
        ("GET", "/internal/v1/workspaces/workspace-2", None),
        ("GET", "/internal/v1/workspaces/workspace-2/members/user-1/active", None),
        (
            "PUT",
            "/internal/v1/workspaces/workspace-2",
            {"name": "Updated"},
        ),
        ("DELETE", "/internal/v1/workspaces/workspace-2", None),
    ]


@pytest.mark.asyncio
async def test_dataservice_client_account_contract_methods() -> None:
    seen: list[tuple[str, str, dict[str, Any] | None]] = []

    def user_payload(user_id: str = "user-1") -> dict[str, Any]:
        return {
            "id": user_id,
            "email": "user@example.com",
            "name": "User",
            "role": "user",
            "is_active": True,
            "is_superuser": False,
            "credits": 10,
            "total_credits_earned": 20,
            "total_credits_spent": 10,
        }

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else None
        seen.append((request.method, request.url.path, body))
        path = request.url.path
        if request.method == "POST":
            return httpx.Response(200, json={"status": "ok", "data": user_payload()})
        if path.endswith("/admin-stats"):
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "data": {"total_users": 3, "active_users": 2, "admin_users": 1},
                },
            )
        if path.endswith("/growth"):
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "data": {
                        "total_users": 3,
                        "new_in_range": 1,
                        "time_series": [{"date": "2026-05-22T00:00:00", "signups": 1}],
                    },
                },
            )
        if request.method == "GET" and path == "/internal/v1/account/users":
            return httpx.Response(
                200,
                json={"status": "ok", "data": {"users": [user_payload()], "total": 1}},
            )
        return httpx.Response(200, json={"status": "ok", "data": user_payload("user-2")})

    transport = httpx.MockTransport(handler)
    async with AsyncDataServiceClient(
        base_url="http://dataservice",
        internal_token="secret",
        transport=transport,
    ) as client:
        created = await client.create_account_user(
            AccountUserCreatePayload(
                email="user@example.com",
                hashed_password="hashed",
                name="User",
            )
        )
        fetched = await client.get_account_user("user-2")
        stats = await client.get_account_admin_stats()
        listed = await client.list_account_users(page=1, page_size=10)
        status = await client.update_account_user_status(
            "user-2",
            AccountUserStatusPayload(is_active=False),
        )
        role = await client.update_account_user_role(
            "user-2",
            AccountUserRolePayload(role="admin"),
        )
        growth = await client.aggregate_account_user_growth(
            since=datetime.fromisoformat("2026-05-22T00:00:00"),
        )

    assert created is not None and created.id == "user-1"
    assert fetched is not None and fetched.id == "user-2"
    assert stats.admin_users == 1
    assert listed.total == 1
    assert status is not None and status.id == "user-2"
    assert role is not None and role.id == "user-2"
    assert growth.new_in_range == 1
    assert seen == [
        (
            "POST",
            "/internal/v1/account/users",
            {
                "email": "user@example.com",
                "hashed_password": "hashed",
                "name": "User",
                "auto_commit": True,
            },
        ),
        ("GET", "/internal/v1/account/users/user-2", None),
        ("GET", "/internal/v1/account/admin-stats", None),
        ("GET", "/internal/v1/account/users", None),
        ("PATCH", "/internal/v1/account/users/user-2/status", {"is_active": False}),
        ("PATCH", "/internal/v1/account/users/user-2/role", {"role": "admin"}),
        ("GET", "/internal/v1/account/growth", None),
    ]


@pytest.mark.asyncio
async def test_dataservice_client_audit_contract_methods() -> None:
    seen: list[tuple[str, str, dict[str, Any] | None]] = []

    def audit_payload() -> dict[str, Any]:
        return {
            "id": 1,
            "action": "thread.create",
            "user_id": "user-1",
            "workspace_id": "workspace-1",
            "target_type": "thread",
            "target_id": "thread-1",
            "payload": {},
        }

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else None
        seen.append((request.method, request.url.path, body))
        data = [audit_payload()] if request.method == "GET" else audit_payload()
        return httpx.Response(200, json={"status": "ok", "data": data})

    transport = httpx.MockTransport(handler)
    async with AsyncDataServiceClient(
        base_url="http://dataservice",
        internal_token="secret",
        transport=transport,
    ) as client:
        created = await client.create_audit_log(
            AuditLogCreatePayload(
                action="thread.create",
                user_id="user-1",
                workspace_id="workspace-1",
                target_type="thread",
                target_id="thread-1",
            )
        )
        listed = await client.query_audit_logs(workspace_id="workspace-1")

    assert created.id == 1
    assert listed[0].action == "thread.create"
    assert seen == [
        (
            "POST",
            "/internal/v1/audit/logs",
            {
                "action": "thread.create",
                "user_id": "user-1",
                "workspace_id": "workspace-1",
                "target_type": "thread",
                "target_id": "thread-1",
                "payload": {},
                "ip": None,
                "ua": None,
            },
        ),
        ("GET", "/internal/v1/audit/logs", None),
    ]


@pytest.mark.asyncio
async def test_dataservice_client_template_contract_methods() -> None:
    seen: list[tuple[str, str, dict[str, Any] | None]] = []

    def template_payload(template_id: str = "template-1") -> dict[str, Any]:
        return {
            "id": template_id,
            "workspace_id": "workspace-1",
            "name": "Template",
            "category": "thesis",
            "source_type": "upload",
            "structure": {},
            "format_spec": {},
            "content_guidelines": {},
            "is_active": True,
            "is_builtin": False,
        }

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else None
        seen.append((request.method, request.url.path, body))
        path = request.url.path
        if request.method == "DELETE":
            return httpx.Response(200, json={"status": "ok", "data": {"deleted": True}})
        if path.endswith("/deactivate-active"):
            return httpx.Response(200, json={"status": "ok", "data": {"deactivated": True}})
        if request.method == "GET" and path == "/internal/v1/templates/workspaces/workspace-1":
            return httpx.Response(200, json={"status": "ok", "data": [template_payload()]})
        return httpx.Response(200, json={"status": "ok", "data": template_payload("template-2")})

    transport = httpx.MockTransport(handler)
    async with AsyncDataServiceClient(
        base_url="http://dataservice",
        internal_token="secret",
        transport=transport,
    ) as client:
        active = await client.get_active_workspace_template("workspace-1")
        listed = await client.list_workspace_templates("workspace-1")
        created = await client.create_workspace_template(
            WorkspaceTemplateCreatePayload(
                workspace_id="workspace-1",
                name="Template",
                category="thesis",
                source_type="upload",
            )
        )
        deactivated = await client.deactivate_active_workspace_templates(
            "workspace-1",
            WorkspaceTemplateDeactivatePayload(exclude_template_id="template-2"),
        )
        activated = await client.activate_workspace_template(
            workspace_id="workspace-1",
            template_id="template-2",
        )
        fetched = await client.get_workspace_template("template-2")
        deleted = await client.delete_workspace_template(
            "template-2",
            workspace_id="workspace-1",
        )

    assert active is not None and active.id == "template-2"
    assert listed[0].id == "template-1"
    assert created is not None and created.id == "template-2"
    assert deactivated is True
    assert activated is not None and activated.id == "template-2"
    assert fetched is not None and fetched.id == "template-2"
    assert deleted is True
    assert seen == [
        ("GET", "/internal/v1/templates/workspaces/workspace-1/active", None),
        ("GET", "/internal/v1/templates/workspaces/workspace-1", None),
        (
            "POST",
            "/internal/v1/templates",
            {
                "workspace_id": "workspace-1",
                "name": "Template",
                "category": "thesis",
                "source_type": "upload",
                "source_file_path": None,
                "structure": {},
                "format_spec": {},
                "content_guidelines": {},
                "latex_preamble": None,
            },
        ),
        (
            "POST",
            "/internal/v1/templates/workspaces/workspace-1/deactivate-active",
            {"exclude_template_id": "template-2"},
        ),
        ("POST", "/internal/v1/templates/workspaces/workspace-1/template-2/activate", None),
        ("GET", "/internal/v1/templates/template-2", None),
        ("DELETE", "/internal/v1/templates/template-2", None),
    ]


@pytest.mark.asyncio
async def test_dataservice_client_catalog_contract_methods() -> None:
    seen: list[tuple[str, str, dict[str, Any] | None]] = []

    def capability_payload(capability_id: str = "idea_to_manuscript") -> dict[str, Any]:
        return {
            "id": capability_id,
            "workspace_type": "thesis",
            "schema_version": "capability.v2",
            "enabled": True,
            "tier": "primary",
            "entry_surface": "workbench",
            "display_name": "Idea to Manuscript",
            "description": "",
            "intent_description": "",
            "trigger_phrases": [],
            "required_decisions": [],
            "brief_schema": {},
            "graph_template": {},
            "ui_meta": {},
            "runtime": {},
            "dashboard_meta": {},
            "definition_json": {},
            "notes": None,
            "checksum": None,
            "source_path": None,
            "created_at": None,
            "updated_at": None,
        }

    def skill_payload(skill_id: str = "writer") -> dict[str, Any]:
        return {
            "id": skill_id,
            "schema_version": "capability_skill.v2",
            "enabled": True,
            "display_name": "Writer",
            "description": "",
            "worker_type": "writer",
            "subagent_type": "writer",
            "prompt": "",
            "allowed_tools": [],
            "resources": [],
            "config": {},
            "skill_json": {},
            "checksum": None,
            "source_path": None,
        }

    def admin_log_payload() -> dict[str, Any]:
        return {
            "id": "log-1",
            "action": "capability_create",
            "target_type": "user",
            "target_user_id": None,
            "details": {"capability_id": "idea_to_manuscript"},
            "ip_address": None,
            "created_at": None,
            "admin": {},
            "target_user": None,
        }

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else None
        seen.append((request.method, request.url.path, body))
        path = request.url.path
        if path.endswith("/exists"):
            return httpx.Response(200, json={"status": "ok", "data": {"exists": True}})
        if path.endswith("/seed-load"):
            return httpx.Response(
                200,
                json={"status": "ok", "data": {"loaded": 1, "skipped": False, "checksum": "root"}},
            )
        if request.method == "DELETE":
            return httpx.Response(200, json={"status": "ok", "data": {"deleted": True}})
        if path.endswith("/admin-logs") and request.method == "GET":
            return httpx.Response(200, json={"status": "ok", "data": {"items": [admin_log_payload()], "total": 1}})
        if path.endswith("/admin-logs"):
            return httpx.Response(200, json={"status": "ok", "data": admin_log_payload()})
        if "/skills" in path:
            data: Any = [skill_payload()] if request.method == "GET" and path.endswith("/skills") else skill_payload()
            return httpx.Response(200, json={"status": "ok", "data": data})
        data = [capability_payload()] if request.method == "GET" and path.endswith("/capabilities") else capability_payload()
        return httpx.Response(200, json={"status": "ok", "data": data})

    transport = httpx.MockTransport(handler)
    async with AsyncDataServiceClient(
        base_url="http://dataservice",
        internal_token="secret",
        transport=transport,
    ) as client:
        capabilities = await client.list_catalog_capabilities(workspace_type="thesis", enabled_only=True)
        has_capabilities = await client.has_catalog_capabilities()
        capability = await client.get_catalog_capability(
            workspace_type="thesis",
            capability_id="idea_to_manuscript",
            enabled_only=True,
        )
        upserted_capability = await client.upsert_catalog_capability(
            workspace_type="thesis",
            capability_id="idea_to_manuscript",
            command=CatalogUpsertPayload(data=capability_payload(), checksum="abc"),
        )
        toggled_capability = await client.set_catalog_capability_enabled(
            workspace_type="thesis",
            capability_id="idea_to_manuscript",
            command=CatalogEnabledPayload(enabled=False),
        )
        deleted_capability = await client.delete_catalog_capability(
            workspace_type="thesis",
            capability_id="idea_to_manuscript",
        )
        capability_seed_result = await client.load_catalog_capability_seed_items(
            CatalogSeedLoadPayload(
                seed_root="/seed/capabilities",
                overwrite=True,
                items=[
                    CatalogSeedItemPayload(
                        data=capability_payload(),
                        checksum="cap-checksum",
                        source_path="/seed/capabilities/thesis/idea.yaml",
                    )
                ],
            )
        )
        skills = await client.list_catalog_skills(enabled_only=True)
        has_skills = await client.has_catalog_skills()
        skill = await client.get_catalog_skill("writer", enabled_only=True)
        upserted_skill = await client.upsert_catalog_skill(
            "writer",
            CatalogUpsertPayload(data=skill_payload(), checksum="def"),
        )
        toggled_skill = await client.set_catalog_skill_enabled(
            "writer",
            CatalogEnabledPayload(enabled=False),
        )
        deleted_skill = await client.delete_catalog_skill("writer")
        skill_seed_result = await client.load_catalog_skill_seed_items(
            CatalogSeedLoadPayload(
                seed_root="/seed/skills",
                items=[
                    CatalogSeedItemPayload(
                        data=skill_payload(),
                        checksum="skill-checksum",
                        source_path="/seed/skills/writer.yaml",
                    )
                ],
            )
        )
        admin_log = await client.record_catalog_admin_log(
            CatalogAdminLogCreatePayload(
                action="capability_create",
                admin_id="admin-1",
                details={"capability_id": "idea_to_manuscript"},
            )
        )
        admin_logs, admin_total = await client.list_catalog_admin_logs(action="capability_create")

    assert capabilities[0].id == "idea_to_manuscript"
    assert has_capabilities is True
    assert capability is not None and capability.workspace_type == "thesis"
    assert upserted_capability.id == "idea_to_manuscript"
    assert toggled_capability is not None and toggled_capability.enabled is True
    assert deleted_capability is True
    assert capability_seed_result.loaded == 1
    assert skills[0].id == "writer"
    assert has_skills is True
    assert skill is not None and skill.subagent_type == "writer"
    assert upserted_skill.id == "writer"
    assert toggled_skill is not None and toggled_skill.enabled is True
    assert deleted_skill is True
    assert skill_seed_result.loaded == 1
    assert admin_log.action == "capability_create"
    assert admin_logs[0].id == "log-1"
    assert admin_total == 1
    assert seen[0][1] == "/internal/v1/catalog/capabilities"
    assert seen[-1][1] == "/internal/v1/catalog/admin-logs"


@pytest.mark.asyncio
async def test_dataservice_client_credit_contract_methods() -> None:
    seen: list[tuple[str, str, dict[str, Any] | None]] = []

    def rule_payload(rule_id: str = "rule-1") -> dict[str, Any]:
        return {
            "id": rule_id,
            "name": "Registration",
            "rule_type": "registration_bonus",
            "enabled": True,
            "amount": 10,
            "description": None,
            "config": {},
        }

    def tx_payload(tx_id: str = "tx-1") -> dict[str, Any]:
        return {
            "id": tx_id,
            "user_id": "user-1",
            "transaction_type": "admin_grant",
            "amount": 10,
            "balance_after": 20,
            "metadata": {},
        }

    def code_payload() -> dict[str, Any]:
        return {
            "id": "code-1",
            "code": "ABC123",
            "amount": 10,
            "max_uses": 1,
            "use_count": 0,
            "per_user_limit": 1,
            "enabled": True,
        }

    def referral_payload() -> dict[str, Any]:
        return {
            "id": "ref-1",
            "referrer_user_id": "user-a",
            "referee_user_id": "user-b",
        }

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else None
        seen.append((request.method, request.url.path, body))
        path = request.url.path
        if path == "/internal/v1/credit/grant-rules" and request.method == "GET":
            return httpx.Response(200, json={"status": "ok", "data": [rule_payload()]})
        if path.startswith("/internal/v1/credit/grant-rules"):
            if request.method == "DELETE":
                return httpx.Response(200, json={"status": "ok", "data": {"deleted": True}})
            return httpx.Response(200, json={"status": "ok", "data": rule_payload("rule-2")})
        if path.endswith("/summary"):
            return httpx.Response(
                200,
                json={"status": "ok", "data": {"credits": 20, "total_earned": 30, "total_spent": 10}},
            )
        if path.endswith("/history") or path == "/internal/v1/credit/history":
            return httpx.Response(
                200,
                json={"status": "ok", "data": {"transactions": [tx_payload()], "total": 1}},
            )
        if path.endswith("/admin-summary"):
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "data": {
                        "total_issued": 30,
                        "total_spent": 10,
                        "in_circulation": 20,
                        "manual_deductions": 0,
                        "overdraft_users": 0,
                        "overdraft_credits_total": 0,
                        "total_transactions": 1,
                    },
                },
            )
        if path.endswith("/thread-token-usage"):
            return httpx.Response(
                200,
                json={"status": "ok", "data": {"total_tokens": 100, "transactions": 1, "users": 1}},
            )
        if path.endswith("/consumption-stats"):
            return httpx.Response(
                200,
                json={"status": "ok", "data": {"kpis": {"total_issued": 30}, "credit_series": []}},
            )
        if path.startswith("/internal/v1/credit/redeem-codes"):
            data = [code_payload()] if request.method == "GET" else code_payload()
            return httpx.Response(200, json={"status": "ok", "data": data})
        if path.startswith("/internal/v1/credit/referrals"):
            return httpx.Response(200, json={"status": "ok", "data": referral_payload()})
        if path.endswith("/consume"):
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "data": {"transaction": tx_payload(), "balance_before": 20},
                },
            )
        return httpx.Response(200, json={"status": "ok", "data": tx_payload()})

    transport = httpx.MockTransport(handler)
    async with AsyncDataServiceClient(
        base_url="http://dataservice",
        internal_token="secret",
        transport=transport,
    ) as client:
        rules = await client.list_credit_grant_rules()
        fetched_rule = await client.get_credit_grant_rule("rule-2")
        created_rule = await client.create_credit_grant_rule(
            CreditGrantRuleCreatePayload(
                name="Registration",
                rule_type="registration_bonus",
                amount=10,
                admin_id="admin-1",
            )
        )
        updated_rule = await client.update_credit_grant_rule(
            "rule-2",
            CreditGrantRuleUpdatePayload(name="Registration", amount=20),
        )
        toggled = await client.toggle_credit_grant_rule("rule-2")
        deleted = await client.delete_credit_grant_rule("rule-2")
        summary = await client.get_credit_summary("user-1")
        history = await client.get_credit_history(user_id="user-1")
        admin_summary = await client.get_credit_admin_summary()
        token_usage = await client.get_credit_thread_token_usage()
        stats = await client.aggregate_credit_consumption_stats(
            since=datetime.fromisoformat("2026-05-22T00:00:00"),
        )
        consumed, balance_before = await client.record_credit_consumption(
            CreditConsumptionCreatePayload(
                user_id="user-1",
                transaction_type="thread_token_consume",
                amount=1,
                description="consume",
            )
        )
        refunded = await client.refund_credit_consumption(
            CreditRefundPayload(user_id="user-1", original_transaction_id="tx-1", reason="refund")
        )
        adjusted = await client.admin_adjust_credit(
            CreditAdminAdjustPayload(
                target_user_id="user-1",
                amount=10,
                transaction_type="admin_grant",
                description="grant",
            )
        )
        code = await client.create_credit_redeem_code(
            CreditRedeemCodeCreatePayload(
                code="ABC123",
                amount=10,
                max_uses=1,
                per_user_limit=1,
                admin_id="admin-1",
                batch_id="batch-1",
            )
        )
        codes = await client.list_credit_redeem_codes()
        disabled = await client.disable_credit_redeem_code("code-1")
        redeemed = await client.redeem_credit_code(
            CreditRedeemPayload(code="ABC123", user_id="user-1")
        )
        referral = await client.record_credit_referral(
            CreditReferralCreatePayload(referrer_user_id="user-a", referee_user_id="user-b")
        )
        found_referral = await client.get_credit_referral_by_referee("user-b")

    assert rules[0].id == "rule-1"
    assert fetched_rule is not None and fetched_rule.id == "rule-2"
    assert created_rule is not None and updated_rule is not None and toggled is not None
    assert deleted is True
    assert summary is not None and summary.credits == 20
    assert history.total == 1
    assert admin_summary.in_circulation == 20
    assert token_usage.total_tokens == 100
    assert stats.kpis["total_issued"] == 30
    assert consumed is not None and balance_before == 20
    assert refunded is not None and adjusted is not None and redeemed is not None
    assert code is not None and codes[0].id == "code-1" and disabled is not None
    assert referral is not None and found_referral is not None
    assert len(seen) == 20


@pytest.mark.asyncio
async def test_dataservice_client_provenance_contract_methods() -> None:
    seen: list[tuple[str, str, dict[str, Any] | None]] = []

    def link_payload() -> dict[str, Any]:
        return {
            "id": "link-1",
            "workspace_id": "workspace-1",
            "source_id": "source-1",
            "target_domain": "prism",
            "target_kind": "file",
            "target_ref_json": {},
            "relation_kind": "cites",
            "metadata_json": {},
        }

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else None
        seen.append((request.method, request.url.path, body))
        if request.method == "GET":
            return httpx.Response(200, json={"status": "ok", "data": [link_payload()]})
        if request.method == "DELETE":
            return httpx.Response(200, json={"status": "ok", "data": {"deleted": 1}})
        return httpx.Response(200, json={"status": "ok", "data": link_payload()})

    transport = httpx.MockTransport(handler)
    async with AsyncDataServiceClient(
        base_url="http://dataservice",
        internal_token="secret",
        transport=transport,
    ) as client:
        created = await client.create_provenance_link(
            ProvenanceLinkCreatePayload(
                workspace_id="workspace-1",
                source_id="source-1",
                target_domain="prism",
                target_kind="file",
                relation_kind="cites",
            )
        )
        listed = await client.list_provenance_links(workspace_id="workspace-1")
        deleted = await client.delete_provenance_links(workspace_id="workspace-1")

    assert created.id == "link-1"
    assert listed[0].id == "link-1"
    assert deleted == 1
    assert seen == [
        (
            "POST",
            "/internal/v1/provenance/links",
            {
                "workspace_id": "workspace-1",
                "source_id": "source-1",
                "source_anchor_id": None,
                "target_domain": "prism",
                "target_kind": "file",
                "target_id": None,
                "target_ref_json": {},
                "relation_kind": "cites",
                "citation_key": None,
                "claim_text": None,
                "generated_text": None,
                "review_item_id": None,
                "execution_id": None,
                "metadata_json": {},
            },
        ),
        ("GET", "/internal/v1/provenance/links", None),
        ("DELETE", "/internal/v1/provenance/links", None),
    ]


@pytest.mark.asyncio
async def test_dataservice_client_conversation_contract_methods() -> None:
    seen: list[tuple[str, str, dict[str, Any] | None]] = []

    def message_payload(message_id: str = "message-1") -> dict[str, Any]:
        return {
            "id": message_id,
            "thread_id": "thread-1",
            "user_id": "user-1",
            "workspace_id": "ws-1",
            "role": "assistant",
            "content": "Hello",
            "sequence_index": 0,
            "metadata_json": {},
            "blocks": [
                {
                    "id": "block-1",
                    "message_id": message_id,
                    "thread_id": "thread-1",
                    "block_type": "text",
                    "sequence_index": 0,
                    "payload_json": {"kind": "text", "content": "Hello"},
                }
            ],
        }

    def thread_payload(thread_id: str = "thread-1") -> dict[str, Any]:
        return {
            "id": thread_id,
            "user_id": "user-1",
            "workspace_id": "ws-1",
            "title": "Thread",
            "model": "gpt-test",
            "skill": None,
            "skill_name": None,
            "workspace_type": None,
            "message_count": 0,
            "last_message_preview": None,
            "last_message_role": None,
            "created_at": None,
            "updated_at": None,
        }

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else None
        seen.append((request.method, request.url.path, body))
        if request.url.path.endswith("/lock"):
            return httpx.Response(200, json={"status": "ok", "data": {"locked": True}})
        if request.url.path.endswith("/summaries"):
            return httpx.Response(200, json={"status": "ok", "data": [thread_payload()]})
        if request.url.path.endswith("/owned") or request.url.path.endswith("/latest"):
            return httpx.Response(200, json={"status": "ok", "data": thread_payload()})
        if request.url.path.endswith("/threads") and request.method == "POST":
            return httpx.Response(200, json={"status": "ok", "data": thread_payload()})
        if request.url.path.endswith("/threads") and request.method == "GET":
            return httpx.Response(200, json={"status": "ok", "data": [thread_payload()]})
        if "/threads/" in request.url.path and request.method == "GET":
            return httpx.Response(200, json={"status": "ok", "data": thread_payload()})
        if "/threads/" in request.url.path and request.method == "PATCH":
            payload = thread_payload()
            payload["title"] = body["title"] if body else "Updated"
            return httpx.Response(200, json={"status": "ok", "data": payload})
        if "/threads/" in request.url.path and request.method == "DELETE":
            return httpx.Response(200, json={"status": "ok", "data": {"deleted": True}})
        if request.method == "POST":
            return httpx.Response(200, json={"status": "ok", "data": message_payload("message-1")})
        return httpx.Response(200, json={"status": "ok", "data": [message_payload("message-2")]})

    transport = httpx.MockTransport(handler)
    async with AsyncDataServiceClient(
        base_url="http://dataservice",
        internal_token="secret",
        transport=transport,
    ) as client:
        appended = await client.append_conversation_message(
            "thread-1",
            ConversationMessageCreatePayload(
                thread_id="thread-1",
                user_id="user-1",
                workspace_id="ws-1",
                role="assistant",
                content="Hello",
                sequence_index=0,
                blocks=[{"kind": "text", "content": "Hello"}],
            ),
        )
        rebuilt = await client.rebuild_conversation_messages(
            "thread-1",
            ConversationMessagesRebuildPayload(
                thread_id="thread-1",
                user_id="user-1",
                workspace_id="ws-1",
                messages=[{"role": "assistant", "content": "Hello"}],
            ),
        )
        listed = await client.list_conversation_messages("thread-1")
        created_thread = await client.create_conversation_thread(
            ConversationThreadCreatePayload(
                user_id="user-1",
                workspace_id="ws-1",
                title="Thread",
                model="gpt-test",
            )
        )
        fetched_thread = await client.get_conversation_thread("thread-1")
        owned_thread = await client.get_owned_conversation_thread(thread_id="thread-1", user_id="user-1")
        latest_thread = await client.get_latest_workspace_conversation_thread(
            user_id="user-1",
            workspace_id="ws-1",
        )
        thread_summaries = await client.list_workspace_conversation_thread_summaries(
            workspace_id="ws-1",
        )
        threads = await client.list_conversation_threads(user_id="user-1", workspace_id="ws-1")
        updated_thread = await client.update_conversation_thread(
            "thread-1",
            ConversationThreadUpdatePayload(title="Updated"),
        )
        locked = await client.lock_conversation_thread("thread-1")
        deleted_thread = await client.delete_conversation_thread(thread_id="thread-1", user_id="user-1")

    assert appended is not None
    assert appended.blocks[0].block_type == "text"
    assert rebuilt[0].id == "message-2"
    assert listed[0].thread_id == "thread-1"
    assert created_thread.id == "thread-1"
    assert fetched_thread is not None and fetched_thread.id == "thread-1"
    assert owned_thread is not None and owned_thread.id == "thread-1"
    assert latest_thread is not None and latest_thread.id == "thread-1"
    assert thread_summaries[0].id == "thread-1"
    assert threads[0].id == "thread-1"
    assert updated_thread is not None and updated_thread.title == "Updated"
    assert locked is True
    assert deleted_thread is True
    assert seen[0][0] == "POST"
    assert seen[1][0] == "PUT"
    assert seen[2] == ("GET", "/internal/v1/conversations/thread-1/messages", None)


@pytest.mark.asyncio
async def test_dataservice_client_compute_session_contract_methods() -> None:
    seen: list[tuple[str, str, dict[str, Any] | None]] = []

    def session_payload(session_id: str = "compute-1") -> dict[str, Any]:
        return {
            "id": session_id,
            "execution_id": "exec-1",
            "workspace_id": "ws-1",
            "user_id": "user-1",
            "sandbox_session_id": "sandbox-1",
            "active_view": "overview",
            "ui_state": {},
            "created_at": None,
            "updated_at": None,
        }

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else None
        seen.append((request.method, request.url.path, body))
        if request.method == "POST":
            return httpx.Response(200, json={"status": "ok", "data": {"session": session_payload(), "changed": True}})
        if request.method == "GET" and request.url.path.endswith("/list"):
            return httpx.Response(200, json={"status": "ok", "data": [session_payload()]})
        if request.method == "PATCH":
            payload = session_payload()
            payload["active_view"] = body["active_view"] if body else "files"
            return httpx.Response(200, json={"status": "ok", "data": payload})
        return httpx.Response(200, json={"status": "ok", "data": session_payload("compute-2")})

    transport = httpx.MockTransport(handler)
    async with AsyncDataServiceClient(
        base_url="http://dataservice",
        internal_token="secret",
        transport=transport,
    ) as client:
        ensured, changed = await client.ensure_compute_session(
            ComputeSessionEnsurePayload(
                execution_id="exec-1",
                workspace_id="ws-1",
                user_id="user-1",
                sandbox_session_id="sandbox-1",
            )
        )
        fetched = await client.get_compute_session("compute-2")
        by_execution = await client.get_compute_session_by_execution("exec-1")
        listed = await client.list_compute_sessions(workspace_id="ws-1", user_id="user-1")
        updated = await client.update_compute_session(
            "compute-1",
            ComputeSessionUpdatePayload(active_view="files"),
        )

    assert ensured.id == "compute-1"
    assert changed is True
    assert fetched is not None and fetched.id == "compute-2"
    assert by_execution is not None and by_execution.execution_id == "exec-1"
    assert listed[0].workspace_id == "ws-1"
    assert updated is not None and updated.active_view == "files"
    assert seen == [
        (
            "POST",
            "/internal/v1/executions/compute-sessions/ensure",
            {
                "execution_id": "exec-1",
                "workspace_id": "ws-1",
                "user_id": "user-1",
                "sandbox_session_id": "sandbox-1",
            },
        ),
        ("GET", "/internal/v1/executions/compute-sessions/compute-2", None),
        ("GET", "/internal/v1/executions/compute-sessions/by-execution/exec-1", None),
        ("GET", "/internal/v1/executions/compute-sessions/list", None),
        ("PATCH", "/internal/v1/executions/compute-sessions/compute-1", {"active_view": "files"}),
    ]


@pytest.mark.asyncio
async def test_dataservice_client_execution_node_contract_methods() -> None:
    seen: list[tuple[str, str, dict[str, Any] | None]] = []

    def node_payload(status: str = "running") -> dict[str, Any]:
        return {
            "id": "node-row-1",
            "execution_id": "exec-1",
            "parent_node_id": None,
            "node_id": "node-1",
            "node_type": "agent",
            "label": "Draft",
            "status": status,
            "input_data": None,
            "output_data": None,
            "thinking": None,
            "tool_calls": None,
            "token_usage": None,
            "node_metadata": None,
            "started_at": None,
            "completed_at": None,
            "created_at": None,
            "updated_at": None,
        }

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else None
        seen.append((request.method, request.url.path, body))
        if request.url.path.endswith("/active-users/count"):
            return httpx.Response(200, json={"status": "ok", "data": {"count": 4}})
        if request.url.path.endswith("/analytics/stats"):
            return httpx.Response(
                200,
                json={"status": "ok", "data": {"kpis": {"total": 5}, "time_series": []}},
            )
        if request.url.path.endswith("/analytics/status-counts"):
            return httpx.Response(
                200,
                json={"status": "ok", "data": {"completed": 3, "failed": 1}},
            )
        if request.url.path.endswith("/features/running-count"):
            return httpx.Response(200, json={"status": "ok", "data": {"count": 2}})
        if request.url.path.endswith("/features/latest-status"):
            return httpx.Response(200, json={"status": "ok", "data": {"status": "running"}})
        if request.url.path.endswith("/reconcile-interrupted"):
            return httpx.Response(200, json={"status": "ok", "data": {"reconciled": 2}})
        if request.method == "GET" and request.url.path.endswith("/nodes"):
            return httpx.Response(200, json={"status": "ok", "data": [node_payload()]})
        if request.method == "GET" and request.url.path.endswith("/nodes/batch"):
            return httpx.Response(200, json={"status": "ok", "data": [node_payload()]})
        if request.method == "PATCH":
            return httpx.Response(200, json={"status": "ok", "data": node_payload("completed")})
        if request.method == "POST":
            return httpx.Response(200, json={"status": "ok", "data": node_payload("running")})
        return httpx.Response(200, json={"status": "ok", "data": node_payload()})

    transport = httpx.MockTransport(handler)
    async with AsyncDataServiceClient(
        base_url="http://dataservice",
        internal_token="secret",
        transport=transport,
    ) as client:
        created_since = datetime(2026, 5, 20)
        active_users = await client.count_active_execution_users(created_since=created_since)
        stats = await client.aggregate_execution_stats(created_since=created_since)
        status_counts = await client.count_executions_by_status(user_id="user-1")
        running_count = await client.count_running_feature_executions(
            workspace_id="ws-1",
            capability_id="idea_to_manuscript",
        )
        latest_status = await client.get_latest_feature_execution_status(
            workspace_id="ws-1",
            capability_id="idea_to_manuscript",
        )
        reconciled = await client.reconcile_interrupted_executions()
        listed = await client.list_execution_nodes("exec-1")
        batch_listed = await client.list_execution_nodes_by_execution_ids(["exec-1"])
        fetched = await client.get_execution_node("node-row-1")
        found = await client.find_execution_node(execution_id="exec-1", node_id="node-1")
        upserted = await client.upsert_execution_node(
            "exec-1",
            ExecutionNodeUpsertPayload(
                node_id="node-1",
                node_type="agent",
                label="Draft",
                status="running",
            ),
        )
        updated = await client.update_execution_node(
            "node-row-1",
            ExecutionNodePatchPayload(status="completed"),
        )

    assert active_users == 4
    assert stats["kpis"] == {"total": 5}
    assert status_counts == {"completed": 3, "failed": 1}
    assert running_count == 2
    assert latest_status == "running"
    assert reconciled == 2
    assert listed[0].id == "node-row-1"
    assert batch_listed[0].id == "node-row-1"
    assert fetched is not None and fetched.node_id == "node-1"
    assert found is not None and found.execution_id == "exec-1"
    assert upserted.status == "running"
    assert updated is not None and updated.status == "completed"
    assert seen == [
        ("GET", "/internal/v1/executions/analytics/active-users/count", None),
        ("GET", "/internal/v1/executions/analytics/stats", None),
        ("GET", "/internal/v1/executions/analytics/status-counts", None),
        ("GET", "/internal/v1/executions/features/running-count", None),
        ("GET", "/internal/v1/executions/features/latest-status", None),
        ("POST", "/internal/v1/executions/reconcile-interrupted", None),
        ("GET", "/internal/v1/executions/exec-1/nodes", None),
        ("GET", "/internal/v1/executions/nodes/batch", None),
        ("GET", "/internal/v1/executions/nodes/node-row-1", None),
        ("GET", "/internal/v1/executions/exec-1/nodes/node-1", None),
        (
            "POST",
            "/internal/v1/executions/exec-1/nodes",
            {
                "node_id": "node-1",
                "node_type": "agent",
                "label": "Draft",
                "status": "running",
            },
        ),
        ("PATCH", "/internal/v1/executions/nodes/node-row-1", {"status": "completed"}),
    ]


@pytest.mark.asyncio
async def test_dataservice_client_knowledge_contract_methods() -> None:
    seen: list[tuple[str, str, dict[str, Any] | None]] = []

    def knowledge_payload(knowledge_id: str = "knowledge-1") -> dict[str, Any]:
        return {
            "id": knowledge_id,
            "user_id": "user-1",
            "category": "preference",
            "content": "Use concise prose",
            "confidence": 0.8,
            "source": "manual",
            "workspace_context": None,
            "is_active": True,
            "created_at": None,
            "updated_at": None,
        }

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else None
        seen.append((request.method, request.url.path, body))
        path = request.url.path
        if path.endswith("/archive-low-confidence"):
            return httpx.Response(200, json={"status": "ok", "data": {"archived": 2}})
        if path.endswith("/active-count"):
            return httpx.Response(200, json={"status": "ok", "data": {"count": 3}})
        if path.endswith("/deactivate"):
            return httpx.Response(200, json={"status": "ok", "data": {"deactivated": True}})
        if request.method == "DELETE":
            return httpx.Response(200, json={"status": "ok", "data": {"deleted": True}})
        if request.method == "GET" and "/users/" in path:
            return httpx.Response(200, json={"status": "ok", "data": [knowledge_payload()]})
        return httpx.Response(200, json={"status": "ok", "data": knowledge_payload("knowledge-2")})

    transport = httpx.MockTransport(handler)
    async with AsyncDataServiceClient(
        base_url="http://dataservice",
        internal_token="secret",
        transport=transport,
    ) as client:
        created = await client.create_knowledge_memory(
            KnowledgeMemoryCreatePayload(
                user_id="user-1",
                category="preference",
                content="Use concise prose",
                confidence=0.8,
                source="manual",
            )
        )
        upserted = await client.upsert_knowledge_memory(
            KnowledgeMemoryCreatePayload(
                user_id="user-1",
                category="preference",
                content="Use concise prose",
            )
        )
        fetched = await client.get_knowledge_memory("knowledge-2")
        listed = await client.list_user_knowledge_memory(user_id="user-1")
        active = await client.list_active_knowledge_memory(user_id="user-1", workspace_context="ws-1")
        updated = await client.update_knowledge_memory(
            "knowledge-2",
            KnowledgeMemoryUpdatePayload(confidence=0.9),
        )
        deactivated = await client.deactivate_knowledge_memory("knowledge-2")
        deleted = await client.delete_knowledge_memory("knowledge-2")
        archived = await client.archive_low_confidence_knowledge_memory(
            user_id="user-1",
            command=KnowledgeArchiveLowConfidencePayload(threshold=0.4),
        )
        count = await client.count_active_knowledge_memory(user_id="user-1")

    assert created is not None and created.id == "knowledge-2"
    assert upserted is not None and upserted.category == "preference"
    assert fetched is not None and fetched.id == "knowledge-2"
    assert listed[0].user_id == "user-1"
    assert active[0].content == "Use concise prose"
    assert updated is not None and updated.confidence == 0.8
    assert deactivated is True
    assert deleted is True
    assert archived == 2
    assert count == 3
    assert seen[0][1] == "/internal/v1/knowledge"
    assert seen[-1][1] == "/internal/v1/knowledge/users/user-1/active-count"


@pytest.mark.asyncio
async def test_dataservice_client_latex_contract_methods() -> None:
    seen: list[tuple[str, str, dict[str, Any] | None]] = []

    def project_payload(project_id: str = "project-1") -> dict[str, Any]:
        return {
            "id": project_id,
            "user_id": "user-1",
            "name": "Paper",
            "template_id": "acl",
            "main_file": "main.tex",
            "tags": [],
            "archived": False,
            "trashed": False,
            "trashed_at": None,
            "file_order": {},
            "llm_config": None,
            "workspace_id": "ws-1",
            "surface_role": "primary_manuscript",
            "created_at": None,
            "updated_at": None,
        }

    def template_payload() -> dict[str, Any]:
        return {
            "id": "acl",
            "label": "ACL",
            "main_file": "main.tex",
            "category": "academic",
            "description": "ACL template",
            "description_en": "ACL template",
            "tags": ["ACL"],
            "author": "WenjinPrism",
            "featured": True,
            "template_path": "acl",
        }

    def history_payload() -> dict[str, Any]:
        return {
            "id": "history-1",
            "project_id": "project-1",
            "engine": "xelatex",
            "main_file": "main.tex",
            "status": 0,
            "log": None,
            "pdf_path": "/tmp/main.pdf",
            "created_at": None,
        }

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else None
        seen.append((request.method, request.url.path, body))
        path = request.url.path
        if request.method == "DELETE":
            return httpx.Response(200, json={"status": "ok", "data": {"deleted": True}})
        if path.endswith("/ensure-defaults"):
            return httpx.Response(200, json={"status": "ok", "data": {"ensured": True}})
        if path == "/internal/v1/latex/templates":
            return httpx.Response(200, json={"status": "ok", "data": [template_payload()]})
        if "/templates/" in path:
            return httpx.Response(200, json={"status": "ok", "data": template_payload()})
        if path.endswith("/compile-history") and request.method == "GET":
            return httpx.Response(200, json={"status": "ok", "data": [history_payload()]})
        if "/compile-history" in path:
            return httpx.Response(200, json={"status": "ok", "data": history_payload()})
        if request.method == "GET" and path == "/internal/v1/latex/projects":
            return httpx.Response(200, json={"status": "ok", "data": [project_payload()]})
        return httpx.Response(200, json={"status": "ok", "data": project_payload("project-2")})

    transport = httpx.MockTransport(handler)
    async with AsyncDataServiceClient(
        base_url="http://dataservice",
        internal_token="secret",
        transport=transport,
    ) as client:
        listed = await client.list_latex_projects_by_user(user_id="user-1")
        fetched = await client.get_latex_project("project-2")
        owned = await client.get_owned_latex_project(project_id="project-2", user_id="user-1")
        primary = await client.get_workspace_primary_latex_project(workspace_id="ws-1", owner_user_id="user-1")
        created = await client.create_latex_project(LatexProjectCreatePayload(user_id="user-1", name="Paper"))
        updated = await client.update_latex_project("project-2", LatexProjectUpdatePayload(name="Paper 2"))
        touched = await client.touch_latex_project("project-2", LatexProjectTouchPayload(main_file="paper.tex"))
        attached = await client.attach_workspace_latex_project(
            "project-2",
            LatexProjectAttachWorkspacePayload(workspace_id="ws-1"),
        )
        soft_deleted = await client.soft_delete_latex_project("project-2")
        deleted = await client.delete_latex_project("project-2")
        template = await client.get_latex_template("acl")
        ensured = await client.ensure_default_latex_templates()
        templates = await client.list_latex_templates()
        history = await client.record_latex_compile_history(
            LatexCompileHistoryCreatePayload(
                project_id="project-1",
                engine="xelatex",
                main_file="main.tex",
                status=0,
            )
        )
        fetched_history = await client.get_latex_compile_history("history-1")
        histories = await client.list_latex_compile_history("project-1")
        deleted_history = await client.delete_latex_compile_history("history-1")

    assert listed[0].id == "project-1"
    assert fetched is not None and fetched.id == "project-2"
    assert owned is not None and owned.user_id == "user-1"
    assert primary is not None and primary.workspace_id == "ws-1"
    assert created is not None and created.name == "Paper"
    assert updated is not None and updated.id == "project-2"
    assert touched is not None and touched.main_file == "main.tex"
    assert attached is not None and attached.surface_role == "primary_manuscript"
    assert soft_deleted is not None and soft_deleted.id == "project-2"
    assert deleted is True
    assert template is not None and template.id == "acl"
    assert ensured is True
    assert templates[0].featured is True
    assert history is not None and history.id == "history-1"
    assert fetched_history is not None and fetched_history.project_id == "project-1"
    assert histories[0].engine == "xelatex"
    assert deleted_history is True
    assert seen[0][1] == "/internal/v1/latex/projects"
    assert seen[-1][1] == "/internal/v1/latex/compile-history/history-1"


@pytest.mark.asyncio
async def test_dataservice_client_task_contract_methods() -> None:
    seen: list[tuple[str, str, dict[str, Any] | None]] = []

    def task_payload(status: str = "pending") -> dict[str, Any]:
        return {
            "id": "task-1",
            "user_id": "user-1",
            "task_type": "lead",
            "workspace_id": "ws-1",
            "feature_id": "feature-1",
            "thread_id": "thread-1",
            "execution_id": "exec-1",
            "action": "run",
            "status": status,
            "priority": 5,
            "payload": {},
            "result": None,
            "error": None,
            "runtime_state": None,
            "progress": 0,
            "message": None,
            "created_at": "2026-05-22T00:00:00",
            "started_at": None,
            "completed_at": None,
        }

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else None
        seen.append((request.method, request.url.path, body))
        path = request.url.path
        if path.endswith("/active-count"):
            return httpx.Response(200, json={"status": "ok", "data": {"count": 2}})
        if path.endswith("/guarded"):
            return httpx.Response(200, json={"status": "ok", "data": {"record": task_payload(), "active_count": 1}})
        if request.method == "GET" and "/users/" in path:
            return httpx.Response(200, json={"status": "ok", "data": [task_payload()]})
        if path.endswith("/completed"):
            return httpx.Response(200, json={"status": "ok", "data": task_payload("completed")})
        if request.method == "PATCH":
            return httpx.Response(200, json={"status": "ok", "data": task_payload("running")})
        return httpx.Response(200, json={"status": "ok", "data": task_payload()})

    transport = httpx.MockTransport(handler)
    async with AsyncDataServiceClient(
        base_url="http://dataservice",
        internal_token="secret",
        transport=transport,
    ) as client:
        created = await client.create_task_record(
            TaskRecordCreatePayload(
                task_id="task-1",
                user_id="user-1",
                task_type="lead",
                priority=5,
                payload={},
            )
        )
        guarded, active_count = await client.create_task_record_guarded(
            TaskRecordCreateGuardedPayload(
                task_id="task-1",
                user_id="user-1",
                task_type="lead",
                priority=5,
                payload={},
                concurrency_limit=1,
                active_statuses=["pending"],
            )
        )
        fetched = await client.get_task_record("task-1")
        updated = await client.update_task_record("task-1", TaskRecordPatchPayload(status="running"))
        listed = await client.list_user_task_records(user_id="user-1", status=["pending"])
        count = await client.count_active_task_records(user_id="user-1", active_statuses=["pending"])
        started = await client.mark_task_record_started(
            "task-1",
            TaskRecordStartedPayload(started_at=datetime(2026, 5, 22)),
        )
        runtime = await client.persist_task_record_runtime_state(
            "task-1",
            TaskRecordRuntimeStatePayload(runtime_state={"step": 1}),
        )
        completed = await client.mark_task_record_completed(
            "task-1",
            TaskRecordCompletedPayload(
                status="completed",
                result={},
                completed_at=datetime(2026, 5, 22),
                progress=100,
            ),
        )

    assert created.id == "task-1"
    assert guarded is not None and guarded.id == "task-1"
    assert active_count == 1
    assert fetched is not None and fetched.task_type == "lead"
    assert updated is not None and updated.status == "running"
    assert listed[0].workspace_id == "ws-1"
    assert count == 2
    assert started is not None and started.id == "task-1"
    assert runtime is not None and runtime.id == "task-1"
    assert completed is not None and completed.status == "completed"
    assert seen[0][1] == "/internal/v1/tasks"
    assert seen[-1][1] == "/internal/v1/tasks/task-1/completed"


@pytest.mark.asyncio
async def test_dataservice_client_prism_review_contract_methods() -> None:
    seen: list[tuple[str, str, dict[str, Any] | None]] = []

    def item_payload(status: str = "pending") -> dict[str, Any]:
        return {
            "id": "item-1",
            "batch_id": "batch-1",
            "workspace_id": "ws-1",
            "source_item_id": "intro",
            "item_kind": "file_change",
            "target_domain": "prism",
            "target_kind": "prism_file_change",
            "target_ref_json": {},
            "status": status,
            "title": "main.tex",
            "summary": None,
            "payload_json": {},
            "preview_json": {},
            "result_json": None,
            "error_text": None,
            "provenance_json": {},
            "sort_order": 0,
            "applied_at": None,
            "created_at": None,
            "updated_at": None,
        }

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else None
        seen.append((request.method, request.url.path, body))
        path = request.url.path
        if path.endswith("/clear-pending"):
            return httpx.Response(200, json={"status": "ok", "data": {"deleted": True}})
        if path.endswith("/applied"):
            return httpx.Response(200, json={"status": "ok", "data": item_payload("applied")})
        if path.endswith("/rejected"):
            return httpx.Response(200, json={"status": "ok", "data": item_payload("rejected")})
        if path.endswith("/reverted"):
            return httpx.Response(200, json={"status": "ok", "data": item_payload("reverted")})
        return httpx.Response(200, json={"status": "ok", "data": item_payload()})

    transport = httpx.MockTransport(handler)
    async with AsyncDataServiceClient(
        base_url="http://dataservice",
        internal_token="secret",
        transport=transport,
    ) as client:
        found = await client.find_prism_file_change(
            workspace_id="ws-1",
            latex_project_id="latex-1",
            logical_key="intro",
            statuses=["pending"],
        )
        upserted = await client.upsert_pending_prism_file_change(
            PrismFileChangeUpsertPayload(
                workspace_id="ws-1",
                latex_project_id="latex-1",
                logical_key="intro",
                path="main.tex",
                reason="draft",
                pending_content="content",
                pending_hash="hash-2",
            )
        )
        cleared = await client.clear_pending_prism_file_change(
            PrismFileChangeClearPayload(
                workspace_id="ws-1",
                latex_project_id="latex-1",
                logical_key="intro",
            )
        )
        applied = await client.mark_prism_file_change_applied(
            "item-1",
            PrismFileChangeAppliedPayload(
                previous_content="old",
                previous_hash="hash-1",
                applied_hash="hash-2",
                revert_signature="sig",
            ),
        )
        rejected = await client.mark_prism_file_change_rejected(
            "item-1",
            PrismFileChangeRejectedPayload(reason="no"),
        )
        reverted = await client.mark_prism_file_change_reverted("item-1")

    assert found is not None and found.id == "item-1"
    assert upserted.status == "pending"
    assert cleared is True
    assert applied is not None and applied.status == "applied"
    assert rejected is not None and rejected.status == "rejected"
    assert reverted is not None and reverted.status == "reverted"
    assert seen[0][1] == "/internal/v1/prism-review/file-changes/find"
    assert seen[-1][1] == "/internal/v1/prism-review/items/item-1/reverted"
