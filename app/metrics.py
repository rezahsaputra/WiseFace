"""Prometheus instrumentation (PRD §3 / §4 step 6).

Metrics carry NO image data and NO employee/identity data — only operational
labels: the calling client (a config label), the endpoint, and the outcome.

Multiprocess note: Gunicorn runs many worker processes. prometheus_client must
run in multiprocess mode so /metrics aggregates across all workers. This
requires PROMETHEUS_MULTIPROC_DIR to be set (see gunicorn_conf.py / Dockerfile).
When that env var is unset (e.g. tests, single-process dev) we fall back to the
default in-process registry transparently.
"""
from __future__ import annotations

import os

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)

# Request volume, labeled by calling client and outcome (success / error code).
REQUESTS = Counter(
    "facecompare_requests_total",
    "Total compare requests.",
    ["client", "endpoint", "outcome"],
)

# End-to-end latency per endpoint (seconds). Buckets sized around the
# p95 < 1.5s target (PRD §2 Latency).
LATENCY = Histogram(
    "facecompare_request_latency_seconds",
    "Compare request latency in seconds.",
    ["endpoint"],
    buckets=(0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 5.0),
)

# Confidence score distribution for successful comparisons (0-100).
CONFIDENCE = Histogram(
    "facecompare_confidence_score",
    "Returned confidence score (successful comparisons only).",
    ["client"],
    buckets=(0, 10, 20, 30, 40, 50, 60, 70, 75, 80, 85, 90, 95, 100),
)


def render_latest() -> tuple[bytes, str]:
    """Return (payload, content_type) for the /metrics endpoint.

    In multiprocess mode we build a fresh registry that merges every worker's
    metric files; otherwise we use the default global registry.
    """
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry), CONTENT_TYPE_LATEST
    return generate_latest(), CONTENT_TYPE_LATEST
