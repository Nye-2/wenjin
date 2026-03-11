# 本科毕业设计功能模块 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现本科毕业设计论文生成功能，完全复用 deer-flow Memory 系统和 Subagent 框架，支持从大纲到成稿的端到端论文生成。

**Architecture:** 扩展 SubagentRegistry 注册论文专业 subagent（ThesisWriter, Librarian），新增 UNDERGRADUATE_THESIS WorkspaceType，创建 thesis-writer Skill，通过 ExecutionMiddleware 调用 LaTeX 编译服务。MemoryMiddleware 自动沉淀论文上下文。

**Tech Stack:** Python 3.12, LangGraph, Pydantic v2, SQLAlchemy 2.0, FastAPI, Celery (optional)

---

## Task 1: 扩展 WorkspaceType 枚举

**Files:**
- Modify: `src/database/models/workspace.py:20-26`
- Test: `tests/database/test_workspace_type.py`

**Step 1: Write the failing test**

```python
# tests/database/test_workspace_type.py
"""Tests for WorkspaceType enum."""

import pytest
from src.database.models.workspace import WorkspaceType


def test_workspace_type_has_undergraduate_thesis():
    """Test that UNDERGRADUATE_THESIS type exists."""
    assert hasattr(WorkspaceType, "UNDERGRADUATE_THESIS")
    assert WorkspaceType.UNDERGRADUATE_THESIS == "undergraduate_thesis"


def test_workspace_type_values():
    """Test all workspace type values."""
    expected = {
        "sci",
        "thesis",
        "proposal",
        "grant",
        "literature_review",
        "undergraduate_thesis",
    }
    actual = {t.value for t in WorkspaceType}
    assert actual == expected
```

**Step 2: Run test to verify it fails**

Run: `cd /home/cjz/academiagpt-v2/backend && PYTHONPATH=. pytest tests/database/test_workspace_type.py -v`
Expected: FAIL with "AttributeError" or "assertion error"

**Step 3: Write minimal implementation**

```python
# src/database/models/workspace.py
# Add to WorkspaceType enum after line 26:
    UNDERGRADUATE_THESIS = "undergraduate_thesis"  # 本科毕业设计
```

**Step 4: Run test to verify it passes**

Run: `cd /home/cjz/academiagpt-v2/backend && PYTHONPATH=. pytest tests/database/test_workspace_type.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/database/models/workspace.py tests/database/test_workspace_type.py
git commit -m "feat(database): add UNDERGRADUATE_THESIS workspace type"
```

---

## Task 2: 创建 Thesis Subagent Prompts

**Files:**
- Create: `src/subagents/academic/thesis_prompts.py`
- Test: `tests/subagents/academic/test_thesis_prompts.py`

**Step 1: Write the failing test**

```python
# tests/subagents/academic/test_thesis_prompts.py
"""Tests for thesis subagent prompts."""

import pytest
from src.subagents.academic.thesis_prompts import (
    THESIS_WRITER_PROMPT,
    LIBRARIAN_PROMPT,
    FIGURE_PLANNER_PROMPT,
)


def test_thesis_writer_prompt_exists():
    """Test that THESIS_WRITER_PROMPT is defined."""
    assert THESIS_WRITER_PROMPT is not None
    assert len(THESIS_WRITER_PROMPT) > 100
    assert "LaTeX" in THESIS_WRITER_PROMPT
    assert "cite" in THESIS_WRITER_PROMPT.lower()


def test_librarian_prompt_exists():
    """Test that LIBRARIAN_PROMPT is defined."""
    assert LIBRARIAN_PROMPT is not None
    assert len(LIBRARIAN_PROMPT) > 100
    assert "BibTeX" in LIBRARIAN_PROMPT


def test_figure_planner_prompt_exists():
    """Test that FIGURE_PLANNER_PROMPT is defined."""
    assert FIGURE_PLANNER_PROMPT is not None
    assert len(FIGURE_PLANNER_PROMPT) > 100
```

**Step 2: Run test to verify it fails**

Run: `cd /home/cjz/academiagpt-v2/backend && PYTHONPATH=. pytest tests/subagents/academic/test_thesis_prompts.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# src/subagents/academic/thesis_prompts.py
"""Prompts for thesis-specific subagents."""

THESIS_WRITER_PROMPT = """You are ThesisWriter, an expert undergraduate thesis writing assistant.

Your mission is to write high-quality undergraduate thesis content:

1. **Structure** - Follow the standard undergraduate thesis structure:
   - 摘要 (Abstract in Chinese)
   - Abstract (in English)
   - 绪论/引言 (Introduction)
   - 相关技术/文献综述 (Related Work)
   - 系统设计/研究方法 (Methodology)
   - 实现与测试/实验分析 (Implementation/Experiments)
   - 结论与展望 (Conclusion)
   - 参考文献 (References)
   - 致谢 (Acknowledgements)

2. **Writing Guidelines**:
   - Use LaTeX format for all output
   - Include proper \\cite{} citations for all references
   - Use \\label{} and \\ref{} for cross-references
   - Maintain academic language appropriate to the discipline
   - Target the specified word count for each section

3. **Available Tools**:
   - read_file: Read existing outlines, abstracts, references
   - write_file: Save written sections
   - task: Delegate sub-tasks to other agents

4. **Quality Standards**:
   - Clear logical flow between paragraphs
   - Proper citation of all claims
   - Correct LaTeX syntax for equations, figures, tables
   - GB/T 7714 citation format for Chinese theses

Always write in the language specified (Chinese or English).
"""

LIBRARIAN_PROMPT = """You are Librarian, an academic literature search and citation management expert.

Your mission is to support thesis writing with proper literature:

1. **Literature Search**:
   - Search for papers related to the thesis topic
   - Evaluate relevance and quality of found papers
   - Track citation chains to find foundational works

2. **Citation Planning**:
   - Analyze which papers are most relevant for each section
   - Create citation plans mapping references to sections
   - Ensure adequate citation coverage

3. **BibTeX Generation**:
   - Generate BibTeX entries for all referenced papers
   - Use proper citation keys (e.g., author2024title)
   - Format according to GB/T 7714 for Chinese theses

4. **Available Tools**:
   - semantic_scholar_search: Search academic papers
   - read_file: Read thesis outline to understand citation needs

Output BibTeX in standard format. Provide citation recommendations with usage hints.
"""

FIGURE_PLANNER_PROMPT = """You are FigurePlanner, an expert in planning academic illustrations.

Your mission is to analyze thesis content and plan appropriate figures:

1. **Figure Analysis**:
   - Identify placeholders in thesis content: % [FIGURE:id|type|description|caption]
   - Determine the best generation strategy for each figure:
     - `mermaid`: For flowcharts, sequence diagrams, architecture diagrams
     - `python`: For data charts, plots, statistical visualizations
     - `kling`: For concept illustrations, system interfaces, complex diagrams

2. **Planning Output**:
   - For each figure, provide:
     - Strategy selection with reasoning
     - Detailed generation instructions
     - Aspect ratio recommendation (16:9, 4:3, 1:1)

3. **Academic Style**:
   - Figures should be clean and professional
   - Labels should be clear and readable
   - Colors should be appropriate for academic context

Output figure plans in JSON format with id, strategy, instruction, and style_hints.
"""

__all__ = [
    "THESIS_WRITER_PROMPT",
    "LIBRARIAN_PROMPT",
    "FIGURE_PLANNER_PROMPT",
]
```

