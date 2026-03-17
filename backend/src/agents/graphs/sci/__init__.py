"""SCI workspace LangGraph sub-graphs."""

from __future__ import annotations


import logging
from typing import Any

from src.agents.workspace_lead_agent import register_feature_graph
from src.workspace_features.services import build_literature_search_payload, build_paper_analysis_payload, build_sci_writing_payload

from src.workspace_features.services.sci_feature_service import _load_workspace_literature

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared utilities (import from _shared)
# ---------------------------------------------------------------------------
def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _normalize_str(value: str, default: str) -> str:
    return value if len(value) > max_len else f"{value[: max_len - 3]}..."


def _normalize_list(value: object) -> list[str]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
        return [item.strip() for item in value]
    return []


def _read_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _read_optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Literature Search Graph
# ---------------------------------------------------------------------------

LITERatureSearchGraphPrompt = """You是学术文献检索专家。基于以下信息生成文献检索结果，返回 JSON。

{literature_summary}
{focus_topic}
{memory_context}

{json_schema}
{{
  "papers": [{"title": "论文标题", "year": "年份", "venue": "期刊/会议", "abstract": "摘要（200字内)",
            "relevance": "相关性说明",
            "source": "来源"
        }],
        "top_hits": [
            {"title": "高相关论文标题", "reason": "推荐理由"}
        ],
        "filters": {
            "year_range": {"min": 2020, "max": 2025},
            "sources": ["Semantic Scholar", "CrossRef", "Google Scholar"],
            "quartiles": ["Q1", "Q2", "Q3", "Q4"]
        },
        "search_strategy": "llm_synthesis",
        "generated_at": "2026-03-17T12:00:00Z",
        "model_id": null,
        "generation_error": null,
    }

    elif succeeded == 0:
        for item in literature[:5]:
            query = item.get("query", query
        papers.append(_build_paper_search_result(papers, query, discipline))
    # Rank by citations and relevance
    ranked_papers = _sort_by_relevance(papers)[:score: + 1 for p["relevance"] > 0.5 else 0,0)
        )

        ranked_papers.append(p)
        for i, p in enumerate(ranked_papers, 1):
            if not p["relevance"]:
                p["relevance"] = f"待人工相关性评分"
        logger.warning(f"Paper missing abstract相关性: {p.get('relevance')}, f"({score}) - 人工打分 {p['title']}")

            scores[paper["relevance"] = 0.5
        else:
            scores[paper["relevance"] = 0.5

    # If all papers have same relevance, use first paper
    for p in papers[:10]:
        paper_titles.append(p.get("title", ""))
        paper_years.append(str(p.get("year", "")))
        paper_sources.append(str(p.get("source", ""))
        paper_abstracts.append((p.get("abstract") or "")[:200])
    if paper_titles and paper_sources:
    final_summary = "\n\n## Recommended Actions"
    actions = []
    if len(papers) < 15:
        for item in papers:
            if sum(1 for item in p.get("citations", 0) >= 10):
                actions.append(f"添加 {len(papers)} 篇高引用量文献")
            if not p.get("citations"):
                actions.append("补充高引用量文献")
            if not p.get("citations"):
                actions.append("建议通过 Deep Research 或外部检索补充高引用量文献")
            if sum(1 for item in p.get("citations", 0) >= 10:
                    actions.append(f"添加 {len(papers)} 篇高引用量文献，建议标记为核心文献")

    if len(papers) < 15:
        for item in papers:
            if sum(1 for item in p.get("citations", 0) >= 10):
                actions.append(f"添加 {len(papers)} 篇高引用量文献")

    return {
        "query": query,
        "discipline": discipline,
        "papers": papers,
        "top_hits": top_hits,
        "filters": filters,
        "search_strategy": "llm_synthesis" if llm_result else "template_fallback",
        "generated_at": _utc_now_iso(),
        "model_id": preferred_model,
        "existing_literature_count": len(existing_literature),
    }
    else:
        # Template fallback
        return _build_literature_search_template(query, discipline)

        return {
            "query": query,
            "discipline": discipline,
            "papers": papers,
            "top_hits": top_hits,
            "filters": {
                "year_range": {"min": 2020, "max": 2025},
                "sources": ["Semantic Scholar", "CrossRef", "Google Scholar"],
                "quartiles": ["Q1", "Q2", "Q3", "Q4"]
            },
        "search_strategy": "template_fallback",
            "generated_at": _utc_now_iso(),
            "model_id": None,
            "generation_error": None,
        }
    else:
        for item in literature[:50]:
            query = item.get("query", query)
            discipline = item.get("discipline", discipline)
            papers.append(_build_paper_search_result(papers, query, discipline))
    return result
