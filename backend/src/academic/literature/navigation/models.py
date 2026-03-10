# src/academic/literature/navigation/models.py
"""Data models for TOC navigation."""

from pydantic import BaseModel, Field


class TOCEntry(BaseModel):
    """论文目录条目"""
    title: str = Field(..., description="章节标题")
    level: int = Field(..., ge=1, le=5, description="层级 (1=章, 2=节, 3=小节)")
    page_start: int | None = Field(None, description="起始页码")
    char_start: int = Field(..., ge=0, description="在全文中的字符起始位置")
    char_end: int = Field(..., ge=0, description="字符结束位置")
    children: list["TOCEntry"] = Field(default_factory=list, description="子章节")

    class Config:
        json_schema_extra = {
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


class PaperTOC(BaseModel):
    """论文完整目录结构"""
    paper_id: str = Field(..., description="论文 ID")
    title: str = Field(..., description="论文标题")
    abstract: str = Field(default="", description="摘要内容，始终可访问")
    entries: list[TOCEntry] = Field(default_factory=list, description="目录条目列表")
    total_chars: int = Field(default=0, ge=0, description="全文字符数")

    def find_entry(self, title: str) -> TOCEntry | None:
        """通过标题查找目录条目"""
        return self._find_entry_recursive(title, self.entries)

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

    class Config:
        json_schema_extra = {
            "example": {
                "paper_id": "paper-123",
                "section_title": "3. Methodology",
                "content": "## 3. Methodology\n\nWe propose a novel approach...",
                "word_count": 1500,
                "has_subsections": True
            }
        }
