"""Report workspace Prism binding integrity issues.

Usage:
    cd backend && .venv/bin/python -m scripts.workspace_prism_integrity_report
    cd backend && .venv/bin/python -m scripts.workspace_prism_integrity_report --json
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


async def _run(*, user_id: str | None) -> dict[str, list[dict[str, Any]]]:
    async with get_db_session() as db:
        return await WorkspacePrismService(db).get_binding_integrity_report(
            user_id=user_id,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Report workspaces with missing or duplicate primary Prism projects.",
    )
    parser.add_argument("--user-id", help="Restrict report to a single user id")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Always exit 0 even when integrity issues are found",
    )
    args = parser.parse_args()

    report = asyncio.run(_run(user_id=args.user_id))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_format_report(report))

    if _issue_count(report) and not args.no_fail:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
