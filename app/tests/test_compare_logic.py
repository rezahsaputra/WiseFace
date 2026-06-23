"""Similarity + confidence calibration math (PRD §8 unit tests)."""
import numpy as np

from app.config import get_settings
from app.face_engine import cosine_similarity, similarity_to_confidence


def test_identical_vectors_similarity_one():
    v = np.array([1.0, 2.0, 3.0])
    assert cosine_similarity(v, v) == 1.0


def test_orthogonal_vectors_similarity_zero():
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert abs(cosine_similarity(a, b)) < 1e-9


def test_zero_vector_safe():
    a = np.zeros(4)
    b = np.ones(4)
    assert cosine_similarity(a, b) == 0.0


def test_confidence_clamped_0_100():
    settings = get_settings()
    assert similarity_to_confidence(1.0, settings) <= 100.0
    assert similarity_to_confidence(-1.0, settings) >= 0.0


def test_confidence_rounded_3_decimals():
    settings = get_settings()
    conf = similarity_to_confidence(0.123456, settings)
    # at most 3 decimal places
    assert round(conf, 3) == conf
