"""Wenjin observability metrics — spec §4.5.4 key metrics.

These are module-level Prometheus objects initialised once at import time.
The prometheus_client library deduplicates registrations, so it is safe to
import this module multiple times.
"""

from prometheus_client import Counter, Histogram

# SSE first-frame latency for Mission streams
mission_stream_latency = Histogram(
    "mission_stream_latency_seconds",
    "Mission SSE first-frame latency",
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0],
)

# WorkspaceAgent first-token latency
workspace_agent_response_latency = Histogram(
    "workspace_agent_response_latency_seconds",
    "WorkspaceAgent first-token latency",
    buckets=[0.1, 0.3, 0.5, 1.0, 2.0, 5.0],
)

# Mission slice duration, labelled by outcome
mission_slice_duration = Histogram(
    "mission_slice_duration_seconds",
    "Mission runtime slice duration",
    labelnames=["outcome"],
)

# Auto-compact trigger counter
auto_compact_trigger = Counter(
    "auto_compact_trigger_total",
    "Auto-compact triggers",
)
