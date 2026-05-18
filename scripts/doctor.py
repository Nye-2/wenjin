#!/usr/bin/env python3
"""Wenjin health check script.

Usage:
    python scripts/doctor.py

Exit codes:
  0: required checks passed
  1: one or more required checks failed
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit


Status = Literal["ok", "warn", "fail", "skip"]


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


def red(text: str) -> str:
    return _c(text, "31")


def cyan(text: str) -> str:
    return _c(text, "36")


def bold(text: str) -> str:
    return _c(text, "1")


def _icon(status: Status) -> str:
    return {
        "ok": green("✓"),
        "warn": yellow("!"),
        "fail": red("✗"),
        "skip": "—",
    }[status]


def _run(cmd: list[str]) -> str | None:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return (result.stdout or result.stderr).strip()
    except Exception:
        return None


def _backend_python(backend_dir: Path) -> Path:
    """Prefer the repo's backend virtualenv interpreter when it exists."""
    candidate = backend_dir / ".venv" / "bin" / "python"
    if candidate.exists():
        return candidate
    return Path(sys.executable)


def _parse_major(version_text: str) -> int | None:
    first_token = version_text.strip().split()[0] if version_text.strip() else ""
    value = first_token.lstrip("v").split(".", 1)[0]
    return int(value) if value.isdigit() else None


def _split_use_path(use: str) -> tuple[str, str] | None:
    if ":" not in use:
        return None
    module_name, attr_name = use.split(":", 1)
    if not module_name or not attr_name:
        return None
    return module_name, attr_name


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


def _value_from_env_sources(env_name: str, env_files: list[Path]) -> str | None:
    if os.environ.get(env_name):
        return os.environ.get(env_name)
    for file in env_files:
        value = _parse_dotenv(file).get(env_name)
        if value:
            return value
    return None


