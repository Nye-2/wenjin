"""Tests for LaTeX execution provider."""

import pytest

from src.execution.providers.latex import LaTeXProvider


class TestLaTeXProvider:
    """Tests for LaTeXProvider."""

    @pytest.fixture
    def provider(self):
        """Create LaTeXProvider instance."""
        return LaTeXProvider()

    def test_execution_type(self, provider):
        """Should return correct execution type."""
        assert provider.execution_type == "latex_compile"

    def test_docker_image(self, provider):
        """Should return Docker image name."""
        assert provider.docker_image == "wenjin/texlive:2024"

    def test_build_command_simple(self, provider):
        """Should build command for simple LaTeX."""
        content = r"\documentclass{article}\begin{document}Hello\end{document}"
        command = provider.build_command(content, {})

        assert "xelatex" in " ".join(command)
        assert "main.tex" in " ".join(command)

    def test_build_command_heredoc_terminator_stays_on_own_line(self, provider):
        """Heredoc terminator must not be followed by shell operators."""
        content = r"\documentclass{article}\begin{document}Hello\end{document}"
        command = provider.build_command(content, {"compiler": "pdflatex"})

        script = command[2]
        assert "\nLATEX_EOF\n" in script
        assert "LATEX_EOF &&" not in script

    def test_build_command_with_bibtex(self, provider):
        """Should build command chain with BibTeX."""
        content = r"\documentclass{article}\begin{document}Hello\end{document}"
        options = {"bibliography": "@article{test, ...}"}
        command = provider.build_command(content, options)

        cmd_str = " ".join(command)
        assert "bibtex" in cmd_str.lower()

    def test_build_command_uses_pdflatex(self, provider):
        """Should use pdflatex when specified."""
        content = r"\documentclass{article}\begin{document}Hello\end{document}"
        options = {"compiler": "pdflatex"}
        command = provider.build_command(content, options)

        assert "pdflatex" in " ".join(command)

    def test_extract_error_latex_error(self, provider):
        """Should extract LaTeX error message."""
        log = "! LaTeX Error: Environment undefined.\nBlah blah"
        error = provider._extract_error(log)
        assert "LaTeX Error" in error

    def test_extract_error_file_not_found(self, provider):
        """Should extract file not found error."""
        log = "! File `missing.tex' not found"
        error = provider._extract_error(log)
        assert "missing.tex" in error
