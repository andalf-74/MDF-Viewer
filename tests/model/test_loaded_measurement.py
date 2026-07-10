"""Tests for LoadedMeasurement and make_label (#101)."""

from __future__ import annotations

import pytest

from mdf_viewer.model.loaded_measurement import LoadedMeasurement, make_label
from mdf_viewer.model.mdf_loader import MdfLoader
from mdf_viewer.model.measurement import MeasurementInfo


@pytest.mark.requirement("REQ-FILE-027")
def test_make_label_uses_file_stem() -> None:
    assert make_label("C:/data/run1.mf4", []) == "run1"


@pytest.mark.requirement("REQ-FILE-027")
def test_make_label_disambiguates_collision() -> None:
    assert make_label("C:/data/run1.mf4", ["run1"]) == "run1 (2)"


@pytest.mark.requirement("REQ-FILE-027")
def test_make_label_disambiguates_multiple_collisions() -> None:
    label = make_label("run1.mf4", ["run1", "run1 (2)", "run1 (3)"])
    assert label == "run1 (4)"


@pytest.mark.requirement("REQ-FILE-027")
def test_make_label_ignores_unrelated_existing_labels() -> None:
    assert make_label("run1.mf4", ["other", "another"]) == "run1"


def test_offset_defaults_to_zero() -> None:
    measurement = LoadedMeasurement(
        loader=MdfLoader(), info=MeasurementInfo(file_name="run1.mf4"), label="run1",
    )
    assert measurement.offset_s == 0.0


def test_offset_is_mutable() -> None:
    measurement = LoadedMeasurement(
        loader=MdfLoader(), info=MeasurementInfo(file_name="run1.mf4"), label="run1",
    )
    measurement.offset_s = 5.0
    assert measurement.offset_s == 5.0
