"""Admin skill management endpoints."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status

from src.database import User, get_db_session
from src.gateway.auth_dependencies import get_current_admin
from src.services.admin_skill_service import AdminSkillService

router = APIRouter(prefix="/admin/skills", tags=["admin", "skills"])

SKILL_SEED_DIR = Path(__file__).resolve().parent.parent.parent.parent / "seed" / "skills"


async def _service(request: Request) -> AdminSkillService:
    async with get_db_session() as db:
        yield AdminSkillService(db=db)


def _to_dict(skill) -> dict[str, Any]:
    return {
        "id": skill.id,
        "enabled": skill.enabled,
        "display_name": skill.display_name,
        "description": skill.description,
        "subagent_type": skill.subagent_type,
    }


@router.get("")
async def list_skills(
    service: AdminSkillService = Depends(_service),
    _admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    items = await service.list_all()
    return {"items": [_to_dict(s) for s in items], "total": len(items)}


@router.get("/export")
async def export_zip(
    service: AdminSkillService = Depends(_service),
    _admin: User = Depends(get_current_admin),
) -> Response:
    items = await service.list_all()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for skill in items:
            path = f"skills/{skill.id}.yaml"
            zf.writestr(path, service.to_yaml_text(skill))
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="skills.zip"'},
    )


@router.get("/{skill_id}")
async def get_skill(
    skill_id: str,
    service: AdminSkillService = Depends(_service),
    _admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    skill = await service.get(skill_id)
    if skill is None:
        raise HTTPException(404, "skill not found")
    return {
        "yaml": service.to_yaml_text(skill),
        "updated_at": getattr(skill, "updated_at", None),
    }


@router.post("/validate")
async def validate_skill(
    payload: dict = Body(...),
    service: AdminSkillService = Depends(_service),
    _admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    errors = await service.validate(payload.get("yaml", ""))
    return {"valid": not errors, "errors": errors}


@router.post("")
async def create_skill(
    payload: dict = Body(...),
    service: AdminSkillService = Depends(_service),
    admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    try:
        skill = await service.create(yaml_text=payload["yaml"], admin_id=admin.id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return _to_dict(skill)


@router.put("/{skill_id}")
async def update_skill(
    skill_id: str,
    payload: dict = Body(...),
    service: AdminSkillService = Depends(_service),
    admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    try:
        skill = await service.update(
            skill_id=skill_id,
            yaml_text=payload["yaml"],
            admin_id=admin.id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return _to_dict(skill)


@router.delete("/{skill_id}")
async def delete_skill(
    skill_id: str,
    service: AdminSkillService = Depends(_service),
    admin: User = Depends(get_current_admin),
) -> Response:
    try:
        await service.delete(skill_id, admin_id=admin.id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{skill_id}/toggle")
async def toggle_skill(
    skill_id: str,
    service: AdminSkillService = Depends(_service),
    admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    try:
        skill = await service.toggle(skill_id, admin_id=admin.id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return _to_dict(skill)


@router.post("/import-from-seed")
async def import_from_seed(
    service: AdminSkillService = Depends(_service),
    admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    from src.database.models.capability_skill import CapabilitySkill

    loaded: list[dict[str, str]] = []
    async with get_db_session() as db:
        if not SKILL_SEED_DIR.exists():
            return {"loaded": []}
        for path in sorted(SKILL_SEED_DIR.glob("*.yaml")):
            with open(path) as f:
                data = yaml.safe_load(f)
            existing = await db.get(CapabilitySkill, data["id"])
            if existing:
                for k, v in data.items():
                    if k != "id":
                        setattr(existing, k, v)
                loaded.append({"id": data["id"]})
            else:
                skill = CapabilitySkill(**data)
                db.add(skill)
                loaded.append({"id": data["id"]})
        await db.commit()
    return {"loaded": loaded}
