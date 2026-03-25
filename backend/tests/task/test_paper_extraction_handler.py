"""Tests for the internal paper extraction task handler."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest

from src.task.handlers import paper_extraction_handler as handler


class _AsyncContext:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_execute_paper_extraction_runs_services_and_reports_progress(
    monkeypatch: pytest.MonkeyPatch,
):
    progress = AsyncMock()
    paper = SimpleNamespace(id="paper-1", file_path="/data/papers/paper-1.pdf")
    extraction = SimpleNamespace(
        id="ext-1",
        paper_id="paper-1",
        tier=2,
        extraction_type="structured",
        structured_data={"title": "Agent Systems"},
        processing_time_ms=321,
        model_used="gpt-4.1",
    )
    sections = [SimpleNamespace(id="sec-1"), SimpleNamespace(id="sec-2")]

    paper_service = AsyncMock()
    paper_service.get = AsyncMock(return_value=paper)

    extraction_service = AsyncMock()
    extraction_service.extract_paper = AsyncMock(return_value=extraction)
    extraction_service.extract_sections = AsyncMock(return_value=sections)

    monkeypatch.setattr(handler, "get_db_session", lambda: _AsyncContext(object()))
    monkeypatch.setattr(handler, "PaperService", lambda db: paper_service)
    monkeypatch.setattr(handler, "ExtractionService", lambda db: extraction_service)

    result = await handler.execute_paper_extraction(
        {
            "workspace_id": "ws-1",
            "paper_id": "paper-1",
            "tier": 2,
        },
        progress,
    )

    extraction_service.extract_paper.assert_awaited_once_with(
        paper_id="paper-1",
        file_path="/data/papers/paper-1.pdf",
        tier=2,
    )
    extraction_service.extract_sections.assert_awaited_once_with(
        paper_id="paper-1",
        workspace_id="ws-1",
        file_path="/data/papers/paper-1.pdf",
    )
    progress.update.assert_has_awaits(
        [
            call(5, "Loading paper", current_step="load"),
            call(25, "Extracting paper content", current_step="extract"),
            call(75, "Extracting sections", current_step="sections"),
            call(95, "Finalizing extraction", current_step="finalize"),
        ]
    )
    assert result == {
        "success": True,
        "paper_id": "paper-1",
        "workspace_id": "ws-1",
        "tier": 2,
        "message": "Paper extraction completed",
        "data": {
            "extraction": {
                "id": "ext-1",
                "paper_id": "paper-1",
                "tier": 2,
                "extraction_type": "structured",
                "structured_data": {"title": "Agent Systems"},
                "processing_time_ms": 321,
                "model_used": "gpt-4.1",
            },
            "sections_count": 2,
        },
        "refresh_targets": ["papers"],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"workspace_id": "ws-1", "tier": 1}, "missing paper_id"),
        ({"paper_id": "paper-1", "tier": 1}, "missing workspace_id"),
        (
            {"workspace_id": "ws-1", "paper_id": "paper-1", "tier": 3},
            "Invalid extraction tier: 3",
        ),
    ],
)
async def test_execute_paper_extraction_validates_payload(payload: dict, message: str):
    progress = AsyncMock()

    with pytest.raises(ValueError, match=message):
        await handler.execute_paper_extraction(payload, progress)


@pytest.mark.asyncio
async def test_execute_paper_extraction_raises_when_paper_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    progress = AsyncMock()
    paper_service = AsyncMock()
    paper_service.get = AsyncMock(return_value=None)
    extraction_service = AsyncMock()

    monkeypatch.setattr(handler, "get_db_session", lambda: _AsyncContext(object()))
    monkeypatch.setattr(handler, "PaperService", lambda db: paper_service)
    monkeypatch.setattr(handler, "ExtractionService", lambda db: extraction_service)

    with pytest.raises(ValueError, match="Paper not found: paper-404"):
        await handler.execute_paper_extraction(
            {
                "workspace_id": "ws-1",
                "paper_id": "paper-404",
                "tier": 1,
            },
            progress,
        )

    extraction_service.extract_paper.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_paper_extraction_raises_when_paper_has_no_file_path(
    monkeypatch: pytest.MonkeyPatch,
):
    progress = AsyncMock()
    paper_service = AsyncMock()
    paper_service.get = AsyncMock(
        return_value=SimpleNamespace(id="paper-1", file_path=None)
    )
    extraction_service = AsyncMock()

    monkeypatch.setattr(handler, "get_db_session", lambda: _AsyncContext(object()))
    monkeypatch.setattr(handler, "PaperService", lambda db: paper_service)
    monkeypatch.setattr(handler, "ExtractionService", lambda db: extraction_service)

    with pytest.raises(ValueError, match="Paper has no file path for extraction"):
        await handler.execute_paper_extraction(
            {
                "workspace_id": "ws-1",
                "paper_id": "paper-1",
                "tier": 1,
            },
            progress,
        )

    extraction_service.extract_paper.assert_not_awaited()
