# 文献管理模块精简重构设计文档

> **创建日期**: 2026-03-10
> **状态**: 已批准
> **作者**: Claude + 用户

## 1. 概述

### 1.1 背景

AcademiaGPT v2 当前文献管理模块存在以下问题：
- RAG 向量检索依赖 embedding 模型，- 服务端资源消耗大
- 架构复杂，- 与 LLM 工具调用模式不匹配

### 1.2 目标

将文献管理模块重构为 **TOC-Driven** (目录驱动) 检索系统：
- 移除 RAG 向量检索
- 宻现基于论文目录结构的导航
- 集成外部学术数据库
- LLM 通过工具主动调用获取内容

## 2. 目录结构

```
src/academic/literature/
├── __init__.py
├── models.py                    # 共享数据模型
├── tools.py                     # LLM 工具定义
├── extraction/                  # PDF 解析模块
│   ├── __init__.py
│   ├── pdf_extractor.py     # PDF 文本/元数据提取
│   └── toc_extractor.py     # 目录结构提取
├── navigation/                  # TOC 导航模块 (新增)
│   ├── __init__.py
│   ├── models.py               # 数据模型
│   ├── toc_service.py          # 目录服务
│   └── section_loader.py       # 章节内容加载
└── external/                   # 外部数据库模块 (新增)
    ├── __init__.py
    ├── base.py                  # 基类
    ├── semantic_scholar.py      # Semantic Scholar API
    ├── arxiv.py                 # arXiv API
    ├── crossref.py              # Crossref/DOI API
    └── openalex.py              # OpenAlex API

# 移除
src/academic/literature/rag/   # ❌ 删除整个目录
```

## 3. 数据模型

### 3.1 TOC 数据结构

```python
# src/academic/literature/navigation/models.py

from pydantic import BaseModel
from typing import Literal

class TOCEntry(BaseModel):
    """论文目录条目"""
    title: str              # "3. Methodology"
    level: int              # 层级 (1=章, 2=节, 3=小节)
    page_start: int | None  # 起始页
    char_start: int         # 在全文中的字符起始位置
    char_end: int           # 字符结束位置
    children: list["TOCEntry"] = []

class PaperTOC(BaseModel):
    """论文完整目录结构"""
    paper_id: str
    title: str
    abstract: str           # 摘要单独存储，总是可访问
    entries: list[TOCEntry]
    total_chars: int        # 全文字符数

class SectionContent(BaseModel):
    """章节内容"""
    paper_id: str
    section_title: str
    content: str            # Markdown 格式
    word_count: int
    has_subsections: bool
```

### 3.2 外部数据库模型

```python
# src/academic/literature/external/base.py

from abc import ABC, abstractmethod
from typing import Any

class ExternalDBBase(ABC):
    """外部学术数据库基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """数据库名称"""
        pass

    @property
    @abstractmethod
    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """搜索论文"""
        pass

    @abstractmethod
    async def get_by_doi(self, doi: str) -> dict[str, Any] | None:
        """通过 DOI 获取论文详情"""
        pass

    @abstractmethod
    async def get_citations(self, paper_id: str, limit: int = 10) -> list[dict]:
        """获取引用列表"""
        pass

class PaperSearchResult(BaseModel):
    """统一的搜索结果"""
    title: str
    authors: list[str]
    year: int
    doi: str | None
    url: str
    abstract: str
    source: Literal["semantic_scholar", "arxiv", "crossref", "openalex"]
    citations_count: int | None = None
```

## 4. LLM 工具设计

### 4.1 工具列表

