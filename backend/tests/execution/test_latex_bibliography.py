"""Tests for LaTeX provider bibliography handling."""

import pytest
from src.execution.providers.latex import LaTeXProvider


def test_inject_bibliography_commands():
    """Test automatic bibliography command injection."""
    provider = LaTeXProvider()

    latex = r"""\documentclass{article}
\begin{document}
Hello world \cite{Smith2024}.
\end{document}"""

    result = provider._inject_bibliography(latex, "refs", "plain")

    assert r"\bibliographystyle{plain}" in result
    assert r"\bibliography{refs}" in result
    assert result.endswith(r"\end{document}")


def test_no_injection_if_bibliography_exists():
    """Test no injection if bibliography commands already exist."""
    provider = LaTeXProvider()

    latex = r"""\documentclass{article}
\begin{document}
Hello world \cite{Smith2024}.
\bibliographystyle{alpha}
\bibliography{refs}
\end{document}"""

    result = provider._inject_bibliography(latex, "refs", "alpha")

    # Should not add duplicate commands
    assert result.count(r"\bibliography{refs}") == 1
    assert result.count(r"\bibliographystyle") == 1


def test_no_injection_if_no_citations():
    """Test no injection if LaTeX has no citations."""
    provider = LaTeXProvider()

    latex = r"""\documentclass{article}
\begin{document}
Hello world.
\end{document}"""

    result = provider._inject_bibliography(latex, "refs", "plain")

    # Should not add bibliography
    assert r"\bibliography" not in result


def test_injection_before_end_document():
    r"""Test that injection happens before \end{document}."""
    provider = LaTeXProvider()

    latex = r"""\documentclass{article}
\begin{document}
\cite{Test2024}
\end{document}"""

    result = provider._inject_bibliography(latex, "refs", "plain")

    # Bibliography should appear before \end{document}
    bib_pos = result.find(r"\bibliography{refs}")
    end_pos = result.find(r"\end{document}")
    assert bib_pos < end_pos