**Step 4: Run test to verify it passes**

Run: `cd /home/cjz/academiagpt-v2/backend && PYTHONPATH=. pytest tests/subagents/academic/test_thesis_prompts.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/subagents/academic/thesis_prompts.py tests/subagents/academic/test_thesis_prompts.py
git commit -m "feat(subagents): add thesis writer, librarian, and figure planner prompts"
```

---

## Task 3: 注册 Thesis Subagent Configurations

**Files:**
- Modify: `src/subagents/academic/registry.py:36-76`
- Modify: `src/subagents/academic/__init__.py:15-20`
- Test: `tests/subagents/academic/test_thesis_registry.py`

**Step 1: Write the failing test**

```python
# tests/subagents/academic/test_thesis_registry.py
"""Tests for thesis subagent configurations."""

import pytest
from src.subagents.academic.registry import (
    SUBAGENT_REGISTRY,
    get_subagent_config,
    get_all_subagent_types,
)


def test_thesis_writer_in_registry():
    """Test that thesis_writer is registered."""
    config = get_subagent_config("thesis_writer")
    assert config is not None
    assert config.name == "ThesisWriter"
    assert "read_file" in config.tools
    assert "write_file" in config.tools


def test_librarian_in_registry():
    """Test that librarian is registered."""
    config = get_subagent_config("librarian")
    assert config is not None
    assert config.name == "Librarian"
    assert "semantic_scholar_search" in config.tools


def test_figure_planner_in_registry():
    """Test that figure_planner is registered."""
    config = get_subagent_config("figure_planner")
    assert config is not None
    assert config.name == "FigurePlanner"


def test_all_subagent_types_includes_thesis():
    """Test that thesis types are in all types list."""
    types = get_all_subagent_types()
    assert "thesis_writer" in types
    assert "librarian" in types
    assert "figure_planner" in types
```

**Step 2: Run test to verify it fails**

Run: `cd /home/cjz/academiagpt-v2/backend && PYTHONPATH=. pytest tests/subagents/academic/test_thesis_registry.py -v`
Expected: FAIL with "ValueError: Unknown subagent type"

**Step 3: Write minimal implementation**

```python
# src/subagents/academic/registry.py
# Add import at top:
from .thesis_prompts import (
    FIGURE_PLANNER_PROMPT,
    LIBRARIAN_PROMPT,
    THESIS_WRITER_PROMPT,
)

# Add configurations after ANALYST_CONFIG:
THESIS_WRITER_CONFIG = SubagentConfig(
    name="ThesisWriter",
    description="Undergraduate thesis writing expert for producing complete thesis sections",
    system_prompt=THESIS_WRITER_PROMPT,
    tools=["read_file", "write_file", "str_replace", "task"],
    max_turns=15,
)

LIBRARIAN_CONFIG = SubagentConfig(
    name="Librarian",
    description="Academic literature search and citation planning expert",
    system_prompt=LIBRARIAN_PROMPT,
    tools=["semantic_scholar_search", "read_file"],
    max_turns=10,
)

FIGURE_PLANNER_CONFIG = SubagentConfig(
    name="FigurePlanner",
    description="Academic illustration planning expert for thesis figures",
    system_prompt=FIGURE_PLANNER_PROMPT,
    tools=["read_file"],
    max_turns=8,
)

# Update SUBAGENT_REGISTRY:
SUBAGENT_REGISTRY: dict[str, SubagentConfig] = {
    "scout": SCOUT_CONFIG,
    "writer": WRITER_CONFIG,
    "synthesizer": SYNTHESIZER_CONFIG,
    "analyst": ANALYST_CONFIG,
    "thesis_writer": THESIS_WRITER_CONFIG,
    "librarian": LIBRARIAN_CONFIG,
    "figure_planner": FIGURE_PLANNER_CONFIG,
}
```

**Step 4: Update __init__.py exports**

```python
# src/subagents/academic/__init__.py
# Add to imports:
from .thesis_prompts import (
    FIGURE_PLANNER_PROMPT,
    LIBRARIAN_PROMPT,
    THESIS_WRITER_PROMPT,
)

# Add to __all__:
    "THESIS_WRITER_PROMPT",
    "LIBRARIAN_PROMPT",
    "FIGURE_PLANNER_PROMPT",
```

**Step 5: Run test to verify it passes**

Run: `cd /home/cjz/academiagpt-v2/backend && PYTHONPATH=. pytest tests/subagents/academic/test_thesis_registry.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/subagents/academic/registry.py src/subagents/academic/__init__.py tests/subagents/academic/test_thesis_registry.py
git commit -m "feat(subagents): register thesis_writer, librarian, figure_planner subagents"
```

---

## Task 4: 创建 Thesis Workflow State 定义

