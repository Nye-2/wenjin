from src.services.prism_file_content import (
    ensure_latex_document,
    normalize_prism_file_change_content,
)


def test_tex_file_change_wraps_markdownish_manuscript_as_latex_document():
    source = """# **联邦学习大模型**

**摘要**
这是摘要，包含 95% 的性能和 `FedAvg` 基线。

### **1. 引言**

1. 通信效率
2. 隐私保护

| 方法 | 准确率 |
| :--- | :---: |
| FedCoLLM | 95.4% |
"""

    result = normalize_prism_file_change_content(source, path="main.tex")

    assert result.startswith("\\documentclass[UTF8,12pt]{ctexart}")
    assert "\\title{联邦学习大模型}" in result
    assert "\\section{1. 引言}" in result
    assert "\\begin{enumerate}" in result
    assert "\\item 通信效率" in result
    assert "\\begin{verbatim}" in result
    assert "95\\%" in result
    assert "\\texttt{FedAvg}" in result
    assert result.rstrip().endswith("\\end{document}")


def test_existing_complete_latex_document_is_preserved():
    source = "\\documentclass{article}\\begin{document}Draft\\end{document}"

    assert ensure_latex_document(source) == source


def test_fenced_complete_latex_document_is_unwrapped():
    source = "```latex\n\\documentclass{article}\\begin{document}Draft\\end{document}\n```"

    assert ensure_latex_document(source) == "\\documentclass{article}\\begin{document}Draft\\end{document}"


def test_non_tex_file_change_keeps_plain_content():
    source = "# Markdown report"

    assert normalize_prism_file_change_content(source, path="report.md") == source


def test_raw_tex_file_change_preserves_fragment_content():
    source = "\\section{方法}\n只修改被选中的局部片段。"

    assert (
        normalize_prism_file_change_content(
            source,
            path="sections/method.tex",
            content_format="raw",
        )
        == source
    )
