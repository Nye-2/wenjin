"""LaTeX compiler engine defaults and validation helpers."""

from __future__ import annotations

import os
from typing import Literal

_SUPPORTED_ENGINES = frozenset(
    {
        "xelatex",
        "pdflatex",
    }
)
_FALLBACK_ENGINE = "xelatex"


def is_supported_latex_engine(engine: str) -> bool:
    """Return whether the provided engine is supported."""
    return engine in _SUPPORTED_ENGINES


def get_supported_latex_engines() -> tuple[str, ...]:
    """Return supported engines in a stable order."""
    return tuple(sorted(_SUPPORTED_ENGINES))


def get_default_latex_engine() -> Literal["xelatex", "pdflatex"]:
    """Resolve default LaTeX engine from environment with safe fallback."""
    configured = str(os.getenv("WENJIN_LATEX_DEFAULT_COMPILER", "")).strip().lower()
    if configured and configured in _SUPPORTED_ENGINES:
        return configured  # type: ignore[return-value]
    return _FALLBACK_ENGINE  # type: ignore[return-value]
