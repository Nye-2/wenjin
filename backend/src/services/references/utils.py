"""Shared helpers for the workspace reference library."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_NON_WORD_RE = re.compile(r"\W+", flags=re.UNICODE)
_UNSAFE_KEY_RE = re.compile(r"[^A-Za-z0-9_:-]+")
_SAFE_CITATION_KEY_RE = re.compile(r"^[A-Za-z0-9_:-]+$")
_LATEX_CITE_RE = re.compile(
    r"\\(?:cite|citep|citet|citealp|citealt|parencite|textcite|autocite|supercite)"
    r"(?:\[[^\]]*\])*\{([^}]+)\}"
)


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def normalize_title(value: str | None) -> str:
    normalized = _NON_WORD_RE.sub(" ", str(value or "").lower())
    return " ".join(normalized.split())


def normalize_doi(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    for prefix in ("https://doi.org/", "http://dx.doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized.removeprefix(prefix)
    normalized = normalized.strip().strip(".")
    return normalized or None


def parse_authors(raw_authors: Any) -> list[str]:
    if isinstance(raw_authors, list):
        authors: list[str] = []
        for item in raw_authors:
            if isinstance(item, dict):
                candidate = item.get("name") or item.get("author") or item.get("full_name")
            else:
                candidate = item
            text = str(candidate or "").strip()
            if text:
                authors.append(text)
        return authors[:80]

    text = str(raw_authors or "").strip()
    if not text:
        return []
    for separator in ("；", ";", "|", "\n", " and "):
        text = text.replace(separator, ",")
    return [part.strip() for part in text.split(",") if part.strip()][:80]


def safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def first_author_last_name(authors: list[str]) -> str:
    if not authors:
        return "ref"
    first = str(authors[0] or "").strip()
    if not first:
        return "ref"
    if "," in first:
        first = first.split(",", 1)[0]
    else:
        first = first.split()[-1]
    key = _UNSAFE_KEY_RE.sub("", first)
    return key or "ref"


def slug_words(value: str | None, *, max_words: int = 3) -> str:
    words = _NON_WORD_RE.sub(" ", str(value or "").lower()).split()
    if not words:
        return ""
    return "".join(word[:16] for word in words[:max_words])


def build_citation_key_base(
    *,
    title: str,
    authors: list[str],
    year: int | None,
) -> str:
    author = first_author_last_name(authors)
    year_part = str(year or "nd")
    title_part = slug_words(title, max_words=2)
    base = f"{author}{year_part}"
    if title_part and author == "ref":
        base = f"{base}{title_part}"
    return _UNSAFE_KEY_RE.sub("", base) or "ref"


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def guess_bibtex_entry_type(venue: str | None = None, publication_type: str | None = None) -> str:
    normalized = f"{publication_type or ''} {venue or ''}".lower()
    if "conference" in normalized or "proceedings" in normalized or "conf" in normalized:
        return "inproceedings"
    if "book" in normalized:
        return "book"
    return "article"


def maybe_path_name(path: str | None) -> str:
    return Path(str(path or "")).name


def extract_citation_keys_from_text(text: str) -> list[str]:
    """Extract BibTeX citation keys from LaTeX citation commands."""
    keys: list[str] = []
    seen: set[str] = set()
    for match in _LATEX_CITE_RE.finditer(str(text or "")):
        raw_keys = match.group(1)
        for raw_key in raw_keys.split(","):
            key = raw_key.strip()
            if not key or key == "*" or not _SAFE_CITATION_KEY_RE.fullmatch(key):
                continue
            if key in seen:
                continue
            seen.add(key)
            keys.append(key)
    return keys


def extract_citation_keys_from_payload(payload: Any) -> list[str]:
    """Extract citation keys from nested artifact/feature payloads."""
    keys: list[str] = []
    seen: set[str] = set()

    def add_from_text(value: str) -> None:
        for key in extract_citation_keys_from_text(value):
            if key not in seen:
                seen.add(key)
                keys.append(key)

    def visit(value: Any) -> None:
        if isinstance(value, str):
            add_from_text(value)
            return
        if isinstance(value, dict):
            for item in value.values():
                visit(item)
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    visit(payload)
    return keys
