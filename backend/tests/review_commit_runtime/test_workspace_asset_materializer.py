from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.dataservice_client.contracts.mission import MissionReviewItemPayload
from src.review_commit_runtime.materializer import MissionDomainWriter
from src.review_commit_runtime.preview_store import MissionPreviewStore

from .test_preview_store import _png


def _item(
    *,
    preview_ref: str,
    content_hash: str,
    review_item_id: str = "review-1",
) -> MissionReviewItemPayload:
    now = datetime.now(UTC)
    return MissionReviewItemPayload(
        review_item_id=review_item_id,
        mission_id="mission-1",
        source_item_seq=2,
        output_key="academic_figure",
        target_kind="workspace_asset",
        target_room="assets",
        title="Academic figure",
        risk_level="medium",
        status="accepted",
        preview_json={
            "figure_type": "graphical_abstract",
            "materialization": {
                "operation": "assets.create_from_preview",
                "payload": {
                    "asset_kind": "academic_visual",
                    "name": "figure.png",
                    "mime_type": "image/png",
                    "content_hash": content_hash,
                    "metadata_json": {"strategy": "llm_image"},
                },
            },
        },
        preview_ref=preview_ref,
        preview_hash="metadata-hash",
        preview_expires_at=now + timedelta(hours=1),
        requires_explicit_review=True,
        batch_acceptable=False,
        suggested_selected=False,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_workspace_asset_materialization_is_verified_and_idempotent(tmp_path) -> None:
    store = MissionPreviewStore(tmp_path / "previews", default_ttl_seconds=3600, max_bytes=1024 * 1024)
    descriptor = await store.put(
        workspace_id="workspace-1",
        content=_png(),
        mime_type="image/png",
        filename="figure.png",
    )
    asset = SimpleNamespace(id="asset-1", content_hash=descriptor.content_hash)
    dataservice = SimpleNamespace(
        list_assets=AsyncMock(side_effect=[[], [asset]]),
        register_asset=AsyncMock(return_value=asset),
    )
    writer = MissionDomainWriter(
        dataservice,
        preview_store=store,
        workspace_asset_root=tmp_path / "assets",
    )
    item = _item(preview_ref=descriptor.ref, content_hash=descriptor.content_hash)

    first = await writer.apply(
        item,
        workspace_id="workspace-1",
        mission_commit_id="commit-1",
        mission_commit_attempt_token="attempt-token-commit-1",
        actor_user_id="user-1",
    )
    second = await writer.apply(
        item,
        workspace_id="workspace-1",
        mission_commit_id="commit-1",
        mission_commit_attempt_token="attempt-token-commit-1",
        actor_user_id="user-1",
    )

    command = dataservice.register_asset.await_args.args[0]
    assert first.target_ref == second.target_ref == "asset-1"
    assert command.source_kind == "mission_review_item"
    assert command.source_id == "review-1"
    assert command.storage_path.endswith(f"{descriptor.content_hash}.png")
    assert (tmp_path / "assets" / "workspace-1" / command.storage_path).read_bytes() == _png()
    dataservice.register_asset.assert_awaited_once()


@pytest.mark.asyncio
async def test_workspace_asset_materialization_keeps_multiple_items_in_one_commit_distinct(tmp_path) -> None:
    store = MissionPreviewStore(tmp_path / "previews", default_ttl_seconds=3600, max_bytes=1024 * 1024)
    first_descriptor = await store.put(
        workspace_id="workspace-1",
        content=_png(),
        mime_type="image/png",
        filename="first.png",
    )
    second_content = _png(pixel=b"\xff\xff\xff\xff")
    second_descriptor = await store.put(
        workspace_id="workspace-1",
        content=second_content,
        mime_type="image/png",
        filename="second.png",
    )
    dataservice = SimpleNamespace(
        list_assets=AsyncMock(return_value=[]),
        register_asset=AsyncMock(
            side_effect=[
                SimpleNamespace(id="asset-1", content_hash=first_descriptor.content_hash),
                SimpleNamespace(id="asset-2", content_hash=second_descriptor.content_hash),
            ]
        ),
    )
    writer = MissionDomainWriter(
        dataservice,
        preview_store=store,
        workspace_asset_root=tmp_path / "assets",
    )

    first = await writer.apply(
        _item(
            preview_ref=first_descriptor.ref,
            content_hash=first_descriptor.content_hash,
            review_item_id="review-1",
        ),
        workspace_id="workspace-1",
        mission_commit_id="commit-1",
        mission_commit_attempt_token="attempt-token-commit-1",
        actor_user_id="user-1",
    )
    second = await writer.apply(
        _item(
            preview_ref=second_descriptor.ref,
            content_hash=second_descriptor.content_hash,
            review_item_id="review-2",
        ),
        workspace_id="workspace-1",
        mission_commit_id="commit-1",
        mission_commit_attempt_token="attempt-token-commit-1",
        actor_user_id="user-1",
    )

    assert (first.target_ref, second.target_ref) == ("asset-1", "asset-2")
    assert [
        call.args[0].source_id for call in dataservice.register_asset.await_args_list
    ] == ["review-1", "review-2"]


@pytest.mark.asyncio
async def test_workspace_asset_materialization_rejects_descriptor_mismatch(tmp_path) -> None:
    store = MissionPreviewStore(tmp_path / "previews", default_ttl_seconds=3600, max_bytes=1024 * 1024)
    descriptor = await store.put(
        workspace_id="workspace-1",
        content=_png(),
        mime_type="image/png",
        filename="figure.png",
    )
    dataservice = SimpleNamespace(list_assets=AsyncMock(return_value=[]), register_asset=AsyncMock())
    writer = MissionDomainWriter(
        dataservice,
        preview_store=store,
        workspace_asset_root=tmp_path / "assets",
    )

    with pytest.raises(ValueError, match="workspace_asset_content_hash_mismatch"):
        await writer.apply(
            _item(preview_ref=descriptor.ref, content_hash="0" * 64),
            workspace_id="workspace-1",
            mission_commit_id="commit-1",
            mission_commit_attempt_token="attempt-token-commit-1",
            actor_user_id="user-1",
        )
    dataservice.register_asset.assert_not_awaited()
