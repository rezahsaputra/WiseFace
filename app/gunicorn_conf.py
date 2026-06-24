"""Gunicorn configuration (PRD §5 worker sizing, §9.5 concurrency).

10 Uvicorn workers is the RAM-derived ceiling on the 16 GB host, not the thread
ceiling. Each worker holds its own Facenet512 instance. One intra-op thread per
worker (OMP_NUM_THREADS=1) keeps the 10 workers from oversubscribing the 16
logical threads — leaving headroom for Nginx/Prometheus/Grafana/WSL2.
"""
import os

# Import at module load, NOT inside child_exit: child_exit runs from the SIGCHLD
# handler, and importing during signal handling can hit a partially-initialized
# module (circular import) and crash the arbiter.
try:
    from prometheus_client import multiprocess as _prom_multiprocess
except Exception:  # prometheus_client always present, but never crash the master
    _prom_multiprocess = None

# --- Workers ---
# Overridable via env so the same image can run on different hardware.
workers = int(os.environ.get("GUNICORN_WORKERS", "10"))
worker_class = "uvicorn.workers.UvicornWorker"
# NOTE: `threads` does not bound concurrency for the async UvicornWorker — the
# event loop offloads each compare to a threadpool. One-compare-at-a-time per
# worker is enforced in the app via an anyio CapacityLimiter (INFERENCE_CONCURRENCY,
# default 1); load shedding is bounded by MAX_CONCURRENT_REQUESTS. See app/main.py.
threads = 1

# --- Networking ---
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")

# --- Timeouts ---
# Generous vs. the 1.5s p95 target to absorb cold paths without killing workers.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "30"))
graceful_timeout = 30
keepalive = 5

# --- Recycle workers periodically to bound any slow memory creep ---
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "2000"))
max_requests_jitter = 200

# --- Logging ---
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOGLEVEL", "info")


def child_exit(server, worker):
    """Required for prometheus_client multiprocess mode: clean up the dead
    worker's metric files so /metrics doesn't double-count."""
    if _prom_multiprocess and os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        _prom_multiprocess.mark_process_dead(worker.pid)
