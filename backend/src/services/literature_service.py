"""Literature service for managing workspace literature references.

This service provides literature management functionality including:
- Listing literature with filters
- Creating literature entries
- Batch importing literature
- Updating literature metadata
- Deleting literature
- Counting literature
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Artifact, WorkspaceLiterature


def _safe_int(value: Any) -> int | None:
    """Best-effort integer conversion."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_title(value: str) -> str:
    """Normalize title for duplicate detection."""
    return " ".join((value or "").strip().lower().split())


def _normalize_doi(value: str | None) -> str | None:
    """Normalize DOI for duplicate detection."""
    normalized = (value or "").strip().lower()
    return normalized or None


def _parse_authors(raw_authors: Any) -> list[str]:
    """Normalize author list from heterogeneous shapes."""
    if isinstance(raw_authors, list):
        names: list[str] = []
        for item in raw_authors:
            if isinstance(item, dict):
                candidate = (
                    item.get("name")
                    or item.get("author")
                    or item.get("full_name")
                )
            else:
                candidate = item

            text = str(candidate or "").strip()
            if text:
                names.append(text)
        return names[:50]

    text = str(raw_authors or "").strip()
    if not text:
        return []

    for sep in (";", "；", "|"):
        text = text.replace(sep, ",")
    names = [part.strip() for part in text.split(",") if part.strip()]
    return names[:50]


def _iter_candidate_papers(content: Any) -> list[dict[str, Any]]:
    """Extract candidate paper dicts from deep-research artifact content."""
    if not isinstance(content, dict):
        return []

    candidates: list[dict[str, Any]] = []

    discovery = content.get("discovery")
    if isinstance(discovery, dict):
        for key in ("seminal_works", "recent_works"):
            works = discovery.get(key)
            if isinstance(works, list):
                for item in works:
                    if isinstance(item, dict):
                        candidates.append(item)

    # Compatibility: allow direct paper lists in legacy artifacts.
    for key in ("papers", "works", "seminal_works", "recent_works"):
        works = content.get(key)
        if isinstance(works, list):
            for item in works:
                if isinstance(item, dict):
                    candidates.append(item)

    return candidates


def _build_literature_row(
    *,
    workspace_id: str,
    source: str,
    paper: dict[str, Any],
) -> dict[str, Any] | None:
    """Convert a paper candidate into WorkspaceLiterature payload."""
    title = str(paper.get("title") or "").strip()
    if not title:
        return None

    authors = _parse_authors(
        paper.get("authors")
        or paper.get("author")
    )
    year = _safe_int(paper.get("year"))
    citations = _safe_int(
        paper.get("citations")
        or paper.get("citation_count")
        or paper.get("cited_by")
    )
    doi = _normalize_doi(
        paper.get("doi")
        or paper.get("DOI")
    )
    venue = str(
        paper.get("venue")
        or paper.get("journal")
        or paper.get("publication")
        or ""
    ).strip() or None

    abstract_parts = [
        str(paper.get("abstract") or "").strip(),
        str(paper.get("summary") or "").strip(),
        str(paper.get("significance") or "").strip(),
        str(paper.get("relevance") or "").strip(),
    ]
    abstract = "\n".join([part for part in abstract_parts if part]) or None

    return {
        "workspace_id": workspace_id,
        "title": title,
        "authors": authors,
        "year": year,
        "citations": citations,
        "venue": venue,
        "quartile": None,
        "abstract": abstract,
        "doi": doi,
        "source": source,
        "is_core": False,
    }


