"""Tests for thesis_feature_service compile payload behavior."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from src.workspace_features.services import thesis_feature_service


@pytest.mark.asyncio
async def test_build_compile_payload_uses_abstract_override_and_keywords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_load_workspace_artifacts(_workspace_id: str):
        return [
            SimpleNamespace(
                type="thesis_chapter",
                title="绪论",
                content={
                    "chapter_index": 0,
                    "chapter_title": "绪论",
                    "markdown": "# 绪论\n\n这是章节正文。",
                },
                created_at="2026-03-20T00:00:00+00:00",
            )
        ]

    async def _fake_load_workspace_literature(_workspace_id: str):
        return []

    @asynccontextmanager
    async def _fake_db_session():
        yield object()

    monkeypatch.setattr(
        thesis_feature_service,
        "_load_workspace_artifacts",
        _fake_load_workspace_artifacts,
    )
    monkeypatch.setattr(
        thesis_feature_service,
        "_load_workspace_literature",
        _fake_load_workspace_literature,
    )
    monkeypatch.setattr(
        thesis_feature_service,
        "get_db_session",
        _fake_db_session,
    )

    payload = await thesis_feature_service.build_compile_payload(
        workspace_id="ws-1",
        workspace_name="测试论文",
        workspace_description="默认摘要",
        thread_id="thread-1",
        template="default",
        compiler="xelatex",
        bibliography_style="gbt7714",
        abstract_override="这是覆盖后的摘要内容。",
        keywords_override=["关键词A", "关键词B"],
    )

    assert payload["abstract_source"] == "llm_override"
    assert payload["keywords"] == ["关键词A", "关键词B"]
    assert "这是覆盖后的摘要内容。" in payload["latex_content"]
    assert "关键词A" in payload["latex_content"]
    assert "关键词B" in payload["latex_content"]
    assert "latex_project_id" not in payload
    assert "compile_status" not in payload


@pytest.mark.asyncio
async def test_build_compile_payload_ignores_legacy_latex_project_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_load_workspace_artifacts(_workspace_id: str):
        return [
            SimpleNamespace(
                type="latex_project",
                title="论文主稿 LaTeX",
                content={
                    "paper_title": "可编辑主稿",
                    "main_tex": "\\documentclass{article}\n\\begin{document}\nHello Panel\n\\end{document}",
                    "bib_tex": "@article{demo,title={Demo}}",
                },
                created_at="2026-03-20T00:00:00+00:00",
                updated_at="2026-03-20T01:00:00+00:00",
                id="artifact-latex-1",
            ),
            SimpleNamespace(
                type="thesis_chapter",
                title="绪论",
                content={
                    "chapter_index": 0,
                    "chapter_title": "绪论",
                    "markdown": "# 绪论\n\n这是章节正文。",
                },
                created_at="2026-03-20T00:00:00+00:00",
            ),
        ]

    async def _fake_load_workspace_literature(_workspace_id: str):
        return []

    @asynccontextmanager
    async def _fake_db_session():
        yield object()

    monkeypatch.setattr(
        thesis_feature_service,
        "_load_workspace_artifacts",
        _fake_load_workspace_artifacts,
    )
    monkeypatch.setattr(
        thesis_feature_service,
        "_load_workspace_literature",
        _fake_load_workspace_literature,
    )
    monkeypatch.setattr(
        thesis_feature_service,
        "get_db_session",
        _fake_db_session,
    )

    payload = await thesis_feature_service.build_compile_payload(
        workspace_id="ws-1",
        workspace_name="测试论文",
        workspace_description="默认摘要",
        thread_id="thread-1",
        template="default",
        compiler="xelatex",
        bibliography_style="gbt7714",
    )

    assert payload["paper_title"] == "测试论文"
    assert "Hello Panel" not in payload["latex_content"]
    assert "这是章节正文。" in payload["latex_content"]
    assert payload["bib_content"] == ""
    assert "latex_project_artifact_id" not in payload["source_summary"]
    assert "latex_project_id" not in payload
    assert "compile_status" not in payload


@pytest.mark.asyncio
async def test_build_compile_payload_falls_back_to_outline_keywords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_load_workspace_artifacts(_workspace_id: str):
        return [
            SimpleNamespace(
                type="framework_outline",
                title="论文大纲",
                content={
                    "paper_title": "轮廓标题",
                    "outline": {
                        "abstract": "轮廓摘要",
                        "keywords": ["关键词甲", "关键词乙"],
                    },
                },
                created_at="2026-03-20T00:00:00+00:00",
            ),
            SimpleNamespace(
                type="thesis_chapter",
                title="绪论",
                content={
                    "chapter_index": 0,
                    "chapter_title": "绪论",
                    "markdown": "# 绪论\n\n这是章节正文。",
                },
                created_at="2026-03-20T00:00:00+00:00",
            ),
        ]

    async def _fake_load_workspace_literature(_workspace_id: str):
        return []

    @asynccontextmanager
    async def _fake_db_session():
        yield object()

    class FakeTemplateService:
        def __init__(self, db: object) -> None:
            _ = db

        async def get_active(self, workspace_id: str):
            _ = workspace_id
            return None

    monkeypatch.setattr(
        thesis_feature_service,
        "_load_workspace_artifacts",
        _fake_load_workspace_artifacts,
    )
    monkeypatch.setattr(
        thesis_feature_service,
        "_load_workspace_literature",
        _fake_load_workspace_literature,
    )
    monkeypatch.setattr(
        thesis_feature_service,
        "get_db_session",
        _fake_db_session,
    )
    monkeypatch.setattr(
        "src.services.template_service.TemplateService",
        FakeTemplateService,
    )

    payload = await thesis_feature_service.build_compile_payload(
        workspace_id="ws-1",
        workspace_name="测试论文",
        workspace_description="默认摘要",
        thread_id="thread-1",
        template="default",
        compiler="xelatex",
        bibliography_style="gbt7714",
    )

    assert payload["paper_title"] == "轮廓标题"
    assert payload["keywords"] == ["关键词甲", "关键词乙"]
    assert "关键词甲" in payload["latex_content"]
    assert "关键词乙" in payload["latex_content"]


@pytest.mark.asyncio
async def test_build_compile_payload_uses_uploaded_latex_template_preamble(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_load_workspace_artifacts(_workspace_id: str):
        return [
            SimpleNamespace(
                type="thesis_chapter",
                title="绪论",
                content={
                    "chapter_index": 0,
                    "chapter_title": "绪论",
                    "markdown": "# 绪论\n\n这是章节正文。",
                },
                created_at="2026-03-20T00:00:00+00:00",
            )
        ]

    async def _fake_load_workspace_literature(_workspace_id: str):
        return []

    @asynccontextmanager
    async def _fake_db_session():
        yield object()

    class FakeTemplateService:
        def __init__(self, db: object) -> None:
            _ = db

        async def get_active(self, workspace_id: str):
            _ = workspace_id
            return SimpleNamespace(
                latex_preamble=(
                    "\\documentclass{article}\n"
                    "\\usepackage{geometry}\n"
                    "\\begin{document}\n"
                    "Template Body\n"
                    "\\end{document}\n"
                )
            )

    monkeypatch.setattr(
        thesis_feature_service,
        "_load_workspace_artifacts",
        _fake_load_workspace_artifacts,
    )
    monkeypatch.setattr(
        thesis_feature_service,
        "_load_workspace_literature",
        _fake_load_workspace_literature,
    )
    monkeypatch.setattr(
        thesis_feature_service,
        "get_db_session",
        _fake_db_session,
    )
    monkeypatch.setattr(
        "src.services.template_service.TemplateService",
        FakeTemplateService,
    )

    payload = await thesis_feature_service.build_compile_payload(
        workspace_id="ws-1",
        workspace_name="测试论文",
        workspace_description="默认摘要",
        thread_id="thread-1",
        template="default",
        compiler="xelatex",
        bibliography_style="apalike",
    )

    assert "\\documentclass{article}" in payload["latex_content"]
    assert "\\bibliographystyle{apalike}" in payload["latex_content"]
    assert "Template Body" not in payload["latex_content"]
    assert "这是章节正文。" in payload["latex_content"]


@pytest.mark.asyncio
async def test_build_compile_payload_uses_uploaded_latex_class_template_asset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_load_workspace_artifacts(_workspace_id: str):
        return [
            SimpleNamespace(
                type="thesis_chapter",
                title="绪论",
                content={
                    "chapter_index": 0,
                    "chapter_title": "绪论",
                    "markdown": "# 绪论\n\n这是章节正文。",
                },
                created_at="2026-03-20T00:00:00+00:00",
            )
        ]

    async def _fake_load_workspace_literature(_workspace_id: str):
        return []

    @asynccontextmanager
    async def _fake_db_session():
        yield object()

    class FakeTemplateService:
        def __init__(self, db: object) -> None:
            _ = db

        async def get_active(self, workspace_id: str):
            _ = workspace_id
            return SimpleNamespace(
                source_file_path="/tmp/custom_thesis.cls",
                latex_preamble=(
                    "\\NeedsTeXFormat{LaTeX2e}\n"
                    "\\ProvidesClass{custom_thesis}\n"
                    "\\LoadClass{ctexart}\n"
                ),
            )

    monkeypatch.setattr(
        thesis_feature_service,
        "_load_workspace_artifacts",
        _fake_load_workspace_artifacts,
    )
    monkeypatch.setattr(
        thesis_feature_service,
        "_load_workspace_literature",
        _fake_load_workspace_literature,
    )
    monkeypatch.setattr(
        thesis_feature_service,
        "get_db_session",
        _fake_db_session,
    )
    monkeypatch.setattr(
        "src.services.template_service.TemplateService",
        FakeTemplateService,
    )

    payload = await thesis_feature_service.build_compile_payload(
        workspace_id="ws-1",
        workspace_name="测试论文",
        workspace_description="默认摘要",
        thread_id="thread-1",
        template="default",
        compiler="xelatex",
        bibliography_style="gbt7714",
    )

    assert "\\documentclass{custom_thesis}" in payload["latex_content"]
    assert "这是章节正文。" in payload["latex_content"]
    assert payload["template_assets"] == [
        {
            "path": "custom_thesis.cls",
            "content": (
                "\\NeedsTeXFormat{LaTeX2e}\n"
                "\\ProvidesClass{custom_thesis}\n"
                "\\LoadClass{ctexart}"
            ),
        }
    ]


@pytest.mark.asyncio
async def test_build_compile_payload_uses_uploaded_latex_style_template_asset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_load_workspace_artifacts(_workspace_id: str):
        return [
            SimpleNamespace(
                type="thesis_chapter",
                title="绪论",
                content={
                    "chapter_index": 0,
                    "chapter_title": "绪论",
                    "markdown": "# 绪论\n\n这是章节正文。",
                },
                created_at="2026-03-20T00:00:00+00:00",
            )
        ]

    async def _fake_load_workspace_literature(_workspace_id: str):
        return []

    @asynccontextmanager
    async def _fake_db_session():
        yield object()

    class FakeTemplateService:
        def __init__(self, db: object) -> None:
            _ = db

        async def get_active(self, workspace_id: str):
            _ = workspace_id
            return SimpleNamespace(
                source_file_path="/tmp/brandstyle.sty",
                latex_preamble=(
                    "\\NeedsTeXFormat{LaTeX2e}\n"
                    "\\ProvidesPackage{brandstyle}\n"
                    "\\RequirePackage{xcolor}\n"
                ),
            )

    monkeypatch.setattr(
        thesis_feature_service,
        "_load_workspace_artifacts",
        _fake_load_workspace_artifacts,
    )
    monkeypatch.setattr(
        thesis_feature_service,
        "_load_workspace_literature",
        _fake_load_workspace_literature,
    )
    monkeypatch.setattr(
        thesis_feature_service,
        "get_db_session",
        _fake_db_session,
    )
    monkeypatch.setattr(
        "src.services.template_service.TemplateService",
        FakeTemplateService,
    )

    payload = await thesis_feature_service.build_compile_payload(
        workspace_id="ws-1",
        workspace_name="测试论文",
        workspace_description="默认摘要",
        thread_id="thread-1",
        template="default",
        compiler="xelatex",
        bibliography_style="gbt7714",
    )

    assert "\\usepackage{brandstyle}" in payload["latex_content"]
    assert "\\documentclass[UTF8, a4paper, 12pt, openany]{ctexart}" in payload["latex_content"]
    assert "这是章节正文。" in payload["latex_content"]
    assert payload["template_assets"] == [
        {
            "path": "brandstyle.sty",
            "content": (
                "\\NeedsTeXFormat{LaTeX2e}\n"
                "\\ProvidesPackage{brandstyle}\n"
                "\\RequirePackage{xcolor}"
            ),
        }
    ]


@pytest.mark.asyncio
async def test_build_compile_payload_raises_when_no_renderable_chapter_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_load_workspace_artifacts(_workspace_id: str):
        return [
            SimpleNamespace(
                type="thesis_chapter",
                title="绪论",
                content={
                    "chapter_index": 0,
                    "chapter_title": "绪论",
                    "markdown": "",
                },
                created_at="2026-03-20T00:00:00+00:00",
            )
        ]

    async def _fake_load_workspace_literature(_workspace_id: str):
        return []

    monkeypatch.setattr(
        thesis_feature_service,
        "_load_workspace_artifacts",
        _fake_load_workspace_artifacts,
    )
    monkeypatch.setattr(
        thesis_feature_service,
        "_load_workspace_literature",
        _fake_load_workspace_literature,
    )

    with pytest.raises(RuntimeError, match="no renderable markdown content"):
        await thesis_feature_service.build_compile_payload(
            workspace_id="ws-1",
            workspace_name="测试论文",
            workspace_description="默认摘要",
            thread_id="thread-1",
            template="default",
            compiler="xelatex",
            bibliography_style="gbt7714",
        )
