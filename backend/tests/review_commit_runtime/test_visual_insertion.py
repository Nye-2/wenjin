"""Reviewed academic-visual insertion boundary tests."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.contracts.prism_context import PrismContextRef
from src.contracts.prism_visual_insertion import insert_after_prism_selection
from src.dataservice_client.contracts.mission import MissionReviewItemPayload
from src.review_commit_runtime.materializer import MissionDomainWriter
from src.review_commit_runtime.visual_insertion import PrismVisualInsertionService


def _sha256(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode()).hexdigest()}"


def _membership() -> SimpleNamespace:
    return SimpleNamespace(require_active_member=AsyncMock())


@pytest.mark.asyncio
async def test_stage_builds_one_hash_bound_prism_review_without_mutating_source() -> None:
    source_review_item_id = "11111111-1111-4111-8111-111111111111"
    mission_id = "22222222-2222-4222-8222-222222222222"
    asset_id = "33333333-3333-4333-8333-333333333333"
    source_commit_id = "44444444-4444-4444-8444-444444444444"
    content = "# Method 😀\n\nKeep trailing spaces here.  \n\nNext paragraph.\n"
    selected = "Keep trailing spaces here.  "
    selected_start = content.index(selected)
    start = len(content[:selected_start].encode("utf-8"))
    end = start + len(selected.encode("utf-8"))
    source_item = SimpleNamespace(
        review_item_id=source_review_item_id,
        status=SimpleNamespace(value="committed"),
        target_kind="workspace_asset",
    )
    source_commit = SimpleNamespace(
        commit_id=source_commit_id,
        review_item_id=source_review_item_id,
        status=SimpleNamespace(value="committed"),
        targets_json={"target_ref": asset_id},
    )
    missions = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                mission_id=mission_id,
                workspace_id="workspace-1",
                user_id="user-1",
                state_version=7,
            )
        ),
        list_review_items=AsyncMock(return_value=[source_item]),
        get_commit_for_review_item=AsyncMock(
            return_value=SimpleNamespace(commit=source_commit)
        ),
        create_derived_review_item=AsyncMock(
            return_value=SimpleNamespace(items=[SimpleNamespace(review_item_id="derived-1")])
        ),
    )
    dataservice = SimpleNamespace(
        missions=missions,
        get_asset=AsyncMock(
            return_value=SimpleNamespace(
                id=asset_id,
                workspace_id="workspace-1",
                deleted_at=None,
                source_kind="mission_review_item",
                source_id=source_review_item_id,
                content_hash="a" * 64,
                mime_type="image/png",
                storage_path="mission-assets/figure.png",
                metadata_json={"caption": "Federated tuning workflow", "alt_text": "Workflow diagram"},
                title="Workflow",
                name="figure.png",
            )
        ),
        get_prism_surface=AsyncMock(
            return_value=SimpleNamespace(project=SimpleNamespace(id="project-1"))
        ),
        get_prism_workspace_file=AsyncMock(
            return_value=SimpleNamespace(
                file=SimpleNamespace(
                    id="file-1",
                    path="paper.md",
                    content_hash=_sha256(content),
                ),
                current_version=SimpleNamespace(
                    id="version-1",
                    content_inline=content,
                ),
            )
        ),
    )

    result = await PrismVisualInsertionService(
        dataservice=dataservice,
        membership=_membership(),
    ).stage(
        mission_id,
        actor_user_id="user-1",
        source_review_item_id=source_review_item_id,
        prism_context_ref=PrismContextRef(
            workspace_id="workspace-1",
            prism_project_id="project-1",
            file_id="file-1",
            base_revision_ref="version-1",
            selection_hash=_sha256(selected),
            selection_byte_range=(start, end),
        ),
    )
    replay = await PrismVisualInsertionService(
        dataservice=dataservice,
        membership=_membership(),
    ).stage(
        mission_id,
        actor_user_id="user-1",
        source_review_item_id=source_review_item_id,
        prism_context_ref=PrismContextRef(
            workspace_id="workspace-1",
            prism_project_id="project-1",
            file_id="file-1",
            base_revision_ref="version-1",
            selection_hash=_sha256(selected),
            selection_byte_range=(start, end),
        ),
    )

    assert result.review_item_id == "derived-1"
    assert replay.review_item_id == "derived-1"
    command = missions.create_derived_review_item.await_args.args[1]
    first_command = missions.create_derived_review_item.await_args_list[0].args[1]
    assert command.item.review_item_id == first_command.item.review_item_id
    payload = command.item.preview_json["materialization"]["payload"]
    assert command.source_review_item_id == source_review_item_id
    assert command.item.target_kind == "prism_visual_insertion"
    assert command.item.base_revision_ref == "version-1"
    assert command.item.base_hash == _sha256(content)
    assert payload["asset_id"] == asset_id
    assert payload["source_mission_commit_id"] == source_commit_id
    assert payload["selection_byte_range"] == [start, end]
    assert payload["selection_hash"] == _sha256(selected)
    assert "![Workflow diagram](/api/workspaces/workspace-1/files/mission-assets/figure.png)" in payload["insertion"]
    assert "content_inline" not in payload
    assert payload["expected_content_hash"] == _sha256(
        insert_after_prism_selection(
            content=content,
            selection_byte_range=(start, end),
            selection_hash=_sha256(selected),
            insertion=payload["insertion"],
        )
    )
    assert dataservice.get_asset.await_count == 2


@pytest.mark.asyncio
async def test_materializer_delegates_visual_write_to_prism_transaction() -> None:
    now = datetime.now(UTC)
    item = MissionReviewItemPayload(
        review_item_id="11111111-1111-4111-8111-111111111111",
        mission_id="22222222-2222-4222-8222-222222222222",
        source_item_seq=4,
        output_key="visual-insertion:abc",
        target_kind="prism_visual_insertion",
        target_room="documents",
        target_ref="prism-file:file-1",
        base_revision_ref="version-1",
        base_hash="old-hash",
        title="Insert visual",
        risk_level="medium",
        status="accepted",
        preview_json={
            "materialization": {
                "operation": "documents.insert_visual_asset",
                "payload": {
                    "prism_project_id": "project-1",
                    "selection_byte_range": [0, 3],
                    "selection_hash": _sha256("old"),
                    "insertion": "![Figure](/figure.png)",
                    "expected_content_hash": _sha256("next manuscript"),
                    "asset_id": "33333333-3333-4333-8333-333333333333",
                    "source_mission_commit_id": "44444444-4444-4444-8444-444444444444",
                    "metadata_json": {"caption": "Figure 1"},
                },
            }
        },
        requires_explicit_review=True,
        batch_acceptable=False,
        suggested_selected=False,
        created_at=now,
        updated_at=now,
    )
    dataservice = SimpleNamespace(
        insert_prism_visual_asset=AsyncMock(
            return_value=SimpleNamespace(
                manuscript=SimpleNamespace(
                    file=SimpleNamespace(id="file-1", current_version_id="version-2", content_hash="next-hash"),
                    version=SimpleNamespace(id="version-2", content_hash="next-hash"),
                ),
                asset_file=SimpleNamespace(file=SimpleNamespace(id="asset-file-1")),
            )
        )
    )

    receipt = await MissionDomainWriter(dataservice).apply(
        item,
        workspace_id="workspace-1",
        mission_commit_id="55555555-5555-4555-8555-555555555555",
        mission_commit_attempt_token="attempt-token-commit-1",
        actor_user_id="user-1",
    )

    command = dataservice.insert_prism_visual_asset.await_args.args[1]
    assert command.target_file_id == "file-1"
    assert command.expected_current_version_id == "version-1"
    assert command.expected_current_hash == "old-hash"
    assert command.prism_project_id == "project-1"
    assert command.mission_write_authority.attempt_token == "attempt-token-commit-1"
    assert command.mission_write_authority.mission_review_item_id == item.review_item_id
    assert (
        command.mission_write_authority.mission_commit_id
        == "55555555-5555-4555-8555-555555555555"
    )
    assert receipt.target_ref == "prism-file:file-1"
    assert receipt.revision_ref == "version-2"
    assert receipt.provenance["asset_prism_ref"] == "prism-file:asset-file-1"
