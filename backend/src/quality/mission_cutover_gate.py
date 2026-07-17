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
    "backend/Makefile",
    "backend/config.yaml",
    "backend/langgraph.json",
    "backend/pyproject.toml",
    "docker-compose.local-build.yml",
    "docker-compose.yml",
)
SOURCE_SUFFIXES = frozenset(
    {".json", ".py", ".sh", ".toml", ".ts", ".tsx", ".yaml", ".yml"}
)
EXCLUDED_PRODUCTION_FILES = frozenset(
    {"backend/src/quality/mission_cutover_gate.py"}
)
FORBIDDEN_PRODUCTION_PATH_PREFIXES = {
    "old_yaml_runtime_config": ("backend/config.yaml",),
    "old_runtime_config_loader": ("backend/src/config/config_loader.py",),
    "old_billing_policy_facade": ("backend/src/services/billing_policy.py",),
    "old_langgraph_server_config": ("backend/langgraph.json",),
    "old_chat_agent_path": ("backend/src/agents/chat_agent/",),
    "old_lead_agent_path": ("backend/src/agents/lead_agent/",),
    "old_execution_path": ("backend/src/execution/",),
    "old_operations_path": ("backend/src/dataservice/domains/operations/",),
    "old_capability_seed_path": ("backend/seed/capabilities/",),
    "old_public_skill_path": ("backend/skills/public/",),
    "old_agent_middleware_path": ("backend/src/agents/middlewares/",),
    "old_agent_thread_state_path": ("backend/src/agents/thread_state.py",),
    "old_builtin_tool_path": ("backend/src/tools/builtins/",),
    "old_subagents_path": ("backend/src/subagents/",),
    "old_thesis_runtime_path": ("backend/src/thesis/",),
    "old_mcp_runtime_path": ("backend/src/mcp/",),
    "old_dataservice_sandbox_path": (
        "backend/src/dataservice/domains/sandbox/",
        "backend/src/dataservice/sandbox_api.py",
        "backend/src/dataservice_app/routers/sandbox.py",
        "backend/src/dataservice_client/sandbox_client.py",
        "backend/src/dataservice_client/contracts/sandbox.py",
    ),
    "old_memory_capture_path": (
        "backend/src/agents/memory/capture.py",
        "backend/src/agents/memory/queue.py",
        "backend/src/services/memory_capture_service.py",
        "backend/src/task/tasks/memory.py",
    ),
    "old_event_bus_path": ("backend/src/services/event_bus.py",),
    "old_thread_usage_accumulator_path": (
        "backend/src/services/thread_billing.py",
        "backend/src/services/token_usage_collector.py",
    ),
    "old_observability_shim_path": (
        "backend/src/observability/metrics.py",
        "backend/src/observability/tracing.py",
    ),
    "old_parallel_latex_editor_path": ("frontend/components/latex/",),
    "old_frontend_latex_state_path": (
        "frontend/stores/latex.ts",
        "frontend/lib/api/latex.ts",
    ),
    "old_latex_direct_docker_client_path": (
        "backend/src/services/latex/docker_client.py",
    ),
    "old_latex_compile_router_path": (
        "backend/src/gateway/routers/latex_compile.py",
    ),
    "old_latex_compile_service_path": (
        "backend/src/services/latex/compile_service.py",
        "backend/src/services/latex/engine_config.py",
        "backend/src/services/latex/feedback_revision_service.py",
        "backend/src/gateway/routers/latex_feedback.py",
    ),
}

