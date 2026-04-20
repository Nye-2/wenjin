#!/usr/bin/env python3
"""Wenjin interactive setup wizard.

Usage:
    python scripts/setup_wizard.py
"""

from __future__ import annotations

import getpass
import os
import shutil
import sys
from pathlib import Path
from typing import Any


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


def yellow(text: str) -> str:
    return _c(text, "33")


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


def ask_text(prompt: str, *, default: str = "", secret: bool = False) -> str:
    suffix = f" [{default}] " if default else " "
    reader = getpass.getpass if secret else input
    value = reader(prompt + suffix).strip()
    if not value:
        return default
    return value


def _load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid yaml document at {path}: expected mapping")
    return data


def _save_yaml(path: Path, data: dict[str, Any]) -> None:
    import yaml

    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


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


def _collect_model_env_vars(config_data: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for model in config_data.get("models", []):
        if not isinstance(model, dict):
            continue
        api_key = model.get("api_key")
        if isinstance(api_key, str) and api_key.startswith("$"):
            env_name = api_key[1:].strip()
            if env_name and env_name not in keys:
                keys.append(env_name)
    return keys


def _choose_default_model(config_data: dict[str, Any]) -> str | None:
    models = config_data.get("models", [])
    if not isinstance(models, list) or not models:
        return None

    names = [
        str(item.get("name")).strip()
        for item in models
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    ]
    if not names:
        return None

    current = str(config_data.get("default_model", "")).strip()
    print()
    print(bold("Available default models:"))
    for idx, name in enumerate(names, start=1):
        marker = " (current)" if name == current else ""
        print(f"  {idx}. {name}{marker}")
    print(f"  {len(names) + 1}. keep current ({current or 'unset'})")

    while True:
        choice = input("Choose default model number [keep current]: ").strip()
        if not choice:
            return current or None
        if not choice.isdigit():
            print("Please enter a number.")
            continue
        selected = int(choice)
        if selected == len(names) + 1:
            return current or None
        if 1 <= selected <= len(names):
            return names[selected - 1]
        print("Choice out of range.")


def _choose_sandbox_use(config_data: dict[str, Any]) -> str | None:
    current = ""
    sandbox = config_data.get("sandbox")
    if isinstance(sandbox, dict):
        current = str(sandbox.get("use", "")).strip()
    print()
    print(bold("Execution sandbox mode:"))
    print("  1. Local sandbox (default)")
    print("  2. Docker sandbox")
    print(f"  3. keep current ({current or 'unset'})")
    while True:
        choice = input("Choose mode [keep current]: ").strip()
        if not choice or choice == "3":
            return current or None
        if choice == "1":
            return "src.sandbox.providers.local:LocalSandboxProvider"
        if choice == "2":
            return "src.sandbox.providers.docker:DockerSandboxProvider"
        print("Please choose 1, 2, or 3.")


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

    backend_env = backend_dir / ".env"
    backend_env_example = backend_dir / ".env.example"
    frontend_env = frontend_dir / ".env"
    frontend_env_example = frontend_dir / ".env.example"
    config_path = backend_dir / "config.yaml"

    print()
    print(bold("Welcome to Wenjin Setup Wizard"))
    print("This wizard prepares .env files and core backend config.")
    print()

    if not backend_dir.exists() or not frontend_dir.exists():
        print("Project structure is incomplete (missing backend/ or frontend/).")
        return 1

    created_backend_env = _ensure_env_file(backend_env, backend_env_example)
    created_frontend_env = _ensure_env_file(frontend_env, frontend_env_example)
    if created_backend_env:
        print(green(f"Created {backend_env.relative_to(project_root)}"))
    if created_frontend_env:
        print(green(f"Created {frontend_env.relative_to(project_root)}"))

    if not config_path.exists():
        print(yellow("backend/config.yaml not found. Wizard will only update .env files."))
        config_data: dict[str, Any] = {}
    else:
        try:
            config_data = _load_yaml(config_path)
        except Exception as exc:
            print(f"Failed to parse backend/config.yaml: {exc}")
            return 1

    current_env = _parse_dotenv(backend_env)
    updates: dict[str, str] = {}

    model_key_envs = _collect_model_env_vars(config_data)
    if model_key_envs:
        print()
        print(bold("Model API keys"))
        print("Press Enter to keep existing values.")
        for env_name in model_key_envs:
            current_masked = "set" if current_env.get(env_name) else "not set"
            if ask_yes_no(f"Set {env_name}? (current: {current_masked})", default=False):
                value = ask_text(f"{env_name}", secret=True)
                if value:
                    updates[env_name] = value

    if ask_yes_no("Configure common service URLs in backend/.env?", default=False):
        for key in ("DATABASE_URL", "REDIS_URL"):
            default = current_env.get(key, "")
            value = ask_text(key, default=default)
            if value:
                updates[key] = value

    if updates:
        _write_dotenv_updates(backend_env, updates)
        print(green(f"Updated {backend_env.relative_to(project_root)}"))

    should_update_config = bool(config_data) and ask_yes_no(
        "Apply optional backend/config.yaml updates (default model / sandbox)?",
        default=False,
    )
    if should_update_config:
        selected_model = _choose_default_model(config_data)
        selected_sandbox_use = _choose_sandbox_use(config_data)
        if selected_model:
            config_data["default_model"] = selected_model
        if selected_sandbox_use:
            sandbox = config_data.get("sandbox")
            if not isinstance(sandbox, dict):
                sandbox = {}
            sandbox["use"] = selected_sandbox_use
            config_data["sandbox"] = sandbox
        _save_yaml(config_path, config_data)
        print(green(f"Updated {config_path.relative_to(project_root)}"))

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
        raise SystemExit(130)
