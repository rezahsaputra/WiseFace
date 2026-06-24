"""Image loading + Face++ precedence resolution (PRD §3 / §8 unit tests)."""
import base64

import cv2
import numpy as np
import pytest

from app import errors
from app.config import Settings, get_settings
from app.image_loader import ImageSlot, resolve_slot


def _encode_jpeg(height: int, width: int) -> bytes:
    """A uniform JPEG of the given dimensions (decodes back to height x width)."""
    img = np.full((height, width, 3), 127, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


@pytest.fixture
def settings():
    return get_settings()


def test_decode_valid_file(settings, jpeg_bytes):
    slot = ImageSlot(name="image1", image_file=jpeg_bytes)
    img = resolve_slot(slot, settings)
    assert img.shape == (32, 32, 3)


def test_decode_valid_base64(settings, jpeg_bytes):
    b64 = base64.b64encode(jpeg_bytes).decode()
    slot = ImageSlot(name="image1", image_base64=b64)
    img = resolve_slot(slot, settings)
    assert img.shape[2] == 3


def test_base64_data_uri_prefix(settings, jpeg_bytes):
    b64 = "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode()
    slot = ImageSlot(name="image1", image_base64=b64)
    img = resolve_slot(slot, settings)
    assert img.size > 0


def test_precedence_file_over_base64_over_url(settings, jpeg_bytes):
    # file present alongside base64+url -> file wins (no network call attempted).
    slot = ImageSlot(
        name="image1",
        image_file=jpeg_bytes,
        image_base64="not-real-base64",
        image_url="http://example.invalid/x.jpg",
    )
    img = resolve_slot(slot, settings)  # must not raise / must not fetch URL
    assert img.shape == (32, 32, 3)


def test_precedence_base64_over_url(settings, jpeg_bytes):
    b64 = base64.b64encode(jpeg_bytes).decode()
    slot = ImageSlot(
        name="image1",
        image_base64=b64,
        image_url="http://example.invalid/x.jpg",
    )
    img = resolve_slot(slot, settings)  # base64 used, URL never fetched
    assert img.size > 0


def test_invalid_image_bytes_raises(settings):
    slot = ImageSlot(name="image1", image_file=b"this is not an image")
    with pytest.raises(errors.CompareError) as exc:
        resolve_slot(slot, settings)
    assert exc.value.error_message == errors.INVALID_IMAGE


def test_missing_arguments_raises(settings):
    slot = ImageSlot(name="image1")  # nothing supplied
    with pytest.raises(errors.CompareError) as exc:
        resolve_slot(slot, settings)
    assert exc.value.error_message == errors.MISSING_ARGUMENTS


def test_face_token_only_is_missing_arguments(settings):
    # face_token is unsupported in v1 -> treated as no usable image.
    slot = ImageSlot(name="image1", face_token="tok_123")
    with pytest.raises(errors.CompareError) as exc:
        resolve_slot(slot, settings)
    assert exc.value.error_message == errors.MISSING_ARGUMENTS


# --- Input downscaling (throughput fix): big phone photos are scaled down
# before detection, which dominates CPU cost on large inputs. -----------------
def test_large_image_downscaled_to_max_dim():
    s = Settings(max_image_dim=100)
    slot = ImageSlot(name="image1", image_file=_encode_jpeg(400, 200))
    img = resolve_slot(slot, s)
    # Longest side clamped to max_image_dim, aspect ratio preserved (400x200 -> 100x50).
    assert max(img.shape[0], img.shape[1]) == 100
    assert img.shape[0] == 100 and img.shape[1] == 50


def test_small_image_not_upscaled():
    s = Settings(max_image_dim=1000)
    slot = ImageSlot(name="image1", image_file=_encode_jpeg(400, 200))
    img = resolve_slot(slot, s)
    assert img.shape[0] == 400 and img.shape[1] == 200


def test_downscale_disabled_when_zero():
    s = Settings(max_image_dim=0)
    slot = ImageSlot(name="image1", image_file=_encode_jpeg(400, 200))
    img = resolve_slot(slot, s)
    assert img.shape[0] == 400 and img.shape[1] == 200
