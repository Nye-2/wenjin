"""Service helpers for thesis workspace feature handlers.

This module keeps handler logic thin and reusable by encapsulating:
1. figure generation (with degrade fallback),
2. thesis compile payload assembly (with compile fallback),
3. opening report payload generation (template + optional LLM fill).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from src.academic.services import ArtifactService
from src.artifacts import ArtifactType
from src.database import Artifact, get_db_session
from src.execution.public_paths import sandbox_path_to_public_url
from src.execution.types import ExecutionType
from src.models.factory import create_chat_model
from src.models.router import list_user_selectable_models, route_writing_model
from src.services.literature_service import LiteratureService
from src.thesis.execution import get_execution_service
from src.thesis.execution.figure_tool import generate_figure
from src.thesis.execution.latex_tool import compile_latex
from src.thesis.workflow.latex_template import get_template

logger = logging.getLogger(__name__)

THESIS_SCHEMA_VERSION = "v1"
THESIS_OUTPUT_LANGUAGE = "zh"

_FIGURE_STRATEGY_BY_TYPE: dict[str, str] = {
    "flowchart": "mermaid",
    "architecture": "mermaid",
    "diagram": "mermaid",
    "data_visualization": "python",
    "data_chart": "python",
    "chart": "python",
    "graph": "python",
    "concept_map": "kling",
    "concept": "kling",
}

_REPORT_TYPES = {
    "opening_report",
    "literature_review",
    "feasibility_analysis",
}

_STRATEGY_TO_EXECUTION_TYPE: dict[str, ExecutionType] = {
    "mermaid": ExecutionType.MERMAID_DIAGRAM,
    "python": ExecutionType.PYTHON_PLOT,
    "kling": ExecutionType.AI_IMAGE,
}


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def resolve_thesis_output_language(template: str | None = None) -> str:
    """Thesis output language is fixed to Chinese regardless of template."""
    _ = template
    return THESIS_OUTPUT_LANGUAGE


def _truncate(value: str, max_len: int = 280) -> str:
    if len(value) <= max_len:
        return value
    return f"{value[: max_len - 3]}..."


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_figure_type(raw_type: str) -> str:
    value = (raw_type or "").strip().lower()
    if not value:
        return "flowchart"
    return value


def _resolve_figure_strategy(fig_type: str) -> str:
    normalized = _normalize_figure_type(fig_type)
    return _FIGURE_STRATEGY_BY_TYPE.get(normalized, "mermaid")


def _sanitize_mermaid_label(label: str) -> str:
    cleaned = label.replace('"', "'").replace("\n", " ").strip()
    return _truncate(cleaned, max_len=36)


def _build_mermaid_source(description: str) -> str:
    summary = _sanitize_mermaid_label(description or "研究流程")
    return "\n".join(
        [
            "flowchart TD",
            f'  A["研究问题: {summary}"] --> B["方法设计"]',
            '  B --> C["实验验证"]',
            '  C --> D["结果分析"]',
            '  D --> E["结论与展望"]',
        ]
    )


def _build_python_source(description: str) -> str:
    title = (description or "实验结果对比").replace("'", "").replace("\n", " ")
    title = _truncate(title, max_len=40)
    return "\n".join(
        [
            "import matplotlib.pyplot as plt",
            "",
            "labels = ['方案A', '方案B', '方案C', '方案D']",
            "values = [0.68, 0.74, 0.81, 0.79]",
            "",
            "fig, ax = plt.subplots(figsize=(8, 4.5))",
            "ax.bar(labels, values, color=['#2563eb', '#0891b2', '#16a34a', '#f59e0b'])",
            "ax.set_ylim(0, 1)",
            f"ax.set_title('{title}')",
            "ax.set_ylabel('Score')",
            "for idx, value in enumerate(values):",
            "    ax.text(idx, value + 0.02, f'{value:.2f}', ha='center')",
            "plt.tight_layout()",
            "",
            "# Required by PythonVizProvider: write image into /workspace/output",
            "plt.savefig('/workspace/output/chart.png', dpi=200)",
        ]
    )


def _build_kling_prompt(description: str) -> str:
    desc = _truncate((description or "研究概念图").replace("\n", " "), max_len=120)
    return (
        "生成一张用于本科论文的学术概念图，风格简洁、信息层次清晰。"
        f"主题：{desc}。要求包含核心实体、关键关系和流程方向，可直接用于论文插图。"
    )


def _build_figure_source(strategy: str, description: str) -> str:
    if strategy == "python":
        return _build_python_source(description)
    if strategy == "kling":
        return _build_kling_prompt(description)
    return _build_mermaid_source(description)


def _provider_ready(strategy: str) -> bool:
    exec_type = _STRATEGY_TO_EXECUTION_TYPE.get(strategy)
    if exec_type is None:
        return False

    try:
        execution_service = get_execution_service()
    except Exception:
        return False

    provider_map = getattr(execution_service, "PROVIDER_MAP", None)
    return isinstance(provider_map, dict) and exec_type in provider_map


def _build_degraded_figure_payload(
    *,
    fig_type: str,
    description: str,
    chapter_index: int | None,
    strategy: str,
    source: str,
    error: str | None,
) -> dict[str, Any]:
    content_field = "prompt" if strategy == "kling" else "source_code"
    return {
        "figure_type": fig_type,
        "description": description,
        "chapter_index": chapter_index,
        "strategy": strategy,
        "status": "degraded",
        "generated_at": _utc_now_iso(),
        "render_data": {},
        content_field: source,
        "upgrade": {
            "auto_upgrade": True,
            "required_execution_type": _STRATEGY_TO_EXECUTION_TYPE[strategy].value,
            "provider_ready": _provider_ready(strategy),
            "last_error": error,
        },
    }


async def build_figure_payload(
    *,
    workspace_id: str,
    workspace_name: str,
    thread_id: str | None,
    fig_type: str,
    description: str,
    chapter_index: int | None,
) -> dict[str, Any]:
    """Build figure artifact content with runtime generation + degrade fallback."""
    normalized_type = _normalize_figure_type(fig_type)
    strategy = _resolve_figure_strategy(normalized_type)
    source = _build_figure_source(strategy, description)

    if not _provider_ready(strategy):
        return _build_degraded_figure_payload(
            fig_type=normalized_type,
            description=description,
            chapter_index=chapter_index,
            strategy=strategy,
            source=source,
            error=f"provider for {strategy} is not ready",
        )

    figure_id = f"{workspace_name or 'figure'}-{int(datetime.now().timestamp())}"
    figure_id = re.sub(r"[^a-zA-Z0-9_.-]+", "-", figure_id).strip("-").lower()
    figure_id = _truncate(figure_id, max_len=64)

    result = await generate_figure(
        strategy=strategy,
        content=source,
        workspace_id=workspace_id,
        thread_id=thread_id,
        figure_id=figure_id,
        timeout=60,
    )

    if result.success:
        file_url = sandbox_path_to_public_url(
            result.figure_path,
            thread_id=thread_id,
        )
        payload: dict[str, Any] = {
            "figure_type": normalized_type,
            "description": description,
            "chapter_index": chapter_index,
            "strategy": strategy,
            "status": "generated",
            "generated_at": _utc_now_iso(),
            "render_data": {
                "file_path": result.figure_path,
                "file_url": file_url,
                "format": result.format,
            },
            "upgrade": {
                "auto_upgrade": False,
                "provider_ready": True,
                "last_error": None,
            },
        }
        # Keep source/prompt for reproducibility and future re-render.
        if strategy == "kling":
            payload["prompt"] = source
        else:
            payload["source_code"] = source
        return payload

    return _build_degraded_figure_payload(
        fig_type=normalized_type,
        description=description,
        chapter_index=chapter_index,
        strategy=strategy,
        source=source,
        error=result.error or "unknown generation error",
    )


def _escape_latex(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    escaped = text
    for raw, replacement in replacements.items():
        escaped = escaped.replace(raw, replacement)
    return escaped


def _render_markdown_to_latex(markdown: str) -> str:
    lines = markdown.splitlines()
    output: list[str] = []
    in_code_block = False
    in_list = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_list:
                output.append(r"\end{itemize}")
                in_list = False
            if in_code_block:
                output.append(r"\end{lstlisting}")
            else:
                output.append(r"\begin{lstlisting}")
            in_code_block = not in_code_block
            continue

        if in_code_block:
            output.append(line)
            continue

        if stripped.startswith("# "):
            if in_list:
                output.append(r"\end{itemize}")
                in_list = False
            output.append(f"\\section{{{_escape_latex(stripped[2:].strip())}}}")
            continue

        if stripped.startswith("## "):
            if in_list:
                output.append(r"\end{itemize}")
                in_list = False
            output.append(f"\\subsection{{{_escape_latex(stripped[3:].strip())}}}")
            continue

        if stripped.startswith("### "):
            if in_list:
                output.append(r"\end{itemize}")
                in_list = False
            output.append(f"\\subsubsection{{{_escape_latex(stripped[4:].strip())}}}")
            continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                output.append(r"\begin{itemize}")
                in_list = True
            output.append(f"\\item {_escape_latex(stripped[2:].strip())}")
            continue

        if not stripped:
            if in_list:
                output.append(r"\end{itemize}")
                in_list = False
            output.append("")
            continue

        if in_list:
            output.append(r"\end{itemize}")
            in_list = False
        output.append(_escape_latex(stripped))

    if in_list:
        output.append(r"\end{itemize}")
    if in_code_block:
        output.append(r"\end{lstlisting}")

    rendered = "\n".join(output).strip()
    return rendered or "\\section{内容占位}\n待补充章节内容。"


def _artifact_content(artifact: Artifact) -> dict[str, Any]:
    return artifact.content if isinstance(artifact.content, dict) else {}


async def _load_workspace_artifacts(workspace_id: str) -> list[Artifact]:
    async with get_db_session() as db:
        service = ArtifactService(db)
        return await service.list_by_workspace(workspace_id=workspace_id, limit=300)


async def _load_workspace_literature(workspace_id: str) -> list[dict[str, Any]]:
    async with get_db_session() as db:
        service = LiteratureService(db)
        response = await service.list_literature(workspace_id, offset=0, limit=120)
    items = response.get("items")
    return items if isinstance(items, list) else []


def _extract_outline_content(artifacts: list[Artifact]) -> dict[str, Any]:
    for artifact in artifacts:
        if artifact.type == ArtifactType.FRAMEWORK_OUTLINE.value:
            content = _artifact_content(artifact)
            outline = content.get("outline")
            if isinstance(outline, dict):
                return {"paper_title": content.get("paper_title"), **outline}
            return content
    return {}


def _extract_sorted_chapters(artifacts: list[Artifact]) -> list[dict[str, Any]]:
    chapter_artifacts = [
        artifact
        for artifact in artifacts
        if artifact.type == ArtifactType.THESIS_CHAPTER.value
    ]

    def sort_key(artifact: Artifact) -> tuple[int, str]:
        content = _artifact_content(artifact)
        index = _coerce_int(content.get("chapter_index"))
        return (index if index is not None else 999, str(artifact.created_at))

    chapter_artifacts.sort(key=sort_key)

    chapters: list[dict[str, Any]] = []
    for artifact in chapter_artifacts:
        content = _artifact_content(artifact)
        title = str(
            content.get("chapter_title")
            or artifact.title
            or f"章节{len(chapters) + 1}"
        )
        markdown = str(content.get("markdown") or "").strip()
        if markdown and not markdown.lstrip().startswith("#"):
            markdown = f"# {title}\n\n{markdown}"
        if not markdown:
            summary = str(content.get("summary") or content.get("content") or "待补充")
            markdown = f"# {title}\n\n{summary}"
        chapters.append(
            {
                "index": _coerce_int(content.get("chapter_index")),
                "title": title,
                "markdown": markdown,
            }
        )
    return chapters


def _extract_figures(artifacts: list[Artifact]) -> list[dict[str, Any]]:
    figures: list[dict[str, Any]] = []
    for artifact in artifacts:
        if artifact.type != ArtifactType.FIGURE.value:
            continue
        content = _artifact_content(artifact)
        render_data = content.get("render_data")
        file_path = (
            render_data.get("file_path")
            if isinstance(render_data, dict)
            else None
        )
        figures.append(
            {
                "title": artifact.title or "",
                "description": str(content.get("description") or ""),
                "status": str(content.get("status") or "unknown"),
                "file_path": file_path,
                "source_code": content.get("source_code"),
                "prompt": content.get("prompt"),
                "chapter_index": _coerce_int(content.get("chapter_index")),
            }
        )
    return figures


def _build_outline_fallback_chapters(outline: dict[str, Any]) -> list[dict[str, Any]]:
    raw_chapters = outline.get("chapters")
    if not isinstance(raw_chapters, list):
        return []

    chapter_payloads: list[dict[str, Any]] = []
    for index, chapter in enumerate(raw_chapters, start=1):
        if not isinstance(chapter, dict):
            continue
        title = str(chapter.get("title") or f"第{index}章")
        position = str(chapter.get("position") or "")
        key_points = chapter.get("keyPoints")
        points = (
            [str(item) for item in key_points if item]
            if isinstance(key_points, list)
            else []
        )
        lines = [f"# {title}"]
        if position:
            lines.append(f"\n{position}")
        if points:
            lines.append("\n## 关键要点")
            lines.extend(f"- {item}" for item in points[:6])
        chapter_payloads.append(
            {
                "index": index - 1,
                "title": title,
                "markdown": "\n".join(lines),
            }
        )
    return chapter_payloads


def _build_figure_latex(figures: list[dict[str, Any]]) -> str:
    if not figures:
        return ""

    blocks = [r"\section{图表产出与说明}"]
    for index, figure in enumerate(figures, start=1):
        description = _escape_latex(figure.get("description") or f"图表{index}")
        chapter_index = figure.get("chapter_index")
        chapter_hint = (
            f"（关联章节：第 {chapter_index + 1} 章）"
            if isinstance(chapter_index, int) and chapter_index >= 0
            else ""
        )
        blocks.append(f"\\subsection{{图表 {index}: {description}{chapter_hint}}}")
        status = figure.get("status")
        if figure.get("file_path"):
            blocks.append(
                "图表已通过执行服务生成，产出路径："
                f"\\texttt{{{_escape_latex(str(figure['file_path']))}}}。"
            )
        else:
            blocks.append(
                "当前以降级模式保存图表源信息，可在 provider 就绪后自动升级为渲染文件。"
            )
        blocks.append(f"当前状态：\\textbf{{{_escape_latex(str(status or 'unknown'))}}}。")

        source = figure.get("source_code") or figure.get("prompt")
        if source:
            blocks.append(r"\begin{lstlisting}")
            blocks.append(str(source)[:1600])
            blocks.append(r"\end{lstlisting}")

    return "\n\n".join(blocks)


def _build_bibtex(literature: list[dict[str, Any]]) -> str:
    if not literature:
        return ""

    entries: list[str] = []
    for idx, item in enumerate(literature[:60], start=1):
        title = str(item.get("title") or f"Reference {idx}").replace("{", "").replace("}", "")
        authors_value = item.get("authors")
        authors_list = (
            [str(author) for author in authors_value if author]
            if isinstance(authors_value, list)
            else []
        )
        authors = " and ".join(authors_list)
        year = str(item.get("year") or "2024")
        venue = str(item.get("venue") or "")
        doi = str(item.get("doi") or "")

        fields = [
            f"  title = {{{title}}}",
            f"  year = {{{year}}}",
        ]
        if authors:
            fields.append(f"  author = {{{authors}}}")
        if venue:
            fields.append(f"  journal = {{{venue}}}")
        if doi:
            fields.append(f"  doi = {{{doi}}}")
        joined_fields = ",\n".join(fields)
        entry = f"@article{{ref{idx},\n{joined_fields}\n}}"
        entries.append(entry)

    return "\n\n".join(entries)


async def build_compile_payload(
    *,
    workspace_id: str,
    workspace_name: str,
    workspace_description: str,
    thread_id: str | None,
    template: str,
    compiler: str,
    bibliography_style: str,
) -> dict[str, Any]:
    """Build compile artifact content with real assembly + compile attempt."""
    artifacts, literature = await asyncio.gather(
        _load_workspace_artifacts(workspace_id),
        _load_workspace_literature(workspace_id),
    )

    outline = _extract_outline_content(artifacts)
    chapters = _extract_sorted_chapters(artifacts)
    if not chapters:
        chapters = _build_outline_fallback_chapters(outline)
    figures = _extract_figures(artifacts)

    paper_title = str(
        outline.get("paper_title")
        or workspace_name
        or "未命名论文"
    )
    abstract_text = str(
        outline.get("abstract")
        or workspace_description
        or f"本文围绕《{paper_title}》展开研究。"
    )

    chapter_latex = [
        _render_markdown_to_latex(chapter.get("markdown", ""))
        for chapter in chapters
    ]
    if not chapter_latex:
        chapter_latex = [
            "\\section{正文占位}\n目前尚无章节产出，请先在论文写作模块生成章节。"
        ]

    figure_latex = _build_figure_latex(figures)
    if figure_latex:
        chapter_latex.append(figure_latex)

    content_body = "\n\n".join(chapter_latex)
    abstract_latex = f"\\begin{{abstract}}\n{_escape_latex(abstract_text)}\n\\end{{abstract}}\n"

    language = resolve_thesis_output_language(template)
    final_latex = get_template(language).format(
        title=_escape_latex(paper_title),
        author="",
        abstract=abstract_latex,
        content=content_body,
        acknowledgements="",
    )
    bib_content = _build_bibtex(literature)

    normalized_compiler = compiler.lower().strip()
    if normalized_compiler not in {"xelatex", "pdflatex"}:
        normalized_compiler = "xelatex"

    compile_result = await compile_latex(
        latex_source=final_latex,
        workspace_id=workspace_id,
        thread_id=thread_id,
        bibliography=bib_content,
        compiler=normalized_compiler,
        bibliography_style=bibliography_style,
        timeout=180,
    )

    compile_status = "success" if compile_result.success else "failed"
    pdf_url = sandbox_path_to_public_url(
        compile_result.pdf_path,
        thread_id=thread_id,
    )
    return {
        "schema_version": THESIS_SCHEMA_VERSION,
        "template": template,
        "output_language": language,
        "compiler": normalized_compiler,
        "bibliography_style": bibliography_style,
        "paper_title": paper_title,
        "latex_content": final_latex,
        "bib_content": bib_content,
        "compile_status": compile_status,
        "pdf_path": compile_result.pdf_path,
        "pdf_url": pdf_url,
        "page_count": compile_result.page_count,
        "compile_error": compile_result.error,
        "compile_logs": _truncate(compile_result.logs or "", max_len=3000),
        "source_summary": {
            "outline_count": 1 if outline else 0,
            "chapter_count": len(chapters),
            "figure_count": len(figures),
            "literature_count": len(literature),
        },
        "generated_at": _utc_now_iso(),
    }


def _normalize_report_type(report_type: str) -> str:
    normalized = (report_type or "").strip().lower()
    if normalized not in _REPORT_TYPES:
        return "opening_report"
    return normalized


def _build_literature_highlights(literature: list[dict[str, Any]], max_items: int = 8) -> list[str]:
    highlights: list[str] = []
    for item in literature[:max_items]:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        year = item.get("year")
        venue = str(item.get("venue") or "").strip()
        year_part = f"（{year}）" if year else ""
        venue_part = f" - {venue}" if venue else ""
        highlights.append(f"{title}{year_part}{venue_part}")
    return highlights


def _build_opening_template_sections(
    *,
    report_type: str,
    topic: str,
    workspace_description: str,
    literature_highlights: list[str],
) -> list[dict[str, str]]:
    if report_type == "literature_review":
        sections = [
            {
                "title": "检索范围与方法",
                "content": (
                    f"围绕“{topic}”设定检索范围，优先覆盖近5年高相关文献；"
                    "使用关键词组合、前向/后向追踪与主题聚类进行筛选。"
                ),
            },
            {
                "title": "代表性研究脉络",
                "content": "从方法路线、数据条件与评价指标三个维度梳理主流研究脉络。",
            },
            {
                "title": "关键文献评述",
                "content": "比较代表性工作的创新点、局限性与可复现性，提炼可借鉴策略。",
            },
            {
                "title": "研究空白与切入点",
                "content": "结合现有成果缺口提出可执行的论文切入点，并说明预期贡献。",
            },
        ]
    elif report_type == "feasibility_analysis":
        sections = [
            {
                "title": "研究目标与约束条件",
                "content": f"研究主题为“{topic}”，需在现有时间、算力和数据条件下完成可验证结论。",
            },
            {
                "title": "技术可行性",
                "content": "评估核心方法的实现复杂度、工程风险和替代技术方案。",
            },
            {
                "title": "资源与数据可行性",
                "content": "确认数据来源、标注成本与实验环境，确保复现实验链路可运行。",
            },
            {
                "title": "计划与风险控制",
                "content": "给出里程碑计划、关键风险清单及相应的降级与兜底方案。",
            },
        ]
    else:
        sections = [
            {
                "title": "研究背景与意义",
                "content": (
                    f"围绕“{topic}”阐述问题背景与研究价值。"
                    f"{workspace_description or '结合所在领域实践需求，明确研究动机。'}"
                ),
            },
            {
                "title": "国内外研究现状",
                "content": "从主流方法、数据基础和评测方式三个方面总结研究现状。",
            },
            {
                "title": "研究目标与主要内容",
                "content": "明确论文研究目标、关键问题定义及章节级研究内容。",
            },
            {
                "title": "技术路线与方法设计",
                "content": "说明从问题建模、方法实现到实验验证的完整技术路线。",
            },
            {
                "title": "创新点与预期成果",
                "content": "提炼可验证创新点并定义预期论文产出与评估指标。",
            },
            {
                "title": "进度安排与风险预案",
                "content": "按阶段给出里程碑计划，并补充关键风险和应对策略。",
            },
        ]

    if literature_highlights:
        sections.append(
            {
                "title": "参考文献线索",
                "content": "核心参考：\n" + "\n".join(f"- {item}" for item in literature_highlights[:6]),
            }
        )
    return sections


def _extract_response_text(response: Any) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                texts.append(item["text"])
        return "\n".join(texts).strip()
    return str(content).strip()


def _parse_json_payload(raw_text: str) -> dict[str, Any] | None:
    if not raw_text:
        return None

    candidates = [raw_text.strip()]

    code_block_match = re.search(r"```json\s*(.*?)\s*```", raw_text, re.DOTALL | re.IGNORECASE)
    if code_block_match:
        candidates.append(code_block_match.group(1).strip())

    first_brace = raw_text.find("{")
    last_brace = raw_text.rfind("}")
    if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
        candidates.append(raw_text[first_brace : last_brace + 1].strip())

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            continue
    return None


def _normalize_llm_sections(
    raw_sections: Any,
    template_sections: list[dict[str, str]],
) -> list[dict[str, str]] | None:
    if not isinstance(raw_sections, list):
        return None

    normalized: list[dict[str, str]] = []
    for index, template_section in enumerate(template_sections):
        candidate = raw_sections[index] if index < len(raw_sections) else None
        if isinstance(candidate, dict):
            candidate_content = str(candidate.get("content") or "").strip()
            if candidate_content:
                normalized.append(
                    {
                        "title": template_section["title"],
                        "content": candidate_content,
                        "source": "llm",
                    }
                )
                continue

        normalized.append(
            {
                "title": template_section["title"],
                "content": template_section["content"],
                "source": "template",
            }
        )

    # If LLM didn't provide meaningful content for any section, treat as invalid.
    if not any(section["source"] == "llm" for section in normalized):
        return None
    return normalized


async def _try_generate_opening_sections(
    *,
    report_type: str,
    topic: str,
    workspace_description: str,
    template_sections: list[dict[str, str]],
    literature_highlights: list[str],
    preferred_model: str | None,
) -> tuple[list[dict[str, str]] | None, str | None, str | None]:
    models = list_user_selectable_models(purpose="writing")
    if not models:
        return None, None, "no_generation_model_configured"

    try:
        model_id = route_writing_model(requested_model=preferred_model)
    except Exception:
        model_id = models[0].id

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except Exception as exc:
        return None, model_id, f"langchain_message_import_failed: {exc}"

    try:
        model = create_chat_model(model_id, temperature=0.3)
    except Exception as exc:
        return None, model_id, f"model_init_failed: {exc}"

    prompt = "\n".join(
        [
            f"请根据主题生成一份{report_type}报告，返回 JSON。",
            f"主题：{topic}",
            f"工作区描述：{workspace_description or '无'}",
            "你必须输出如下结构：",
            '{"sections":[{"title":"章节标题","content":"章节内容"}]}',
            "章节标题必须和以下模板顺序一致：",
            "\n".join(f"- {section['title']}" for section in template_sections),
            "可参考文献线索：",
            "\n".join(f"- {item}" for item in literature_highlights) or "- 无",
            "要求：学术写作风格、内容可直接用于开题材料，避免空话。",
        ]
    )

    try:
        response = await model.ainvoke(
            [
                SystemMessage(content="你是严谨的学术写作助手，只输出 JSON。"),
                HumanMessage(content=prompt),
            ]
        )
    except Exception as exc:
        return None, model_id, f"llm_generation_failed: {exc}"

    parsed = _parse_json_payload(_extract_response_text(response))
    if parsed is None:
        return None, model_id, "llm_output_not_json"

    sections = _normalize_llm_sections(parsed.get("sections"), template_sections)
    if sections is None:
        return None, model_id, "llm_sections_invalid"
    return sections, model_id, None


async def build_opening_report_payload(
    *,
    workspace_id: str,
    workspace_name: str,
    workspace_description: str,
    topic: str,
    report_type: str,
    preferred_model: str | None = None,
) -> dict[str, Any]:
    """Build opening report content with template-first, LLM-optional strategy."""
    normalized_report_type = _normalize_report_type(report_type)
    normalized_topic = (topic or workspace_name or "未命名研究主题").strip()
    if not normalized_topic:
        normalized_topic = "未命名研究主题"

    literature = await _load_workspace_literature(workspace_id)
    literature_highlights = _build_literature_highlights(literature)
    template_sections = _build_opening_template_sections(
        report_type=normalized_report_type,
        topic=normalized_topic,
        workspace_description=workspace_description,
        literature_highlights=literature_highlights,
    )

    llm_sections, model_id, generation_error = await _try_generate_opening_sections(
        report_type=normalized_report_type,
        topic=normalized_topic,
        workspace_description=workspace_description,
        template_sections=template_sections,
        literature_highlights=literature_highlights,
        preferred_model=preferred_model,
    )

    if llm_sections is not None:
        sections = llm_sections
        generation_mode = "llm"
    else:
        sections = [
            {
                "title": section["title"],
                "content": section["content"],
                "source": "template",
            }
            for section in template_sections
        ]
        generation_mode = "template_fallback"

    return {
        "topic": normalized_topic,
        "report_type": normalized_report_type,
        "workspace_description": workspace_description,
        "generation_mode": generation_mode,
        "model_id": model_id,
        "generation_error": generation_error,
        "sections": sections,
        "reference_clues": literature_highlights,
        "literature_count": len(literature),
        "generated_at": _utc_now_iso(),
    }


def _normalize_source_name(source: object) -> str:
    text = str(source or "unknown").strip()
    return text or "unknown"


def _paper_brief(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "title": str(item.get("title") or "未命名文献"),
        "authors": item.get("authors") if isinstance(item.get("authors"), list) else [],
        "year": _coerce_int(item.get("year")),
        "citations": _coerce_int(item.get("citations")) or 0,
        "venue": item.get("venue"),
        "is_core": bool(item.get("is_core")),
        "doi": item.get("doi"),
        "source": _normalize_source_name(item.get("source")),
    }


async def build_literature_management_payload(
    *,
    workspace_id: str,
    workspace_name: str,
    focus_topic: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic literature management report payload."""
    literature = await _load_workspace_literature(workspace_id)
    papers = [_paper_brief(item) for item in literature]

    total = len(papers)
    core_count = sum(1 for item in papers if item["is_core"])
    with_abstract = sum(1 for item in literature if str(item.get("abstract") or "").strip())
    with_doi = sum(1 for item in papers if str(item.get("doi") or "").strip())

    citations = [int(item["citations"]) for item in papers if int(item["citations"]) > 0]
    avg_citations = round(sum(citations) / len(citations), 2) if citations else 0.0

    by_source: dict[str, int] = {}
    by_year: dict[str, int] = {}
    for item in papers:
        source = str(item["source"])
        by_source[source] = by_source.get(source, 0) + 1

        year = item["year"]
        if year:
            key = str(year)
            by_year[key] = by_year.get(key, 0) + 1

    top_cited = sorted(papers, key=lambda x: int(x["citations"]), reverse=True)[:10]
    core_papers = [item for item in papers if item["is_core"]][:10]

    missing_title = [item for item in papers if not str(item.get("title") or "").strip()]
    missing_authors = [item for item in papers if not item["authors"]]
    missing_year = [item for item in papers if not item["year"]]
    missing_abstract = [item for item in literature if not str(item.get("abstract") or "").strip()]
    missing_doi = [item for item in papers if not str(item.get("doi") or "").strip()]

    recommended_actions: list[str] = []
    if total == 0:
        recommended_actions.extend(
            [
                "当前文献库为空，建议先通过 Deep Research 或手动录入补齐基础文献。",
                "至少补充 15 篇高相关文献后再启动论文写作。",
            ]
        )
    if total > 0 and core_count < max(5, int(total * 0.25)):
        recommended_actions.append("核心文献比例偏低，建议将关键奠基论文标记为核心文献。")
    if total > 0 and len(missing_abstract) > int(total * 0.4):
        recommended_actions.append("摘要缺失较多，建议补齐摘要以提升后续自动写作质量。")
    if total > 0 and len(missing_doi) > int(total * 0.5):
        recommended_actions.append("DOI 缺失较多，建议补齐 DOI 便于后续引用管理与查重。")
    if not recommended_actions:
        recommended_actions.append("文献结构完整度较好，可继续推进开题调研与正文写作。")

    return {
        "workspace_id": workspace_id,
        "workspace_name": workspace_name,
        "focus_topic": focus_topic or workspace_name,
        "summary": {
            "total": total,
            "core_count": core_count,
            "with_abstract": with_abstract,
            "with_doi": with_doi,
            "average_citations": avg_citations,
            "by_source": by_source,
            "by_year": by_year,
        },
        "top_cited": top_cited,
        "core_papers": core_papers,
        "quality_check": {
            "missing_title_count": len(missing_title),
            "missing_authors_count": len(missing_authors),
            "missing_year_count": len(missing_year),
            "missing_abstract_count": len(missing_abstract),
            "missing_doi_count": len(missing_doi),
        },
        "recommended_actions": recommended_actions,
        "generated_at": _utc_now_iso(),
    }
