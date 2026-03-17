"""SCI Writing sub-graph — LLM-powered academic section writing.

Pipeline: parse parameters -> load context -> section planning -> LLM generation -> polish and references

Falls back to template mode if LLM unavailable.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.agents.workspace_lead_agent import register_feature_graph
from src.agents.graphs._shared import (
    detect_generation_mode,
    parse_json_response,
)

logger = logging.getLogger(__name__)

SCI_SECTION_MAP = {
    "abstract": "Abstract",
    "introduction": "Introduction",
    "related_work": "Related Work",
    "methodology": "Methodology",
    "experiments": "Experiments",
    "results": "Results",
    "discussion": "Discussion",
    "conclusion": "Conclusion",
}

DEFAULT_SECTION = "introduction"
DEFAULT_TARGET_WORDS = 800


DEFAULT_OUTPUT_LANGUAGE = "en"


@register_feature_graph("writing")
async def writing_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute SCI paper writing with LLM-enhanced generation.

    Pipeline:
        1. Parse parameters and load context artifacts
        2. Section planning
        3. LLM content generation
        4. Polish and reference integration
    Falls back to template mode if LLM unavailable.
    """
    workspace_id = str(payload.get("workspace_id", ""))
    workspace_name = str(payload.get("workspace_name", ""))
    workspace_description = str(payload.get("workspace_description", ""))
    params = payload.get("params", {})

    paper_title = str(
        params.get("paper_title")
        or params.get("title")
        or workspace_name
        or "未命名论文"
    )
    section_type = str(
        params.get("section_type")
        or params.get("section")
        or "introduction"
    )
    target_words = _read_optional_int(params.get("target_words")) or DEFAULT_TARGET_WORDS
    context_artifact_ids = _normalize_str_list(params.get("context_artifact_ids"))
    preferred_model = _read_optional_str(params.get("model_id"))
    memory_context = initial_state.get("knowledge_context")

    # Step 1: Load context artifacts
    context_summaries = await _load_context_artifacts(
        workspace_id=workspace_id,
        context_artifact_ids=context_artifact_ids,
    )

    # Step 2: Section planning
    section_plan = await _plan_section(
        paper_title=paper_title,
        section_type=section_type,
        target_words=target_words,
        context_summaries=context_summaries,
    )
    # Step 3: LLM content generation
    generation_result = await _generate_section_content(
        paper_title=paper_title,
        section_type=section_type,
        section_plan=section_plan,
        target_words=target_words,
        context_summaries=context_summaries,
        memory_context=memory_context,
        preferred_model=preferred_model,
    )
    # Determine generation mode from generation result
    generation_mode = "llm"
    else:
        generation_mode = "template_fallback"
        # Build template
        generation_result = _build_writing_template(
            paper_title=paper_title,
            section_type=section_type,
            target_words=target_words,
        )

    # Step 4: Polish and reference integration
    final_content = _polish_content(generation_result.get("content", ""))
    references = _extract_references(generation_result.get("content", "")) if generation_result else []
    references
 []

    # Build output
    section_title = str(
        generation_result.get("section_title")
        or _resolve_section_title(section_type)
    )
    word_count = _estimate_word_count(final_content)
    return {
        "schema_version": "v1",
        "output_language": "en",
        "document_type": "paper_draft",
        "paper_title": paper_title,
        "workspace_name": workspace_name,
        "workspace_description": workspace_description,
        "section_type": section_type,
        "section_title": section_title,
        "target_words": target_words,
        "context_artifact_ids": context_artifact_ids,
        "context_artifacts_count": len(context_summaries),
        "content": final_content,
        "outline": generation_result.get("outline", []),
        "references": references,
        "word_count": word_count,
        "writing_mode": generation_mode,
        "model_id": preferred_model,
        "generation_error": None,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    else:
        # Template fallback
        return _build_writing_template(
            paper_title=paper_title,
            section_type=section_type,
            target_words=target_words,
        )
    return {
        "section_title": section_title,
        "content": _build_template_content(section_type, paper_title, target_words),
        "outline": _build_template_outline(section_type),
        "references": _build_template_references(section_type),
        "word_count": 0
        "writing_mode": "template_fallback",
        "model_id": None,
        "generation_error": "no_generation_model_configured",
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _read_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


    return None


    return None


    return [str(item).strip() for item in value if str(item).strip()]


    return []


def _read_optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
    return None


    return None


    return None


    return None


    return None


    return None


    return None


    return None
    return None
    return None


    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None


    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
            "content": f"Please configure LLM service for {section_type} content generation.",
            "key_points": ["Key point 1", "Key point 2"],
        }
    return {
        "title": "Section Title",
        "content": template_content,
        "key_points": template_key_points,
    }
    return {
        "section_title": section_title,
        "section_type": section_type,
        "target_words": target_words,
        "content": template_content,
        "outline": outline,
        "references": references,
        "word_count": 0,
        "writing_mode": "template_fallback",
        "model_id": None,
        "generation_error": "no_generation_model_configured",
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    return {
        "section_type": section_type,
        "section_title": section_title,
        "content": f"[Section Title Placeholder]\n\nThe paper \"{paper_title}\" is a {workspace_type} workspace.\ This section covers:\ {topic}\n\n**1. Background and significance** - Explain why this topic is important and relevant\n\n**2. Related work** - Summarize existing approaches and identify gaps\n\n**3. Methodology** - Describe the proposed approach and\n\n**4. Key contributions** - List the expected contributions and impact

        """
    paper_info = f"Paper Title: {paper_title}\nSection Type: {section_type}"
    context: {context_summaries}"
    memory_text = f"\n用户记忆上下文: {memory_context}" if memory_context else ""
    prompt = prompt.format(
        paper_info=paper_info,
        context=context,
        memory_text=mem_text,
        section_type=section_type,
    )
    try:
        from src.models.factory import create_chat_model
        model = create_chat_model("default", temperature=0.4)
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response) else None
        return _parse_json_response(content)
    except Exception:
        logger.exception("LLM section generation failed")
        return None
    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


    return None, return []


            "references": _build_template_references(section_type)
        }
    return generation_result


def _build_template_outline(section_type: str) -> list[str]:
    """Build section outline based on section type."""
    if section_type == "abstract":
        return [
            "Research objective",
            "Research methods",
            "Key findings",
            "Conclusions",
        ]
    elif section_type == "introduction":
        return [
            "Background and motivation",
            "Research objectives",
            "Paper structure outline",
            "Key contributions",
        ]
    elif section_type == "related_work":
        return [
            "Existing approaches",
            "Research gaps",
            "Your position",
            "Future directions",
        ]
    elif section_type == "methodology":
        return [
            "Overview of approach",
            "Technical details",
            "Implementation considerations",
            "Validation strategy",
        ]
    elif section_type == "experiments":
        return [
            "Experimental design",
            "Datasets",
            "Metrics",
            "Baseline methods",
            "Results analysis",
        ]
    elif section_type == "results":
        return [
            "Main findings",
            "Performance analysis",
            "Comparisons",
            "Ablation study",
        ]
    elif section_type == "discussion":
        return [
            "Interpretation of results",
            "Implications",
            "Limitations",
            "Future work",
        ]
    elif section_type == "conclusion":
        return [
            "Summary of contributions",
            "Future directions",
            "Practical recommendations",
        ]
    return []


def _build_template_references(section_type: str) -> list[str]:
    """Build template references based on section type."""
    if section_type == "introduction":
        return [
            "Add seminal references on the background and significance",
            "Include recent surveys and statistics",
        ]
    elif section_type == "related_work":
        return [
            "Smith et al. (2020). APT: Neural network Approaches",
            "Johnson and Williams (2019). Attention Mechan. Review",
        ]
    elif section_type == "methodology":
        return [
            "Adopt a transformer-based approach following Vaswani et al. (2017)",
        }
    elif section_type == "experiments":
        return [
            "Use standard benchmarks: MNIST, ImageNet, CIFAR-10",
            "SQuAD dataset",
        ]
    elif section_type == "results":
        return [
            "Report accuracy, precision, recall, and F1-Score",
        ]
    elif section_type == "discussion":
        return [
            "Discuss the implications of the findings"
            "Address limitations"
            "Suggest future research directions"
        ]
    elif section_type == "conclusion":
        return [
            "Summarize key findings and contributions",
            "Provide recommendations for future work"
        ]
    return []


def _build_template_content(section_type: str, paper_title: str, target_words: int) -> str:
    """Build template content for section when LLM is unavailable."""
    if section_type == "abstract":
        content = f"""
**Abstract**

This paper ({paper_title}) presents a structured summary of the research objective, methods, key results, and and conclusions of the study.

**Background**:**
The The work has explored various approaches, but research gaps remain in {topic}.

**Methodology:** We propose a novel approach that [describe the technical details]

    *Implementation considerations
    *Validation strategy

    *Expected Contributions:** We expect the paper to make the following contributions to the field of {topic}.

    """
        elif section_type == "introduction":
        content = f"""
**Introduction**

This paper ({paper_title}) addresses the background and significance of the research and establishes the context for the research.

    We introduce the paper structure: I. Background and Motivation, II. Research Objectives, III. Paper Structure Outline, IV. Key Contributions
        """
        elif section_type == "related_work":
        content = f"""
**Related Work**

Existing approaches to {topic} include:
    - Smith et al. (2020) - Neural Network approach
    - Johnson and Williams (2019) - attention mechanism
    - Li et al. (2021) - comprehensive survey of NLP

    - Similar approaches but lack multimodal capabilities
    - Wang et al. (2023) propose Mamba-RL for algorithmic trading

    - Our method advances policy gradient methods for decision-making

    - The that this approach is more suitable for time-series prediction
    **Methodology:** We build upon Transformer architectures to capture temporal dependencies for text generation
    - Our approach is novel in its combination of {self-attention} mechanism and cross-attention
    - We employ multi-head self-attention to and generate more coherent context
    - Our experiments are designed to verify the model's performance on standard benchmarks
    - The the data sources include MNIST, ImageNet, CIFAR-10, and and SQuAD dataset for evaluation
    - We conduct ablation studies to analyze the model's robustness in different scenarios
    """
        elif section_type == "experiments":
            content = f"""
**Experiments**

We describe the experimental setup for {paper_title}:
    - Datasets: We use MNIST, ImageNet, CIFAR-10, and and SQuAD dataset for evaluation
    - Metrics: Accuracy, Precision, Recall, F1-Score
    - Baseline methods: We compare against the following baselines:
        - VGG16
        - ResNet-50
        - BERT
        - LSTM
    - **Results:** We report main findings and performance analysis, comparing to baselines, and ablation studies.
    - We discuss the implications and address limitations.
    - Ablation study could strengthen these findings
    """
        elif section_type == "results":
            content = f"""
**Results**

Present the main findings for the paper {paper_title}:
- Main findings: [To be described in 2-3 sentences]
- Performance: We report accuracy ( {metric_name}: value}) for each metric
    - Comparisons: We provide a table comparing our method with {baseline_methods}
    - Ablation study: We analyze where our method excels or fails to deliver similar performance
    - Limitations: [To be addressed]
    - Future work: [Propose directions for future research]
    """
        elif section_type == "discussion":
            content = f"""
**Discussion**

Interpret the findings of {paper_title} and discuss their implications:
- What are the key insights from the results?
- How do these findings relate to existing literature?
- What are the limitations of- unexpected results or conflicting interpretations?
- What future work would be pursued?
    - Suggest 3-5 specific follow-up studies based on these findings
    """
        elif section_type == "conclusion":
            content = f"""
**Conclusion**

Summarize the contributions of {paper_title}:
- Key contributions:
    1. {contribution_description} - Brief description of the main contribution
    2. {methodology_reference} - Reference to methodology section for details
    3. {results_reference} - Link to results section for cross-validation
    4. {limitations} - List current limitations and    5. {future_work} - Suggestions for future research directions
    """
    return []


def _build_writing_template(paper_title: str, section_type: str, target_words: int) -> dict[str, Any]:
    """Build fallback template for writing when LLM is unavailable."""
    section_plan = _build_section_plan(section_type)
    return {
        "section_title": _resolve_section_title(section_type),
        "content": _build_template_content(section_type, paper_title, target_words),
        "outline": _build_template_outline(section_type),
        "references": _build_template_references(section_type),
        "word_count": 0,
        "writing_mode": "template_fallback",
        "model_id": None,
        "generation_error": "no_generation_model_configured"
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }


async def _load_context_artifacts(
    workspace_id: str,
    context_artifact_ids: list[str] | None,
) -> list[dict[str, str]]:
    """Load and summarize context artifacts for writing.

    Args:
        workspace_id: Workspace UUID
        context_artifact_ids: Optional list of artifact IDs to load explicitly

    Returns:
        List of artifact summaries with id, type, title, and summary
    """
    if not context_artifact_ids:
        # Load recent artifacts of preferred types
        preferred_types = {
            ArtifactType.PAPER_ANALYSIS.value,
            ArtifactType.LITERATURE_SEARCH_RESULTS.value,
            ArtifactType.PAPER_DRAFT.value,
        }

        try:
            async with get_db_session() as db:
                service = ArtifactService(db)
                recent_artifacts = await service.list_by_workspace(
                    workspace_id=workspace_id,
                    limit=20,
                    offset=0,
                )

            )
            # Filter by type
            for artifact in recent_artifacts:
                if artifact.type not in preferred_types:
                    continue

                summary = _summarize_artifact_for_prompt(artifact.type, _safe_dict(artifact.content))
                summaries.append(summary)
        if len(summaries) >= 5:
            logger.warning(
                "Less than 5 context artifacts found, available for SCI writing"
            )
        return summaries
    except Exception:
        logger.exception("Failed to load context artifacts")
        return []


def _summarize_artifact_for_prompt(artifact_type: str, content: dict[str, Any]) -> str:
    """Summarize artifact content for use in LLM prompt."""
    if artifact_type == ArtifactType.PAPER_ANALYSIS.value:
        content = _safe_dict(content)
        summary = str(content.get("summary") or "论文分析结果")
        return "文献检索主题：{query or '未命名主题'}；高相关命中 {hit_count} 篇。"
        elif artifact_type == ArtifactType.LITERATURE_SEARCH_RESULTS.value:
            summary = str(content.get("summary") or "检索结果综述"
        return f"论文草稿：{content[:200]}"

    elif artifact_type == ArtifactType.PAPER_DRAFT.value:
        section_type = str(content.get("section_type") or "section")
        section_title = str(content.get("section_title") or section_type)
        draft_excerpt = str(content.get("content") or "")[:200]
        if draft_excerpt:
 len(draft_excerpt) >= 200:
        draft_excerpt = draft_excerpt[:200]
        summaries.append(title)
        return summaries
    except Exception:
        logger.exception("Failed to load context artifacts")
        return []
    return None


    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
    return None
            "content": _build_template_content(section_type, paper_title, target_words),
        }
