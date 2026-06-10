"""Content normalization for Prism file-change payloads."""

from __future__ import annotations

import re

_LATEX_DOCUMENT_RE = re.compile(
    r"\\documentclass(?:\[[^\]]*\])?\{[^}]+\}.*?\\begin\{document\}.*?\\end\{document\}",
    re.DOTALL,
)
_FENCED_CODE_RE = re.compile(r"^```(?:latex|tex)?\s*\n(?P<body>.*)\n```\s*$", re.DOTALL | re.IGNORECASE)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_ORDERED_ITEM_RE = re.compile(r"^\s*\d+[.)]\s+(.+?)\s*$")
_UNORDERED_ITEM_RE = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")
_INLINE_TOKEN_RE = re.compile(r"(\*\*.+?\*\*|`.+?`)")
_AMSMATH_PACKAGE_RE = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{(?:[^}]*,)?amsmath(?:,[^}]*)?\}")
_AMSSYMB_PACKAGE_RE = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{(?:[^}]*,)?(?:amssymb|amsfonts)(?:,[^}]*)?\}")
_MALFORMED_ARGUMENT_COMMAND_RE = re.compile(
    r"\\(?P<command>ref|eqref|autoref|pageref|cite|citet|citep|citealp|parencite|textcite):"
    r"(?P<argument>[A-Za-z0-9_.:-]+)\}"
)
_COMMON_MATH_OPERATORS = {
    "argmin": r"arg\,min",
    "argmax": r"arg\,max",
}
_COMMON_THEOREM_ENVIRONMENTS = {
    "assumption": "Assumption",
    "claim": "Claim",
    "corollary": "Corollary",
    "example": "Example",
}
PRISM_SEMANTIC_CONTRACT_SCHEMA = "wenjin.prism.semantic_contract.v1"
_LATEX_CITE_RE = re.compile(
    r"\\(?:cite|citep|citet|citealp|citealt|parencite|textcite|autocite|supercite)"
    r"(?:\[[^\]]*\])*\{([^}]+)\}"
)
_SAFE_CITATION_KEY_RE = re.compile(r"^[A-Za-z0-9_:-]+$")
_LATEX_ENV_RE = re.compile(r"\\(?P<op>begin|end)\{(?P<env>[^{}]+)\}")
_EQUATION_ENVS = {
    "align",
    "align*",
    "equation",
    "equation*",
    "gather",
    "gather*",
    "math",
    "multline",
    "multline*",
    "split",
}
_TABLE_ENVS = {"longtable", "tabular", "tabular*", "table", "table*"}


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


def summarize_prism_file_change_content_contract(
    content: str,
    *,
    path: str,
) -> dict[str, object]:
    """Return a bounded structural contract for Prism review projections."""

    file_path = str(path or "").strip()
    text = str(content or "")
    if not file_path.lower().endswith(".tex"):
        return {
            "path": file_path,
            "content_format": "text",
            "latex_shape": "not_latex",
            "balanced_braces": True,
        }
    balanced = _has_balanced_latex_braces(text)
    if _LATEX_DOCUMENT_RE.search(text):
        latex_shape = "document"
        content_format = "latex_document"
    elif text.strip():
        latex_shape = "fragment" if balanced else "invalid"
        content_format = "latex_fragment"
    else:
        latex_shape = "invalid"
        content_format = "latex_fragment"
    return {
        "path": file_path,
        "content_format": content_format,
        "latex_shape": latex_shape,
        "balanced_braces": balanced,
    }


def summarize_prism_file_change_semantic_contract(
    content: str,
    *,
    path: str,
    content_contract: dict[str, object] | None = None,
    source_contract: dict[str, object] | None = None,
) -> dict[str, object]:
    """Return bounded semantic-preservation signals for a Prism review item.

    This is a deterministic structural heuristic, not a model judge. If a
    trusted upstream contract is already present, we sanitize and preserve it.
    """

    file_path = str(path or "").strip()
    if isinstance(source_contract, dict) and source_contract:
        return _sanitize_semantic_contract(source_contract, target_path=file_path)

    text = str(content or "")
    structural_contract = content_contract or summarize_prism_file_change_content_contract(
        text,
        path=file_path,
    )
    structurally_valid = (
        structural_contract.get("balanced_braces") is True
        and str(structural_contract.get("latex_shape") or "") != "invalid"
    )
    citation_keys = _extract_citation_keys(text)
    has_malformed_citation = bool(_MALFORMED_ARGUMENT_COMMAND_RE.search(text))
    has_equations = _has_equation_constructs(text)
    has_tables = _has_table_constructs(text)
    equations_balanced = _has_balanced_named_environments(text, _EQUATION_ENVS) and _has_balanced_math_delimiters(text)
    tables_balanced = _has_balanced_named_environments(text, _TABLE_ENVS)
    preserves_claims = structurally_valid and bool(text.strip())
    preserves_citations = not has_malformed_citation
    preserves_equations = equations_balanced
    preserves_tables = tables_balanced
    risk = (
        "high"
        if not (
            preserves_claims
            and preserves_citations
            and preserves_equations
            and preserves_tables
        )
        else "low"
    )
    return {
        "schema": PRISM_SEMANTIC_CONTRACT_SCHEMA,
        "target_path": file_path,
        "basis": "bounded_structural_heuristic",
        "preserves_claims": preserves_claims,
        "preserves_citations": preserves_citations,
        "preserves_equations": preserves_equations,
        "preserves_tables": preserves_tables,
        "risk": risk,
        "citation_key_count": len(citation_keys),
        "has_equations": has_equations,
        "has_tables": has_tables,
    }


