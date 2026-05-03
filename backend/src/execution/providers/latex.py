"""LaTeX execution provider.

This module provides Docker-based LaTeX compilation with security validation.
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, TYPE_CHECKING

from ..base import ExecutionProvider
from ..security.latex_sanitizer import sanitize_latex
from ..types import ProviderResult

if TYPE_CHECKING:
    from ..docker.client import DockerClient

logger = logging.getLogger(__name__)

DEFAULT_LATEX_DOCKER_IMAGE = "wenjin/texlive:2024"


class LaTeXProvider(ExecutionProvider):
    """LaTeX compilation provider using Docker.

    Features:
    - XeLaTeX and PDFLaTeX support
    - BibTeX/BibLaTeX integration
    - Security validation via latex_sanitizer
    - Page counting with PyMuPDF
    - Error extraction from LaTeX logs
    """

    _execution_type = "latex_compile"
    _docker_image = DEFAULT_LATEX_DOCKER_IMAGE

    @property
    def execution_type(self) -> str:
        """Execution type this provider handles."""
        return self._execution_type

    @property
    def docker_image(self) -> str | None:
        """Docker image name."""
        return os.getenv("GUANLAN_TEXLIVE_IMAGE", self._docker_image)

    def build_command(self, content: str, options: dict[str, Any]) -> list[str]:
        """Build Docker command for LaTeX compilation.

        Args:
            content: LaTeX source code.
            options: Compilation options:
                - compiler: "xelatex" (default) or "pdflatex"
                - bibliography: BibTeX content string
                - bibliography_file: BibTeX filename (default: "refs.bib")
                - bibliography_style: Bibliography style (default: "plain")

        Returns:
            Command list for Docker execution.
        """
        compiler = options.get("compiler", "xelatex")
        bibliography = options.get("bibliography", "")
        has_bib = bool(bibliography or options.get("bibliography_file"))

        # Inject bibliography commands if needed
        if has_bib:
            bib_filename = options.get("bibliography_file", "refs.bib").replace(".bib", "")
            style = options.get("bibliography_style", "plain")
            content = self._inject_bibliography(content, bib_filename, style)

        script_lines: list[str] = ["set -e"]

        # Write main.tex file.
        script_lines.extend([
            "cat > main.tex << 'LATEX_EOF'",
            content.rstrip("\n"),
            "LATEX_EOF",
        ])

        # Write bibliography if provided.
        if bibliography:
            bib_filename = options.get("bibliography_file", "refs.bib")
            script_lines.extend([
                f"cat > {bib_filename} << 'BIB_EOF'",
                bibliography.rstrip("\n"),
                "BIB_EOF",
            ])

        # Build compilation chain.
        script_lines.extend(self._build_compile_chain(compiler, has_bib))

        return ["/bin/bash", "-c", "\n".join(script_lines)]

    def _build_compile_chain(self, compiler: str, has_bib: bool) -> list[str]:
        """Build LaTeX compilation command chain.

        Args:
            compiler: LaTeX compiler (xelatex or pdflatex).
            has_bib: Whether to include BibTeX compilation.

        Returns:
            List of shell commands.
        """
        commands = []

        # First compilation
        commands.append(f"{compiler} -interaction=nonstopmode main.tex")

        if has_bib:
            # BibTeX
            commands.append("bibtex main")
            # Second compilation for references
            commands.append(f"{compiler} -interaction=nonstopmode main.tex")

        # Final compilation
        commands.append(f"{compiler} -interaction=nonstopmode main.tex")

        return commands

    def _inject_bibliography(
        self,
        content: str,
        bib_filename: str = "refs",
        style: str = "plain",
    ) -> str:
        """Inject bibliography commands into LaTeX if needed.

        Args:
            content: LaTeX source code.
            bib_filename: BibTeX filename (without .bib extension).
            style: Bibliography style name.

        Returns:
            LaTeX content with bibliography commands if needed.
        """
        # Check if bibliography commands already exist
        if r"\bibliography{" in content:
            return content

        # Check if there are any \cite{} commands
        if r"\cite{" not in content:
            return content

        # Inject before \end{document}
        injection = f"\\bibliographystyle{{{style}}}\n\\bibliography{{{bib_filename}}}\n"

        if r"\end{document}" in content:
            return content.replace(r"\end{document}", injection + r"\end{document}")
        else:
            # No \end{document}, append at end
            return content + "\n" + injection

    async def execute(
        self,
        content: str,
        work_dir: str,
        options: dict[str, Any],
        docker_client: "DockerClient | None" = None,  # type: ignore[override]
    ) -> ProviderResult:
        """Execute LaTeX compilation.

        This method performs security validation only. The actual Docker execution
        is handled by the DockerExecutionService.

        Args:
            content: LaTeX source code.
            work_dir: Working directory path.
            options: Compilation options.
            docker_client: Docker client (not used in this method).

        Returns:
            ProviderResult with validation status.
        """
        # Security validation
        is_safe, error_msg = sanitize_latex(content)
        if not is_safe:
            logger.warning(f"LaTeX security violation: {error_msg}")
            return ProviderResult(
                success=False,
                error_message=error_msg,
                metadata={"security_violation": True}
            )

        # Check bibliography if provided
        bibliography = options.get("bibliography", "")
        if bibliography:
            is_safe, error_msg = sanitize_latex(bibliography)
            if not is_safe:
                logger.warning(f"Bibliography security violation: {error_msg}")
                return ProviderResult(
                    success=False,
                    error_message=f"Bibliography: {error_msg}",
                    metadata={"security_violation": True}
                )

        # Return success - actual execution handled by DockerExecutionService
        return ProviderResult(
            success=True,
            metadata={"validated": True}
        )

    async def process_result(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        work_dir: str,
        options: dict[str, Any],
    ) -> ProviderResult:
        """Process Docker execution result.

        Args:
            exit_code: Container exit code.
            stdout: Container stdout.
            stderr: Container stderr.
            work_dir: Working directory path.
            options: Execution options.

        Returns:
            ProviderResult with output files and metadata.
        """
        work_path = Path(work_dir)

        # Check if PDF was generated
        pdf_path = work_path / "main.pdf"
        if not pdf_path.exists():
            # Compilation failed
            log_content = self._read_log(work_path / "main.log")

            return ProviderResult(
                success=False,
                error_message=self._extract_error(log_content or stderr or stdout),
                logs=self._truncate_log(log_content or stdout)
            )

        # Count pages
        page_count = self._count_pages(pdf_path)

        # Read log for metadata
        log_path = work_path / "main.log"
        log_content = self._read_log(log_path)

        return ProviderResult(
            success=True,
            output_files=["main.pdf"],
            metadata={
                "page_count": page_count,
                "compiler": options.get("compiler", "xelatex"),
                "file_size": pdf_path.stat().st_size,
            },
            logs=self._truncate_log(log_content) if log_content else None
        )

    def _extract_error(self, log: str) -> str:
        """Extract error message from LaTeX log.

        Args:
            log: LaTeX log content.

        Returns:
            Extracted error message.
        """
        if not log:
            return "Unknown error (no log output)"

        # Common LaTeX error patterns
        patterns = [
            # LaTeX Error
            r"^!\s*(LaTeX Error:.*?)(?:\n|$)",
            # File not found
            r"^!\s*(File `[^']+\' not found)",
            # Package error
            r"^!\s*(Package\s+\w+\s+Error:.*?)(?:\n|$)",
            # Generic error with line number
            r"^!\s*(.*?)(?:\n|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, log, re.MULTILINE | re.IGNORECASE)
            if match:
                error = match.group(1).strip()
                # Add context line if available
                lines = log.split('\n')
                for i, line in enumerate(lines):
                    if error in line and i + 1 < len(lines):
                        context = lines[i + 1].strip()
                        if context and not context.startswith('!'):
                            error += f"\n{context}"
                        break
                return error

        # Fallback: first non-empty line after first !
        if '!' in log:
            idx = log.index('!')
            error_lines = log[idx:].split('\n')[:3]
            return '\n'.join(line.strip() for line in error_lines if line.strip())

        return "Unknown error"

    def _count_pages(self, pdf_path: Path) -> int:
        """Count pages in PDF using PyMuPDF.

        Args:
            pdf_path: Path to PDF file.

        Returns:
            Number of pages, or 0 if counting fails.
        """
        try:
            import fitz  # PyMuPDF
            with fitz.open(str(pdf_path)) as doc:
                return int(doc.page_count)
        except Exception as e:
            logger.warning(f"Failed to count PDF pages: {e}")
            return 0

    def _truncate_log(self, log: str, max_len: int = 10000) -> str:
        """Truncate log to maximum length.

        Args:
            log: Log content.
            max_len: Maximum length (default: 10000 characters).

        Returns:
            Truncated log with ellipsis if needed.
        """
        if not log:
            return ""

        if len(log) <= max_len:
            return log

        # Keep start and end
        half = max_len // 2
        return log[:half] + "\n... (truncated) ...\n" + log[-half:]

    def _read_log(self, log_path: Path) -> str | None:
        """Read log file safely.

        Args:
            log_path: Path to log file.

        Returns:
            Log content or None if file doesn't exist.
        """
        try:
            if log_path.exists():
                return log_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"Failed to read log file: {e}")
        return None
