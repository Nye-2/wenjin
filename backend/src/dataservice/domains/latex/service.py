"""LaTeX adapter command/query service."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.latex.repository import LatexRepository

_UNSET = object()

_DEFAULT_TEMPLATES: tuple[dict[str, object], ...] = (
    {
        "id": "acl",
        "label": "ACL",
        "main_file": "main.tex",
        "category": "academic",
        "description": "ACL conference template",
        "description_en": "ACL conference template",
        "tags": ["ACL", "NLP"],
        "author": "WenjinPrism",
        "featured": True,
        "template_path": "acl",
    },
    {
        "id": "cvpr",
        "label": "CVPR",
        "main_file": "main.tex",
        "category": "academic",
        "description": "CVPR conference template",
        "description_en": "CVPR conference template",
        "tags": ["CVPR", "Computer Vision"],
        "author": "WenjinPrism",
        "featured": True,
        "template_path": "cvpr",
    },
    {
        "id": "neurips",
        "label": "NeurIPS",
        "main_file": "main.tex",
        "category": "academic",
        "description": "NeurIPS conference template",
        "description_en": "NeurIPS conference template",
        "tags": ["NeurIPS", "Machine Learning"],
        "author": "WenjinPrism",
        "featured": True,
        "template_path": "neurips",
    },
    {
        "id": "icml",
        "label": "ICML",
        "main_file": "main.tex",
        "category": "academic",
        "description": "ICML conference template",
        "description_en": "ICML conference template",
        "tags": ["ICML", "Machine Learning"],
        "author": "WenjinPrism",
        "featured": True,
        "template_path": "icml",
    },
)


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
        return await self.repository.get_template(template_id)

    async def ensure_default_templates(self) -> None:
        if await self.repository.has_templates():
            return
        for payload in _DEFAULT_TEMPLATES:
            self.repository.create_template(dict(payload))
        await self._finish()

    async def list_templates(self) -> list[Any]:
        await self.ensure_default_templates()
        return await self.repository.list_templates()

    async def record_compile_history(
        self,
        *,
        project_id: str,
        engine: str,
        main_file: str,
        status: int,
        log: str | None,
        pdf_path: str | None,
    ) -> Any:
        history = self.repository.create_compile_history(
            {
                "project_id": project_id,
                "engine": engine,
                "main_file": main_file,
                "status": status,
                "log": log,
                "pdf_path": pdf_path,
            }
        )
        await self._finish(history)
        return history

    async def get_compile_history(self, history_id: str) -> Any | None:
        return await self.repository.get_compile_history(history_id)

    async def list_compile_history(self, project_id: str) -> list[Any]:
        return await self.repository.list_compile_history(project_id)

    async def delete_compile_histories(self, histories: list[Any]) -> None:
        for history in histories:
            await self.repository.delete_compile_history(history)
        await self._finish()

    async def _finish(self, record: Any | None = None) -> None:
        if self.autocommit:
            await self.session.commit()
            if record is not None:
                await self.session.refresh(record)
            return
        await self.session.flush()
