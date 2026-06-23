# syntax=docker/dockerfile:1
# Pinned base image (no `latest` in production, PRD §9.7).
FROM python:3.11-slim-bookworm

# --- Runtime env ---
# Keep every math library single-threaded per worker (PRD §9.5). 10 workers ×
# 1 thread fits the 16-logical-thread budget with headroom.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    TF_NUM_INTRAOP_THREADS=1 \
    TF_NUM_INTEROP_THREADS=1 \
    TF_CPP_MIN_LOG_LEVEL=2 \
    DEEPFACE_HOME=/home/app/.deepface \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc \
    # Abort a stalled download after 120s instead of hanging the whole build.
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# OpenCV (headless) still needs libGL + glib at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# --- Non-root runtime user ---
RUN useradd --create-home --uid 10001 app

WORKDIR /app

COPY requirements.txt .
# Cache-mount keeps downloaded wheels across build attempts, so a retry after a
# flaky-network failure doesn't re-download the whole ~500 MB ML stack.
# --retries lets pip recover from a stalled socket instead of giving up.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --retries 10 -r requirements.txt

COPY . /app/app
# Make the package importable as `app` (WORKDIR/app/app/__init__.py).
RUN mkdir -p "$PROMETHEUS_MULTIPROC_DIR" "$DEEPFACE_HOME" \
    && chown -R app:app /app "$PROMETHEUS_MULTIPROC_DIR" "$DEEPFACE_HOME"

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["gunicorn", "app.main:app", "-c", "app/gunicorn_conf.py"]
