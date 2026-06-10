"""Tool registry for the Wenjin-native agent harness."""

from __future__ import annotations

from collections.abc import Iterable

from .contracts import HarnessToolSpec


class UnknownHarnessToolError(KeyError):
    """Raised when a declared harness tool cannot be resolved."""


class HarnessToolRegistry:
    """Deterministic name-to-spec registry for harness tools."""

    def __init__(self, specs: Iterable[HarnessToolSpec] = ()) -> None:
        self._specs: dict[str, HarnessToolSpec] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: HarnessToolSpec) -> None:
        name = spec.name.strip()
        if not name:
            raise ValueError("harness tool name cannot be empty")
        if name in self._specs:
            raise ValueError(f"duplicate harness tool: {name}")
        self._validate_spec_name(spec)
        self._specs[name] = spec

    def get(self, name: str) -> HarnessToolSpec:
        key = str(name).strip()
        try:
            return self._specs[key]
        except KeyError as exc:
            raise UnknownHarnessToolError(f"unknown harness tool: {key}") from exc

    def resolve(self, names: Iterable[str]) -> list[HarnessToolSpec]:
        return [self.get(name) for name in names]

    def names(self) -> tuple[str, ...]:
        return tuple(self._specs)

    @staticmethod
    def _validate_spec_name(spec: HarnessToolSpec) -> None:
        if "." not in spec.name:
            raise ValueError(f"harness tool name must be namespaced: {spec.name}")
        namespace = spec.name.split(".", 1)[0]
        if namespace != spec.namespace:
            raise ValueError(
                "harness tool namespace mismatch: "
                f"{spec.name} declares namespace={spec.namespace}"
            )
