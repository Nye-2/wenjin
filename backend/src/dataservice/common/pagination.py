"""Pagination models shared by DataService query endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PageRequest(BaseModel):
    """Offset pagination request."""

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class Page(BaseModel):
    """Offset pagination result."""

    items: list[Any]
    total: int
    limit: int
    offset: int
