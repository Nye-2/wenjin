"""LaTeX adapter command/query service."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.latex.repository import LatexRepository

_UNSET = object()

_BACKEND_ROOT = Path(__file__).resolve().parents[4]
_LATEX_TEMPLATE_SEED_ROOT = _BACKEND_ROOT / "seed" / "latex_templates"
_LATEX_TEMPLATE_REGISTRY_PATH = _LATEX_TEMPLATE_SEED_ROOT / "registry.yaml"
_LATEX_TEMPLATE_ASSET_ROOT = _LATEX_TEMPLATE_SEED_ROOT / "assets"
_TEMPLATE_REGISTRY_FIELDS = {
    "id",
    "label",
    "main_file",
    "category",
    "description",
    "description_en",
    "tags",
    "author",
    "featured",
    "template_path",
    "metadata_json",
}


def _load_template_registry() -> list[dict[str, Any]]:
    registry_path = Path(_LATEX_TEMPLATE_REGISTRY_PATH)
    if not registry_path.is_file():
        raise FileNotFoundError(f"LaTeX template registry missing: {registry_path}")
    raw = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    if raw.get("schema_version") != "latex_template_registry.v1":
        raise ValueError("LaTeX template registry must use schema_version latex_template_registry.v1")
    templates = raw.get("templates")
    if not isinstance(templates, list) or not templates:
        raise ValueError("LaTeX template registry must define templates")

    payloads: list[dict[str, Any]] = []
    for item in templates:
        if not isinstance(item, dict):
            raise ValueError("LaTeX template registry entries must be objects")
        payload = {key: deepcopy(item[key]) for key in _TEMPLATE_REGISTRY_FIELDS if key in item}
        template_id = str(payload.get("id") or "").strip()
        if not template_id:
            raise ValueError("LaTeX template registry entry missing id")
        payload["id"] = template_id
        payload.setdefault("main_file", "main.tex")
        payload.setdefault("category", "academic")
        payload.setdefault("tags", [])
        payload.setdefault("featured", False)
        payload.setdefault("metadata_json", {})
        _validate_template_asset(payload)
        payloads.append(payload)
    return payloads


def _validate_template_asset(payload: dict[str, Any]) -> None:
    template_id = str(payload["id"])
    template_path = str(payload.get("template_path") or template_id).strip()
    if not template_path:
        raise ValueError(f"LaTeX template {template_id} missing template_path")
    asset_root = Path(_LATEX_TEMPLATE_ASSET_ROOT).resolve()
    raw_path = Path(template_path)
    candidate = raw_path if raw_path.is_absolute() else asset_root / raw_path
    candidate = candidate.resolve()
    if not _is_relative_to(candidate, asset_root):
        raise ValueError(f"LaTeX template path escapes asset root: {template_id}")
    if not candidate.is_dir():
        raise FileNotFoundError(f"LaTeX template asset directory missing: {template_id}")
    metadata = payload.get("metadata_json")
    if not isinstance(metadata, dict):
        raise ValueError(f"LaTeX template metadata_json must be an object: {template_id}")
    visual_profile = metadata.get("visual_profile")
    if isinstance(visual_profile, dict) and str(visual_profile.get("id") or "").strip():
        expected_profile_id = str(visual_profile["id"]).strip()
        profile_path = candidate / "visual-profile.yaml"
        if not profile_path.is_file():
            raise FileNotFoundError(f"LaTeX template visual profile missing: {template_id}")
        profile_payload = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
        actual_profile_id = str(profile_payload.get("id") or "").strip()
        if actual_profile_id != expected_profile_id:
            raise ValueError(
                f"LaTeX template {template_id} visual profile id mismatch: "
                f"expected {expected_profile_id}, got {actual_profile_id or '<empty>'}"
            )


def _is_relative_to(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


class DataServiceLatexService:
    """DataService-owned LaTeX adapter persistence operations."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = LatexRepository(session)

    async def list_projects_by_user(
        self,
        user_id: str,
        *,
        include_trashed: bool = False,
    ) -> list[Any]:
        return await self.repository.list_projects_by_user(
            user_id,
            include_trashed=include_trashed,
        )

    async def get_project(self, project_id: str) -> Any | None:
        return await self.repository.get_project(project_id)

    async def get_owned_project(self, *, project_id: str, user_id: str) -> Any | None:
        return await self.repository.get_owned_project(project_id=project_id, user_id=user_id)

    async def get_workspace_primary_project(
        self,
        *,
        workspace_id: str,
        owner_user_id: str,
        template: str | None = None,
    ) -> Any | None:
        return await self.repository.get_workspace_primary_project(
            workspace_id=workspace_id,
            owner_user_id=owner_user_id,
            template=template,
        )

    async def create_project(
        self,
        *,
        user_id: str,
        name: str,
        template_id: str | None = None,
    ) -> Any:
        project = self.repository.create_project(
            {
                "user_id": user_id,
                "name": name,
                "template_id": template_id,
                "main_file": "main.tex",
                "tags": [],
                "archived": False,
                "trashed": False,
                "file_order": {},
            }
        )
        await self._finish(project)
        return project

    async def update_project(self, project: Any, **kwargs: Any) -> Any:
        if "name" in kwargs and kwargs["name"] is not None:
            next_name = str(kwargs["name"]).strip()
            if next_name:
                project.name = next_name
        if "template_id" in kwargs:
            project.template_id = kwargs["template_id"]
        if "main_file" in kwargs and kwargs["main_file"] is not None:
            next_main = str(kwargs["main_file"]).strip()
            if next_main:
                project.main_file = next_main
        if "tags" in kwargs and kwargs["tags"] is not None:
            project.tags = list(kwargs["tags"])
        if "archived" in kwargs and kwargs["archived"] is not None:
            project.archived = bool(kwargs["archived"])
        if "trashed" in kwargs and kwargs["trashed"] is not None:
            next_trashed = bool(kwargs["trashed"])
            project.trashed = next_trashed
            project.trashed_at = datetime.now(tz=UTC) if next_trashed else None
        if "llm_config" in kwargs:
            project.llm_config = deepcopy(kwargs["llm_config"]) if kwargs["llm_config"] is not None else None
            llm_config = kwargs["llm_config"]
            if (
                isinstance(llm_config, dict)
                and llm_config.get("bridge") == "workspace_latex_project"
                and llm_config.get("workspace_id")
            ):
                project.workspace_id = str(llm_config["workspace_id"])
                project.surface_role = "primary_manuscript"
        if "file_order" in kwargs and kwargs["file_order"] is not None:
            project.file_order = dict(kwargs["file_order"])
        project.updated_at = datetime.now(tz=UTC)
        await self._finish(project)
        return project

    async def touch_project(
        self,
        project: Any,
        *,
        file_order: Any = _UNSET,
        main_file: Any = _UNSET,
        llm_config: Any = _UNSET,
    ) -> Any:
        updates: dict[str, Any] = {}
        if file_order is not _UNSET:
            updates["file_order"] = file_order
        if main_file is not _UNSET:
            updates["main_file"] = main_file
        if llm_config is not _UNSET:
            updates["llm_config"] = llm_config
        return await self.update_project(project, **updates)

    async def attach_workspace_project(
        self,
        project: Any,
        *,
        workspace_id: str,
    ) -> Any:
        project.workspace_id = workspace_id
        project.surface_role = "primary_manuscript"
        await self._finish(project)
        return project

    async def soft_delete_project(self, project: Any) -> Any:
        project.trashed = True
        project.trashed_at = datetime.now(tz=UTC)
        await self._finish(project)
        return project

    async def delete_project(self, project: Any) -> None:
        await self.repository.delete_project(project)
        await self._finish()

    async def get_template(self, template_id: str) -> Any | None:
        template = await self.repository.get_template(template_id)
        if template is not None:
            return template
        await self.ensure_default_templates()
        return await self.repository.get_template(template_id)

    async def ensure_default_templates(self) -> None:
        for payload in _load_template_registry():
            await self._upsert_template(payload)
        await self._finish()

    async def _upsert_template(self, payload: dict[str, Any]) -> Any:
        upsert = getattr(self.repository, "upsert_template", None)
        if callable(upsert):
            return await upsert(dict(payload))
        existing = await self.repository.get_template(str(payload["id"]))
        if existing is None:
            return self.repository.create_template(dict(payload))
        for key, value in payload.items():
            if key != "id":
                setattr(existing, key, value)
        return existing

    async def list_templates(self) -> list[Any]:
        await self.ensure_default_templates()
        return await self.repository.list_templates()

    async def _finish(self, record: Any | None = None) -> None:
        if self.autocommit:
            await self.session.commit()
            if record is not None:
                await self.session.refresh(record)
            return
        await self.session.flush()
        if record is not None:
            await self.session.refresh(record)
