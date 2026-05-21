"""Reference usage service tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database import ReferenceLibraryStatus
from src.dataservice.source_api import SourceCitationUsageCreateCommand, SourceDataService
from src.services.references.utils import extract_citation_keys_from_payload


def _execute_result(values: list[object]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


@pytest.mark.asyncio
async def test_record_usage_can_record_access_without_marking_used_in_draft() -> None:
    source = SimpleNamespace(
        id="ref-1",
        citation_key="smith2020",
        library_status=ReferenceLibraryStatus.INCLUDED,
        is_deleted=False,
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=_execute_result([source]))
    db.commit = AsyncMock()

    result = await SourceDataService(db).record_citation_usage(
        SourceCitationUsageCreateCommand(
            workspace_id="ws-1",
            citation_keys=["smith2020"],
            target_domain="reference_library",
            target_kind="source_text_unit",
            target_id="unit-1",
            target_ref_json={
                "outline_node_id": "node-1",
                "text_unit_id": "unit-1",
            },
            usage_type="background",
            mark_used_in_draft=False,
        )
    )

    assert result.recorded == 1
    assert result.source_ids == ["ref-1"]
    assert source.library_status == ReferenceLibraryStatus.INCLUDED
    link = db.add.call_args.args[0]
    assert link.source_id == "ref-1"
    assert link.target_domain == "reference_library"
    assert link.target_kind == "source_text_unit"
    assert link.target_ref_json["outline_node_id"] == "node-1"
    assert link.target_ref_json["text_unit_id"] == "unit-1"
    assert link.citation_key == "smith2020"


@pytest.mark.asyncio
async def test_record_usage_by_citation_keys_marks_used_in_draft() -> None:
    source = SimpleNamespace(
        id="ref-1",
        citation_key="smith2020",
        library_status=ReferenceLibraryStatus.INCLUDED,
        is_deleted=False,
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=_execute_result([source]))
    db.commit = AsyncMock()

    result = await SourceDataService(db).record_citation_usage(
        SourceCitationUsageCreateCommand(
            workspace_id="ws-1",
            citation_keys=["smith2020"],
            artifact_id="artifact-1",
        )
    )

    assert result.recorded == 1
    assert result.citation_keys == ["smith2020"]
    assert source.library_status == "used_in_draft"


def test_extract_citation_keys_from_nested_payload() -> None:
    payload = {
        "content": r"See \cite{smith2020,doe-2021}.",
        "sections": [{"text": r"More detail in \parencite[12]{smith2020}."}],
    }

    assert extract_citation_keys_from_payload(payload) == ["smith2020", "doe-2021"]
