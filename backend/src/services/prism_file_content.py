"""Content normalization for Prism file-change payloads."""

from __future__ import annotations

import re

_LATEX_DOCUMENT_RE = re.compile(
    r"\\documentclass(?:\[[^\]]*\])?\{[^}]+\}.*\\begin\{document\}.*\\end\{document\}",
    re.DOTALL,
)
_FENCED_CODE_RE = re.compile(r"^```(?:latex|tex)?\s*\n(?P<body>.*)\n```\s*$", re.DOTALL | re.IGNORECASE)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_ORDERED_ITEM_RE = re.compile(r"^\s*\d+[.)]\s+(.+?)\s*$")
_UNORDERED_ITEM_RE = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")
_INLINE_TOKEN_RE = re.compile(r"(\*\*.+?\*\*|`.+?`)")


def normalize_prism_file_change_content(
    content: str,
    *,
    path: str,
    content_format: str | None = None,
) -> str:
    """Normalize Prism file-change content to the file contract.

    Prism's LaTeX adapter stores `main.tex` as an actual LaTeX source file. If a
    capability maps plain manuscript text or Markdown into a `.tex` path, the
    review payload must be converted before staging so apply/compile remains a
    closed loop.
    """

    normalized_format = (content_format or "").strip().lower()
    if normalized_format in {"raw", "latex_fragment", "tex_fragment"}:
        return content
    if normalized_format in {"latex", "latex_document", "tex"} or path.lower().endswith(".tex"):
        return ensure_latex_document(content)
    return content


def ensure_latex_document(content: str) -> str:
    """Return a complete LaTeX document for manuscript content."""

    text = content.strip()
    fenced = _FENCED_CODE_RE.match(text)
    if fenced:
        text = fenced.group("body").strip()
    if _LATEX_DOCUMENT_RE.search(text):
        return text
    return markdownish_to_latex_document(text)


def markdownish_to_latex_document(content: str) -> str:
    """Convert simple Markdown-ish manuscript text into compileable LaTeX."""

    lines = content.splitlines()
    title = "SCI Manuscript Draft"
    body_start = 0
    for index, line in enumerate(lines):
        match = _HEADING_RE.match(line.strip())
        if match and len(match.group(1)) == 1:
            title = _strip_markdown_inline(match.group(2))
            body_start = index + 1
            break

    body_lines = _convert_markdownish_body(lines[body_start:])
    escaped_title = _convert_inline(title)
    body = "\n".join(body_lines).strip()
    if not body:
        body = r"\section{Draft}" + "\n" + _convert_inline(content)

    return (
        "\\documentclass[UTF8,12pt]{ctexart}\n"
        "\\usepackage[a4paper,margin=1in]{geometry}\n"
        "\\usepackage{amsmath}\n"
        "\\usepackage{booktabs}\n"
        "\\usepackage{array}\n"
        "\\usepackage{enumitem}\n"
        "\\usepackage{hyperref}\n\n"
        f"\\title{{{escaped_title}}}\n"
        "\\author{}\n"
        "\\date{\\today}\n\n"
        "\\begin{document}\n"
        "\\maketitle\n\n"
        f"{body}\n\n"
        "\\end{document}\n"
    )


def _convert_markdownish_body(lines: list[str]) -> list[str]:
    output: list[str] = []
    list_env: str | None = None
    in_verbatim = False

    def close_list() -> None:
        nonlocal list_env
        if list_env:
            output.append(f"\\end{{{list_env}}}")
            output.append("")
            list_env = None

    def open_list(env: str) -> None:
        nonlocal list_env
        if list_env == env:
            return
        close_list()
        output.append(f"\\begin{{{env}}}[leftmargin=*]")
        list_env = env

    def close_verbatim() -> None:
        nonlocal in_verbatim
        if in_verbatim:
            output.append("\\end{verbatim}")
            output.append("")
            in_verbatim = False

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if in_verbatim:
            if stripped.startswith("|"):
                output.append(line)
                continue
            close_verbatim()

        if not stripped:
            close_list()
            output.append("")
            continue

        if _is_markdown_rule(stripped):
            close_list()
            output.append("\\par\\medskip\\hrule\\medskip")
            output.append("")
            continue

        if stripped.startswith("|"):
            close_list()
            output.append("\\begin{verbatim}")
            output.append(line)
            in_verbatim = True
            continue

        heading = _HEADING_RE.match(stripped)
        if heading:
            close_list()
            level = len(heading.group(1))
            command = "section" if level <= 3 else "subsection"
            if level >= 5:
                command = "paragraph"
            output.append(f"\\{command}{{{_convert_inline(_strip_markdown_inline(heading.group(2)))}}}")
            output.append("")
            continue

        ordered = _ORDERED_ITEM_RE.match(line)
        if ordered:
            open_list("enumerate")
            output.append(f"\\item {_convert_inline(ordered.group(1))}")
            continue

        unordered = _UNORDERED_ITEM_RE.match(line)
        if unordered:
            open_list("itemize")
            output.append(f"\\item {_convert_inline(unordered.group(1))}")
            continue

        close_list()
        output.append(_convert_inline(stripped))
        output.append("")

    close_verbatim()
    close_list()
    return output


def _is_markdown_rule(value: str) -> bool:
    return bool(re.fullmatch(r"[-*_]{3,}", value))


def _strip_markdown_inline(value: str) -> str:
    text = value.strip()
    while text.startswith("**") and text.endswith("**") and len(text) >= 4:
        text = text[2:-2].strip()
    return text


def _convert_inline(value: str) -> str:
    parts: list[str] = []
    position = 0
    for match in _INLINE_TOKEN_RE.finditer(value):
        if match.start() > position:
            parts.append(_escape_latex_text(value[position:match.start()]))
        token = match.group(0)
        if token.startswith("**") and token.endswith("**"):
            parts.append(f"\\textbf{{{_escape_latex_text(token[2:-2])}}}")
        elif token.startswith("`") and token.endswith("`"):
            parts.append(f"\\texttt{{{_escape_latex_text(token[1:-1])}}}")
        position = match.end()
    if position < len(value):
        parts.append(_escape_latex_text(value[position:]))
    return "".join(parts)


def _escape_latex_text(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in value)
