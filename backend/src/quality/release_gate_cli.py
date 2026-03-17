"""CLI entrypoint for running release gate checks."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from src.services.release_gate_service import ReleaseGateService


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 3 release gate checks.")
    parser.add_argument(
        "--include-extended",
        action="store_true",
        help="Run extended integration checks in addition to core checks.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=600,
        help="Timeout in seconds for each check command.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output path for JSON report.",
    )
    return parser


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    service = ReleaseGateService(timeout_seconds=args.timeout_seconds)
    return await service.run(include_extended=args.include_extended)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    report = asyncio.run(_run(args))

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")

    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