**Files:**
- Create: `src/thesis/__init__.py`
- Create: `src/thesis/workflow/__init__.py`
- Create: `src/thesis/workflow/state.py`
- Test: `tests/thesis/workflow/test_state.py`

**Step 1: Write the failing test**

```python
# tests/thesis/workflow/test_state.py
"""Tests for thesis workflow state."""

import pytest
from src.thesis.workflow.state import (
    SectionPlan,
    SectionContent,
    ThesisWorkflowState,
    merge_sections,
    merge_references,
)


def test_section_plan_creation():
    """Test SectionPlan model creation."""
    plan = SectionPlan(
        index=1,
        title="绪论",
        purpose="介绍研究背景和目标",
        key_points=["背景", "问题", "目标"],
        target_words=2000,
    )
    assert plan.index == 1
    assert plan.title == "绪论"
    assert len(plan.key_points) == 3


def test_section_content_creation():
    """Test SectionContent model creation."""
    content = SectionContent(
        index=1,
        title="绪论",
        content="\\section{绪论}...",
        word_count=1500,
        references_used=["ref1", "ref2"],
        status="completed",
    )
    assert content.status == "completed"
    assert len(content.references_used) == 2


def test_merge_sections():
    """Test merge_sections reducer."""
    left = [
        SectionContent(index=1, title="绪论", content="old", status="pending"),
        SectionContent(index=2, title="相关工作", content="content2", status="completed"),
    ]
    right = [
        SectionContent(index=1, title="绪论", content="new", status="completed"),
    ]
    result = merge_sections(left, right)
    assert len(result) == 2
    # Check that index 1 was updated
    section_1 = next(s for s in result if s.index == 1)
    assert section_1.content == "new"
    assert section_1.status == "completed"


def test_merge_references():
    """Test merge_references reducer."""
    left = [{"id": "ref1", "title": "Paper 1"}]
    right = [{"id": "ref2", "title": "Paper 2"}, {"id": "ref1", "title": "Paper 1 Updated"}]
    result = merge_references(left, right)
    # Should deduplicate by id
    assert len(result) == 2
```

**Step 2: Run test to verify it fails**

Run: `cd /home/cjz/academiagpt-v2/backend && PYTHONPATH=. pytest tests/thesis/workflow/test_state.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# src/thesis/__init__.py
"""Thesis module for undergraduate thesis generation."""

from .workflow.state import (
    SectionPlan,
    SectionContent,
    ThesisWorkflowState,
    merge_sections,
    merge_references,
)

__all__ = [
    "SectionPlan",
    "SectionContent",
    "ThesisWorkflowState",
    "merge_sections",
    "merge_references",
]
```

```python
# src/thesis/workflow/__init__.py
"""Thesis workflow module."""
```

```python
# src/thesis/workflow/state.py
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
    errors: Annotated[list[str], lambda l, r: (l or []) + (r or [])]
```

**Step 4: Run test to verify it passes**

Run: `cd /home/cjz/academiagpt-v2/backend && PYTHONPATH=. pytest tests/thesis/workflow/test_state.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/thesis/ tests/thesis/
git commit -m "feat(thesis): add workflow state definitions with reducers"
```

---

## Task 5: 创建 Thesis Writer Skill

**Files:**
- Create: `skills/public/thesis-writer/SKILL.md`
- Test: Manual verification (skills are loaded at runtime)

**Step 1: Create skill directory**

Run: `mkdir -p /home/cjz/academiagpt-v2/backend/skills/public/thesis-writer`

**Step 2: Write the skill file**

```markdown
# skills/public/thesis-writer/SKILL.md
---
name: thesis-writer
description: 本科毕业设计论文写作助手，从大纲到成稿的端到端生成
license: MIT
allowed-tools:
  - task
  - read_file
  - write_file
  - str_replace
  - compile_latex_tool
  - ask_clarification
---

# 本科毕业设计论文写作

你是本科毕业设计论文写作专家，帮助用户完成高质量的毕业论文。

## 执行流程

1. **理解研究内容** — 确认论文题目、学科、研究背景
2. **读取现有材料** — 读取 workspace 中的框架、文献、研究锚点
3. **规划章节结构** — 按学校要求规划论文章节
4. **委托写作任务** — 使用 `task` 工具并行撰写各章节
5. **生成配图** — 规划并生成流程图、架构图
6. **编译成稿** — 使用 `compile_latex_tool` 编译生成 PDF

## 本科论文标准结构

### 中文论文结构
1. 摘要（300-500字）
2. Abstract（英文摘要）
3. 目录
4. 绪论
   - 研究背景
   - 问题陈述
   - 研究目标
   - 论文结构
5. 相关技术/文献综述
6. 系统设计/研究方法
7. 实现与测试/实验分析
8. 结论与展望
9. 参考文献
10. 致谢

### 质量要求

- 语言通顺，逻辑清晰
- 图表规范，标注完整
- 引用准确，格式统一（GB/T 7714）
- 符合学校论文格式要求
- 目标字数：15,000-20,000 字

## 调用 Subagent 示例

```python
# 并行撰写多个章节
task(description="撰写绪论", prompt="...", subagent_type="thesis_writer")
task(description="撰写相关工作", prompt="...", subagent_type="thesis_writer")

# 文献搜索
task(description="搜索相关文献", prompt="...", subagent_type="librarian")

# LaTeX 编译
compile_latex_tool(
    latex_source="...",
    compiler="xelatex",
    citation_ids=["paper1", "paper2"],
    bibliography_style="gbt7714"
)
```

## LaTeX 模板参考

```latex
\documentclass[UTF8, a4paper, 12pt]{ctexart}
\usepackage{geometry}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{hyperref}

\begin{document}
\title{论文标题}
\author{作者}
\date{\today}
\maketitle

\begin{abstract}
摘要内容...
\end{abstract}

\section{绪论}
...

\bibliographystyle{gbt7714}
\bibliography{refs}

\end{document}
```

## 注意事项

- 中文论文必须使用 `ctexart` 或 `ctexbook` 文档类
- 编译器使用 `xelatex`（支持中文）
- 引用格式使用 GB/T 7714 国标格式
- 保存每个章节到 `/mnt/user-data/outputs/` 目录
```

