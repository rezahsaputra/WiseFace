"""Cosine-similarity -> 0..100 confidence calibration.

This is where the Milestone 0 FAR/FRR-derived mapping lives. Two methods:

- ``linear``  : affine ``similarity * scale + offset`` (simple placeholder).
- ``logistic``: an S-curve ``100 / (1 + e^(-k(sim - m)))`` — the expected
  production form, since face-pair similarity separates non-linearly around a
  decision midpoint.

Both clamp to [0, 100] and round to 3 decimals to match Face++'s ``confidence``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Calibrator:
    method: str = "linear"
    # linear params
    scale: float = 100.0
    offset: float = 0.0
    # logistic params
    midpoint: float = 0.5
    steepness: float = 10.0

    def confidence(self, similarity: float) -> float:
        if self.method == "linear":
            raw = similarity * self.scale + self.offset
        elif self.method == "logistic":
            # Clamp the exponent to avoid OverflowError on extreme inputs.
            z = max(-700.0, min(700.0, -self.steepness * (similarity - self.midpoint)))
            raw = 100.0 / (1.0 + math.exp(z))
        else:
            raise ValueError(f"unknown calibration method: {self.method!r}")

        raw = max(0.0, min(100.0, raw))
        return round(raw, 3)