class LiteratureService:
    """Service for managing workspace literature.

    This class provides CRUD operations for literature entries within a workspace.
    It requires an AsyncSession for database operations.

    Attributes:
        db: AsyncSession for database operations
    """

    def __init__(self, db: AsyncSession):
        """Initialize LiteratureService with database session.

        Args:
            db: AsyncSession for database operations
        """
        self.db = db

    async def list_literature(
        self,
        workspace_id: str,
        source: str | None = None,
        is_core: bool | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """List literature entries for a workspace with optional filters.

        Args:
            workspace_id: UUID of the workspace
            source: Optional filter by source (manual, deep_research, etc.)
            is_core: Optional filter by core reference status
            offset: Number of items to skip
            limit: Maximum number of items to return

        Returns:
            Dictionary with items, total count, and core count
        """
        # Build base query
        base_query = select(WorkspaceLiterature).where(
            WorkspaceLiterature.workspace_id == workspace_id
        )

        # Apply filters
        if source is not None:
            base_query = base_query.where(WorkspaceLiterature.source == source)
        if is_core is not None:
            base_query = base_query.where(WorkspaceLiterature.is_core == is_core)

        # Get total count
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Get core count
        core_query = select(func.count()).where(
            WorkspaceLiterature.workspace_id == workspace_id,
            WorkspaceLiterature.is_core == True,  # noqa: E712
        )
        core_result = await self.db.execute(core_query)
        core_count = core_result.scalar() or 0

        # Get paginated items
        items_query = base_query.order_by(WorkspaceLiterature.created_at.desc())
        items_query = items_query.offset(offset).limit(limit)
        items_result = await self.db.execute(items_query)
        items = items_result.scalars().all()

        return {
            "items": [self._to_dict(item) for item in items],
            "total": total,
            "core_count": core_count,
        }

    async def create_literature(
        self,
        workspace_id: str,
        title: str,
        authors: list[str] | None = None,
        year: int | None = None,
        citations: int | None = None,
        venue: str | None = None,
        quartile: str | None = None,
        abstract: str | None = None,
        doi: str | None = None,
        source: str = "manual",
        is_core: bool = False,
    ) -> dict[str, Any]:
        """Create a new literature entry.

        Args:
            workspace_id: UUID of the workspace
            title: Title of the literature
            authors: List of author names
            year: Publication year
            citations: Number of citations
            venue: Publication venue
            quartile: Journal quartile (Q1, Q2, Q3, Q4)
            abstract: Abstract or summary
            doi: Digital Object Identifier
            source: Source of the literature (default: manual)
            is_core: Whether this is a core reference

        Returns:
            Created literature entry as dictionary
        """
        literature = WorkspaceLiterature(
            workspace_id=workspace_id,
            title=title,
            authors=authors or [],
            year=year,
            citations=citations,
            venue=venue,
            quartile=quartile,
            abstract=abstract,
            doi=doi,
            source=source,
            is_core=is_core,
        )

        self.db.add(literature)
        await self.db.commit()
        await self.db.refresh(literature)

        return self._to_dict(literature)

    async def batch_import(
        self,
        workspace_id: str,
        source: str,
        paper_ids: list[str],
    ) -> dict[str, Any]:
        """Batch import literature entries from source artifacts.

        For ``source="deep_research"``, ``paper_ids`` are interpreted as
        artifact IDs. The method extracts candidate papers from artifact content
        and persists non-duplicate literature rows.
        """
        if source != "deep_research":
            return {"imported": 0}

        artifact_ids = list(dict.fromkeys([pid.strip() for pid in paper_ids if pid and pid.strip()]))
        if not artifact_ids:
            return {"imported": 0}

        artifacts_result = await self.db.execute(
            select(Artifact).where(
                Artifact.workspace_id == workspace_id,
                Artifact.id.in_(artifact_ids),
            )
        )
        artifacts = artifacts_result.scalars().all()
        if not artifacts:
            return {"imported": 0}

        rows: list[dict[str, Any]] = []
        for artifact in artifacts:
            candidates = _iter_candidate_papers(artifact.content)
            for paper in candidates:
                row = _build_literature_row(
                    workspace_id=workspace_id,
                    source=source,
                    paper=paper,
                )
                if row:
                    rows.append(row)

        if not rows:
            return {"imported": 0}

        existing_query = select(WorkspaceLiterature).where(
            WorkspaceLiterature.workspace_id == workspace_id
        )
        existing_result = await self.db.execute(existing_query)
        existing_items = existing_result.scalars().all()

        existing_titles = {_normalize_title(str(item.title)) for item in existing_items if item.title}
        existing_dois = {_normalize_doi(item.doi) for item in existing_items if item.doi}

        imported = 0
        seen_batch_titles: set[str] = set()
        seen_batch_dois: set[str] = set()

        for row in rows:
            title_key = _normalize_title(str(row["title"]))
            doi_key = _normalize_doi(row.get("doi"))

            if title_key in existing_titles or title_key in seen_batch_titles:
                continue
            if doi_key and (doi_key in existing_dois or doi_key in seen_batch_dois):
                continue

            literature = WorkspaceLiterature(
                workspace_id=workspace_id,
                title=str(row["title"]),
                authors=row.get("authors") or [],
                year=row.get("year"),
                citations=row.get("citations"),
                venue=row.get("venue"),
                quartile=row.get("quartile"),
                abstract=row.get("abstract"),
                doi=row.get("doi"),
                source=source,
                is_core=False,
            )
            self.db.add(literature)
            imported += 1
            seen_batch_titles.add(title_key)
            if doi_key:
                seen_batch_dois.add(doi_key)

        if imported > 0:
            await self.db.commit()

        return {"imported": imported}

    async def update_literature(
        self,
        literature_id: str,
        workspace_id: str | None = None,
        **kwargs,
    ) -> dict[str, Any] | None:
        """Update a literature entry.

        Args:
            literature_id: UUID of the literature entry
            **kwargs: Fields to update (is_core, title, authors, etc.)

        Returns:
            Updated literature entry as dictionary, or None if not found
        """
        query = select(WorkspaceLiterature).where(WorkspaceLiterature.id == literature_id)
        if workspace_id is not None:
            query = query.where(WorkspaceLiterature.workspace_id == workspace_id)

        result = await self.db.execute(query)
        literature = result.scalar_one_or_none()

        if literature is None:
            return None

        # Update allowed fields
        allowed_fields = {
            "title", "authors", "year", "citations", "venue",
            "quartile", "abstract", "doi", "source", "is_core",
        }

        for key, value in kwargs.items():
            if key in allowed_fields:
                setattr(literature, key, value)

        await self.db.commit()
        await self.db.refresh(literature)

        return self._to_dict(literature)

    async def delete_literature(
        self,
        literature_id: str,
        workspace_id: str | None = None,
    ) -> bool:
        """Delete a literature entry.

        Args:
            literature_id: UUID of the literature entry

        Returns:
            True if deleted, False if not found
        """
        query = select(WorkspaceLiterature).where(WorkspaceLiterature.id == literature_id)
        if workspace_id is not None:
            query = query.where(WorkspaceLiterature.workspace_id == workspace_id)

        result = await self.db.execute(query)
        literature = result.scalar_one_or_none()

        if literature is None:
            return False

        await self.db.delete(literature)
        await self.db.commit()

        return True

    async def count_literature(self, workspace_id: str) -> dict[str, int]:
        """Count literature entries for a workspace.

        Args:
            workspace_id: UUID of the workspace

        Returns:
            Dictionary with total and core counts
        """
        # Get total count
        total_query = select(func.count()).where(
            WorkspaceLiterature.workspace_id == workspace_id
        )
        total_result = await self.db.execute(total_query)
        total = total_result.scalar() or 0

        # Get core count
        core_query = select(func.count()).where(
            WorkspaceLiterature.workspace_id == workspace_id,
            WorkspaceLiterature.is_core == True,  # noqa: E712
        )
        core_result = await self.db.execute(core_query)
        core = core_result.scalar() or 0

        return {"total": total, "core": core}

    def _to_dict(self, literature: WorkspaceLiterature) -> dict[str, Any]:
        """Convert WorkspaceLiterature ORM object to dictionary.

        Args:
            literature: WorkspaceLiterature ORM object

        Returns:
            Dictionary representation
        """
        return {
            "id": str(literature.id),
            "workspace_id": str(literature.workspace_id),
            "title": literature.title,
            "authors": literature.authors or [],
            "year": literature.year,
            "citations": literature.citations,
            "venue": literature.venue,
            "quartile": literature.quartile,
            "abstract": literature.abstract,
            "doi": literature.doi,
            "source": literature.source,
            "is_core": literature.is_core,
            "created_at": literature.created_at.isoformat() if literature.created_at else None,
            "updated_at": literature.updated_at.isoformat() if literature.updated_at else None,
        }
