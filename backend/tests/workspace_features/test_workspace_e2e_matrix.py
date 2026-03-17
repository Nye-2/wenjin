"""Phase 3 workspace matrix tests (language constraints first)."""

import pytest

from src.workspace_features.services.patent_feature_service import (
    build_patent_outline_payload,
)
from src.workspace_features.services.proposal_feature_service import (
    build_proposal_outline_payload,
)
from src.workspace_features.services.sci_feature_service import (
    SCI_OUTPUT_LANGUAGE,
    _build_sci_writing_template,
    _resolve_section_title,
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


def test_sci_template_payload_is_english_and_marks_output_language() -> None:
    payload = _build_sci_writing_template(
        paper_title="A Test Paper",
        section_type="introduction",
        target_words=1200,
    )
    assert payload["output_language"] == "en"
    assert "The paper" in payload["content"]
    assert "第一段" not in payload["content"]


@pytest.mark.asyncio
async def test_sci_writing_payload_has_schema_and_output_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_load_context_summaries(**kwargs):
        return []

    async def _fake_try_llm(**kwargs):
        return None, None, "no_generation_model_configured"

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


@pytest.mark.asyncio
async def test_proposal_payload_has_required_audit_fields() -> None:
    payload = await build_proposal_outline_payload(
        workspace_id="ws-proposal",
        workspace_name="proposal workspace",
        topic="Project Topic",
        proposal_type="other",
        period_months=24,
    )
    assert payload["generation_mode"] in {"llm", "template_fallback"}
    assert payload["schema_version"] == "v1"
    assert payload["output_language"] == "zh"
    assert payload["generated_at"]


@pytest.mark.asyncio
async def test_patent_payload_has_required_audit_fields() -> None:
    payload = await build_patent_outline_payload(
        workspace_id="ws-patent",
        workspace_name="patent workspace",
        workspace_description="test description",
        innovation_description="test innovation",
        technical_field="computer science",
        application_scenario="edge deployment",
        implementation_method="method details",
    )
    assert payload["generation_mode"] in {"llm", "template_fallback"}
    assert payload["schema_version"] == "v1"
    assert payload["output_language"] == "zh"
    assert payload["generated_at"]


@pytest.mark.asyncio
async def test_copyright_technical_description_payload_has_required_audit_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_load_materials(_: str):
        return None

    async def _fake_try_llm(**kwargs):
        return None, None, "no_generation_model_configured"

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
    assert payload["generation_mode"] in {"llm", "template_fallback"}
    assert payload["schema_version"] == "v1"
    assert payload["output_language"] == "zh"
    assert payload["generated_at"]
