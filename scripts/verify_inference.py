"""Real end-to-end inference check (not mocked).

Runs the actual pipeline — image_loader -> face_engine (Facenet512) -> cosine ->
calibration — on real face images, and prints the confidence for each pair.

Usage (inside the face-compare-api image, repo mounted at /work):
    PYTHONPATH=/work python scripts/verify_inference.py img_a.jpg img_b.jpg ...

It compares every image against the first one and prints confidence scores.
Sanity expectations:
  - an image vs. itself  -> confidence ~100 (embedding consistency)
  - same person          -> higher than different person
"""
from __future__ import annotations

import sys

from app.config import get_settings
from app.face_engine import cosine_similarity, represent, similarity_to_confidence
from app.image_loader import ImageSlot, resolve_slot


def embed(path: str, settings, slot_name: str):
    with open(path, "rb") as f:
        slot = ImageSlot(name=slot_name, image_file=f.read())
    img = resolve_slot(slot, settings)
    return represent(img, settings, slot_name)


def main(paths: list[str]) -> int:
    if len(paths) < 2:
        print("need at least 2 image paths")
        return 2

    settings = get_settings()
    print(f"model={settings.model_name} detector={settings.detector_backend} "
          f"calibration={settings.calibration_method}")

    ref = embed(paths[0], settings, "image1")
    print(f"\nreference: {paths[0]}")
    for p in paths:
        emb = embed(p, settings, "image2")
        sim = cosine_similarity(ref, emb)
        conf = similarity_to_confidence(sim, settings)
        print(f"  vs {p:<28} cosine={sim:6.3f}  confidence={conf:7.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
