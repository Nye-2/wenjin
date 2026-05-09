"""Wenjin observability metrics — spec §4.5.4 key metrics.

These are module-level Prometheus objects initialised once at import time.
The prometheus_client library deduplicates registrations, so it is safe to
import this module multiple times.
"""

from prometheus_client import Counter, Gauge, Histogram

# SSE first-frame latency for execution streams
execution_stream_latency = Histogram(
    "execution_stream_latency_seconds",
    "SSE first-frame latency",
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0],
)

# Chat agent first-token latency
chat_agent_response_latency = Histogram(
    "chat_agent_response_latency_seconds",
    "Chat agent first-token latency",
    buckets=[0.1, 0.3, 0.5, 1.0, 2.0, 5.0],
)

# Per-node execution time, labelled by node type
execution_node_duration = Histogram(
    "execution_node_duration_seconds",
    "Per-node execution time",
    labelnames=["node_type"],
)

# Resolver cache hit / miss (label value "hit" or "miss")
capability_resolve_cache_hit = Counter(
    "capability_resolve_cache_hit_total",
    "Resolver cache hit/miss count",
    labelnames=["hit"],
)

# Dispatch rejected because lead is busy
lead_agent_busy_rejection = Counter(
    "lead_agent_busy_rejection_total",
    "Dispatch rejected because lead is busy",
)

# Auto-compact trigger counter
auto_compact_trigger = Counter(
    "auto_compact_trigger_total",
    "Auto-compact triggers",
)