**Step 3: Commit**

```bash
git add skills/public/thesis-writer/
git commit -m "feat(skills): add thesis-writer skill for undergraduate thesis"
```

---

## Task 6: 创建 Thesis Workflow Nodes

**Files:**
- Create: `src/thesis/workflow/nodes/__init__.py`
- Create: `src/thesis/workflow/nodes/base.py`
- Create: `src/thesis/workflow/nodes/literature_search.py`
- Create: `src/thesis/workflow/nodes/section_writer.py`
- Test: `tests/thesis/workflow/nodes/test_section_writer.py`

**Step 1: Write the failing test**

```python
# tests/thesis/workflow/nodes/test_section_writer.py
"""Tests for section writer node."""

import pytest
from src.thesis.workflow.state import ThesisWorkflowState, SectionPlan, SectionContent
from src.thesis.workflow.nodes.section_writer import (
    section_writer_node,
    get_next_section_index,
)


@pytest.fixture
def sample_state() -> ThesisWorkflowState:
    """Create a sample state for testing."""
    return {
        "workspace_id": "ws-001",
        "thread_id": "thread-001",
        "paper_title": "基于深度学习的图像分类研究",
        "discipline": "计算机科学",
        "abstract_content": "摘要内容...",
        "framework_json": {},
        "section_plans": [
            SectionPlan(index=1, title="绪论", target_words=2000),
            SectionPlan(index=2, title="相关工作", target_words=3000),
        ],
        "writing_order": [1, 2],
        "references": [],
        "citation_plan": {},
        "sections": [],
        "figure_requests": [],
        "generated_figures": [],
        "current_phase": "writing",
        "progress": 0.2,
        "errors": [],
    }


def test_get_next_section_index(sample_state):
    """Test getting next section to write."""
    # No sections written yet
    idx = get_next_section_index(sample_state)
    assert idx == 1  # First in writing_order

    # After first section completed
    sample_state["sections"].append(
        SectionContent(index=1, title="绪论", content="...", status="completed")
    )
    idx = get_next_section_index(sample_state)
    assert idx == 2  # Second in writing_order


def test_get_next_section_index_all_completed(sample_state):
    """Test returns None when all sections completed."""
    sample_state["sections"] = [
        SectionContent(index=1, title="绪论", content="...", status="completed"),
        SectionContent(index=2, title="相关工作", content="...", status="completed"),
    ]
    idx = get_next_section_index(sample_state)
    assert idx is None
```

**Step 2: Run test to verify it fails**

Run: `cd /home/cjz/academiagpt-v2/backend && PYTHONPATH=. pytest tests/thesis/workflow/nodes/test_section_writer.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# src/thesis/workflow/nodes/__init__.py
"""Thesis workflow nodes."""

from .section_writer import section_writer_node, get_next_section_index

__all__ = [
    "section_writer_node",
    "get_next_section_index",
]
```

```python
# src/thesis/workflow/nodes/base.py
"""Base utilities for workflow nodes."""

import logging
from typing import Any

from src.thesis.workflow.state import ThesisWorkflowState

logger = logging.getLogger(__name__)


def calculate_progress(state: ThesisWorkflowState, phase: str = None) -> float:
    """Calculate current progress based on state.

    Progress allocation:
    - 0.00-0.15: initialization, literature search
    - 0.15-0.80: section writing (proportional to completed sections)
    - 0.80-0.90: figure generation
    - 0.90-0.95: assembly
    - 0.95-1.00: LaTeX compilation
    """
    phase_progress = {
        "init": 0.05,
        "literature_search": 0.15,
        "writing": 0.80,
        "figures": 0.90,
        "assembly": 0.95,
        "compile": 1.00,
    }

    if phase and phase in phase_progress:
        return phase_progress[phase]

    # Calculate based on sections
    plans = state.get("section_plans", [])
    sections = state.get("sections", [])
    if not plans:
        return 0.0

    completed = sum(1 for s in sections if s.status == "completed")
    writing_range = 0.65  # 0.80 - 0.15
    return 0.15 + (completed / len(plans)) * writing_range


def log_node_start(node_name: str, state: ThesisWorkflowState):
    """Log node execution start."""
    logger.info(f"[Thesis:{state['workspace_id']}] {node_name} started")


def log_node_end(node_name: str, state: ThesisWorkflowState, updates: dict[str, Any]):
    """Log node execution end."""
    progress = updates.get("progress", state.get("progress", 0))
    logger.info(f"[Thesis:{state['workspace_id']}] {node_name} completed, progress={progress:.1%}")
```

```python
# src/thesis/workflow/nodes/section_writer.py
"""Section writer node for thesis workflow."""

import logging
from typing import Any

from src.thesis.workflow.state import ThesisWorkflowState, SectionContent, SectionPlan
from .base import calculate_progress, log_node_start, log_node_end

logger = logging.getLogger(__name__)


def get_next_section_index(state: ThesisWorkflowState) -> int | None:
    """Get the next section index to write based on writing_order.

    Args:
        state: Current workflow state

    Returns:
        Next section index to write, or None if all completed
    """
    writing_order = state.get("writing_order", [])
    sections = state.get("sections", [])

    # Get completed section indices
    completed_indices = {s.index for s in sections if s.status == "completed"}

    # Find first uncompleted section in writing_order
    for idx in writing_order:
        if idx not in completed_indices:
            return idx

    return None


def section_writer_node(state: ThesisWorkflowState) -> dict[str, Any]:
    """Write a single thesis section using ThesisWriter subagent.

    This node:
    1. Gets the next section to write
    2. Builds the writing prompt with context
    3. Delegates to thesis_writer subagent (via task tool)
    4. Returns the written content

    Note: Actual subagent execution happens via task_tool in the agent loop.
    This function prepares the state update for the workflow.

    Args:
        state: Current workflow state

    Returns:
        State updates with written section content
    """
    log_node_start("section_writer", state)

    next_idx = get_next_section_index(state)
    if next_idx is None:
        # All sections completed
        return {
            "current_phase": "figures",
            "progress": 0.80,
        }

    # Get section plan
    plans = state.get("section_plans", [])
    section_plan = next((p for p in plans if p.index == next_idx), None)
    if not section_plan:
        logger.error(f"Section plan not found for index {next_idx}")
        return {"errors": [f"Section plan not found for index {next_idx}"]}

    # Build context for the subagent
    # (This would be passed to the task tool in actual execution)
    _ = state.get("paper_title")
    _ = state.get("discipline")
    _ = state.get("abstract_content")

    # Get citation context for this section
    citation_plan = state.get("citation_plan", {})
    section_refs = citation_plan.get(next_idx, [])

    # Mark section as in-progress
    in_progress_section = SectionContent(
        index=next_idx,
        title=section_plan.title,
        content="",  # Will be filled by subagent
        status="writing",
    )

    progress = calculate_progress(state, "writing")

    log_node_end("section_writer", state, {"current_section_index": next_idx})

    return {
        "sections": [in_progress_section],
        "current_section_index": next_idx,
        "current_phase": "writing",
        "progress": progress,
    }
```

