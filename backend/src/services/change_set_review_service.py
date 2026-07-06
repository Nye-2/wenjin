"""Review-state service for execution ChangeSets."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from typing import Any, Literal

from src.contracts.change_set import ChangeSet
from src.dataservice_client import AsyncDataServiceClient
from src.services.execution_service import ExecutionService

ReviewAction = Literal["accept", "reject", "undo"]

_REVIEW_STATE_SCHEMA = "wenjin.change_set.review_state.v1"
_STATE_KEYS = ("accepted_unit_ids", "rejected_unit_ids", "undone_unit_ids")


class ChangeSetReviewNotFoundError(LookupError):
    """Raised when the execution or its ChangeSet is not visible to the actor."""


class ChangeSetReviewPersistenceError(RuntimeError):
    """Raised when a ChangeSet review-state update is not durably persisted."""


class ChangeSetReviewService:
    """Manage per-user review decisions for a persisted execution ChangeSet."""

    def __init__(
        self,
        *,
        execution_service: ExecutionService,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self.execution = execution_service
        self._dataservice = dataservice

    async def get_change_set(
        self,
        execution_id: str,
        *,
        actor_user_id: str,
    ) -> dict[str, Any]:
        execution = await self._load_visible_execution(execution_id, actor_user_id=actor_user_id)
        result_payload = _execution_result_payload(execution)
        change_set = _load_change_set(result_payload, execution_id)
        review_state = _normalize_review_state(result_payload.get("change_set_review_state"))
        return _response(change_set, review_state)

    async def accept_units(
        self,
        execution_id: str,
        *,
        unit_ids: list[str],
        actor_user_id: str,
    ) -> dict[str, Any]:
        return await self._mutate(
            execution_id,
            actor_user_id=actor_user_id,
            unit_ids=unit_ids,
            action="accept",
        )

    async def reject_units(
        self,
        execution_id: str,
        *,
        unit_ids: list[str],
        actor_user_id: str,
    ) -> dict[str, Any]:
        return await self._mutate(
            execution_id,
            actor_user_id=actor_user_id,
            unit_ids=unit_ids,
            action="reject",
        )

    async def undo_units(
        self,
        execution_id: str,
        *,
        unit_ids: list[str],
        actor_user_id: str,
    ) -> dict[str, Any]:
        return await self._mutate(
            execution_id,
            actor_user_id=actor_user_id,
            unit_ids=unit_ids,
            action="undo",
        )

    async def _mutate(
        self,
        execution_id: str,
        *,
        actor_user_id: str,
        unit_ids: list[str],
        action: ReviewAction,
    ) -> dict[str, Any]:
        selected_ids = _normalize_unit_ids(unit_ids)
        if not selected_ids:
            raise ValueError("unit_ids must contain at least one unit id")

        execution = await self._load_visible_execution(execution_id, actor_user_id=actor_user_id)
        result_payload = _execution_result_payload(execution)
        change_set = _load_change_set(result_payload, execution_id)
        units_by_id = {unit.id: unit for unit in change_set.units}
        missing = [unit_id for unit_id in selected_ids if unit_id not in units_by_id]
        if missing:
            raise ValueError("unit_ids contains unknown unit id(s): " + ", ".join(missing))
        review_state = _normalize_review_state(result_payload.get("change_set_review_state"))
        next_state = _apply_review_action(
            review_state,
            selected_ids=selected_ids,
            action=action,
            change_set=change_set,
        )
        if _same_review_decisions(review_state, next_state):
            return _response(change_set, review_state)
        persisted = await self._persist_review_state(
            execution_id,
            actor_user_id=actor_user_id,
            next_state=next_state,
        )
        persisted_payload = _execution_result_payload(persisted)
        if persisted_payload is None:
            raise ChangeSetReviewPersistenceError("change_set_review_state persistence failed")
        persisted_state = _normalize_review_state(persisted_payload.get("change_set_review_state"))
        if persisted_state != next_state:
            raise ChangeSetReviewPersistenceError("change_set_review_state persistence failed")
        return _response(change_set, next_state)

    async def _persist_review_state(
        self,
        execution_id: str,
        *,
        actor_user_id: str,
        next_state: dict[str, Any],
    ) -> Any:
        del actor_user_id
        patch_execution_result = _static_callable_attr(self.execution, "patch_execution_result")
        if not callable(patch_execution_result):
            raise ChangeSetReviewPersistenceError(
                "change_set_review_state requires locked result patch support"
            )
        return await patch_execution_result(
            execution_id,
            result_patch={"change_set_review_state": next_state},
            commit=True,
        )

    async def _load_visible_execution(self, execution_id: str, *, actor_user_id: str) -> Any:
        execution = await self.execution.get_by_id(execution_id)
        if execution is None:
            raise ChangeSetReviewNotFoundError(f"execution {execution_id} not found")
        if str(getattr(execution, "user_id", "")) != str(actor_user_id):
            raise ChangeSetReviewNotFoundError(f"execution {execution_id} not found")
        await self._ensure_active_workspace_membership(
            execution,
            actor_user_id=actor_user_id,
        )
        return execution

    async def _ensure_active_workspace_membership(
        self,
        execution: Any,
        *,
        actor_user_id: str,
    ) -> None:
        if self._dataservice is None:
            return
        workspace_id = str(getattr(execution, "workspace_id", "") or "")
        if not workspace_id:
            return
        checker = getattr(self._dataservice, "workspace_has_active_membership", None)
        if not callable(checker):
            return
        result = checker(workspace_id=workspace_id, user_id=str(actor_user_id))
        if inspect.isawaitable(result):
            result = await result
        if result is False:
            raise ChangeSetReviewNotFoundError(f"execution {getattr(execution, 'id', '')} not found")


def _load_change_set(result_payload: dict[str, Any], execution_id: str) -> ChangeSet:
    raw = result_payload.get("change_set")
    if not isinstance(raw, dict):
        raise ChangeSetReviewNotFoundError(f"execution {execution_id} has no change_set")
    return ChangeSet.model_validate(raw)


def _static_callable_attr(value: Any, attr_name: str) -> Any | None:
    try:
        inspect.getattr_static(value, attr_name)
    except AttributeError:
        return None
    attr = getattr(value, attr_name, None)
    return attr if callable(attr) else None


def _response(change_set: ChangeSet, review_state: dict[str, Any]) -> dict[str, Any]:
    unit_states = [
        {
            "unit_id": unit.id,
            "default_apply_state": unit.default_apply_state,
            "state": _effective_unit_state(unit.id, unit.default_apply_state, review_state),
        }
        for unit in change_set.units
    ]
    return {
        "change_set": change_set.model_dump(mode="json"),
        "review_state": review_state,
        "unit_states": unit_states,
    }


def _effective_unit_state(
    unit_id: str,
    default_state: str,
    review_state: dict[str, Any],
) -> str:
    if unit_id in set(review_state["undone_unit_ids"]):
        return "undone"
    if unit_id in set(review_state["rejected_unit_ids"]):
        return "rejected"
    if unit_id in set(review_state["accepted_unit_ids"]):
        return "accepted"
    return default_state


def _apply_review_action(
    review_state: dict[str, Any],
    *,
    selected_ids: list[str],
    action: ReviewAction,
    change_set: ChangeSet,
) -> dict[str, Any]:
    accepted = set(review_state["accepted_unit_ids"])
    rejected = set(review_state["rejected_unit_ids"])
    undone = set(review_state["undone_unit_ids"])

    if action == "accept":
        accepted.update(selected_ids)
        rejected.difference_update(selected_ids)
        undone.difference_update(selected_ids)
    elif action == "reject":
        rejected.update(selected_ids)
        accepted.difference_update(selected_ids)
        undone.difference_update(selected_ids)
    elif action == "undo":
        undone.update(selected_ids)
        accepted.difference_update(selected_ids)
        rejected.difference_update(selected_ids)

    ordered = [unit.id for unit in change_set.units]
    return {
        "schema_version": _REVIEW_STATE_SCHEMA,
        "accepted_unit_ids": _ordered_ids(accepted, ordered),
        "rejected_unit_ids": _ordered_ids(rejected, ordered),
        "undone_unit_ids": _ordered_ids(undone, ordered),
        "updated_at": datetime.now(UTC).isoformat(),
    }


def _normalize_review_state(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    return {
        "schema_version": _REVIEW_STATE_SCHEMA,
        "accepted_unit_ids": _normalize_unit_ids(raw.get("accepted_unit_ids") or []),
        "rejected_unit_ids": _normalize_unit_ids(raw.get("rejected_unit_ids") or []),
        "undone_unit_ids": _normalize_unit_ids(raw.get("undone_unit_ids") or []),
        "updated_at": str(raw.get("updated_at") or ""),
    }


def _normalize_unit_ids(values: Any) -> list[str]:
    if not isinstance(values, list | tuple | set | frozenset):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        unit_id = str(value or "").strip()
        if not unit_id or unit_id in seen:
            continue
        result.append(unit_id)
        seen.add(unit_id)
    return result


def _ordered_ids(values: set[str], ordered: list[str]) -> list[str]:
    return [unit_id for unit_id in ordered if unit_id in values]


def _same_review_decisions(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return all(list(left.get(key) or []) == list(right.get(key) or []) for key in _STATE_KEYS)


def _execution_result_payload(execution: Any) -> dict[str, Any]:
    result = getattr(execution, "result", None)
    if isinstance(result, dict):
        return result
    result_json = getattr(execution, "result_json", None)
    if isinstance(result_json, dict):
        return result_json
    return {}
