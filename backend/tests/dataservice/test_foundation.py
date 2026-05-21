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
from src.dataservice_client.contracts.conversation import (
    ConversationMessageCreatePayload,
    ConversationMessagesRebuildPayload,
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
        fetched = await client.get_workspace("workspace-2")
        updated = await client.update_workspace(
            "workspace-2",
            WorkspaceUpdatePayload(name="Updated"),
        )
        deleted = await client.delete_workspace("workspace-2")

    assert created.workspace_type == "thesis"
    assert listed[0].id == "workspace-1"
    assert fetched is not None
    assert fetched.id == "workspace-2"
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
        ("GET", "/internal/v1/workspaces/workspace-2", None),
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

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else None
        seen.append((request.method, request.url.path, body))
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

    assert appended is not None
    assert appended.blocks[0].block_type == "text"
    assert rebuilt[0].id == "message-2"
    assert listed[0].thread_id == "thread-1"
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
        if request.url.path.endswith("/features/running-count"):
            return httpx.Response(200, json={"status": "ok", "data": {"count": 2}})
        if request.url.path.endswith("/features/latest-status"):
            return httpx.Response(200, json={"status": "ok", "data": {"status": "running"}})
        if request.url.path.endswith("/reconcile-interrupted"):
            return httpx.Response(200, json={"status": "ok", "data": {"reconciled": 2}})
        if request.method == "GET" and request.url.path.endswith("/nodes"):
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
    assert running_count == 2
    assert latest_status == "running"
    assert reconciled == 2
    assert listed[0].id == "node-row-1"
    assert fetched is not None and fetched.node_id == "node-1"
    assert found is not None and found.execution_id == "exec-1"
    assert upserted.status == "running"
    assert updated is not None and updated.status == "completed"
    assert seen == [
        ("GET", "/internal/v1/executions/analytics/active-users/count", None),
        ("GET", "/internal/v1/executions/analytics/stats", None),
        ("GET", "/internal/v1/executions/features/running-count", None),
        ("GET", "/internal/v1/executions/features/latest-status", None),
        ("POST", "/internal/v1/executions/reconcile-interrupted", None),
        ("GET", "/internal/v1/executions/exec-1/nodes", None),
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
