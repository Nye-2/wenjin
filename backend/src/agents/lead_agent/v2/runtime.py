"""Lead Agent v2 runtime — resolves capability, compiles graph, executes, returns TaskReport."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, TypedDict

from src.agents.contracts.task_brief import TaskBrief
from src.agents.contracts.task_report import ResultError, ResultOutput, TaskReport
from src.agents.lead_agent.v2.compiler import compile_graph
from src.services.capability_resolver import CapabilityResolver

logger = logging.getLogger(__name__)


class ExecutionAborted(Exception):
    """Raised when the execution is cancelled via the Redis abort signal."""


class ExecutionState(TypedDict, total=False):
    """LangGraph state threaded through all subagent nodes."""

    workspace_id: str
    execution_id: str
    inputs_for_tasks: dict
    workspace_data: dict
    node_results: dict


class LeadAgentRuntime:
    """Runs a capability end-to-end and returns a TaskReport.

    Responsibilities (spec §4.2.6):
    1. Resolve capability via CapabilityResolver
    2. Compile graph_template → LangGraph
    3. Publish execution.graph_structure event
    4. Invoke graph (subagents run in nodes)
    5. Publish execution.completed event
    6. Build TaskReport
    """

    def __init__(
        self,
        *,
        resolver: CapabilityResolver,
        publish_event: Callable | None = None,
        get_workspace_type: Callable | None = None,
        redis: Any | None = None,
    ) -> None:
        """
        Args:
            resolver: CapabilityResolver instance used to load capabilities.
            publish_event: Async callable (execution_id, event_name, payload) → None.
                Defaults to a no-op if not supplied.
            get_workspace_type: Async callable (workspace_id) → str.
                Defaults to a stub that returns "thesis".
            redis: Optional async Redis client used to poll abort signals.
                If None, abort checking is skipped.
        """
        self.resolver = resolver
        self.publish_event = publish_event or _noop_publish
        self.get_workspace_type = get_workspace_type or _stub_get_ws_type
        self.redis = redis

    async def run_session(
        self,
        *,
        execution_id: str,
        brief: TaskBrief,
    ) -> TaskReport:
        """Execute one capability invocation from start to finish.

        Args:
            execution_id: Unique identifier for this execution run.
            brief: TaskBrief describing the capability and inputs.

        Returns:
            TaskReport with status, outputs, narrative, and optional errors.
        """
        started_at = datetime.now(timezone.utc)

        ws_type = await self.get_workspace_type(brief.workspace_id)
        cap = await self.resolver.resolve(brief.capability_id, ws_type)

        # Publish graph structure for the frontend panel
        graph_structure = self._to_panel_graph(cap.graph_template)
        await self.publish_event(
            execution_id,
            "execution.graph_structure",
            {"graph_structure": graph_structure},
        )

        # Assemble initial state
        initial_state: ExecutionState = {
            "workspace_id": brief.workspace_id,
            "execution_id": execution_id,
            "inputs_for_tasks": self._distribute_brief(brief, cap),
            "workspace_data": {},
            "node_results": {},
        }

        # Compile + Execute — both are wrapped so unknown subagent_type is also caught
        try:
            # Check abort before starting (covers cancel-before-run race)
            if await self._check_abort(execution_id):
                raise ExecutionAborted(f"execution {execution_id} was cancelled before start")
            graph = compile_graph(
                cap.graph_template,
                state_class=ExecutionState,
                abort_check=lambda: self._check_abort(execution_id),
            )
            final_state = await graph.ainvoke(initial_state)
            errors: list[ResultError] = []
            status = "completed"
        except ExecutionAborted:
            logger.info("execution %s was cancelled", execution_id)
            final_state = initial_state
            errors = []
            status = "cancelled"
        except Exception as exc:
            logger.exception(
                "graph execution failed",
                extra={"execution_id": execution_id},
            )
            final_state = initial_state
            errors = [ResultError(phase="-", task="-", error=str(exc))]
            status = "failed_partial"

        # Scan node_results for per-node errors (Task 2.12 failure handling)
        if status == "completed":
            node_errors = self._collect_node_errors(final_state, cap)
            if node_errors:
                errors = node_errors
                status = "failed_partial"

        # Build report
        duration = int((datetime.now(timezone.utc) - started_at).total_seconds())
        outputs = self._collect_outputs(final_state, cap)
        narrative = self._build_narrative(cap, final_state)
        token_usage = self._aggregate_token_usage(final_state)

        report = TaskReport(
            execution_id=execution_id,
            capability_id=brief.capability_id,
            status=status,
            duration_seconds=duration,
            token_usage=token_usage,
            narrative=narrative,
            outputs=outputs,
            errors=errors,
        )

        await self.publish_event(
            execution_id,
            "execution.completed",
            report.model_dump(mode="json"),
        )
        return report

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _check_abort(self, execution_id: str) -> bool:
        """Return True if a Redis abort signal exists for this execution."""
        if self.redis is None:
            return False
        try:
            val = await self.redis.get(f"abort:exec:{execution_id}")
            return val is not None
        except Exception:
            return False

    def _to_panel_graph(self, template: dict) -> dict:
        """Translate capability template into Panel-friendly nodes + edges structure."""
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        for phase in template["phases"]:
            for task in phase["tasks"]:
                nid = f"{phase['name']}__{task['name']}"
                nodes.append(
                    {
                        "id": nid,
                        "phase": phase["name"],
                        "task": task["name"],
                        "subagent_type": task["subagent_type"],
                        "label": task.get("display_name", task["name"]),
                    }
                )

        # Phase deps → edges between every src.task and every dst.task
        for phase in template["phases"]:
            for dep in phase.get("depends_on", []):
                dep_phase = next(p for p in template["phases"] if p["name"] == dep)
                for src_t in dep_phase["tasks"]:
                    for dst_t in phase["tasks"]:
                        edges.append(
                            {
                                "from": f"{dep_phase['name']}__{src_t['name']}",
                                "to": f"{phase['name']}__{dst_t['name']}",
                            }
                        )

        return {"nodes": nodes, "edges": edges}

    def _distribute_brief(self, brief: TaskBrief, cap: Any) -> dict:
        """V1: every task receives the full brief.brief dict as inputs."""
        result: dict[str, dict] = {}
        for phase in cap.graph_template["phases"]:
            for task in phase["tasks"]:
                result[task["name"]] = dict(brief.brief)
        return result

    def _collect_node_errors(self, state: dict, cap: Any) -> list[ResultError]:
        """Scan node_results for entries that have an "error" key (Task 2.12)."""
        node_results = state.get("node_results", {})
        errors: list[ResultError] = []
        for phase in cap.graph_template.get("phases", []):
            for task in phase.get("tasks", []):
                task_name = task["name"]
                nr = node_results.get(task_name)
                if isinstance(nr, dict) and "error" in nr and "output" not in nr:
                    errors.append(
                        ResultError(
                            phase=phase["name"],
                            task=task_name,
                            error=nr["error"],
                        )
                    )
        return errors

    def _collect_outputs(self, state: dict, cap: Any) -> list[ResultOutput]:
        """V1: return empty list.

        TODO (Phase 2 follow-up): capability YAML will declare 'output_mapping'
        rules that translate node_results.{task_name}.output into typed
        ResultOutput objects (library_item, document, memory_fact, etc.).
        """
        return []

    def _build_narrative(self, cap: Any, state: dict) -> str:
        n_nodes = len(state.get("node_results", {}))
        return f"完成 {cap.display_name}，共执行 {n_nodes} 个节点。"

    def _aggregate_token_usage(self, state: dict) -> dict[str, int] | None:
        usage: dict[str, int] = {"input": 0, "output": 0}
        for node_result in state.get("node_results", {}).values():
            tu = node_result.get("token_usage") or {}
            usage["input"] += tu.get("input", 0)
            usage["output"] += tu.get("output", 0)
        return usage if (usage["input"] or usage["output"]) else None


# ---------------------------------------------------------------------------
# Default callables
# ---------------------------------------------------------------------------


async def _noop_publish(*args: Any, **kwargs: Any) -> None:
    """No-op event publisher used when no publish_event is provided."""


async def _stub_get_ws_type(workspace_id: str) -> str:
    """Stub workspace-type resolver that always returns 'thesis'."""
    return "thesis"
