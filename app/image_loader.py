"""Resolve a Face++-style image slot into an in-memory BGR ndarray.

Precedence per slot (PRD §3 / §5.1, identical to Face++):
    image_file  >  image_base64  >  image_url

`face_token` is intentionally NOT implemented in v1 (PRD §5.1) — if a slot
supplies only a face_token it is treated as "no usable image" and raises
MISSING_ARGUMENTS.

Images are decoded in memory and never written to disk (PRD §2 Data Handling).
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Optional

import cv2
import httpx
import numpy as np

from . import errors
from .config import Settings


@dataclass
class ImageSlot:
    """The raw inputs for one image slot, before resolution."""

    name: str  # "image1" | "image2"
    image_file: Optional[bytes] = None
    image_base64: Optional[str] = None
    image_url: Optional[str] = None
    face_token: Optional[str] = None

    def has_any_input(self) -> bool:
        return bool(
            self.image_file or self.image_base64 or self.image_url or self.face_token
        )


def _maybe_downscale(img: np.ndarray, settings: Settings) -> np.ndarray:
    """Scale `img` down so its longest side is <= settings.max_image_dim.

    Detection cost scales with pixel count; the detected face is resized to the
    model's 160px input anyway, so shrinking oversized inputs cuts CPU with no
    meaningful accuracy loss. Never upscales. Disabled when max_image_dim <= 0.
    """
    max_dim = settings.max_image_dim
    if max_dim <= 0:
        return img
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest <= max_dim:
        return img
    scale = max_dim / longest
    new_w = max(1, round(w * scale))
    new_h = max(1, round(h * scale))
    # INTER_AREA is the recommended filter for shrinking.
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)


def _decode_bytes(buf: bytes, settings: Settings, slot_name: str) -> np.ndarray:
    """Decode raw image bytes to a BGR ndarray, or raise INVALID_IMAGE."""
    if not buf:
        raise errors.CompareError(errors.INVALID_IMAGE)
    arr = np.frombuffer(buf, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None or img.size == 0:
        raise errors.CompareError(errors.INVALID_IMAGE)
    return _maybe_downscale(img, settings)


def _from_base64(data: str, settings: Settings, slot_name: str) -> np.ndarray:
    # Tolerate data-URI prefixes ("data:image/jpeg;base64,....").
    if "," in data and data.lstrip().lower().startswith("data:"):
        data = data.split(",", 1)[1]
    try:
        raw = base64.b64decode(data, validate=False)
    except (binascii.Error, ValueError):
        raise errors.CompareError(errors.INVALID_IMAGE)
    if len(raw) > settings.max_image_bytes:
        raise errors.CompareError(errors.IMAGE_TOO_LARGE)
    return _decode_bytes(raw, settings, slot_name)


def _from_url(url: str, settings: Settings, slot_name: str) -> np.ndarray:
    try:
        with httpx.Client(
            timeout=settings.image_download_timeout_s, follow_redirects=True
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            raw = resp.content
    except httpx.HTTPError:
        raise errors.CompareError(errors.IMAGE_DOWNLOAD_FAILED)
    if len(raw) > settings.max_image_bytes:
        raise errors.CompareError(errors.IMAGE_TOO_LARGE)
    return _decode_bytes(raw, settings, slot_name)


def _from_file(buf: bytes, settings: Settings, slot_name: str) -> np.ndarray:
    if len(buf) > settings.max_image_bytes:
        raise errors.CompareError(errors.IMAGE_TOO_LARGE)
    return _decode_bytes(buf, settings, slot_name)


def resolve_slot(slot: ImageSlot, settings: Settings) -> np.ndarray:
    """Apply Face++ precedence and return a decoded BGR image for the slot.

    Raises MISSING_ARGUMENTS if the slot has no usable image input.
    """
    if slot.image_file is not None:
        return _from_file(slot.image_file, settings, slot.name)
    if slot.image_base64:
        return _from_base64(slot.image_base64, settings, slot.name)
    if slot.image_url:
        return _from_url(slot.image_url, settings, slot.name)
    # Only a face_token (unsupported in v1) or nothing at all was supplied.
    raise errors.missing_arguments(slot.name)
