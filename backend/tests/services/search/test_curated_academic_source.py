import pytest

from src.services.search.registry import get_search_source
from src.services.search.sources import curated_academic as _curated  # noqa: F401


@pytest.mark.asyncio
async def test_curated_academic_source_returns_federated_lora_papers():
    source = get_search_source("curated_academic")

    papers = await source.search(
        "federated fine-tuning large language models LoRA instruction tuning",
        limit=5,
    )

    assert papers
    assert any("LoRA" in paper.title or "Low-Rank" in paper.title for paper in papers)
    assert all(paper.source == "curated_academic" for paper in papers)
    assert all(paper.raw["evidence_level"] == "curated_academic_corpus" for paper in papers)