**Step 4: Run test to verify it passes**

Run: `cd /home/cjz/academiagpt-v2/backend && PYTHONPATH=. pytest tests/thesis/workflow/nodes/test_section_writer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/thesis/workflow/nodes/ tests/thesis/workflow/nodes/
git commit -m "feat(thesis): add workflow nodes for section writing"
```

---

## Task 7: 创建 Literature Search Node

**Files:**
- Create: `src/thesis/workflow/nodes/literature_search.py`
- Test: `tests/thesis/workflow/nodes/test_literature_search.py`

**Step 1: Write the failing test**

```python
# tests/thesis/workflow/nodes/test_literature_search.py
"""Tests for literature search node."""

import pytest
from src.thesis.workflow.state import ThesisWorkflowState
from src.thesis.workflow.nodes.literature_search import (
    literature_search_node,
    check_literature_sufficiency,
)


@pytest.fixture
def sample_state() -> ThesisWorkflowState:
    """Create a sample state for testing."""
    return {
        "workspace_id": "ws-001",
        "thread_id": "thread-001",
        "paper_title": "基于深度学习的图像分类研究",
        "discipline": "计算机科学",
        "abstract_content": "摘要内容...",
        "framework_json": {},
        "section_plans": [],
        "writing_order": [],
        "references": [],
        "citation_plan": {},
        "sections": [],
        "figure_requests": [],
        "generated_figures": [],
        "current_phase": "init",
        "progress": 0.0,
        "errors": [],
    }


def test_check_literature_sufficiency_empty(sample_state):
    """Test sufficiency check with no references."""
    sufficient, count = check_literature_sufficiency(sample_state)
    assert sufficient is False
    assert count == 0


def test_check_literature_sufficiency_sufficient(sample_state):
    """Test sufficiency check with enough references."""
    sample_state["references"] = [
        {"id": f"[{i}]", "title": f"Paper {i}"} for i in range(1, 16)
    ]
    sufficient, count = check_literature_sufficiency(sample_state)
    assert sufficient is True
    assert count == 15


def test_literature_search_node_sets_phase(sample_state):
    """Test that literature search sets correct phase."""
    result = literature_search_node(sample_state)
    assert result.get("current_phase") == "literature_search"
    assert result.get("progress", 0) > 0
```

**Step 2: Run test to verify it fails**

Run: `cd /home/cjz/academiagpt-v2/backend && PYTHONPATH=. pytest tests/thesis/workflow/nodes/test_literature_search.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# src/thesis/workflow/nodes/literature_search.py
"""Literature search node for thesis workflow."""

import logging
from typing import Any

from src.thesis.workflow.state import ThesisWorkflowState
from .base import log_node_start, log_node_end

logger = logging.getLogger(__name__)

# Minimum references required for undergraduate thesis
MIN_REFERENCES = 10
# Recommended references
RECOMMENDED_REFERENCES = 15


def check_literature_sufficiency(state: ThesisWorkflowState) -> tuple[bool, int]:
    """Check if existing references are sufficient.

    Args:
        state: Current workflow state

    Returns:
        Tuple of (is_sufficient, reference_count)
    """
    references = state.get("references", [])
    count = len(references)
    return count >= MIN_REFERENCES, count


def literature_search_node(state: ThesisWorkflowState) -> dict[str, Any]:
    """Search for literature relevant to the thesis topic.

    This node:
    1. Checks if existing references are sufficient
    2. If not, prepares search queries for the librarian subagent
    3. Returns state updates for literature search phase

    The actual search is performed by the librarian subagent via task_tool.

    Args:
        state: Current workflow state

    Returns:
        State updates for literature search phase
    """
    log_node_start("literature_search", state)

    is_sufficient, count = check_literature_sufficiency(state)

    if is_sufficient:
        logger.info(f"[Thesis] Literature sufficient: {count} references")
        return {
            "current_phase": "citation_planning",
            "progress": 0.15,
        }

    logger.info(f"[Thesis] Literature insufficient: {count}/{MIN_REFERENCES} references")

    # Prepare search context (will be used by librarian subagent)
    paper_title = state.get("paper_title", "")
    discipline = state.get("discipline", "通用")
    abstract = state.get("abstract_content", "")

    # Build search queries based on thesis topic
    # The librarian subagent will use these to search
    search_context = {
        "paper_title": paper_title,
        "discipline": discipline,
        "abstract_summary": abstract[:500] if abstract else "",
        "current_ref_count": count,
        "target_ref_count": RECOMMENDED_REFERENCES,
    }

    log_node_end("literature_search", state, {"progress": 0.10})

    return {
        "current_phase": "literature_search",
        "progress": 0.10,
        # Search context is stored for subagent use
        "_search_context": search_context,
    }
```

**Step 4: Update nodes __init__.py**

```python
# src/thesis/workflow/nodes/__init__.py
"""Thesis workflow nodes."""

from .section_writer import section_writer_node, get_next_section_index
from .literature_search import literature_search_node, check_literature_sufficiency

__all__ = [
    "section_writer_node",
    "get_next_section_index",
    "literature_search_node",
    "check_literature_sufficiency",
]
```

