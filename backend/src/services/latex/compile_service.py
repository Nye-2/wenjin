"""Compilation service for persisted LaTeX projects."""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import shutil
from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.latex_compile_history import LatexCompileHistory
from src.database.models.latex_project import LatexProject
from src.execution.docker.client import DockerClient, DockerExecutionError

from .engine_config import get_default_latex_engine, is_supported_latex_engine
from .paths import (
    compile_runs_root,
    normalize_relative_path,
    project_root,
    resolve_project_relative,
)

_DEFAULT_LATEX_DOCKER_IMAGE = "wenjin/texlive:2024"
_DEFAULT_COMPILE_TIMEOUT_SECONDS = 300
_MIN_COMPILE_TIMEOUT_SECONDS = 30
_MAX_COMPILE_TIMEOUT_SECONDS = 1800


def get_latex_compile_timeout_seconds() -> int:
    """Resolve LaTeX compile timeout from env with clamped safe bounds."""
    raw = str(os.getenv("WENJIN_LATEX_COMPILE_TIMEOUT_SECONDS", "")).strip()
    if not raw:
        return _DEFAULT_COMPILE_TIMEOUT_SECONDS
    try:
        parsed = int(raw)
    except ValueError:
        return _DEFAULT_COMPILE_TIMEOUT_SECONDS
    return max(_MIN_COMPILE_TIMEOUT_SECONDS, min(_MAX_COMPILE_TIMEOUT_SECONDS, parsed))


