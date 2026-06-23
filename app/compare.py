"""Pipeline orchestration for a single comparison (PRD §4 steps 3-5).

This is the blocking, CPU-bound core. The FastAPI route offloads it to a
threadpool so a worker's event loop isn't blocked during inference.
"""
from __future__ import annotations

from .config import Settings
from .face_engine import (
    cosine_similarity,
    represent,
    similarity_to_confidence,
)
from .image_loader import ImageSlot, resolve_slot


def thresholds(settings: Settings) -> dict[str, float]:
    """Face++-shaped threshold tiers (structurally compatible, recalibrated)."""
    return {
        "1e-3": settings.threshold_1e_3,
        "1e-4": settings.threshold_1e_4,
        "1e-5": settings.threshold_1e_5,
    }


def run_comparison(
    slot1: ImageSlot, slot2: ImageSlot, settings: Settings
) -> float:
    """Resolve both slots, embed each face, return the confidence score.

    Raises CompareError (NO_FACE_DETECTED / INVALID_IMAGE / MISSING_ARGUMENTS /
    IMAGE_*) which the caller maps to a Face++-shaped error response. The
    decoded images and embeddings stay in memory and are discarded when this
    function returns (PRD §2 Data Handling).
    """
    img1 = resolve_slot(slot1, settings)
    emb1 = represent(img1, settings, slot1.name)

    img2 = resolve_slot(slot2, settings)
    emb2 = represent(img2, settings, slot2.name)

    similarity = cosine_similarity(emb1, emb2)
    return similarity_to_confidence(similarity, settings)
