"""Phase 3 workspace matrix tests (language constraints first)."""

import pytest

from src.workspace_features.services.patent_feature_service import (
    build_patent_outline_payload,
)
from src.workspace_features.services.proposal_feature_service import (
    build_experiment_design_payload,
    build_proposal_outline_payload,
)
from src.workspace_features.services.sci_feature_service import (
    SCI_OUTPUT_LANGUAGE,
    _resolve_section_title,
    build_framework_outline_payload,
    build_journal_recommend_payload,
    build_peer_review_payload,
    build_sci_literature_review_payload,
    build_sci_writing_payload,
)
from src.workspace_features.services.software_copyright_feature_service import (
    build_technical_description_payload,
)
from src.workspace_features.services.thesis_feature_service import (
    resolve_thesis_output_language,
)


def test_thesis_output_language_is_forced_to_zh_for_any_template() -> None:
    assert resolve_thesis_output_language("default") == "zh"
    assert resolve_thesis_output_language("ieee") == "zh"
    assert resolve_thesis_output_language("english") == "zh"


def test_sci_output_language_constant_is_en() -> None:
    assert SCI_OUTPUT_LANGUAGE == "en"


def test_sci_section_title_uses_english_labels() -> None:
    assert _resolve_section_title("introduction") == "Introduction"
    assert _resolve_section_title("methodology") == "Methodology"
    assert _resolve_section_title("unknown_section") == "Section"


@pytest.mark.asyncio
async def test_sci_writing_payload_has_schema_and_output_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_load_context_summaries(**kwargs):
        return []

    async def _fake_try_llm(**kwargs):
        _ = kwargs
        return (
            {
                "section_title": "Introduction",
                "content": "This is an introduction section.",
                "outline": ["Background", "Problem"],
                "references": ["Ref A"],
                "output_language": "en",
                "writing_mode": "llm",
            },
            "mock-model",
            None,
        )

    monkeypatch.setattr(
        "src.workspace_features.services.sci_feature_service._load_artifact_context_summaries",
        _fake_load_context_summaries,
    )
    monkeypatch.setattr(
        "src.workspace_features.services.sci_feature_service._try_llm_sci_writing",
        _fake_try_llm,
    )

    payload = await build_sci_writing_payload(
        workspace_id="ws-sci",
        workspace_name="SCI Workspace",
        workspace_description="desc",
        paper_title="A Test Paper",
        section_type="introduction",
        target_words=800,
    )
    assert payload["schema_version"] == "v1"
    assert payload["output_language"] == "en"
    assert payload["section_title"] == "Introduction"
    assert payload["generation_error"] is None
    assert "latex_project_id" not in payload


@pytest.mark.asyncio
async def test_sci_literature_review_payload_has_required_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_load_context_summaries(**kwargs):
        _ = kwargs
        return []

    async def _fake_load_workspace_literature(_: str):
        return []

    async def _fake_try_llm(**kwargs):
        _ = kwargs
        return (
            {
                "summary": "Review summary",
                "sections": [{"title": "Background", "content": "Content"}],
                "key_papers": [{"title": "Paper A", "reason": "Foundational"}],
                "research_gaps": ["Gap A"],
                "next_actions": ["Action A"],
            },
            "mock-model",
            None,
        )

    monkeypatch.setattr(
        "src.workspace_features.services.sci_feature_service._load_artifact_context_summaries",
        _fake_load_context_summaries,
    )
    monkeypatch.setattr(
        "src.workspace_features.services.sci_feature_service._load_workspace_literature",
        _fake_load_workspace_literature,
    )
    monkeypatch.setattr(
        "src.workspace_features.services.sci_feature_service._try_llm_literature_review",
        _fake_try_llm,
    )

    payload = await build_sci_literature_review_payload(
        workspace_id="ws-sci",
        topic="LLM planning",
    )
    assert payload["schema_version"] == "v1"
    assert payload["output_language"] == "en"
    assert payload["document_type"] == "literature_review"
    assert payload["generation_error"] is None


