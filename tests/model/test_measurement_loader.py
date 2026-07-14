"""Tests for the MeasurementLoader protocol (#147)."""

from __future__ import annotations

from mdf_viewer.model.mdf_loader import MdfLoader
from mdf_viewer.model.measurement_loader import MeasurementLoader
from mdf_viewer.model.virtual_measurement_loader import VirtualMeasurementLoader


def test_mdf_loader_satisfies_measurement_loader_protocol() -> None:
    assert isinstance(MdfLoader(), MeasurementLoader)


def test_virtual_measurement_loader_satisfies_measurement_loader_protocol() -> None:
    assert isinstance(VirtualMeasurementLoader(owner_plugin="test_plugin"), MeasurementLoader)


def test_mdf_loader_path_is_none_before_open() -> None:
    assert MdfLoader().path is None
