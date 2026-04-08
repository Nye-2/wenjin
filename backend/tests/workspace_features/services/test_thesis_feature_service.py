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

    captured: dict[str, str] = {}

    @asynccontextmanager
    async def _fake_db_session():
        yield object()

    class _FakeBridgeService:
        def __init__(self, _db) -> None:
            pass

        async def sync_project(self, **kwargs):
            captured["latex_source"] = str(kwargs["main_tex"])
            return SimpleNamespace(
                id="latex-project-1",
                main_file="main.tex",
                llm_config={"metadata": {"sync_conflicts": []}},
            )

    class _FakeCompileService:
        def __init__(self, _db) -> None:
            pass

        async def compile_project(self, _project, *, main_file: str, engine: str):
            assert main_file == "main.tex"
            assert engine == "xelatex"
            return {
                "ok": True,
                "status": 0,
                "engine": engine,
                "main_file": main_file,
                "pdf_path": "/tmp/main.pdf",
                "pdf_endpoint": "/api/latex/projects/latex-project-1/compile/history-1/pdf",
                "log": "ok",
                "error": None,
                "history_id": "history-1",
                "page_count": 3,
            }

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
        thesis_feature_service,
        "WorkspaceLatexProjectService",
        _FakeBridgeService,
    )
    monkeypatch.setattr(
        thesis_feature_service,
        "LatexCompileService",
        _FakeCompileService,
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

    assert payload["compile_status"] == "success"
    assert payload["abstract_source"] == "llm_override"
    assert payload["keywords"] == ["关键词A", "关键词B"]
    assert "这是覆盖后的摘要内容。" in payload["latex_content"]
    assert "关键词A" in payload["latex_content"]
    assert "关键词B" in payload["latex_content"]
    assert payload["latex_content"] == captured["latex_source"]


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

    captured: dict[str, str] = {}

    @asynccontextmanager
    async def _fake_db_session():
        yield object()

    class _FakeBridgeService:
        def __init__(self, _db) -> None:
            pass

        async def sync_project(self, **kwargs):
            captured["latex_source"] = str(kwargs["main_tex"])
            captured["bibliography"] = str(kwargs["bib_tex"])
            return SimpleNamespace(
                id="latex-project-2",
                main_file="main.tex",
                llm_config={"metadata": {"sync_conflicts": []}},
            )

    class _FakeCompileService:
        def __init__(self, _db) -> None:
            pass

        async def compile_project(self, _project, *, main_file: str, engine: str):
            return {
                "ok": True,
                "status": 0,
                "engine": engine,
                "main_file": main_file,
                "pdf_path": "/tmp/main.pdf",
                "pdf_endpoint": "/api/latex/projects/latex-project-2/compile/history-2/pdf",
                "log": "ok",
                "error": None,
                "history_id": "history-2",
                "page_count": 2,
            }

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
        thesis_feature_service,
        "WorkspaceLatexProjectService",
        _FakeBridgeService,
    )
    monkeypatch.setattr(
        thesis_feature_service,
        "LatexCompileService",
        _FakeCompileService,
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
    assert payload["latex_content"] == captured["latex_source"]
    assert "Hello Panel" not in payload["latex_content"]
    assert "这是章节正文。" in payload["latex_content"]
    assert captured["bibliography"] == ""
    assert "latex_project_artifact_id" not in payload["source_summary"]


@pytest.mark.asyncio
async def test_build_compile_payload_raises_when_linked_pipeline_fails(
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

    class _FailingBridgeService:
        def __init__(self, _db) -> None:
            pass

        async def sync_project(self, **_kwargs):
            raise RuntimeError("bridge unavailable")

    class _UnusedCompileService:
        def __init__(self, _db) -> None:
            pass

        async def compile_project(self, *_args, **_kwargs):
            raise AssertionError("compile_project should not run when sync_project fails")

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
        thesis_feature_service,
        "WorkspaceLatexProjectService",
        _FailingBridgeService,
    )
    monkeypatch.setattr(
        thesis_feature_service,
        "LatexCompileService",
        _UnusedCompileService,
    )

    with pytest.raises(RuntimeError, match="linked_latex_pipeline_failed"):
        await thesis_feature_service.build_compile_payload(
            workspace_id="ws-1",
            workspace_name="测试论文",
            workspace_description="默认摘要",
            thread_id="thread-1",
            template="default",
            compiler="xelatex",
            bibliography_style="gbt7714",
        )
