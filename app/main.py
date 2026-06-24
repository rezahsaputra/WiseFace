"""FastAPI application exposing the Face++-compatible compare API.

Endpoints:
  POST /facepp/v3/compare   - Face++ Compare-shaped endpoint (primary)
  POST /v3/compare          - alias for the same handler
  GET  /health              - liveness/readiness for Docker healthcheck
  GET  /metrics             - Prometheus scrape target

The service is stateless: no database, no employee/identity concept, no image
persistence (PRD §2, §6).
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import anyio
from anyio import CapacityLimiter
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from . import errors, metrics
from .compare import run_comparison, thresholds
from .config import Credential, get_settings
from .face_engine import warmup
from .image_loader import ImageSlot

logger = logging.getLogger("facecompare")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    app.state.settings = settings
    app.state.credentials = settings.load_credentials()
    # Serialize inference within this worker. The default of 1 closes the
    # OpenCV CascadeClassifier thread-safety race (cv2 getScaleData crash) that
    # surfaces under burst, since starlette's default threadpool would otherwise
    # run many compares per worker at once. True parallelism is the worker count.
    app.state.inference_limiter = CapacityLimiter(settings.inference_concurrency)
    # Per-worker load-shedding: bound how many compares a worker will hold
    # (running + queued) before returning CONCURRENCY_LIMIT_EXCEEDED.
    app.state.inflight = 0
    app.state.max_inflight = settings.max_concurrent_requests
    # Preload the model so the first real request doesn't pay cold-start cost.
    # Skipped when SKIP_MODEL_WARMUP is set (tests / fast local boots).
    if not os.environ.get("SKIP_MODEL_WARMUP"):
        await run_in_threadpool(warmup, settings)
    yield


app = FastAPI(
    title="Self-Hosted Face Compare API",
    version="1.0.0",
    description="Face++ Compare API drop-in replacement (stateless, image-pair only).",
    lifespan=lifespan,
)


# --------------------------------------------------------------------------- #
# Request parsing                                                             #
# --------------------------------------------------------------------------- #
async def _parse_request(request: Request) -> tuple[str, str, ImageSlot, ImageSlot]:
    """Pull Face++ parameters from the request into typed inputs.

    Credentials follow the Face++ convention — passed as query parameters:
      ?api_key=...&api_secret=...

    Image fields arrive as multipart/form-data (file uploads),
    application/x-www-form-urlencoded, or also query string.
    """
    query = request.query_params
    form = {}
    files: dict[str, bytes] = {}
    content_type = request.headers.get("content-type", "")
    if content_type.startswith(("multipart/form-data", "application/x-www-form-urlencoded")):
        raw_form = await request.form()
        for key, value in raw_form.multi_items():
            if hasattr(value, "read"):  # UploadFile
                files[key] = await value.read()
            else:
                form[key] = value

    def get(name: str) -> Optional[str]:
        return query.get(name) or form.get(name)

    api_key = get("api_key") or ""
    api_secret = get("api_secret") or ""

    slot1 = ImageSlot(
        name="image1",
        image_file=files.get("image_file1"),
        image_base64=get("image_base64_1"),
        image_url=get("image_url1"),
        face_token=get("face_token1"),
    )
    slot2 = ImageSlot(
        name="image2",
        image_file=files.get("image_file2"),
        image_base64=get("image_base64_2"),
        image_url=get("image_url2"),
        face_token=get("face_token2"),
    )
    return api_key, api_secret, slot1, slot2


def _authenticate(request: Request, api_key: str, api_secret: str) -> Credential:
    creds: dict[str, Credential] = request.app.state.credentials
    cred = creds.get(api_key)
    if cred is None or cred.api_secret != api_secret:
        raise errors.auth_error()
    return cred


def _error_response(err: errors.CompareError, request_id: str, started: float) -> JSONResponse:
    time_used = int((time.perf_counter() - started) * 1000)
    return JSONResponse(
        status_code=err.http_status,
        content={
            "error_message": err.error_message,
            "request_id": request_id,
            "time_used": time_used,
        },
    )


# --------------------------------------------------------------------------- #
# Routes                                                                      #
# --------------------------------------------------------------------------- #
async def _compare(request: Request, endpoint: str) -> Response:
    started = time.perf_counter()
    request_id = str(uuid.uuid4())
    state = request.app.state
    settings = state.settings
    client_label = "unknown"

    # Shed load fast if this worker is already saturated, so a burst degrades to
    # retryable rejections instead of requests queueing past the 30s timeout.
    if state.max_inflight and state.inflight >= state.max_inflight:
        metrics.REQUESTS.labels(
            client_label, endpoint, errors.CONCURRENCY_LIMIT_EXCEEDED
        ).inc()
        return _error_response(errors.concurrency_limit_error(), request_id, started)

    state.inflight += 1
    try:
        api_key, api_secret, slot1, slot2 = await _parse_request(request)
        cred = _authenticate(request, api_key, api_secret)
        client_label = cred.client

        # Offload the blocking CPU-bound pipeline off the event loop, capped by
        # the inference limiter so a worker runs one compare at a time (default).
        confidence = await anyio.to_thread.run_sync(
            run_comparison, slot1, slot2, settings, limiter=state.inference_limiter
        )

        time_used = int((time.perf_counter() - started) * 1000)
        metrics.REQUESTS.labels(client_label, endpoint, "success").inc()
        metrics.LATENCY.labels(endpoint).observe(time.perf_counter() - started)
        metrics.CONFIDENCE.labels(client_label).observe(confidence)
        return JSONResponse(
            content={
                "confidence": confidence,
                "thresholds": thresholds(settings),
                "request_id": request_id,
                "time_used": time_used,
            }
        )

    except errors.CompareError as err:
        metrics.REQUESTS.labels(client_label, endpoint, err.error_message).inc()
        metrics.LATENCY.labels(endpoint).observe(time.perf_counter() - started)
        return _error_response(err, request_id, started)

    except Exception:  # noqa: BLE001 - last-resort guard, must not leak details
        logger.exception("Unhandled error in compare (request_id=%s)", request_id)
        metrics.REQUESTS.labels(client_label, endpoint, errors.INTERNAL_ERROR).inc()
        metrics.LATENCY.labels(endpoint).observe(time.perf_counter() - started)
        return _error_response(
            errors.CompareError(errors.INTERNAL_ERROR, http_status=500),
            request_id,
            started,
        )

    finally:
        state.inflight -= 1


@app.post("/facepp/v3/compare")
async def facepp_compare(request: Request) -> Response:
    return await _compare(request, "/facepp/v3/compare")


@app.post("/v3/compare")
async def compare_alias(request: Request) -> Response:
    return await _compare(request, "/v3/compare")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
async def metrics_endpoint() -> Response:
    payload, content_type = metrics.render_latest()
    return Response(content=payload, media_type=content_type)
