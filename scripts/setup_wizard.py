#!/usr/bin/env python3
"""Wenjin environment setup wizard.

Usage:
    python scripts/setup_wizard.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def _is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _c(text: str, code: str) -> str:
    if _supports_color():
        return f"\033[{code}m{text}\033[0m"
    return text


def green(text: str) -> str:
    return _c(text, "32")


def cyan(text: str) -> str:
    return _c(text, "36")


def bold(text: str) -> str:
    return _c(text, "1")


def ask_yes_no(prompt: str, *, default: bool) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    while True:
        answer = input(prompt + suffix).strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please answer y or n.")


def ask_text(prompt: str, *, default: str = "") -> str:
    suffix = f" [{default}] " if default else " "
    value = input(prompt + suffix).strip()
    if not value:
        return default
    return value


def _ensure_env_file(target: Path, example: Path) -> bool:
    """Create target from example when missing. Return True if created."""
    if target.exists():
        return False
    if example.exists():
        shutil.copyfile(example, target)
    else:
        target.write_text("", encoding="utf-8")
    return True


def _parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _write_dotenv_updates(path: Path, updates: dict[str, str]) -> None:
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pending = dict(updates)
    rendered: list[str] = []

    for raw_line in existing_lines:
        line = raw_line
        stripped = line.strip()
        key_part = stripped
        if stripped.startswith("export "):
            key_part = stripped[7:].lstrip()
        if "=" in key_part:
            key = key_part.split("=", 1)[0].strip()
            if key in pending:
                rendered.append(f"{key}={pending.pop(key)}")
                continue
        rendered.append(raw_line)

    if pending:
        if rendered and rendered[-1].strip():
            rendered.append("")
        rendered.append("# Updated by scripts/setup_wizard.py")
        for key, value in sorted(pending.items()):
            rendered.append(f"{key}={value}")

    path.write_text("\n".join(rendered).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    if not _is_interactive():
        print(
            "Non-interactive environment detected.\n"
            "Run this script in a terminal, or configure files manually."
        )
        return 1

    project_root = Path(__file__).resolve().parents[1]
    backend_dir = project_root / "backend"
    frontend_dir = project_root / "frontend"

    root_env = project_root / ".env"
    root_env_example = project_root / ".env.example"
    print()
    print(bold("Welcome to Wenjin Setup Wizard"))
    print("This wizard prepares the root .env file used by every service.")
    print()

    if not backend_dir.exists() or not frontend_dir.exists():
        print("Project structure is incomplete (missing backend/ or frontend/).")
        return 1

    created_root_env = _ensure_env_file(root_env, root_env_example)
    if created_root_env:
        print(green(f"Created {root_env.relative_to(project_root)}"))

    current_env = _parse_dotenv(root_env)
    updates: dict[str, str] = {}

    if ask_yes_no("Configure common service URLs in root .env?", default=False):
        for key in ("DATABASE_URL", "REDIS_URL"):
            default = current_env.get(key, "")
            value = ask_text(key, default=default)
            if value:
                updates[key] = value

    if updates:
        _write_dotenv_updates(root_env, updates)
        print(green(f"Updated {root_env.relative_to(project_root)}"))

    print()
    print(bold("Setup complete"))
    print("Next steps:")
    print(f"  {cyan('python scripts/doctor.py')}     # Validate environment")
    print(f"  {cyan('cd backend && make install')}   # Install backend deps")
    print(f"  {cyan('cd backend && make gateway')}   # Start API")
    print(f"  {cyan('cd backend && make worker')}    # Start worker")
    print(f"  {cyan('cd frontend && npm install && npm run dev')}  # Start frontend")
    print()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nSetup cancelled.")
        raise SystemExit(130) from None
