"""The single runtime source of tool descriptors and handlers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from src.tools.orchestrator.contracts import (
    SideEffectClass,
    ToolCallerKind,
    ToolDescriptor,
    ToolExecutionLimit,
    ToolHandlerResult,
    ToolInvocationContext,
    ToolKind,
    ToolOperation,
)
from src.tools.orchestrator.errors import UnknownToolError

ToolHandler = Callable[[ToolOperation, BaseModel], Awaitable[ToolHandlerResult]]
ToolSemanticIdentityBuilder = Callable[
    [BaseModel, ToolInvocationContext],
    Awaitable[BaseModel | dict[str, Any]],
]


@dataclass(frozen=True)
class ToolRegistration:
    descriptor: ToolDescriptor
    input_model: type[BaseModel]
    handler: ToolHandler
    semantic_identity_builder: ToolSemanticIdentityBuilder | None = None


class ToolCatalog:
    """Explicitly assembled catalog; no import-time registration side effects."""

    def __init__(self, registrations: Iterable[ToolRegistration] = ()) -> None:
        self._registrations: dict[str, ToolRegistration] = {}
        self._frozen = False
        for registration in registrations:
            self.register(registration)

    def register(self, registration: ToolRegistration) -> None:
        if self._frozen:
            raise RuntimeError("ToolCatalog is frozen")
        tool_id = registration.descriptor.tool_id
        if tool_id in self._registrations:
            raise ValueError(f"duplicate tool descriptor: {tool_id}")
        expected_hash = schema_hash(registration.input_model.model_json_schema())
        if registration.descriptor.schema_hash != expected_hash:
            raise ValueError(f"schema hash mismatch for tool: {tool_id}")
        self._registrations[tool_id] = registration

    def freeze(self) -> ToolCatalog:
        if not self._registrations:
            raise ValueError("ToolCatalog cannot be frozen while empty")
        self._frozen = True
        return self

    @property
    def frozen(self) -> bool:
        return self._frozen

    def require(self, tool_id: str) -> ToolRegistration:
        registration = self._registrations.get(str(tool_id or "").strip())
        if registration is None:
            raise UnknownToolError(f"unknown tool: {tool_id}")
        return registration

    def descriptors(self) -> tuple[ToolDescriptor, ...]:
        return tuple(registration.descriptor for _tool_id, registration in sorted(self._registrations.items()))

    def descriptor_snapshot_hash(self) -> str:
        return schema_hash([descriptor.model_dump(mode="json") for descriptor in self.descriptors()])

    def execution_limits(
        self,
        tool_ids: Iterable[str],
    ) -> tuple[ToolExecutionLimit, ...]:
        if not self._frozen:
            raise RuntimeError("ToolCatalog must be frozen before execution limits are pinned")
        requested = tuple(tool_ids)
        if len(requested) != len(set(requested)):
            raise ValueError("tool execution limits require unique tool ids")
        limits: list[ToolExecutionLimit] = []
        for tool_id in requested:
            descriptor = self.require(tool_id).descriptor
            limits.append(
                ToolExecutionLimit(
                    tool_id=descriptor.tool_id,
                    descriptor_schema_hash=descriptor.schema_hash,
                    descriptor_hash=schema_hash(
                        descriptor.model_dump(mode="json")
                    ),
                    timeout_seconds=descriptor.timeout_seconds,
                    max_attempts=descriptor.max_attempts,
                )
            )
        return tuple(limits)


def build_tool_registration(
    *,
    tool_id: str,
    tool_version: str,
    kind: ToolKind,
    input_model: type[BaseModel],
    handler: ToolHandler,
    side_effect_class: SideEffectClass,
    allowed_callers: tuple[ToolCallerKind, ...],
    required_permissions: tuple[str, ...] = (),
    network_profile: str = "none",
    budget_class: str = "standard",
    timeout_seconds: float,
    max_attempts: int,
    payload_limit_bytes: int = 262_144,
    provenance_requirements: tuple[str, ...] = (),
    semantic_identity_builder: ToolSemanticIdentityBuilder | None = None,
) -> ToolRegistration:
    descriptor = ToolDescriptor(
        tool_id=tool_id,
        tool_version=tool_version,
        schema_hash=schema_hash(input_model.model_json_schema()),
        kind=kind,
        input_schema_ref=_type_ref(input_model),
        output_schema_ref=_type_ref(ToolHandlerResult),
        side_effect_class=side_effect_class,
        allowed_callers=allowed_callers,
        required_permissions=required_permissions,
        network_profile=network_profile,
        budget_class=budget_class,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        payload_limit_bytes=payload_limit_bytes,
        provenance_requirements=provenance_requirements,
    )
    return ToolRegistration(
        descriptor=descriptor,
        input_model=input_model,
        handler=handler,
        semantic_identity_builder=semantic_identity_builder,
    )


def schema_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _type_ref(model: type[BaseModel]) -> str:
    return f"{model.__module__}:{model.__qualname__}"


__all__ = [
    "ToolCatalog",
    "ToolHandler",
    "ToolRegistration",
    "ToolSemanticIdentityBuilder",
    "build_tool_registration",
    "schema_hash",
]