RULES: tuple[CutoverRule, ...] = (
    CutoverRule(
        "old_langgraph_server_surface",
        re.compile(
            r"\bdebug-langgraph\b|\bLANGGRAPH_IMAGE\b"
            r"|\bNEXT_PUBLIC_LANGGRAPH_BASE_URL\b|\bwenjin-langgraph\b"
            r"|\blanggraph-cli\b|^FROM base AS langgraph$"
        ),
    ),
    CutoverRule(
        "old_token_credit_policy",
        re.compile(
            r"\bTokenBillingPolicy\b|\bTokenBillingCharge\b"
            r"|\bcalculate_token_billing_charge\b|\btokens_per_credit\b"
        ),
        ("backend/src",),
    ),
    CutoverRule(
        "old_chat_turn_accounting_surface",
        re.compile(
            r"\bappend_conversation_message\b|\bappend_thread_message\b"
            r"|\bensure_thread_turn_budget\b|\bcan_start_thread_turn\b"
            r"|\bhas_thread_turn_capacity\b|\bget_consumed_thread_tokens\b"
            r"|\brecord_credit_consumption\b|\bget_credit_consumed_tokens\b"
            r"|\brollback_last_user_message\b|\bchat_turn_credit_reserve\b"
            r"|\bmax_total_tokens\b|\breserved_thread_tokens\b"
            r"|\bConversationMessagesRebuild(?:Command|Payload)\b"
            r"|\brebuild_conversation_messages\b|\brebuild_messages\b"
            r"|\breplace_thread_messages\b|\block_conversation_thread\b"
            r"|\bdirect:|chat-turn:\{run_id\}"
            r"|\bCHAT_TURN_REQUEST_ID_METADATA_KEY\b|_chat_turn_request_id"
        ),
        ("backend/src", "backend/seed"),
    ),
    CutoverRule(
        "old_execution_record",
        re.compile(r"\bExecution(?:Node)?Record\b"),
    ),
    CutoverRule(
        "old_execution_provenance",
        re.compile(r"\bexecution:"),
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
        re.compile(
            r"\bsupports_(?:tools|json_mode|json_schema|streaming|vision|reasoning_effort)\b"
        ),
        (
            "backend/src/config/llm_config.py",
            "backend/src/database/models/model_catalog.py",
            "backend/src/dataservice/domains/model_catalog",
            "backend/src/dataservice_client/contracts/model_catalog.py",
            "backend/src/services/model_catalog_cache.py",
            "frontend/app/dashboard/admin/models",
            "frontend/lib/api/admin-models.ts",
            "frontend/lib/api/types.ts",
        ),
    ),
    CutoverRule(
        "old_model_provider_protocol",
        re.compile(r"\bprovider_protocol\b"),
        (
            "backend/src/dataservice/domains/model_catalog",
            "backend/src/dataservice_client/contracts/model_catalog.py",
            "frontend/app/dashboard/admin/models",
            "frontend/lib/api/admin-models.ts",
            "frontend/lib/api/types.ts",
        ),
    ),
    CutoverRule(
        "old_thread_checkpoint_api",
        re.compile(
            r"\bPlatformThread(?:Response|Summary|State|HistoryEntry)\b"
            r"|[\"'`](?:/api)?/threads(?:/\{thread_id\})?/(?:search|state|history)"
        ),
        (
            "backend/src/gateway/routers/threads.py",
            "frontend/lib/api/threads.ts",
            "frontend/lib/api/types.ts",
        ),
    ),
    CutoverRule(
        "old_frontend_latex_adapter_route",
        re.compile(r"/prism/latex-adapter"),
        (
            "frontend/app",
            "frontend/components",
            "frontend/hooks",
            "frontend/lib",
            "frontend/stores",
        ),
    ),
    CutoverRule(
        "old_prism_dual_review_projection",
        re.compile(r"\b(?:file_changes|applied_file_changes)\b"),
        (
            "backend/src/gateway/routers/workspaces_contracts.py",
            "frontend/lib/api/types.ts",
        ),
    ),
    CutoverRule(
        "old_billing_compatibility_surface",
        re.compile(
            r"\b(?:CreditReservationScope|SandboxPricingPolicyConfig"
            r"|OperationBillingPolicy|SandboxPricingEstimate)\b"
            r"|\b(?:get_public_workflow_costs|get_workflow_costs"
            r"|get_mission_billing_policy|get_sandbox_billing_policy"
            r"|refund_failed_task)\b"
            r"|\bsandbox_operation_billing\b"
        ),
    ),
    CutoverRule(
        "hardcoded_registration_credit_bonus",
        re.compile(
            r"^\s*REGISTRATION_BONUS\s*=\s*\d+"
            r"|\bgrant_registration_bonus\b"
        ),
        ("backend/src/services/credit_service.py",),
    ),
    CutoverRule(
        "old_external_credit_reservation_transport",
        re.compile(
            r"/internal/v1/credit/(?:reservations|refund)"
            r"|\bCreditReservation(?:Create|Settle|Release)Payload\b"
            r"|\bCreditRefundPayload\b"
        ),
    ),
    CutoverRule(
        "old_memory_worker",
        re.compile(r"\bmemory-worker\b|\bmemory_queue\b"),
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
