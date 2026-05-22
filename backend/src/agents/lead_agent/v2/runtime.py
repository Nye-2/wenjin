"""Lead Agent v2 runtime — resolves capability, compiles graph, executes, returns TaskReport."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypedDict

from src.agents.contracts.task_brief import TaskBrief
from src.agents.contracts.task_report import ResultError, ResultOutput, TaskReport
from src.agents.lead_agent.v2.compiler import compile_graph
from src.agents.lead_agent.v2.output_mapping import OutputMappingResolver
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
    capability_policy: dict[str, Any]


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
        set_graph_structure: Callable | None = None,
        record_node_event: Callable | None = None,
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
            set_graph_structure: Async callable (graph_structure: dict) → None.
                Called once after computing the graph structure to persist it.
            record_node_event: Async callable used to persist per-node lifecycle
                events (running / completed / failed) so the frontend node
                detail endpoint can render real input/output/thinking instead
                of an empty row.  Signature::

                    async def record(
                        *, execution_id: str, node_id: str, node_type: str,
                        label: str | None, status: str,
                        input_data: dict | None = None,
                        output_data: dict | None = None,
                        thinking: str | None = None,
                        tool_calls: list | None = None,
                        token_usage: dict | None = None,
                        error: str | None = None,
                    ) -> None
        """
        self.resolver = resolver
        self.publish_event = publish_event or _noop_publish
        self.get_workspace_type = get_workspace_type or _stub_get_ws_type
        self.redis = redis
        self.set_graph_structure = set_graph_structure
        self.record_node_event = record_node_event or _noop_record_node

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
        started_at = datetime.now(UTC)

        ws_type = await self.get_workspace_type(brief.workspace_id)
        cap = await self.resolver.resolve(brief.capability_id, ws_type)

        # Publish graph structure for the frontend panel
        graph_structure = self._to_panel_graph(cap.graph_template)
        await self.publish_event(
            execution_id,
            "execution.graph_structure",
            {"graph_structure": graph_structure},
        )

        # Persist graph_structure to ExecutionRecord
        if self.set_graph_structure is not None:
            try:
                await self.set_graph_structure(graph_structure)
            except Exception:
                logger.warning("Failed to persist graph_structure", exc_info=True)

        # Assemble initial state
        initial_state: ExecutionState = {
            "workspace_id": brief.workspace_id,
            "execution_id": execution_id,
            "inputs_for_tasks": self._distribute_brief(brief, cap),
            "workspace_data": {},
            "node_results": {},
            "capability_policy": self._capability_policy(cap),
        }

        # Compile + Execute — both are wrapped so unknown subagent_type is also caught
        try:
            # Pre-load skills referenced by tasks
            skills = await self._load_skills_for_template(cap.graph_template)

            # Check abort before starting (covers cancel-before-run race)
            if await self._check_abort(execution_id):
                raise ExecutionAborted(f"execution {execution_id} was cancelled before start")
            graph = compile_graph(
                cap.graph_template,
                state_class=ExecutionState,
                runner_factory=self._build_persisting_runner_factory(
                    execution_id, cap.graph_template,
                ),
                abort_check=lambda: self._check_abort(execution_id),
                skills=skills,
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
        duration = int((datetime.now(UTC) - started_at).total_seconds())
        outputs = self._collect_outputs(final_state, cap)
        narrative = self._build_narrative(cap, final_state)
        token_usage = self._aggregate_token_usage(final_state)
        review_items = await self._load_review_items_for_execution(
            workspace_id=brief.workspace_id,
            execution_id=execution_id,
        )

        report = TaskReport(
            execution_id=execution_id,
            capability_id=brief.capability_id,
            status=status,
            duration_seconds=duration,
            token_usage=token_usage,
            narrative=narrative,
            outputs=outputs,
            review_items=review_items,
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

    @staticmethod
    def _capability_policy(cap: Any) -> dict[str, Any]:
        definition = getattr(cap, "definition_json", None)
        if not isinstance(definition, dict):
            definition = {}
        return {
            "mission": dict(definition.get("mission") or {}),
            "context_policy": dict(definition.get("context_policy") or {}),
            "sandbox_policy": dict(definition.get("sandbox_policy") or {}),
            "review_policy": dict(definition.get("review_policy") or {}),
            "quality_gates": list(definition.get("quality_gates") or []),
        }

    async def _load_skills_for_template(self, template: dict) -> dict[str, Any]:
        """Pre-load all skills referenced by tasks in the template."""
        from src.dataservice_client.provider import dataservice_client

        skill_ids: set[str] = set()
        for phase in template.get("phases", []):
            for task in phase.get("tasks", []):
                sid = task.get("skill_id")
                if sid:
                    skill_ids.add(sid)
        if not skill_ids:
            return {}
        try:
            async with dataservice_client() as client:
                skills = await client.list_catalog_skills()
                return {skill.id: skill for skill in skills if skill.id in skill_ids}
        except Exception:
            logger.warning("Failed to pre-load skills", exc_info=True)
            return {}

    async def _load_review_items_for_execution(
        self,
        *,
        workspace_id: str,
        execution_id: str,
    ) -> list[dict[str, Any]]:
        """Load canonical Prism review items produced by this execution."""
        from src.dataservice_client.provider import dataservice_client
        from src.services.prism_review_projection import prism_review_item_projection

        try:
            async with dataservice_client() as client:
                items = await client.list_review_items(
                    workspace_id=workspace_id,
                    execution_id=execution_id,
                    target_domain="prism",
                )
                return [
                    prism_review_item_projection(item, execution_id=execution_id)
                    for item in items
                ]
        except Exception:
            logger.warning("Failed to load Prism review items", exc_info=True)
            return []

    async def _check_abort(self, execution_id: str) -> bool:
        """Return True if a Redis abort signal exists for this execution."""
        if self.redis is None:
            return False
        try:
            val = await self.redis.get(f"abort:exec:{execution_id}")
            return val is not None
        except Exception:
            return False

    def _build_persisting_runner_factory(
        self,
        execution_id: str,
        graph_template: dict,
    ) -> Callable:
        """Wrap ``_default_runner_factory`` so each node lifecycle event is
        persisted via ``self.record_node_event`` and published via
        ``self.publish_event``.

        Frontend's node-detail polling expects the ``execution_nodes`` table to
        contain a row per ``{phase}__{task}`` with the rendered ``input_data``
        and the subagent's ``output_data`` / ``thinking`` / error.  Without
        this, nodes sit at "pending" forever even after the run finishes.
        """
        from src.agents.lead_agent.v2.compiler import _default_runner_factory
        from src.agents.lead_agent.v2.template import (
            build_task_render_context,
            render_template,
        )

        # Build (task_name → node_id, label, node_type) lookup so we don't
        # have to walk phases inside every node call.
        node_meta: dict[str, dict[str, str]] = {}
        phase_index: dict[str, list[str]] = {}
        for phase in graph_template["phases"]:
            phase_index[phase["name"]] = [t["name"] for t in phase["tasks"]]
            for task in phase["tasks"]:
                node_id = f"{phase['name']}__{task['name']}"
                node_meta[task["name"]] = {
                    "node_id": node_id,
                    "node_type": task.get("subagent_type", "subagent"),
                    "label": task.get("label", task["name"]),
                }

        recorder = self.record_node_event
        publish = self.publish_event

        async def _emit(node_id: str, status: str, **fields: Any) -> None:
            await publish(
                execution_id,
                "execution.node",
                {"node_id": node_id, "status": status, **fields},
            )

        # Throttled thinking-delta emitter (flushes every 500 ms per node)
        _thinking_buffers: dict[str, str] = {}
        _last_flush: dict[str, float] = {}

        async def _emit_delta(node_id: str, content: str) -> None:
            buf = _thinking_buffers.get(node_id, "") + content
            _thinking_buffers[node_id] = buf
            now = time.monotonic()
            last = _last_flush.get(node_id, 0.0)
            if now - last >= 0.5:
                await publish(
                    execution_id,
                    "execution.node.delta",
                    {"node_id": node_id, "thinking": buf},
                )
                _last_flush[node_id] = now
                _thinking_buffers[node_id] = ""

        async def _flush_delta(node_id: str) -> None:
            buf = _thinking_buffers.get(node_id, "")
            if not buf:
                return
            await publish(
                execution_id,
                "execution.node.delta",
                {"node_id": node_id, "thinking": buf},
            )
            _last_flush[node_id] = time.monotonic()
            _thinking_buffers[node_id] = ""

        def factory(subagent_cls: Any, task_spec: dict) -> Callable:
            task_name = task_spec["name"]
            meta = node_meta.get(task_name, {
                "node_id": task_name,
                "node_type": task_spec.get("subagent_type", "subagent"),
                "label": task_name,
            })

            async def _node_emit_delta(event_type: str, content: str) -> None:
                if event_type == "thinking":
                    await _emit_delta(meta["node_id"], content)

            inner = _default_runner_factory(subagent_cls, task_spec, emit_delta=_node_emit_delta)
            raw_inputs_template = task_spec.get("inputs") or {}

            async def persisting_run(state: dict) -> dict:
                # Recompute the rendered inputs for the node-state record so
                # the FE sees the actual inputs the subagent ran with — not the
                # raw template strings.  The inner runner will compute and use
                # its own rendered copy too; we just need them for the DB row.
                brief = state.get("inputs_for_tasks", {}).get(task_name, {})
                try:
                    if raw_inputs_template:
                        render_ctx = build_task_render_context(
                            brief=brief,
                            node_results=state.get("node_results", {}),
                            phase_index=phase_index,
                        )
                        rendered_inputs: Any = render_template(
                            raw_inputs_template, render_ctx,
                        )
                    else:
                        rendered_inputs = dict(brief)
                except Exception:
                    rendered_inputs = dict(brief)

                started_at = datetime.now(UTC)
                try:
                    await recorder(
                        execution_id=execution_id,
                        node_id=meta["node_id"],
                        node_type=meta["node_type"],
                        label=meta.get("label"),
                        status="running",
                        input_data=rendered_inputs if isinstance(rendered_inputs, dict) else {"value": rendered_inputs},
                        started_at=started_at,
                    )
                    await _emit(meta["node_id"], "running")
                except Exception:
                    logger.warning(
                        "Failed to record node 'running' for %s", meta["node_id"],
                        exc_info=True,
                    )

                result_state = await inner(state)

                # Resolve the per-node payload from the latest node_results.
                node_result = (result_state or {}).get("node_results", {}).get(task_name, {})
                completed_at = datetime.now(UTC)
                try:
                    await _flush_delta(meta["node_id"])
                    if isinstance(node_result, dict) and "error" in node_result:
                        await recorder(
                            execution_id=execution_id,
                            node_id=meta["node_id"],
                            node_type=meta["node_type"],
                            label=meta.get("label"),
                            status="failed",
                            output_data={"error": node_result["error"]},
                            completed_at=completed_at,
                        )
                        await _emit(meta["node_id"], "failed", error=node_result["error"])
                    else:
                        await recorder(
                            execution_id=execution_id,
                            node_id=meta["node_id"],
                            node_type=meta["node_type"],
                            label=meta.get("label"),
                            status="completed",
                            output_data=node_result.get("output") if isinstance(node_result, dict) else None,
                            thinking=node_result.get("thinking") if isinstance(node_result, dict) else None,
                            tool_calls=node_result.get("tool_calls") if isinstance(node_result, dict) else None,
                            token_usage=node_result.get("token_usage") if isinstance(node_result, dict) else None,
                            completed_at=completed_at,
                        )
                        await _emit(meta["node_id"], "completed")
                except Exception:
                    logger.warning(
                        "Failed to record node final state for %s", meta["node_id"],
                        exc_info=True,
                    )

                return result_state

            return persisting_run

        return factory

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
                task_inputs = dict(brief.brief)
                if brief.manuscript_context:
                    task_inputs["manuscript_context"] = brief.manuscript_context
                result[task["name"]] = task_inputs
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
        graph_template = cap.graph_template if hasattr(cap, "graph_template") else {}
        node_results = state.get("node_results", {})
        if not graph_template or not node_results:
            return []
        return OutputMappingResolver().resolve(graph_template, node_results)

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


async def _noop_record_node(*args: Any, **kwargs: Any) -> None:
    """No-op node-event recorder used when no record_node_event is provided."""
