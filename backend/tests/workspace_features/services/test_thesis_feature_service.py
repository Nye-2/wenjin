"""Tests for thesis_feature_service compile payload behavior."""

from __future__ import annotations

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

    async def _fake_compile_latex(
        *,
        latex_source: str,
        workspace_id: str,
        thread_id: str | None,
        bibliography: str,
        compiler: str,
        bibliography_style: str,
        timeout: int,
    ):
        captured["latex_source"] = latex_source
        return SimpleNamespace(
            success=True,
            pdf_path="/mnt/user-data/execution/latex_compile/20260320/main.pdf",
            page_count=3,
            error=None,
            logs="ok",
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
        "compile_latex",
        _fake_compile_latex,
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