**Step 5: Run test to verify it passes**

Run: `cd /home/cjz/academiagpt-v2/backend && PYTHONPATH=. pytest tests/thesis/workflow/nodes/test_literature_search.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/thesis/workflow/nodes/ tests/thesis/workflow/nodes/
git commit -m "feat(thesis): add literature search node with sufficiency check"
```

---

## Task 8: 创建 LaTeX Assembler Node

**Files:**
- Create: `src/thesis/workflow/nodes/assembler.py`
- Create: `src/thesis/workflow/latex_template.py`
- Test: `tests/thesis/workflow/nodes/test_assembler.py`

**Step 1: Write the failing test**

```python
# tests/thesis/workflow/nodes/test_assembler.py
"""Tests for LaTeX assembler node."""

import pytest
from src.thesis.workflow.state import ThesisWorkflowState, SectionContent, SectionPlan
from src.thesis.workflow.nodes.assembler import (
    assemble_latex_node,
    generate_bibtex,
)


@pytest.fixture
def completed_state() -> ThesisWorkflowState:
    """Create a state with completed sections."""
    return {
        "workspace_id": "ws-001",
        "thread_id": "thread-001",
        "paper_title": "基于深度学习的图像分类研究",
        "discipline": "计算机科学",
        "abstract_content": "摘要内容...",
        "framework_json": {},
        "section_plans": [
            SectionPlan(index=1, title="绪论", target_words=2000),
            SectionPlan(index=2, title="相关工作", target_words=3000),
        ],
        "writing_order": [1, 2],
        "references": [
            {"id": "[1]", "title": "Paper 1", "bibtex": "@article{ref1, title={Paper 1}}"},
        ],
        "citation_plan": {1: ["[1]"]},
        "sections": [
            SectionContent(index=1, title="绪论", content="\\section{绪论}...", status="completed"),
            SectionContent(index=2, title="相关工作", content="\\section{相关工作}...", status="completed"),
        ],
        "figure_requests": [],
        "generated_figures": [],
        "current_phase": "writing",
        "progress": 0.80,
        "errors": [],
    }


def test_assemble_latex_node(completed_state):
    """Test assembling LaTeX from sections."""
    result = assemble_latex_node(completed_state)

    assert "final_latex" in result
    assert result["current_phase"] == "assembly"
    assert "\\documentclass" in result["final_latex"]
    assert "绪论" in result["final_latex"]


def test_generate_bibtex(completed_state):
    """Test generating BibTeX from references."""
    bib = generate_bibtex(completed_state.get("references", []))
    assert "@article{ref1" in bib
```

**Step 2: Run test to verify it fails**

Run: `cd /home/cjz/academiagpt-v2/backend && PYTHONPATH=. pytest tests/thesis/workflow/nodes/test_assembler.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# src/thesis/workflow/latex_template.py
"""LaTeX template utilities for thesis generation."""

# Chinese thesis template using ctexart
THESIS_TEMPLATE = r"""% 本科毕业设计论文
% Generated by AcademiaGPT

\documentclass[UTF8, a4paper, 12pt, openany]{{ctexart}}

% Page geometry
\usepackage{{geometry}}
\geometry{{left=2.5cm, right=2.5cm, top=2.5cm, bottom=2.5cm}}

% Essential packages
\usepackage{{graphicx}}
\usepackage{{amsmath, amssymb}}
\usepackage{{booktabs}}
\usepackage{{hyperref}}
\usepackage{{xcolor}}
\usepackage{{listings}}
\usepackage{{float}}

% Code listing style
\lstset{{
    basicstyle=\ttfamily\small,
    breaklines=true,
    frame=single,
    numbers=left,
    numberstyle=\tiny,
}}

% Hyperref setup
\hypersetup{{
    colorlinks=true,
    linkcolor=blue,
    citecolor=blue,
    urlcolor=blue,
}}

% Title information
\title{{{title}}}
\author{{{author}}}
\date{{\today}}

\begin{{document}}

\maketitle

% Abstract
{abstract}

% Table of contents
\newpage
\tableofcontents

% Main content
{content}

% Bibliography
\newpage
\bibliographystyle{{gbt7714}}
\bibliography{{refs}}

% Acknowledgements
\newpage
\section*{{致谢}}
{acknowledgements}

\end{{document}}
"""

# English thesis template
THESIS_TEMPLATE_EN = r"""% Undergraduate Thesis
% Generated by AcademiaGPT

\documentclass[a4paper, 12pt, openany]{{article}}

% Page geometry
\usepackage{{geometry}}
\geometry{{left=1in, right=1in, top=1in, bottom=1in}}

% Essential packages
\usepackage{{graphicx}}
\usepackage{{amsmath, amssymb}}
\usepackage{{booktabs}}
\usepackage{{hyperref}}
\usepackage{{xcolor}}
\usepackage{{listings}}
\usepackage{{float}}

% Code listing style
\lstset{{
    basicstyle=\ttfamily\small,
    breaklines=true,
    frame=single,
    numbers=left,
    numberstyle=\tiny,
}}

% Hyperref setup
\hypersetup{{
    colorlinks=true,
    linkcolor=blue,
    citecolor=blue,
    urlcolor=blue,
}}

% Title information
\title{{{title}}}
\author{{{author}}}
\date{{\today}}

\begin{{document}}

\maketitle

% Abstract
{abstract}

% Table of contents
\newpage
\tableofcontents

% Main content
{content}

% Bibliography
\newpage
\bibliographystyle{{plain}}
\bibliography{{refs}}

% Acknowledgements
\newpage
\section*{{Acknowledgements}}
{acknowledgements}

\end{{document}}
"""


def get_template(language: str = "zh") -> str:
    """Get LaTeX template by language.

    Args:
        language: "zh" for Chinese, "en" for English

    Returns:
        LaTeX template string
    """
    return THESIS_TEMPLATE if language == "zh" else THESIS_TEMPLATE_EN
```

