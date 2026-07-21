"""Pure filename recovery for legacy ZIP metadata encodings."""

from __future__ import annotations

import unicodedata


def recover_legacy_zip_filename(value: str) -> str:
    """Recover UTF-8/GB18030 bytes that a ZIP reader exposed as CP437 text."""

    original = unicodedata.normalize("NFC", str(value or ""))
    try:
        raw = original.encode("cp437")
    except UnicodeEncodeError:
        return original
    if raw.isascii():
        return original
    original_score = _filename_quality(original)
    for encoding in ("utf-8", "gb18030"):
        try:
            candidate = unicodedata.normalize("NFC", raw.decode(encoding))
        except UnicodeDecodeError:
            continue
        if _filename_quality(candidate) > original_score:
            return candidate
    return original


def _filename_quality(value: str) -> int:
    score = 0
    for char in value:
        codepoint = ord(char)
        category = unicodedata.category(char)
        if char in {"\ufffd", "\x00"} or category.startswith("C"):
            score -= 20
        elif 0x4E00 <= codepoint <= 0x9FFF:
            score += 4
        elif 0x2500 <= codepoint <= 0x257F:
            score -= 5
        elif 0x0370 <= codepoint <= 0x03FF:
            score -= 2
        elif category in {"Sm", "So"}:
            score -= 1
        elif char.isalnum() or char in "/._-（）()：:，, ":
            score += 1
    return score


__all__ = ["recover_legacy_zip_filename"]
