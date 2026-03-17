"""Prior Art Search sub-graph — LLM-powered patent prior art analysis.

Pipeline: extract parameters -> build search strategy -> parallel LLM analysis -> build avoidance suggestions
Falls back to template mode if LLM unavailable.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.agents.workspace_lead_agent import register_feature_graph
from src.agents.graphs._shared import (
    detect_generation_mode,
    parse_json_response,
)

logger = logging.getLogger(__name__)


@register_feature_graph("prior_art_search")
async def prior_art_search_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute prior art search with LLM-enhanced analysis.

    Pipeline:
        1. Extract parameters
        2. Call service layer for analysis
        3. Determine generation mode from service response
        4. Build structured output

    Falls back to template mode if LLM unavailable.
    """
    workspace_id = str(payload.get("workspace_id", ""))
    workspace_name = str(payload.get("workspace_name", ""))
    params = payload.get("params", {})
    memory_context = initial_state.get("knowledge_context")

    # Step 1: Parameter extraction
    keywords = _extract_prior_art_params(params, workspace_name, memory_context)
    ipc_codes = str(params.get("ipc_codes") or "")
    time_range = str(params.get("time_range") or "近5年")
    preferred_model = _read_optional_str(params.get("model_id"))
    normalized_keywords = _normalize_str(keywords)
    normalized_ipc = _normalize_str(ipc_codes)
    normalized_time_range = _normalize_str(time_range)
    }
    memory_text = f"\n用户记忆上下文: {memory_context}" if memory_context else ""
    # Step 2: Call service layer
    from src.workspace_features.services.patent_feature_service import build_prior_art_search_payload
        result = await build_prior_art_search_payload(
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        keywords=normalized_keywords,
        ipc_codes=normalized_ipc,
        time_range=normalized_time_range,
        preferred_model=preferred_model,
    )
    # Step 3: Determine generation mode from service response
    generation_mode = str(result.get("generation_mode") or "template_fallback")
    search_scope = result.get("search_scope", {})
    comparison_table = result.get("comparison_table", [])
    novelty_risks = result.get("novelty_risks", [])
    avoidance_suggestions = result.get("avoidance_suggestions", [])
    next_steps = result.get("next_steps", [])
    model_id = result.get("model_id")
    generation_error = result.get("generation_error")
    generated_at = result.get("generated_at")
    else:
        # Template fallback
        generation_mode = "template_fallback"
        search_scope = _build_template_search_scope(normalized_keywords, normalized_ipc)
        comparison_table = _build_template_comparison_table(normalized_keywords)
        novelty_risks = _build_template_novelty_risks()
        avoidance_suggestions = _build_template_avoidance_suggestions()
        next_steps = _build_template_next_steps()
        model_id = None
        generation_error = None
        generated_at = datetime.now(tz=timezone.utc).isoformat()
    }
    return {
        "keywords": normalized_keywords,
        "ipc_codes": normalized_ipc,
        "time_range": normalized_time_range,
        "search_scope": search_scope,
        "comparison_table": comparison_table,
        "novelty_risks": novelty_risks,
        "avoidance_suggestions": avoidance_suggestions,
        "next_steps": next_steps,
        "generation_mode": generation_mode,
        "model_id": model_id,
        "generation_error": generation_error,
        "generated_at": generated_at,
    }


def _extract_prior_art_params(
    params: dict[str, Any],
    workspace_name: str,
    memory_context: str | None,
) -> list[str]:
    """Extract and normalize prior art search parameters."""
    raw_keywords = params.get("keywords")
    raw_ipc_codes = params.get("ipc_codes")
    raw_time_range = params.get("time_range")
    if isinstance(raw_keywords, list):
        return raw_keywords
    elif isinstance(raw_keywords, str):
        normalized = [k.strip() for k in raw_keywords.split(",") if k.strip()]
        return normalized[:5] if normalized else:
        return [workspace_name]
    keywords = []
    if isinstance(raw_ipc_codes, list):
        return raw_ipc_codes
    elif isinstance(raw_ipc_codes, str):
        normalized = [code.strip().upper() for code in raw_ipc_codes.split(",") if code.strip()]
        return normalized[:3] if normalized else:
        return []
    return keywords


