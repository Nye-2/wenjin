"""Metadata and filesystem service for LaTeX projects."""

from __future__ import annotations

import json
import logging
import mimetypes
import shutil
from collections.abc import Iterable
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.latex_project import LatexProject
from src.database.models.latex_template import LatexTemplate

from .paths import (
    get_latex_template_dir,
    is_reserved_project_path,
    project_root,
    resolve_project_relative,
)

logger = logging.getLogger(__name__)

_DEFAULT_MAIN_TEX = (
    "\\documentclass{article}\n"
    "\\begin{document}\n"
    "Hello from Wenjin LaTeX.\n"
    "\\end{document}\n"
)


class LatexTemplateError(ValueError):
    """Base error for invalid LaTeX template selection."""


class LatexTemplateNotFoundError(LatexTemplateError):
    """Raised when selected template id does not exist."""


class LatexTemplateUnavailableError(LatexTemplateError):
    """Raised when selected template assets are unavailable."""


class LatexProjectService:
    """Manage LaTeX project records and persisted files."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_user(
        self,
        user_id: str,
        *,
        include_trashed: bool = False,
    ) -> list[LatexProject]:
        stmt = select(LatexProject).where(LatexProject.user_id == user_id)
        if not include_trashed:
            stmt = stmt.where(LatexProject.trashed.is_(False))
        stmt = stmt.order_by(LatexProject.updated_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_owned(self, project_id: str, user_id: str) -> LatexProject | None:
        stmt = select(LatexProject).where(
            LatexProject.id == project_id,
            LatexProject.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: str,
        name: str,
        template_id: str | None = None,
    ) -> LatexProject:
        project = LatexProject(
            user_id=user_id,
            name=name,
            template_id=template_id,
            main_file="main.tex",
            tags=[],
            archived=False,
            trashed=False,
            file_order={},
        )
        self.db.add(project)
        await self.db.commit()
        await self.db.refresh(project)

        root = project_root(project.id)
        root.mkdir(parents=True, exist_ok=True)

        template_applied = await self._copy_template_if_available(template_id, root)
        if not template_applied:
            self._write_default_files(root)
        detected_main = self._detect_main_file(
            root,
            preferred=project.main_file,
        )
        if detected_main is not None and detected_main != project.main_file:
            project.main_file = detected_main
            await self.db.commit()
            await self.db.refresh(project)

        await self.sync_project_meta(project)
        return project

    async def update(self, project: LatexProject, **kwargs: Any) -> LatexProject:
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
            project.llm_config = kwargs["llm_config"]
        if "file_order" in kwargs and kwargs["file_order"] is not None:
            project.file_order = dict(kwargs["file_order"])

        await self.db.commit()
        await self.db.refresh(project)
        await self.sync_project_meta(project)
        return project

    async def soft_delete(self, project: LatexProject) -> None:
        project.trashed = True
        project.trashed_at = datetime.now(tz=UTC)
        await self.db.commit()
        await self.db.refresh(project)
        await self.sync_project_meta(project)

    async def permanent_delete(self, project: LatexProject) -> None:
        root = project_root(project.id)
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        compile_root = root.parent / "_compile_runs" / str(project.id)
        if compile_root.exists():
            shutil.rmtree(compile_root, ignore_errors=True)
        await self.db.delete(project)
        await self.db.commit()

    def build_tree(self, project: LatexProject) -> list[dict[str, str]]:
        root = project_root(project.id)
        if not root.exists():
            return []

        items: list[dict[str, str]] = []
        skip_roots = {".compile", ".git", "__pycache__", "project.json"}
        file_order = dict(project.file_order or {})

        def emit_dir(directory: Path, folder: str) -> None:
            children = [
                child for child in directory.iterdir()
                if child.name not in skip_roots
            ]
            for child in self._sort_children(
                children,
                folder=folder,
                file_order=file_order,
            ):
                rel = f"{folder}/{child.name}" if folder else child.name
                if child.is_dir():
                    items.append({"path": rel, "type": "dir"})
                    emit_dir(child, rel)
                else:
                    items.append({"path": rel, "type": "file"})

        emit_dir(root, "")
        return items

    def read_text_file(self, project: LatexProject, relative_path: str) -> str:
        self._ensure_user_path_allowed(relative_path)
        target = resolve_project_relative(project_root(project.id), relative_path)
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(relative_path)
        return target.read_text(encoding="utf-8")

    async def write_text_file(
        self,
        project: LatexProject,
        relative_path: str,
        content: str,
    ) -> None:
        self._ensure_user_path_allowed(relative_path)
        target = resolve_project_relative(project_root(project.id), relative_path)
        existed = target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

        if not existed:
            project.file_order = self._append_child_to_order(
                dict(project.file_order or {}),
                relative_path,
            )
        project.updated_at = datetime.now(tz=UTC)
        await self.db.commit()
        await self.db.refresh(project)
        await self.sync_project_meta(project)

    def resolve_blob_file(self, project: LatexProject, relative_path: str) -> tuple[Path, str]:
        self._ensure_user_path_allowed(relative_path)
        target = resolve_project_relative(project_root(project.id), relative_path)
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(relative_path)

        media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return target, media_type

    def read_blob(self, project: LatexProject, relative_path: str) -> tuple[bytes, str]:
        target, media_type = self.resolve_blob_file(project, relative_path)
        return target.read_bytes(), media_type

    async def save_upload(
        self,
        project: LatexProject,
        relative_path: str,
        content: bytes,
    ) -> str:
        self._ensure_user_path_allowed(relative_path)
        target = resolve_project_relative(project_root(project.id), relative_path)
        existed = target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

        if not existed:
            project.file_order = self._append_child_to_order(
                dict(project.file_order or {}),
                relative_path,
            )
        project.updated_at = datetime.now(tz=UTC)
        await self.db.commit()
        await self.db.refresh(project)
        await self.sync_project_meta(project)
        return target.relative_to(project_root(project.id)).as_posix()

    async def save_uploads(
        self,
        project: LatexProject,
        *,
        files: list[tuple[str, bytes]],
        folders: list[str] | None = None,
    ) -> tuple[list[str], list[str]]:
        """Persist uploaded files/folders in one transaction for large batches."""
        root = project_root(project.id)
        next_order = dict(project.file_order or {})
        saved_files: list[str] = []
        created_folders: list[str] = []
        touched = False

        for folder_path in folders or []:
            self._ensure_user_path_allowed(folder_path)
            target = resolve_project_relative(root, folder_path)
            existed = target.exists()
            target.mkdir(parents=True, exist_ok=True)
            normalized = target.relative_to(root).as_posix()
            if not existed:
                next_order = self._append_child_to_order(next_order, normalized)
                created_folders.append(normalized)
                touched = True

        for relative_path, content in files:
            self._ensure_user_path_allowed(relative_path)
            target = resolve_project_relative(root, relative_path)
            existed = target.exists()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            normalized = target.relative_to(root).as_posix()
            saved_files.append(normalized)
            if not existed:
                next_order = self._append_child_to_order(next_order, normalized)
            touched = True

        if touched:
            uploaded_main_candidate = self._pick_preferred_tex_path(saved_files)
            try:
                current_main_path = resolve_project_relative(root, project.main_file)
            except ValueError:
                current_main_path = root / project.main_file

            current_main_exists = current_main_path.exists() and current_main_path.is_file()
            if not current_main_exists:
                detected_main = self._detect_main_file(root, preferred=uploaded_main_candidate)
                if detected_main:
                    project.main_file = detected_main
            elif project.main_file == "main.tex":
                uploaded_tex_paths = [
                    path for path in saved_files if path.lower().endswith(".tex")
                ]
                uploaded_has_root_main = any(
                    path.lower() == "main.tex" for path in uploaded_tex_paths
                )
                if uploaded_tex_paths and not uploaded_has_root_main:
                    try:
                        current_main_content = current_main_path.read_text(encoding="utf-8")
                    except UnicodeDecodeError:
                        current_main_content = ""
                    if current_main_content == _DEFAULT_MAIN_TEX:
                        detected_main = self._detect_main_file(
                            root,
                            preferred=uploaded_main_candidate,
                        )
                        if detected_main:
                            project.main_file = detected_main

            project.file_order = next_order
            project.updated_at = datetime.now(tz=UTC)
            await self.db.commit()
            await self.db.refresh(project)
            await self.sync_project_meta(project)

        return saved_files, created_folders

    async def update_file_order(
        self,
        project: LatexProject,
        folder: str,
        order: list[str],
    ) -> None:
        next_map = dict(project.file_order or {})
        next_map[str(folder or "")] = [str(item) for item in order]
        project.file_order = next_map

        await self.db.commit()
        await self.db.refresh(project)
        await self.sync_project_meta(project)

    async def update_llm_config(
        self,
        project: LatexProject,
        llm_config: dict[str, Any] | None,
    ) -> LatexProject:
        project.llm_config = deepcopy(llm_config) if llm_config is not None else None
        project.updated_at = datetime.now(tz=UTC)
        await self.db.commit()
        await self.db.refresh(project)
        await self.sync_project_meta(project)
        return project

    async def create_folder(self, project: LatexProject, relative_path: str) -> str:
        self._ensure_user_path_allowed(relative_path)
        target = resolve_project_relative(project_root(project.id), relative_path)
        existed = target.exists()
        target.mkdir(parents=True, exist_ok=True)

        if not existed:
            project.file_order = self._append_child_to_order(
                dict(project.file_order or {}),
                relative_path,
            )
        project.updated_at = datetime.now(tz=UTC)
        await self.db.commit()
        await self.db.refresh(project)
        await self.sync_project_meta(project)
        return target.relative_to(project_root(project.id)).as_posix()

    async def rename_path(
        self,
        project: LatexProject,
        from_path: str,
        to_path: str,
    ) -> str:
        self._ensure_user_path_allowed(from_path)
        self._ensure_user_path_allowed(to_path)
        root = project_root(project.id)
        source = resolve_project_relative(root, from_path)
        destination = resolve_project_relative(root, to_path)
        if not source.exists():
            raise FileNotFoundError(from_path)
        if destination.exists():
            raise FileExistsError(to_path)

        destination.parent.mkdir(parents=True, exist_ok=True)
        was_dir = source.is_dir()
        source.rename(destination)

        project.file_order = self._rename_in_order_map(
            dict(project.file_order or {}),
            old_path=from_path,
            new_path=to_path,
            is_dir=was_dir,
        )
        project.main_file = self._remap_main_file(
            project.main_file,
            old_path=from_path,
            new_path=to_path,
        )
        project.updated_at = datetime.now(tz=UTC)
        await self.db.commit()
        await self.db.refresh(project)
        await self.sync_project_meta(project)
        return destination.relative_to(root).as_posix()

    async def delete_path(self, project: LatexProject, relative_path: str) -> None:
        self._ensure_user_path_allowed(relative_path)
        root = project_root(project.id)
        target = resolve_project_relative(root, relative_path)
        if not target.exists():
            raise FileNotFoundError(relative_path)

        is_dir = target.is_dir()
        if is_dir:
            shutil.rmtree(target)
        else:
            target.unlink()

        project.file_order = self._delete_from_order_map(
            dict(project.file_order or {}),
            relative_path=relative_path,
            is_dir=is_dir,
        )
        if self._path_affects_main_file(project.main_file, relative_path):
            project.main_file = self._detect_main_file(root, preferred=None) or "main.tex"
        project.updated_at = datetime.now(tz=UTC)
        await self.db.commit()
        await self.db.refresh(project)
        await self.sync_project_meta(project)

    async def sync_project_meta(self, project: LatexProject) -> None:
        root = project_root(project.id)
        root.mkdir(parents=True, exist_ok=True)
        payload = {
            "id": project.id,
            "name": project.name,
            "templateId": project.template_id,
            "mainFile": project.main_file,
            "tags": project.tags,
            "archived": project.archived,
            "trashed": project.trashed,
            "trashedAt": project.trashed_at.isoformat() if project.trashed_at else None,
            "fileOrder": project.file_order,
            "createdAt": project.created_at.isoformat(),
            "updatedAt": project.updated_at.isoformat(),
        }
        (root / "project.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def _copy_template_if_available(
        self,
        template_id: str | None,
        target_root: Path,
    ) -> bool:
        if not template_id:
            return False

        template = await self.db.get(LatexTemplate, template_id)
        if template is None:
            raise LatexTemplateNotFoundError(f"Template not found: {template_id}")

        template_dir = get_latex_template_dir()
        candidate: Path | None = None
        if template.template_path:
            raw = Path(template.template_path)
            candidate = raw if raw.is_absolute() else (template_dir / raw)
        if candidate is None or not candidate.exists() or not candidate.is_dir():
            logger.warning("Template path not found for template_id=%s", template_id)
            raise LatexTemplateUnavailableError(
                f"Template assets unavailable: {template_id}"
            )

        shutil.copytree(candidate, target_root, dirs_exist_ok=True)

        main_file = target_root / (template.main_file or "main.tex")
        if not main_file.exists():
            detected_main = self._detect_main_file(
                target_root,
                preferred=template.main_file,
            )
            if detected_main is None:
                self._write_default_files(target_root)
        bib_file = target_root / "references.bib"
        if not bib_file.exists():
            bib_file.write_text("", encoding="utf-8")
        return True

    @staticmethod
    def _write_default_files(root: Path) -> None:
        (root / "main.tex").write_text(_DEFAULT_MAIN_TEX, encoding="utf-8")
        (root / "references.bib").write_text("", encoding="utf-8")

    @staticmethod
    def _detect_main_file(root: Path, *, preferred: str | None) -> str | None:
        candidates: list[str] = []
        if preferred:
            candidates.append(preferred)
        candidates.extend(
            [
                "main.tex",
                "template.tex",
                "acl_latex.tex",
                "acl_lualatex.tex",
            ]
        )
        seen: set[str] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            path = root / candidate
            if path.exists() and path.is_file():
                return candidate

        tex_files = sorted(path.relative_to(root).as_posix() for path in root.rglob("*.tex"))
        if tex_files:
            return tex_files[0]
        return None

    @staticmethod
    def _pick_preferred_tex_path(paths: Iterable[str]) -> str | None:
        tex_paths = [path for path in paths if path.lower().endswith(".tex")]
        if not tex_paths:
            return None

        def key(path: str) -> tuple[int, int, int, str]:
            lower = path.lower()
            name = Path(path).name.lower()
            if lower == "main.tex" or name == "main.tex":
                priority = 0
            elif lower == "template.tex" or name == "template.tex":
                priority = 1
            else:
                priority = 2
            depth = path.count("/")
            return priority, depth, len(path), path

        return min(tex_paths, key=key)

    @staticmethod
    def _folder_key(path: str) -> str:
        folder = Path(path).parent.as_posix()
        return "" if folder == "." else folder

    @staticmethod
    def _ensure_user_path_allowed(relative_path: str) -> None:
        if is_reserved_project_path(relative_path):
            raise ValueError("File path is reserved")

    @staticmethod
    def _basename(path: str) -> str:
        return Path(path).name

    @classmethod
    def _append_child_to_order(
        cls,
        file_order: dict[str, list[str]],
        relative_path: str,
    ) -> dict[str, list[str]]:
        folder = cls._folder_key(relative_path)
        name = cls._basename(relative_path)
        next_map = dict(file_order)
        order = list(next_map.get(folder, []))
        if name not in order:
            order.append(name)
        next_map[folder] = order
        return next_map

    @classmethod
    def _rename_in_order_map(
        cls,
        file_order: dict[str, list[str]],
        *,
        old_path: str,
        new_path: str,
        is_dir: bool,
    ) -> dict[str, list[str]]:
        old_folder = cls._folder_key(old_path)
        new_folder = cls._folder_key(new_path)
        old_name = cls._basename(old_path)
        new_name = cls._basename(new_path)
        next_map: dict[str, list[str]] = {}

        for folder, names in file_order.items():
            mapped_folder = folder
            if is_dir:
                if folder == old_path:
                    mapped_folder = new_path
                elif folder.startswith(f"{old_path}/"):
                    mapped_folder = f"{new_path}{folder[len(old_path):]}"

            updated_names: list[str] = []
            for name in names:
                if folder == old_folder and name == old_name:
                    if old_folder == new_folder:
                        updated_names.append(new_name)
                    continue
                updated_names.append(name)

            if updated_names:
                next_map[mapped_folder] = updated_names

        if old_folder == new_folder:
            names = list(next_map.get(new_folder, []))
            if new_name not in names:
                names.append(new_name)
            next_map[new_folder] = names
        else:
            if old_folder in next_map:
                next_map[old_folder] = [name for name in next_map[old_folder] if name != old_name]
                if not next_map[old_folder]:
                    next_map.pop(old_folder)
            names = list(next_map.get(new_folder, []))
            if new_name not in names:
                names.append(new_name)
            next_map[new_folder] = names
        return next_map

    @classmethod
    def _delete_from_order_map(
        cls,
        file_order: dict[str, list[str]],
        *,
        relative_path: str,
        is_dir: bool,
    ) -> dict[str, list[str]]:
        folder = cls._folder_key(relative_path)
        name = cls._basename(relative_path)
        next_map: dict[str, list[str]] = {}
        for current_folder, names in file_order.items():
            if is_dir and (
                current_folder == relative_path or current_folder.startswith(f"{relative_path}/")
            ):
                continue
            filtered = [
                current_name for current_name in names
                if not (current_folder == folder and current_name == name)
            ]
            if filtered:
                next_map[current_folder] = filtered
        return next_map

    @staticmethod
    def _path_affects_main_file(main_file: str, relative_path: str) -> bool:
        return main_file == relative_path or main_file.startswith(f"{relative_path}/")

    @staticmethod
    def _remap_main_file(main_file: str, *, old_path: str, new_path: str) -> str:
        if main_file == old_path:
            return new_path
        if main_file.startswith(f"{old_path}/"):
            return f"{new_path}{main_file[len(old_path):]}"
        return main_file

    @classmethod
    def _sort_children(
        cls,
        children: Iterable[Path],
        *,
        folder: str,
        file_order: dict[str, list[str]],
    ) -> list[Path]:
        ordered_names = file_order.get(folder, [])
        ordered_index = {name: index for index, name in enumerate(ordered_names)}

        def sort_key(child: Path) -> tuple[int, int, int, str]:
            if child.name in ordered_index:
                return (0, ordered_index[child.name], 0, child.name)
            return (1, 0, 0 if child.is_dir() else 1, child.name)

        return sorted(children, key=sort_key)
