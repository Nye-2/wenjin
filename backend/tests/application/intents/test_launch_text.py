"""Tests for launch/resume text normalization helpers."""

from __future__ import annotations

from src.application.intents.launch_text import (
    is_generic_feature_launch_text,
    normalize_inline_text,
)


def test_normalize_inline_text_collapses_whitespace() -> None:
    assert normalize_inline_text("  A\n\nB\t C  ") == "A B C"


def test_generic_feature_launch_text_detection() -> None:
    assert is_generic_feature_launch_text("开始吧")
    assert is_generic_feature_launch_text("Go ahead")
    assert is_generic_feature_launch_text("请帮我开始「深度调研」。")
    assert not is_generic_feature_launch_text("研究主题改为多模态医学影像分割")

