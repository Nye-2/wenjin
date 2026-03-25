"""Paper extraction task handler."""

from __future__ import annotations

from typing import Any

from src.academic.services.extraction_service import ExtractionService
from src.academic.services.paper_service import PaperService
from src.database import get_db_session


def _serialize_extraction(extraction: Any) -> dict[str, Any]:
    return {
        "id": str(extraction.id),
        "paper_id": str(extraction.paper_id),
        "tier": int(extraction.tier),
        "extraction_type": str(extraction.extraction_type),
        "structured_data": extraction.structured_data or {},
        "processing_time_ms": extraction.processing_time_ms,
        "model_used": extraction.model_used,
    }


async def execute_paper_extraction(payload: dict[str, Any], progress) -> dict[str, Any]:
    """Execute asynchronous paper extraction for a workspace paper."""
    paper_id = str(payload.get("paper_id") or "").strip()
    workspace_id = str(payload.get("workspace_id") or "").strip()
    tier = int(payload.get("tier") or 1)

    if not paper_id:
        raise ValueError("Paper extraction payload missing paper_id")
    if not workspace_id:
        raise ValueError("Paper extraction payload missing workspace_id")
    if tier not in (1, 2):
        raise ValueError(f"Invalid extraction tier: {tier}")

    await progress.update(5, "Loading paper", current_step="load")

    async with get_db_session() as db:
        paper_service = PaperService(db)
        extraction_service = ExtractionService(db)

        paper = await paper_service.get(paper_id)
        if paper is None:
            raise ValueError(f"Paper not found: {paper_id}")
        if not paper.file_path:
            raise ValueError("Paper has no file path for extraction")

        await progress.update(25, "Extracting paper content", current_step="extract")
        extraction = await extraction_service.extract_paper(
            paper_id=paper_id,
            file_path=paper.file_path,
            tier=tier,
        )

        await progress.update(75, "Extracting sections", current_step="sections")
        sections = await extraction_service.extract_sections(
            paper_id=paper_id,
            workspace_id=workspace_id,
            file_path=paper.file_path,
        )

        await progress.update(95, "Finalizing extraction", current_step="finalize")
        return {
            "success": True,
            "paper_id": paper_id,
            "workspace_id": workspace_id,
            "tier": tier,
            "message": "Paper extraction completed",
            "data": {
                "extraction": _serialize_extraction(extraction),
                "sections_count": len(sections),
            },
            "refresh_targets": ["papers"],
        }
