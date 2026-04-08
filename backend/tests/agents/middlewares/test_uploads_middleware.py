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
                "path": "/mnt/user-data/uploads/paper.pdf",
                "size": 1234,
                "kind": "literature",
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
    assert "预处理状态: succeeded" in rendered
    assert "可读文本路径" in rendered
    assert "manifest.json" in rendered
