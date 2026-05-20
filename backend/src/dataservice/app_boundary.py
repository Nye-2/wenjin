"""DataService boundary constants used by guards and future migrations."""

from __future__ import annotations

DATASERVICE_PACKAGE_ROOTS = (
    "src.dataservice",
    "src.dataservice_app",
    "src.dataservice_client",
)

FORBIDDEN_DOMAIN_IMPORT_PREFIXES = (
    "src.agents",
    "src.application",
    "src.compute",
    "src.execution",
    "src.gateway",
    "src.services",
    "src.task",
    "src.tools",
)


def is_dataservice_package(module: str) -> bool:
    """Return whether a module belongs to the DataService boundary."""
    return any(module == root or module.startswith(root + ".") for root in DATASERVICE_PACKAGE_ROOTS)
