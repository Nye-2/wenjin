"""Capability resolver — loads capabilities with caching and cache invalidation."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from sqlalchemy import select

if TYPE_CHECKING:
    from .event_bus import EventBus

logger = logging.getLogger(__name__)

# Allowed template variables in prompt_template
ALLOWED_VARS = {"topic", "language", "time_range", "decisions", "raw_message", "workspace"}

_VALID_OUTPUT_KINDS = {"library_item", "document", "memory_fact", "decision", "task"}

_REQUIRED_OUTPUT_FIELDS = {
    "library_item": {"title", "authors"},
    "document": {"name", "mime_type", "storage_path", "size_bytes"},
    "memory_fact": {"content"},
    "decision": {"key", "value"},
    "task": {"title"},
}

_VALID_FIELDS_BY_KIND = {
    "library_item": {"title", "authors", "year", "doi", "url", "abstract", "metadata"},
    "document": {"name", "mime_type", "storage_path", "size_bytes", "doc_kind", "parent_id"},
    "memory_fact": {"content", "category", "confidence"},
    "decision": {"key", "value", "confidence"},
    "task": {"title", "description", "priority"},
}


class CapabilityNotFound(Exception):
    """Raised when a capability cannot be found by id + workspace_type."""

    def __init__(self, capability_id: str, workspace_type: str) -> None:
        self.capability_id = capability_id
        self.workspace_type = workspace_type
        super().__init__(
            f"Capability '{capability_id}' not found for workspace type '{workspace_type}'"
        )


class CapabilityResolver:
    """Resolves capabilities from DB with in-memory caching.

    Cache is invalidated via ``capability.invalidated`` events on the EventBus.

    Args:
        session_factory: Callable returning a new AsyncSession.
        event_bus: EventBus instance for cache invalidation.
        model: Optional test ORM model. Production reads through DataService catalog.
    """

    def __init__(self, session_factory, event_bus: EventBus, model=None) -> None:
        self.session_factory = session_factory
        self.event_bus = event_bus
        self._model = model
        self._cache: dict[tuple[str, str], object] = {}
        event_bus.subscribe("capability.invalidated", self._on_invalidate)

    async def resolve(self, capability_id: str, workspace_type: str):
        """Load a capability from cache or DB.

        Raises:
            CapabilityNotFound: If the capability does not exist or is disabled.
        """
        key = (capability_id, workspace_type)
        if key in self._cache:
            return self._cache[key]

        async with self.session_factory() as session:
            if self._model is None:
                from src.dataservice.catalog_api import CatalogDataService

                cap = await CatalogDataService(session, autocommit=False).get_capability(
                    capability_id=capability_id,
                    workspace_type=workspace_type,
                    enabled_only=True,
                )
                if cap is None:
                    raise CapabilityNotFound(capability_id, workspace_type)
                self._cache[key] = cap
                return cap

            result = await session.execute(
                select(self._model).where(
                    self._model.id == capability_id,
                    self._model.workspace_type == workspace_type,
                    self._model.enabled.is_(True),
                )
            )
            cap = result.scalar_one_or_none()

        if cap is None:
            raise CapabilityNotFound(capability_id, workspace_type)

        self._cache[key] = cap
        return cap

    async def list_for_workspace_type(self, workspace_type: str) -> list:
        """List all enabled capabilities for a workspace type."""
        async with self.session_factory() as session:
            if self._model is None:
                from src.dataservice.catalog_api import CatalogDataService

                return await CatalogDataService(session, autocommit=False).list_capabilities(
                    workspace_type=workspace_type,
                    enabled_only=True,
                )

            result = await session.execute(
                select(self._model).where(
                    self._model.workspace_type == workspace_type,
                    self._model.enabled.is_(True),
                )
            )
            return list(result.scalars().all())

    async def _on_invalidate(self, event: dict) -> None:
        """Handle cache invalidation from EventBus."""
        key = (event["id"], event["workspace_type"])
        self._cache.pop(key, None)
        logger.debug("Cache invalidated for %s", key)


def validate_capability(
    data: dict,
    subagent_registry: list[str] | None = None,
) -> list[str]:
    """Validate capability data. Returns list of error strings (empty = OK).

    Checks:
    1. graph_template.phases[*].depends_on references existing phase names
    2. graph_template.phases[*].tasks[*].subagent_type in subagent_registry (if provided)
    3. prompt_template / system_prompt template vars are in ALLOWED_VARS or brief_schema.properties

    Args:
        data: Capability data dict.
        subagent_registry: Optional list of known subagent types. If None, check 2 is skipped.
    """
    errors: list[str] = []

    graph = data.get("graph_template", {})
    phases = graph.get("phases", [])
    phase_names = {p.get("name") for p in phases if p.get("name")}

    for i, phase in enumerate(phases):
        phase_name = phase.get("name", f"phase[{i}]")
        for dep in phase.get("depends_on", []):
            if dep not in phase_names:
                errors.append(
                    f"Phase '{phase_name}' depends_on '{dep}' which does not exist"
                )

        if subagent_registry is not None:
            for j, task in enumerate(phase.get("tasks", [])):
                sa_type = task.get("subagent_type")
                if sa_type and sa_type not in subagent_registry:
                    errors.append(
                        f"Phase '{phase_name}' task[{j}] subagent_type "
                        f"'{sa_type}' not in registry"
                    )

                # Validate outputs declarations
                for k, out_decl in enumerate(task.get("outputs", [])):
                    out_kind = out_decl.get("kind", "")
                    if out_kind not in _VALID_OUTPUT_KINDS:
                        errors.append(
                            f"Phase '{phase_name}' task[{j}] outputs[{k}] "
                            f"has unknown output kind '{out_kind}'"
                        )
                        continue
                    required = _REQUIRED_OUTPUT_FIELDS.get(out_kind, set())
                    mapping_keys = set(out_decl.get("mapping", {}).keys())
                    missing = required - mapping_keys
                    if missing:
                        errors.append(
                            f"Phase '{phase_name}' task[{j}] outputs[{k}] "
                            f"kind '{out_kind}' missing required mapping fields: {sorted(missing)}"
                        )
                    iterate_on = out_decl.get("iterate_on", "")
                    if iterate_on and not iterate_on.startswith("output."):
                        errors.append(
                            f"Phase '{phase_name}' task[{j}] outputs[{k}] "
                            f"iterate_on must start with 'output.'"
                        )
                    valid_fields = _VALID_FIELDS_BY_KIND.get(out_kind, set())
                    task_name = task.get("name", f"task[{j}]")
                    for field_name in out_decl.get("mapping", {}):
                        if field_name not in valid_fields:
                            errors.append(
                                f"Unknown field '{field_name}' in {out_kind} output mapping for task '{task_name}'"
                            )

    # Collect allowed template variables from brief_schema.properties
    brief_schema = data.get("brief_schema", {})
    brief_properties = set(brief_schema.get("properties", {}).keys())
    all_allowed = ALLOWED_VARS | brief_properties

    # Check template vars in graph_template tasks' prompt_template
    for i, phase in enumerate(phases):
        phase_name = phase.get("name", f"phase[{i}]")
        for j, task in enumerate(phase.get("tasks", [])):
            prompt = task.get("prompt_template", "")
            for var in _extract_template_vars(prompt):
                if var not in all_allowed:
                    errors.append(
                        f"Phase '{phase_name}' task[{j}] prompt_template uses "
                        f"undefined template variable '{{{{{var}}}}}'"
                    )

    return errors


def _extract_template_vars(text: str) -> list[str]:
    """Extract template variable names from {{var}} patterns."""
    return re.findall(r"\{\{(\w+)\}\}", text)
