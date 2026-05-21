"""Workspace summary aggregation service for cockpit surfaces."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.provider import dataservice_client
from src.services.dashboard_service import DashboardService
from src.services.execution_service import ExecutionService
from src.services.workspace_activity_service import WorkspaceActivityService

_WORKSPACE_LABELS = {
    "thesis": "学位论文",
    "sci": "学术论文",
    "proposal": "研究计划",
    "software_copyright": "软著申请",
    "patent": "专利申请",
}

_STATUS_LABELS = {
    "not_started": "未开始",
    "in_progress": "进行中",
    "completed": "已完成",
    "failed": "失败",
}

_MIN_LITERATURE_TOTAL = 5
_MIN_LITERATURE_CORE = 3


class WorkspaceSummaryService:
    """Build a concise task summary for workspace cockpit surfaces."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        dashboard_service: DashboardService | None = None,
        activity_service: WorkspaceActivityService | None = None,
        execution_service: ExecutionService | None = None,
        capability_model: type | None = None,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self.db = db
        self._dashboard_service = dashboard_service or DashboardService(db)
        self._activity_service = activity_service or WorkspaceActivityService(db)
        self._execution_service = execution_service
        self._capability_model = capability_model
        self._dataservice = dataservice

    async def _list_catalog_capabilities(
        self,
        *,
        workspace_type: str,
        enabled_only: bool,
    ) -> list[Any]:
        if self._dataservice is not None:
            return await self._dataservice.list_catalog_capabilities(
                workspace_type=workspace_type,
                enabled_only=enabled_only,
            )
        async with dataservice_client() as client:
            return await client.list_catalog_capabilities(
                workspace_type=workspace_type,
                enabled_only=enabled_only,
            )

    async def get_summary(
        self,
        workspace_id: str,
        *,
        workspace_type: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Aggregate a workspace summary payload for the dashboard."""
        dashboard = await self._dashboard_service.get_dashboard(
            workspace_id,
            workspace_type=workspace_type,
        )
        executions = await self._list_executions(
            workspace_id,
            user_id=user_id,
        )
        modules = await self._normalize_modules(
            workspace_type,
            dashboard.get("modules") if isinstance(dashboard, dict) else [],
            executions,
        )
        progress = self._build_progress(modules)
        current_phase = self._build_current_phase(modules, executions)
        next_step = self._build_next_step(modules, executions)
        recommended_actions = self._build_recommended_actions(modules, executions)
        risk_items = self._build_risk_items(workspace_type, modules, executions)
        recent_activity = await self._build_recent_activity(
            workspace_id,
            user_id=user_id,
        )

        return {
            "workspace_id": workspace_id,
            "workspace_type": workspace_type,
            "headline": self._build_headline(
                workspace_type,
                current_phase=current_phase,
                next_step=next_step,
                progress=progress,
            ),
            "progress": progress,
            "current_phase": current_phase,
            "next_step": next_step,
            "recommended_actions": recommended_actions,
            "risk_items": risk_items,
            "recent_activity": recent_activity,
        }

    async def _normalize_modules(
        self,
        workspace_type: str,
        raw_modules: list[dict[str, Any]] | Any,
        executions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        module_by_id: dict[str, dict[str, Any]] = {}
        if isinstance(raw_modules, list):
            for module in raw_modules:
                if not isinstance(module, dict):
                    continue
                module_id = str(module.get("id") or "").strip()
                if not module_id:
                    continue
                summary = module.get("summary")
                module_by_id[module_id] = {
                    "id": module_id,
                    "status": str(module.get("status") or "not_started"),
                    "summary": summary if isinstance(summary, dict) else {},
                }

        latest_execution_by_feature: dict[str, dict[str, Any]] = {}
        for execution in executions:
            feature_id = str(execution.get("feature_id") or "").strip()
            if not feature_id or feature_id in latest_execution_by_feature:
                continue
            latest_execution_by_feature[feature_id] = execution

        if self._capability_model is not None:
            capability_model = self._capability_model
            result = await self.db.execute(
                select(capability_model)
                .where(capability_model.workspace_type == workspace_type)
                .where(capability_model.enabled == True)  # noqa: E712
            )
            raw_capabilities = result.scalars().all()
        else:
            raw_capabilities = await self._list_catalog_capabilities(
                workspace_type=workspace_type,
                enabled_only=True,
            )
        capabilities = sorted(raw_capabilities, key=lambda c: ((c.ui_meta or {}).get("order", 0), c.id))

        normalized: list[dict[str, Any]] = []
        for cap in capabilities:
            if (cap.dashboard_meta or {}).get("hidden") is True:
                continue
            module = module_by_id.get(cap.id, {})
            latest_execution: dict[str, Any] | None = latest_execution_by_feature.get(cap.id)
            if latest_execution:
                module_status = self._module_status_from_execution(latest_execution)
                module_summary = {
                    **(cast(dict[str, Any], module.get("summary")) if isinstance(module.get("summary"), dict) else {}),
                    "execution_id": latest_execution.get("id"),
                    "result_summary": latest_execution.get("result_summary"),
                    "current_phase": self._execution_current_phase(latest_execution),
                }
            else:
                module_status = str(module.get("status") or "not_started")
                module_summary = module.get("summary") or {}
            normalized.append(
                {
                    "id": cap.id,
                    "title": cap.display_name,
                    "description": cap.description,
                    "status": module_status,
                    "summary": module_summary,
                }
            )
        return normalized

    async def _list_executions(
        self,
        workspace_id: str,
        *,
        user_id: str | None,
    ) -> list[dict[str, Any]]:
        if not user_id:
            return []
        service = self._execution_service
        if service is None:
            if not isinstance(self.db, AsyncSession):
                return []
            service = ExecutionService(self.db)
        try:
            executions = await service.list_executions(
                workspace_id=workspace_id,
                user_id=user_id,
                limit=20,
            )
        except Exception:
            return []

        serialized: list[dict[str, Any]] = []
        for execution in executions:
            serialized.append(
                {
                    "id": execution.id,
                    "feature_id": execution.feature_id,
                    "status": execution.status,
                    "result_summary": execution.result_summary,
                    "next_actions": list(execution.next_actions or []),
                    "graph_structure": execution.graph_structure,
                    "node_states": execution.node_states,
                    "updated_at": execution.updated_at,
                }
            )
        serialized.sort(
            key=lambda item: str(item.get("updated_at") or ""),
            reverse=True,
        )
        return serialized

    @staticmethod
    def _module_status_from_execution(execution: dict[str, Any]) -> str:
        status = str(execution.get("status") or "").strip().lower()
        if status in {"running", "pending", "awaiting_user_input"}:
            return "in_progress"
        if status in {"completed", "failed_partial"}:
            return "completed"
        if status in {"failed", "cancelled"}:
            return "failed"
        return "not_started"

    @staticmethod
    def _execution_current_phase(execution: dict[str, Any]) -> str | None:
        graph_structure = execution.get("graph_structure")
        node_states = execution.get("node_states")
        if not isinstance(graph_structure, dict) or not isinstance(node_states, dict):
            return None
        nodes = graph_structure.get("nodes")
        if not isinstance(nodes, list):
            return None
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id") or "").strip()
            if not node_id:
                continue
            node_state = node_states.get(node_id)
            if isinstance(node_state, dict) and node_state.get("status") == "running":
                phase = node.get("phase")
                if isinstance(phase, str) and phase.strip():
                    return phase.strip()
        return None

    def _build_progress(self, modules: list[dict[str, Any]]) -> dict[str, int]:
        total = len(modules)
        completed = sum(1 for module in modules if module["status"] == "completed")
        in_progress = sum(1 for module in modules if module["status"] == "in_progress")
        failed = sum(1 for module in modules if module["status"] == "failed")
        if total == 0:
            percent = 0
        else:
            percent = round(((completed + in_progress * 0.5) / total) * 100)
        return {
            "completed": completed,
            "in_progress": in_progress,
            "failed": failed,
            "total": total,
            "percent": percent,
        }

    def _build_current_phase(
        self,
        modules: list[dict[str, Any]],
        executions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        active_execution = next(
            (
                execution
                for execution in executions
                if str(execution.get("status") or "") in {"running", "pending", "awaiting_user_input"}
            ),
            None,
        )
        if active_execution:
            feature_id = str(active_execution.get("feature_id") or "").strip() or None
            module = next(
                (item for item in modules if item["id"] == feature_id),
                None,
            )
            current_phase = self._execution_current_phase(active_execution)
            return {
                "feature_id": feature_id,
                "title": (
                    str(current_phase or "").strip()
                    or (module["title"] if module else "执行中")
                ),
                "status": "in_progress",
                "description": (
                    str(active_execution.get("result_summary") or "").strip()
                    or "该执行会话正在推进中。"
                ),
            }

        failed = self._find_first(modules, "failed")
        if failed:
            return {
                "feature_id": failed["id"],
                "title": failed["title"],
                "status": failed["status"],
                "description": "该模块上次执行失败，建议优先检查输入并重试。",
            }

        active = self._find_first(modules, "in_progress")
        if active:
            return {
                "feature_id": active["id"],
                "title": active["title"],
                "status": active["status"],
                "description": "该模块正在推进中，适合继续追问、补充材料或等待结果。",
            }

        next_pending = self._find_first(modules, "not_started")
        if next_pending:
            return {
                "feature_id": next_pending["id"],
                "title": next_pending["title"],
                "status": next_pending["status"],
                "description": "这是当前任务链上最自然的下一步。",
            }

        return {
            "feature_id": None,
            "title": "任务收尾",
            "status": "completed",
            "description": "核心模块已完成，可继续导出、评审或开启新的任务分支。",
        }

    def _build_next_step(
        self,
        modules: list[dict[str, Any]],
        executions: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        active_execution = next(
            (
                execution
                for execution in executions
                if str(execution.get("status") or "") in {"running", "pending", "awaiting_user_input"}
            ),
            None,
        )
        if active_execution:
            next_actions = active_execution.get("next_actions")
            if isinstance(next_actions, list) and next_actions:
                first_action = next_actions[0]
                if isinstance(first_action, dict):
                    feature_id = str(first_action.get("feature_id") or active_execution.get("feature_id") or "")
                    module = next((item for item in modules if item["id"] == feature_id), None)
                    return {
                        "feature_id": feature_id,
                        "title": str(first_action.get("label") or (module["title"] if module else feature_id)),
                        "description": module.get("description") if module else None,
                        "reason": str(active_execution.get("result_summary") or "当前执行建议优先跟进下一步。"),
                        "status": "in_progress",
                        "status_label": _STATUS_LABELS.get("in_progress"),
                    }

        failed = self._find_first(modules, "failed")
        if failed:
            return self._action_from_module(
                failed,
                "上一个关键模块失败，建议先重试或修正输入。",
            )

        active = self._find_first(modules, "in_progress")
        if active:
            return self._action_from_module(
                active,
                "当前已有任务在运行，建议优先跟进其结果。",
            )

        next_pending = self._find_first(modules, "not_started")
        if next_pending:
            return self._action_from_module(
                next_pending,
                "这是当前建议优先推进的模块。",
            )

        return None

    def _build_recommended_actions(
        self,
        modules: list[dict[str, Any]],
        executions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []

        active_execution = next(
            (
                execution
                for execution in executions
                if str(execution.get("status") or "") in {"running", "pending", "awaiting_user_input"}
            ),
            None,
        )
        if active_execution:
            next_actions = active_execution.get("next_actions")
            if isinstance(next_actions, list):
                for item in next_actions:
                    if not isinstance(item, dict):
                        continue
                    feature_id = str(item.get("feature_id") or active_execution.get("feature_id") or "")
                    module = next((module for module in modules if module["id"] == feature_id), None)
                    if not feature_id:
                        continue
                    actions.append(
                        {
                            "feature_id": feature_id,
                            "title": str(item.get("label") or (module["title"] if module else feature_id)),
                            "description": module.get("description") if module else None,
                            "reason": str(active_execution.get("result_summary") or "当前执行建议优先跟进下一步。"),
                            "status": "in_progress",
                            "status_label": _STATUS_LABELS.get("in_progress"),
                        }
                    )

        failed = self._find_first(modules, "failed")
        if failed:
            actions.append(
                self._action_from_module(
                    failed,
                    "先处理失败模块，避免后续任务链断开。",
                )
            )

        active = self._find_first(modules, "in_progress")
        if active:
            actions.append(
                self._action_from_module(
                    active,
                    "已有任务在执行，继续跟进最划算。",
                )
            )

        for module in modules:
            if module["status"] != "not_started":
                continue
            actions.append(
                self._action_from_module(
                    module,
                    "主链推荐下一步。",
                )
            )

        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for action in actions:
            feature_id = str(action.get("feature_id") or "")
            if not feature_id or feature_id in seen:
                continue
            deduped.append(action)
            seen.add(feature_id)
            if len(deduped) >= 4:
                break

        if deduped:
            return deduped

        for module in modules[:3]:
            deduped.append(
                self._action_from_module(
                    module,
                    "主链模块已完成，可按需继续查看或复用结果。",
                )
            )
        return deduped

    def _build_risk_items(
        self,
        workspace_type: str,
        modules: list[dict[str, Any]],
        executions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        risks: list[dict[str, Any]] = []
        module_by_id = {module["id"]: module for module in modules if module.get("id")}

        for execution in executions:
            if str(execution.get("status") or "") != "awaiting_user_input":
                continue
            feature_id = str(execution.get("feature_id") or "").strip()
            module = module_by_id.get(feature_id)
            risks.append(
                {
                    "id": f"advisory:{feature_id or execution.get('id')}",
                    "title": (
                        str(execution.get("result_summary") or "").strip()
                        or f"{module['title'] if module else feature_id} 当前需要补充输入后再执行。"
                    ),
                    "tone": "warning",
                }
            )

        for module in modules:
            if module["status"] != "failed":
                continue
            risks.append(
                {
                    "id": f"failed:{module['id']}",
                    "title": f"{module['title']} 执行失败，建议优先排查。",
                    "tone": "danger",
                }
            )

        literature_module = None
        if workspace_type == "thesis":
            literature_module = next(
                (module for module in modules if module["id"] == "literature_management"),
                None,
            )
        elif workspace_type == "sci":
            literature_module = next(
                (module for module in modules if module["id"] == "literature_search"),
                None,
            )

        if literature_module:
            summary = literature_module.get("summary") or {}
            total = self._safe_int(summary.get("total") or summary.get("results_count"))
            core = self._safe_int(summary.get("core"))
            if total < _MIN_LITERATURE_TOTAL:
                risks.append(
                    {
                        "id": f"literature-total:{literature_module['id']}",
                        "title": f"当前文献储备偏少（{total}），建议先补充检索与筛选。",
                        "tone": "warning",
                    }
                )
            elif workspace_type == "thesis" and core < _MIN_LITERATURE_CORE:
                risks.append(
                    {
                        "id": "literature-core:thesis",
                        "title": f"核心文献仅 {core} 篇，后续写作支撑可能不足。",
                        "tone": "warning",
                    }
                )

        if workspace_type == "proposal":
            background_research = module_by_id.get("background_research")
            experiment_design = module_by_id.get("experiment_design")
            proposal_outline = module_by_id.get("proposal_outline")
            if (
                background_research
                and background_research["status"] == "not_started"
                and proposal_outline
                and proposal_outline["status"] in {"in_progress", "completed"}
            ):
                risks.append(
                    {
                        "id": "proposal:background_research",
                        "title": "背景调研尚未形成，立项依据与问题定义可能偏弱。",
                        "tone": "warning",
                    }
                )
            if (
                experiment_design
                and experiment_design["status"] == "not_started"
                and (
                    (background_research and background_research["status"] == "completed")
                    or (proposal_outline and proposal_outline["status"] == "completed")
                )
            ):
                risks.append(
                    {
                        "id": "proposal:experiment_design",
                        "title": "实验设计尚未产出，研究方案与评审说服力可能不足。",
                        "tone": "warning",
                    }
                )

        if workspace_type == "patent":
            patent_outline = module_by_id.get("patent_outline")
            prior_art_search = module_by_id.get("prior_art_search")
            if (
                patent_outline
                and patent_outline["status"] == "completed"
                and prior_art_search
                and prior_art_search["status"] == "not_started"
            ):
                risks.append(
                    {
                        "id": "patent:prior_art_search",
                        "title": "现有技术检索尚未完成，新颖性与授权风险仍未显式收敛。",
                        "tone": "warning",
                    }
                )

        if workspace_type == "software_copyright":
            copyright_materials = module_by_id.get("copyright_materials")
            technical_description = module_by_id.get("technical_description")
            if (
                copyright_materials
                and copyright_materials["status"] == "completed"
                and technical_description
                and technical_description["status"] == "not_started"
            ):
                risks.append(
                    {
                        "id": "software_copyright:technical_description",
                        "title": "技术说明书尚未产出，当前软著材料包仍不完整。",
                        "tone": "warning",
                    }
                )

        return risks[:3]

    async def _build_recent_activity(
        self,
        workspace_id: str,
        *,
        user_id: str | None,
    ) -> dict[str, Any] | None:
        activity = await self._activity_service.get_activity(
            workspace_id,
            user_id=user_id,
            limit=1,
        )
        items = activity.get("items") if isinstance(activity, dict) else []
        if not isinstance(items, list) or not items:
            return None

        item = items[0] if isinstance(items[0], dict) else {}
        occurred_at = item.get("occurred_at")
        return {
            "title": str(item.get("title") or "最近活动"),
            "summary": item.get("summary"),
            "kind": str(item.get("kind") or ""),
            "occurred_at": occurred_at.isoformat() if isinstance(occurred_at, datetime) else str(occurred_at or ""),
        }

    def _build_headline(
        self,
        workspace_type: str,
        *,
        current_phase: dict[str, Any],
        next_step: dict[str, Any] | None,
        progress: dict[str, int],
    ) -> str:
        workspace_label = _WORKSPACE_LABELS.get(workspace_type, "当前任务")
        current_title = current_phase.get("title") or "当前阶段"

        if progress["total"] > 0 and progress["completed"] >= progress["total"]:
            return f"{workspace_label}主链路已完成，可继续导出、评审或开启新的任务分支。"

        if current_phase.get("status") == "failed":
            return f"{workspace_label}当前阻塞在「{current_title}」，建议先修复该模块后再推进。"

        if current_phase.get("status") == "in_progress":
            return f"{workspace_label}正在推进「{current_title}」，可以在线程中继续补充上下文。"

        if next_step and next_step.get("title"):
            return f"{workspace_label}建议优先推进「{next_step['title']}」，保持任务链连续。"

        return f"{workspace_label}已进入稳定推进阶段，可继续通过线程驱动下一步模块。"

    def _action_from_module(
        self,
        module: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        return {
            "feature_id": module["id"],
            "title": module["title"],
            "description": module.get("description"),
            "reason": reason,
            "status": module["status"],
            "status_label": _STATUS_LABELS.get(module["status"], module["status"]),
        }

    def _find_first(
        self,
        modules: list[dict[str, Any]],
        status: str,
    ) -> dict[str, Any] | None:
        for module in modules:
            if module["status"] == status:
                return module
        return None

    @staticmethod
    def _safe_int(value: Any) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(float(value))
            except ValueError:
                return 0
        return 0
