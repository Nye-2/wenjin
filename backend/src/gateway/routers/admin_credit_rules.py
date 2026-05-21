"""Admin endpoints for credit grant rules."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Response

from src.database import User, get_db_session
from src.dataservice.credit_api import CreditGrantRuleType
from src.gateway.auth_dependencies import get_current_admin
from src.services.credit_grant_rule_service import CreditGrantRuleService

router = APIRouter(prefix="/admin/credit-rules", tags=["admin", "credits"])


async def _service():
    async with get_db_session() as db:
        yield CreditGrantRuleService(db)


def _to_dict(rule) -> dict[str, Any]:
    return {
        "id": rule.id, "name": rule.name, "rule_type": rule.rule_type.value,
        "enabled": rule.enabled, "amount": rule.amount, "description": rule.description,
        "config": rule.config, "last_triggered_at": rule.last_triggered_at,
        "created_at": rule.created_at, "updated_at": rule.updated_at,
    }


@router.get("")
async def list_rules(
    service: CreditGrantRuleService = Depends(_service),
    _admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    rules = await service.list_all()
    return {"items": [_to_dict(r) for r in rules], "total": len(rules)}


@router.post("")
async def create_rule(
    payload: dict = Body(...),
    service: CreditGrantRuleService = Depends(_service),
    admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    try:
        rule = await service.create(
            name=payload["name"],
            rule_type=CreditGrantRuleType(payload["rule_type"]),
            amount=int(payload["amount"]),
            config=payload.get("config", {}),
            description=payload.get("description"),
            admin_id=admin.id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return _to_dict(rule)


@router.put("/{rule_id}")
async def update_rule(
    rule_id: str,
    payload: dict = Body(...),
    service: CreditGrantRuleService = Depends(_service),
    admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    try:
        rule = await service.update(
            rule_id=rule_id,
            name=payload["name"],
            amount=int(payload["amount"]),
            config=payload.get("config", {}),
            description=payload.get("description"),
            admin_id=admin.id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return _to_dict(rule)


@router.post("/{rule_id}/toggle")
async def toggle_rule(
    rule_id: str,
    service: CreditGrantRuleService = Depends(_service),
    admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    try:
        rule = await service.toggle(rule_id, admin_id=admin.id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return _to_dict(rule)


@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: str,
    service: CreditGrantRuleService = Depends(_service),
    admin: User = Depends(get_current_admin),
) -> Response:
    try:
        await service.delete(rule_id, admin_id=admin.id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return Response(status_code=204)
