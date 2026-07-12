"""Architecture guard for the DataService transaction boundary."""

from __future__ import annotations

import ast
import importlib.util
from dataclasses import dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = BACKEND_ROOT / "src"

GUARDED_ROOTS = (
    SRC_ROOT / "gateway",
    SRC_ROOT / "mission_runtime",
    SRC_ROOT / "agents" / "workspace_agent",
    SRC_ROOT / "subagent_runtime",
    SRC_ROOT / "review_commit_runtime",
)

# These layers may use src.dataservice_client and its typed contracts. DataService
# domain code, database ownership, and SQLAlchemy remain inside the DataService process.
FORBIDDEN_IMPORT_PREFIXES = (
    "src.dataservice",
    "src.database",
    "sqlalchemy",
)

SESSION_RECEIVER_NAMES = frozenset(
    {
        "db",
        "db_session",
        "database_session",
        "session",
    }
)
SESSION_SQL_METHODS = frozenset(
    {
        "add",
        "add_all",
        "begin",
        "commit",
        "delete",
        "execute",
        "flush",
        "merge",
        "rollback",
        "scalar",
        "scalars",
    }
)
SESSION_FACTORY_CALLS = frozenset(
    {
        "async_sessionmaker",
        "create_async_engine",
        "get_async_session_factory",
        "get_db",
        "get_db_session",
        "sessionmaker",
    }
)


@dataclass(frozen=True)
class BoundaryViolation:
    line: int
    reason: str


def _module_name(path: Path) -> str:
    relative = path.relative_to(BACKEND_ROOT).with_suffix("")
    parts = relative.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imported_module(node: ast.ImportFrom, path: Path) -> str:
    module = node.module or ""
    if node.level == 0:
        return module

    current_module = _module_name(path)
    package = current_module if path.name == "__init__.py" else current_module.rpartition(".")[0]
    return importlib.util.resolve_name("." * node.level + module, package)


def _matches_prefix(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def _session_receiver_name(node: ast.AST) -> str | None:
    while isinstance(node, ast.Attribute):
        candidate = node.attr.removeprefix("_")
        if candidate in SESSION_RECEIVER_NAMES:
            return candidate
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    candidate = node.id.removeprefix("_")
    return candidate if candidate in SESSION_RECEIVER_NAMES else None


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _boundary_violations(path: Path) -> list[BoundaryViolation]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[BoundaryViolation] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for prefix in FORBIDDEN_IMPORT_PREFIXES:
                    if _matches_prefix(alias.name, prefix):
                        violations.append(
                            BoundaryViolation(node.lineno, f"imports {alias.name}")
                        )
        elif isinstance(node, ast.ImportFrom):
            module = _imported_module(node, path)
            for prefix in FORBIDDEN_IMPORT_PREFIXES:
                if _matches_prefix(module, prefix):
                    violations.append(
                        BoundaryViolation(node.lineno, f"imports {module}")
                    )
        elif isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            if call_name in SESSION_FACTORY_CALLS:
                violations.append(
                    BoundaryViolation(node.lineno, f"calls session factory {call_name}")
                )
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            receiver = _session_receiver_name(node.func.value)
            if receiver is not None and call_name in SESSION_SQL_METHODS:
                violations.append(
                    BoundaryViolation(
                        node.lineno,
                        f"performs business SQL through {receiver}.{call_name}",
                    )
                )

    return violations


def _guarded_python_files() -> list[Path]:
    files: set[Path] = set()
    for root in GUARDED_ROOTS:
        assert root.is_dir(), f"Guarded architecture root is missing: {root}"
        files.update(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)
    return sorted(files)


def test_dataservice_boundary_detector_covers_imports_sessions_and_sql(tmp_path: Path) -> None:
    path = tmp_path / "src" / "gateway" / "sample.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "\n".join(
            (
                "from src.dataservice.domains.mission.repository import MissionRepository",
                "from src.database.models.mission import MissionRun",
                "from src.database.session import get_async_session_factory",
                "from sqlalchemy import select",
                "factory = get_async_session_factory()",
                "await session.execute(query)",
                "await self._db.flush()",
            )
        ),
        encoding="utf-8",
    )

    reasons = [violation.reason for violation in _boundary_violations(path)]

    assert reasons == [
        "imports src.dataservice.domains.mission.repository",
        "imports src.database.models.mission",
        "imports src.database.session",
        "imports sqlalchemy",
        "calls session factory get_async_session_factory",
        "performs business SQL through session.execute",
        "performs business SQL through db.flush",
    ]


def test_dataservice_client_is_the_only_dataservice_access_from_guarded_layers(
    tmp_path: Path,
) -> None:
    path = tmp_path / "src" / "mission_runtime" / "sample.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "\n".join(
            (
                "from src.dataservice_client import AsyncDataServiceClient",
                "from src.dataservice_client.contracts.mission import MissionRunPayload",
                "from src.dataservice_client.mission_client import MissionDataServiceClient",
            )
        ),
        encoding="utf-8",
    )

    assert _boundary_violations(path) == []


def test_runtime_layers_keep_dataservice_as_the_transaction_owner() -> None:
    violations: list[str] = []
    for path in _guarded_python_files():
        relative = path.relative_to(SRC_ROOT)
        violations.extend(
            f"{relative}:{violation.line} {violation.reason}"
            for violation in _boundary_violations(path)
        )

    assert not violations, (
        "Gateway, MissionRuntime, WorkspaceAgent, SubagentRuntime, and "
        "ReviewCommitRuntime must use typed DataService clients; DataService alone "
        "owns repositories, database models, sessions, and business SQL:\n"
        + "\n".join(violations)
    )
