"""Abstract search source interface."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """Normalized search result."""

    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    abstract: str | None = None
    doi: str | None = None
    url: str | None = None
    citations: int | None = None
    venue: str | None = None
    external_id: str = ""
    source: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


class SearchSource(Protocol):
    """Protocol all concrete search sources must implement."""

    name: str

    async def search(
        self,
        query: str,
        *,
        year_range: tuple[int, int] | None = None,
        limit: int = 30,
        **kwargs: Any,
    ) -> list[SearchResult]: ...