class LatexCompileService:
    """Compile a persisted project by mounting its full file tree into Docker."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._docker = DockerClient()

    async def compile_project(
        self,
        project: LatexProject,
        *,
        main_file: str | None = None,
        engine: str | None = None,
    ) -> dict[str, object]:
        compiler = (engine or "").strip().lower() or get_default_latex_engine()
        if not is_supported_latex_engine(compiler):
            raise ValueError(f"Unsupported compiler: {compiler}")

        raw_entry_file = (main_file or project.main_file or "main.tex").strip() or "main.tex"
        entry_file = normalize_relative_path(raw_entry_file)
        source_root = project_root(project.id)
        entry_path = resolve_project_relative(source_root, entry_file)
        if not entry_path.exists() or not entry_path.is_file():
            raise FileNotFoundError(entry_file)

        run_id = uuid4().hex
        run_root = compile_runs_root(project.id) / run_id
        mounted_project_dir = run_root / "project"
        mounted_project_dir.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copytree(
                source_root,
                mounted_project_dir,
                ignore=shutil.ignore_patterns(".compile", ".git", "__pycache__"),
            )
            stdout, stderr, pdf_path = await self._run_compile_in_docker(
                mounted_project_dir,
                entry_file=entry_file,
                compiler=compiler,
            )
            log = "\n".join(part for part in (stdout, stderr) if part).strip() or None
            success = pdf_path.exists()
            history = LatexCompileHistory(
                project_id=project.id,
                engine=compiler,
                main_file=entry_file,
                status=0 if success else 1,
                log=log,
                pdf_path=str(pdf_path) if success else None,
            )
            self.db.add(history)
            await self.db.commit()
            await self.db.refresh(history)

            return {
                "ok": success,
                "status": 0 if success else 1,
                "engine": compiler,
                "main_file": entry_file,
                "pdf_path": str(pdf_path) if success else None,
                "pdf_endpoint": (
                    f"/api/latex/projects/{project.id}/compile/{history.id}/pdf"
                    if success
                    else None
                ),
                "log": log,
                "error": None if success else "No PDF generated.",
                "history_id": history.id,
                "page_count": None,
            }
        except (DockerExecutionError, FileNotFoundError, TimeoutError) as exc:
            history = LatexCompileHistory(
                project_id=project.id,
                engine=compiler,
                main_file=entry_file,
                status=1,
                log=str(exc),
                pdf_path=None,
            )
            self.db.add(history)
            await self.db.commit()
            await self.db.refresh(history)
            return {
                "ok": False,
                "status": 1,
                "engine": compiler,
                "main_file": entry_file,
                "pdf_path": None,
                "pdf_endpoint": None,
                "log": str(exc),
                "error": str(exc),
                "history_id": history.id,
                "page_count": None,
            }

    async def get_history_pdf(
        self,
        *,
        history_id: str,
        project_id: str,
    ) -> Path | None:
        history = await self.db.get(LatexCompileHistory, history_id)
        if history is None or history.project_id != project_id or not history.pdf_path:
            return None
        candidate = Path(history.pdf_path).resolve()
        allowed_roots = [
            project_root(project_id).resolve(),
            compile_runs_root(project_id).resolve(),
        ]
        try:
            if not any(candidate.is_relative_to(root) for root in allowed_roots):
                return None
        except AttributeError:
            from os.path import commonpath

            if not any(
                commonpath([str(candidate), str(root)]) == str(root)
                for root in allowed_roots
            ):
                return None
        if not candidate.exists() or not candidate.is_file():
            return None
        return candidate

    async def get_history_synctex(
        self,
        *,
        history_id: str,
        project_id: str,
    ) -> Path | None:
        history = await self.db.get(LatexCompileHistory, history_id)
        if history is None or history.project_id != project_id or not history.pdf_path:
            return None
        pdf_candidate = Path(history.pdf_path).resolve()
        candidate = pdf_candidate.with_suffix(".synctex.gz")

        allowed_roots = [
            project_root(project_id).resolve(),
            compile_runs_root(project_id).resolve(),
        ]
        try:
            if not any(candidate.is_relative_to(root) for root in allowed_roots):
                return None
        except AttributeError:
            from os.path import commonpath

            if not any(
                commonpath([str(candidate), str(root)]) == str(root)
                for root in allowed_roots
            ):
                return None

        if not candidate.exists() or not candidate.is_file():
            return None
        return candidate

    @staticmethod
    def _parse_synctex_edit_output(output: str) -> tuple[str, int, int] | None:
        input_match = re.search(r"(?mi)^Input:(.+)$", output)
        line_match = re.search(r"(?mi)^Line:(\d+)$", output)
        column_match = re.search(r"(?mi)^Column:(\d+)$", output)
        if not input_match or not line_match:
            return None
        source_input = str(input_match.group(1)).strip()
        line = int(line_match.group(1))
        column = int(column_match.group(1)) if column_match else 1
        return source_input, line, column

    @staticmethod
    def _parse_synctex_view_output(output: str) -> tuple[int, float, float] | None:
        page_match = re.search(r"(?mi)^Page:(\d+)$", output)
        x_match = re.search(r"(?mi)^x:([0-9.+-]+)$", output)
        y_match = re.search(r"(?mi)^y:([0-9.+-]+)$", output)
        if not page_match:
            return None
        page = int(page_match.group(1))
        x = float(x_match.group(1)) if x_match else 0.0
        y = float(y_match.group(1)) if y_match else 0.0
        return page, x, y

    async def _run_synctex(self, args: list[str]) -> str:
        try:
            process = await asyncio.create_subprocess_exec(
                "synctex",
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("synctex binary not found") from exc

        stdout, stderr = await process.communicate()
        output = "\n".join(
            part for part in (stdout.decode("utf-8", errors="ignore"), stderr.decode("utf-8", errors="ignore"))
            if part
        )
        if process.returncode != 0:
            raise RuntimeError(f"synctex command failed: {output.strip() or process.returncode}")
        return output

    @staticmethod
    def _line_column_to_offset(content: str, line: int, column: int) -> int:
        safe_line = max(1, line)
        safe_column = max(1, column)
        offset = 0
        current_line = 1
        while current_line < safe_line and offset < len(content):
            next_newline = content.find("\n", offset)
            if next_newline < 0:
                return len(content)
            offset = next_newline + 1
            current_line += 1
        return min(len(content), offset + safe_column - 1)

    @staticmethod
    def _offset_to_line_column(content: str, offset: int) -> tuple[int, int]:
        safe_offset = max(0, min(offset, len(content)))
        line = 1
        line_start = 0
        for index, char in enumerate(content[:safe_offset]):
            if char == "\n":
                line += 1
                line_start = index + 1
        column = safe_offset - line_start + 1
        return line, max(1, column)

    @staticmethod
    def _resolve_compile_project_root(pdf_path: Path) -> Path:
        cursor = pdf_path.parent
        while cursor != cursor.parent:
            if cursor.name == "project":
                return cursor
            cursor = cursor.parent
        return pdf_path.parent

    @staticmethod
    def _read_pdf_page_size(pdf_path: Path, page: int) -> tuple[float, float] | None:
        try:
            from pypdf import PdfReader  # type: ignore
        except Exception:
            return None
        try:
            reader = PdfReader(str(pdf_path))
            page_obj = reader.pages[max(0, page - 1)]
            width = float(page_obj.mediabox.width)
            height = float(page_obj.mediabox.height)
            if width <= 0 or height <= 0:
                return None
            return width, height
        except Exception:
            return None

    async def map_pdf_point_to_source(
        self,
        *,
        history_id: str,
        project_id: str,
        page: int,
        x: float,
        y: float,
    ) -> dict[str, object] | None:
        history = await self.db.get(LatexCompileHistory, history_id)
        if history is None or history.project_id != project_id or not history.pdf_path:
            return None
        pdf_path = Path(history.pdf_path).resolve()
        synctex_path = await self.get_history_synctex(history_id=history_id, project_id=project_id)
        if synctex_path is None:
            return None

        attempts: list[tuple[float, float]] = [(float(x), float(y))]
        if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
            size = self._read_pdf_page_size(pdf_path, page)
            if size is not None:
                width, height = size
                attempts = [
                    (x * width, y * height),
                    (x * width, (1.0 - y) * height),
                ]

        for candidate_x, candidate_y in attempts:
            try:
                output = await self._run_synctex(
                    ["edit", "-o", f"{int(page)}:{float(candidate_x)}:{float(candidate_y)}:{pdf_path}"]
                )
            except RuntimeError:
                continue
            parsed = self._parse_synctex_edit_output(output)
            if parsed is None:
                continue
            source_input, line, column = parsed
            source_path = Path(source_input)
            compile_project_root = self._resolve_compile_project_root(pdf_path)
            try:
                relative_source_path = source_path.resolve().relative_to(compile_project_root).as_posix()
            except Exception:
                relative_source_path = source_path.name
            return {
                "file_path": relative_source_path,
                "line": line,
                "column": column,
            }
        return None

    async def map_source_line_to_pdf(
        self,
        *,
        history_id: str,
        project_id: str,
        relative_file_path: str,
        line: int,
        column: int = 1,
    ) -> dict[str, object] | None:
        history = await self.db.get(LatexCompileHistory, history_id)
        if history is None or history.project_id != project_id or not history.pdf_path:
            return None
        pdf_path = Path(history.pdf_path).resolve()
        compile_project_root = self._resolve_compile_project_root(pdf_path)
        source_path = (compile_project_root / relative_file_path).resolve()
        if not source_path.exists():
            return None

        output = await self._run_synctex(
            ["view", "-i", f"{max(1, line)}:{max(1, column)}:{source_path}", "-o", str(pdf_path)]
        )
        parsed = self._parse_synctex_view_output(output)
        if parsed is None:
            return None
        page, x, y = parsed
        page_size = self._read_pdf_page_size(pdf_path, page)
        normalized_x: float | None = None
        normalized_y: float | None = None
        if page_size is not None:
            width, height = page_size
            if width > 0 and height > 0:
                normalized_x = max(0.0, min(1.0, x / width))
                normalized_y = max(0.0, min(1.0, y / height))
        return {
            "page": page,
            "x": x,
            "y": y,
            "normalized_x": normalized_x,
            "normalized_y": normalized_y,
        }

    async def _run_compile_in_docker(
        self,
        mounted_project_dir: Path,
        *,
        entry_file: str,
        compiler: str,
    ) -> tuple[str, str, Path]:
        command = self._build_command(entry_file=entry_file, compiler=compiler)
        exit_code, stdout, stderr = await self._docker.run_container(
            image=os.getenv("GUANLAN_TEXLIVE_IMAGE", _DEFAULT_LATEX_DOCKER_IMAGE),
            command=command,
            volumes=self._docker.build_volume_mapping(
                host_path=str(mounted_project_dir.parent),
                container_path="/workspace",
            ),
            working_dir="/workspace/project",
            entrypoint="",
            timeout=get_latex_compile_timeout_seconds(),
        )
        output_pdf = self._resolve_output_pdf(
            mounted_project_dir,
            entry_file=entry_file,
        )
        if exit_code != 0 and not output_pdf.exists():
            return stdout, stderr, output_pdf
        return stdout, stderr, output_pdf

    @staticmethod
    def _resolve_output_pdf(mounted_project_dir: Path, *, entry_file: str) -> Path:
        entry = Path(entry_file)
        return mounted_project_dir / entry.parent / f"{entry.stem}.pdf"

    @staticmethod
    def _build_command(*, entry_file: str, compiler: str) -> list[str]:
        entry = Path(entry_file)
        main_dir = entry.parent.as_posix() if entry.parent.as_posix() else "."
        main_name = entry.name
        main_stem = entry.stem
        latex_flags = "-interaction=nonstopmode -halt-on-error -file-line-error -synctex=1"
        main_dir_arg = shlex.quote(main_dir)
        main_name_arg = shlex.quote(main_name)
        main_stem_arg = shlex.quote(main_stem)
        script = "\n".join(
            [
                "set +e",
                "cd /workspace/project",
                f"cd {main_dir_arg}",
                f"{compiler} {latex_flags} {main_name_arg} > compile-pass1.log 2>&1",
                (
                    f"if [ -f {main_stem_arg}.aux ] && grep -q '\\\\abx@aux@' {main_stem_arg}.aux; "
                    f"then biber {main_stem_arg} > compile-bib.log 2>&1; "
                    f"elif [ -f {main_stem_arg}.aux ] && grep -Eq '\\\\citation|\\\\bibdata' {main_stem_arg}.aux; "
                    f"then bibtex {main_stem_arg} > compile-bib.log 2>&1; fi"
                ),
                f"{compiler} {latex_flags} {main_name_arg} > compile-pass2.log 2>&1",
                f"{compiler} {latex_flags} {main_name_arg} > compile-pass3.log 2>&1",
                "cat compile-pass1.log 2>/dev/null",
                "cat compile-bib.log 2>/dev/null",
                "cat compile-pass2.log 2>/dev/null",
                "cat compile-pass3.log 2>/dev/null",
            ]
        )
        return ["/bin/bash", "-lc", script]