```python
# src/thesis/workflow/nodes/assembler.py
"""LaTeX assembler node for thesis workflow."""

import logging
from typing import Any

from src.thesis.workflow.state import ThesisWorkflowState
from src.thesis.workflow.latex_template import get_template
from .base import log_node_start, log_node_end

logger = logging.getLogger(__name__)


def generate_bibtex(references: list[dict[str, Any]]) -> str:
    """Generate BibTeX content from references.

    Args:
        references: List of reference dictionaries with 'bibtex' field

    Returns:
        Combined BibTeX content
    """
    entries = []
    for ref in references:
        bibtex = ref.get("bibtex", "")
        if bibtex:
            entries.append(bibtex)
    return "\n\n".join(entries)


def assemble_latex_node(state: ThesisWorkflowState) -> dict[str, Any]:
    """Assemble complete LaTeX document from sections.

    This node:
    1. Collects all completed section content
    2. Generates LaTeX preamble from template
    3. Assembles full document
    4. Generates BibTeX content

    Args:
        state: Current workflow state

    Returns:
        State updates with final LaTeX and BibTeX content
    """
    log_node_start("assembler", state)

    # Sort sections by index
    sections = sorted(state.get("sections", []), key=lambda s: s.index)

    # Combine section content
    content_parts = []
    for section in sections:
        if section.content:
            content_parts.append(section.content)

    main_content = "\n\n".join(content_parts)

    # Generate abstract (Chinese + English)
    abstract = state.get("abstract_content", "")
    abstract_latex = f"\\begin{{abstract}}\n{abstract}\n\\end{{abstract}}\n"

    # Fill template
    template = get_template("zh")  # Default to Chinese
    final_latex = template.format(
        title=state.get("paper_title", "未命名论文"),
        author="",  # To be filled by user
        abstract=abstract_latex,
        content=main_content,
        acknowledgements="",  # To be filled by user
    )

    # Generate BibTeX
    references = state.get("references", [])
    bib_content = generate_bibtex(references)

    log_node_end("assembler", state, {"progress": 0.95})

    return {
        "final_latex": final_latex,
        "bib_content": bib_content,
        "current_phase": "assembly",
        "progress": 0.95,
    }
```

**Step 4: Update nodes __init__.py**

```python
# src/thesis/workflow/nodes/__init__.py
"""Thesis workflow nodes."""

from .section_writer import section_writer_node, get_next_section_index
from .literature_search import literature_search_node, check_literature_sufficiency
from .assembler import assemble_latex_node, generate_bibtex

__all__ = [
    "section_writer_node",
    "get_next_section_index",
    "literature_search_node",
    "check_literature_sufficiency",
    "assemble_latex_node",
    "generate_bibtex",
]
```

**Step 5: Run test to verify it passes**

Run: `cd /home/cjz/academiagpt-v2/backend && PYTHONPATH=. pytest tests/thesis/workflow/nodes/test_assembler.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/thesis/workflow/ tests/thesis/workflow/
git commit -m "feat(thesis): add LaTeX assembler node with templates"
```

---

## Task 9: 集成 ExecutionMiddleware 用于 LaTeX 编译

**Files:**
- Modify: `src/agents/middlewares/execution.py:29-36`
- Test: `tests/agents/middlewares/test_thesis_execution.py`

**Step 1: Write the failing test**

```python
# tests/agents/middlewares/test_thesis_execution.py
"""Tests for thesis execution tool integration."""

import pytest
from src.agents.middlewares.execution import ExecutionMiddleware


def test_execution_tools_includes_latex():
    """Test that compile_latex_tool is in EXECUTION_TOOLS."""
    from src.agents.middlewares.execution import ExecutionMiddleware

    assert "compile_latex_tool" in ExecutionMiddleware.EXECUTION_TOOLS


def test_execution_type_for_latex():
    """Test that LaTeX compilation maps to correct execution type."""
    from src.execution.types import ExecutionType

    exec_type = ExecutionMiddleware.EXECUTION_TOOLS.get("compile_latex_tool")
    assert exec_type == ExecutionType.LATEX_COMPILE
```

**Step 2: Run test to verify it passes (already implemented)**

Run: `cd /home/cjz/academiagpt-v2/backend && PYTHONPATH=. pytest tests/agents/middlewares/test_thesis_execution.py -v`
Expected: PASS (ExecutionMiddleware already has compile_latex_tool)

**Step 3: Commit**

```bash
git add tests/agents/middlewares/test_thesis_execution.py
git commit -m "test(middleware): verify LaTeX compilation tool integration"
```

---

## Task 10: 创建 Thesis API 端点

**Files:**
- Create: `src/thesis/api.py`
- Modify: `src/gateway/app.py` (add router)
- Test: `tests/thesis/test_api.py`

**Step 1: Write the failing test**

