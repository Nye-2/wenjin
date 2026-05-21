"""Source index service tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.dataservice.source_api import SourceDataService


@pytest.mark.asyncio
async def test_read_pages_uses_page_range_overlap_predicate() -> None:
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=result)

    await SourceDataService(db, autocommit=False).read_source_pages(
        workspace_id="ws-1",
        source_id="source-1",
        page_start=4,
        page_end=4,
    )

    stmt = db.execute.await_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()
    assert "source_text_units.page_start <= 4" in compiled
    assert "coalesce(source_text_units.page_end, source_text_units.page_start) >= 4" in compiled
    assert "source_text_units.page_start is not null" in compiled
