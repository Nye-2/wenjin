"""Mission operation claims and append-only execution ledger."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import timedelta
from typing import Any

from src.contracts.model_usage import (
    ModelCallLedgerBinding,
    ModelCallStartedPayload,
    ModelCallState,
    ModelCallTerminalOutcome,
    ModelCallTerminalPayload,
    ModelUsageReceiptPayload,
)
from src.contracts.subagent_progress import validate_subagent_progress_identity
from src.database.models.mission import MissionItemRecord, MissionRunRecord
from src.dataservice.common.errors import (
    DataServiceConflictError,
    DataServiceNotFoundError,
    DataServiceValidationError,
)
from src.dataservice.domains.mission._store_core import (
    TERMINAL_MISSION_STATUSES,
    _aware,
    _operation_receipt_from_items,
)
from src.dataservice.domains.mission.projection import (
    mission_item_to_payload,
    mission_run_to_payload,
)
from src.dataservice_client.contracts.mission import (
    MissionAppendPayload,
    MissionAppendResultPayload,
    MissionCheckpointPayload,
    MissionItemDraftPayload,
    MissionModelCallStatePayload,
    MissionOperationClaimPayload,
    MissionOperationClaimResultPayload,
    MissionOperationFinishPayload,
    MissionOperationFinishResultPayload,
    MissionOperationReceiptPayload,
)

_MODEL_LEDGER_ITEM_TYPES = frozenset(
    {"model_call_started", "usage_receipt", "model_call_terminal"}
)
_MODEL_TERMINAL_ITEM_TYPES = frozenset(
    {"usage_receipt", "model_call_terminal"}
)
_MODEL_DISPATCH_ITEM_TYPES = frozenset(
    {"model_call_started", "subagent_spawned"}
)

ModelLedgerPayload = (
    ModelCallStartedPayload
    | ModelUsageReceiptPayload
    | ModelCallTerminalPayload
)


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)


def _execution_record_matches(
    record: MissionItemRecord,
    draft: MissionItemDraftPayload,
) -> bool:
    return (
        record.item_type == draft.item_type
        and record.operation_id == draft.operation_id
        and record.phase == _enum_value(draft.phase)
        and record.stage_id == draft.stage_id
        and record.producer == draft.producer
        and record.summary == draft.summary
        and record.risk_level == _enum_value(draft.risk_level)
        and dict(record.payload_json or {}) == draft.payload_json
        and record.payload_ref == draft.payload_ref
    )


def _validate_subagent_progress_item(
    run: MissionRunRecord,
    *,
    operation_id: str | None,
    phase: object,
    producer: str | None,
    summary: str | None,
    payload_json: dict[str, Any],
) -> str:
    try:
        progress_id, _progress_hash = validate_subagent_progress_identity(
            summary=summary,
            payload_json=payload_json,
        )
    except ValueError as exc:
        raise DataServiceValidationError(
            "Mission subagent progress identity is invalid",
            detail={
                "mission_id": run.mission_id,
                "operation_id": operation_id,
                "reason": str(exc),
            },
        ) from exc
    job_id = str(payload_json["job_id"])
    lifecycle_phase = str(payload_json["lifecycle_phase"])
    expected_phase = "completed" if lifecycle_phase == "terminal" else "progress"
    if (
        not operation_id
        or producer != job_id
        or _enum_value(phase) != expected_phase
    ):
        raise DataServiceValidationError(
            "Mission subagent progress binding is invalid",
            detail={
                "mission_id": run.mission_id,
                "operation_id": operation_id,
                "progress_id": progress_id,
            },
        )
    return progress_id


def _ledger_binding(
    payload: ModelLedgerPayload,
) -> ModelCallLedgerBinding:
    return ModelCallLedgerBinding.model_validate(
        payload.model_dump(
            mode="python",
            include={
                "model_call_id",
                "model_id",
                "turn",
                "attempt",
                "parent_operation_id",
                "job_id",
            },
        )
    )


def _validate_model_ledger_item(
    run: MissionRunRecord,
    *,
    item_type: str,
    operation_id: str | None,
    phase: object,
    producer: str | None,
    payload_json: dict[str, Any],
) -> ModelLedgerPayload:
    if not operation_id or not producer:
        raise DataServiceValidationError(
            "Mission model ledger item is semantically incomplete",
            detail={
                "mission_id": run.mission_id,
                "item_type": item_type,
                "operation_id": operation_id,
            },
        )
    payload_type: type[ModelLedgerPayload]
    if item_type == "model_call_started":
        payload_type = ModelCallStartedPayload
    elif item_type == "usage_receipt":
        payload_type = ModelUsageReceiptPayload
    elif item_type == "model_call_terminal":
        payload_type = ModelCallTerminalPayload
    else:
        raise DataServiceValidationError(
            "Mission model ledger item type is invalid",
            detail={"mission_id": run.mission_id, "item_type": item_type},
        )
    try:
        payload = payload_type.model_validate(payload_json)
    except ValueError as exc:
        raise DataServiceValidationError(
            "Mission model ledger payload is invalid",
            detail={
                "mission_id": run.mission_id,
                "item_type": item_type,
                "operation_id": operation_id,
                "reason": str(exc),
            },
        ) from exc
    expected_phase = {
        "model_call_started": "started",
        "usage_receipt": "completed",
        "model_call_terminal": (
            "cancelled"
            if isinstance(payload, ModelCallTerminalPayload)
            and payload.outcome is ModelCallTerminalOutcome.CANCELLED
            else "failed"
        ),
    }[item_type]
    if _enum_value(phase) != expected_phase:
        raise DataServiceValidationError(
            "Mission model ledger phase does not match its terminal semantics",
            detail={
                "mission_id": run.mission_id,
                "item_type": item_type,
                "operation_id": operation_id,
                "expected_phase": expected_phase,
            },
        )
    if payload.model_call_id != operation_id or payload.model_id != run.model_id:
        raise DataServiceValidationError(
            "Mission model ledger identity does not match the Mission call",
            detail={
                "mission_id": run.mission_id,
                "item_type": item_type,
                "operation_id": operation_id,
            },
        )
    if payload.job_id is None:
        if producer != "workspace_agent":
            raise DataServiceValidationError(
                "Workspace model ledger items require the workspace_agent producer",
                detail={"mission_id": run.mission_id, "operation_id": operation_id},
            )
    elif producer != payload.job_id:
        raise DataServiceValidationError(
            "Subagent model ledger producer must match job_id",
            detail={"mission_id": run.mission_id, "operation_id": operation_id},
        )
    return payload


def _require_terminal_matches_started(
    run: MissionRunRecord,
    *,
    operation_id: str,
    terminal_payload: ModelUsageReceiptPayload | ModelCallTerminalPayload,
    terminal_stage_id: str | None,
    terminal_producer: str,
    started: tuple[ModelCallStartedPayload, str | None, str, int | None],
    terminal_seq: int | None = None,
) -> None:
    started_payload, started_stage_id, started_producer, started_seq = started
    matches = (
        _ledger_binding(terminal_payload) == _ledger_binding(started_payload)
        and terminal_stage_id == started_stage_id
        and terminal_producer == started_producer
        and (
            terminal_seq is None
            or started_seq is None
            or terminal_seq > started_seq
        )
    )
    if not matches:
        raise DataServiceValidationError(
            "Mission model call terminal does not match its started model call",
            detail={"mission_id": run.mission_id, "operation_id": operation_id},
        )


def _model_call_states_from_records(
    run: MissionRunRecord,
    records: list[MissionItemRecord],
) -> list[MissionModelCallStatePayload]:
    grouped: dict[
        str,
        dict[str, tuple[MissionItemRecord, ModelLedgerPayload]],
    ] = {}
    for record in records:
        operation_id = str(record.operation_id or "")
        payload = _validate_model_ledger_item(
            run,
            item_type=record.item_type,
            operation_id=record.operation_id,
            phase=record.phase,
            producer=record.producer,
            payload_json=dict(record.payload_json or {}),
        )
        entries = grouped.setdefault(operation_id, {})
        key = (
            "started"
            if record.item_type == "model_call_started"
            else "terminal"
        )
        if key in entries:
            raise DataServiceConflictError(
                "Mission model_call_id has duplicate durable ledger rows",
                detail={
                    "mission_id": run.mission_id,
                    "operation_id": operation_id,
                    "ledger_phase": key,
                },
            )
        entries[key] = (record, payload)

    projected: list[MissionModelCallStatePayload] = []
    for operation_id, entries in grouped.items():
        started_entry = entries.get("started")
        terminal_entry = entries.get("terminal")
        if started_entry is None:
            raise DataServiceValidationError(
                "Mission model call terminal has no durable started call",
                detail={
                    "mission_id": run.mission_id,
                    "operation_id": operation_id,
                },
            )
        started_record, started_payload = started_entry
        assert isinstance(started_payload, ModelCallStartedPayload)
        state = ModelCallState.OPEN
        terminal_item = None
        if terminal_entry is not None:
            terminal_record, terminal_payload = terminal_entry
            assert isinstance(
                terminal_payload,
                (ModelUsageReceiptPayload, ModelCallTerminalPayload),
            )
            _require_terminal_matches_started(
                run,
                operation_id=operation_id,
                terminal_payload=terminal_payload,
                terminal_stage_id=terminal_record.stage_id,
                terminal_producer=str(terminal_record.producer),
                started=(
                    started_payload,
                    started_record.stage_id,
                    str(started_record.producer),
                    started_record.seq,
                ),
                terminal_seq=terminal_record.seq,
            )
            state = (
                ModelCallState.RECEIPT
                if isinstance(terminal_payload, ModelUsageReceiptPayload)
                else ModelCallState(terminal_payload.outcome.value)
            )
            terminal_item = mission_item_to_payload(terminal_record)
        projected.append(
            MissionModelCallStatePayload(
                state=state,
                started=mission_item_to_payload(started_record),
                terminal=terminal_item,
            )
        )
    projected.sort(key=lambda item: item.started.seq)
    return projected


def _parallel_subagent_model_starts_allowed(
    states: list[MissionModelCallStatePayload],
    drafts: list[MissionItemDraftPayload],
) -> bool:
    dispatch_drafts = [
        draft
        for draft in drafts
        if draft.item_type in _MODEL_DISPATCH_ITEM_TYPES
    ]
    if not dispatch_drafts or any(
        draft.item_type != "model_call_started" for draft in dispatch_drafts
    ):
        return False
    if any(state.state is not ModelCallState.OPEN for state in states):
        return False
    existing_payloads = [
        ModelCallStartedPayload.model_validate(state.started.payload_json)
        for state in states
    ]
    parent_operation_ids = {
        payload.parent_operation_id for payload in existing_payloads
    }
    if None in parent_operation_ids or len(parent_operation_ids) != 1:
        return False
    parent_operation_id = next(iter(parent_operation_ids))
    active_job_ids = {payload.job_id for payload in existing_payloads}
    for draft in dispatch_drafts:
        payload = ModelCallStartedPayload.model_validate(draft.payload_json)
        if (
            payload.parent_operation_id != parent_operation_id
            or payload.job_id is None
            or payload.job_id in active_job_ids
        ):
            return False
        active_job_ids.add(payload.job_id)
    return True


class MissionExecutionOperations:
    """Mission operation claims and append-only execution ledger."""

    async def _model_call_states(
        self,
        run: MissionRunRecord,
    ) -> list[MissionModelCallStatePayload]:
        records = await self.repository.list_model_ledger_items(
            mission_id=run.mission_id,
        )
        return _model_call_states_from_records(run, records)

    async def list_model_call_states(
        self,
        mission_id: str,
    ) -> list[MissionModelCallStatePayload]:
        run = await self.repository.get_run(mission_id)
        if run is None:
            raise DataServiceNotFoundError("MissionRun not found")
        return await self._model_call_states(run)

    @staticmethod
    def _model_call_issue_ids(
        states: list[MissionModelCallStatePayload],
    ) -> tuple[str, ...]:
        return tuple(
            str(state.started.operation_id)
            for state in states
            if state.state in {ModelCallState.OPEN, ModelCallState.UNRESOLVED}
        )

    async def _prepare_execution_ledger_append(
        self,
        run: MissionRunRecord,
        drafts: list[MissionItemDraftPayload],
    ) -> tuple[list[MissionItemDraftPayload], dict[int, MissionItemRecord]]:
        model_positions = [
            index
            for index, draft in enumerate(drafts)
            if draft.item_type in _MODEL_LEDGER_ITEM_TYPES
        ]
        progress_positions = [
            index
            for index, draft in enumerate(drafts)
            if draft.item_type == "subagent_progress"
        ]
        if not model_positions and not progress_positions:
            return list(drafts), {}

        operation_ids: list[str] = []
        for index in model_positions:
            operation_id = drafts[index].operation_id
            if not operation_id:
                raise DataServiceValidationError(
                    "Mission model ledger item requires operation_id",
                    detail={
                        "mission_id": run.mission_id,
                        "item_type": drafts[index].item_type,
                    },
                )
            operation_ids.append(operation_id)
        existing_records = await self.repository.list_model_ledger_items(
            mission_id=run.mission_id,
            operation_ids=tuple(dict.fromkeys(operation_ids)),
        )
        existing_by_key: dict[tuple[str, str], MissionItemRecord] = {}
        parsed_existing: dict[tuple[str, str], ModelLedgerPayload] = {}
        for record in existing_records:
            operation_id = str(record.operation_id or "")
            key = (operation_id, record.item_type)
            if not operation_id or key in existing_by_key:
                raise DataServiceConflictError(
                    "Mission model_call_id has duplicate durable ledger rows",
                    detail={
                        "mission_id": run.mission_id,
                        "operation_id": operation_id or None,
                        "item_type": record.item_type,
                    },
                )
            existing_by_key[key] = record
            parsed_existing[key] = _validate_model_ledger_item(
                run,
                item_type=record.item_type,
                operation_id=record.operation_id,
                phase=record.phase,
                producer=record.producer,
                payload_json=dict(record.payload_json or {}),
            )
        _model_call_states_from_records(run, existing_records)

        progress_operation_ids: list[str] = []
        progress_ids_by_position: dict[int, str] = {}
        for index in progress_positions:
            draft = drafts[index]
            progress_id = _validate_subagent_progress_item(
                run,
                operation_id=draft.operation_id,
                phase=draft.phase,
                producer=draft.producer,
                summary=draft.summary,
                payload_json=draft.payload_json,
            )
            assert draft.operation_id is not None
            progress_operation_ids.append(draft.operation_id)
            progress_ids_by_position[index] = progress_id
        existing_progress = await self.repository.list_subagent_progress_items(
            mission_id=run.mission_id,
            operation_ids=tuple(dict.fromkeys(progress_operation_ids)),
        )
        existing_progress_by_id: dict[str, MissionItemRecord] = {}
        for record in existing_progress:
            progress_id = _validate_subagent_progress_item(
                run,
                operation_id=record.operation_id,
                phase=record.phase,
                producer=record.producer,
                summary=record.summary,
                payload_json=dict(record.payload_json or {}),
            )
            if progress_id in existing_progress_by_id:
                raise DataServiceConflictError(
                    "Mission subagent progress identity has duplicate durable rows",
                    detail={
                        "mission_id": run.mission_id,
                        "progress_id": progress_id,
                    },
                )
            existing_progress_by_id[progress_id] = record

        starts: dict[
            str, tuple[ModelCallStartedPayload, str | None, str, int | None]
        ] = {}
        for (operation_id, item_type), record in existing_by_key.items():
            if item_type != "model_call_started":
                continue
            payload = parsed_existing[(operation_id, item_type)]
            assert isinstance(payload, ModelCallStartedPayload)
            starts[operation_id] = (
                payload,
                record.stage_id,
                str(record.producer),
                record.seq,
            )
        terminal_types: dict[str, str] = {}
        for (operation_id, item_type), record in existing_by_key.items():
            if item_type not in _MODEL_TERMINAL_ITEM_TYPES:
                continue
            payload = parsed_existing[(operation_id, item_type)]
            assert isinstance(
                payload,
                (ModelUsageReceiptPayload, ModelCallTerminalPayload),
            )
            started = starts.get(operation_id)
            if started is None:
                raise DataServiceValidationError(
                    "Mission model call terminal has no durable started call",
                    detail={
                        "mission_id": run.mission_id,
                        "operation_id": operation_id,
                    },
                )
            _require_terminal_matches_started(
                run,
                operation_id=operation_id,
                terminal_payload=payload,
                terminal_stage_id=record.stage_id,
                terminal_producer=str(record.producer),
                started=started,
                terminal_seq=record.seq,
            )
            terminal_types[operation_id] = item_type

        replayed: dict[int, MissionItemRecord] = {}
        drafts_to_append: list[MissionItemDraftPayload] = []
        command_keys: set[tuple[str, str]] = set()
        command_progress_ids: set[str] = set()
        for index, draft in enumerate(drafts):
            if draft.item_type == "subagent_progress":
                progress_id = progress_ids_by_position[index]
                if progress_id in command_progress_ids:
                    raise DataServiceValidationError(
                        "Mission append contains duplicate subagent progress identity",
                        detail={
                            "mission_id": run.mission_id,
                            "progress_id": progress_id,
                        },
                    )
                command_progress_ids.add(progress_id)
                existing_progress_item = existing_progress_by_id.get(progress_id)
                if existing_progress_item is not None:
                    if not _execution_record_matches(
                        existing_progress_item,
                        draft,
                    ):
                        raise DataServiceConflictError(
                            "Mission subagent progress identity has divergent content",
                            detail={
                                "mission_id": run.mission_id,
                                "progress_id": progress_id,
                            },
                        )
                    replayed[index] = existing_progress_item
                    continue
                drafts_to_append.append(draft)
                continue
            if draft.item_type not in _MODEL_LEDGER_ITEM_TYPES:
                drafts_to_append.append(draft)
                continue
            operation_id = str(draft.operation_id or "")
            key = (operation_id, draft.item_type)
            if key in command_keys:
                raise DataServiceValidationError(
                    "Mission append contains duplicate model ledger items",
                    detail={
                        "mission_id": run.mission_id,
                        "operation_id": operation_id,
                        "item_type": draft.item_type,
                    },
                )
            command_keys.add(key)
            payload = _validate_model_ledger_item(
                run,
                item_type=draft.item_type,
                operation_id=draft.operation_id,
                phase=draft.phase,
                producer=draft.producer,
                payload_json=draft.payload_json,
            )
            existing = existing_by_key.get(key)
            if existing is not None:
                if not _execution_record_matches(existing, draft):
                    raise DataServiceConflictError(
                        "Mission model_call_id is bound to a divergent ledger item",
                        detail={
                            "mission_id": run.mission_id,
                            "operation_id": operation_id,
                            "item_type": draft.item_type,
                        },
                    )
                replayed[index] = existing
                continue

            if isinstance(payload, ModelCallStartedPayload):
                if operation_id in starts:
                    raise DataServiceConflictError(
                        "Mission model_call_id already has a started ledger item",
                        detail={
                            "mission_id": run.mission_id,
                            "operation_id": operation_id,
                        },
                    )
                starts[operation_id] = (
                    payload,
                    draft.stage_id,
                    str(draft.producer),
                    None,
                )
            else:
                prior_terminal_type = terminal_types.get(operation_id)
                if prior_terminal_type is not None:
                    raise DataServiceConflictError(
                        "Mission model_call_id already has a terminal ledger item",
                        detail={
                            "mission_id": run.mission_id,
                            "operation_id": operation_id,
                            "existing_item_type": prior_terminal_type,
                            "requested_item_type": draft.item_type,
                        },
                    )
                started = starts.get(operation_id)
                if started is None:
                    raise DataServiceValidationError(
                        "Mission model call terminal requires a matching started model call",
                        detail={
                            "mission_id": run.mission_id,
                            "operation_id": operation_id,
                        },
                    )
                assert isinstance(
                    payload,
                    (ModelUsageReceiptPayload, ModelCallTerminalPayload),
                )
                _require_terminal_matches_started(
                    run,
                    operation_id=operation_id,
                    terminal_payload=payload,
                    terminal_stage_id=draft.stage_id,
                    terminal_producer=str(draft.producer),
                    started=started,
                )
                terminal_types[operation_id] = draft.item_type
            drafts_to_append.append(draft)
        return drafts_to_append, replayed

    async def claim_operation(
        self,
        mission_id: str,
        command: MissionOperationClaimPayload,
    ) -> MissionOperationClaimResultPayload:
        run = await self._locked_run(mission_id)
        model_call_issues = self._model_call_issue_ids(
            await self._model_call_states(run)
        )
        if model_call_issues:
            raise DataServiceConflictError(
                "Mission model calls must be closed before operation dispatch",
                detail={
                    "mission_id": mission_id,
                    "model_call_ids": list(model_call_issues),
                },
            )
        now = await self.repository.database_now()
        self._require_effect_epoch(run, lease_epoch=command.lease_epoch, now=now)
        items = await self.repository.list_operation_receipt_items(
            mission_id=mission_id,
            operation_id=command.operation_key,
        )
        receipt = _operation_receipt_from_items(mission_id, command.operation_key, items)
        if receipt is not None and (receipt.kind != command.kind or receipt.request_hash != command.request_hash):
            raise DataServiceConflictError(
                "Operation key is already bound to a different request",
                detail={"mission_id": mission_id, "operation_key": command.operation_key},
            )
        if receipt is not None and receipt.status.value != "claimed":
            return MissionOperationClaimResultPayload(receipt=receipt, acquired=False)
        expires_at = _aware(receipt.lease_expires_at) if receipt is not None else None
        if receipt is not None and expires_at is not None and expires_at > now:
            return MissionOperationClaimResultPayload(receipt=receipt, acquired=False)
        attempt = (receipt.attempt + 1) if receipt is not None else 1
        claim_token = secrets.token_urlsafe(32)
        expires_at = now + timedelta(seconds=command.ttl_seconds)
        claim = self._append_drafts(
            run,
            [
                MissionItemDraftPayload(
                    item_type="operation_claim",
                    operation_id=command.operation_key,
                    phase="started",
                    producer=command.claimant,
                    summary=f"{command.kind.value} operation claimed",
                    payload_json={
                        "kind": command.kind.value,
                        "request_hash": command.request_hash,
                        "status": "claimed",
                        "claimant": command.claimant,
                        "lease_epoch": command.lease_epoch,
                        "claim_token": claim_token,
                        "lease_expires_at": expires_at.isoformat(),
                        "attempt": attempt,
                    },
                )
            ],
            now=now,
        )[0]
        self._touch(run, now)
        await self._finish()
        return MissionOperationClaimResultPayload(
            receipt=_operation_receipt_from_items(
                mission_id,
                command.operation_key,
                [*items, claim],
            ),
            acquired=True,
        )

    async def get_operation(
        self,
        mission_id: str,
        operation_key: str,
    ) -> MissionOperationReceiptPayload | None:
        if await self.repository.get_run(mission_id) is None:
            raise DataServiceNotFoundError("MissionRun not found")
        items = await self.repository.list_operation_receipt_items(
            mission_id=mission_id,
            operation_id=operation_key,
        )
        return _operation_receipt_from_items(mission_id, operation_key, items)

    async def finish_operation(
        self,
        mission_id: str,
        command: MissionOperationFinishPayload,
    ) -> MissionOperationFinishResultPayload:
        run = await self._locked_run(mission_id)
        now = await self.repository.database_now()
        self._require_effect_epoch(run, lease_epoch=command.lease_epoch, now=now)
        items = await self.repository.list_operation_receipt_items(
            mission_id=mission_id,
            operation_id=command.operation_key,
        )
        receipt = _operation_receipt_from_items(mission_id, command.operation_key, items)
        if receipt is None:
            raise DataServiceConflictError("Operation must be claimed before it can finish")
        if receipt.kind != command.kind or receipt.request_hash != command.request_hash:
            raise DataServiceConflictError("Operation finish does not match the claimed request")
        if receipt.claim_token != command.claim_token:
            raise DataServiceConflictError("Operation terminal claim fence was lost")
        desired = command.model_dump(mode="json")["receipt_json"]
        reference_projection = [item.model_dump(mode="json") for item in command.references]
        reference_projection_hash = hashlib.sha256(
            json.dumps(
                reference_projection,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        if receipt.status.value != "claimed":
            terminal_item = next(
                (item for item in reversed(items) if item.item_type == "operation_terminal"),
                None,
            )
            same = (
                receipt.status == command.status
                and receipt.receipt_json == desired
                and receipt.payload_ref == command.payload_ref
                and terminal_item is not None
                and terminal_item.payload_json.get("reference_projection_hash") == reference_projection_hash
            )
            if not same:
                raise DataServiceConflictError("Terminal operation receipt is immutable")
            return MissionOperationFinishResultPayload(
                receipt=receipt,
                finalized=False,
            )
        if receipt.claimant != command.claimant or receipt.lease_epoch != command.lease_epoch:
            raise DataServiceConflictError("Operation terminal fence was lost")
        appended = self._append_drafts(
            run,
            [
                MissionItemDraftPayload(
                    item_type="operation_terminal",
                    operation_id=command.operation_key,
                    phase=("completed" if command.status.value == "succeeded" else "failed"),
                    producer=command.claimant,
                    summary=f"{command.kind.value} operation {command.status.value}",
                    payload_json={
                        "kind": command.kind.value,
                        "request_hash": command.request_hash,
                        "status": command.status.value,
                        "claimant": command.claimant,
                        "lease_epoch": command.lease_epoch,
                        "claim_token": command.claim_token,
                        "attempt": receipt.attempt,
                        "receipt": desired,
                        "reference_projection_hash": reference_projection_hash,
                    },
                    payload_ref=command.payload_ref,
                ),
                *[
                    MissionItemDraftPayload(
                        item_type=reference.category,
                        operation_id=command.operation_key,
                        phase="completed",
                        stage_id=command.stage_id,
                        producer=command.producer or command.claimant,
                        summary=reference.title or reference.reference_id,
                        payload_json={
                            "reference_id": reference.reference_id,
                            "kind": reference.reference_kind,
                            "title": reference.title,
                            "uri": reference.uri,
                            "metadata": reference.metadata,
                            "source_type": reference.source_type,
                            "verified": reference.verified,
                            "receipt_operation_key": command.operation_key,
                        },
                        payload_ref=reference.reference_id,
                    )
                    for reference in command.references
                ],
            ],
            now=now,
        )
        terminal = appended[0]
        self._touch(run, now)
        await self._finish()
        return MissionOperationFinishResultPayload(
            receipt=_operation_receipt_from_items(
                mission_id,
                command.operation_key,
                [*items, terminal],
            ),
            finalized=True,
        )

    async def append_items_and_update_snapshot(
        self,
        mission_id: str,
        command: MissionAppendPayload,
    ) -> MissionAppendResultPayload:
        if any(item.item_type == "command_received" for item in command.items):
            raise DataServiceValidationError("command_received must use append_command_once so the durable cursor advances")
        run = await self._locked_run(mission_id)
        now = await self.repository.database_now()
        drafts_to_append, replayed = await self._prepare_execution_ledger_append(
            run,
            command.items,
        )
        if command.items and len(replayed) == len(command.items):
            if (
                command.snapshot_json is not None
                or command.patch.model_fields_set
            ):
                raise DataServiceConflictError(
                    "Mission execution ledger replay cannot apply new run state",
                    detail={"mission_id": mission_id},
                )
            self._require_driver_fence(
                run,
                expected_state_version=run.state_version,
                lease_owner=command.lease_owner,
                lease_epoch=command.lease_epoch,
                now=now,
            )
            await self._finish()
            return MissionAppendResultPayload(
                mission=mission_run_to_payload(run),
                items=[
                    mission_item_to_payload(replayed[index])
                    for index in range(len(command.items))
                ],
            )
        model_call_states = await self._model_call_states(run)
        issue_ids = self._model_call_issue_ids(model_call_states)
        if (
            issue_ids
            and any(
                draft.item_type in _MODEL_DISPATCH_ITEM_TYPES
                for draft in drafts_to_append
            )
            and not _parallel_subagent_model_starts_allowed(
                [
                    state
                    for state in model_call_states
                    if state.state in {
                        ModelCallState.OPEN,
                        ModelCallState.UNRESOLVED,
                    }
                ],
                drafts_to_append,
            )
        ):
            raise DataServiceConflictError(
                "Mission model calls require closure or reconciliation before dispatch",
                detail={
                    "mission_id": mission_id,
                    "model_call_ids": list(issue_ids),
                },
            )
        terminalized_ids = {
            str(draft.operation_id)
            for draft in drafts_to_append
            if draft.item_type in _MODEL_TERMINAL_ITEM_TYPES
            and draft.operation_id is not None
        }
        open_after_append = {
            str(model_call.started.operation_id)
            for model_call in model_call_states
            if model_call.state is ModelCallState.OPEN
            and model_call.started.operation_id not in terminalized_ids
        }
        open_after_append.update(
            str(draft.operation_id)
            for draft in drafts_to_append
            if draft.item_type == "model_call_started"
            and draft.operation_id is not None
            and draft.operation_id not in terminalized_ids
        )
        issues_after_append = set(issue_ids)
        for draft in drafts_to_append:
            operation_id = str(draft.operation_id or "")
            if draft.item_type == "model_call_started":
                issues_after_append.add(operation_id)
            elif draft.item_type == "usage_receipt":
                issues_after_append.discard(operation_id)
            elif draft.item_type == "model_call_terminal":
                terminal = ModelCallTerminalPayload.model_validate(
                    draft.payload_json
                )
                if terminal.outcome is ModelCallTerminalOutcome.UNRESOLVED:
                    issues_after_append.add(operation_id)
                else:
                    issues_after_append.discard(operation_id)
        if (
            issues_after_append
            and "active_stage_id" in command.patch.model_fields_set
            and command.patch.active_stage_id != run.active_stage_id
        ):
            raise DataServiceConflictError(
                "Mission cannot advance stages with model calls requiring closure",
                detail={
                    "mission_id": mission_id,
                    "model_call_ids": sorted(issues_after_append),
                },
            )
        patch_status = _enum_value(command.patch.status)
        if patch_status == "waiting" and issues_after_append:
            raise DataServiceConflictError(
                "Mission cannot wait with model calls requiring closure",
                detail={
                    "mission_id": mission_id,
                    "model_call_ids": sorted(issues_after_append),
                },
            )
        if patch_status in TERMINAL_MISSION_STATUSES and open_after_append:
            raise DataServiceConflictError(
                "Mission cannot become terminal with open model calls",
                detail={
                    "mission_id": mission_id,
                    "model_call_ids": sorted(open_after_append),
                },
            )
        self._require_driver_fence(
            run,
            expected_state_version=command.expected_state_version,
            lease_owner=command.lease_owner,
            lease_epoch=command.lease_epoch,
            now=now,
        )
        prepared_snapshot = (
            self._prepare_snapshot_replacement(
                run,
                command.snapshot_json,
            )
            if command.snapshot_json is not None
            else None
        )
        records = self._append_drafts(
            run,
            drafts_to_append,
            now=now,
            execution_ledger_validated=True,
        )
        if prepared_snapshot is not None:
            self._install_prepared_snapshot(run, prepared_snapshot)
        self._apply_patch(run, command.patch, now=now)
        self._touch(run, now)
        await self._finish()
        appended = iter(records)
        resolved_records = [
            replayed[index] if index in replayed else next(appended)
            for index in range(len(command.items))
        ]
        return MissionAppendResultPayload(
            mission=mission_run_to_payload(run),
            items=[mission_item_to_payload(record) for record in resolved_records],
        )

    async def checkpoint_run(
        self,
        mission_id: str,
        command: MissionCheckpointPayload,
    ) -> MissionAppendResultPayload:
        """Persist one safe-boundary snapshot under the normal driver fence."""
        return await self.append_items_and_update_snapshot(mission_id, command)

__all__ = ['MissionExecutionOperations']
