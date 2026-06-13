"""Lead Agent v2 runtime — resolves capability, compiles graph, executes, returns TaskReport."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Annotated, Any, TypedDict

from src.agents.contracts.task_brief import TaskBrief
from src.agents.contracts.task_report import (
    MemoryFactData,
    MemoryFactOutput,
    ResultError,
    ResultOutput,
    TaskReport,
)
from src.agents.harness.diff_tracker import build_harness_node_metadata_from_tool_calls
from src.agents.lead_agent.v2.compiler import compile_graph
from src.agents.lead_agent.v2.output_mapping import OutputMappingResolver
from src.agents.lead_agent.v2.prism_review_staging import (
    build_prism_file_change_command,
)
from src.agents.lead_agent.v2.runtime_context import RuntimeContextAssembler
from src.agents.lead_agent.v2.sandbox_artifact_review import (
    collect_sandbox_artifact_candidates,
    sandbox_artifact_payload_for_candidate,
    sandbox_review_item_projection,
    workspace_asset_payload_for_candidate,
)
from src.dataservice_client.contracts.source import SourceCitationUsageCreatePayload
from src.services.capability_resolver import CapabilityResolver
from src.services.references.utils import extract_citation_keys_from_text
from src.services.thread_billing import TokenUsage
from src.services.token_usage_collector import (
    bind_token_usage_collector,
    get_collected_token_usage,
    reset_token_usage_collector,
)

logger = logging.getLogger(__name__)


_MEMORY_BRIEF_LABELS = {
    "topic": "研究主题",
    "research_question": "研究问题",
    "target_journal": "目标期刊/会议",
    "target_conference": "目标会议",
    "deliverable": "交付物",
    "goal": "任务目标",
    "language": "写作语言",
    "method": "方法方向",
    "focus": "研究焦点",
}
_EMPTY_MEMORY_VALUES = {"", "待定", "unknown", "n/a", "none", "null"}


class ExecutionAborted(Exception):
    """Raised when the execution is cancelled via the Redis abort signal."""


def merge_node_results(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(left or {})
    merged.update(dict(right or {}))
    return merged


def _memory_facts_from_brief(brief: TaskBrief) -> list[MemoryFactData]:
    """Derive reviewable workspace memory candidates from a capability brief."""

    facts: list[MemoryFactData] = []
    payload = brief.brief if isinstance(brief.brief, dict) else {}
    for key, label in _MEMORY_BRIEF_LABELS.items():
        value = _stringify_memory_value(payload.get(key))
        if value is None:
            continue
        facts.append(
            MemoryFactData(
                content=f"{label}：{value}",
                category="context",
                confidence=0.9,
            )
        )

    if not facts:
        raw_message = _stringify_memory_value(brief.raw_message)
        if raw_message is not None:
            facts.append(
                MemoryFactData(
                    content=f"用户当前任务需求：{raw_message}",
                    category="context",
                    confidence=0.75,
                )
            )
    return facts[:3]


def _stringify_memory_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
    elif isinstance(value, (int, float, bool)):
        text = str(value).strip()
    elif isinstance(value, list):
        text = "、".join(str(item).strip() for item in value if str(item).strip())
    else:
        return None
    if not text or text.lower() in _EMPTY_MEMORY_VALUES:
        return None
    return text[:500]


class ExecutionState(TypedDict, total=False):
    """LangGraph state threaded through all subagent nodes."""

    workspace_id: str
    user_id: str
    execution_id: str
    inputs_for_tasks: dict
    workspace_data: dict
    node_results: Annotated[dict[str, Any], merge_node_results]
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
        self.context_assembler = RuntimeContextAssembler()

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

        runtime_kind = self._runtime_mode(cap)
        if runtime_kind == "team_kernel":
            graph_structure = self._to_team_panel_graph(cap)
            await self.publish_event(
                execution_id,
                "execution.graph_structure",
                {"graph_structure": graph_structure},
            )
            if self.set_graph_structure is not None:
                try:
                    await self.set_graph_structure(graph_structure)
                except Exception:
                    logger.warning("Failed to persist team graph_structure", exc_info=True)

            from src.agents.lead_agent.v2.team.kernel import TeamKernelRuntime

            report = await TeamKernelRuntime(
                publish_event=self.publish_event,
                record_node_event=self.record_node_event,
                abort_check=self._check_abort,
                load_workspace_data=self.context_assembler.load_workspace_data,
                needs_library_context=self.context_assembler.needs_library_context,
                capability_policy_builder=self._capability_policy,
                collect_policy_memory_outputs=self._collect_policy_memory_outputs,
            ).run(
                execution_id=execution_id,
                brief=brief,
                capability=cap,
                started_at=started_at,
            )
            await self.publish_event(
                execution_id,
                "execution.completed",
                report.model_dump(mode="json"),
            )
            return report

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

        capability_policy = self._capability_policy(cap)
        context_requirements = self.context_assembler.context_requirements_from_brief(brief)
        workspace_data = (
            await self.context_assembler.load_workspace_data(
                brief.workspace_id,
                capability_policy=capability_policy,
                context_requirements=context_requirements,
                user_id=brief.user_id,
            )
            if self.context_assembler.needs_workspace_context(capability_policy, context_requirements)
            else {}
        )

        # Assemble initial state
        initial_state: ExecutionState = {
            "workspace_id": brief.workspace_id,
            "user_id": brief.user_id,
            "execution_id": execution_id,
            "inputs_for_tasks": self._distribute_brief(
                brief,
                cap,
                workspace_data=workspace_data,
            ),
            "workspace_data": workspace_data,
            "node_results": {},
            "capability_policy": capability_policy,
        }

        collected_token_usage: TokenUsage | None = None
        collector_token = bind_token_usage_collector()
        try:
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
        finally:
            collected_token_usage = get_collected_token_usage()
            reset_token_usage_collector(collector_token)

        # Scan node_results for per-node errors (Task 2.12 failure handling)
        if status == "completed":
            node_errors = self._collect_node_errors(final_state, cap)
            if node_errors:
                errors = node_errors
                status = "failed_partial"

        # Build report
        duration = int((datetime.now(UTC) - started_at).total_seconds())
        outputs = self._collect_outputs(final_state, cap, brief=brief)
        narrative = self._build_narrative(cap, final_state)
        token_usage = self._aggregate_token_usage(
            final_state,
            collected_token_usage=collected_token_usage,
        )
        if status == "completed":
            await self._stage_prism_review_items(
                final_state,
                cap,
                brief=brief,
                execution_id=execution_id,
            )
            await self._stage_sandbox_artifact_review_items(
                final_state,
                brief=brief,
                execution_id=execution_id,
            )
            await self._sync_prism_bibliography(
                brief=brief,
                state=final_state,
            )
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
            "citation_policy": dict(definition.get("citation_policy") or {}),
            "research_evidence": dict(definition.get("research_evidence") or {}),
            "quality_gates": list(definition.get("quality_gates") or []),
        }

    @staticmethod
    def _runtime_mode(cap: Any) -> str:
        runtime = getattr(cap, "runtime", None)
        if isinstance(runtime, dict) and runtime.get("mode") == "team_kernel":
            return "team_kernel"
        return "static_graph"

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
        """Load canonical review items produced by this execution."""
        from src.dataservice_client.provider import dataservice_client
        from src.services.prism_review_projection import prism_review_item_projection

        review_items: list[dict[str, Any]] = []
        try:
            async with dataservice_client() as client:
                prism_items = await client.list_review_items(
                    workspace_id=workspace_id,
                    execution_id=execution_id,
                    target_domain="prism",
                )
                review_items.extend(
                    prism_review_item_projection(item, execution_id=execution_id)
                    for item in prism_items
                )
                sandbox_items = await client.list_review_items(
                    workspace_id=workspace_id,
                    execution_id=execution_id,
                    target_domain="sandbox",
                    target_kind="sandbox_artifact",
                )
                review_items.extend(
                    sandbox_review_item_projection(item, execution_id=execution_id)
                    for item in sandbox_items
                )
        except Exception:
            logger.warning("Failed to load execution review items", exc_info=True)
        return review_items

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

            inner = _default_runner_factory(
                subagent_cls,
                task_spec,
                emit_delta=_node_emit_delta,
                publish_event=publish,
            )
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
                    await _emit(
                        meta["node_id"],
                        "running",
                        input_data=rendered_inputs if isinstance(rendered_inputs, dict) else {"value": rendered_inputs},
                        started_at=started_at.isoformat(),
                    )
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
                        await _emit(
                            meta["node_id"],
                            "failed",
                            output_data={"error": node_result["error"]},
                            output_preview=str(node_result["error"])[:240],
                            completed_at=completed_at.isoformat(),
                            error=node_result["error"],
                        )
                    else:
                        output_data = node_result.get("output") if isinstance(node_result, dict) else None
                        thinking = node_result.get("thinking") if isinstance(node_result, dict) else None
                        tool_calls = node_result.get("tool_calls") if isinstance(node_result, dict) else None
                        token_usage = node_result.get("token_usage") if isinstance(node_result, dict) else None
                        node_metadata = build_harness_node_metadata_from_tool_calls(tool_calls)
                        await recorder(
                            execution_id=execution_id,
                            node_id=meta["node_id"],
                            node_type=meta["node_type"],
                            label=meta.get("label"),
                            status="completed",
                            output_data=output_data,
                            thinking=thinking,
                            tool_calls=tool_calls,
                            token_usage=token_usage,
                            node_metadata=node_metadata,
                            completed_at=completed_at,
                        )
                        await _emit(
                            meta["node_id"],
                            "completed",
                            output_data=output_data,
                            output_preview=_preview_output(output_data),
                            thinking=thinking,
                            tool_calls=tool_calls,
                            token_usage=token_usage,
                            node_metadata=node_metadata,
                            completed_at=completed_at.isoformat(),
                        )
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

    def _to_team_panel_graph(self, cap: Any) -> dict[str, Any]:
        """Return the stable team-kernel graph projection for the panel."""
        nodes: list[dict[str, Any]] = [
            {
                "id": "team_prepare",
                "phase": "team_kernel",
                "task": "prepare_context",
                "subagent_type": "leader",
                "label": "准备上下文",
            },
            {
                "id": "team_recruit",
                "phase": "team_kernel",
                "task": "recruit_members",
                "subagent_type": "leader",
                "label": "组建团队",
            },
            {
                "id": "team_dispatch",
                "phase": "team_kernel",
                "task": "dispatch_invocations",
                "subagent_type": "team",
                "label": "成员执行",
            },
            {
                "id": "team_quality_gate",
                "phase": "team_kernel",
                "task": "quality_gate",
                "subagent_type": "quality_gate",
                "label": "质量闭环",
            },
            {
                "id": "team_finish",
                "phase": "team_kernel",
                "task": "finish",
                "subagent_type": "leader",
                "label": "整理结果",
            },
        ]
        edges = [
            {"from": "team_prepare", "to": "team_recruit"},
            {"from": "team_recruit", "to": "team_dispatch"},
            {"from": "team_dispatch", "to": "team_quality_gate"},
            {"from": "team_quality_gate", "to": "team_finish"},
        ]
        return {"mode": "team_kernel", "nodes": nodes, "edges": edges}

    def _distribute_brief(
        self,
        brief: TaskBrief,
        cap: Any,
        *,
        workspace_data: dict[str, Any] | None = None,
    ) -> dict:
        """V1: every task receives the full brief.brief dict as inputs."""
        workspace_data = workspace_data or {}
        library_context = workspace_data.get("library_context")
        workspace_manuscript_context = workspace_data.get("manuscript_context")
        result: dict[str, dict] = {}
        for phase in cap.graph_template["phases"]:
            for task in phase["tasks"]:
                task_inputs = dict(brief.brief)
                nested_brief = task_inputs.get("brief")
                if isinstance(nested_brief, Mapping):
                    task_inputs = {
                        **dict(nested_brief),
                        **{key: value for key, value in task_inputs.items() if key != "brief"},
                    }
                task_inputs.setdefault("raw_message", brief.raw_message)
                task_inputs.setdefault("workspace_id", brief.workspace_id)
                if brief.user_id:
                    task_inputs.setdefault("user_id", brief.user_id)
                task_inputs.setdefault("capability_id", brief.capability_id)
                if brief.manuscript_context:
                    task_inputs["manuscript_context"] = brief.manuscript_context
                elif isinstance(workspace_manuscript_context, dict):
                    task_inputs["manuscript_context"] = workspace_manuscript_context
                if isinstance(library_context, dict) and library_context.get("citable_sources"):
                    task_inputs["library_context"] = library_context
                    task_inputs["citation_context"] = library_context
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

    def _collect_outputs(
        self,
        state: dict,
        cap: Any,
        *,
        brief: TaskBrief,
    ) -> list[ResultOutput]:
        graph_template = cap.graph_template if hasattr(cap, "graph_template") else {}
        node_results = state.get("node_results", {})
        if not graph_template or not node_results:
            outputs: list[ResultOutput] = []
        else:
            outputs = OutputMappingResolver().resolve(graph_template, node_results)
        outputs.extend(self._collect_policy_memory_outputs(cap, brief, outputs))
        return outputs

    def _collect_policy_memory_outputs(
        self,
        cap: Any,
        brief: TaskBrief,
        existing_outputs: list[ResultOutput],
    ) -> list[ResultOutput]:
        if any(output.kind == "memory_fact" for output in existing_outputs):
            return []
        policy = self._capability_policy(cap).get("review_policy", {})
        targets = policy.get("default_targets") if isinstance(policy, dict) else []
        if "room_memory_candidate" not in set(targets or []):
            return []

        facts = _memory_facts_from_brief(brief)
        return [
            MemoryFactOutput(
                id=f"policy-memory-{index}",
                kind="memory_fact",
                preview=fact.content[:80],
                default_checked=True,
                data=fact,
            )
            for index, fact in enumerate(facts)
        ]

    async def _stage_prism_review_items(
        self,
        state: dict,
        cap: Any,
        *,
        brief: TaskBrief,
        execution_id: str,
    ) -> None:
        graph_template = cap.graph_template if hasattr(cap, "graph_template") else {}
        node_results = state.get("node_results", {})
        if not graph_template or not isinstance(node_results, dict):
            return

        manuscript_context = brief.manuscript_context
        if not isinstance(manuscript_context, dict):
            return
        latex_project_id = str(manuscript_context.get("latex_project_id") or "").strip()
        if not latex_project_id:
            return

        from src.dataservice_client.contracts.prism_review import (
            PrismFileChangeUpsertPayload,
        )
        from src.dataservice_client.provider import dataservice_client

        commands: list[tuple[PrismFileChangeUpsertPayload, list[str]]] = []
        default_path = str(manuscript_context.get("main_file") or "main.tex").strip() or "main.tex"
        workspace_data = state.get("workspace_data") if isinstance(state, dict) else {}
        library_context = (
            workspace_data.get("library_context")
            if isinstance(workspace_data, dict)
            else None
        )
        citation_policy = self._capability_policy(cap).get("citation_policy", {})
        if not isinstance(citation_policy, dict):
            citation_policy = {}
        require_bibliography = (
            isinstance(library_context, dict)
            and bool(library_context.get("citation_keys"))
        )
        allowed_citation_keys = self._library_citation_keys(library_context)
        block_missing = citation_policy.get("missing_key_behavior") == "block_prism_stage"

        for phase in graph_template.get("phases", []):
            for task in phase.get("tasks", []):
                task_name = str(task.get("name") or "").strip()
                if not task_name:
                    continue
                node_result = node_results.get(task_name)
                if not isinstance(node_result, dict):
                    continue
                output = node_result.get("output")
                if not isinstance(output, dict):
                    continue
                for decl in task.get("outputs", []):
                    if not isinstance(decl, dict) or decl.get("kind") != "prism_file_change":
                        continue
                    command = self._build_prism_file_change_command(
                        decl,
                        output,
                        workspace_id=brief.workspace_id,
                        latex_project_id=latex_project_id,
                        task_name=task_name,
                        execution_id=execution_id,
                        default_path=default_path,
                        require_bibliography=require_bibliography,
                    )
                    if command is not None:
                        cited_keys = extract_citation_keys_from_text(command.pending_content)
                        missing_keys = [
                            key for key in cited_keys
                            if key not in allowed_citation_keys
                        ]
                        if (
                            command.path.endswith(".tex")
                            and citation_policy.get("source_scope") == "workspace_library"
                            and block_missing
                            and missing_keys
                        ):
                            logger.warning(
                                "Blocked Prism staging for %s because citations are missing from Library: %s",
                                command.path,
                                ", ".join(missing_keys),
                            )
                            continue
                        commands.append((command, cited_keys))

        if not commands:
            return

        try:
            async with dataservice_client() as client:
                for command, cited_keys in commands:
                    review_item = await client.upsert_pending_prism_file_change(command)
                    await self._record_prism_file_citation_usage(
                        client,
                        command=command,
                        cited_keys=cited_keys,
                        allowed_citation_keys=allowed_citation_keys,
                        review_item_id=str(getattr(review_item, "id", "") or "") or None,
                        citation_policy=citation_policy,
                    )
        except Exception:
            logger.warning("Failed to stage Prism review items", exc_info=True)

    async def _stage_sandbox_artifact_review_items(
        self,
        state: dict,
        *,
        brief: TaskBrief,
        execution_id: str,
    ) -> None:
        """Register sandbox-generated artifact candidates as review items."""

        candidates = collect_sandbox_artifact_candidates(state.get("node_results", {}))
        if not candidates:
            return

        from src.dataservice_client.provider import dataservice_client

        try:
            async with dataservice_client() as client:
                for candidate in candidates:
                    asset = await client.register_asset(
                        workspace_asset_payload_for_candidate(
                            workspace_id=brief.workspace_id,
                            execution_id=execution_id,
                            candidate=candidate,
                        )
                    )
                    await client.register_sandbox_artifact(
                        sandbox_artifact_payload_for_candidate(
                            workspace_id=brief.workspace_id,
                            execution_id=execution_id,
                            workspace_asset_id=str(asset.id),
                            candidate=candidate,
                        )
                    )
        except Exception:
            logger.warning("Failed to stage sandbox artifact review items", exc_info=True)

    @staticmethod
    def _library_citation_keys(library_context: Any) -> set[str]:
        if not isinstance(library_context, dict):
            return set()
        return {
            str(key).strip()
            for key in list(library_context.get("citation_keys") or [])
            if str(key).strip()
        }

    async def _record_prism_file_citation_usage(
        self,
        client: Any,
        *,
        command: Any,
        cited_keys: list[str],
        allowed_citation_keys: set[str],
        review_item_id: str | None,
        citation_policy: dict[str, Any],
    ) -> None:
        if not citation_policy.get("record_usage", True):
            return
        citation_keys = [
            key for key in cited_keys
            if not allowed_citation_keys or key in allowed_citation_keys
        ]
        if not citation_keys:
            return
        recorder = getattr(client, "record_source_citation_usage", None)
        if not callable(recorder):
            recorder = getattr(client, "record_citation_usage", None)
        if not callable(recorder):
            return
        if citation_policy.get("source_scope") == "workspace_library":
            citation_keys = [key for key in citation_keys if key in allowed_citation_keys]
        if not citation_keys:
            return
        try:
            await recorder(
                SourceCitationUsageCreatePayload(
                    workspace_id=command.workspace_id,
                    citation_keys=citation_keys,
                    execution_id=command.source_execution_id,
                    task_id=command.source_task_id,
                    latex_project_id=command.latex_project_id,
                    target_domain="prism",
                    target_kind="prism_file",
                    target_id=review_item_id,
                    target_ref_json={
                        "logical_key": command.logical_key,
                        "path": command.path,
                    },
                    generated_text=command.pending_content[:4000],
                    usage_type="manuscript_citation",
                    accepted_status="pending",
                )
            )
        except Exception:
            logger.warning(
                "Failed to record Prism file citation usage for %s",
                command.path,
                exc_info=True,
            )

    async def _sync_prism_bibliography(
        self,
        *,
        brief: TaskBrief,
        state: dict,
    ) -> None:
        """Keep workspace Library BibTeX materialized in Prism after manuscript runs."""
        workspace_data = state.get("workspace_data") if isinstance(state, dict) else {}
        library_context = (
            workspace_data.get("library_context")
            if isinstance(workspace_data, dict)
            else None
        )
        if not isinstance(library_context, dict) or not library_context.get("citation_keys"):
            return
        try:
            from src.services.references import SourceBibliographyService

            await SourceBibliographyService().sync_prism(
                workspace_id=brief.workspace_id,
            )
        except Exception:
            logger.warning("Failed to sync Prism BibTeX from Library", exc_info=True)

    @staticmethod
    def _build_prism_file_change_command(
        decl: dict[str, Any],
        output: dict[str, Any],
        *,
        workspace_id: str,
        latex_project_id: str,
        task_name: str,
        execution_id: str,
        default_path: str,
        require_bibliography: bool = False,
    ) -> Any | None:
        return build_prism_file_change_command(
            decl,
            output,
            workspace_id=workspace_id,
            latex_project_id=latex_project_id,
            task_name=task_name,
            execution_id=execution_id,
            default_path=default_path,
            require_bibliography=require_bibliography,
        )

    def _build_narrative(self, cap: Any, state: dict) -> str:
        n_nodes = len(state.get("node_results", {}))
        return f"完成 {cap.display_name}，共执行 {n_nodes} 个节点。"

    def _aggregate_token_usage(
        self,
        state: dict,
        *,
        collected_token_usage: TokenUsage | None = None,
    ) -> dict[str, int] | None:
        usage: dict[str, int] = {"input": 0, "output": 0}
        for node_result in state.get("node_results", {}).values():
            tu = node_result.get("token_usage") or {}
            usage["input"] += tu.get("input", 0)
            usage["output"] += tu.get("output", 0)
        if collected_token_usage is not None:
            usage["input"] += collected_token_usage.input_tokens
            usage["output"] += collected_token_usage.output_tokens
        return usage if (usage["input"] or usage["output"]) else None


# ---------------------------------------------------------------------------
# Default callables
# ---------------------------------------------------------------------------


def _preview_output(output_data: Any) -> str | None:
    """Return a compact, UI-safe output preview for execution.node events."""
    if output_data is None:
        return None
    if isinstance(output_data, dict):
        for key in ("summary", "message", "report_markdown", "stdout", "text"):
            value = output_data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:500]
    if isinstance(output_data, str):
        return output_data.strip()[:500]
    try:
        return json.dumps(output_data, ensure_ascii=False, sort_keys=True)[:500]
    except Exception:
        return str(output_data)[:500]


async def _noop_publish(*args: Any, **kwargs: Any) -> None:
    """No-op event publisher used when no publish_event is provided."""


async def _stub_get_ws_type(workspace_id: str) -> str:
    """Stub workspace-type resolver that always returns 'thesis'."""
    return "thesis"


async def _noop_record_node(*args: Any, **kwargs: Any) -> None:
    """No-op node-event recorder used when no record_node_event is provided."""
