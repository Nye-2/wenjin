"""OpenTelemetry tracing setup placeholder.

V1 exposes `tracer` from `tracing` for use by ExecutionService and other
critical paths. Full OTEL exporter wiring is Phase 2+.
"""

import logging

logger = logging.getLogger(__name__)

# V1 stub: provides a no-op tracer that satisfies imports.
# Phase 2 will replace with real opentelemetry-sdk setup.


class _NoOpSpan:
    def __enter__(self) -> "_NoOpSpan":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def set_attribute(self, *args: object, **kwargs: object) -> None:
        pass

    def add_event(self, *args: object, **kwargs: object) -> None:
        pass


class _NoOpTracer:
    def start_as_current_span(
        self, name: str, *args: object, **kwargs: object
    ) -> _NoOpSpan:
        return _NoOpSpan()


tracer = _NoOpTracer()