@pytest.mark.asyncio
async def test_sci_framework_outline_payload_has_required_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_load_context_summaries(**kwargs):
        _ = kwargs
        return []

    async def _fake_try_llm(**kwargs):
        _ = kwargs
        return (
            {
                "abstract": "Abstract",
                "keywords": ["LLM"],
                "sections": [{"title": "Introduction", "focus": "Background"}],
                "contributions": ["Contribution A"],
            },
            "mock-model",
            None,
        )

    monkeypatch.setattr(
        "src.workspace_features.services.sci_feature_service._load_artifact_context_summaries",
        _fake_load_context_summaries,
    )
    monkeypatch.setattr(
        "src.workspace_features.services.sci_feature_service._try_llm_framework_outline",
        _fake_try_llm,
    )

    payload = await build_framework_outline_payload(
        workspace_id="ws-sci",
        paper_title="Paper Title",
        topic="LLM planning",
    )
    assert payload["schema_version"] == "v1"
    assert payload["document_type"] == "framework_outline"
    assert payload["output_language"] == "en"
    assert payload["generation_error"] is None
    assert "latex_project_id" not in payload


@pytest.mark.asyncio
async def test_sci_review_and_journal_payloads_have_required_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_review(**kwargs):
        _ = kwargs
        return (
            {
                "overall_assessment": "Strong draft",
                "score": 7.8,
                "strengths": ["A"],
                "weaknesses": ["B"],
                "revision_actions": ["C"],
            },
            "mock-model",
            None,
        )

    async def _fake_journal(**kwargs):
        _ = kwargs
        return (
            {
                "paper_profile": "Profile",
                "journals": [{"name": "Journal A", "fit": "High", "reason": "Reason"}],
                "submission_notes": ["Note A"],
            },
            "mock-model",
            None,
        )

    monkeypatch.setattr(
        "src.workspace_features.services.sci_feature_service._try_llm_peer_review",
        _fake_review,
    )
    monkeypatch.setattr(
        "src.workspace_features.services.sci_feature_service._try_llm_journal_recommend",
        _fake_journal,
    )

    review_payload = await build_peer_review_payload(
        paper_title="Paper Title",
        manuscript_excerpt="Draft excerpt",
    )
    journal_payload = await build_journal_recommend_payload(
        paper_title="Paper Title",
        abstract="Abstract",
    )

    assert review_payload["document_type"] == "review"
    assert review_payload["generation_error"] is None
    assert journal_payload["document_type"] == "summary"
    assert journal_payload["generation_error"] is None


@pytest.mark.asyncio
async def test_proposal_payload_has_required_audit_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_try_generate_proposal_sections(**kwargs):
        _ = kwargs
        return (
            [
                {"id": "basis", "title": "立项依据", "content": "内容", "source": "llm"},
                {"id": "objectives", "title": "研究目标与内容", "content": "内容", "source": "llm"},
                {"id": "methodology", "title": "研究方案与技术路线", "content": "内容", "source": "llm"},
                {"id": "schedule", "title": "计划进度", "content": "内容", "source": "llm"},
                {"id": "budget", "title": "经费预算框架", "content": "内容", "source": "llm"},
            ],
            "mock-model",
            None,
        )

    monkeypatch.setattr(
        "src.workspace_features.services.proposal_feature_service._try_generate_proposal_sections",
        _fake_try_generate_proposal_sections,
    )

    payload = await build_proposal_outline_payload(
        workspace_id="ws-proposal",
        workspace_name="proposal workspace",
        topic="Project Topic",
        proposal_type="other",
        period_months=24,
    )
    assert payload["generation_mode"] == "llm"
    assert payload["schema_version"] == "v1"
    assert payload["output_language"] == "zh"
    assert payload["generated_at"]
    assert payload["generation_error"] is None
    assert "latex_project_id" not in payload