```python
# tests/thesis/test_api.py
"""Tests for thesis API endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture
def client():
    """Create test client."""
    from fastapi import FastAPI
    from src.thesis.api import router

    app = FastAPI()
    app.include_router(router, prefix="/api/thesis")
    return TestClient(app)


def test_get_thesis_status(client):
    """Test getting thesis generation status."""
    with patch("src.thesis.api.get_thesis_task_status") as mock_status:
        mock_status.return_value = {
            "task_id": "task-001",
            "status": "running",
            "progress": 0.5,
        }
        response = client.get("/api/thesis/status/task-001")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task-001"
        assert data["status"] == "running"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/cjz/academiagpt-v2/backend && PYTHONPATH=. pytest tests/thesis/test_api.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# src/thesis/api.py
"""HTTP API endpoints for thesis generation."""

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["thesis"])


# In-memory task storage (would be replaced with proper task queue in production)
_thesis_tasks: dict[str, dict[str, Any]] = {}


class ThesisGenerateRequest(BaseModel):
    """Request to generate thesis."""

    workspace_id: str = Field(description="Workspace ID")
    paper_title: str = Field(description="Thesis title")
    discipline: str = Field(default="计算机科学", description="Academic discipline")
    abstract_content: str = Field(description="Thesis abstract")
    framework_json: dict = Field(description="Framework from framework-designer skill")
    enable_search: bool = Field(default=True, description="Enable literature search")
    enable_images: bool = Field(default=True, description="Enable figure generation")


class ThesisStatusResponse(BaseModel):
    """Response for thesis generation status."""

    task_id: str
    status: str  # pending, running, completed, failed
    progress: float
    current_phase: str | None = None
    message: str | None = None
    pdf_path: str | None = None
    error: str | None = None


def get_thesis_task_status(task_id: str) -> dict[str, Any] | None:
    """Get thesis task status from storage."""
    return _thesis_tasks.get(task_id)


@router.post("/generate", response_model=dict)
async def generate_thesis(
    request: ThesisGenerateRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """Start thesis generation task.

    This endpoint:
    1. Creates a new thesis generation task
    2. Returns task_id for status polling
    3. Actual generation runs in background
    """
    import uuid

    task_id = str(uuid.uuid4())[:12]

    # Initialize task status
    _thesis_tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0.0,
        "current_phase": "init",
        "message": "Task created, waiting to start",
    }

    # TODO: Add background task execution
    # background_tasks.add_task(run_thesis_workflow, task_id, request)

    logger.info(f"[Thesis] Created task {task_id} for workspace {request.workspace_id}")

    return {
        "task_id": task_id,
        "status": "pending",
        "message": "Thesis generation task created",
    }


@router.get("/status/{task_id}", response_model=ThesisStatusResponse)
async def get_status(task_id: str) -> ThesisStatusResponse:
    """Get thesis generation task status.

    Args:
        task_id: Task ID from generate endpoint

    Returns:
        Current task status and progress
    """
    task = get_thesis_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return ThesisStatusResponse(
        task_id=task["task_id"],
        status=task["status"],
        progress=task["progress"],
        current_phase=task.get("current_phase"),
        message=task.get("message"),
        pdf_path=task.get("pdf_path"),
        error=task.get("error"),
    )


@router.get("/preview/{task_id}")
async def get_preview(task_id: str) -> dict:
    """Get thesis preview content.

    Returns the current LaTeX content for preview.
    """
    task = get_thesis_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "task_id": task_id,
        "latex_content": task.get("latex_content", ""),
        "sections_completed": task.get("sections_completed", 0),
        "sections_total": task.get("sections_total", 0),
    }
```

**Step 4: Run test to verify it passes**

Run: `cd /home/cjz/academiagpt-v2/backend && PYTHONPATH=. pytest tests/thesis/test_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/thesis/api.py tests/thesis/test_api.py
git commit -m "feat(thesis): add HTTP API endpoints for thesis generation"
```

---

## Task 11: 更新 Thesis Module __init__.py

**Files:**
- Modify: `src/thesis/__init__.py`

**Step 1: Update exports**

```python
# src/thesis/__init__.py
"""Thesis module for undergraduate thesis generation.

This module provides:
- Workflow state definitions for thesis generation
- Workflow nodes for each generation phase
- API endpoints for thesis generation requests
- Subagent configurations for thesis-specific tasks

Integration points:
- MemoryMiddleware: Automatically captures thesis discussion context
- ExecutionMiddleware: Handles LaTeX compilation via compile_latex_tool
- SubagentRegistry: Provides thesis_writer, librarian, figure_planner
"""

from .workflow.state import (
    SectionPlan,
    SectionContent,
    PaperReference,
    FigureRequest,
    GeneratedFigure,
    ThesisWorkflowState,
    merge_sections,
    merge_references,
)

from .workflow.nodes import (
    section_writer_node,
    get_next_section_index,
    literature_search_node,
    check_literature_sufficiency,
    assemble_latex_node,
    generate_bibtex,
)

__all__ = [
    # State types
    "SectionPlan",
    "SectionContent",
    "PaperReference",
    "FigureRequest",
    "GeneratedFigure",
    "ThesisWorkflowState",
    # Reducers
    "merge_sections",
    "merge_references",
    # Workflow nodes
    "section_writer_node",
    "get_next_section_index",
    "literature_search_node",
    "check_literature_sufficiency",
    "assemble_latex_node",
    "generate_bibtex",
]
```

**Step 2: Commit**

```bash
git add src/thesis/__init__.py
git commit -m "docs(thesis): update module exports and documentation"
```

---

## Task 12: 运行完整测试套件

**Files:**
- None (verification step)

**Step 1: Run all thesis tests**

Run: `cd /home/cjz/academiagpt-v2/backend && PYTHONPATH=. pytest tests/thesis/ -v --tb=short`
Expected: All tests PASS

**Step 2: Run subagent tests to verify integration**

Run: `cd /home/cjz/academiagpt-v2/backend && PYTHONPATH=. pytest tests/subagents/academic/ -v --tb=short`
Expected: All tests PASS (including new thesis tests)

**Step 3: Run full test suite**

Run: `cd /home/cjz/academiagpt-v2/backend && PYTHONPATH=. pytest tests/ -v --tb=short -x`
Expected: All tests PASS

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat(thesis): complete undergraduate thesis generation module

- Add UNDERGRADUATE_THESIS workspace type
- Register thesis_writer, librarian, figure_planner subagents
- Add thesis workflow state with reducers
- Add literature_search and section_writer nodes
- Add LaTeX assembler with Chinese thesis template
- Add thesis-writer skill
- Add HTTP API endpoints for thesis generation

Integrates with:
- MemoryMiddleware for context persistence
- ExecutionMiddleware for LaTeX compilation
- SubagentRegistry for task delegation"
```

---

## Summary

| Task | Description | Files Changed |
|------|-------------|---------------|
| 1 | 扩展 WorkspaceType | 2 |
| 2 | 创建 Thesis Prompts | 2 |
| 3 | 注册 Thesis Subagents | 3 |
| 4 | 创建 Workflow State | 4 |
| 5 | 创建 Thesis Writer Skill | 1 |
| 6 | 创建 Section Writer Node | 4 |
| 7 | 创建 Literature Search Node | 3 |
| 8 | 创建 LaTeX Assembler Node | 4 |
| 9 | 验证 ExecutionMiddleware 集成 | 1 |
| 10 | 创建 API 端点 | 2 |
| 11 | 更新 Module __init__ | 1 |
| 12 | 运行测试套件 | 0 |

**Total: ~27 files, ~1500 lines of code**
