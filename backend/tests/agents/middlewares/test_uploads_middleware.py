"""Tests for UploadsMiddleware."""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from src.agents.middlewares.uploads import UploadsMiddleware
from src.agents.thread_state import ThreadState


@pytest.mark.asyncio
async def test_uploads_middleware_includes_preprocess_paths_in_prompt() -> None:
    middleware = UploadsMiddleware()
    state = ThreadState(
        messages=[HumanMessage(content="请基于我上传的文件继续分析。")],
        uploaded_files=[
            {
                "name": "paper.pdf",
                "path": "reference://reference-1",
                "size": 1234,
                "kind": "literature",
                "reference_id": "reference-1",
                "metadata": {
                    "preprocess": {
                        "status": "succeeded",
                        "markdown_paths": [
                            "/mnt/user-data/uploads/_preprocessed/paper/doc_0.md",
                        ],
                        "manifest_path": "/mnt/user-data/uploads/_preprocessed/paper/manifest.json",
                    }
                },
            }
        ],
    )

    result = await middleware.before_model(state, config={"configurable": {}})

    assert "messages" in result
    rendered = result["messages"][-1].content
    assert "<uploaded_files>" in rendered
    assert "Reference Library ID: reference-1" in rendered
    assert "预处理状态: succeeded" in rendered
    assert "可读文本路径" in rendered
    assert "Reference Library" in rendered
    assert "manifest.json" in rendered


@pytest.mark.asyncio
async def test_uploads_middleware_reads_workspace_relative_markdown_excerpt(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_root = tmp_path / "workspace_uploads"
    markdown_path = workspace_root / "ws-1" / "references" / "_preprocessed" / "paper" / "doc_0.md"
    markdown_path.parent.mkdir(parents=True)
    markdown_path.write_text("# Parsed\n\nImportant PDF content.", encoding="utf-8")
    monkeypatch.setattr(
        "src.agents.middlewares.uploads.DEFAULT_WORKSPACE_UPLOAD_ROOT",
        workspace_root,
    )

    middleware = UploadsMiddleware()
    state = ThreadState(
        messages=[HumanMessage(content="总结附件。")],
        workspace_id="ws-1",
        uploaded_files=[
            {
                "name": "paper.pdf",
                "path": "reference://reference-1",
                "size": 1234,
                "kind": "literature",
                "reference_id": "reference-1",
                "metadata": {
                    "preprocess": {
                        "status": "succeeded",
                        "provider": "layout_parsing",
                        "markdown_paths": [
                            "/references/_preprocessed/paper/doc_0.md",
                        ],
                    }
                },
            }
        ],
    )

    result = await middleware.before_model(
        state,
        config={"configurable": {"workspace_id": "ws-1"}},
    )

    rendered = result["messages"][-1].content
    assert "内容摘要:" in rendered
    assert "Important PDF content." in rendered
    assert "Mission 的工作区资料读取工具" in rendered


@pytest.mark.asyncio
async def test_uploads_middleware_warns_for_pending_preprocess() -> None:
    middleware = UploadsMiddleware()
    state = ThreadState(
        messages=[HumanMessage(content="总结附件。")],
        uploaded_files=[
            {
                "name": "paper.pdf",
                "path": "reference://reference-1",
                "size": 1234,
                "kind": "literature",
                "reference_id": "reference-1",
                "metadata": {
                    "preprocess": {
                        "status": "pending",
                        "provider": "layout_parsing",
                        "task_id": "task-preprocess-1",
                    }
                },
            }
        ],
    )

    result = await middleware.before_model(state, config={"configurable": {}})

    rendered = result["messages"][-1].content
    assert "该文件正在后台解析" in rendered
    assert "不要引用或臆测 PDF 全文内容" in rendered
