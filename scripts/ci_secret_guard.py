#!/usr/bin/env python3
"""Fail CI when tracked files contain high-confidence local secrets."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsk-(?:proj-|kimi-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\btp-[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(
        r"(?i)\b(api[_-]?key|token|password|secret)\b\s*[:=]\s*"
        r"['\"][^'\"<>{}\s][^'\"]{15,}['\"]"
    ),
)

PLACEHOLDER_MARKERS = (
    "change-this",
    "your_",
    "your-",
    "example",
    "dummy",
    "securepassword",
    "anotherpassword",
    "test_password",
    "wrong_password",
    "wenjin-e2e-password",
    "sk-live-1234abcd",
    "test-secret",
    "test-token",
    "secret-key-for-pytest",
)

SKIPPED_SUFFIXES = (
    ".example",
    ".md",
    ".lock",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
)


def tracked_files() -> list[str]:
    output = subprocess.check_output(["git", "ls-files"], text=True)
    return [line.strip() for line in output.splitlines() if line.strip()]


def is_env_file(path: str) -> bool:
    name = Path(path).name
    return name in {".env", ".env.local"} or path.endswith("/.env")


def should_scan(path: str) -> bool:
    if path.startswith(("frontend/node_modules/", ".git/")):
        return False
    return not path.endswith(SKIPPED_SUFFIXES)


def line_has_secret(line: str) -> bool:
    lowered = line.lower()
    if any(marker in lowered for marker in PLACEHOLDER_MARKERS):
        return False
    return any(pattern.search(line) for pattern in SECRET_PATTERNS)


def main() -> int:
    failures: list[str] = []
    for path in tracked_files():
        if is_env_file(path):
            failures.append(f"{path}: tracked local environment file")
            continue
        if not should_scan(path):
            continue
        if not Path(path).exists():
            continue
        try:
            text = Path(path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if line_has_secret(line):
                failures.append(f"{path}:{line_number}: possible secret")

    if failures:
        print("Secret hygiene guard failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print("Secret hygiene guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
