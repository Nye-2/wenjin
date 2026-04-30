"""Reference usage service tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database import ReferenceLibraryStatus
from src.services.references import ReferenceUsageService
from src.services.references.utils import extract_citation_keys_from_payload


def _execute_result(values: list[object]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


@pytest.mark.asyncio
async def test_record_usage_can_record_access_without_marking_used_in_draft() -> None:
    reference = SimpleNamespace(
        id="ref-1",
        citation_key="smith2020",
        library_status=ReferenceLibraryStatus.INCLUDED,
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=_execute_result([reference]))
    db.commit = AsyncMock()

    result = await ReferenceUsageService(db).record_usage(
        workspace_id="ws-1",
        reference_ids=["ref-1"],
        outline_node_id="node-1",
        text_unit_id="unit-1",
        usage_type="background",
        mark_used_in_draft=False,
    )

    assert result["recorded"] == 1
    assert reference.library_status == ReferenceLibraryStatus.INCLUDED
    event = db.add.call_args.args[0]
    assert event.outline_node_id == "node-1"
    assert event.text_unit_id == "unit-1"
    assert event.citation_key == "smith2020"


@pytest.mark.asyncio
async def test_record_usage_by_citation_keys_marks_used_in_draft() -> None:
    reference = SimpleNamespace(
        id="ref-1",
        citation_key="smith2020",
        library_status=ReferenceLibraryStatus.INCLUDED,
    )
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            _execute_result([reference]),
            _execute_result([reference]),
        ]
    )
    db.commit = AsyncMock()

    result = await ReferenceUsageService(db).record_usage_by_citation_keys(
        workspace_id="ws-1",
        citation_keys=["smith2020"],
        artifact_id="artifact-1",
    )

    assert result["recorded"] == 1
    assert result["citation_keys"] == ["smith2020"]
    assert reference.library_status == ReferenceLibraryStatus.USED_IN_DRAFT


def test_extract_citation_keys_from_nested_payload() -> None:
    payload = {
        "content": r"See \cite{smith2020,doe-2021}.",
        "sections": [{"text": r"More detail in \parencite[12]{smith2020}."}],
    }

    assert extract_citation_keys_from_payload(payload) == ["smith2020", "doe-2021"]
