"""Shared utilities for LangGraph sub-graphs.

This module provides common utilities used across all workspace graph implementations:
- JSON parsing with markdown fence handling
- Model creation with safety
- Generation mode detection
- Parameter normalization helpers
"""

from __future__ import annotations

from .utils import (
    _normalize_list,
    _normalize_text,
    _read_optional_int,
    _read_optional_str,
    _utc_now_iso,
    build_memory_context_text,
    create_model_safe,
    detect_generation_mode,
    parse_json_list_response,
    parse_json_response,
)

__all__ = [
    # Public API
    "build_memory_context_text",
    "create_model_safe",
    "detect_generation_mode",
    "parse_json_list_response",
    "parse_json_response",
    # Internal utilities (exposed for graph modules)
    "_normalize_list",
    "_normalize_text",
    "_read_optional_int",
    "_read_optional_str",
    "_utc_now_iso",
]
