# src/academic/literature/navigation/models.py
"""Data models for TOC navigation."""

from pydantic import BaseModel, ConfigDict, Field


class TOCEntry(BaseModel):
    """论文目录条目"""
    title: str = Field(..., description="章节标题")
    level: int = Field(..., ge=1, le=5, description="层级 (1=章, 2=节, 3=小节)")
    page_start: int | None = Field(None, description="起始页码")
    char_start: int = Field(..., ge=0, description="在全文中的字符起始位置")
    char_end: int = Field(..., ge=0, description="字符结束位置")
    children: list["TOCEntry"] = Field(default_factory=list, description="子章节")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "3. Methodology",
                "level": 1,
                "page_start": 5,
                "char_start": 15000,
                "char_end": 25000,
                "children": [
                    {
                        "title": "3.1 Dataset",
                        "level": 2,
                        "char_start": 16000,
                        "char_end": 18000,
                        "children": []
                    }
                ]
            }
        }
    )


class PaperTOC(BaseModel):
    """论文完整目录结构"""
    paper_id: str = Field(..., description="论文 ID")
    title: str = Field(..., description="论文标题")
    abstract: str = Field(default="", description="摘要内容，始终可访问")
    entries: list[TOCEntry] = Field(default_factory=list, description="目录条目列表")
    total_chars: int = Field(default=0, ge=0, description="全文字符数")

    def find_entry(self, title: str) -> TOCEntry | None:
        """通过标题查找目录条目 — 支持精确匹配和模糊匹配"""
        # 1. Exact match (case-insensitive)
        exact = self._find_entry_recursive(title, self.entries)
        if exact:
            return exact

        # 2. Fuzzy match using difflib
        import difflib

        all_entries = self._flatten_entries(self.entries)
        titles = [e.title for e in all_entries]
        matches = difflib.get_close_matches(title, titles, n=1, cutoff=0.6)
        if matches:
            return self._find_entry_recursive(matches[0], self.entries)

        return None

    def find_entry_by_path(self, section_path: str) -> TOCEntry | None:
        """通过章节路径查找 (如 "3.2.1")"""
        return self._find_by_path_recursive(section_path, self.entries, "")

    def _find_by_path_recursive(
        self,
        target_path: str,
        entries: list[TOCEntry],
        prefix: str,
    ) -> TOCEntry | None:
        for i, entry in enumerate(entries):
            current_path = f"{i + 1}" if not prefix else f"{prefix}.{i + 1}"
            if current_path == target_path:
                return entry
            if entry.children:
                found = self._find_by_path_recursive(
                    target_path, entry.children, current_path
                )
                if found:
                    return found
        return None

    def _flatten_entries(self, entries: list[TOCEntry]) -> list[TOCEntry]:
        """Flatten nested entries into a flat list."""
        result: list[TOCEntry] = []
        for entry in entries:
            result.append(entry)
            if entry.children:
                result.extend(self._flatten_entries(entry.children))
        return result

    def _find_entry_recursive(self, title: str, entries: list[TOCEntry]) -> TOCEntry | None:
        for entry in entries:
            if entry.title.lower() == title.lower():
                return entry
            if entry.children:
                found = self._find_entry_recursive(title, entry.children)
                if found:
                    return found
        return None


class SectionContent(BaseModel):
    """章节内容"""
    paper_id: str = Field(..., description="论文 ID")
    section_title: str = Field(..., description="章节标题")
    content: str = Field(..., description="章节 markdown 内容")
    word_count: int = Field(default=0, ge=0, description="字数统计")
    has_subsections: bool = Field(default=False, description="是否有子章节")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "paper_id": "paper-123",
                "section_title": "3. Methodology",
                "content": "## 3. Methodology\n\nWe propose a novel approach...",
                "word_count": 1500,
                "has_subsections": True
            }
        }
    )
