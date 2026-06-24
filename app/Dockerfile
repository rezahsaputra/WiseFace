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
#
# deepface (and its retina-face / mtcnn deps) require the `tensorflow`
# distribution, which on Linux is the GPU build: pip installs it ALONGSIDE our
# pinned tensorflow-cpu and drags in ~3 GB of `nvidia-*` CUDA wheels we never
# use. `tensorflow` and `tensorflow-cpu` are different distributions that ship
# the SAME `tensorflow/` package, so pip can't dedupe them by resolution. We
# fix the end state in this one layer instead:
#   1. install everything (tensorflow + tensorflow-cpu both land);
#   2. drop the GPU `tensorflow` distribution — this also deletes the shared
#      `tensorflow/` files, since they're recorded under its dist-info;
#   3. force-reinstall tensorflow-cpu (--no-deps, from cache) to restore those
#      files without the GPU distribution;
#   4. purge the now-orphaned nvidia CUDA wheels (pip doesn't drop them on its
#      own). tensorflow-cpu has no nvidia deps, so this is safe.
# `import tensorflow` still works (provided by tensorflow-cpu); `pip check` will
# note deepface/retina-face/mtcnn "require tensorflow" by dist name — that's
# expected and harmless, so we don't run it here.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --retries 10 -r requirements.txt \
    && pip uninstall -y tensorflow \
    && pip install --retries 10 --no-deps --force-reinstall tensorflow-cpu==2.18.0 \
    && { pip freeze | grep -i '^nvidia-' || true; } > /tmp/nvidia-cuda.txt \
    && if [ -s /tmp/nvidia-cuda.txt ]; then pip uninstall -y -r /tmp/nvidia-cuda.txt; fi \
    && rm -f /tmp/nvidia-cuda.txt \
    && python -c "import tensorflow as tf; print('tensorflow-cpu OK', tf.__version__)"

COPY . /app/app
# Make the package importable as `app` (WORKDIR/app/app/__init__.py).
RUN mkdir -p "$PROMETHEUS_MULTIPROC_DIR" "$DEEPFACE_HOME" \
    && chown -R app:app /app "$PROMETHEUS_MULTIPROC_DIR" "$DEEPFACE_HOME"

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["gunicorn", "app.main:app", "-c", "app/gunicorn_conf.py"]
