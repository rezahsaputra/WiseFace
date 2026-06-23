"""Face detection + embedding + similarity, wrapping DeepFace/Facenet512.

DeepFace (and TensorFlow) are imported lazily so the pure-logic modules and the
test suite can run without the heavy ML stack installed. Production loads the
model once per worker at startup via `warmup()`.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

import numpy as np

from . import errors
from .calibration import Calibrator
from .config import Settings

logger = logging.getLogger("facecompare.engine")

_model_lock = threading.Lock()
_model_loaded = False


def warmup(settings: Settings) -> None:
    """Force the recognition model to load into this process's memory.

    Called once at worker startup so the first real request doesn't eat the
    cold-load latency. Each Gunicorn worker holds its own model instance
    (~500-600 MB for Facenet512) — see PRD §5 memory budget.
    """
    global _model_loaded
    with _model_lock:
        if _model_loaded:
            return
        from deepface import DeepFace  # noqa: WPS433 (lazy import by design)

        DeepFace.build_model(settings.model_name)
        _model_loaded = True
        logger.info("Recognition model %s loaded.", settings.model_name)


def represent(img: np.ndarray, settings: Settings, slot_name: str) -> np.ndarray:
    """Detect+align a face in `img` and return its embedding vector.

    Raises NO_FACE_DETECTED if no face is found, INVALID_IMAGE if DeepFace
    rejects the input for any other reason.
    """
    from deepface import DeepFace  # lazy import

    try:
        reps = DeepFace.represent(
            img_path=img,  # DeepFace accepts a BGR ndarray directly
            model_name=settings.model_name,
            detector_backend=settings.detector_backend,
            enforce_detection=True,
            align=settings.align,
        )
    except ValueError as exc:
        # DeepFace raises ValueError("Face could not be detected ...") when
        # enforce_detection=True and no face is present.
        msg = str(exc).lower()
        if "face could not be detected" in msg or "could not be detected" in msg:
            raise errors.CompareError(errors.NO_FACE_DETECTED)
        raise errors.CompareError(errors.INVALID_IMAGE)

    if not reps:
        raise errors.CompareError(errors.NO_FACE_DETECTED)

    # DeepFace returns a list (one entry per detected face). The compare
    # contract uses the most prominent face; DeepFace orders by detection,
    # so take the first.
    embedding = np.asarray(reps[0]["embedding"], dtype=np.float64)
    return embedding


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def similarity_to_confidence(similarity: float, settings: Settings) -> float:
    """Map cosine similarity to a 0-100 Face++-style confidence.

    Delegates to the configured Calibrator (linear or logistic). The default
    params are PLACEHOLDERs — replace with the Milestone 0 calibration so
    confidence and thresholds are on the same scale.
    """
    calibrator = Calibrator(
        method=settings.calibration_method,
        scale=settings.confidence_scale,
        offset=settings.confidence_offset,
        midpoint=settings.logistic_midpoint,
        steepness=settings.logistic_steepness,
    )
    return calibrator.confidence(similarity)
