"""Tests for explicit LaTeX bridge sync helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.workspace_features.latex_sync import (
    LatexCompileResult,
    LatexSyncResult,
    compile_thesis_payload,
    sync_background_research_payload,
    sync_experiment_design_payload,
    sync_patent_outline_payload,
    sync_proposal_outline_payload,
    sync_sci_framework_outline_payload,
    sync_sci_writing_payload,
    sync_software_materials_payload,
    sync_software_technical_description_payload,
)


class _AsyncContextManager:
    def __init__(self, value: object) -> None:
        self._value = value

    async def __aenter__(self) -> object:
        return self._value

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        _ = (exc_type, exc, tb)
        return False


@pytest.mark.asyncio
async def test_sync_proposal_outline_payload_returns_bridge_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = object()
    captured: dict[str, object] = {}

    class FakeBridge:
        def __init__(self, db: object) -> None:
            captured["db"] = db

        async def sync_proposal_outline_project(
            self,
            *,
            workspace_id: str,
            project_title: str,
            sections: list[dict[str, object]],
        ) -> tuple[object, dict[str, str]]:
            captured["workspace_id"] = workspace_id
            captured["project_title"] = project_title
            captured["sections"] = sections
            return (
                SimpleNamespace(
                    id="latex-proj-1",
                    main_file="main.tex",
                    llm_config={
                        "metadata": {
                            "sync_conflicts": [
                                {"logical_key": "basis", "path": "sections/01_basis.tex", "reason": "user_modified"}
                            ]
                        }
                    },
                ),
                {"basis": "sections/01_basis.tex"},
            )

    monkeypatch.setattr(
        "src.workspace_features.latex_sync.get_db_session",
        lambda: _AsyncContextManager(fake_db),
    )
    monkeypatch.setattr(
        "src.workspace_features.latex_sync.WorkspaceLatexProjectService",
        FakeBridge,
    )

    result = await sync_proposal_outline_payload(
        workspace_id="ws-proposal",
        workspace_name="Proposal Workspace",
        payload={
            "topic": "Agent Evaluation",
            "sections": [{"id": "basis", "title": "立项依据", "content": "内容"}],
        },
    )

    assert captured == {
        "db": fake_db,
        "workspace_id": "ws-proposal",
        "project_title": "Agent Evaluation",
        "sections": [{"id": "basis", "title": "立项依据", "content": "内容"}],
    }
    assert result == LatexSyncResult(
        latex_project_id="latex-proj-1",
        main_file="main.tex",
        section_map={"basis": "sections/01_basis.tex"},
        sync_conflicts=[{"logical_key": "basis", "path": "sections/01_basis.tex", "reason": "user_modified"}],
    )


@pytest.mark.asyncio
async def test_sync_background_research_payload_prefers_keywords_for_project_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeBridge:
        def __init__(self, db: object) -> None:
            captured["db"] = db

        async def sync_proposal_sections(
            self,
            *,
            workspace_id: str,
            project_title: str,
            sections: list[dict[str, object]],
        ) -> tuple[object, dict[str, str]]:
            captured["workspace_id"] = workspace_id
            captured["project_title"] = project_title
            captured["sections"] = sections
            return (
                SimpleNamespace(
                    id="latex-proj-bg-1",
                    main_file="main.tex",
                    llm_config={"metadata": {}},
                ),
                {"background": "sections/10_background.tex"},
            )

    monkeypatch.setattr(
        "src.workspace_features.latex_sync.get_db_session",
        lambda: _AsyncContextManager(object()),
    )
    monkeypatch.setattr(
        "src.workspace_features.latex_sync.WorkspaceLatexProjectService",
        FakeBridge,
    )

    result = await sync_background_research_payload(
        workspace_id="ws-proposal",
        workspace_name="Workspace Name",
        payload={
            "keywords": "Agent Evaluation",
            "sections": [{"id": "background", "title": "研究背景", "content": "内容"}],
        },
    )

    assert captured["workspace_id"] == "ws-proposal"
    assert captured["project_title"] == "Agent Evaluation"
    assert captured["sections"] == [{"id": "background", "title": "研究背景", "content": "内容"}]
    assert result == LatexSyncResult(
        latex_project_id="latex-proj-bg-1",
        main_file="main.tex",
        section_map={"background": "sections/10_background.tex"},
        sync_conflicts=[],
    )


@pytest.mark.asyncio
async def test_sync_experiment_design_payload_preserves_section_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeBridge:
        def __init__(self, db: object) -> None:
            _ = db

        async def sync_proposal_experiment_design(
            self,
            *,
            workspace_id: str,
            project_title: str,
            payload: dict[str, object],
        ) -> tuple[object, str, dict[str, str]]:
            assert workspace_id == "ws-proposal"
            assert project_title == "Agent Evaluation"
            assert payload["topic"] == "Agent Evaluation"
            return (
                SimpleNamespace(
                    id="latex-proj-2",
                    main_file="main.tex",
                    llm_config={"metadata": {}},
                ),
                "sections/70_experiment_design.tex",
                {"experiment_design": "sections/70_experiment_design.tex"},
            )

    monkeypatch.setattr(
        "src.workspace_features.latex_sync.get_db_session",
        lambda: _AsyncContextManager(object()),
    )
    monkeypatch.setattr(
        "src.workspace_features.latex_sync.WorkspaceLatexProjectService",
        FakeBridge,
    )

    result = await sync_experiment_design_payload(
        workspace_id="ws-proposal",
        workspace_name="Experiment Workspace",
        payload={"topic": "Agent Evaluation", "hypotheses": ["H1"]},
    )

    assert result.as_payload() == {
        "latex_project_id": "latex-proj-2",
        "main_file": "main.tex",
        "section_file": "sections/70_experiment_design.tex",
        "section_map": {"experiment_design": "sections/70_experiment_design.tex"},
        "sync_conflicts": [],
    }


@pytest.mark.asyncio
async def test_sync_patent_outline_payload_prefers_innovation_description_for_project_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeBridge:
        def __init__(self, db: object) -> None:
            captured["db"] = db

        async def sync_patent_outline_project(
            self,
            *,
            workspace_id: str,
            project_title: str,
            sections: list[dict[str, object]],
            claims_draft: dict[str, object],
        ) -> tuple[object, dict[str, str]]:
            captured["workspace_id"] = workspace_id
            captured["project_title"] = project_title
            captured["sections"] = sections
            captured["claims_draft"] = claims_draft
            return (
                SimpleNamespace(
                    id="latex-patent-1",
                    main_file="main.tex",
                    llm_config={"metadata": {}},
                ),
                {"technical_field": "sections/10_technical_field.tex"},
            )

    monkeypatch.setattr(
        "src.workspace_features.latex_sync.get_db_session",
        lambda: _AsyncContextManager(object()),
    )
    monkeypatch.setattr(
        "src.workspace_features.latex_sync.WorkspaceLatexProjectService",
        FakeBridge,
    )

    result = await sync_patent_outline_payload(
        workspace_id="ws-patent",
        workspace_name="Workspace Name",
        payload={
            "innovation_description": "Agent planner",
            "sections": [{"id": "technical_field", "title": "技术领域", "content": "内容"}],
            "claims_draft": {"independent_claims": [{"id": "claim_1", "content": "内容"}]},
        },
    )

    assert captured["workspace_id"] == "ws-patent"
    assert captured["project_title"] == "Agent planner"
    assert captured["sections"] == [{"id": "technical_field", "title": "技术领域", "content": "内容"}]
    assert captured["claims_draft"] == {"independent_claims": [{"id": "claim_1", "content": "内容"}]}
    assert result == LatexSyncResult(
        latex_project_id="latex-patent-1",
        main_file="main.tex",
        section_map={"technical_field": "sections/10_technical_field.tex"},
        sync_conflicts=[],
    )


@pytest.mark.asyncio
async def test_sync_patent_outline_payload_is_best_effort_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeBridge:
        def __init__(self, db: object) -> None:
            _ = db

        async def sync_patent_outline_project(self, **kwargs: object) -> tuple[object, dict[str, str]]:
            _ = kwargs
            raise RuntimeError("bridge unavailable")

    monkeypatch.setattr(
        "src.workspace_features.latex_sync.get_db_session",
        lambda: _AsyncContextManager(object()),
    )
    monkeypatch.setattr(
        "src.workspace_features.latex_sync.WorkspaceLatexProjectService",
        FakeBridge,
    )

    result = await sync_patent_outline_payload(
        workspace_id="ws-patent",
        workspace_name="Patent Workspace",
        payload={
            "innovation_description": "Agent planner",
            "sections": [{"id": "technical_field", "title": "技术领域", "content": "内容"}],
            "claims_draft": {"independent_claims": [{"id": "claim_1", "content": "内容"}]},
        },
    )

    assert result == LatexSyncResult()


@pytest.mark.asyncio
async def test_sync_sci_framework_outline_payload_returns_bridge_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeBridge:
        def __init__(self, db: object) -> None:
            captured["db"] = db

        async def sync_sci_outline_project(
            self,
            *,
            workspace_id: str,
            paper_title: str,
            abstract: str,
            keywords: list[str],
            sections: list[dict[str, object]],
        ) -> tuple[object, dict[str, str]]:
            captured["workspace_id"] = workspace_id
            captured["paper_title"] = paper_title
            captured["abstract"] = abstract
            captured["keywords"] = keywords
            captured["sections"] = sections
            return (
                SimpleNamespace(
                    id="latex-sci-1",
                    main_file="main.tex",
                    llm_config={
                        "metadata": {
                            "sync_conflicts": [
                                {
                                    "logical_key": "introduction",
                                    "path": "sections/introduction.tex",
                                    "reason": "user_modified",
                                }
                            ]
                        }
                    },
                ),
                {"introduction": "sections/introduction.tex"},
            )

    monkeypatch.setattr(
        "src.workspace_features.latex_sync.get_db_session",
        lambda: _AsyncContextManager(object()),
    )
    monkeypatch.setattr(
        "src.workspace_features.latex_sync.WorkspaceLatexProjectService",
        FakeBridge,
    )

    result = await sync_sci_framework_outline_payload(
        workspace_id="ws-sci",
        workspace_name="SCI Workspace",
        payload={
            "paper_title": "Paper Title",
            "abstract": "Abstract",
            "keywords": ["agents"],
            "sections": [{"title": "Introduction", "focus": "Background"}],
        },
    )

    assert captured["workspace_id"] == "ws-sci"
    assert captured["paper_title"] == "Paper Title"
    assert captured["abstract"] == "Abstract"
    assert captured["keywords"] == ["agents"]
    assert result == LatexSyncResult(
        latex_project_id="latex-sci-1",
        main_file="main.tex",
        section_map={"introduction": "sections/introduction.tex"},
        sync_conflicts=[
            {
                "logical_key": "introduction",
                "path": "sections/introduction.tex",
                "reason": "user_modified",
            }
        ],
    )


@pytest.mark.asyncio
async def test_sync_sci_writing_payload_preserves_section_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeBridge:
        def __init__(self, db: object) -> None:
            _ = db

        async def sync_sci_section_draft(
            self,
            *,
            workspace_id: str,
            paper_title: str,
            section_type: str,
            section_title: str,
            content: str,
        ) -> tuple[object, str, dict[str, str]]:
            assert workspace_id == "ws-sci"
            assert paper_title == "Paper Title"
            assert section_type == "introduction"
            assert section_title == "Introduction"
            assert content == "Draft content"
            return (
                SimpleNamespace(
                    id="latex-sci-2",
                    main_file="main.tex",
                    llm_config={"metadata": {}},
                ),
                "sections/introduction.tex",
                {"introduction": "sections/introduction.tex"},
            )

    monkeypatch.setattr(
        "src.workspace_features.latex_sync.get_db_session",
        lambda: _AsyncContextManager(object()),
    )
    monkeypatch.setattr(
        "src.workspace_features.latex_sync.WorkspaceLatexProjectService",
        FakeBridge,
    )

    result = await sync_sci_writing_payload(
        workspace_id="ws-sci",
        workspace_name="SCI Workspace",
        payload={
            "paper_title": "Paper Title",
            "section_type": "introduction",
            "section_title": "Introduction",
            "content": "Draft content",
        },
    )

    assert result.as_payload() == {
        "latex_project_id": "latex-sci-2",
        "main_file": "main.tex",
        "section_file": "sections/introduction.tex",
        "section_map": {"introduction": "sections/introduction.tex"},
        "sync_conflicts": [],
    }


@pytest.mark.asyncio
async def test_sync_sci_writing_payload_falls_back_to_workspace_name_when_title_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeBridge:
        def __init__(self, db: object) -> None:
            _ = db

        async def sync_sci_section_draft(
            self,
            *,
            workspace_id: str,
            paper_title: str,
            section_type: str,
            section_title: str,
            content: str,
        ) -> tuple[object, str, dict[str, str]]:
            assert workspace_id == "ws-sci"
            assert paper_title == "SCI Workspace"
            assert section_type == "introduction"
            assert section_title == "Introduction"
            assert content == "Draft content"
            return (
                SimpleNamespace(
                    id="latex-sci-3",
                    main_file="main.tex",
                    llm_config={"metadata": {}},
                ),
                "sections/introduction.tex",
                {"introduction": "sections/introduction.tex"},
            )

    monkeypatch.setattr(
        "src.workspace_features.latex_sync.get_db_session",
        lambda: _AsyncContextManager(object()),
    )
    monkeypatch.setattr(
        "src.workspace_features.latex_sync.WorkspaceLatexProjectService",
        FakeBridge,
    )

    result = await sync_sci_writing_payload(
        workspace_id="ws-sci",
        workspace_name="SCI Workspace",
        payload={
            "paper_title": "",
            "section_type": "introduction",
            "section_title": "Introduction",
            "content": "Draft content",
        },
    )

    assert result.as_payload() == {
        "latex_project_id": "latex-sci-3",
        "main_file": "main.tex",
        "section_file": "sections/introduction.tex",
        "section_map": {"introduction": "sections/introduction.tex"},
        "sync_conflicts": [],
    }


@pytest.mark.asyncio
async def test_sync_software_technical_description_payload_returns_bridge_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeBridge:
        def __init__(self, db: object) -> None:
            _ = db

        async def sync_software_copyright_technical_description(
            self,
            *,
            workspace_id: str,
            project_title: str,
            sections: dict[str, object],
        ) -> tuple[object, dict[str, str]]:
            assert workspace_id == "ws-soft"
            assert project_title == "Agent Studio"
            assert sections["system_overview"]["title"] == "系统概述"
            return (
                SimpleNamespace(
                    id="latex-soft-1",
                    main_file="main.tex",
                    llm_config={"metadata": {"sync_conflicts": []}},
                ),
                {"system_overview": "sections/01_system_overview.tex"},
            )

    monkeypatch.setattr(
        "src.workspace_features.latex_sync.get_db_session",
        lambda: _AsyncContextManager(object()),
    )
    monkeypatch.setattr(
        "src.workspace_features.latex_sync.WorkspaceLatexProjectService",
        FakeBridge,
    )

    result = await sync_software_technical_description_payload(
        workspace_id="ws-soft",
        workspace_name="Software Workspace",
        payload={
            "software_profile": {"software_name": "Agent Studio"},
            "sections": {"system_overview": {"title": "系统概述", "content": "内容"}},
        },
    )

    assert result == LatexSyncResult(
        latex_project_id="latex-soft-1",
        main_file="main.tex",
        section_map={"system_overview": "sections/01_system_overview.tex"},
        sync_conflicts=[],
    )


@pytest.mark.asyncio
async def test_sync_software_materials_payload_preserves_section_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeBridge:
        def __init__(self, db: object) -> None:
            _ = db

        async def sync_software_copyright_materials(
            self,
            *,
            workspace_id: str,
            project_title: str,
            required_materials: list[dict[str, object]],
            review_checklist: list[str],
        ) -> tuple[object, str, dict[str, str]]:
            assert workspace_id == "ws-soft"
            assert project_title == "Agent Studio"
            assert required_materials[0]["id"] == "application_form"
            assert review_checklist
            return (
                SimpleNamespace(
                    id="latex-soft-2",
                    main_file="main.tex",
                    llm_config={"metadata": {"sync_conflicts": []}},
                ),
                "sections/70_materials_checklist.tex",
                {"materials_checklist": "sections/70_materials_checklist.tex"},
            )

    monkeypatch.setattr(
        "src.workspace_features.latex_sync.get_db_session",
        lambda: _AsyncContextManager(object()),
    )
    monkeypatch.setattr(
        "src.workspace_features.latex_sync.WorkspaceLatexProjectService",
        FakeBridge,
    )

    result = await sync_software_materials_payload(
        workspace_id="ws-soft",
        workspace_name="Software Workspace",
        payload={
            "software_profile": {"software_name": "Agent Studio"},
            "required_materials": [{"id": "application_form"}],
            "review_checklist": ["核对项"],
        },
    )

    assert result.as_payload() == {
        "latex_project_id": "latex-soft-2",
        "main_file": "main.tex",
        "section_file": "sections/70_materials_checklist.tex",
        "section_map": {"materials_checklist": "sections/70_materials_checklist.tex"},
        "sync_conflicts": [],
    }


@pytest.mark.asyncio
async def test_compile_thesis_payload_returns_compile_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = object()
    captured: dict[str, object] = {}

    class FakeBridge:
        def __init__(self, db: object) -> None:
            captured["bridge_db"] = db

        async def sync_project(self, **kwargs: object) -> object:
            captured["sync_kwargs"] = kwargs
            return SimpleNamespace(
                id="latex-thesis-1",
                main_file="main.tex",
                llm_config={
                    "metadata": {
                        "sync_conflicts": [
                            {"logical_key": "project:main", "path": "main.tex", "reason": "user_modified"}
                        ]
                    }
                },
            )

    class FakeCompileService:
        def __init__(self, db: object) -> None:
            captured["compile_db"] = db

        async def compile_project(self, project: object, *, main_file: str, engine: str) -> dict[str, object]:
            captured["compile_project"] = project
            captured["compile_main_file"] = main_file
            captured["compile_engine"] = engine
            return {
                "ok": True,
                "pdf_path": "/tmp/main.pdf",
                "pdf_endpoint": "/api/latex/projects/latex-thesis-1/compile/history-1/pdf",
                "log": "ok",
                "error": None,
                "page_count": 12,
            }

    monkeypatch.setattr(
        "src.workspace_features.latex_sync.get_db_session",
        lambda: _AsyncContextManager(fake_db),
    )
    monkeypatch.setattr(
        "src.workspace_features.latex_sync.WorkspaceLatexProjectService",
        FakeBridge,
    )
    monkeypatch.setattr(
        "src.workspace_features.latex_sync.LatexCompileService",
        FakeCompileService,
    )

    result = await compile_thesis_payload(
        workspace_id="ws-thesis",
        payload={
            "paper_title": "Thesis Title",
            "main_file": "main.tex",
            "latex_content": "\\documentclass{article}",
            "bib_content": "",
            "template": "default",
            "compiler": "xelatex",
            "bibliography_style": "gbt7714",
            "output_language": "zh",
            "source_summary": {"chapter_count": 1},
        },
    )

    assert captured["bridge_db"] is fake_db
    assert captured["compile_db"] is fake_db
    assert captured["compile_main_file"] == "main.tex"
    assert captured["compile_engine"] == "xelatex"
    assert result == LatexCompileResult(
        latex_project_id="latex-thesis-1",
        main_file="main.tex",
        compile_status="success",
        pdf_path="/tmp/main.pdf",
        pdf_url="/api/latex/projects/latex-thesis-1/compile/history-1/pdf",
        pdf_endpoint="/api/latex/projects/latex-thesis-1/compile/history-1/pdf",
        page_count=12,
        compile_error=None,
        compile_logs="ok",
        sync_conflicts=[{"logical_key": "project:main", "path": "main.tex", "reason": "user_modified"}],
    )


@pytest.mark.asyncio
async def test_compile_thesis_payload_forwards_template_assets_to_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeBridge:
        def __init__(self, db: object) -> None:
            captured["bridge_db"] = db

        async def sync_project(self, **kwargs: object) -> object:
            captured["sync_kwargs"] = kwargs
            return SimpleNamespace(
                id="latex-thesis-2",
                main_file="main.tex",
                llm_config={"metadata": {}},
            )

    class FakeCompileService:
        def __init__(self, db: object) -> None:
            captured["compile_db"] = db

        async def compile_project(self, project: object, *, main_file: str, engine: str) -> dict[str, object]:
            captured["compile_project"] = project
            captured["compile_main_file"] = main_file
            captured["compile_engine"] = engine
            return {
                "ok": True,
                "pdf_path": "/tmp/main.pdf",
                "pdf_endpoint": "/api/latex/projects/latex-thesis-2/compile/history-1/pdf",
                "log": "ok",
                "error": None,
                "page_count": 5,
            }

    monkeypatch.setattr(
        "src.workspace_features.latex_sync.get_db_session",
        lambda: _AsyncContextManager(object()),
    )
    monkeypatch.setattr(
        "src.workspace_features.latex_sync.WorkspaceLatexProjectService",
        FakeBridge,
    )
    monkeypatch.setattr(
        "src.workspace_features.latex_sync.LatexCompileService",
        FakeCompileService,
    )

    result = await compile_thesis_payload(
        workspace_id="ws-thesis",
        payload={
            "paper_title": "Thesis Title",
            "main_file": "main.tex",
            "latex_content": "\\documentclass{custom_thesis}",
            "bib_content": "",
            "template_assets": [{"path": "custom_thesis.cls", "content": "\\ProvidesClass{custom_thesis}"}],
            "template": "default",
            "compiler": "xelatex",
        },
    )

    assert captured["sync_kwargs"]["extra_files"] == [
        {"path": "custom_thesis.cls", "content": "\\ProvidesClass{custom_thesis}"}
    ]
    assert captured["compile_main_file"] == "main.tex"
    assert captured["compile_engine"] == "xelatex"
    assert result.latex_project_id == "latex-thesis-2"
    assert result.compile_status == "success"


@pytest.mark.asyncio
async def test_compile_thesis_payload_raises_on_pipeline_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingBridge:
        def __init__(self, db: object) -> None:
            _ = db

        async def sync_project(self, **kwargs: object) -> object:
            _ = kwargs
            raise RuntimeError("bridge unavailable")

    monkeypatch.setattr(
        "src.workspace_features.latex_sync.get_db_session",
        lambda: _AsyncContextManager(object()),
    )
    monkeypatch.setattr(
        "src.workspace_features.latex_sync.WorkspaceLatexProjectService",
        FailingBridge,
    )

    with pytest.raises(RuntimeError, match="linked_latex_pipeline_failed"):
        await compile_thesis_payload(
            workspace_id="ws-thesis",
            payload={
                "paper_title": "Thesis Title",
                "latex_content": "\\documentclass{article}",
                "bib_content": "",
                "template": "default",
                "compiler": "xelatex",
            },
        )
