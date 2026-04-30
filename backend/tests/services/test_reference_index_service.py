"""Reference index service tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.references import ReferenceIndexService


@pytest.mark.asyncio
async def test_read_pages_uses_page_range_overlap_predicate() -> None:
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=result)

    await ReferenceIndexService(db).read_pages(
        workspace_id="ws-1",
        reference_id="ref-1",
        page_start=4,
        page_end=4,
    )

    stmt = db.execute.await_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()
    assert "reference_text_units.page_start <= 4" in compiled
    assert "coalesce(reference_text_units.page_end, reference_text_units.page_start) >= 4" in compiled
    assert "reference_text_units.page_start is not null" in compiled

