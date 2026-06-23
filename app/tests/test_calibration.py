"""TDD spec for the confidence calibration module.

Calibration converts a cosine similarity (roughly -1..1, realistically 0..1 for
face pairs) into a Face++-style 0..100 confidence. This is where the Milestone 0
FAR/FRR-derived mapping plugs in, so it must support more than a raw affine:
a logistic (S-curve) mapping is the expected production form.

These tests are written before `app.calibration` exists (red first).
"""
import math

import pytest

from app.calibration import Calibrator


# --- linear method -------------------------------------------------------- #
def test_linear_identity():
    c = Calibrator(method="linear", scale=100.0, offset=0.0)
    assert c.confidence(0.8) == 80.0


def test_linear_offset():
    c = Calibrator(method="linear", scale=100.0, offset=5.0)
    assert c.confidence(0.5) == 55.0


def test_linear_clamped_high():
    c = Calibrator(method="linear", scale=100.0, offset=0.0)
    assert c.confidence(1.5) == 100.0


def test_linear_clamped_low():
    c = Calibrator(method="linear", scale=100.0, offset=0.0)
    assert c.confidence(-0.5) == 0.0


# --- logistic method ------------------------------------------------------ #
def test_logistic_midpoint_is_fifty():
    c = Calibrator(method="logistic", midpoint=0.5, steepness=10.0)
    assert c.confidence(0.5) == 50.0


def test_logistic_monotonic_increasing():
    c = Calibrator(method="logistic", midpoint=0.5, steepness=10.0)
    xs = [0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0]
    ys = [c.confidence(x) for x in xs]
    assert ys == sorted(ys)
    assert len(set(ys)) > 1  # not flat


def test_logistic_bounded_0_100():
    c = Calibrator(method="logistic", midpoint=0.5, steepness=10.0)
    assert 0.0 <= c.confidence(-5.0) <= 100.0
    assert 0.0 <= c.confidence(5.0) <= 100.0


def test_logistic_saturates_high_and_low():
    c = Calibrator(method="logistic", midpoint=0.5, steepness=12.0)
    assert c.confidence(5.0) > 99.0
    assert c.confidence(-5.0) < 1.0


# --- common behavior ------------------------------------------------------ #
def test_confidence_rounded_3_decimals():
    c = Calibrator(method="logistic", midpoint=0.5, steepness=7.3)
    val = c.confidence(0.6137)
    assert round(val, 3) == val


def test_unknown_method_rejected():
    with pytest.raises(ValueError):
        Calibrator(method="bogus").confidence(0.5)