@pytest.mark.asyncio
async def test_experiment_design_payload_has_required_audit_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_try_llm(**kwargs):
        _ = kwargs
        return (
            {
                "hypotheses": ["H1"],
                "variables": [{"name": "x", "definition": "factor", "type": "independent"}],
                "procedure": ["step1"],
                "evaluation": ["metric1"],
                "risks": ["risk1"],
            },
            "mock-model",
            None,
        )

    monkeypatch.setattr(
        "src.workspace_features.services.proposal_feature_service._try_llm_experiment_design",
        _fake_try_llm,
    )

    payload = await build_experiment_design_payload(
        topic="Agent evaluation",
        objective="Design an experiment plan",
    )
    assert payload["schema_version"] == "v1"
    assert payload["document_type"] == "methodology"
    assert payload["output_language"] == "zh"
    assert payload["generation_error"] is None


@pytest.mark.asyncio
async def test_patent_payload_has_required_audit_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_try_generate_patent_outline_llm(**kwargs):
        _ = kwargs
        return (
            {
                "sections": [
                    {"id": "technical_field", "title": "技术领域", "content": "内容"},
                    {"id": "background_art", "title": "背景技术", "content": "内容"},
                    {"id": "invention_content", "title": "发明内容", "content": "内容"},
                    {"id": "drawings_description", "title": "附图说明", "content": "内容"},
                    {"id": "detailed_implementation", "title": "具体实施方式", "content": "内容"},
                ],
                "claims_draft": {
                    "independent_claims": [{"id": "claim_1", "content": "内容"}],
                    "dependent_claims": [{"id": "claim_2", "content": "内容"}],
                },
            },
            "mock-model",
            None,
        )

    monkeypatch.setattr(
        "src.workspace_features.services.patent_feature_service._try_generate_patent_outline_llm",
        _fake_try_generate_patent_outline_llm,
    )

    payload = await build_patent_outline_payload(
        workspace_id="ws-patent",
        workspace_name="patent workspace",
        workspace_description="test description",
        innovation_description="test innovation",
        technical_field="computer science",
        application_scenario="edge deployment",
        implementation_method="method details",
    )
    assert payload["generation_mode"] == "llm"
    assert payload["schema_version"] == "v1"
    assert payload["output_language"] == "zh"
    assert payload["generated_at"]
    assert payload["generation_error"] is None


@pytest.mark.asyncio
async def test_copyright_technical_description_payload_has_required_audit_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_load_materials(_: str):
        return None

    async def _fake_try_llm(**kwargs):
        _ = kwargs
        return (
            {
                "system_overview": {"title": "系统概述", "content": "内容", "source": "llm"},
                "module_design": {"title": "模块设计", "content": "内容", "source": "llm", "modules": ["m1"]},
                "data_flow": {"title": "数据流程", "content": "内容", "source": "llm"},
                "deployment_architecture": {
                    "title": "部署架构",
                    "content": "内容",
                    "source": "llm",
                    "architecture_type": "B/S",
                },
                "security_and_permissions": {"title": "安全与权限", "content": "内容", "source": "llm"},
                "operation_steps": {"title": "操作步骤", "content": "内容", "source": "llm", "steps": ["s1"]},
            },
            "mock-model",
            None,
        )

    monkeypatch.setattr(
        "src.workspace_features.services.software_copyright_feature_service._load_copyright_materials_artifact",
        _fake_load_materials,
    )
    monkeypatch.setattr(
        "src.workspace_features.services.software_copyright_feature_service._try_generate_technical_sections",
        _fake_try_llm,
    )

    payload = await build_technical_description_payload(
        workspace_id="ws-copyright",
        workspace_name="copyright workspace",
        workspace_description="desc",
        software_name="App Name",
        version="V1.0",
        core_modules=["module-a"],
        deployment_architecture="B/S",
        database_middleware=["PostgreSQL"],
        interface_protocols=["REST"],
        highlights=["feature-a"],
    )
    assert payload["generation_mode"] == "llm"
    assert payload["schema_version"] == "v1"
    assert payload["output_language"] == "zh"
    assert payload["generated_at"]
    assert payload["generation_error"] is None
