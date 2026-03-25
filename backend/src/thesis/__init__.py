"""Thesis domain package."""

from .config import ThesisSettings, thesis_settings
from .latex_template import THESIS_TEMPLATE_EN, THESIS_TEMPLATE_ZH, get_template

__all__ = [
    "ThesisSettings",
    "thesis_settings",
    "THESIS_TEMPLATE_ZH",
    "THESIS_TEMPLATE_EN",
    "get_template",
]
