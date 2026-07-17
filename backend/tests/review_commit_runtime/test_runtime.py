from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from src.dataservice_client.contracts.mission import (
    MissionCommitPayload,
    MissionCommitStatus,
    MissionReviewItemPayload,
    MissionRunPayload,
)
from src.review_commit_runtime.contracts import (
    CommitBatchOutcome,
    CommitOutcome,
    MaterializationReceipt,
    PreviewObject,
    PreviewObjectDescriptor,
    ReviewAction,
    ReviewDecision,
    TargetSnapshot,
)
from src.review_commit_runtime.materializer import MissionDomainWriter
from src.review_commit_runtime.runtime import ReviewCommitRuntime


def _membership() -> SimpleNamespace:
    return SimpleNamespace(require_active_member=AsyncMock())


def _run(*, version: int = 1, review_mode: str = "balanced_default") -> MissionRunPayload:
    now = datetime.now(UTC)
    return MissionRunPayload(
        mission_id="mission-1",
        workspace_id="workspace-1",
        thread_id="thread-1",
        user_id="user-1",
        workspace_type="sci",
        title="Research",
        objective="Research well",
        status="completed",
        review_mode=review_mode,
        model_id="gpt-5.6-sol",
        reasoning_effort="xhigh",
        pending_review_count=2,
        evidence_count=0,
        artifact_count=0,
        active_subagent_count=0,
        last_command_seq=0,
        last_applied_command_seq=0,
        lease_epoch=0,
        state_version=version,
        last_item_seq=0,
        created_at=now,
        updated_at=now,
    )