def ensure_latex_document(content: str) -> str:
    """Return a complete LaTeX document for manuscript content."""

    text = content.strip()
    fenced = _FENCED_CODE_RE.match(text)
    if fenced:
        text = fenced.group("body").strip()
    document = _LATEX_DOCUMENT_RE.search(text)
    if document:
        return _normalize_latex_document(document.group(0).strip())
    return _normalize_latex_document(markdownish_to_latex_document(text))


def _normalize_latex_document(content: str) -> str:
    repaired = _repair_common_latex_argument_braces(content)
    with_math = _ensure_common_math_operator_declarations(repaired)
    return _ensure_common_theorem_environment_declarations(with_math)


def _repair_common_latex_argument_braces(content: str) -> str:
    """Repair common LLM typos like `\\ref:label}` to `\\ref{label}`."""

    return _MALFORMED_ARGUMENT_COMMAND_RE.sub(
        lambda match: f"\\{match.group('command')}{{{match.group('argument')}}}",
        content,
    )


def _has_balanced_latex_braces(content: str) -> bool:
    depth = 0
    escaped = False
    for char in content:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _sanitize_semantic_contract(value: dict[str, object], *, target_path: str) -> dict[str, object]:
    risk = str(value.get("risk") or "medium").strip().lower()
    if risk not in {"low", "medium", "high"}:
        risk = "medium"
    return {
        "schema": PRISM_SEMANTIC_CONTRACT_SCHEMA,
        "target_path": str(value.get("target_path") or target_path),
        "basis": str(value.get("basis") or "upstream_contract")[:80],
        "preserves_claims": value.get("preserves_claims") is True,
        "preserves_citations": value.get("preserves_citations") is True,
        "preserves_equations": value.get("preserves_equations") is True,
        "preserves_tables": value.get("preserves_tables") is True,
        "risk": risk,
        "citation_key_count": _nonnegative_int(value.get("citation_key_count")),
        "has_equations": value.get("has_equations") is True,
        "has_tables": value.get("has_tables") is True,
    }


def _extract_citation_keys(content: str) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for match in _LATEX_CITE_RE.finditer(str(content or "")):
        for raw_key in match.group(1).split(","):
            key = raw_key.strip()
            if not key or key == "*" or not _SAFE_CITATION_KEY_RE.fullmatch(key):
                continue
            if key in seen:
                continue
            seen.add(key)
            keys.append(key)
    return keys


def _has_equation_constructs(content: str) -> bool:
    text = str(content or "")
    return (
        any(rf"\begin{{{env}}}" in text for env in _EQUATION_ENVS)
        or r"\[" in text
        or r"\(" in text
        or bool(re.search(r"(?<!\\)\$", text))
    )


def _has_table_constructs(content: str) -> bool:
    text = str(content or "")
    return any(rf"\begin{{{env}}}" in text for env in _TABLE_ENVS)


def _has_balanced_named_environments(content: str, names: set[str]) -> bool:
    stack: list[str] = []
    for match in _LATEX_ENV_RE.finditer(str(content or "")):
        env_name = str(match.group("env") or "").strip()
        if env_name not in names:
            continue
        if match.group("op") == "begin":
            stack.append(env_name)
            continue
        if not stack or stack.pop() != env_name:
            return False
    return not stack


def _has_balanced_math_delimiters(content: str) -> bool:
    text = str(content or "")
    if text.count(r"\[") != text.count(r"\]"):
        return False
    if text.count(r"\(") != text.count(r"\)"):
        return False
    stripped = re.sub(r"\\.", "", text)
    display_dollars = stripped.count("$$")
    stripped = stripped.replace("$$", "")
    inline_dollars = stripped.count("$")
    return display_dollars % 2 == 0 and inline_dollars % 2 == 0


def _nonnegative_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _ensure_common_theorem_environment_declarations(content: str) -> str:
    """Declare theorem-like environments that generated manuscripts often use."""

    begin_index = content.find(r"\begin{document}")
    if begin_index < 0:
        return content

    preamble = content[:begin_index].rstrip()
    declarations: list[str] = []
    for env_name, display_name in _COMMON_THEOREM_ENVIRONMENTS.items():
        if not re.search(rf"\\begin\{{{re.escape(env_name)}\}}", content):
            continue
        if re.search(rf"\\newtheorem\{{{re.escape(env_name)}\}}", preamble):
            continue
        declarations.append(rf"\newtheorem{{{env_name}}}{{{display_name}}}")

    if not declarations:
        return content

    body = content[begin_index:].lstrip()
    return f"{preamble}\n" + "\n".join(declarations) + f"\n\n{body}"


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


def _ensure_common_math_operator_declarations(content: str) -> str:
    """Declare common operators that LLM manuscripts often use as commands."""

    begin_index = content.find(r"\begin{document}")
    if begin_index < 0:
        return content

    package_insertions: list[str] = []
    preamble = content[:begin_index].rstrip()
    if r"\mathbb" in content and not _AMSSYMB_PACKAGE_RE.search(preamble):
        package_insertions.append(r"\usepackage{amssymb}")

    declarations: list[str] = []
    for command, operator_text in _COMMON_MATH_OPERATORS.items():
        if not re.search(rf"\\{command}(?=[^A-Za-z]|$)", content):
            continue
        if re.search(rf"\\DeclareMathOperator\*?\{{\\{command}\}}", content):
            continue
        declarations.append(rf"\DeclareMathOperator*{{\{command}}}{{{operator_text}}}")

    if not package_insertions and not declarations:
        return content

    body = content[begin_index:].lstrip()
    insertion = []
    if not _AMSMATH_PACKAGE_RE.search(preamble):
        insertion.append(r"\usepackage{amsmath}")
    insertion.extend(package_insertions)
    insertion.extend(declarations)
    return f"{preamble}\n" + "\n".join(insertion) + f"\n\n{body}"


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
