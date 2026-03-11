"""Thesis workflow state definitions."""

from typing import Annotated, Any, NotRequired, TypedDict
from pydantic import BaseModel, Field


class SectionPlan(BaseModel):
    """章节规划"""
    index: int = Field(description="章节序号")
    title: str = Field(description="章节标题")
    purpose: str = Field(default="", description="章节目的")
    key_points: list[str] = Field(default_factory=list, description="关键要点")
    target_words: int = Field(default=2000, description="目标字数")
    dependencies: list[int] = Field(default_factory=list, description="依赖章节")
    literature_needs: list[str] = Field(default_factory=list, description="文献需求")


class SectionContent(BaseModel):
    """章节内容"""
    index: int = Field(description="章节序号")
    title: str = Field(description="章节标题")
    content: str = Field(default="", description="LaTeX 内容")
    word_count: int = Field(default=0, description="实际字数")
    references_used: list[str] = Field(default_factory=list, description="使用的引用 ID")
    status: str = Field(default="pending", description="状态: pending/writing/completed")


class PaperReference(BaseModel):
    """参考文献"""
    id: str = Field(description="引用 ID，如 [1]")
    title: str = Field(description="论文标题")
    authors: list[str] = Field(default_factory=list, description="作者列表")
    year: int | None = Field(default=None, description="发表年份")
    venue: str = Field(default="", description="发表场所")
    doi: str | None = Field(default=None, description="DOI")
    bibtex: str = Field(default="", description="BibTeX 条目")


class FigureRequest(BaseModel):
    """配图需求"""
    id: str = Field(description="图片 ID")
    section_index: int = Field(description="所属章节")
    figure_type: str = Field(description="类型: flowchart/architecture/chart/concept")
    description: str = Field(description="图片描述")
    caption: str = Field(default="", description="图片标题")
    strategy: str = Field(default="", description="生成策略: mermaid/python/kling")


class GeneratedFigure(BaseModel):
    """生成的图片"""
    id: str = Field(description="图片 ID")
    request_id: str = Field(description="对应的需求 ID")
    file_path: str = Field(description="文件路径")
    latex_ref: str = Field(description="LaTeX 引用代码")


def merge_sections(
    left: list[SectionContent] | None,
    right: list[SectionContent] | None,
) -> list[SectionContent]:
    """合并章节列表，按 index 去重，新值覆盖旧值"""
    if not right:
        return left or []
    if not left:
        return right
    result = {s.index: s for s in left}
    result.update({s.index: s for s in right})
    return list(result.values())


def merge_references(
    left: list[dict[str, Any]] | None,
    right: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """合并参考文献列表，按 id 去重"""
    if not right:
        return left or []
    if not left:
        return right
    result = {r["id"]: r for r in left}
    result.update({r["id"]: r for r in right})
    return list(result.values())


def merge_errors(
    left: list[str] | None,
    right: list[str] | None,
) -> list[str]:
    """合并错误列表，追加新错误"""
    return (left or []) + (right or [])


class ThesisWorkflowState(TypedDict):
    """论文生成工作流状态

    此状态用于后台任务（Celery）或 LangGraph 状态机，
    与 ThreadState 分离但通过 workspace_id 关联。
    """
    # === 输入 ===
    workspace_id: str
    thread_id: str
    paper_title: str
    discipline: str
    abstract_content: str
    framework_json: dict[str, Any]  # 来自 framework-designer skill

    # === 规划 ===
    section_plans: list[SectionPlan]
    writing_order: list[int]

    # === 文献 ===
    references: Annotated[list[dict[str, Any]], merge_references]
    citation_plan: dict[int, list[str]]  # section_index -> ref_ids

    # === 写作 ===
    sections: Annotated[list[SectionContent], merge_sections]
    current_section_index: NotRequired[int]

    # === 配图 ===
    figure_requests: list[dict[str, Any]]
    generated_figures: list[dict[str, Any]]

    # === 输出 ===
    final_latex: NotRequired[str]
    pdf_path: NotRequired[str]
    bib_content: NotRequired[str]

    # === 进度 ===
    current_phase: str
    progress: float  # 0.0 - 1.0
    errors: Annotated[list[str], merge_errors]
