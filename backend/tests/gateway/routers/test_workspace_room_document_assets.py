"""Tests for document-room projections over DataService assets."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.dataservice_client.contracts.asset import WorkspaceAssetPayload
from src.gateway.routers.workspace_rooms import _asset_to_document, _create_document_asset


def _asset(**overrides: object) -> WorkspaceAssetPayload:
    values = {
        "id": "asset-1",
        "workspace_id": "ws-1",
        "asset_kind": "document",
        "name": "Draft",
        "title": "Draft",
        "mime_type": "text/markdown",
        "storage_backend": "local",
        "storage_path": "inline://asset-1",
        "size_bytes": 12,
        "content_hash": None,
        "parent_asset_id": None,
        "created_by": "user",
        "source_kind": "documents_room",
        "source_id": None,
        "metadata_json": {"kind": "draft", "version": 1},
        "deleted_at": None,
        "created_at": None,
        "updated_at": None,
    }
    values.update(overrides)
    return WorkspaceAssetPayload(**values)


@pytest.mark.asyncio
async def test_add_with_parent_creates_document_asset_version() -> None:
    assets = MagicMock()
    assets.get_asset = AsyncMock(
        return_value=_asset(
            id="parent-doc",
            metadata_json={"kind": "draft", "version": 2},
        )
    )
    assets.register_asset = AsyncMock(
        return_value=_asset(
            id="child-doc",
            parent_asset_id="parent-doc",
            source_id="parent-doc",
            metadata_json={"kind": "draft", "version": 3, "parent_id": "parent-doc"},
        )
    )

    document = await _create_document_asset(
        assets,
        workspace_id="ws-1",
        data={
            "name": "Draft v3",
            "kind": "draft",
            "parent_id": "parent-doc",
            "storage_path": "inline://child-doc",
            "added_by": "user",
        },
    )

    command = assets.register_asset.await_args.args[0]
    assert command.parent_asset_id == "parent-doc"
    assert command.source_kind == "documents_room"
    assert command.source_id == "parent-doc"
    assert document["id"] == "child-doc"
    assert document["version"] == 3


def test_document_asset_projection_uses_canonical_metadata() -> None:
    view = _asset_to_document(
        _asset(
            source_kind="documents_v2",
            metadata_json={
                "kind": "outline",
                "version": 4,
                "parent_id": "parent-canonical",
            },
        )
    )

    assert view["kind"] == "outline"
    assert view["version"] == 4
    assert view["parent_id"] == "parent-canonical"