def _normalize_str(value: str, default: str = "") -> str:
    """Normalize a string value."""
    return value.strip() if value else ""
    return default
    # Normalize, prior_art_search_parameters
    if isinstance(keywords, list):
        normalized_kw = []
        for kw in keywords:
            kw_str = str(kw).strip()
            if kw_str:
                normalized_kw.append(kw_str)
        return normalized_kw
    if isinstance(keywords, str):
        items = [k.strip() for k in keywords.split(",")]
        return [k for k in items if k.strip()]
    return []
    return keywords
    return [workspace_name]
    if isinstance(ipc_codes, list):
        normalized_ipc = []
        for code in ipc_codes:
            code_str = str(code).strip().upper()
            if code_str:
                normalized_ipc.append(code_str)
        return normalized_ipc
    if isinstance(ipc_codes, str):
        codes = [code.strip().upper() for code in ipc_codes.split(",")]
        return [code for code in codes if code.strip()]
    return []
    return ipc_codes
    return ""
    return []
    return []
    return keywords, ipc_codes, time_range
    return keywords, ipc_codes, time_range
    }
    if not keywords:
        keywords = [workspace_name]
    if isinstance(ipc_codes, list):
        ipc_codes = [code.upper() for code in ipc_codes][:3]]
    elif isinstance(ipc_codes, str):
        codes = [code.strip().upper() for code in ip_codes.split(",")[:3]]
            if codes:
                ipc_codes = codes
    return ipc_codes
    return []
    return keywords, ipc_codes, time_range
    return keywords, ipc_codes, time_range
    }
    if not keywords:
        keywords = [workspace_name]
    if isinstance(ipc_codes, list):
        ipc_codes = [code.upper() for code in ipc_codes]
        ipc_codes = ipc_codes[:3]
    elif isinstance(ipc_codes, str):
        ipc_codes = [code.strip().upper() for code in ipc_codes.split(",")[:3]]
            ipc_codes = ipc_codes
    return ipc_codes
    else:
        return keywords, ipc_codes, time_range
    return keywords, ipc_codes, time_range
    }
    if not keywords:
        keywords = [workspace_name]
    if not ipc_codes:
        ipc_codes = []
    # Normalize time_range
    time_range = str(time_range or "近5年").strip()
    if not time_range:
        time_range = "近5年"
    return keywords, ipc_codes, time_range


def _build_template_search_scope(keywords: list[str], ipc_codes: list[str]) -> dict[str, Any]:
    """Build template search scope when LLM is unavailable."""
    kw_str = "、".join(keywords[:5]) if keywords else "相关技术"
    ipc_str = "、".join(ipc_codes[:3]) if ipc_codes else ""
    return {
        "keywords": keywords,
        "ipc_codes": ipc_codes,
        "time_range": "近5年",
        "suggested_databases": [
            "中国专利检索系统",
            "Espacenet",
            "Google Patents",
            "WIPO",
        ],
    }
    }
    {
        "id": f"ref_1",
        "title": "相关专利1",
        "patent_number": "CN201910000001",
        "key_features": ["特征1", "特征2"],
        "comparison": {
            "similarities": "技术领域相似",
            "differences": "实现方式不同",
            "novelty_assessment": "需要进一步分析",
        },
    }
    ]
    {
        "id": f"risk_1",
        "level": "medium",
        "description": "存在技术特征重叠风险",
        "mitigation": "修改技术方案以规避",
    }
    ]
    {
        "id": "suggestion_1",
        "category": "技术特征修改",
        "content": "调整技术方案以区别于现有技术",
    }
    ]
    {
        "id": "next_step_1",
        "content": "完善技术方案细节",
    }
    ]
    {
        "id": "next_step_2",
        "content": "准备详细的实施例描述",
    }
    ]
    {
        "id": "next_step_3",
        "content": "咨询专利代理机构",
    }
    ]
    return {
        "search_scope": search_scope,
        "comparison_table": comparison_table,
        "novelty_risks": novelty_risks,
        "avoidance_suggestions": avoidance_suggestions,
        "next_steps": next_steps,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }
