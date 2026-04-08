"""Bridge workspace outputs to persisted LaTeX projects."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.latex_project import LatexProject
from src.services.latex import LatexProjectService

_SCI_SECTION_SPECS: tuple[tuple[str, str, str], ...] = (
    ("abstract", "Abstract", "sections/00_abstract.tex"),
    ("introduction", "Introduction", "sections/10_introduction.tex"),
    ("related_work", "Related Work", "sections/20_related_work.tex"),
    ("methodology", "Methodology", "sections/30_methodology.tex"),
    ("experiments", "Experiments", "sections/40_experiments.tex"),
    ("results", "Results", "sections/50_results.tex"),
    ("discussion", "Discussion", "sections/60_discussion.tex"),
    ("conclusion", "Conclusion", "sections/70_conclusion.tex"),
)

_PROPOSAL_DEFAULT_SECTION_SPECS: tuple[tuple[str, str, str], ...] = (
    ("background", "研究背景与意义", "sections/10_background.tex"),
    ("status", "国内外研究现状", "sections/20_status.tex"),
    ("objectives", "研究目标与主要内容", "sections/30_objectives.tex"),
    ("methodology", "技术路线与方法设计", "sections/40_methodology.tex"),
    ("innovation", "创新点与预期成果", "sections/50_innovation.tex"),
    ("schedule", "进度安排与风险预案", "sections/60_schedule.tex"),
)

_PATENT_DEFAULT_SECTION_SPECS: tuple[tuple[str, str, str], ...] = (
    ("technical_field", "技术领域", "sections/10_technical_field.tex"),
    ("background", "背景技术", "sections/20_background.tex"),
    ("summary", "发明内容", "sections/30_summary.tex"),
    ("drawings", "附图说明", "sections/40_drawings.tex"),
    ("embodiments", "具体实施方式", "sections/50_embodiments.tex"),
)

_SOFTWARE_COPYRIGHT_SECTION_SPECS: tuple[tuple[str, str, str], ...] = (
    ("system_overview", "系统概述", "sections/10_system_overview.tex"),
    ("module_design", "模块设计", "sections/20_module_design.tex"),
    ("data_flow", "数据流程", "sections/30_data_flow.tex"),
    ("deployment_architecture", "部署架构", "sections/40_deployment_architecture.tex"),
    ("security_and_permissions", "安全与权限", "sections/50_security_permissions.tex"),
    ("operation_steps", "操作步骤", "sections/60_operation_steps.tex"),
    ("materials_checklist", "材料清单与核对", "sections/70_materials_checklist.tex"),
)


class WorkspaceLatexProjectService:
    """Create or update the canonical LaTeX project linked to a workspace."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.project_service = LatexProjectService(db)

    @staticmethod
    def _project_bridge_metadata(project: LatexProject) -> dict[str, Any]:
        llm_config = project.llm_config if isinstance(project.llm_config, dict) else {}
        metadata = llm_config.get("metadata")
        return dict(metadata) if isinstance(metadata, dict) else {}

    @classmethod
    def _merge_bridge_metadata(
        cls,
        project: LatexProject,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        metadata = cls._project_bridge_metadata(project)
        metadata.setdefault("managed_files", {})
        metadata.setdefault("sync_conflicts", [])
        metadata.update(updates)
        if not isinstance(metadata.get("managed_files"), dict):
            metadata["managed_files"] = {}
        if not isinstance(metadata.get("sync_conflicts"), list):
            metadata["sync_conflicts"] = []
        return metadata

    @staticmethod
    def _clear_conflicts(metadata: dict[str, Any]) -> None:
        metadata["sync_conflicts"] = []

    @staticmethod
    def _content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _record_conflict(
        metadata: dict[str, Any],
        *,
        logical_key: str,
        relative_path: str,
        pending_content: str,
    ) -> None:
        conflicts = metadata.setdefault("sync_conflicts", [])
        if not isinstance(conflicts, list):
            conflicts = []
            metadata["sync_conflicts"] = conflicts
        conflicts[:] = [
            item
            for item in conflicts
            if not (
                isinstance(item, dict)
                and str(item.get("logical_key") or "") == logical_key
            )
        ]
        entry = {
            "logical_key": logical_key,
            "path": relative_path,
            "reason": "user_modified",
            "pending_content": pending_content,
        }
        conflicts.append(entry)

    async def _safe_bridge_write(
        self,
        project: LatexProject,
        *,
        relative_path: str,
        content: str,
        logical_key: str,
        metadata: dict[str, Any],
    ) -> None:
        managed_files = metadata.setdefault("managed_files", {})
        if not isinstance(managed_files, dict):
            managed_files = {}
            metadata["managed_files"] = managed_files
        record = managed_files.get(logical_key)

        try:
            current_content = self.project_service.read_text_file(project, relative_path)
        except FileNotFoundError:
            current_content = None

        if current_content == content:
            managed_files[logical_key] = {
                "path": relative_path,
                "content_hash": self._content_hash(content),
                "protected": (
                    bool(record.get("protected"))
                    if isinstance(record, dict)
                    else False
                ),
            }
            return

        safe_to_write = current_content is None
        if isinstance(record, dict) and current_content is not None:
            recorded_hash = str(record.get("content_hash") or "")
            recorded_path = str(record.get("path") or "")
            protected = bool(record.get("protected"))
            if (
                recorded_path == relative_path
                and recorded_hash == self._content_hash(current_content)
                and not protected
            ):
                safe_to_write = True

        if not safe_to_write:
            self._record_conflict(
                metadata,
                logical_key=logical_key,
                relative_path=relative_path,
                pending_content=content,
            )
            return

        await self.project_service.write_text_file(project, relative_path, content)
        managed_files[logical_key] = {
            "path": relative_path,
            "content_hash": self._content_hash(content),
            "protected": False,
        }

    async def sync_project(
        self,
        *,
        workspace_id: str,
        project_name: str,
        main_file: str,
        main_tex: str,
        bib_tex: str,
        template: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LatexProject:
        workspace = await self._load_workspace_bridge_row(workspace_id)
        if workspace is None:
            raise ValueError(f"Workspace not found: {workspace_id}")

        owner_user_id = str(workspace["user_id"])
        linked_project = await self._find_existing_project(
            workspace_id,
            owner_user_id=owner_user_id,
            template=template,
        )
        if linked_project is None:
            linked_project = await self.project_service.create(
                user_id=owner_user_id,
                name=project_name,
                template_id=None,
            )

        project_metadata = self._merge_bridge_metadata(linked_project, metadata or {})
        await self._safe_bridge_write(
            linked_project,
            relative_path=main_file,
            content=main_tex,
            logical_key="project:main",
            metadata=project_metadata,
        )
        await self._safe_bridge_write(
            linked_project,
            relative_path="references.bib",
            content=bib_tex,
            logical_key="project:references",
            metadata=project_metadata,
        )
        if bib_tex.strip():
            await self._safe_bridge_write(
                linked_project,
                relative_path="refs.bib",
                content=bib_tex,
                logical_key="project:refs_alias",
                metadata=project_metadata,
            )
        update_payload: dict[str, Any] = {
            "name": project_name,
            "main_file": main_file,
        }
        update_payload["llm_config"] = {
            "workspace_id": workspace_id,
            "bridge": "workspace_latex_project",
            "template": template,
            "role": "primary",
            "metadata": project_metadata,
        }
        linked_project = await self.project_service.update(
            linked_project,
            **update_payload,
        )
        return linked_project

    async def _load_workspace_bridge_row(self, workspace_id: str) -> dict[str, Any] | None:
        result = await self.db.execute(
            text(
                """
                select id, user_id, name, description
                from workspaces
                where id = :workspace_id
                limit 1
                """
            ),
            {"workspace_id": workspace_id},
        )
        row = result.mappings().first()
        return dict(row) if row is not None else None

    async def _find_existing_project(
        self,
        workspace_id: str,
        *,
        owner_user_id: str,
        template: str | None = None,
    ) -> LatexProject | None:
        params: dict[str, Any] = {
            "workspace_id": workspace_id,
            "owner_user_id": owner_user_id,
        }
        template_clause = ""
        if template:
            template_clause = "and llm_config->>'template' = :template"
            params["template"] = template

        result = await self.db.execute(
            text(
                f"""
                select id
                from latex_projects
                where llm_config is not null
                  and user_id = :owner_user_id
                  and llm_config->>'workspace_id' = :workspace_id
                  {template_clause}
                order by updated_at desc
                limit 1
                """
            ),
            params,
        )
        row = result.mappings().first()
        if row is not None:
            project = await self.db.get(LatexProject, str(row["id"]))
            if project is not None:
                return project
        return None

    async def sync_sci_outline_project(
        self,
        *,
        workspace_id: str,
        paper_title: str,
        abstract: str,
        keywords: list[str],
        sections: list[dict[str, Any]],
    ) -> tuple[LatexProject, dict[str, str]]:
        workspace = await self._load_workspace_bridge_row(workspace_id)
        if workspace is None:
            raise ValueError(f"Workspace not found: {workspace_id}")

        linked_project = await self._find_existing_project(
            workspace_id,
            owner_user_id=str(workspace["user_id"]),
            template="sci_default",
        )
        if linked_project is None:
            linked_project = await self.project_service.create(
                user_id=str(workspace["user_id"]),
                name=paper_title,
                template_id=None,
            )

        project_metadata = self._merge_bridge_metadata(
            linked_project,
            {
                "paper_title": paper_title,
                "keywords": keywords,
            },
        )
        self._clear_conflicts(project_metadata)
        section_map = dict(project_metadata.get("section_map") or {})
        for key, _title, filename in _SCI_SECTION_SPECS:
            section_map.setdefault(key, filename)
        project_metadata["section_map"] = section_map

        focus_by_key = self._sci_outline_focus_by_key(sections)
        for key, title, filename in _SCI_SECTION_SPECS:
            try:
                existing_content = self.project_service.read_text_file(linked_project, filename)
            except FileNotFoundError:
                existing_content = ""

            if key == "abstract":
                content = abstract.strip() or "Abstract to be refined."
            elif existing_content.strip():
                continue
            else:
                focus = focus_by_key.get(key) or f"Draft the {title.lower()} section here."
                content = f"% {title}\n{focus}\n"

            await self._safe_bridge_write(
                linked_project,
                relative_path=filename,
                content=content,
                logical_key=f"section:{key}",
                metadata=project_metadata,
            )

        main_tex = self._build_sci_main_tex(
            paper_title=paper_title,
            keywords=keywords,
            section_map=section_map,
        )
        await self._safe_bridge_write(
            linked_project,
            relative_path="main.tex",
            content=main_tex,
            logical_key="project:main",
            metadata=project_metadata,
        )
        linked_project = await self.project_service.update(
            linked_project,
            name=paper_title,
            main_file="main.tex",
            llm_config={
                "workspace_id": workspace_id,
                "bridge": "workspace_latex_project",
                "template": "sci_default",
                "role": "primary",
                "metadata": project_metadata,
            },
        )
        return linked_project, section_map

    async def sync_sci_section_draft(
        self,
        *,
        workspace_id: str,
        paper_title: str,
        section_type: str,
        section_title: str,
        content: str,
    ) -> tuple[LatexProject, str, dict[str, str]]:
        linked_project, section_map = await self.sync_sci_outline_project(
            workspace_id=workspace_id,
            paper_title=paper_title,
            abstract="Abstract to be refined.",
            keywords=[],
            sections=[],
        )
        project_metadata = self._merge_bridge_metadata(
            linked_project,
            {
                "paper_title": paper_title,
                "keywords": list(self._project_bridge_metadata(linked_project).get("keywords") or []),
                "section_map": section_map,
            },
        )
        self._clear_conflicts(project_metadata)
        section_file = section_map.get(section_type) or f"sections/{section_type}.tex"
        section_map[section_type] = section_file
        project_metadata["section_map"] = section_map
        body = content.strip()
        if section_type == "abstract":
            file_content = body
        else:
            file_content = f"% {section_title}\n{body}\n"
        await self._safe_bridge_write(
            linked_project,
            relative_path=section_file,
            content=file_content,
            logical_key=f"section:{section_type}",
            metadata=project_metadata,
        )

        project_keywords = list(project_metadata.get("keywords") or [])
        main_tex = self._build_sci_main_tex(
            paper_title=paper_title,
            keywords=project_keywords,
            section_map=section_map,
        )
        await self._safe_bridge_write(
            linked_project,
            relative_path="main.tex",
            content=main_tex,
            logical_key="project:main",
            metadata=project_metadata,
        )
        linked_project = await self.project_service.update(
            linked_project,
            name=paper_title,
            main_file="main.tex",
            llm_config={
                "workspace_id": workspace_id,
                "bridge": "workspace_latex_project",
                "template": "sci_default",
                "role": "primary",
                "metadata": project_metadata,
            },
        )
        return linked_project, section_file, section_map

    @staticmethod
    def _normalize_sci_section_key(raw_title: str) -> str:
        normalized = re.sub(r"[^a-z]+", "_", raw_title.lower()).strip("_")
        if "abstract" in normalized:
            return "abstract"
        if "introduction" in normalized or normalized == "intro":
            return "introduction"
        if "related" in normalized:
            return "related_work"
        if "method" in normalized:
            return "methodology"
        if "experiment" in normalized:
            return "experiments"
        if "result" in normalized:
            return "results"
        if "discussion" in normalized:
            return "discussion"
        if "conclusion" in normalized:
            return "conclusion"
        return normalized or "section"

    @classmethod
    def _sci_outline_focus_by_key(cls, sections: list[dict[str, Any]]) -> dict[str, str]:
        focus_by_key: dict[str, str] = {}
        for section in sections:
            if not isinstance(section, dict):
                continue
            title = str(section.get("title") or "").strip()
            focus = str(section.get("focus") or "").strip()
            if not title:
                continue
            key = cls._normalize_sci_section_key(title)
            if key == "results" and "discussion" in title.lower():
                focus_by_key.setdefault("results", focus)
                focus_by_key.setdefault("discussion", focus)
                continue
            if focus:
                focus_by_key[key] = focus
        return focus_by_key

    @staticmethod
    def _build_sci_main_tex(
        *,
        paper_title: str,
        keywords: list[str],
        section_map: dict[str, str],
    ) -> str:
        keyword_line = ", ".join(keyword for keyword in keywords if keyword.strip())
        section_inputs: list[str] = []
        for key, title, _filename in _SCI_SECTION_SPECS:
            if key == "abstract":
                continue
            path = section_map.get(key)
            if not path:
                continue
            section_inputs.append(f"\\section{{{title}}}\n\\input{{{path}}}\n")
        abstract_path = section_map.get("abstract", "sections/00_abstract.tex")
        return "\n".join(
            [
                "\\documentclass[11pt]{article}",
                "\\usepackage[margin=1in]{geometry}",
                "\\usepackage{graphicx}",
                "\\usepackage{amsmath,amssymb}",
                "\\usepackage{booktabs}",
                "\\usepackage{hyperref}",
                "\\title{" + paper_title.replace("{", "").replace("}", "") + "}",
                "\\author{}",
                "\\date{\\today}",
                "\\begin{document}",
                "\\maketitle",
                "\\begin{abstract}",
                f"\\input{{{abstract_path}}}",
                "\\end{abstract}",
                (f"\\noindent\\textbf{{Keywords}}: {keyword_line}\n" if keyword_line else ""),
                *section_inputs,
                "\\bibliographystyle{plain}",
                "\\bibliography{references}",
                "\\end{document}",
            ]
        )

    async def sync_proposal_outline_project(
        self,
        *,
        workspace_id: str,
        project_title: str,
        sections: list[dict[str, Any]],
    ) -> tuple[LatexProject, dict[str, str]]:
        workspace = await self._load_workspace_bridge_row(workspace_id)
        if workspace is None:
            raise ValueError(f"Workspace not found: {workspace_id}")

        linked_project = await self._find_existing_project(
            workspace_id,
            owner_user_id=str(workspace["user_id"]),
            template="proposal_default",
        )
        if linked_project is None:
            linked_project = await self.project_service.create(
                user_id=str(workspace["user_id"]),
                name=project_title,
                template_id=None,
            )

        project_metadata = self._merge_bridge_metadata(
            linked_project,
            {"project_title": project_title},
        )
        self._clear_conflicts(project_metadata)
        section_map = dict(project_metadata.get("section_map") or {})
        if not section_map:
            for key, _title, filename in _PROPOSAL_DEFAULT_SECTION_SPECS:
                section_map[key] = filename
        project_metadata["section_map"] = section_map

        for index, section in enumerate(sections):
            if not isinstance(section, dict):
                continue
            section_id = str(section.get("id") or "").strip() or f"section_{index + 1}"
            section_title = str(section.get("title") or section_id).strip() or section_id
            section_content = str(section.get("content") or "").strip()
            section_file = section_map.get(section_id) or f"sections/{index + 1:02d}_{section_id}.tex"
            section_map[section_id] = section_file
            if section_content:
                rendered = f"% {section_title}\n{section_content}\n"
            else:
                rendered = f"% {section_title}\n待补充。\n"
            await self._safe_bridge_write(
                linked_project,
                relative_path=section_file,
                content=rendered,
                logical_key=f"section:{section_id}",
                metadata=project_metadata,
            )

        main_tex = self._build_proposal_main_tex(
            project_title=project_title,
            section_map=section_map,
            sections=sections,
        )
        await self._safe_bridge_write(
            linked_project,
            relative_path="main.tex",
            content=main_tex,
            logical_key="project:main",
            metadata=project_metadata,
        )
        linked_project = await self.project_service.update(
            linked_project,
            name=project_title,
            main_file="main.tex",
            llm_config={
                "workspace_id": workspace_id,
                "bridge": "workspace_latex_project",
                "template": "proposal_default",
                "role": "primary",
                "metadata": project_metadata,
            },
        )
        return linked_project, section_map

    async def sync_proposal_sections(
        self,
        *,
        workspace_id: str,
        project_title: str,
        sections: list[dict[str, Any]],
    ) -> tuple[LatexProject, dict[str, str]]:
        linked_project, section_map = await self.sync_proposal_outline_project(
            workspace_id=workspace_id,
            project_title=project_title,
            sections=[],
        )
        project_metadata = self._merge_bridge_metadata(
            linked_project,
            {
                "project_title": project_title,
                "section_map": section_map,
            },
        )
        self._clear_conflicts(project_metadata)
        for index, section in enumerate(sections):
            if not isinstance(section, dict):
                continue
            section_id = str(section.get("id") or "").strip() or f"section_{index + 1}"
            section_title = str(section.get("title") or section_id).strip() or section_id
            section_content = str(section.get("content") or "").strip()
            section_file = section_map.get(section_id) or f"sections/{index + 1:02d}_{section_id}.tex"
            section_map[section_id] = section_file
            project_metadata["section_map"] = section_map
            await self._safe_bridge_write(
                linked_project,
                relative_path=section_file,
                content=f"% {section_title}\n{section_content}\n",
                logical_key=f"section:{section_id}",
                metadata=project_metadata,
            )

        ordered_sections = self._proposal_sections_from_map(section_map)
        main_tex = self._build_proposal_main_tex(
            project_title=project_title,
            section_map=section_map,
            sections=ordered_sections,
        )
        await self._safe_bridge_write(
            linked_project,
            relative_path="main.tex",
            content=main_tex,
            logical_key="project:main",
            metadata=project_metadata,
        )
        linked_project = await self.project_service.update(
            linked_project,
            name=project_title,
            main_file="main.tex",
            llm_config={
                "workspace_id": workspace_id,
                "bridge": "workspace_latex_project",
                "template": "proposal_default",
                "role": "primary",
                "metadata": project_metadata,
            },
        )
        return linked_project, section_map

    async def sync_proposal_experiment_design(
        self,
        *,
        workspace_id: str,
        project_title: str,
        payload: dict[str, Any],
    ) -> tuple[LatexProject, str, dict[str, str]]:
        linked_project, section_map = await self.sync_proposal_outline_project(
            workspace_id=workspace_id,
            project_title=project_title,
            sections=[],
        )
        project_metadata = self._merge_bridge_metadata(
            linked_project,
            {
                "project_title": project_title,
                "section_map": section_map,
            },
        )
        self._clear_conflicts(project_metadata)
        section_id = "experiment_design"
        section_file = section_map.get(section_id) or "sections/70_experiment_design.tex"
        section_map[section_id] = section_file
        project_metadata["section_map"] = section_map
        content = self._render_proposal_experiment_design(payload)
        await self._safe_bridge_write(
            linked_project,
            relative_path=section_file,
            content=f"% Experiment Design\n{content}\n",
            logical_key=f"section:{section_id}",
            metadata=project_metadata,
        )
        ordered_sections = self._proposal_sections_from_map(section_map)
        main_tex = self._build_proposal_main_tex(
            project_title=project_title,
            section_map=section_map,
            sections=ordered_sections,
        )
        await self._safe_bridge_write(
            linked_project,
            relative_path="main.tex",
            content=main_tex,
            logical_key="project:main",
            metadata=project_metadata,
        )
        linked_project = await self.project_service.update(
            linked_project,
            name=project_title,
            main_file="main.tex",
            llm_config={
                "workspace_id": workspace_id,
                "bridge": "workspace_latex_project",
                "template": "proposal_default",
                "role": "primary",
                "metadata": project_metadata,
            },
        )
        return linked_project, section_file, section_map

    @staticmethod
    def _build_proposal_main_tex(
        *,
        project_title: str,
        section_map: dict[str, str],
        sections: list[dict[str, Any]],
    ) -> str:
        section_inputs: list[str] = []
        ordered = sections or WorkspaceLatexProjectService._proposal_sections_from_map(section_map)
        for index, section in enumerate(ordered, start=1):
            section_id = str(section.get("id") or "").strip()
            title = str(section.get("title") or f"Section {index}").strip()
            path = section_map.get(section_id)
            if not path:
                continue
            section_inputs.append(f"\\section{{{title}}}\n\\input{{{path}}}\n")
        return "\n".join(
            [
                "\\documentclass[UTF8,12pt]{ctexart}",
                "\\usepackage[a4paper,margin=1in]{geometry}",
                "\\usepackage{hyperref}",
                "\\usepackage{booktabs}",
                "\\title{" + project_title.replace("{", "").replace("}", "") + "}",
                "\\author{}",
                "\\date{\\today}",
                "\\begin{document}",
                "\\maketitle",
                "\\tableofcontents",
                "\\newpage",
                *section_inputs,
                "\\end{document}",
            ]
        )

    @staticmethod
    def _proposal_sections_from_map(section_map: dict[str, str]) -> list[dict[str, str]]:
        ordered: list[dict[str, str]] = []
        for section_id, path in sorted(section_map.items(), key=lambda item: item[1]):
            title = section_id.replace("_", " ").title()
            ordered.append({"id": section_id, "title": title})
        return ordered

    @staticmethod
    def _render_proposal_experiment_design(payload: dict[str, Any]) -> str:
        lines: list[str] = []
        hypotheses = payload.get("hypotheses")
        if isinstance(hypotheses, list) and hypotheses:
            lines.append("\\subsection{研究假设}")
            for item in hypotheses:
                lines.append(f"- {str(item)}")
            lines.append("")

        procedure = payload.get("procedure")
        if isinstance(procedure, list) and procedure:
            lines.append("\\subsection{实验步骤}")
            for item in procedure:
                lines.append(f"- {str(item)}")
            lines.append("")

        evaluation = payload.get("evaluation")
        if isinstance(evaluation, list) and evaluation:
            lines.append("\\subsection{评价指标}")
            for item in evaluation:
                lines.append(f"- {str(item)}")
            lines.append("")

        risks = payload.get("risks")
        if isinstance(risks, list) and risks:
            lines.append("\\subsection{潜在风险}")
            for item in risks:
                lines.append(f"- {str(item)}")
            lines.append("")

        return "\n".join(lines).strip() or "待补充实验设计内容。"

    async def sync_patent_outline_project(
        self,
        *,
        workspace_id: str,
        project_title: str,
        sections: list[dict[str, Any]],
        claims_draft: dict[str, Any],
    ) -> tuple[LatexProject, dict[str, str]]:
        workspace = await self._load_workspace_bridge_row(workspace_id)
        if workspace is None:
            raise ValueError(f"Workspace not found: {workspace_id}")

        linked_project = await self._find_existing_project(
            workspace_id,
            owner_user_id=str(workspace["user_id"]),
            template="patent_default",
        )
        if linked_project is None:
            linked_project = await self.project_service.create(
                user_id=str(workspace["user_id"]),
                name=project_title,
                template_id=None,
            )

        project_metadata = self._merge_bridge_metadata(
            linked_project,
            {"project_title": project_title},
        )
        self._clear_conflicts(project_metadata)
        section_map = dict(project_metadata.get("section_map") or {})
        for key, _title, filename in _PATENT_DEFAULT_SECTION_SPECS:
            section_map.setdefault(key, filename)
        section_map.setdefault("claims", "sections/90_claims.tex")
        project_metadata["section_map"] = section_map

        section_content_by_key = self._patent_sections_by_key(sections)
        for key, title, filename in _PATENT_DEFAULT_SECTION_SPECS:
            content = section_content_by_key.get(key) or f"待补充：{title}"
            await self._safe_bridge_write(
                linked_project,
                relative_path=filename,
                content=f"% {title}\n{content}\n",
                logical_key=f"section:{key}",
                metadata=project_metadata,
            )

        claims_text = self._render_patent_claims(claims_draft)
        await self._safe_bridge_write(
            linked_project,
            relative_path=section_map["claims"],
            content=f"% Claims\n{claims_text}\n",
            logical_key="section:claims",
            metadata=project_metadata,
        )

        main_tex = self._build_patent_main_tex(
            project_title=project_title,
            section_map=section_map,
        )
        await self._safe_bridge_write(
            linked_project,
            relative_path="main.tex",
            content=main_tex,
            logical_key="project:main",
            metadata=project_metadata,
        )
        linked_project = await self.project_service.update(
            linked_project,
            name=project_title,
            main_file="main.tex",
            llm_config={
                "workspace_id": workspace_id,
                "bridge": "workspace_latex_project",
                "template": "patent_default",
                "role": "primary",
                "metadata": project_metadata,
            },
        )
        return linked_project, section_map

    @staticmethod
    def _patent_sections_by_key(sections: list[dict[str, Any]]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for section in sections:
            if not isinstance(section, dict):
                continue
            title = str(section.get("title") or "").strip().lower()
            content = str(section.get("content") or "").strip()
            if not content:
                continue
            if "技术领域" in title:
                mapping["technical_field"] = content
            elif "背景" in title:
                mapping["background"] = content
            elif "发明内容" in title or "概述" in title:
                mapping["summary"] = content
            elif "附图" in title:
                mapping["drawings"] = content
            elif "实施" in title:
                mapping["embodiments"] = content
        return mapping

    @staticmethod
    def _render_patent_claims(claims_draft: dict[str, Any]) -> str:
        lines: list[str] = ["\\section{权利要求书}"]
        independent = claims_draft.get("independent_claims")
        dependent = claims_draft.get("dependent_claims")
        if isinstance(independent, list) and independent:
            lines.append("\\subsection{独立权利要求}")
            for item in independent:
                if isinstance(item, dict):
                    lines.append(str(item.get("content") or item.get("claim") or ""))
        if isinstance(dependent, list) and dependent:
            lines.append("\\subsection{从属权利要求}")
            for item in dependent:
                if isinstance(item, dict):
                    lines.append(str(item.get("content") or item.get("claim") or ""))
        return "\n\n".join(line for line in lines if line.strip())

    @staticmethod
    def _build_patent_main_tex(
        *,
        project_title: str,
        section_map: dict[str, str],
    ) -> str:
        inputs = [
            ("技术领域", section_map.get("technical_field")),
            ("背景技术", section_map.get("background")),
            ("发明内容", section_map.get("summary")),
            ("附图说明", section_map.get("drawings")),
            ("具体实施方式", section_map.get("embodiments")),
            ("权利要求书", section_map.get("claims")),
        ]
        blocks = []
        for title, path in inputs:
            if not path:
                continue
            blocks.append(f"\\section{{{title}}}\n\\input{{{path}}}\n")
        return "\n".join(
            [
                "\\documentclass[UTF8,12pt]{ctexart}",
                "\\usepackage[a4paper,margin=1in]{geometry}",
                "\\usepackage{hyperref}",
                "\\title{" + project_title.replace("{", "").replace("}", "") + "}",
                "\\author{}",
                "\\date{\\today}",
                "\\begin{document}",
                "\\maketitle",
                *blocks,
                "\\end{document}",
            ]
        )

    async def sync_software_copyright_technical_description(
        self,
        *,
        workspace_id: str,
        project_title: str,
        sections: dict[str, Any],
    ) -> tuple[LatexProject, dict[str, str]]:
        workspace = await self._load_workspace_bridge_row(workspace_id)
        if workspace is None:
            raise ValueError(f"Workspace not found: {workspace_id}")

        linked_project = await self._find_existing_project(
            workspace_id,
            owner_user_id=str(workspace["user_id"]),
            template="software_copyright_default",
        )
        if linked_project is None:
            linked_project = await self.project_service.create(
                user_id=str(workspace["user_id"]),
                name=project_title,
                template_id=None,
            )

        project_metadata = self._merge_bridge_metadata(
            linked_project,
            {"project_title": project_title},
        )
        self._clear_conflicts(project_metadata)
        section_map = dict(project_metadata.get("section_map") or {})
        for key, _title, filename in _SOFTWARE_COPYRIGHT_SECTION_SPECS:
            section_map.setdefault(key, filename)
        project_metadata["section_map"] = section_map

        for key, title, filename in _SOFTWARE_COPYRIGHT_SECTION_SPECS:
            section = sections.get(key) if isinstance(sections, dict) else None
            section_content = (
                str(section.get("content") or "").strip()
                if isinstance(section, dict)
                else ""
            )
            content = section_content or f"待补充：{title}"
            await self._safe_bridge_write(
                linked_project,
                relative_path=filename,
                content=f"% {title}\n{content}\n",
                logical_key=f"section:{key}",
                metadata=project_metadata,
            )

        main_tex = self._build_software_copyright_main_tex(
            project_title=project_title,
            section_map=section_map,
        )
        await self._safe_bridge_write(
            linked_project,
            relative_path="main.tex",
            content=main_tex,
            logical_key="project:main",
            metadata=project_metadata,
        )
        linked_project = await self.project_service.update(
            linked_project,
            name=project_title,
            main_file="main.tex",
            llm_config={
                "workspace_id": workspace_id,
                "bridge": "workspace_latex_project",
                "template": "software_copyright_default",
                "role": "primary",
                "metadata": project_metadata,
            },
        )
        return linked_project, section_map

    async def sync_software_copyright_materials(
        self,
        *,
        workspace_id: str,
        project_title: str,
        required_materials: list[dict[str, Any]],
        review_checklist: list[str],
    ) -> tuple[LatexProject, str, dict[str, str]]:
        linked_project, section_map = await self.sync_software_copyright_technical_description(
            workspace_id=workspace_id,
            project_title=project_title,
            sections={},
        )
        project_metadata = self._merge_bridge_metadata(
            linked_project,
            {
                "project_title": project_title,
                "section_map": section_map,
            },
        )
        self._clear_conflicts(project_metadata)
        section_file = section_map.get("materials_checklist") or "sections/70_materials_checklist.tex"
        section_map["materials_checklist"] = section_file
        project_metadata["section_map"] = section_map
        content = self._render_software_copyright_materials(
            required_materials=required_materials,
            review_checklist=review_checklist,
        )
        await self._safe_bridge_write(
            linked_project,
            relative_path=section_file,
            content=f"% 材料清单与核对\n{content}\n",
            logical_key="section:materials_checklist",
            metadata=project_metadata,
        )
        main_tex = self._build_software_copyright_main_tex(
            project_title=project_title,
            section_map=section_map,
        )
        await self._safe_bridge_write(
            linked_project,
            relative_path="main.tex",
            content=main_tex,
            logical_key="project:main",
            metadata=project_metadata,
        )
        linked_project = await self.project_service.update(
            linked_project,
            name=project_title,
            main_file="main.tex",
            llm_config={
                "workspace_id": workspace_id,
                "bridge": "workspace_latex_project",
                "template": "software_copyright_default",
                "role": "primary",
                "metadata": project_metadata,
            },
        )
        return linked_project, section_file, section_map

    @staticmethod
    def _build_software_copyright_main_tex(
        *,
        project_title: str,
        section_map: dict[str, str],
    ) -> str:
        blocks = []
        for key, title, _filename in _SOFTWARE_COPYRIGHT_SECTION_SPECS:
            path = section_map.get(key)
            if not path:
                continue
            blocks.append(f"\\section{{{title}}}\n\\input{{{path}}}\n")
        return "\n".join(
            [
                "\\documentclass[UTF8,12pt]{ctexart}",
                "\\usepackage[a4paper,margin=1in]{geometry}",
                "\\usepackage{hyperref}",
                "\\title{" + project_title.replace("{", "").replace("}", "") + "}",
                "\\author{}",
                "\\date{\\today}",
                "\\begin{document}",
                "\\maketitle",
                *blocks,
                "\\end{document}",
            ]
        )

    @staticmethod
    def _render_software_copyright_materials(
        *,
        required_materials: list[dict[str, Any]],
        review_checklist: list[str],
    ) -> str:
        lines: list[str] = []
        if required_materials:
            lines.append("\\subsection{材料清单}")
            for item in required_materials:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or item.get("id") or "材料项")
                lines.append(f"\\paragraph{{{title}}}")
                required_fields = item.get("required_fields")
                if isinstance(required_fields, list):
                    for field in required_fields:
                        lines.append(f"- {str(field)}")
                tips = item.get("tips") or item.get("notes")
                if isinstance(tips, list):
                    for tip in tips[:3]:
                        lines.append(f"- 备注：{str(tip)}")
                lines.append("")

        if review_checklist:
            lines.append("\\subsection{核对清单}")
            for item in review_checklist:
                lines.append(f"- {str(item)}")

        return "\n".join(lines).strip() or "待补充软件著作权申请材料。"
