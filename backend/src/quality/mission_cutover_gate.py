"""Production-path guard for the Mission Runtime clean cutover."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class CutoverRule:
    id: str
    pattern: re.Pattern[str]
    path_prefixes: tuple[str, ...] = ()


@dataclass(frozen=True)
class CutoverFinding:
    rule_id: str
    path: str
    line: int
    excerpt: str


PRODUCTION_ROOTS = (
    "backend/src",
    "backend/seed",
    "backend/skills",
    "frontend/app",
    "frontend/components",
    "frontend/hooks",
    "frontend/lib",
    "frontend/stores",
    "scripts",
)
PRODUCTION_FILES = (
    ".env.example",
    "backend/Dockerfile",
    "backend/config.yaml",
    "backend/extensions_config.json",
    "backend/pyproject.toml",
    "docker-compose.yml",
)
SOURCE_SUFFIXES = frozenset(
    {".json", ".py", ".sh", ".toml", ".ts", ".tsx", ".yaml", ".yml"}
)
EXCLUDED_PRODUCTION_FILES = frozenset(
    {"backend/src/quality/mission_cutover_gate.py"}
)
FORBIDDEN_PRODUCTION_PATH_PREFIXES = {
    "old_chat_agent_path": ("backend/src/agents/chat_agent/",),
    "old_lead_agent_path": ("backend/src/agents/lead_agent/",),
    "old_execution_path": ("backend/src/execution/",),
    "old_operations_path": ("backend/src/dataservice/domains/operations/",),
    "old_capability_seed_path": ("backend/seed/capabilities/",),
    "old_public_skill_path": ("backend/skills/public/",),
}

RULES: tuple[CutoverRule, ...] = (
    CutoverRule(
        "old_execution_record",
        re.compile(r"\bExecution(?:Node)?Record\b"),
    ),
    CutoverRule(
        "old_lead_agent_runtime",
        re.compile(r"\bLeadAgentRuntime\b|agents[./]lead_agent"),
    ),
    CutoverRule(
        "old_feature_launcher",
        re.compile(r"\blaunch_feature\b"),
    ),
    CutoverRule(
        "old_execution_state_blob",
        re.compile(r"\bnode_states_json\b"),
    ),
    CutoverRule(
        "old_review_ssot",
        re.compile(r"\bReviewBatch\b|\bChangeSet\b|\baccepted_(?:unit_)?ids\b"),
    ),
    CutoverRule(
        "old_search_provider",
        re.compile(r"semantic_scholar|curated_academic|deep_search", re.IGNORECASE),
    ),
    CutoverRule(
        "old_search_provider_dependency",
        re.compile(r'^\s*"(?:arxiv|semanticscholar)[<=>~!]', re.IGNORECASE),
        ("backend/pyproject.toml",),
    ),
    CutoverRule(
        "old_brand_config",
        re.compile(r"\bGUANLAN_[A-Z0-9_]+\b"),
    ),
    CutoverRule(
        "old_thread_skill_selector",
        re.compile(
            r"\bskill_explicit\b|\bcurrent_skill(?:_name)?\b|\bskills_path\b"
            r"|\bthread\.skill\b|\bgeneration_records\b"
        ),
    ),
    CutoverRule(
        "heterogeneous_workspace_activity_projection",
        re.compile(r"\bbuild_(?:task|thread)_activity_item\b"),
    ),
    CutoverRule(
        "old_fixed_subagent_config",
        re.compile(r"^\s*(?:subagents|types)\s*:", re.IGNORECASE),
        ("backend/config.yaml", "backend/seed"),
    ),
    CutoverRule(
        "old_config_tool_id",
        re.compile(
            r"\b(?:semantic_scholar_search|web_search|read_file|write_file|bash)\b",
            re.IGNORECASE,
        ),
        ("backend/config.yaml", "backend/seed"),
    ),
    CutoverRule(
        "old_operations_persistence",
        re.compile(
            r"\bDataService(?:OutboxEvent|IdempotencyKey|MigrationReport)\b"
            r"|\bappend_outbox_event\b|dataservice[./]domains[./]operations"
            r"|\bmission_operation_receipts\b|\bMissionOperationReceiptRecord\b"
        ),
    ),
    CutoverRule(
        "forbidden_mission_status",
        re.compile(r"MissionRunStatus\.(?:awaiting_user_review|committing|blocked)"),
    ),
    CutoverRule(
        "assistant_text_tool_protocol",
        re.compile(r"<\/?tool_call\b|<\/?arguments\b", re.IGNORECASE),
    ),
    CutoverRule(
        "unsupported_chat_search_tool",
        re.compile(r"web_search_preview|chat_search_model"),
    ),
    CutoverRule(
        "global_chat_turn_route",
        re.compile(r"[\"'`](?:/api)?/runs/(?:stream|wait|\{run_id\})"),
        (
            "backend/src/gateway",
            "frontend/app",
            "frontend/components",
            "frontend/hooks",
            "frontend/lib",
            "frontend/stores",
        ),
    ),
    CutoverRule(
        "configurable_sandbox_provider",
        re.compile(r"\bsandbox_provider\b"),
    ),
    CutoverRule(
        "old_harness_runtime",
        re.compile(
            r"\bHarnessRunContext\b|\bsandbox_execution_tools\b"
            r"|agents[./]harness[./](?:context_assembly|scheduler|diff_tracker|output_budget)"
        ),
    ),
    CutoverRule(
        "old_feature_task_contract",
        re.compile(
            r"\bFeatureExecution(?:Advisory|Outcome)\b|\bFeatureTaskSubmission\b"
            r"|\bfeature_execution_reservation_key\b"
        ),
    ),
    CutoverRule(
        "old_product_capability_contract",
        re.compile(
            r"\bcapability_overrides\b|\bcapability_goal\b"
            r"|\b(?:WorkspaceCapability|CapabilityTeamPresentationV1)\b"
            r"|services[./]capability_schema"
            r"|\bcapability (?:entry|execution|runs?)\b",
            re.IGNORECASE,
        ),
    ),
    CutoverRule(
        "old_feature_task_metric",
        re.compile(r"\bfeature_tasks\b"),
    ),
    CutoverRule(
        "old_auxiliary_task_context",
        re.compile(r"\bfeature_id\b|\bexecution_id\b"),
        (
            "backend/src/database/models/task.py",
            "backend/src/dataservice/domains/task",
            "backend/src/dataservice_client/contracts/task.py",
            "backend/src/task/progress.py",
            "backend/src/task/service.py",
            "backend/src/task/store.py",
        ),
    ),
    CutoverRule(
        "model_capability_compatibility_flags",
        re.compile(r"\bsupports_(?:tools|json_mode|json_schema)\b"),
        (
            "backend/src/config/llm_config.py",
            "backend/src/database/models/model_catalog.py",
            "backend/src/dataservice/domains/model_catalog",
            "backend/src/dataservice_client/contracts/model_catalog.py",
            "backend/src/services/model_catalog_cache.py",
        ),
    ),
)


def scan_mission_cutover(project_root: Path) -> list[CutoverFinding]:
    """Return forbidden old-runtime references from production source paths."""

    root = project_root.resolve()
    findings: list[CutoverFinding] = []
    for file_path in _production_files(root):
        relative_path = file_path.relative_to(root).as_posix()
        for rule_id, prefixes in FORBIDDEN_PRODUCTION_PATH_PREFIXES.items():
            if relative_path.startswith(prefixes):
                findings.append(
                    CutoverFinding(
                        rule_id=rule_id,
                        path=relative_path,
                        line=1,
                        excerpt="forbidden production path",
                    )
                )
        for line_number, line in enumerate(
            file_path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            for rule in RULES:
                if rule.path_prefixes and not relative_path.startswith(
                    rule.path_prefixes
                ):
                    continue
                if rule.pattern.search(line):
                    findings.append(
                        CutoverFinding(
                            rule_id=rule.id,
                            path=relative_path,
                            line=line_number,
                            excerpt=" ".join(line.strip().split())[:240],
                        )
                    )
    return findings


def build_cutover_report(project_root: Path) -> dict[str, object]:
    findings = scan_mission_cutover(project_root)
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.rule_id] = counts.get(finding.rule_id, 0) + 1
    return {
        "status": "passed" if not findings else "failed",
        "finding_count": len(findings),
        "counts_by_rule": dict(sorted(counts.items())),
        "findings": [asdict(finding) for finding in findings],
    }


def _production_files(project_root: Path) -> Iterable[Path]:
    for relative_file in PRODUCTION_FILES:
        path = project_root / relative_file
        if path.is_file():
            yield path
    for relative_root in PRODUCTION_ROOTS:
        source_root = project_root / relative_root
        if not source_root.exists():
            continue
        for path in sorted(source_root.rglob("*")):
            skill_markdown = relative_root == "backend/skills" and path.suffix == ".md"
            if not path.is_file() or (
                path.suffix not in SOURCE_SUFFIXES and not skill_markdown
            ):
                continue
            relative_path = path.relative_to(project_root).as_posix()
            if relative_path not in EXCLUDED_PRODUCTION_FILES:
                yield path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[3],
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Emit the migration baseline without failing the command.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_cutover_report(args.project_root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"Mission cutover gate: {report['status']} "
            f"({report['finding_count']} finding(s))"
        )
        for rule_id, count in report["counts_by_rule"].items():
            print(f"- {rule_id}: {count}")

    if args.report_only:
        return 0
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