def _item(
    item_id: str,
    *,
    risk: str = "low",
    kind: str = "document",
    status: str = "pending",
    target_ref: str | None = None,
    base_hash: str | None = None,
    base_revision: str | None = None,
    expires_at: datetime | None = None,
) -> MissionReviewItemPayload:
    now = datetime.now(UTC)
    preview = {
        "materialization": {
            "operation": "documents.upsert_prism_file",
            "payload": {"content_inline": "x", "content_hash": "new-hash"},
        }
    }
    preview_hash = hashlib.sha256(
        json.dumps(preview, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    explicit = risk == "high" or kind == "citation"
    return MissionReviewItemPayload(
        review_item_id=item_id,
        mission_id="mission-1",
        source_item_seq=1,
        output_key="document",
        target_kind=kind,
        target_room="documents",
        target_ref=target_ref,
        base_revision_ref=base_revision,
        base_hash=base_hash,
        title=item_id,
        risk_level=risk,
        status=status,
        preview_json=preview,
        preview_hash=preview_hash,
        preview_expires_at=expires_at or now + timedelta(hours=1),
        requires_explicit_review=explicit,
        batch_acceptable=not explicit,
        suggested_selected=not explicit,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_auto_draft_accepts_and_commits_only_eligible_new_document() -> None:
    run = _run(review_mode="auto_draft")
    low_draft = _item("low-draft")
    high_draft = _item("high-draft", risk="high")
    existing_document = _item("existing", target_ref="prism-file:file-1")
    missions = SimpleNamespace(
        get=AsyncMock(return_value=run),
        list_review_items=AsyncMock(
            return_value=[low_draft, high_draft, existing_document]
        ),
        apply_review_decisions=AsyncMock(
            return_value=SimpleNamespace(
                mission=_run(version=2, review_mode="auto_draft"),
                items=[_item("low-draft", status="accepted")],
            )
        ),
    )
    runtime = ReviewCommitRuntime(
        missions=missions,
        target_writer=AsyncMock(),
        membership=_membership(),
    )
    runtime.commit_many = AsyncMock(return_value=CommitBatchOutcome(outcomes=[]))

    await runtime.reconcile_auto_drafts("mission-1")

    decision = missions.apply_review_decisions.await_args.args[1]
    assert decision.actor_user_id == "policy:auto_draft"
    assert decision.decisions[0].review_item_id == "low-draft"
    assert decision.decisions[0].decision_json["action"] == "save_draft_only"
    runtime.commit_many.assert_awaited_once_with(
        "mission-1",
        actor_user_id="user-1",
        review_item_ids=["low-draft"],
    )


@pytest.mark.asyncio
async def test_auto_draft_reconcile_is_inert_outside_auto_draft_mode() -> None:
    missions = SimpleNamespace(
        get=AsyncMock(return_value=_run(review_mode="balanced_default")),
        list_review_items=AsyncMock(),
        apply_review_decisions=AsyncMock(),
    )
    runtime = ReviewCommitRuntime(
        missions=missions,
        target_writer=AsyncMock(),
        membership=_membership(),
    )

    outcome = await runtime.reconcile_auto_drafts("mission-1")

    assert outcome.outcomes == []
    missions.list_review_items.assert_not_awaited()
    missions.apply_review_decisions.assert_not_awaited()


@pytest.mark.asyncio
async def test_bulk_accept_skips_trust_bearing_item_but_applies_low_risk_item() -> None:
    missions = SimpleNamespace(
        list_review_items=AsyncMock(
            return_value=[
                _item("high", risk="high", kind="citation"),
                _item("low"),
            ]
        ),
        get=AsyncMock(return_value=_run()),
        apply_review_decisions=AsyncMock(
            return_value=SimpleNamespace(
                mission=_run(version=2),
                items=[_item("low", status="accepted")],
            )
        ),
    )
    runtime = ReviewCommitRuntime(
        missions=missions,
        target_writer=AsyncMock(),
        membership=_membership(),
    )

    result = await runtime.decide(
        "mission-1",
        actor_user_id="user-1",
        decision_id="decision-1",
        decisions=[
            ReviewDecision(review_item_id="high", action=ReviewAction.ACCEPT),
            ReviewDecision(review_item_id="low", action=ReviewAction.ACCEPT),
        ],
    )

    assert result.partial is True
    assert result.outcomes[0].reason_code == "explicit_review_required"
    assert result.outcomes[1].status == "accepted"
    missions.apply_review_decisions.assert_awaited_once()


@pytest.mark.asyncio
async def test_review_batch_applies_all_allowed_decisions_in_one_transaction() -> None:
    first = _item("first")
    second = _item("second")
    missions = SimpleNamespace(
        list_review_items=AsyncMock(return_value=[first, second]),
        get=AsyncMock(return_value=_run()),
        apply_review_decisions=AsyncMock(
            return_value=SimpleNamespace(
                mission=_run(version=2),
                items=[
                    _item("first", status="accepted"),
                    _item("second", status="rejected"),
                ],
            )
        ),
    )
    runtime = ReviewCommitRuntime(
        missions=missions,
        target_writer=AsyncMock(),
        membership=_membership(),
    )

    result = await runtime.decide(
        "mission-1",
        actor_user_id="user-1",
        decision_id="decision-batch",
        decisions=[
            ReviewDecision(review_item_id="first", action=ReviewAction.ACCEPT),
            ReviewDecision(review_item_id="second", action=ReviewAction.REJECT),
        ],
    )

    assert [item.status for item in result.outcomes] == ["accepted", "rejected"]
    missions.apply_review_decisions.assert_awaited_once()
    payload = missions.apply_review_decisions.await_args.args[1]
    assert [item.review_item_id for item in payload.decisions] == ["first", "second"]


@pytest.mark.asyncio
async def test_review_batch_rejects_duplicate_review_item_ids_before_mutation() -> None:
    missions = SimpleNamespace(
        list_review_items=AsyncMock(),
        get=AsyncMock(),
        apply_review_decisions=AsyncMock(),
    )
    runtime = ReviewCommitRuntime(
        missions=missions,
        target_writer=AsyncMock(),
        membership=_membership(),
    )

    with pytest.raises(ValueError, match="duplicate_review_item_id"):
        await runtime.decide(
            "mission-1",
            actor_user_id="user-1",
            decision_id="decision-batch",
            decisions=[
                ReviewDecision(review_item_id="first", action=ReviewAction.ACCEPT),
                ReviewDecision(review_item_id="first", action=ReviewAction.REJECT),
            ],
        )

    missions.apply_review_decisions.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_existing_target_fails_before_commit_or_write() -> None:
    item = _item(
        "item-1",
        status="accepted",
        target_ref="file-1",
        base_hash="old-hash",
        base_revision="version-1",
    )
    missions = SimpleNamespace(
        get=AsyncMock(return_value=_run()),
        list_review_items=AsyncMock(return_value=[item]),
        get_commit_for_review_item=AsyncMock(return_value=None),
        commit=AsyncMock(),
        apply_review_decisions=AsyncMock(
            return_value=SimpleNamespace(mission=_run(version=2), items=[])
        ),
    )
    writer = SimpleNamespace(
        read_target=AsyncMock(
            return_value=TargetSnapshot(
                target_ref="file-1",
                revision_ref="version-2",
                content_hash="newer-hash",
            )
        ),
        apply=AsyncMock(),
    )
    runtime = ReviewCommitRuntime(
        missions=missions, target_writer=writer, membership=_membership()
    )

    with pytest.raises(ValueError, match="stale_target_precondition"):
        await runtime.commit_one(
            "mission-1",
            actor_user_id="user-1",
            review_item_id="item-1",
            commit_key="commit-key",
        )

    missions.commit.assert_not_awaited()
    writer.apply.assert_not_awaited()


@pytest.mark.asyncio
async def test_commit_many_returns_partial_success_without_rolling_back_siblings() -> None:
    runtime = ReviewCommitRuntime(
        missions=AsyncMock(),
        target_writer=AsyncMock(),
        membership=_membership(),
    )
    committed = MissionCommitPayload(
        commit_id="commit-1",
        mission_id="mission-1",
        review_item_id="item-1",
        commit_key="key-1",
        status=MissionCommitStatus.COMMITTED,
        actor_user_id="user-1",
        attempt_count=1,
        created_at=datetime.now(UTC),
    )
    runtime.commit_one = AsyncMock(
        side_effect=[
            CommitOutcome(
                review_item_id="item-1",
                commit=committed,
                committed=True,
                reason_code=None,
            ),
            ValueError("stale_target_precondition"),
        ]
    )

    result = await runtime.commit_many(
        "mission-1",
        actor_user_id="user-1",
        review_item_ids=["item-1", "item-2"],
    )

    assert result.partial is True
    assert [item.committed for item in result.outcomes] == [True, False]


@pytest.mark.asyncio
async def test_expired_preview_fails_before_target_read() -> None:
    item = _item(
        "item-1",
        status="accepted",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    missions = SimpleNamespace(
        get=AsyncMock(return_value=_run()),
        list_review_items=AsyncMock(return_value=[item]),
        get_commit_for_review_item=AsyncMock(return_value=None),
        apply_review_decisions=AsyncMock(
            return_value=SimpleNamespace(mission=_run(version=2), items=[])
        ),
    )
    writer = SimpleNamespace(read_target=AsyncMock(), apply=AsyncMock())
    runtime = ReviewCommitRuntime(
        missions=missions, target_writer=writer, membership=_membership()
    )

    with pytest.raises(ValueError, match="review_preview_expired"):
        await runtime.commit_one(
            "mission-1",
            actor_user_id="user-1",
            review_item_id="item-1",
            commit_key="key-1",
        )
    writer.read_target.assert_not_awaited()


@pytest.mark.asyncio
async def test_revoked_membership_blocks_review_before_mutation() -> None:
    membership = SimpleNamespace(
        require_active_member=AsyncMock(
            side_effect=PermissionError("active_workspace_membership_required")
        )
    )
    missions = SimpleNamespace(
        get=AsyncMock(return_value=_run()),
        list_review_items=AsyncMock(return_value=[_item("item-1")]),
        apply_review_decisions=AsyncMock(),
    )
    runtime = ReviewCommitRuntime(
        missions=missions,
        target_writer=AsyncMock(),
        membership=membership,
    )

    with pytest.raises(PermissionError, match="active_workspace_membership_required"):
        await runtime.decide(
            "mission-1",
            actor_user_id="user-1",
            decision_id="decision-1",
            decisions=[ReviewDecision(review_item_id="item-1", action="accept")],
        )
    missions.apply_review_decisions.assert_not_awaited()


@pytest.mark.asyncio
async def test_tampered_preview_fails_before_materialization() -> None:
    item = _item("item-1", status="accepted")
    item.preview_json["materialization"]["payload"]["content_inline"] = "tampered"
    missions = SimpleNamespace(
        get=AsyncMock(return_value=_run()),
        list_review_items=AsyncMock(return_value=[item]),
        get_commit_for_review_item=AsyncMock(return_value=None),
        apply_review_decisions=AsyncMock(
            return_value=SimpleNamespace(mission=_run(version=2), items=[])
        ),
    )
    writer = SimpleNamespace(read_target=AsyncMock(), apply=AsyncMock())
    runtime = ReviewCommitRuntime(
        missions=missions,
        target_writer=writer,
        membership=_membership(),
    )

    with pytest.raises(ValueError, match="review_preview_integrity_failed"):
        await runtime.commit_one(
            "mission-1",
            actor_user_id="user-1",
            review_item_id="item-1",
            commit_key="key-1",
        )
    writer.read_target.assert_not_awaited()


@pytest.mark.asyncio
async def test_domain_writer_rejects_unreachable_materialization_operation() -> None:
    item = _item("item-1", status="accepted", kind="decision")
    item.preview_json = {
        "materialization": {
            "operation": "decisions.set",
            "payload": {"key": "citation_style", "value": "IEEE"},
        }
    }

    with pytest.raises(ValueError, match="unknown_materialization_operation"):
        await MissionDomainWriter(SimpleNamespace()).apply(
            item,
            workspace_id="workspace-1",
            mission_commit_id="commit-1",
            mission_commit_attempt_token="attempt-token-commit-1",
            actor_user_id="user-1",
        )


@pytest.mark.asyncio
async def test_domain_writer_materializes_source_candidate_into_library() -> None:
    source = SimpleNamespace(
        id="source-1",
        model_dump=lambda **_: {"id": "source-1", "title": "Verified paper"},
    )
    dataservice = SimpleNamespace(
        import_source=AsyncMock(return_value=SimpleNamespace(source=source))
    )
    item = _item("item-1", status="accepted", kind="source")
    item.target_room = "library"
    item.preview_json = {
        "materialization": {
            "operation": "library.import_source",
            "payload": {
                "source_kind": "paper",
                "title": "Verified paper",
                "authors_json": ["A. Researcher"],
                "year": 2026,
                "venue": "Journal",
                "url": "https://example.org/paper",
                "ingest_kind": "mission_verified",
                "ingest_label": "search-receipt:receipt-1#result-1",
                "library_status": "candidate",
                "evidence_level": "external_verified",
                "citation_key": "Researcher2026",
            },
        }
    }

    receipt = await MissionDomainWriter(dataservice).apply(
        item,
        workspace_id="workspace-1",
        mission_commit_id="commit-1",
        mission_commit_attempt_token="attempt-token-commit-1",
        actor_user_id="user-1",
    )

    command = dataservice.import_source.await_args.args[0]
    assert command.workspace_id == "workspace-1"
    assert command.ingest_mission_id == "mission-1"
    assert command.ingest_mission_commit_id == "commit-1"
    assert command.mission_write_authority.mission_review_item_id == "item-1"
    assert receipt.target_ref == "source-1"
    assert receipt.provenance["mission_commit_id"] == "commit-1"


@pytest.mark.asyncio
async def test_prism_target_reader_resolves_canonical_ref_at_dataservice_boundary() -> None:
    current = SimpleNamespace(
        file=SimpleNamespace(
            id="file-1",
            current_version_id="version-1",
            content_hash="old-hash",
        )
    )
    dataservice = SimpleNamespace(
        get_prism_workspace_file=AsyncMock(return_value=current),
    )
    item = _item(
        "item-1",
        status="accepted",
        target_ref="prism-file:file-1",
        base_hash="old-hash",
        base_revision="version-1",
    )

    snapshot = await MissionDomainWriter(dataservice).read_target(
        item,
        workspace_id="workspace-1",
    )

    dataservice.get_prism_workspace_file.assert_awaited_once_with("workspace-1", "file-1")
    assert snapshot.target_ref == "prism-file:file-1"
    assert snapshot.revision_ref == "version-1"
    assert snapshot.content_hash == "old-hash"


@pytest.mark.asyncio
async def test_prism_target_writer_updates_raw_id_and_returns_canonical_receipt() -> None:
    written = SimpleNamespace(
        file=SimpleNamespace(
            id="file-1",
            current_version_id="version-2",
            content_hash="new-hash",
        ),
        version=SimpleNamespace(id="version-2", content_hash="new-hash"),
        skipped_reason=None,
    )
    dataservice = SimpleNamespace(
        update_prism_workspace_file=AsyncMock(return_value=written),
    )
    item = _item(
        "item-1",
        status="accepted",
        target_ref="prism-file:file-1",
        base_hash="old-hash",
        base_revision="version-1",
    )

    receipt = await MissionDomainWriter(dataservice).apply(
        item,
        workspace_id="workspace-1",
        mission_commit_id="commit-1",
        mission_commit_attempt_token="attempt-token-commit-1",
        actor_user_id="user-1",
    )

    args = dataservice.update_prism_workspace_file.await_args.args
    assert args[:2] == ("workspace-1", "file-1")
    assert args[2].expected_current_hash == "old-hash"
    assert receipt.target_ref == "prism-file:file-1"
    assert receipt.revision_ref == "version-2"


@pytest.mark.asyncio
async def test_prism_new_file_writer_uses_create_only_and_rejects_path_conflict() -> None:
    existing = SimpleNamespace(
        file=SimpleNamespace(
            id="file-existing",
            current_version_id="version-1",
            content_hash="existing-hash",
        ),
        version=None,
        changed=False,
        skipped_reason="already_exists",
    )
    dataservice = SimpleNamespace(
        upsert_prism_workspace_file=AsyncMock(return_value=existing),
    )
    item = _item("item-1", status="accepted")
    item.preview_json["materialization"]["payload"]["path"] = "paper/main.tex"

    with pytest.raises(ValueError, match="target_path_conflict"):
        await MissionDomainWriter(dataservice).apply(
            item,
            workspace_id="workspace-1",
            mission_commit_id="commit-1",
            mission_commit_attempt_token="attempt-token-commit-1",
            actor_user_id="user-1",
        )

    command = dataservice.upsert_prism_workspace_file.await_args.args[1]
    assert command.create_only is True


@pytest.mark.asyncio
async def test_prism_target_writer_rejects_legacy_raw_id() -> None:
    dataservice = SimpleNamespace(update_prism_workspace_file=AsyncMock())
    item = _item(
        "item-1",
        status="accepted",
        target_ref="file-1",
        base_hash="old-hash",
        base_revision="version-1",
    )

    with pytest.raises(ValueError, match="invalid_prism_file_target_ref"):
        await MissionDomainWriter(dataservice).apply(
            item,
            workspace_id="workspace-1",
            mission_commit_id="commit-1",
            mission_commit_attempt_token="attempt-token-commit-1",
            actor_user_id="user-1",
        )

    dataservice.update_prism_workspace_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_external_preview_is_verified_and_deleted_after_successful_commit() -> None:
    item = _item("item-1", status="accepted", kind="workspace_asset")
    item.preview_ref = "mpv1_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    item.preview_json = {
        "materialization": {
            "operation": "assets.create_from_preview",
            "payload": {"content_hash": "a" * 64, "mime_type": "image/png"},
        }
    }
    item.preview_hash = hashlib.sha256(
        json.dumps(item.preview_json, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    now = datetime.now(UTC)
    pending_commit = MissionCommitPayload(
        commit_id="commit-1",
        mission_id="mission-1",
        review_item_id="item-1",
        commit_key="commit-key",
        status="pending",
        actor_user_id="user-1",
        attempt_count=0,
        created_at=now,
    )
    committed = pending_commit.model_copy(update={"status": "committed", "attempt_count": 1})
    missions = SimpleNamespace(
        get=AsyncMock(return_value=_run()),
        list_review_items=AsyncMock(return_value=[item]),
        get_commit_for_review_item=AsyncMock(return_value=None),
        commit=AsyncMock(
            return_value=SimpleNamespace(mission=_run(version=2), commit=pending_commit)
        ),
        start_commit=AsyncMock(),
        finish_commit=AsyncMock(return_value=SimpleNamespace(commit=committed)),
    )
    preview_store = SimpleNamespace(
        read=AsyncMock(
            return_value=PreviewObject(
                descriptor=PreviewObjectDescriptor(
                    ref=item.preview_ref,
                    workspace_id="workspace-1",
                    content_hash="a" * 64,
                    mime_type="image/png",
                    filename="figure.png",
                    size_bytes=8,
                    created_at=now,
                    expires_at=now + timedelta(hours=1),
                ),
                content=b"png-data",
            )
        ),
        delete=AsyncMock(),
    )
    writer = SimpleNamespace(
        read_target=AsyncMock(return_value=TargetSnapshot()),
        apply=AsyncMock(
            return_value=MaterializationReceipt(
                target_ref="asset-1",
                content_hash="a" * 64,
            )
        ),
    )
    runtime = ReviewCommitRuntime(
        missions=missions,
        target_writer=writer,
        membership=_membership(),
        preview_store=preview_store,
    )

    outcome = await runtime.commit_one(
        "mission-1",
        actor_user_id="user-1",
        review_item_id="item-1",
        commit_key="commit-key",
    )

    assert outcome.committed is True
    preview_store.read.assert_awaited_once_with(item.preview_ref, workspace_id="workspace-1")
    preview_store.delete.assert_awaited_once_with(item.preview_ref, workspace_id="workspace-1")


@pytest.mark.asyncio
async def test_expired_applying_commit_replays_writer_without_old_base_check() -> None:
    item = _item(
        "item-1",
        status="accepted",
        target_ref="prism-file:file-1",
        base_hash="old-hash",
        base_revision="version-1",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    now = datetime.now(UTC)
    applying = MissionCommitPayload(
        commit_id="commit-1",
        mission_id="mission-1",
        review_item_id="item-1",
        commit_key="mission-review-item:item-1",
        status="applying",
        actor_user_id="user-1",
        attempt_count=1,
        attempt_token="old-attempt-token",
        attempt_expires_at=now - timedelta(seconds=1),
        created_at=now,
    )
    committed = applying.model_copy(update={"status": "committed", "attempt_count": 2})
    missions = SimpleNamespace(
        get=AsyncMock(return_value=_run()),
        list_review_items=AsyncMock(return_value=[item]),
        get_commit_for_review_item=AsyncMock(
            return_value=SimpleNamespace(mission=_run(), commit=applying)
        ),
        commit=AsyncMock(
            return_value=SimpleNamespace(mission=_run(version=2), commit=applying)
        ),
        start_commit=AsyncMock(),
        finish_commit=AsyncMock(return_value=SimpleNamespace(commit=committed)),
    )
    writer = SimpleNamespace(
        read_target=AsyncMock(
            return_value=TargetSnapshot(
                target_ref="prism-file:file-1",
                revision_ref="version-2",
                content_hash="new-hash",
            )
        ),
        apply=AsyncMock(
            return_value=MaterializationReceipt(
                target_ref="prism-file:file-1",
                revision_ref="version-2",
                content_hash="new-hash",
            )
        ),
    )
    runtime = ReviewCommitRuntime(
        missions=missions,
        target_writer=writer,
        membership=_membership(),
    )

    outcome = await runtime.commit_one(
        "mission-1",
        actor_user_id="user-1",
        review_item_id="item-1",
        commit_key="mission-review-item:item-1",
    )

    assert outcome.committed is True
    writer.read_target.assert_not_awaited()
    writer.apply.assert_awaited_once()
    missions.finish_commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_unknown_materialization_outcome_stays_applying_for_idempotent_replay() -> None:
    item = _item("item-1", status="accepted")
    now = datetime.now(UTC)
    pending = MissionCommitPayload(
        commit_id="commit-1",
        mission_id="mission-1",
        review_item_id="item-1",
        commit_key="mission-review-item:item-1",
        status="pending",
        actor_user_id="user-1",
        attempt_count=0,
        created_at=now,
    )
    missions = SimpleNamespace(
        get=AsyncMock(return_value=_run()),
        list_review_items=AsyncMock(return_value=[item]),
        get_commit_for_review_item=AsyncMock(return_value=None),
        commit=AsyncMock(
            return_value=SimpleNamespace(mission=_run(version=2), commit=pending)
        ),
        start_commit=AsyncMock(),
        finish_commit=AsyncMock(),
    )
    writer = SimpleNamespace(
        read_target=AsyncMock(return_value=TargetSnapshot()),
        apply=AsyncMock(side_effect=httpx.ReadTimeout("response lost")),
    )
    runtime = ReviewCommitRuntime(
        missions=missions,
        target_writer=writer,
        membership=_membership(),
    )

    with pytest.raises(httpx.ReadTimeout, match="response lost"):
        await runtime.commit_one(
            "mission-1",
            actor_user_id="user-1",
            review_item_id="item-1",
            commit_key="mission-review-item:item-1",
        )

    missions.start_commit.assert_awaited_once()
    missions.finish_commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_commit_batch_uses_one_stable_key_per_review_item() -> None:
    runtime = ReviewCommitRuntime(
        missions=AsyncMock(),
        target_writer=AsyncMock(),
        membership=_membership(),
    )
    runtime.commit_one = AsyncMock(
        return_value=CommitOutcome(review_item_id="item-1", committed=True)
    )

    await runtime.commit_many(
        "mission-1",
        actor_user_id="user-1",
        review_item_ids=["item-1"],
    )

    assert runtime.commit_one.await_args.kwargs["commit_key"] == "mission-review-item:item-1"