def _load_config(config_path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        import yaml

        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            return None, "top-level config must be a mapping"
        return data, None
    except Exception as exc:
        return None, str(exc)


def _parse_host_port_from_url(raw_url: str) -> tuple[str, int] | None:
    try:
        parsed = urlsplit(raw_url)
        if not parsed.hostname:
            return None
        default_port = 5432 if parsed.scheme.startswith("postgres") else 6379
        return parsed.hostname, int(parsed.port or default_port)
    except Exception:
        return None


def _check_tcp_connectivity(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@dataclass
class CheckResult:
    label: str
    status: Status
    detail: str = ""
    fix: str | None = None

    def render(self) -> None:
        detail_text = f"  ({self.detail})" if self.detail else ""
        print(f"  {_icon(self.status)} {self.label}{detail_text}")
        if self.fix:
            for line in self.fix.splitlines():
                print(f"      {cyan('→')} {line}")


def check_python_version() -> CheckResult:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 12):
        return CheckResult("Python", "ok", version)
    return CheckResult(
        "Python",
        "fail",
        version,
        fix="Install Python 3.12+",
    )


def check_node_version() -> CheckResult:
    if not shutil.which("node"):
        return CheckResult("Node.js", "fail", fix="Install Node.js 20+")
    output = _run(["node", "-v"]) or ""
    major = _parse_major(output)
    if major is None or major < 20:
        return CheckResult(
            "Node.js",
            "fail",
            output or "unknown version",
            fix="Upgrade Node.js to 20+",
        )
    return CheckResult("Node.js", "ok", output.lstrip("v"))


def check_npm() -> CheckResult:
    if not shutil.which("npm"):
        return CheckResult("npm", "fail", fix="Install npm (bundled with Node.js)")
    output = _run(["npm", "-v"]) or ""
    return CheckResult("npm", "ok", output)


def check_uv() -> CheckResult:
    if not shutil.which("uv"):
        return CheckResult(
            "uv",
            "warn",
            fix="Install uv for backend dependency/runtime management",
        )
    output = _run(["uv", "--version"]) or ""
    parts = output.split()
    version = parts[1] if len(parts) > 1 else output
    return CheckResult("uv", "ok", version)


def check_docker() -> CheckResult:
    if not shutil.which("docker"):
        return CheckResult(
            "docker",
            "warn",
            "not installed",
            fix="Install Docker if you use docker-compose or DockerSandboxProvider",
        )
    output = _run(["docker", "--version"]) or ""
    return CheckResult("docker", "ok", output)


def check_file_exists(path: Path, label: str, *, required: bool, fix: str | None = None) -> CheckResult:
    if path.exists():
        return CheckResult(label, "ok")
    if required:
        return CheckResult(label, "fail", fix=fix)
    return CheckResult(label, "warn", fix=fix)


def check_config_loadable(project_root: Path, config_path: Path) -> CheckResult:
    backend_dir = project_root / "backend"
    code = (
        "import sys\n"
        f"sys.path.insert(0, {repr(str(backend_dir))})\n"
        f"sys.path.insert(0, {repr(str(backend_dir / 'src'))})\n"
        "from src.config.config_loader import load_config\n"
        f"load_config({repr(str(config_path))})\n"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        return CheckResult("backend/config.yaml loadable", "fail", str(exc))

    if result.returncode == 0:
        return CheckResult("backend/config.yaml loadable", "ok")

    detail = (result.stderr or result.stdout).strip().splitlines()
    summary = detail[-1] if detail else "unknown error"
    return CheckResult(
        "backend/config.yaml loadable",
        "fail",
        summary,
        fix="Fix backend/config.yaml syntax or placeholders",
    )


def _validate_model_entries(raw: str) -> tuple[list[dict[str, Any]] | None, str | None]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON ({exc.msg})"

    if not isinstance(parsed, list):
        return None, "must be a JSON array"
    if not parsed:
        return None, "must contain at least one model"

    required = {"id", "model", "api_key", "base_url"}
    validated: list[dict[str, Any]] = []
    for idx, item in enumerate(parsed, start=1):
        if not isinstance(item, dict):
            return None, f"entry {idx} must be an object"
        missing = sorted(field for field in required if not str(item.get(field, "")).strip())
        if missing:
            return None, f"entry {idx} missing required fields: {', '.join(missing)}"
        validated.append(item)
    return validated, None


def check_runtime_env(env_files: list[Path]) -> list[CheckResult]:
    """Validate the backend runtime env shape that production code actually uses."""
    results: list[CheckResult] = []

    for env_name in ("DATABASE_URL", "REDIS_URL"):
        if _value_from_env_sources(env_name, env_files):
            results.append(CheckResult(f"{env_name} set", "ok"))
        else:
            results.append(
                CheckResult(
                    f"{env_name} set",
                    "fail",
                    fix=f"Add {env_name}=... to backend/.env or export in shell",
                )
            )

    jwt_secret = _value_from_env_sources("JWT_SECRET_KEY", env_files)
    if not jwt_secret:
        results.append(
            CheckResult(
                "JWT_SECRET_KEY set",
                "fail",
                fix="Add JWT_SECRET_KEY=... to backend/.env or export in shell",
            )
        )
    elif jwt_secret in {
        "change-me-in-production",
        "your-super-secret-key-change-in-production",
    }:
        results.append(
            CheckResult(
                "JWT_SECRET_KEY set",
                "warn",
                "default development secret",
                fix="Replace JWT_SECRET_KEY before any shared or production deployment",
            )
        )
    else:
        results.append(CheckResult("JWT_SECRET_KEY set", "ok"))

    llm_models_raw = _value_from_env_sources("LLM_MODELS", env_files)
    if not llm_models_raw:
        results.append(
            CheckResult(
                "LLM_MODELS set",
                "fail",
                fix="Add LLM_MODELS=[...] JSON to backend/.env",
            )
        )
        return results

    llm_models, llm_error = _validate_model_entries(llm_models_raw)
    if llm_error:
        results.append(CheckResult("LLM_MODELS valid", "fail", llm_error))
        return results

    assert llm_models is not None
    ids = [str(model["id"]).strip() for model in llm_models]
    results.append(CheckResult("LLM_MODELS valid", "ok", f"{len(ids)} model(s)"))

    default_model = _value_from_env_sources("LLM_DEFAULT_MODEL", env_files)
    if not default_model:
        results.append(
            CheckResult(
                "LLM_DEFAULT_MODEL valid",
                "fail",
                fix="Set LLM_DEFAULT_MODEL to one of the ids declared in LLM_MODELS",
            )
        )
    elif default_model in ids:
        results.append(CheckResult("LLM_DEFAULT_MODEL valid", "ok", default_model))
    else:
        results.append(
            CheckResult(
                "LLM_DEFAULT_MODEL valid",
                "fail",
                default_model,
                fix=f"Choose one of: {', '.join(ids)}",
            )
        )

    image_models_raw = _value_from_env_sources("LLM_IMAGE_MODELS", env_files)
    if image_models_raw:
        _, image_error = _validate_model_entries(image_models_raw)
        if image_error:
            results.append(CheckResult("LLM_IMAGE_MODELS valid", "warn", image_error))
        else:
            results.append(CheckResult("LLM_IMAGE_MODELS valid", "ok"))
    else:
        results.append(
            CheckResult(
                "LLM_IMAGE_MODELS set",
                "skip",
                "optional",
            )
        )

    return results


def _check_src_attr_without_import(module_name: str, attr_name: str, backend_dir: Path) -> tuple[bool, str]:
    module_rel = Path(*module_name.split("."))
    candidate_files = [
        backend_dir / f"{module_rel}.py",
        backend_dir / module_rel / "__init__.py",
    ]
    module_file = next((path for path in candidate_files if path.exists()), None)
    if module_file is None:
        return False, f"module file not found for {module_name}"

    source = module_file.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return False, f"syntax error in {module_file}: {exc}"

    declared_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            declared_names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    declared_names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            declared_names.add(node.target.id)

    if attr_name in declared_names:
        return True, ""

    if re.search(rf"\b{re.escape(attr_name)}\b", source):
        # The name exists in this module (possibly re-exported/imported).
        return True, ""

    return False, f"attribute {attr_name} not found in {module_file}"


def _check_external_attr_with_python(
    module_name: str,
    attr_name: str,
    python_executable: Path,
) -> tuple[bool, str]:
    code = (
        "import importlib\n"
        f"module = importlib.import_module({module_name!r})\n"
        f"getattr(module, {attr_name!r})\n"
    )
    try:
        result = subprocess.run(
            [str(python_executable), "-c", code],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        return False, str(exc)

    if result.returncode == 0:
        return True, ""

    detail = (result.stderr or result.stdout).strip().splitlines()
    return False, detail[-1] if detail else "unknown import error"


def check_config_use_paths(
    config_data: dict[str, Any],
    backend_dir: Path,
    python_executable: Path,
) -> list[CheckResult]:
    results: list[CheckResult] = []
    checks: list[tuple[str, str]] = []

    for idx, tool in enumerate(config_data.get("tools", []), start=1):
        if isinstance(tool, dict):
            checks.append((f"tool[{idx}] use path", str(tool.get("use", "")).strip()))
    sandbox = config_data.get("sandbox")
    if isinstance(sandbox, dict):
        checks.append(("sandbox use path", str(sandbox.get("use", "")).strip()))

    for label, use_path in checks:
        split = _split_use_path(use_path)
        if split is None:
            results.append(
                CheckResult(
                    label,
                    "fail",
                    use_path or "empty",
                    fix="Use module:attribute format",
                )
            )
            continue

        module_name, attr_name = split
        if module_name.startswith("src."):
            ok, detail = _check_src_attr_without_import(module_name, attr_name, backend_dir)
            if ok:
                results.append(CheckResult(label, "ok"))
            else:
                results.append(
                    CheckResult(
                        label,
                        "fail",
                        f"{use_path} ({detail})",
                        fix="Install missing dependency or fix the use path",
                    )
                )
            continue

        try:
            ok, detail = _check_external_attr_with_python(
                module_name,
                attr_name,
                python_executable,
            )
            if not ok:
                raise ImportError(detail)
            results.append(CheckResult(label, "ok"))
        except Exception as exc:
            results.append(
                CheckResult(
                    label,
                    "fail",
                    f"{use_path} ({exc})",
                    fix="Install missing dependency or fix the use path",
                )
            )
    return results


def check_backend_runtime_urls(env_files: list[Path]) -> list[CheckResult]:
    results: list[CheckResult] = []
    for env_key, label in (
        ("DATABASE_URL", "database connectivity"),
        ("REDIS_URL", "redis connectivity"),
    ):
        raw_url = _value_from_env_sources(env_key, env_files)
        if not raw_url:
            results.append(
                CheckResult(
                    label,
                    "warn",
                    f"{env_key} not set",
                    fix=f"Set {env_key} in backend/.env",
                )
            )
            continue

        host_port = _parse_host_port_from_url(raw_url)
        if host_port is None:
            results.append(CheckResult(label, "warn", f"cannot parse {env_key}"))
            continue
        host, port = host_port
        if _check_tcp_connectivity(host, port):
            results.append(CheckResult(label, "ok", f"{host}:{port} reachable"))
        else:
            results.append(
                CheckResult(
                    label,
                    "warn",
                    f"{host}:{port} unreachable",
                    fix="Start database/redis or fix URL",
                )
            )
    return results


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    backend_dir = project_root / "backend"
    frontend_dir = project_root / "frontend"
    backend_python = _backend_python(backend_dir)
    config_path = backend_dir / "config.yaml"
    backend_env = backend_dir / ".env"
    frontend_env = frontend_dir / ".env.local"
    root_env = project_root / ".env"

    print()
    print(bold("Wenjin Health Check"))
    print("═" * 40)

    sections: list[tuple[str, list[CheckResult]]] = []

    sections.append(
        (
            "System",
            [
                check_python_version(),
                check_node_version(),
                check_npm(),
                check_uv(),
                check_docker(),
            ],
        )
    )

    config_data, config_error = _load_config(config_path) if config_path.exists() else (None, None)

    cfg_checks: list[CheckResult] = [
        check_file_exists(
            config_path,
            "backend/config.yaml found",
            required=True,
            fix="Create backend/config.yaml",
        ),
        check_file_exists(
            backend_env,
            "backend/.env found",
            required=False,
            fix="Copy backend/.env.example to backend/.env",
        ),
        check_file_exists(
            frontend_env,
            "frontend/.env.local found",
            required=False,
            fix="Copy frontend/.env.example to frontend/.env.local when you need a frontend API override",
        ),
        check_file_exists(
            root_env,
            "root .env found",
            required=False,
            fix="Create root .env when using docker-compose",
        ),
    ]
    if config_error:
        cfg_checks.append(
            CheckResult(
                "backend/config.yaml parse",
                "fail",
                config_error,
                fix="Fix yaml syntax in backend/config.yaml",
            )
        )
    elif config_data is not None:
        cfg_checks.append(check_config_loadable(project_root, config_path))
    sections.append(("Configuration", cfg_checks))

    if config_data is not None:
        env_files = [backend_env, root_env]
        sections.append(("Runtime Env", check_runtime_env(env_files)))
        sections.append(("Use Paths", check_config_use_paths(config_data, backend_dir, backend_python)))
        sections.append(("Runtime Connectivity", check_backend_runtime_urls(env_files)))
    else:
        sections.append(("Runtime Env", [CheckResult("runtime env checks", "skip", "config unavailable")]))
        sections.append(("Use Paths", [CheckResult("use path checks", "skip", "config unavailable")]))
        sections.append(("Runtime Connectivity", [CheckResult("runtime connectivity", "skip", "config unavailable")]))

    total_fail = 0
    total_warn = 0
    for section_name, checks in sections:
        print()
        print(bold(section_name))
        for check in checks:
            check.render()
            if check.status == "fail":
                total_fail += 1
            elif check.status == "warn":
                total_warn += 1

    print()
    print("═" * 40)
    if total_fail == 0 and total_warn == 0:
        print(f"Status: {green('Ready')}")
    elif total_fail == 0:
        print(f"Status: {yellow(f'Ready ({total_warn} warning(s))')}")
    else:
        print(f"Status: {red(f'{total_fail} error(s), {total_warn} warning(s)')}")

    print()
    if total_fail:
        print(f"Fix errors, then rerun {cyan('python scripts/doctor.py')}")
    else:
        print(f"Start backend: {cyan('cd backend && make gateway')}")
    print()
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
