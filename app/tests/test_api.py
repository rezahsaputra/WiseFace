"""API contract tests for the Face++-compatible endpoint (PRD §8).

The recognition engine is mocked (see conftest.fake_embeddings), so these run
without TensorFlow. They assert the wire contract, auth, error shapes, and that
no employee/identity parameter is ever required.
"""
import base64

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import errors
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _auth():
    return {"api_key": "key-a", "api_secret": "secret-a"}


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_compare_success_shape(client, jpeg_bytes, fake_embeddings):
    fake_embeddings(np.ones(512), np.ones(512))  # identical -> high confidence
    b64 = base64.b64encode(jpeg_bytes).decode()
    r = client.post(
        "/facepp/v3/compare",
        data={**_auth(), "image_base64_1": b64, "image_base64_2": b64},
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"confidence", "thresholds", "request_id", "time_used"}
    assert body["confidence"] == 100.0  # cos sim 1.0 * scale 100
    assert set(body["thresholds"]) == {"1e-3", "1e-4", "1e-5"}
    assert isinstance(body["time_used"], int)


def test_v3_alias_works(client, jpeg_bytes, fake_embeddings):
    fake_embeddings(np.ones(512), np.ones(512))
    b64 = base64.b64encode(jpeg_bytes).decode()
    r = client.post(
        "/v3/compare",
        data={**_auth(), "image_base64_1": b64, "image_base64_2": b64},
    )
    assert r.status_code == 200


def test_auth_failure(client, jpeg_bytes):
    b64 = base64.b64encode(jpeg_bytes).decode()
    r = client.post(
        "/facepp/v3/compare",
        data={"api_key": "key-a", "api_secret": "wrong", "image_base64_1": b64, "image_base64_2": b64},
    )
    assert r.status_code == 401
    assert r.json()["error_message"] == errors.AUTHENTICATION_ERROR


def test_missing_image_argument(client, jpeg_bytes, fake_embeddings):
    fake_embeddings(np.ones(512), np.ones(512))
    b64 = base64.b64encode(jpeg_bytes).decode()
    r = client.post(
        "/facepp/v3/compare",
        data={**_auth(), "image_base64_1": b64},  # image2 missing
    )
    assert r.status_code == 400
    assert r.json()["error_message"] == errors.MISSING_ARGUMENTS


def test_invalid_image(client, fake_embeddings):
    fake_embeddings(np.ones(512), np.ones(512))
    bad = base64.b64encode(b"not an image").decode()
    r = client.post(
        "/facepp/v3/compare",
        data={**_auth(), "image_base64_1": bad, "image_base64_2": bad},
    )
    assert r.status_code == 400
    assert r.json()["error_message"] == errors.INVALID_IMAGE


def test_no_face_detected(client, jpeg_bytes, monkeypatch):
    import app.compare as compare

    def raise_no_face(img, settings, slot_name):
        raise errors.CompareError(errors.NO_FACE_DETECTED)

    monkeypatch.setattr(compare, "represent", raise_no_face)
    b64 = base64.b64encode(jpeg_bytes).decode()
    r = client.post(
        "/facepp/v3/compare",
        data={**_auth(), "image_base64_1": b64, "image_base64_2": b64},
    )
    assert r.status_code == 400
    assert r.json()["error_message"] == errors.NO_FACE_DETECTED


def test_file_upload_takes_precedence_over_base64(client, jpeg_bytes, fake_embeddings):
    # Supply both file and a bogus base64; file precedence means success.
    fake_embeddings(np.ones(512), np.ones(512))
    r = client.post(
        "/facepp/v3/compare",
        data={**_auth(), "image_base64_1": "garbage", "image_base64_2": "garbage"},
        files={
            "image_file1": ("a.jpg", jpeg_bytes, "image/jpeg"),
            "image_file2": ("b.jpg", jpeg_bytes, "image/jpeg"),
        },
    )
    assert r.status_code == 200


def test_metrics_endpoint(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "facecompare_requests_total" in r.text


def test_no_identity_param_accepted(client, jpeg_bytes, fake_embeddings):
    # An employee_id param must be silently ignored, never required or used.
    fake_embeddings(np.ones(512), np.ones(512))
    b64 = base64.b64encode(jpeg_bytes).decode()
    r = client.post(
        "/facepp/v3/compare",
        data={**_auth(), "image_base64_1": b64, "image_base64_2": b64, "employee_id": "E123"},
    )
    assert r.status_code == 200
    assert "employee_id" not in r.json()
