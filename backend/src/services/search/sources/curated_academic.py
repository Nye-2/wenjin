"""Curated academic search source for demo/offline resilience.

This source is intentionally small and transparent. It is not a compatibility
fallback; it is an explicit local corpus used when live academic APIs are rate
limited or unavailable, so workspace Library ingestion can still exercise the
same reviewed result flow.
"""

from __future__ import annotations

import re
from typing import Any

from src.services.search.base import SearchResult
from src.services.search.registry import register_search_source


_PAPERS: list[dict[str, Any]] = [
    {
        "title": "FederatedScope-LLM: A Comprehensive Package for Fine-tuning Large Language Models in Federated Learning",
        "year": 2023,
        "venue": "arXiv",
        "url": "https://arxiv.org/abs/2309.00363",
        "abstract": "A toolkit and benchmark package for studying LLM fine-tuning in federated learning settings.",
        "tags": ["federated", "large language models", "fine-tuning", "benchmark"],
    },
    {
        "title": "FedIT: Towards Building the Federated GPT: Federated Instruction Tuning",
        "year": 2023,
        "venue": "arXiv",
        "url": "https://arxiv.org/abs/2305.05644",
        "abstract": "Studies federated instruction tuning as a privacy-preserving path for adapting large language models.",
        "tags": ["federated", "instruction tuning", "large language models"],
    },
    {
        "title": "SLoRA: Federated Parameter Efficient Fine-Tuning of Language Models",
        "year": 2023,
        "venue": "arXiv",
        "url": "https://arxiv.org/abs/2308.06522",
        "abstract": "Applies parameter-efficient fine-tuning to federated language-model adaptation with low-rank updates.",
        "tags": ["federated", "parameter efficient", "lora", "adapter"],
    },
    {
        "title": "Federated Fine-tuning of Large Language Models under Heterogeneous Tasks and Client Resources",
        "year": 2024,
        "venue": "arXiv",
        "url": "https://arxiv.org/abs/2402.11505",
        "abstract": "Analyzes federated LLM fine-tuning when clients differ in task distribution and available resources.",
        "tags": ["federated", "fine-tuning", "large language models", "heterogeneous", "client resources"],
    },
    {
        "title": "FLoRA: Federated Fine-Tuning Large Language Models with Heterogeneous Low-Rank Adaptations",
        "year": 2024,
        "venue": "arXiv / NeurIPS Workshop",
        "url": "https://arxiv.org/abs/2409.05976",
        "abstract": "Studies federated low-rank adaptation under heterogeneous LoRA configurations across clients.",
        "tags": ["federated", "lora", "heterogeneous", "low-rank adaptation"],
    },
    {
        "title": "FDLoRA: Personalized Federated Learning of Large Language Model via Dual LoRA Tuning",
        "year": 2024,
        "venue": "arXiv",
        "url": "https://arxiv.org/abs/2406.07925",
        "abstract": "Uses dual LoRA modules to balance shared federated knowledge with client-specific personalization.",
        "tags": ["federated", "lora", "personalization", "large language model"],
    },
    {
        "title": "Adaptive Parameter-Efficient Federated Fine-Tuning on Heterogeneous Devices",
        "year": 2024,
        "venue": "arXiv",
        "url": "https://arxiv.org/abs/2412.20004",
        "abstract": "Adapts parameter-efficient fine-tuning strategies to heterogeneous device constraints in federated learning.",
        "tags": ["federated", "parameter efficient", "heterogeneous devices", "fine-tuning"],
    },
    {
        "title": "FedLoRA: When Personalized Federated Learning Meets Low-Rank Adaptation",
        "year": 2024,
        "venue": "OpenReview",
        "url": "https://openreview.net/forum?id=bZh06ptG9r",
        "abstract": "Connects personalized federated learning with low-rank adaptation for efficient client-specific tuning.",
        "tags": ["federated", "lora", "personalization", "low-rank adaptation"],
    },
    {
        "title": "ECOLORA: Communication-Efficient Federated Fine-Tuning of Large Language Models",
        "year": 2025,
        "venue": "ACL Anthology",
        "url": "https://aclanthology.org/2025.findings-emnlp.142/",
        "abstract": "Optimizes communication cost for federated LLM fine-tuning with LoRA-style parameter-efficient updates.",
        "tags": ["communication efficient", "federated", "fine-tuning", "large language models", "lora"],
    },
    {
        "title": "Federated Data-Efficient Instruction Tuning for Large Language Models",
        "year": 2025,
        "venue": "ACL Anthology",
        "url": "https://aclanthology.org/2025.findings-acl.270/",
        "abstract": "Studies data-efficient federated instruction tuning for large language models.",
        "tags": ["federated", "instruction tuning", "data efficient", "large language models"],
    },
]


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2
    }


class CuratedAcademicSource:
    name = "curated_academic"

    async def search(
        self,
        query: str,
        *,
        year_range: tuple[int, int] | None = None,
        limit: int = 30,
        **kwargs: Any,
    ) -> list[SearchResult]:
        query_tokens = _tokens(query)
        scored: list[tuple[int, dict[str, Any]]] = []
        for paper in _PAPERS:
            year = paper.get("year")
            if year_range and isinstance(year, int) and not (year_range[0] <= year <= year_range[1]):
                continue
            haystack = " ".join(
                [
                    str(paper.get("title") or ""),
                    str(paper.get("abstract") or ""),
                    " ".join(paper.get("tags") or []),
                ]
            )
            score = len(query_tokens & _tokens(haystack))
            if score > 0:
                scored.append((score, paper))

        scored.sort(key=lambda item: (-item[0], -(item[1].get("year") or 0), item[1]["title"]))
        selected = [paper for _, paper in scored[:limit]]
        return [
            SearchResult(
                title=str(paper["title"]),
                authors=[],
                year=paper.get("year"),
                abstract=str(paper.get("abstract") or ""),
                url=str(paper.get("url") or ""),
                venue=str(paper.get("venue") or ""),
                external_id=f"curated:{idx}:{paper['title']}",
                source=self.name,
                raw={
                    "source": self.name,
                    "evidence_level": "curated_academic_corpus",
                    "tags": paper.get("tags") or [],
                },
            )
            for idx, paper in enumerate(selected)
        ]


register_search_source("curated_academic", CuratedAcademicSource)
