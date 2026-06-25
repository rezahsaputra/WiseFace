"""Shared test fixtures.

Tests run WITHOUT the heavy DeepFace/TensorFlow stack: the recognition engine is
mocked. We set credentials and skip model warmup before the app is imported.
"""
import io
import json
import os

import numpy as np
import pytest

# Configure the service for tests before any app import reads settings.
os.environ.setdefault("SKIP_MODEL_WARMUP", "1")
# Use a temp file so tests never touch /data (which may not exist in CI).
os.environ.setdefault("DB_PATH", "/tmp/wiseface_test.db")
os.environ.setdefault(
    "API_CREDENTIALS",
    json.dumps(
        [
            {"api_key": "key-a", "api_secret": "secret-a", "client": "attendance"},
            {"api_key": "key-b", "api_secret": "secret-b", "client": "other"},
        ]
    ),
)


@pytest.fixture
def jpeg_bytes() -> bytes:
    """A tiny valid JPEG, decodable by OpenCV."""
    from PIL import Image

    img = Image.new("RGB", (32, 32), color=(128, 64, 32))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def fake_embeddings(monkeypatch):
    """Patch the engine so `represent` returns deterministic vectors and no
    TensorFlow is needed. Returns a setter to control the next two embeddings."""
    import app.compare as compare

    state = {"vectors": [np.ones(512), np.ones(512)], "idx": 0}

    def fake_represent(img, settings, slot_name):
        v = state["vectors"][state["idx"] % len(state["vectors"])]
        state["idx"] += 1
        return np.asarray(v, dtype=np.float64)

    monkeypatch.setattr(compare, "represent", fake_represent)

    def set_vectors(v1, v2):
        state["vectors"] = [np.asarray(v1, dtype=np.float64), np.asarray(v2, dtype=np.float64)]
        state["idx"] = 0

    return set_vectors
