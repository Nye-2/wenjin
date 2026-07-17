from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.dataservice_client.contracts.mission import MissionReviewItemPayload, MissionRunPayload
from src.gateway.auth_dependencies import AccountAuthSubject, get_current_user
from src.gateway.deps.core import get_dataservice_client
from src.gateway.routers import missions
from src.review_commit_runtime.composition import get_mission_preview_store
from src.review_commit_runtime.preview_store import MissionPreviewStore

from ...review_commit_runtime.test_preview_store import _png


def _user(user_id: str = "user-1") -> AccountAuthSubject:
    return AccountAuthSubject(
        id=user_id,
        email=f"{user_id}@example.com",
        name=user_id,
        role="user",
        is_active=True,
        is_superuser=False,
    )


def _run(*, user_id: str = "user-1") -> MissionRunPayload:
    now = datetime.now(UTC)
    return MissionRunPayload(
        mission_id="mission-1",
        workspace_id="workspace-1",
        thread_id="thread-1",
        user_id=user_id,
        workspace_type="sci",
        mission_policy_id="sci.research",
        title="Research",
        objective="Create a visual",
        status="running",
        review_mode="balanced_default",
        model_id="gpt-5.6-terra",
        reasoning_effort="xhigh",
        pending_review_count=1,
        evidence_count=0,
        artifact_count=1,
        active_subagent_count=0,
        last_command_seq=0,
        last_applied_command_seq=0,
        lease_epoch=0,
        state_version=1,
        last_item_seq=1,
        created_at=now,
        updated_at=now,
    )


def _item(ref: str, content_hash: str) -> MissionReviewItemPayload:
    now = datetime.now(UTC)
    preview_json = {"content_hash": content_hash}
    preview_hash = hashlib.sha256(
        json.dumps(preview_json, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return MissionReviewItemPayload(
        review_item_id="review-1",
        mission_id="mission-1",
        output_key="figure",
        target_kind="workspace_asset",
        title="Figure",
        risk_level="medium",
        status="pending",
        preview_json=preview_json,
        preview_ref=ref,
        preview_hash=preview_hash,
        preview_expires_at=now + timedelta(hours=1),
        requires_explicit_review=True,
        batch_acceptable=False,
        suggested_selected=False,
        created_at=now,
        updated_at=now,
    )


def test_preview_route_is_owned_private_and_never_accepts_raw_ref(tmp_path) -> None:
    store = MissionPreviewStore(tmp_path, default_ttl_seconds=3600, max_bytes=1024 * 1024)
    descriptor = __import__("asyncio").run(
        store.put(
            workspace_id="workspace-1",
            content=_png(),
            mime_type="image/png",
            filename="figure.png",
        )
    )
    run = _run()
    dataservice = SimpleNamespace(
        missions=SimpleNamespace(
            get=AsyncMock(return_value=run),
            list_review_items=AsyncMock(return_value=[_item(descriptor.ref, descriptor.content_hash)]),
        ),
        workspace_has_active_membership=AsyncMock(return_value=True),
    )
    app = FastAPI()
    app.include_router(missions.router)
    app.dependency_overrides[get_current_user] = lambda: _user()
    app.dependency_overrides[get_dataservice_client] = lambda: dataservice
    app.dependency_overrides[get_mission_preview_store] = lambda: store
    client = TestClient(app)

    response = client.get("/missions/mission-1/review-items/review-1/preview")

    assert response.status_code == 200
    assert response.content == _png()
    assert response.headers["content-type"] == "image/png"
    assert response.headers["etag"] == f'"{descriptor.content_hash}"'
    assert response.headers["cache-control"] == "private, no-store, max-age=0"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert client.get(f"/missions/mission-1/review-items/{descriptor.ref}/preview").status_code == 404


def test_preview_route_hides_foreign_mission_before_store_read(tmp_path) -> None:
    store = SimpleNamespace(read=AsyncMock())
    dataservice = SimpleNamespace(
        missions=SimpleNamespace(get=AsyncMock(return_value=_run(user_id="other-user"))),
        workspace_has_active_membership=AsyncMock(return_value=True),
    )
    app = FastAPI()
    app.include_router(missions.router)
    app.dependency_overrides[get_current_user] = lambda: _user()
    app.dependency_overrides[get_dataservice_client] = lambda: dataservice
    app.dependency_overrides[get_mission_preview_store] = lambda: store
    client = TestClient(app)

    response = client.get("/missions/mission-1/review-items/review-1/preview")

    assert response.status_code == 404
    store.read.assert_not_awaited()


def test_mission_view_exposes_canonical_preview_url_without_raw_ref() -> None:
    run = _run()
    review_item = _item("mpv1_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "a" * 64)
    view = SimpleNamespace(
        model_dump=lambda **_: {
            "mission": run.model_dump(mode="json"),
            "review_items": [review_item.model_dump(mode="json")],
        }
    )
    dataservice = SimpleNamespace(
        missions=SimpleNamespace(
            get=AsyncMock(return_value=run),
            get_view=AsyncMock(return_value=view),
        ),
        workspace_has_active_membership=AsyncMock(return_value=True),
    )
    app = FastAPI()
    app.include_router(missions.router)
    app.dependency_overrides[get_current_user] = lambda: _user()
    app.dependency_overrides[get_dataservice_client] = lambda: dataservice
    client = TestClient(app)

    response = client.get("/missions/mission-1")

    item = response.json()["review_items"][0]
    assert response.status_code == 200
    assert "preview_ref" not in item
    assert item["preview_url"] == "/api/missions/mission-1/review-items/review-1/preview"
