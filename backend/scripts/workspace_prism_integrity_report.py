"""Report workspace Prism binding integrity issues.

Usage:
    cd backend && .venv/bin/python -m scripts.workspace_prism_integrity_report
    cd backend && .venv/bin/python -m scripts.workspace_prism_integrity_report --json
    cd backend && .venv/bin/python -m scripts.workspace_prism_integrity_report --repair-missing
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from src.database import get_db_session
from src.services.workspace_prism_service import WorkspacePrismService


def _issue_count(report: dict[str, list[dict[str, Any]]]) -> int:
    return len(report["missing_primary"]) + len(report["duplicate_primary"])


def _format_report(report: dict[str, list[dict[str, Any]]]) -> str:
    lines: list[str] = []
    missing = report["missing_primary"]
    duplicates = report["duplicate_primary"]

    if not missing and not duplicates:
        return "Workspace Prism integrity: OK"

    if missing:
        lines.append("Missing primary manuscript projects:")
        for item in missing:
            lines.append(
                "- {workspace_id} ({workspace_name}) user={user_id}".format(**item)
            )

    if duplicates:
        if lines:
            lines.append("")
        lines.append("Duplicate primary manuscript projects:")
        for item in duplicates:
            lines.append(
                "- {workspace_id} ({workspace_name}) user={user_id} count={primary_count}".format(
                    **item
                )
            )

    return "\n".join(lines)


def _repair_project_name(item: dict[str, Any]) -> str:
    workspace_name = str(item.get("workspace_name") or "").strip()
    if workspace_name:
        return f"{workspace_name} Manuscript"
    return "Workspace Manuscript"


async def _repair_missing_primary(
    service: WorkspacePrismService,
    missing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    repaired: list[dict[str, Any]] = []
    for item in missing:
        project = await service.ensure_primary_project(
            str(item["workspace_id"]),
            user_id=str(item["user_id"]),
            project_name=_repair_project_name(item),
        )
        repaired.append(
            {
                "workspace_id": str(item["workspace_id"]),
                "user_id": str(item["user_id"]),
                "latex_project_id": str(project.id),
            }
        )
    return repaired


async def _run(
    *,
    user_id: str | None,
    repair_missing: bool,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    async with get_db_session() as db:
        service = WorkspacePrismService(db)
        report = await service.get_binding_integrity_report(
            user_id=user_id,
        )
        repaired: list[dict[str, Any]] = []
        if repair_missing and report["missing_primary"]:
            repaired = await _repair_missing_primary(service, report["missing_primary"])
            report = await service.get_binding_integrity_report(user_id=user_id)
        return report, repaired


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Report workspaces with missing or duplicate primary Prism projects.",
    )
    parser.add_argument("--user-id", help="Restrict report to a single user id")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument(
        "--repair-missing",
        action="store_true",
        help="Create or promote a primary Prism project for workspaces missing one.",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Always exit 0 even when integrity issues are found",
    )
    args = parser.parse_args()

    report, repaired = asyncio.run(
        _run(user_id=args.user_id, repair_missing=args.repair_missing)
    )
    if args.json:
        payload: Any = (
            {"report": report, "repaired_missing": repaired}
            if args.repair_missing
            else report
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if repaired:
            print(f"Repaired missing primary manuscript projects: {len(repaired)}")
        print(_format_report(report))

    if _issue_count(report) and not args.no_fail:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