```python
# src/academic/literature/tools.py

from langchain_core.tools import tool

@tool
def list_papers(workspace_id: str) -> list:
    """列出 workspace 中的所有论文及其 TOC

    Args:
        workspace_id: 工作区 ID

    Returns:
        [{"paper_id": str, "title": str, "toc": [
            {"title": "1. Introduction", "level": 1},
            {"title": "2. Related Work", "level": 1},
            ...
        ]}]
    """
    pass

@tool
def get_section(paper_id: str, section_title: str) -> str:
    """获取论文指定章节的 markdown 内容

    Args:
        paper_id: 论文 ID
        section_title: 章节标题 (如 "3. Methodology")

    Returns:
        章节的 markdown 内容
    """
    pass

@tool
def search_external(query: str, source: str = "all") -> list:
    """搜索外部学术数据库

    Args:
        query: 搜索关键词
        source: 数据源 (semantic_scholar, arxiv, crossref, openalex, all)

    Returns:
        [{"title": str, "authors": list, "year": int,
          "doi": str, "url": str, "abstract": str}]
    """
    pass

@tool
def get_paper_by_doi(doi: str) -> dict:
    """通过 DOI 获取论文元数据

    Args:
        doi: 论文 DOI

    Returns:
        {"title": str, "authors": list, "abstract": str,
         "citations": int, "references": list, ...}
    """
    pass

@tool
def import_paper_to_workspace(doi: str, workspace_id: str) -> str:
    """将外部论文导入到工作区

    Args:
        doi: 论文 DOI
        workspace_id: 目标工作区 ID

    Returns:
        导入状态消息
    """
    pass
```

## 5. 工作流程

### 5.1 LLM 与文献交互流程

```
┌──────────────────────────────────────────────────────────────┐
│                    LLM Agent 工作流程                          │
├──────────────────────────────────────────────────────────────┤
│ 1. 用户提问: "帮我分析这篇论文的方法论"               │
│                                                               │
│ 2. LLM 调用 list_papers 获取 workspace 中的论文列表             │
│    → 返回: [{"id": "p1", "title": "...", "toc": [...]}]       │
│                                                               │
│ 3. LLM 看到论文 TOC，选择调用 get_section                       │
│    → 参数: paper_id="p1", section="3. Methodology"            │
│    → 返回: 章节 markdown 内容                                  │
│                                                               │
│ 4. LLM 根据内容回答用户问题                                   │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 外部搜索流程

```
┌──────────────────────────────────────────────────────────────┐
│                    外部数据库搜索流程                          │
├──────────────────────────────────────────────────────────────┤
│ 1. 用户: "搜索关于 transformer 的最新论文"                   │
│                                                               │
│ 2. LLM 调用 search_external(query="transformer", source="all") │
│    → 并行查询 Semantic Scholar, arXiv, OpenAlex            │
│    → 合并去重后返回结果列表                                    │
│                                                               │
│ 3. LLM 展示结果给用户，用户选择感兴趣的论文                    │
│                                                               │
│ 4. LLM 调用 import_paper_to_workspace 将论文导入工作区         │
└──────────────────────────────────────────────────────────────┘
```

## 6. 迁移计划

### Phase 1: 清理旧代码 (1h)
- [ ] 删除 `src/academic/literature/rag/` 目录
- [ ] 更新 `src/academic/literature/__init__.py` 移除 RAG 导出
- [ ] 清理相关的导入和依赖

### Phase 2: 创建导航模块 (2h)
- [ ] 创建 `navigation/` 目录结构
- [ ] 实现 `TOCEntry`, `PaperTOC`, `SectionContent` 数据模型
- [ ] 实现 `TocService` 服务
- [ ] 实现 `SectionLoader` 章节加载器

### Phase 3: 创建外部数据库模块 (3h)
- [ ] 创建 `external/` 目录结构
- [ ] 实现 `ExternalDBBase` 基类
- [ ] 实现 `SemanticScholarClient`
- [ ] 实现 `ArxivClient`
- [ ] 实现 `CrossrefClient`
- [ ] 实现 `OpenAlexClient`

### Phase 4: 重构工具 (2h)
- [ ] 更新 `tools.py` 中的工具定义
- [ ] 实现工具函数
- [ ] 更新工具注册

### Phase 5: 更新中间件 (1h)
- [ ] 更新 `LiteratureContextMiddleware` 使用新的 TOC 服务
- [ ] 确保向后兼容

### Phase 6: 测试 (2h)
- [ ] 单元测试
- [ ] 集成测试
- [ ] 端到端测试

## 7. 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| TOC 提取不准确 | 添加 fallback 机制，使用 PDF 书签信息 |
| 外部 API 限流 | 宯本机缓存 + Redis 缓存 |
| 章节定位偏移 | 使用字符位置而非页码，更精确 |
| 向后兼容性 | 保留旧 API 但标记为 deprecated |

## 8. 验收标准

- [ ] RAG 模块完全移除
- [ ] 4 个外部数据库集成完成
- [ ] 5 个 LLM 工具可用
- [ ] TOC 导航流程验证
- [ ] 所有测试通过
- [ ] 文档更新完成
