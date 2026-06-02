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
    assert is_generic_feature_launch_text(
        "\n".join(
            [
                "请启动「文献定位与创新点」能力。",
                "能力目标：建立相关工作、gap 和 contribution positioning",
                "如果当前对话缺少具体研究主题、材料或目标，请先向用户确认，不要用空泛主题启动检索、写作或实验。",
                "请先判断是否需要实验或检索；若需要，请由右侧 Lead Agent/subagent 自主推进，并在右侧工作台展示关键证据、运行状态和可审阅结果。",
            ]
        )
    )
    assert not is_generic_feature_launch_text("研究主题改为多模态医学影像分割")
